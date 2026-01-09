/**
 * Radio Command for Karma Logger
 * Phase 3: CLI interface for agent coordination (hooks integration)
 */

import { Command } from 'commander';
import { readFileSync } from 'node:fs';
import {
  RadioClient,
  RadioServerNotRunningError,
  RadioTimeoutError,
  RadioServerError,
  SubscriptionError,
  createRadioClient,
} from '../walkie-talkie/socket-client.js';
import type { RadioEnv, AgentState, AgentStatus, ProgressUpdate, ValidationMode } from '../walkie-talkie/types.js';
import {
  createSubagentWatcher,
  scanSubagents,
  formatAgentsTable,
  formatAgentsJson,
  type SubagentInfo,
} from '../walkie-talkie/subagent-watcher.js';
import { homedir } from 'node:os';
import { join, basename } from 'node:path';
import { existsSync, readdirSync } from 'node:fs';

// ============================================
// Exit Codes
// ============================================

/** Successful execution */
export const EXIT_SUCCESS = 0;
/** Timeout or operation failure */
export const EXIT_FAILURE = 1;
/** Error (missing env vars, invalid args, server error) */
export const EXIT_ERROR = 2;

// ============================================
// ID Validation
// ============================================

/**
 * Regex pattern for valid agent/session IDs
 * Accepts UUIDs, alphanumeric strings with hyphens/underscores, or prefixed IDs
 * Examples: "a1b2c3d4-e5f6-7890-abcd-ef1234567890", "agent_123", "session-abc"
 */
const VALID_ID_PATTERN = /^[a-zA-Z0-9][a-zA-Z0-9_-]{0,63}$/;

/**
 * Validate an ID format
 * @param id The ID to validate
 * @param fieldName Name of the field for error messages
 * @throws Error if ID is invalid
 */
function validateId(id: string, fieldName: string): void {
  if (!id || typeof id !== 'string') {
    throw new Error(`${fieldName} is required and must be a string`);
  }
  if (id.length === 0) {
    throw new Error(`${fieldName} cannot be empty`);
  }
  if (id.length > 64) {
    throw new Error(`${fieldName} is too long (max 64 characters): ${id.slice(0, 20)}...`);
  }
  if (!VALID_ID_PATTERN.test(id)) {
    throw new Error(
      `${fieldName} has invalid format: "${id}". ` +
      `IDs must start with alphanumeric and contain only letters, numbers, hyphens, and underscores.`
    );
  }
}

// ============================================
// Environment Variables
// ============================================

/**
 * Read required environment variables for agent context
 * @throws Error if required variables are missing or invalid
 */
function getRadioEnv(): RadioEnv {
  const agentId = process.env.KARMA_AGENT_ID;
  const sessionId = process.env.KARMA_SESSION_ID;

  if (!agentId || !sessionId) {
    const missing = [];
    if (!agentId) missing.push('KARMA_AGENT_ID');
    if (!sessionId) missing.push('KARMA_SESSION_ID');
    throw new Error(`Missing required environment variables: ${missing.join(', ')}`);
  }

  // Validate ID formats
  validateId(agentId, 'KARMA_AGENT_ID');
  validateId(sessionId, 'KARMA_SESSION_ID');

  const parentId = process.env.KARMA_PARENT_ID;
  if (parentId) {
    validateId(parentId, 'KARMA_PARENT_ID');
  }

  return {
    agentId,
    sessionId,
    parentId,
    agentType: process.env.KARMA_AGENT_TYPE,
    model: process.env.KARMA_MODEL,
  };
}

/**
 * Output JSON response and exit with code
 */
function outputJson(data: unknown, exitCode: number = EXIT_SUCCESS): never {
  console.log(JSON.stringify(data));
  process.exit(exitCode);
}

/**
 * Output error JSON and exit
 */
function outputError(error: string, exitCode: number = EXIT_ERROR): never {
  outputJson({ error }, exitCode);
}

/**
 * Handle errors from radio operations
 */
