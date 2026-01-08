/**
 * karma watch command
 * Phase 5: Real-time streaming display of session activity
 */

import chalk from 'chalk';
import type { SessionMetrics, AgentTreeNode } from '../aggregator.js';
import { MetricsAggregator, connectWatcherToAggregator } from '../aggregator.js';
import { LogWatcher } from '../watcher.js';
import {
  discoverProjects,
  getLatestSession,
  type SessionInfo,
} from '../discovery.js';
import type { LogEntry } from '../types.js';
import { formatNumber, formatCost } from '../tui/utils/format.js';

/**
 * Watch command options
 */
export interface WatchOptions {
  project?: string;
  compact?: boolean;
  activityOnly?: boolean;
}

/**
 * Activity entry for the ring buffer
 */
interface ActivityEntry {
  timestamp: Date;
  model: string;
  type: 'tool' | 'agent_spawn' | 'agent_complete' | 'message';
  content: string;
  agentId?: string;
  isAgent: boolean;
}

/**
 * Ring buffer for activity entries
 */
class ActivityBuffer {
  private entries: ActivityEntry[] = [];
  private maxSize: number;

  constructor(maxSize = 20) {
    this.maxSize = maxSize;
  }

  add(entry: ActivityEntry): void {
    this.entries.push(entry);
    if (this.entries.length > this.maxSize) {
      this.entries.shift();
    }
  }

  getAll(): ActivityEntry[] {
    return [...this.entries];
  }

  clear(): void {
    this.entries = [];
  }
}

/**
 * ANSI escape sequences for terminal control
 */
const ANSI = {
  clearScreen: '\x1b[2J',
  cursorHome: '\x1b[H',
  cursorHide: '\x1b[?25l',
  cursorShow: '\x1b[?25h',
  saveCursor: '\x1b[s',
  restoreCursor: '\x1b[u',
  clearLine: '\x1b[2K',
  moveTo: (row: number, col: number) => `\x1b[${row};${col}H`,
};

/**
 * Box drawing characters
 */
const BOX = {
  topLeft: '┌',
  topRight: '┐',
  bottomLeft: '└',
  bottomRight: '┘',
  horizontal: '─',
  vertical: '│',
  dividerLeft: '├',
  dividerRight: '┤',
  teeDown: '┬',
  teeUp: '┴',
};

/**
 * Format a timestamp as HH:MM:SS
 */
function formatTime(date: Date): string {
  return date.toTimeString().slice(0, 8);
}

/**
 * Shorten model name
 */
function shortModel(model: string): string {
  if (model.includes('opus')) return 'opus';
  if (model.includes('sonnet')) return 'sonnet';
  if (model.includes('haiku')) return 'haiku';
  return model.slice(0, 8);
}

/**
 * Color code by model
 */
function modelColor(model: string): (text: string) => string {
  if (model.includes('opus')) return chalk.magenta;
  if (model.includes('sonnet')) return chalk.blue;
  if (model.includes('haiku')) return chalk.green;
  return chalk.white;
}

/**
 * Color code by tool type
 */
function toolColor(tool: string): (text: string) => string {
  if (tool.includes('Read') || tool.includes('Glob') || tool.includes('Grep')) {
    return chalk.cyan;
  }
  if (tool.includes('Write') || tool.includes('Edit')) {
    return chalk.yellow;
  }
  if (tool.includes('Bash')) {
    return chalk.red;
  }
  if (tool.includes('Task')) {
    return chalk.magenta;
  }
  return chalk.white;
}

/**
 * WatchDisplay manages the terminal output
 */
class WatchDisplay {
  private width: number;
  private activityBuffer: ActivityBuffer;
  private lastMetrics: SessionMetrics | null = null;
  private projectName: string;
  private sessionId: string;
  private compact: boolean;
  private activityOnly: boolean;
  private isRunning = false;

  constructor(options: {
    projectName: string;
    sessionId: string;
    compact?: boolean;
    activityOnly?: boolean;
  }) {
    this.width = Math.min(process.stdout.columns || 80, 80);
    this.activityBuffer = new ActivityBuffer(options.activityOnly ? 30 : 15);
    this.projectName = options.projectName;
    this.sessionId = options.sessionId;
    this.compact = options.compact ?? false;
    this.activityOnly = options.activityOnly ?? false;
  }

