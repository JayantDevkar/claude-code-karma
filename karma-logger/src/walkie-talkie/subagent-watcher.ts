/**
 * Subagent Watcher - Inference-based subagent tracking via JSONL files
 *
 * Monitors Claude Code's subagent JSONL files to infer agent status and
 * reports to the karma radio system for real-time tracking.
 */

import { watch, existsSync, readdirSync, statSync, readFileSync } from 'node:fs';
import { join, basename } from 'node:path';
import { homedir } from 'node:os';
import { createRadioClient, RadioClient } from './socket-client.js';
import type { AgentState, RadioEnv } from './types.js';

/** Subagent info extracted from JSONL */
export interface SubagentInfo {
  agentId: string;
  sessionId: string;
  model: string;
  task: string;
  state: AgentState;
  startedAt: string;
  updatedAt: string;
  toolCount: number;
  lastTool?: string;
  slug?: string;
  /** Hierarchy depth (0 = direct child of root session, JSONL files don't track nesting) */
  depth: number;
}

/** JSONL entry structure from Claude Code */
interface JsonlEntry {
  agentId: string;
  sessionId: string;
  timestamp: string;
  type: 'user' | 'assistant';
  slug?: string;
  message: {
    role: string;
    content: string | Array<{
      type: string;
      text?: string;
      name?: string;
      tool_use_id?: string;
      is_error?: boolean;
    }>;
    model?: string;
    stop_reason?: string | null;
  };
}

/** Debug logger - can be replaced with actual logger in production */
const debugLog = (message: string, ...args: unknown[]) => {
  if (process.env.DEBUG?.includes('subagent-watcher')) {
    console.debug(`[subagent-watcher] ${message}`, ...args);
  }
};

/** Warning logger for important issues */
const warnLog = (message: string, ...args: unknown[]) => {
  if (process.env.DEBUG?.includes('subagent-watcher')) {
    console.warn(`[subagent-watcher] ${message}`, ...args);
  }
};

/** Watcher options */
export interface WatcherOptions {
  sessionId: string;
  projectPath?: string;
  pollInterval?: number;
  onUpdate?: (agents: Map<string, SubagentInfo>) => void;
  reportToRadio?: boolean;
}

/**
 * Find the Claude projects directory
 */
function getClaudeProjectsDir(): string {
  return join(homedir(), '.claude', 'projects');
}

/**
 * Find subagents directory for a session
 */