function handleRadioError(error: unknown): never {
  if (error instanceof RadioServerNotRunningError) {
    outputError('Server not running', EXIT_ERROR);
  }
  if (error instanceof RadioTimeoutError) {
    outputError('Request timed out', EXIT_FAILURE);
  }
  if (error instanceof RadioServerError) {
    outputError(error.message, EXIT_ERROR);
  }
  if (error instanceof Error) {
    outputError(error.message, EXIT_ERROR);
  }
  outputError('Unknown error', EXIT_ERROR);
}

/**
 * Parse JSON string safely
 */
function parseJson(str: string, fieldName: string): Record<string, unknown> {
  try {
    return JSON.parse(str);
  } catch {
    throw new Error(`Invalid JSON for ${fieldName}: ${str}`);
  }
}

/**
 * Read JSON file safely
 */
function readJsonFile(filePath: string): unknown {
  try {
    const content = readFileSync(filePath, 'utf-8');
    return JSON.parse(content);
  } catch (err) {
    if ((err as NodeJS.ErrnoException).code === 'ENOENT') {
      throw new Error(`File not found: ${filePath}`);
    }
    throw new Error(`Invalid JSON file: ${filePath}`);
  }
}

// ============================================
// Command Handlers
// ============================================

/**
 * Handle set-status command
 * karma radio set-status <state> [--tool <name>] [--metadata <json>] [--percent <num>] [--message <text>] [--validate <mode>]
 *
 * Phase 3: Batch operations - supports setting status and progress in a single call
 * Phase 5: Added --validate flag for metadata schema validation
 */
async function handleSetStatus(
  state: string,
  options: { tool?: string; metadata?: string; percent?: string; message?: string; validate?: string },
): Promise<void> {
  try {
    const env = getRadioEnv();
    const client = createRadioClient();

    const validStates: AgentState[] = ['pending', 'active', 'waiting', 'completed', 'failed', 'cancelled'];
    if (!validStates.includes(state as AgentState)) {
      outputError(`Invalid state: ${state}. Valid states: ${validStates.join(', ')}`);
    }

    const args: Record<string, unknown> = {
      state: state as AgentState,
    };

    if (options.metadata) {
      args.metadata = parseJson(options.metadata, '--metadata');
    }

    // Phase 5: Handle validation mode
    if (options.validate) {
      const validModes: ValidationMode[] = ['none', 'warn', 'strict'];
      if (!validModes.includes(options.validate as ValidationMode)) {
        outputError(`Invalid validate mode: ${options.validate}. Valid modes: ${validModes.join(', ')}`);
      }
      args.validateMetadata = options.validate as ValidationMode;
    }

    // Phase 3: Batch operations - include progress if any progress flags provided
    const hasProgressFlags = options.percent !== undefined || options.message !== undefined || options.tool !== undefined;
    if (hasProgressFlags) {
      const progress: ProgressUpdate = {};

      if (options.tool) {
        progress.tool = options.tool;
      }

      if (options.percent !== undefined) {
        const percent = parseInt(options.percent, 10);
        if (isNaN(percent) || percent < 0 || percent > 100) {
          outputError('Invalid percent: must be a number between 0 and 100');
        }
        progress.percent = percent;
      }

      if (options.message) {
        progress.message = options.message;
      }

      args.progress = progress;
    }

    const result = await client.send('set-status', args, env);
    outputJson({ success: true, state, ...result as object });
  } catch (error) {
    handleRadioError(error);
  }
}

/**
 * Handle report-progress command
 * karma radio report-progress [--tool <name>] [--percent <num>] [--message <text>]
 */
async function handleReportProgress(options: {
  tool?: string;
  percent?: string;
  message?: string;
}): Promise<void> {
  try {
    const env = getRadioEnv();
    const client = createRadioClient();

    const progress: ProgressUpdate = {};

    if (options.tool) {
      progress.tool = options.tool;
    }

    if (options.percent !== undefined) {
      const percent = parseInt(options.percent, 10);
      if (isNaN(percent) || percent < 0 || percent > 100) {
        outputError('Invalid percent: must be a number between 0 and 100');
      }
      progress.percent = percent;
    }

    if (options.message) {
      progress.message = options.message;
    }

    const result = await client.send('report-progress', { progress }, env);
    outputJson({ success: true, progress, ...result as object });
  } catch (error) {
    handleRadioError(error);
  }
}