  /**
   * Start the display
   */
  start(): void {
    this.isRunning = true;
    process.stdout.write(ANSI.clearScreen + ANSI.cursorHome + ANSI.cursorHide);
    this.render();
  }

  /**
   * Stop and cleanup
   */
  cleanup(): void {
    this.isRunning = false;
    process.stdout.write(ANSI.cursorShow);
    console.log('\n' + chalk.dim('Watch stopped.'));
  }

  /**
   * Add an activity entry
   */
  addActivity(entry: ActivityEntry): void {
    this.activityBuffer.add(entry);
    if (this.isRunning) {
      this.render();
    }
  }

  /**
   * Update metrics
   */
  updateMetrics(metrics: SessionMetrics): void {
    this.lastMetrics = metrics;
    if (this.isRunning) {
      this.render();
    }
  }

  /**
   * Render the full display
   */
  private render(): void {
    const lines: string[] = [];
    const innerWidth = this.width - 2;

    // Header
    lines.push(this.renderHeader(innerWidth));
    lines.push(this.renderDivider(innerWidth));

    if (!this.activityOnly) {
      // Tokens row
      lines.push(this.renderTokens(innerWidth));
      lines.push(this.renderDivider(innerWidth));
    }

    // Activity section
    lines.push(this.renderActivityHeader(innerWidth));
    lines.push(...this.renderActivityEntries(innerWidth));

    if (!this.activityOnly && !this.compact) {
      lines.push(this.renderDivider(innerWidth));
      // Agent tree
      lines.push(...this.renderAgentTree(innerWidth));
    }

    // Footer
    lines.push(this.renderFooter(innerWidth));

    // Output
    process.stdout.write(ANSI.cursorHome);
    console.log(lines.join('\n'));
  }

  private renderHeader(width: number): string {
    const metrics = this.lastMetrics;
    const cost = metrics ? formatCost(metrics.cost.total) : '$0.00';
    const agents = metrics ? metrics.agentCount : 0;

    const title = chalk.bold.cyan('KARMA WATCH') + chalk.dim(' - ') + chalk.green(this.projectName);
    const costStr = chalk.dim('Cost: ') + chalk.green(cost);

    const line1Left = `  ${title}`;
    const line1Right = `${costStr}  `;

    // Calculate padding
    const line1LeftLen = this.stripAnsi(line1Left).length;
    const line1RightLen = this.stripAnsi(line1Right).length;
    const padding1 = Math.max(0, width - line1LeftLen - line1RightLen);

    const sessionStr = chalk.dim('Session: ') + chalk.yellow(this.sessionId.slice(0, 8));
    const agentsStr = chalk.dim('Agents: ') + (agents > 0 ? chalk.cyan(String(agents)) : chalk.dim('0'));
    const watchStr = chalk.green('↑ Watching');

    const line2Left = `  ${sessionStr} ${chalk.dim('|')} ${agentsStr}`;
    const line2Right = `${watchStr}  `;

    const line2LeftLen = this.stripAnsi(line2Left).length;
    const line2RightLen = this.stripAnsi(line2Right).length;
    const padding2 = Math.max(0, width - line2LeftLen - line2RightLen);

    return (
      BOX.topLeft + BOX.horizontal.repeat(width) + BOX.topRight + '\n' +
      BOX.vertical + line1Left + ' '.repeat(padding1) + line1Right + BOX.vertical + '\n' +
      BOX.vertical + line2Left + ' '.repeat(padding2) + line2Right + BOX.vertical
    );
  }

  private renderDivider(width: number): string {
    return BOX.dividerLeft + BOX.horizontal.repeat(width) + BOX.dividerRight;
  }