function findSubagentsDir(sessionId: string, projectPath?: string): string | null {
  const projectsDir = getClaudeProjectsDir();

  if (!existsSync(projectsDir)) {
    return null;
  }

  // If project path provided, search that specific project
  if (projectPath) {
    const encodedPath = projectPath.replace(/\//g, '-');
    const projectDir = join(projectsDir, encodedPath);
    const sessionDir = join(projectDir, sessionId, 'subagents');
    if (existsSync(sessionDir)) {
      return sessionDir;
    }
  }

  // Search all projects for the session
  const projects = readdirSync(projectsDir);
  for (const project of projects) {
    const sessionDir = join(projectsDir, project, sessionId, 'subagents');
    if (existsSync(sessionDir)) {
      return sessionDir;
    }
  }

  return null;
}

/**
 * Parse a JSONL file to extract subagent info
 */
function parseSubagentJsonl(filePath: string): SubagentInfo | null {
  try {
    const content = readFileSync(filePath, 'utf-8');
    const lines = content.trim().split('\n').filter(Boolean);

    if (lines.length === 0) return null;

    let agentId = '';
    let sessionId = '';
    let model = 'unknown';
    let task = '';
    let startedAt = '';
    let updatedAt = '';
    let toolCount = 0;
    let lastTool = '';
    let slug = '';
    let hasStopReason = false;
    let lastStopReason: string | null = null;
    let lastMessageType = '';
    let lastMessageHasToolUse = false;
    let lastMessageHasTextOnly = false;
    let hasAssistantMessage = false;
    let hasToolError = false;
    let hasErrorPattern = false;
    let lastToolUseId: string | null = null;
    let hasToolResultForLastUse = false;
    let malformedLineCount = 0;

    for (const line of lines) {
      try {
        const entry: JsonlEntry = JSON.parse(line);

        if (!agentId && entry.agentId) agentId = entry.agentId;
        if (!sessionId && entry.sessionId) sessionId = entry.sessionId;
        if (!slug && entry.slug) slug = entry.slug;
        if (!startedAt && entry.timestamp) startedAt = entry.timestamp;
        if (entry.timestamp) updatedAt = entry.timestamp;

        // Track last message characteristics
        lastMessageType = entry.type;
        lastMessageHasToolUse = false;
        lastMessageHasTextOnly = false;

        // Extract model from assistant messages
        if (entry.message?.model) {
          model = entry.message.model;
        }

        // Extract task from first user message
        if (!task && entry.type === 'user' && entry.message?.role === 'user') {
          if (typeof entry.message.content === 'string') {
            task = entry.message.content.slice(0, 100);
          }
        }

        // Count tool uses and track last message content
        if (entry.type === 'assistant' && Array.isArray(entry.message?.content)) {
          hasAssistantMessage = true;
          let hasText = false;
          let hasToolUse = false;

          for (const block of entry.message.content) {
            if (block.type === 'tool_use' && block.name) {
              toolCount++;
              lastTool = block.name;
              hasToolUse = true;
              lastToolUseId = block.tool_use_id || null;
              hasToolResultForLastUse = false; // Reset - waiting for result
            }
            if (block.type === 'text') {
              hasText = true;
              // Check for error patterns in text content
              if (block.text && /error|failed|exception|crash/i.test(block.text)) {
                hasErrorPattern = true;
              }
            }
            // Check for tool_result with error
            if (block.type === 'tool_result') {
              if (block.tool_use_id === lastToolUseId) {
                hasToolResultForLastUse = true;
              }
              if (block.is_error) {
                hasToolError = true;
              }
            }
          }

          lastMessageHasToolUse = hasToolUse;
          lastMessageHasTextOnly = hasText && !hasToolUse;
        }

        // Check for tool_result in user messages (tool results come back as user messages)
        if (entry.type === 'user' && Array.isArray(entry.message?.content)) {
          for (const block of entry.message.content) {
            if (block.type === 'tool_result') {
              if (block.tool_use_id === lastToolUseId) {
                hasToolResultForLastUse = true;
              }
              if (block.is_error) {
                hasToolError = true;
              }
            }
          }
        }

        // Check stop reason for completion
        if (entry.message?.stop_reason !== undefined) {
          lastStopReason = entry.message.stop_reason;
          if (lastStopReason === 'end_turn') {
            hasStopReason = true;
          }
        }
      } catch (parseError) {
        // Log malformed JSON lines at debug level instead of silently skipping
        malformedLineCount++;
        debugLog(`Malformed JSON line in ${filePath}: ${line.slice(0, 100)}...`, parseError);
      }
    }

    // Warn if there were multiple malformed lines
    if (malformedLineCount > 0) {
      warnLog(`Found ${malformedLineCount} malformed JSON lines in ${filePath}`);
    }

    if (!agentId) return null;

    // Infer state from JSONL content
    // State priority (check in order):
    // 1. 'failed' - error stop_reason or tool errors
    // 2. 'cancelled' - max_tokens or interrupted execution
    // 3. 'completed' - explicit end_turn or text-only final message
    // 4. 'waiting' - tool_use without tool_result
    // 5. 'pending' - file exists but no assistant messages
    // 6. 'active' - default for ongoing work
    let state: AgentState = 'active';

    const fileStats = statSync(filePath);
    const msSinceModified = Date.now() - fileStats.mtimeMs;

    // 1. Check for 'failed' state
    if (lastStopReason === 'error' || hasToolError) {
      state = 'failed';
    }
    // 2. Check for 'cancelled' state
    else if (lastStopReason === 'max_tokens') {
      state = 'cancelled';
    }
    // Check for interrupted execution (file stops mid-execution without proper end)
    else if (msSinceModified > 30000 && lastMessageHasToolUse && !hasToolResultForLastUse) {
      // File hasn't been modified in 30+ seconds with pending tool use - likely cancelled
      state = 'cancelled';
    }
    // 3. Check for 'completed' state
    else if (hasStopReason && lastStopReason === 'end_turn') {
      state = 'completed';
    } else if (lastMessageType === 'assistant' && lastMessageHasTextOnly) {
      // Check file modification time - if old enough, consider completed
      if (msSinceModified > 5000) { // 5 seconds
        state = 'completed';
      }
    }
    // 4. Check for 'waiting' state - tool_use without tool_result
    else if (lastMessageType === 'assistant' && lastMessageHasToolUse && !hasToolResultForLastUse) {
      state = 'waiting';
    }
    // 5. Check for 'pending' state - no assistant messages yet
    else if (!hasAssistantMessage) {
      state = 'pending';
    }
    // 6. Default: 'active' (already set)

    // Filter out Claude Code's internal warmup agents
    // These are short-lived agents used for model warmup and should not appear in user-facing lists
    const isWarmupAgent = task.trim().toLowerCase() === 'warmup' ||
                          (toolCount === 0 && !hasAssistantMessage);
    if (isWarmupAgent) {
      debugLog(`Filtering warmup agent: ${agentId.slice(0, 8)} (task: "${task}", toolCount: ${toolCount})`);
      return null;
    }

    return {
      agentId,
      sessionId,
      model,
      task,
      state,
      startedAt,
      updatedAt,
      toolCount,
      lastTool: lastTool || undefined,
      slug: slug || undefined,
      // JSONL files don't track nesting, so all subagents from JSONL are depth 0
      // Proper depth tracking requires agents to register via radio IPC
      depth: 0,
    };
  } catch {
    return null;
  }
}

/**
 * Scan subagents directory and return all agent info
 */
export function scanSubagents(subagentsDir: string): Map<string, SubagentInfo> {
  const agents = new Map<string, SubagentInfo>();

  if (!existsSync(subagentsDir)) {
    return agents;
  }

  const files = readdirSync(subagentsDir);
  for (const file of files) {
    if (!file.endsWith('.jsonl')) continue;

    const filePath = join(subagentsDir, file);
    const info = parseSubagentJsonl(filePath);

    if (info) {
      agents.set(info.agentId, info);
    }
  }

  return agents;
}

/**
 * Report subagent status to radio server
 */
async function reportToRadio(
  client: RadioClient,
  agent: SubagentInfo,
  parentSessionId: string,
): Promise<void> {
  const env: RadioEnv = {
    agentId: agent.agentId,
    sessionId: parentSessionId,
    parentId: parentSessionId,
    agentType: 'subagent',
    model: agent.model,
  };

  try {
    await client.send('set-status', {
      state: agent.state,
      metadata: {
        task: agent.task,
        toolCount: agent.toolCount,
        lastTool: agent.lastTool,
        slug: agent.slug,
      },
      progress: {
        message: agent.lastTool ? `Using ${agent.lastTool}` : agent.task.slice(0, 50),
      },
    }, env);
  } catch (error) {
    // Log radio errors at debug level - server may not be running
    debugLog(
      `Failed to report agent ${agent.agentId} status to radio:`,
      error instanceof Error ? error.message : error
    );
  }
}

/**
 * Create a subagent watcher
 */
export function createSubagentWatcher(options: WatcherOptions): {
  start: () => void;
  stop: () => void;
  getAgents: () => Map<string, SubagentInfo>;
} {
  const { sessionId, projectPath, pollInterval = 1000, onUpdate, reportToRadio: shouldReport = true } = options;

  let watcher: ReturnType<typeof watch> | null = null;
  let pollTimer: ReturnType<typeof setInterval> | null = null;
  let agents = new Map<string, SubagentInfo>();
  let subagentsDir: string | null = null;
  let radioClient: RadioClient | null = null;

  const scan = async () => {
    if (!subagentsDir) {
      subagentsDir = findSubagentsDir(sessionId, projectPath);
      if (!subagentsDir) return;
    }

    const newAgents = scanSubagents(subagentsDir);

    // Check for changes
    let hasChanges = false;
    for (const [id, info] of newAgents) {
      const existing = agents.get(id);
      if (!existing || existing.state !== info.state || existing.toolCount !== info.toolCount) {
        hasChanges = true;

        // Report to radio if enabled
        if (shouldReport && radioClient) {
          await reportToRadio(radioClient, info, sessionId);
        }
      }
    }

    if (hasChanges) {
      agents = newAgents;
      onUpdate?.(agents);
    }
  };

  return {
    start: () => {
      if (shouldReport) {
        radioClient = createRadioClient();
      }

      // Initial scan
      scan();

      // Set up polling (more reliable than fs.watch for JSONL files)
      pollTimer = setInterval(scan, pollInterval);

      // Also try fs.watch for immediate updates
      subagentsDir = findSubagentsDir(sessionId, projectPath);
      if (subagentsDir && existsSync(subagentsDir)) {
        try {
          watcher = watch(subagentsDir, { persistent: false }, () => {
            scan();
          });
        } catch {
          // fs.watch may not work on all systems
        }
      }
    },

    stop: () => {
      if (pollTimer) {
        clearInterval(pollTimer);
        pollTimer = null;
      }
      if (watcher) {
        watcher.close();
        watcher = null;
      }
    },

    getAgents: () => agents,
  };
}

/**
 * Format agents for display
 */
export function formatAgentsTable(agents: Map<string, SubagentInfo>): string {
  if (agents.size === 0) {
    return 'No subagents found';
  }

  const lines: string[] = [];
  lines.push('');
  lines.push(`${'Agent'.padEnd(10)} ${'State'.padEnd(12)} ${'Model'.padEnd(25)} ${'Tools'.padEnd(6)} Task`);
  lines.push('-'.repeat(80));

  for (const [id, info] of agents) {
    const stateIcon = {
      pending: '⏳',
      active: '🔄',
      waiting: '⏸️',
      completed: '✅',
      failed: '❌',
      cancelled: '🚫',
    }[info.state] || '❓';

    const shortId = id.slice(0, 8);
    const shortModel = info.model.replace('claude-', '').slice(0, 23);
    const shortTask = info.task.slice(0, 30).replace(/\n/g, ' ');

    lines.push(
      `${shortId.padEnd(10)} ${(stateIcon + ' ' + info.state).padEnd(12)} ${shortModel.padEnd(25)} ${String(info.toolCount).padEnd(6)} ${shortTask}`
    );
  }

  return lines.join('\n');
}

/**
 * Format agents as JSON summary
 */
export function formatAgentsJson(agents: Map<string, SubagentInfo>): object {
  const summary = {
    total: agents.size,
    byState: {
      pending: 0,
      active: 0,
      waiting: 0,
      completed: 0,
      failed: 0,
      cancelled: 0,
    } as Record<AgentState, number>,
    agents: [] as SubagentInfo[],
  };

  for (const info of agents.values()) {
    summary.byState[info.state]++;
    summary.agents.push(info);
  }

  return summary;
}