/**
 * Handle publish-result command
 * karma radio publish-result <json-file>
 */
async function handlePublishResult(jsonFile: string): Promise<void> {
  try {
    const env = getRadioEnv();
    const client = createRadioClient();

    const result = readJsonFile(jsonFile);

    await client.send('publish-result', { result }, env);
    outputJson({ success: true, published: true });
  } catch (error) {
    handleRadioError(error);
  }
}

/**
 * Handle wait-for command
 * karma radio wait-for <agent-id> <state> [--timeout <ms>] [--poll]
 *
 * Phase 4: Uses subscription-based notifications by default for efficient waiting.
 * Use --poll flag to fall back to polling mode if needed.
 */
async function handleWaitFor(
  agentId: string,
  state: string,
  options: { timeout?: string; poll?: boolean },
): Promise<void> {
  try {
    // Note: We don't need env for subscription-based wait, but validate anyway
    getRadioEnv();
    const client = createRadioClient();

    // Validate agent ID format
    try {
      validateId(agentId, 'agent-id');
    } catch (validationError) {
      outputError((validationError as Error).message);
    }

    const validStates: AgentState[] = ['pending', 'active', 'waiting', 'completed', 'failed', 'cancelled'];
    if (!validStates.includes(state as AgentState)) {
      outputError(`Invalid state: ${state}. Valid states: ${validStates.join(', ')}`);
    }

    // Parse timeout (default: 30000ms)
    let timeoutMs = 30000;
    if (options.timeout) {
      const timeout = parseInt(options.timeout, 10);
      if (isNaN(timeout) || timeout <= 0) {
        outputError('Invalid timeout: must be a positive number');
      }
      timeoutMs = timeout;
    }

    // Phase 4: Use subscription-based wait by default, poll as fallback
    const usePoll = options.poll ?? false;
    const result = await client.waitForAgent(agentId, state as AgentState, timeoutMs, usePoll);
    outputJson({ success: true, status: result, mode: usePoll ? 'poll' : 'subscription' });
  } catch (error) {
    if (error instanceof RadioTimeoutError) {
      // wait-for timeout is a failure, not an error
      outputJson({ success: false, error: 'Timeout waiting for agent state' }, EXIT_FAILURE);
    }
    if (error instanceof SubscriptionError) {
      // Subscription failed
      outputJson({ success: false, error: `Subscription error: ${error.message}` }, EXIT_FAILURE);
    }
    handleRadioError(error);
  }
}

/**
 * Handle wait-for-all command
 * karma radio wait-for-all <agent-ids...> <state> [--timeout <ms>]
 *
 * Wait for multiple agents to reach the specified state.
 * Returns when ALL agents have reached the target state.
 */
async function handleWaitForAll(
  agentIds: string[],
  options: { timeout?: string },
): Promise<void> {
  try {
    getRadioEnv();
    const client = createRadioClient();

    // Need at least 2 arguments: agent IDs and state
    if (agentIds.length < 2) {
      outputError('Usage: wait-for-all <agent1> <agent2> [...] <state>');
    }

    // Last argument is the state
    const state = agentIds[agentIds.length - 1];
    const agents = agentIds.slice(0, -1);

    // Validate all agent IDs
    for (const agentId of agents) {
      try {
        validateId(agentId, `agent-id "${agentId}"`);
      } catch (validationError) {
        outputError((validationError as Error).message);
      }
    }

    const validStates: AgentState[] = ['pending', 'active', 'waiting', 'completed', 'failed', 'cancelled'];
    if (!validStates.includes(state as AgentState)) {
      outputError(`Invalid state: ${state}. Valid states: ${validStates.join(', ')}`);
    }

    // Parse timeout (default: 60000ms for batch operations)
    let timeoutMs = 60000;
    if (options.timeout) {
      const timeout = parseInt(options.timeout, 10);
      if (isNaN(timeout) || timeout <= 0) {
        outputError('Invalid timeout: must be a positive number');
      }
      timeoutMs = timeout;
    }

    // Wait for all agents concurrently
    const startTime = Date.now();
    const results: Array<{ agentId: string; status: AgentStatus }> = [];
    const errors: Array<{ agentId: string; error: string }> = [];

    await Promise.all(
      agents.map(async (agentId) => {
        try {
          const remainingTime = Math.max(1000, timeoutMs - (Date.now() - startTime));
          const status = await client.waitForAgent(agentId, state as AgentState, remainingTime, false);
          results.push({ agentId, status });
        } catch (err) {
          if (err instanceof RadioTimeoutError) {
            errors.push({ agentId, error: 'timeout' });
          } else {
            errors.push({ agentId, error: (err as Error).message });
          }
        }
      })
    );

    if (errors.length > 0) {
      outputJson({
        success: false,
        completed: results,
        failed: errors,
        message: `${errors.length} of ${agents.length} agents did not reach state "${state}"`,
      }, EXIT_FAILURE);
    }

    outputJson({
      success: true,
      agents: results,
      state,
      elapsed: Date.now() - startTime,
    });
  } catch (error) {
    handleRadioError(error);
  }
}