  private renderTokens(width: number): string {
    const metrics = this.lastMetrics;
    const tokensIn = metrics ? formatNumber(metrics.tokensIn) : '0';
    const tokensOut = metrics ? formatNumber(metrics.tokensOut) : '0';
    const cacheTokens = metrics ? formatNumber(metrics.cacheReadTokens) : '0';

    const content = `  ${chalk.bold.dim('TOKENS')}       ` +
      `${chalk.dim('In:')} ${chalk.white(tokensIn.padStart(8))}  ` +
      `${chalk.dim('Out:')} ${chalk.white(tokensOut.padStart(8))}  ` +
      `${chalk.dim('Cache:')} ${chalk.white(cacheTokens.padStart(8))}`;

    const contentLen = this.stripAnsi(content).length;
    const padding = Math.max(0, width - contentLen);

    return BOX.vertical + content + ' '.repeat(padding) + BOX.vertical;
  }

  private renderActivityHeader(width: number): string {
    const header = `  ${chalk.bold.dim('ACTIVITY')}`;
    const headerLen = this.stripAnsi(header).length;
    const padding = Math.max(0, width - headerLen);
    return BOX.vertical + header + ' '.repeat(padding) + BOX.vertical;
  }

  private renderActivityEntries(width: number): string[] {
    const entries = this.activityBuffer.getAll();
    const lines: string[] = [];
    const maxEntries = this.activityOnly ? 25 : 10;

    const displayEntries = entries.slice(-maxEntries);

    if (displayEntries.length === 0) {
      const emptyMsg = chalk.dim('  Waiting for activity...');
      const padding = Math.max(0, width - this.stripAnsi(emptyMsg).length);
      lines.push(BOX.vertical + emptyMsg + ' '.repeat(padding) + BOX.vertical);
    } else {
      for (const entry of displayEntries) {
        const line = this.formatActivityLine(entry, width);
        lines.push(BOX.vertical + line + BOX.vertical);
      }
    }

    // Fill remaining space
    const remaining = maxEntries - displayEntries.length;
    for (let i = 0; i < Math.min(remaining, 3); i++) {
      lines.push(BOX.vertical + ' '.repeat(width) + BOX.vertical);
    }

    return lines;
  }

  private formatActivityLine(entry: ActivityEntry, maxWidth: number): string {
    const time = chalk.dim(formatTime(entry.timestamp));
    const model = modelColor(entry.model)(`[${shortModel(entry.model)}]`);

    let prefix = '  ';
    if (entry.isAgent) {
      prefix = entry.type === 'agent_spawn' ? '  ├─ ' : '  │  ';
    }

    let content: string;
    switch (entry.type) {
      case 'tool':
        content = toolColor(entry.content)(entry.content);
        break;
      case 'agent_spawn':
        content = chalk.magenta('Agent spawned');
        break;
      case 'agent_complete':
        content = chalk.green('Agent completed');
        break;
      default:
        content = chalk.dim(entry.content);
    }

    const line = `${prefix}${time}  ${model}  ${content}`;
    const lineLen = this.stripAnsi(line).length;

    if (lineLen > maxWidth) {
      // Truncate content
      const overflow = lineLen - maxWidth + 3;
      const truncatedContent = entry.content.slice(0, -overflow) + '...';
      return `${prefix}${time}  ${model}  ${toolColor(entry.content)(truncatedContent)}`.padEnd(maxWidth);
    }

    return line + ' '.repeat(Math.max(0, maxWidth - lineLen));
  }

  private renderAgentTree(width: number): string[] {
    const lines: string[] = [];
    const header = `  ${chalk.bold.dim('AGENT TREE')}`;
    const headerLen = this.stripAnsi(header).length;
    lines.push(BOX.vertical + header + ' '.repeat(width - headerLen) + BOX.vertical);

    const metrics = this.lastMetrics;
    if (!metrics || metrics.agentCount === 0) {
      const msg = chalk.dim('  ● main') + chalk.dim(' (no agents)');
      const msgLen = this.stripAnsi(msg).length;
      lines.push(BOX.vertical + msg + ' '.repeat(width - msgLen) + BOX.vertical);
    } else {
      // Show main + agents count
      const mainLine = `  ${chalk.green('●')} main (${shortModel(Array.from(metrics.models)[0] || 'unknown')}) - ${formatCost(metrics.cost.total)}`;
      const mainLen = this.stripAnsi(mainLine).length;
      lines.push(BOX.vertical + mainLine + ' '.repeat(width - mainLen) + BOX.vertical);

      const agentLine = `    └─ ${metrics.agentCount} agent${metrics.agentCount !== 1 ? 's' : ''}`;
      const agentLen = agentLine.length;
      lines.push(BOX.vertical + chalk.dim(agentLine) + ' '.repeat(width - agentLen) + BOX.vertical);
    }

    return lines;
  }

