/**
 * karma status command
 * Phase 4: Display current session metrics
 */

import chalk from 'chalk';
import type { SessionMetrics, AgentTreeNode } from '../aggregator.js';
import { MetricsAggregator } from '../aggregator.js';
import { emptyCostBreakdown } from '../cost.js';
import {
  discoverSessions,
  getLatestSession,
  discoverProjects,
  getSessionAgents,
  type SessionInfo,
} from '../discovery.js';
import { parseSessionFile } from '../parser.js';
import { formatNumber, formatCost, formatDuration } from '../tui/utils/format.js';

/**
 * Status command options
 */
export interface StatusOptions {
  project?: string;
  all?: boolean;
  json?: boolean;
  tree?: boolean;
}

/**
 * Format relative time (e.g., "2 hours ago")
 */
function formatRelativeTime(date: Date): string {
  const now = new Date();
  const diffMs = now.getTime() - date.getTime();
  const diffSeconds = Math.floor(diffMs / 1000);
  const diffMinutes = Math.floor(diffSeconds / 60);
  const diffHours = Math.floor(diffMinutes / 60);
  const diffDays = Math.floor(diffHours / 24);

  if (diffSeconds < 60) return 'just now';
  if (diffMinutes < 60) return `${diffMinutes} minute${diffMinutes !== 1 ? 's' : ''} ago`;
  if (diffHours < 24) return `${diffHours} hour${diffHours !== 1 ? 's' : ''} ago`;
  return `${diffDays} day${diffDays !== 1 ? 's' : ''} ago`;
}

/**
 * Check if a session is stale (no activity in 30 minutes)
 */
function isStaleSession(lastActivity: Date): boolean {
  const thirtyMinutesMs = 30 * 60 * 1000;
  return Date.now() - lastActivity.getTime() > thirtyMinutesMs;
}

/**
 * Draw box border
 */
const BOX_CHARS = {
  topLeft: '╭',
  topRight: '╮',
  bottomLeft: '╰',
  bottomRight: '╯',
  horizontal: '─',
  vertical: '│',
  divider: '├',
  dividerRight: '┤',
};