/**
 * Handle wait-for-children command
 * karma radio wait-for-children <state> [--timeout <ms>]
 *
 * Wait for all child agents to reach the specified state.
 */
async function handleWaitForChildren(
  state: string,
  options: { timeout?: string },
): Promise<void> {
  try {
    const env = getRadioEnv();
    const client = createRadioClient();

    const validStates: AgentState[] = ['pending', 'active', 'waiting', 'completed', 'failed', 'cancelled'];
    if (!validStates.includes(state as AgentState)) {
      outputError(`Invalid state: ${state}. Valid states: ${validStates.join(', ')}`);
    }

    // Parse timeout (default: 60000ms for batch operations)
    let timeoutMs = 60000;
    if (options.timeout) {
      const timeout = parseInt(options.timeout, 10);
      if (isNaN(timeout) || timeout <= 0) {
        outputError('Invalid timeout: must be a positive number');
      }
      timeoutMs = timeout;
    }

    // First, get list of children
    const children = await client.send<AgentStatus[]>('list-agents', { filter: 'children' }, env);

    if (children.length === 0) {
      outputJson({ success: true, agents: [], message: 'No child agents found' });
    }

    // Wait for all children to reach the target state
    const startTime = Date.now();
    const results: Array<{ agentId: string; status: AgentStatus }> = [];
    const errors: Array<{ agentId: string; error: string }> = [];

    await Promise.all(
      children.map(async (child) => {
        try {
          // Check if already in target state
          if (child.state === state) {
            results.push({ agentId: child.agentId, status: child });
            return;
          }

          const remainingTime = Math.max(1000, timeoutMs - (Date.now() - startTime));
          const status = await client.waitForAgent(child.agentId, state as AgentState, remainingTime, false);
          results.push({ agentId: child.agentId, status });
        } catch (err) {
          if (err instanceof RadioTimeoutError) {
            errors.push({ agentId: child.agentId, error: 'timeout' });
          } else {
            errors.push({ agentId: child.agentId, error: (err as Error).message });
          }
        }
      })
    );

    if (errors.length > 0) {
      outputJson({
        success: false,
        completed: results,
        failed: errors,
        message: `${errors.length} of ${children.length} children did not reach state "${state}"`,
      }, EXIT_FAILURE);
    }

    outputJson({
      success: true,
      agents: results,
      state,
      childCount: children.length,
      elapsed: Date.now() - startTime,
    });
  } catch (error) {
    handleRadioError(error);
  }
}

/**
 * Handle send command
 * karma radio send <target-agent-id> <message-json>
 */
async function handleSend(
  targetAgentId: string,
  messageJson: string,
): Promise<void> {
  try {
    const env = getRadioEnv();
    const client = createRadioClient();

    const message = parseJson(messageJson, 'message');

    await client.send('send', { targetAgentId, message }, env);
    outputJson({ success: true, sent: true, target: targetAgentId });
  } catch (error) {
    handleRadioError(error);
  }
}

/**
 * Handle listen command
 * karma radio listen [--agent <id>] [--pattern <glob>]
 */
