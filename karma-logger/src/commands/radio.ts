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
  createRadioClient,
} from '../walkie-talkie/socket-client.js';
import type { RadioEnv, AgentState, AgentStatus, ProgressUpdate } from '../walkie-talkie/types.js';

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
// Environment Variables
// ============================================

/**
 * Read required environment variables for agent context
 * @throws Error if required variables are missing
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

  return {
    agentId,
    sessionId,
    parentId: process.env.KARMA_PARENT_ID,
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
 * karma radio set-status <state> [--tool <name>] [--metadata <json>] [--percent <num>] [--message <text>]
 *
 * Phase 3: Batch operations - supports setting status and progress in a single call
 */
async function handleSetStatus(
  state: string,
  options: { tool?: string; metadata?: string; percent?: string; message?: string },
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
 * karma radio wait-for <agent-id> <state> [--timeout <ms>]
 */
async function handleWaitFor(
  agentId: string,
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

    const args: Record<string, unknown> = {
      targetAgentId: agentId,
      state: state as AgentState,
    };

    if (options.timeout) {
      const timeout = parseInt(options.timeout, 10);
      if (isNaN(timeout) || timeout <= 0) {
        outputError('Invalid timeout: must be a positive number');
      }
      args.timeoutMs = timeout;
    }

    const result = await client.send<AgentStatus>('wait-for', args, env);
    outputJson({ success: true, status: result });
  } catch (error) {
    if (error instanceof RadioTimeoutError) {
      // wait-for timeout is a failure, not an error
      outputJson({ success: false, error: 'Timeout waiting for agent state' }, EXIT_FAILURE);
    }
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
    .description('Wait for agent to reach state')
    .option('--timeout <ms>', 'Timeout in milliseconds (default: 30000)')
    .action(handleWaitFor);

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

  return radio;
}

/**
 * Export the configured radio command
 */
export const radioCommand = createRadioCommand();