function drawBox(lines: string[], width: number): string[] {
  const output: string[] = [];
  const innerWidth = width - 2;

  // Top border
  output.push(
    BOX_CHARS.topLeft + BOX_CHARS.horizontal.repeat(innerWidth) + BOX_CHARS.topRight
  );

  // Content lines
  for (const line of lines) {
    if (line === '---') {
      // Divider
      output.push(
        BOX_CHARS.divider + BOX_CHARS.horizontal.repeat(innerWidth) + BOX_CHARS.dividerRight
      );
    } else {
      const stripped = line.replace(/\x1b\[[0-9;]*m/g, ''); // Strip ANSI for length calc
      const padding = innerWidth - stripped.length;
      output.push(BOX_CHARS.vertical + line + ' '.repeat(Math.max(0, padding)) + BOX_CHARS.vertical);
    }
  }

  // Bottom border
  output.push(
    BOX_CHARS.bottomLeft + BOX_CHARS.horizontal.repeat(innerWidth) + BOX_CHARS.bottomRight
  );

  return output;
}

/**
 * Build metrics from a session file
 */
async function buildSessionMetrics(session: SessionInfo): Promise<SessionMetrics> {
  const entries = await parseSessionFile(session.filePath);
  const aggregator = new MetricsAggregator();

  for (const entry of entries) {
    aggregator.processEntry(entry, session);
  }

  const metrics = aggregator.getSessionMetrics(session.sessionId);

  if (!metrics) {
    // Return empty metrics if nothing was aggregated
    return {
      sessionId: session.sessionId,
      projectPath: session.projectPath,
      projectName: session.projectName,
      startedAt: session.modifiedAt,
      lastActivity: session.modifiedAt,
      endedAt: undefined,
      status: 'active',
      tokensIn: 0,
      tokensOut: 0,
      cacheReadTokens: 0,
      cacheCreationTokens: 0,
      cost: { inputCost: 0, outputCost: 0, cacheReadCost: 0, cacheCreationCost: 0, total: 0, model: 'none' },
      models: new Set(),
      agentCount: 0,
      toolCalls: 0,
      toolUsage: new Map(),
      entryCount: 0,
      assistantEntries: 0,
    };
  }

  return metrics;
}

/**
 * Display formatted status output
 */
function displayStatus(metrics: SessionMetrics, isStale: boolean): void {
  const width = 56;
  const lines: string[] = [];

  // Header section
  lines.push(`  ${chalk.bold.cyan('KARMA STATUS')}`);
  lines.push(`  Session: ${chalk.yellow(metrics.sessionId.slice(0, 8))}`);
  lines.push(`  Project: ${chalk.green(metrics.projectName)}`);
  lines.push(
    `  Started: ${formatRelativeTime(metrics.startedAt)}` +
      (isStale ? chalk.yellow(' (stale)') : chalk.green(' (active)'))
  );

  lines.push('---');

  // Tokens section
  lines.push(`  ${chalk.bold.dim('TOKENS')}`);
  lines.push(`    Input:   ${chalk.white(formatNumber(metrics.tokensIn).padStart(10))}`);
  lines.push(`    Output:  ${chalk.white(formatNumber(metrics.tokensOut).padStart(10))}`);
  lines.push(`    Cached:  ${chalk.white(formatNumber(metrics.cacheReadTokens).padStart(10))}`);

  lines.push('---');

  // Cost section
  lines.push(`  ${chalk.bold.dim('COST')}`);
  lines.push(`    Total:   ${chalk.green(formatCost(metrics.cost.total).padStart(10))}`);
  lines.push(`    Input:   ${chalk.white(formatCost(metrics.cost.inputCost).padStart(10))}`);
  lines.push(`    Output:  ${chalk.white(formatCost(metrics.cost.outputCost).padStart(10))}`);
  lines.push(
    `    Cache:   ${chalk.dim(formatCost(metrics.cost.cacheReadCost).padStart(10))} ${chalk.dim('(saved)')}`
  );

  lines.push('---');

  // Agents section
  lines.push(`  ${chalk.bold.dim('ACTIVITY')}`);
  lines.push(`    Agents:  ${String(metrics.agentCount).padStart(10)}`);
  lines.push(`    Tools:   ${String(metrics.toolCalls).padStart(10)} calls`);
  lines.push(`    Models:  ${Array.from(metrics.models).join(', ') || 'none'}`);

  const boxed = drawBox(lines, width);
  console.log(boxed.join('\n'));
}

/**
 * Display JSON output
 */
function displayJson(metrics: SessionMetrics): void {
  const output = {
    sessionId: metrics.sessionId,
    project: metrics.projectName,
    projectPath: metrics.projectPath,
    startedAt: metrics.startedAt.toISOString(),
    lastActivity: metrics.lastActivity.toISOString(),
    tokens: {
      input: metrics.tokensIn,
      output: metrics.tokensOut,
      cacheRead: metrics.cacheReadTokens,
      cacheCreation: metrics.cacheCreationTokens,
    },
    cost: {
      total: metrics.cost.total,
      input: metrics.cost.inputCost,
      output: metrics.cost.outputCost,
      cacheRead: metrics.cost.cacheReadCost,
      cacheCreation: metrics.cost.cacheCreationCost,
    },
    agents: metrics.agentCount,
    toolCalls: metrics.toolCalls,
    models: Array.from(metrics.models),
    entryCount: metrics.entryCount,
  };

  console.log(JSON.stringify(output, null, 2));
}

/**
 * Display all sessions summary
 */
async function displayAllSessions(): Promise<void> {
  const projects = await discoverProjects();

  if (projects.length === 0) {
    console.log(chalk.yellow('No Claude Code sessions found.'));
    return;
  }

  console.log(chalk.bold.cyan('\nAll Sessions\n'));

  for (const project of projects) {
    const mainSessions = project.sessions.filter(s => !s.isAgent);
    if (mainSessions.length === 0) continue;

    const latestSession = mainSessions[0];
    const metrics = await buildSessionMetrics(latestSession);
    const isStale = isStaleSession(metrics.lastActivity);

    console.log(
      `${chalk.green(project.projectName.padEnd(30))} ` +
        `${chalk.yellow(latestSession.sessionId.slice(0, 8))} ` +
        `${formatNumber(metrics.tokensIn + metrics.tokensOut).padStart(8)} tokens ` +
        `${chalk.green(formatCost(metrics.cost.total).padStart(8))} ` +
        (isStale ? chalk.dim('(stale)') : chalk.green('(active)'))
    );
  }

  console.log();
}

/**
 * Tree display constants
 */
const TREE_CHARS = {
  vertical: '│',
  branch: '├',
  lastBranch: '└',
  horizontal: '──',
  space: '   ',
};

/**
 * Get status indicator for agent node
 */
function getStatusIndicator(node: AgentTreeNode): string {
  const now = Date.now();
  const lastActivity = node.metrics.lastActivity.getTime();
  const isRunning = now - lastActivity < 5000; // Active in last 5 seconds

  if (isRunning) {
    return chalk.yellow('⟳'); // Running
  }
  return chalk.green('✓'); // Complete
}

/**
 * Render a single tree node
 */
function renderTreeNode(
  node: AgentTreeNode,
  prefix: string,
  isLast: boolean,
  depth: number
): string[] {
  const lines: string[] = [];

  // Build connector
  const connector = depth === 0 ? '' : (isLast ? TREE_CHARS.lastBranch : TREE_CHARS.branch) + TREE_CHARS.horizontal;

  // Status indicator
  const status = getStatusIndicator(node);

  // Agent type display
  const typeDisplay = node.type === 'main' ? chalk.cyan('main') : chalk.magenta(node.type);

  // Model display
  const modelDisplay = chalk.dim(`(${node.model})`);

  // Cost display
  const cost = node.metrics.cost?.total ?? 0;
  const costDisplay = chalk.green(formatCost(cost));

  // Build the line
  const line = `${prefix}${connector} ${status} ${typeDisplay} ${modelDisplay} ${costDisplay}`;
  lines.push(line);

  // Render children
  const childPrefix = prefix + (depth === 0 ? '' : (isLast ? TREE_CHARS.space : TREE_CHARS.vertical + '  '));
  node.children.forEach((child, index) => {
    const isChildLast = index === node.children.length - 1;
    lines.push(...renderTreeNode(child, childPrefix, isChildLast, depth + 1));
  });

  return lines;
}

/**
 * Build root node for agent tree (like useAgentTree.ts buildRootNode)
 */
function buildRootNode(
  nodes: AgentTreeNode[],
  sessionId: string,
  metrics: SessionMetrics
): AgentTreeNode {
  return {
    id: sessionId,
    type: 'main',
    model: metrics.models.values().next().value || 'sonnet',
    metrics: {
      agentId: sessionId,
      sessionId,
      agentType: 'main',
      model: metrics.models.values().next().value || 'sonnet',
      startedAt: metrics.startedAt,
      lastActivity: metrics.lastActivity,
      tokensIn: metrics.tokensIn,
      tokensOut: metrics.tokensOut,
      cacheReadTokens: metrics.cacheReadTokens,
      cacheCreationTokens: metrics.cacheCreationTokens,
      cost: metrics.cost,
      toolsUsed: new Set(),
      toolCalls: metrics.toolCalls,
      entryCount: metrics.entryCount,
    },
    children: nodes,
  };
}

/**
 * Display agent tree
 */
async function displayTree(session: SessionInfo, metrics: SessionMetrics): Promise<void> {
  // Build aggregator and parse session to get agents
  const entries = await parseSessionFile(session.filePath);
  const aggregator = new MetricsAggregator();

  for (const entry of entries) {
    aggregator.processEntry(entry, session);
  }

  // Load agent files with types (same pattern as dashboard preload - fixes empty tree)
  const agents = await getSessionAgents(session.projectPath, session.sessionId, { includeAgentTypes: true });
  for (const agent of agents) {
    try {
      aggregator.registerAgent(agent, session);
      const agentEntries = await parseSessionFile(agent.filePath);
      for (const entry of agentEntries) {
        aggregator.processEntry(entry, agent);
      }
    } catch {
      // Skip agents that can't be parsed
    }
  }

  const agentNodes = aggregator.getAgentTree(session.sessionId);
  const rootNode = buildRootNode(agentNodes, session.sessionId, metrics);

  console.log();
  console.log(chalk.bold.cyan('AGENT HIERARCHY'));
  console.log(chalk.dim(`Session: ${session.sessionId.slice(0, 8)} | Project: ${session.projectName}`));
  console.log();

  const lines = renderTreeNode(rootNode, '', true, 0);
  console.log(lines.join('\n'));

  // Summary - count actual loaded agents, not stale metrics
  const totalAgents = agents.length + 1; // +1 for main
  console.log();
  console.log(chalk.dim(`Total: ${totalAgents} agent${totalAgents !== 1 ? 's' : ''} | Cost: ${formatCost(metrics.cost.total)}`));
  console.log();
}

/**
 * Display agent tree as JSON
 */
async function displayTreeJson(session: SessionInfo, metrics: SessionMetrics): Promise<void> {
  const entries = await parseSessionFile(session.filePath);
  const aggregator = new MetricsAggregator();

  for (const entry of entries) {
    aggregator.processEntry(entry, session);
  }

  // Load agent files with types (same pattern as dashboard preload)
  const agents = await getSessionAgents(session.projectPath, session.sessionId, { includeAgentTypes: true });
  for (const agent of agents) {
    try {
      aggregator.registerAgent(agent, session);
      const agentEntries = await parseSessionFile(agent.filePath);
      for (const entry of agentEntries) {
        aggregator.processEntry(entry, agent);
      }
    } catch {
      // Skip agents that can't be parsed
    }
  }

  const agentNodes = aggregator.getAgentTree(session.sessionId);

  // Convert to serializable format
  function serializeNode(node: AgentTreeNode): object {
    return {
      id: node.id,
      type: node.type,
      model: node.model,
      tokensIn: node.metrics.tokensIn,
      tokensOut: node.metrics.tokensOut,
      cost: node.metrics.cost?.total ?? 0,
      toolCalls: node.metrics.toolCalls,
      children: node.children.map(serializeNode),
    };
  }

  const rootNode = buildRootNode(agentNodes, session.sessionId, metrics);
  const output = {
    sessionId: session.sessionId,
    project: session.projectName,
    tree: serializeNode(rootNode),
    totalAgents: agents.length + 1, // +1 for main
    totalCost: metrics.cost.total,
  };

  console.log(JSON.stringify(output, null, 2));
}

/**
 * Main status command handler
 */
export async function statusCommand(options: StatusOptions): Promise<void> {
  // Handle --all flag
  if (options.all) {
    if (options.json) {
      const projects = await discoverProjects();
      const results = [];

      for (const project of projects) {
        const mainSessions = project.sessions.filter(s => !s.isAgent);
        if (mainSessions.length === 0) continue;

        const metrics = await buildSessionMetrics(mainSessions[0]);
        results.push({
          project: project.projectName,
          sessionId: mainSessions[0].sessionId,
          tokens: metrics.tokensIn + metrics.tokensOut,
          cost: metrics.cost.total,
          lastActivity: metrics.lastActivity.toISOString(),
        });
      }

      console.log(JSON.stringify(results, null, 2));
    } else {
      await displayAllSessions();
    }
    return;
  }

  // Find the session to display
  let session: SessionInfo | null = null;

  if (options.project) {
    // Find session for specific project
    const projects = await discoverProjects();
    const matchingProject = projects.find(
      p =>
        p.projectName.toLowerCase().includes(options.project!.toLowerCase()) ||
        p.projectPath.toLowerCase().includes(options.project!.toLowerCase())
    );

    if (matchingProject) {
      const mainSessions = matchingProject.sessions.filter(s => !s.isAgent);
      session = mainSessions[0] ?? null;
    }
  } else {
    // Get the most recent session
    session = await getLatestSession();
  }

  // Handle no session found
  if (!session) {
    if (options.project) {
      console.log(chalk.yellow(`No active session found for project: ${options.project}`));
      console.log(chalk.dim('Try: karma status --all to see all sessions'));
    } else {
      console.log(chalk.yellow('No active Claude Code session found.'));
      console.log(chalk.dim('Start a Claude Code session to see metrics here.'));
    }
    return;
  }

  // Build and display metrics
  const metrics = await buildSessionMetrics(session);
  const isStale = isStaleSession(metrics.lastActivity);

  // Handle --tree flag
  if (options.tree) {
    if (options.json) {
      await displayTreeJson(session, metrics);
    } else {
      await displayTree(session, metrics);
    }
    return;
  }

  if (options.json) {
    displayJson(metrics);
  } else {
    displayStatus(metrics, isStale);
  }
}