async function handleListen(options: {
  agent?: string;
  pattern?: string;
}): Promise<void> {
  try {
    const env = getRadioEnv();
    const client = createRadioClient();

    const args: Record<string, unknown> = {};

    if (options.agent) {
      args.agentId = options.agent;
    }

    if (options.pattern) {
      args.pattern = options.pattern;
    }

    const result = await client.send<unknown[]>('listen', args, env);
    outputJson({ success: true, messages: result });
  } catch (error) {
    handleRadioError(error);
  }
}

/**
 * Handle get-status command
 * karma radio get-status [--agent <id>] [--include-progress]
 */
async function handleGetStatus(options: { agent?: string; includeProgress?: boolean }): Promise<void> {
  try {
    const env = getRadioEnv();
    const client = createRadioClient();

    const args: Record<string, unknown> = {};

    if (options.agent) {
      args.agentId = options.agent;
    }

    if (options.includeProgress) {
      args.includeProgress = true;
    }

    const result = await client.send<AgentStatus | AgentStatus[]>('get-status', args, env);
    outputJson({ success: true, status: result });
  } catch (error) {
    handleRadioError(error);
  }
}

/**
 * Handle list-agents command
 * karma radio list-agents [--children] [--siblings] [--parent] [--status <state>]
 */
async function handleListAgents(options: {
  children?: boolean;
  siblings?: boolean;
  parent?: boolean;
  status?: string;
}): Promise<void> {
  try {
    const env = getRadioEnv();
    const client = createRadioClient();

    let filter: 'children' | 'siblings' | 'parent' | 'all' = 'all';
    if (options.children) filter = 'children';
    else if (options.siblings) filter = 'siblings';
    else if (options.parent) filter = 'parent';

    const args: Record<string, unknown> = { filter };

    if (options.status) {
      const validStates: AgentState[] = ['pending', 'active', 'waiting', 'completed', 'failed', 'cancelled'];
      if (!validStates.includes(options.status as AgentState)) {
        outputError(`Invalid status: ${options.status}. Valid states: ${validStates.join(', ')}`);
      }
      args.status = options.status;
    }

    const result = await client.send<AgentStatus[]>('list-agents', args, env);
    outputJson({ success: true, agents: result });
  } catch (error) {
    handleRadioError(error);
  }
}

// ============================================
// Subagent Watcher Handlers
// ============================================

/**
 * Find subagents directory for a session
 */
function findSubagentsDir(sessionId: string): string | null {
  const projectsDir = join(homedir(), '.claude', 'projects');

  if (!existsSync(projectsDir)) {
    return null;
  }

  // Search all projects for the session
  const projects = readdirSync(projectsDir);
  for (const project of projects) {
    const projectDir = join(projectsDir, project);
    const sessionDir = join(projectDir, sessionId, 'subagents');
    if (existsSync(sessionDir)) {
      return sessionDir;
    }
  }

  return null;
}

/**
 * Handle watch-subagents command
 * karma radio watch-subagents [--json] [--interval <ms>]
 *
 * Monitors Claude Code subagent JSONL files and reports status to radio
 */
async function handleWatchSubagents(options: {
  json?: boolean;
  interval?: string;
}): Promise<void> {
  try {
    const env = getRadioEnv();
    const pollInterval = options.interval ? parseInt(options.interval, 10) : 1000;

    if (options.json) {
      // One-shot JSON output
      const subagentsDir = findSubagentsDir(env.sessionId);
      if (!subagentsDir) {
        outputJson({ success: true, agents: [], message: 'No subagents directory found' });
      }
      const agents = scanSubagents(subagentsDir!);
      outputJson({ success: true, ...formatAgentsJson(agents) });
    }

    // Live watch mode
    console.log(`Watching subagents for session ${env.sessionId}...`);
    console.log('Press Ctrl+C to stop\n');

    const watcher = createSubagentWatcher({
      sessionId: env.sessionId,
      pollInterval,
      reportToRadio: true,
      onUpdate: (agents) => {
        // Clear screen and redraw
        console.clear();
        console.log(`Watching subagents for session ${env.sessionId}`);
        console.log(`Last update: ${new Date().toLocaleTimeString()}`);
        console.log(formatAgentsTable(agents));
      },
    });

    watcher.start();

    // Handle Ctrl+C
    process.on('SIGINT', () => {
      watcher.stop();
      console.log('\nStopped watching');
      process.exit(0);
    });

    // Keep running
    await new Promise(() => {});
  } catch (error) {
    handleRadioError(error);
  }
}