  private renderFooter(width: number): string {
    const msg = chalk.dim('Press Ctrl+C to exit');
    const msgLen = this.stripAnsi(msg).length;
    const padding = Math.floor((width - msgLen) / 2);

    return (
      BOX.bottomLeft + BOX.horizontal.repeat(width) + BOX.bottomRight + '\n' +
      ' '.repeat(padding) + msg
    );
  }

  private stripAnsi(str: string): string {
    return str.replace(/\x1b\[[0-9;]*m/g, '');
  }
}

/**
 * Extract activity info from a log entry
 */
function extractActivity(entry: LogEntry, session: SessionInfo): ActivityEntry | null {
  if (entry.type !== 'assistant') return null;

  const model = entry.model || 'unknown';

  // Check for tool calls
  if (entry.toolCalls.length > 0) {
    return {
      timestamp: entry.timestamp,
      model,
      type: 'tool',
      content: entry.toolCalls.join(', '),
      isAgent: session.isAgent,
      agentId: session.isAgent ? session.sessionId : undefined,
    };
  }

  return null;
}

/**
 * Main watch command handler
 */
export async function watchCommand(options: WatchOptions): Promise<void> {
  // Find the session to watch
  let targetProject: string | undefined;

  if (options.project) {
    const projects = await discoverProjects();
    const matching = projects.find(
      p =>
        p.projectName.toLowerCase().includes(options.project!.toLowerCase()) ||
        p.projectPath.toLowerCase().includes(options.project!.toLowerCase())
    );
    if (matching) {
      targetProject = matching.projectPath;
    } else {
      console.log(chalk.yellow(`No project found matching: ${options.project}`));
      return;
    }
  }

  // Get the latest session
  const session = await getLatestSession(targetProject);

  if (!session) {
    console.log(chalk.yellow('No active Claude Code session found.'));
    console.log(chalk.dim('Start a Claude Code session to watch metrics here.'));
    return;
  }

  // Create watcher and aggregator
  const watcher = new LogWatcher({
    projectPath: session.projectPath,
    processExisting: true,
  });

  const aggregator = new MetricsAggregator();
  connectWatcherToAggregator(watcher, aggregator);

  // Create display
  const display = new WatchDisplay({
    projectName: session.projectName,
    sessionId: session.sessionId,
    compact: options.compact,
    activityOnly: options.activityOnly,
  });

  // Wire up events
  watcher.on('entry', (entry: LogEntry, sessionInfo: SessionInfo) => {
    const activity = extractActivity(entry, sessionInfo);
    if (activity) {
      display.addActivity(activity);
    }

    // Update metrics display
    const metrics = aggregator.getSessionMetrics(session.sessionId);
    if (metrics) {
      display.updateMetrics(metrics);
    }
  });

  watcher.on('agent:spawn', (agent: SessionInfo) => {
    display.addActivity({
      timestamp: new Date(),
      model: 'system',
      type: 'agent_spawn',
      content: `Agent ${agent.sessionId.slice(0, 8)}`,
      isAgent: true,
      agentId: agent.sessionId,
    });
  });

  watcher.on('error', (error: Error) => {
    console.error(chalk.red('Watcher error:'), error.message);
  });

  watcher.on('ready', () => {
    // Initial metrics update
    const metrics = aggregator.getSessionMetrics(session.sessionId);
    if (metrics) {
      display.updateMetrics(metrics);
    }
  });

  // Handle graceful shutdown
  const cleanup = async () => {
    display.cleanup();
    await watcher.stop();
    process.exit(0);
  };

  process.on('SIGINT', cleanup);
  process.on('SIGTERM', cleanup);

  // Start watching
  display.start();
  watcher.watch();
}