/**
 * Handle summary command
 * karma radio summary
 *
 * Shows summary of all agents in current session
 */
async function handleSummary(options: { json?: boolean }): Promise<void> {
  try {
    const env = getRadioEnv();

    // Get subagents from JSONL files
    const subagentsDir = findSubagentsDir(env.sessionId);
    let subagents = new Map<string, SubagentInfo>();
    if (subagentsDir) {
      subagents = scanSubagents(subagentsDir);
    }

    // Also try to get agents from radio server
    let radioAgents: AgentStatus[] = [];
    try {
      const client = createRadioClient();
      radioAgents = await client.send<AgentStatus[]>('list-agents', { filter: 'all' }, env);
    } catch {
      // Server may not be running
    }

    if (options.json) {
      outputJson({
        success: true,
        sessionId: env.sessionId,
        radioAgents: radioAgents.length,
        subagents: formatAgentsJson(subagents),
      });
    }

    // Pretty print
    console.log(`\nSession: ${env.sessionId}`);
    console.log(`Radio agents: ${radioAgents.length}`);
    console.log(`Subagents (from JSONL): ${subagents.size}`);

    if (subagents.size > 0) {
      const summary = formatAgentsJson(subagents) as { byState: Record<string, number> };
      console.log(`\nBy state:`);
      for (const [state, count] of Object.entries(summary.byState)) {
        if (count > 0) {
          console.log(`  ${state}: ${count}`);
        }
      }
      console.log(formatAgentsTable(subagents));
    }

    process.exit(0);
  } catch (error) {
    handleRadioError(error);
  }
}

/**
 * Handle scan command (one-shot subagent scan)
 * karma radio scan [--json]
 */
async function handleScan(options: { json?: boolean }): Promise<void> {
  try {
    const env = getRadioEnv();

    const subagentsDir = findSubagentsDir(env.sessionId);
    if (!subagentsDir) {
      if (options.json) {
        outputJson({ success: true, agents: [], message: 'No subagents directory found' });
      }
      console.log('No subagents directory found for session:', env.sessionId);
      process.exit(0);
    }

    const agents = scanSubagents(subagentsDir);

    if (options.json) {
      outputJson({ success: true, ...formatAgentsJson(agents) });
    }

    console.log(formatAgentsTable(agents));
    process.exit(0);
  } catch (error) {
    handleRadioError(error);
  }
}

// ============================================
// Tree Visualization Types
// ============================================

/** Node in the agent tree hierarchy */
interface TreeNode {
  agentId: string;
  state: AgentState;
  agentType: string;
  model: string;
  children: TreeNode[];
}

/**
 * Build tree structure from flat agent list
 */
function buildAgentTree(agents: AgentStatus[]): TreeNode[] {
  const nodeMap = new Map<string, TreeNode>();
  const roots: TreeNode[] = [];

  // First pass: create all nodes
  for (const agent of agents) {
    nodeMap.set(agent.agentId, {
      agentId: agent.agentId,
      state: agent.state,
      agentType: agent.agentType || 'unknown',
      model: agent.model || 'unknown',
      children: [],
    });
  }

  // Second pass: build parent-child relationships
  for (const agent of agents) {
    const node = nodeMap.get(agent.agentId)!;
    if (agent.parentId && nodeMap.has(agent.parentId)) {
      nodeMap.get(agent.parentId)!.children.push(node);
    } else {
      // No parent or parent not found - this is a root
      roots.push(node);
    }
  }

  return roots;
}

/**
 * Format tree as ASCII art
 */
function formatTree(roots: TreeNode[], options: { json?: boolean } = {}): string {
  if (options.json) {
    return JSON.stringify({ success: true, tree: roots }, null, 2);
  }

  const lines: string[] = [];
  const stateIcons: Record<AgentState, string> = {
    pending: '[P]',
    active: '[A]',
    waiting: '[W]',
    completed: '[C]',
    failed: '[F]',
    cancelled: '[X]',
  };

  function renderNode(node: TreeNode, prefix: string, isLast: boolean): void {
    const connector = isLast ? '\\-- ' : '|-- ';
    const stateIcon = stateIcons[node.state] || '[?]';
    const shortId = node.agentId.length > 8 ? node.agentId.slice(0, 8) : node.agentId;
    const shortModel = node.model.replace('claude-', '').slice(0, 15);

    lines.push(`${prefix}${connector}${stateIcon} ${shortId} (${node.agentType}, ${shortModel})`);

    const childPrefix = prefix + (isLast ? '    ' : '|   ');
    for (let i = 0; i < node.children.length; i++) {
      renderNode(node.children[i], childPrefix, i === node.children.length - 1);
    }
  }

  if (roots.length === 0) {
    return 'No agents found in session';
  }

  lines.push('Agent Hierarchy:');
  lines.push('');

  for (let i = 0; i < roots.length; i++) {
    const root = roots[i];
    const stateIcon = stateIcons[root.state] || '[?]';
    const shortId = root.agentId.length > 8 ? root.agentId.slice(0, 8) : root.agentId;
    const shortModel = root.model.replace('claude-', '').slice(0, 15);

    lines.push(`${stateIcon} ${shortId} (${root.agentType}, ${shortModel})`);

    for (let j = 0; j < root.children.length; j++) {
      renderNode(root.children[j], '', j === root.children.length - 1);
    }

    if (i < roots.length - 1) {
      lines.push('');
    }
  }

  lines.push('');
  lines.push('Legend: [P]=pending [A]=active [W]=waiting [C]=completed [F]=failed [X]=cancelled');

  return lines.join('\n');
}

/**
 * Handle tree command
 * karma radio tree [--session <id>] [--json]
 *
 * Displays agent hierarchy as an ASCII tree
 */
async function handleTree(options: { session?: string; json?: boolean }): Promise<void> {
  try {
    const env = getRadioEnv();
    const client = createRadioClient();

    // Use provided session or current session
    const sessionId = options.session || env.sessionId;

    // Validate session ID if provided
    if (options.session) {
      try {
        validateId(options.session, '--session');
      } catch (validationError) {
        outputError((validationError as Error).message);
      }
    }

    // Get all agents in the session
    const agents = await client.send<AgentStatus[]>('list-agents', { filter: 'all' }, {
      ...env,
      sessionId,
    });

    // Build tree structure
    const tree = buildAgentTree(agents);

    if (options.json) {
      outputJson({
        success: true,
        sessionId,
        agentCount: agents.length,
        tree,
      });
    }

    // Pretty print the tree
    console.log(`\nSession: ${sessionId}`);
    console.log(`Total agents: ${agents.length}`);
    console.log('');
    console.log(formatTree(tree));
    process.exit(0);
  } catch (error) {
    handleRadioError(error);
  }
}

// ============================================
// Command Builder
// ============================================

/**
 * Create the radio command with all subcommands
 */
export function createRadioCommand(): Command {
  const radio = new Command('radio')
    .description('Agent coordination commands (for hooks)')
    .addHelpText('after', `
Environment Variables (required):
  KARMA_AGENT_ID      Agent identifier
  KARMA_SESSION_ID    Session identifier

Environment Variables (optional):
  KARMA_PARENT_ID     Parent agent identifier
  KARMA_AGENT_TYPE    Agent type (e.g., "task", "review")
  KARMA_MODEL         Model being used (e.g., "claude-sonnet-4")

Exit Codes:
  0  Success
  1  Timeout or operation failure
  2  Error (missing env vars, invalid args, server error)

Output:
  All commands output JSON for machine parsing.

Examples:
  $ KARMA_AGENT_ID=a1 KARMA_SESSION_ID=s1 karma radio set-status active
  $ KARMA_AGENT_ID=a1 KARMA_SESSION_ID=s1 karma radio get-status
  $ KARMA_AGENT_ID=a1 KARMA_SESSION_ID=s1 karma radio wait-for a2 completed --timeout 10000
`);

  // set-status
  radio
    .command('set-status <state>')
    .description('Set agent status state (pending|active|waiting|completed|failed|cancelled)')
    .option('-t, --tool <name>', 'Current tool being used (also sets progress.tool)')
    .option('-m, --metadata <json>', 'Additional metadata as JSON')
    .option('-p, --percent <num>', 'Progress percentage (0-100) - batch operation')
    .option('--message <text>', 'Progress message - batch operation')
    .option('--validate <mode>', 'Metadata validation mode (none|warn|strict)')
    .action(handleSetStatus);

  // report-progress
  radio
    .command('report-progress')
    .description('Report progress update')
    .option('-t, --tool <name>', 'Tool name')
    .option('-p, --percent <num>', 'Progress percentage (0-100)')
    .option('-m, --message <text>', 'Progress message')
    .action(handleReportProgress);

  // publish-result
  radio
    .command('publish-result <json-file>')
    .description('Publish agent result from JSON file')
    .action(handlePublishResult);

  // wait-for
  radio
    .command('wait-for <agent-id> <state>')
    .description('Wait for agent to reach state (uses subscription-based notifications by default)')
    .option('--timeout <ms>', 'Timeout in milliseconds (default: 30000)')
    .option('--poll', 'Use polling mode instead of subscription-based notifications')
    .action(handleWaitFor);

  // wait-for-all (batch wait)
  radio
    .command('wait-for-all <agent-ids...>')
    .description('Wait for multiple agents to reach a state. Last argument is the target state.')
    .option('--timeout <ms>', 'Timeout in milliseconds (default: 60000)')
    .action(handleWaitForAll);

  // wait-for-children (batch wait for all children)
  radio
    .command('wait-for-children <state>')
    .description('Wait for all child agents to reach the specified state')
    .option('--timeout <ms>', 'Timeout in milliseconds (default: 60000)')
    .action(handleWaitForChildren);

  // send
  radio
    .command('send <target-agent-id> <message-json>')
    .description('Send message to another agent')
    .action(handleSend);

  // listen
  radio
    .command('listen')
    .description('Listen for incoming messages')
    .option('-a, --agent <id>', 'Filter by sender agent ID')
    .option('-p, --pattern <glob>', 'Filter by message pattern')
    .action(handleListen);

  // get-status
  radio
    .command('get-status')
    .description('Get agent status')
    .option('-a, --agent <id>', 'Get status for specific agent (default: self)')
    .option('-p, --include-progress', 'Include latest progress update in response')
    .action(handleGetStatus);

  // list-agents
  radio
    .command('list-agents')
    .description('List agents in session')
    .option('--children', 'List only child agents')
    .option('--siblings', 'List only sibling agents')
    .option('--parent', 'Get parent agent only')
    .option('-s, --status <state>', 'Filter by agent status (pending|active|waiting|completed|failed|cancelled)')
    .action(handleListAgents);

  // watch-subagents (inference-based tracking)
  radio
    .command('watch-subagents')
    .description('Watch subagents via JSONL file monitoring (inference-based)')
    .option('-j, --json', 'Output JSON and exit (one-shot mode)')
    .option('-i, --interval <ms>', 'Poll interval in milliseconds (default: 1000)')
    .action(handleWatchSubagents);

  // scan (one-shot subagent scan)
  radio
    .command('scan')
    .description('Scan subagents from JSONL files (one-shot)')
    .option('-j, --json', 'Output as JSON')
    .action(handleScan);

  // summary
  radio
    .command('summary')
    .description('Show summary of all agents in session')
    .option('-j, --json', 'Output as JSON')
    .action(handleSummary);

  // tree (hierarchy visualization)
  radio
    .command('tree')
    .description('Display agent hierarchy as an ASCII tree')
    .option('-s, --session <id>', 'Show tree for specific session (default: current)')
    .option('-j, --json', 'Output as JSON')
    .action(handleTree);

  return radio;
}

/**
 * Export the configured radio command
 */
export const radioCommand = createRadioCommand();
