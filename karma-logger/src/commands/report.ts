/**
 * karma report command
 * Phase 6: Historical session reporting from SQLite
 */

import chalk from 'chalk';
import { KarmaDB, getDB, type SessionRecord, type SessionSummary, type AgentRecord } from '../db.js';
import { formatNumber, formatCost, formatDuration } from '../tui/utils/format.js';
import { parseModelsJson, parseToolUsageJson } from '../converters.js';

/**
 * Report command options
 */
export interface ReportOptions {
  sessionId?: string;
  project?: string;
  since?: string;
  limit?: number;
  json?: boolean;
  csv?: boolean;
}

/**
 * Box drawing characters
 */
const BOX = {
  topLeft: '╭',
  topRight: '╮',
  bottomLeft: '╰',
  bottomRight: '╯',
  horizontal: '─',
  vertical: '│',
  divider: '├',
  dividerRight: '┤',
};

/**
 * Draw a box around content lines
 */
function drawBox(lines: string[], width: number): string[] {
  const output: string[] = [];
  const innerWidth = width - 2;

  output.push(BOX.topLeft + BOX.horizontal.repeat(innerWidth) + BOX.topRight);

  for (const line of lines) {
    if (line === '---') {
      output.push(BOX.divider + BOX.horizontal.repeat(innerWidth) + BOX.dividerRight);
    } else {
      const stripped = line.replace(/\x1b\[[0-9;]*m/g, '');
      const padding = innerWidth - stripped.length;
      output.push(BOX.vertical + line + ' '.repeat(Math.max(0, padding)) + BOX.vertical);
    }
  }

  output.push(BOX.bottomLeft + BOX.horizontal.repeat(innerWidth) + BOX.bottomRight);
  return output;
}

/**
 * Format date for display
 */
function formatDate(date: Date): string {
  const now = new Date();
  const isToday = date.toDateString() === now.toDateString();
  const yesterday = new Date(now);
  yesterday.setDate(yesterday.getDate() - 1);
  const isYesterday = date.toDateString() === yesterday.toDateString();

  if (isToday) return 'Today';
  if (isYesterday) return 'Yesterday';

  return date.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
}

/**
 * Format duration from minutes
 */
function formatMinutes(minutes: number): string {
  if (minutes < 60) return `${minutes}m`;
  const hours = Math.floor(minutes / 60);
  const mins = minutes % 60;
  return mins > 0 ? `${hours}h ${mins}m` : `${hours}h`;
}

/**
 * Format time of day
 */
function formatTime(date: Date): string {
  return date.toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit', hour12: false });
}

/**
 * Display session list
 */
function displaySessionList(sessions: SessionSummary[], totals: ReturnType<KarmaDB['getTotals']>): void {
  const width = 66;
  const lines: string[] = [];

  lines.push(`  ${chalk.bold.cyan('RECENT SESSIONS')}`);
  lines.push('---');

  // Header row
  lines.push(
    `  ${chalk.dim('ID'.padEnd(10))}` +
    `${chalk.dim('PROJECT'.padEnd(18))}` +
    `${chalk.dim('DATE'.padEnd(12))}` +
    `${chalk.dim('DURATION'.padEnd(10))}` +
    `${chalk.dim('COST')}`
  );

  // Session rows
  for (const session of sessions) {
    const id = session.id.slice(0, 8);
    const project = session.projectName.slice(0, 16).padEnd(18);
    const date = formatDate(session.startedAt).padEnd(12);
    const duration = formatMinutes(session.duration).padEnd(10);
    const cost = formatCost(session.costTotal);

    lines.push(`  ${chalk.yellow(id)}  ${chalk.white(project)}${chalk.dim(date)}${duration}${chalk.green(cost)}`);
  }

  if (sessions.length === 0) {
    lines.push(chalk.dim('  No sessions found.'));
  }

  lines.push('---');

  // Totals footer
  const period = '7 days';
  lines.push(`  ${chalk.bold.dim(`TOTALS (${period})`)}`);
  lines.push(
    `    Sessions: ${chalk.white(String(totals.sessions))}  |  ` +
    `Cost: ${chalk.green(formatCost(totals.costTotal))}  |  ` +
    `Tokens: ${chalk.white(formatNumber(totals.tokensIn + totals.tokensOut))}`
  );

  const boxed = drawBox(lines, width);
  console.log(boxed.join('\n'));
}

/**
 * Display detailed session report
 */
function displaySessionDetail(session: SessionRecord, agents: AgentRecord[]): void {
  const width = 66;
  const lines: string[] = [];

  const startedAt = new Date(session.startedAt);
  const endedAt = session.endedAt ? new Date(session.endedAt) : null;
  const durationMs = endedAt ? endedAt.getTime() - startedAt.getTime() : 0;
  const durationMinutes = Math.round(durationMs / 60000);

  // Header
  lines.push(`  ${chalk.bold.cyan('SESSION REPORT:')} ${chalk.yellow(session.id.slice(0, 8))}`);
  lines.push(`  Project: ${chalk.green(session.projectName)}`);
  lines.push(
    `  Duration: ${formatMinutes(durationMinutes)} ` +
    `(${formatTime(startedAt)} - ${endedAt ? formatTime(endedAt) : 'ongoing'})`
  );

  lines.push('---');

  // Summary section
  lines.push(`  ${chalk.bold.dim('SUMMARY')}`);
  lines.push(`    Total Cost:     ${chalk.green(formatCost(session.costTotal))}`);
  lines.push(`    Tokens In:      ${formatNumber(session.tokensIn)}`);
  lines.push(`    Tokens Out:     ${formatNumber(session.tokensOut)}`);
  lines.push(`    Tokens Cached:  ${formatNumber(session.cacheReadTokens)}`);
  lines.push(`    Agents:         ${session.agentCount}`);
  lines.push(`    Tool Calls:     ${session.toolCalls}`);

  // Top agents section (if any)
  if (agents.length > 0) {
    lines.push('---');
    lines.push(`  ${chalk.bold.dim('TOP AGENTS BY COST')}`);

    const sortedAgents = [...agents].sort((a, b) => b.costTotal - a.costTotal).slice(0, 5);
    const totalCost = session.costTotal || 1;

    sortedAgents.forEach((agent, i) => {
      const percent = Math.round((agent.costTotal / totalCost) * 100);
      const agentId = agent.id.slice(0, 7);
      const agentType = agent.agentType.slice(0, 12).padEnd(14);
      const cost = formatCost(agent.costTotal).padStart(8);

      lines.push(`  ${i + 1}. ${chalk.yellow(agentId)} ${agentType} ${chalk.green(cost)}  (${percent}%)`);
    });
  }

  // Top tools section
  const toolUsageMap = parseToolUsageJson(session.toolUsage);
  const sortedTools = Array.from(toolUsageMap.entries())
    .sort((a, b) => b[1] - a[1])
    .slice(0, 5);

  if (sortedTools.length > 0) {
    lines.push('---');
    lines.push(`  ${chalk.bold.dim('TOP TOOLS')}`);

    sortedTools.forEach(([ tool, count ], i) => {
      const toolName = tool.padEnd(18);
      lines.push(`  ${i + 1}. ${toolName} ${chalk.dim(String(count) + ' calls')}`);
    });
  }

  // Models used
  const modelsSet = parseModelsJson(session.models);
  if (modelsSet.size > 0) {
    lines.push('---');
    lines.push(`  ${chalk.bold.dim('MODELS USED')}`);
    lines.push(`    ${chalk.dim(Array.from(modelsSet).join(', '))}`);
  }

  const boxed = drawBox(lines, width);
  console.log(boxed.join('\n'));
}

/**
 * Output JSON format
 */
function outputJson(data: unknown): void {
  console.log(JSON.stringify(data, null, 2));
}

/**
 * Output CSV format
 */
function outputCsv(sessions: SessionSummary[]): void {
  console.log('id,project,started_at,duration_minutes,cost,tokens_in,tokens_out,agents');
  for (const s of sessions) {
    console.log(
      `${s.id},${s.projectName},${s.startedAt.toISOString()},${s.duration},` +
      `${s.costTotal.toFixed(4)},${s.tokensIn},${s.tokensOut},${s.agentCount}`
    );
  }
}

/**
 * Parse since date option
 */
function parseSinceDate(since: string): Date {
  // Try ISO date format first
  const isoDate = new Date(since);
  if (!isNaN(isoDate.getTime())) {
    return isoDate;
  }

  // Try relative formats: "7d", "1w", "30d"
  const match = since.match(/^(\d+)([dwmh])$/);
  if (match) {
    const value = parseInt(match[1], 10);
    const unit = match[2];
    const now = new Date();

    switch (unit) {
      case 'h': // hours
        now.setHours(now.getHours() - value);
        break;
      case 'd': // days
        now.setDate(now.getDate() - value);
        break;
      case 'w': // weeks
        now.setDate(now.getDate() - value * 7);
        break;
      case 'm': // months
        now.setMonth(now.getMonth() - value);
        break;
    }
    return now;
  }

  // Default: 7 days ago
  const defaultDate = new Date();
  defaultDate.setDate(defaultDate.getDate() - 7);
  return defaultDate;
}

/**
 * Main report command handler
 */
export async function reportCommand(options: ReportOptions): Promise<void> {
  const db = getDB();

  try {
    // Handle specific session detail view
    if (options.sessionId) {
      const detail = db.getSessionDetail(options.sessionId);

      if (!detail) {
        // Try partial match
        const sessions = db.listSessions({ limit: 100 });
        const match = sessions.find(s => s.id.startsWith(options.sessionId!));

        if (match) {
          const fullDetail = db.getSessionDetail(match.id);
          if (fullDetail) {
            if (options.json) {
              outputJson(fullDetail);
            } else {
              displaySessionDetail(fullDetail.session, fullDetail.agents);
            }
            return;
          }
        }

        console.log(chalk.yellow(`Session not found: ${options.sessionId}`));
        console.log(chalk.dim('Try: karma report --help for usage'));
        return;
      }

      if (options.json) {
        outputJson(detail);
      } else {
        displaySessionDetail(detail.session, detail.agents);
      }
      return;
    }

    // List sessions
    const since = options.since ? parseSinceDate(options.since) : undefined;
    const sevenDaysAgo = new Date();
    sevenDaysAgo.setDate(sevenDaysAgo.getDate() - 7);

    const sessions = db.listSessions({
      limit: options.limit ?? 10,
      project: options.project,
      since,
    });

    const totals = db.getTotals({
      project: options.project,
      since: since ?? sevenDaysAgo,
    });

    // Output format
    if (options.json) {
      outputJson({ sessions, totals });
    } else if (options.csv) {
      outputCsv(sessions);
    } else {
      displaySessionList(sessions, totals);
    }
  } catch (error) {
    if ((error as NodeJS.ErrnoException).code === 'ENOENT') {
      console.log(chalk.yellow('No session history found.'));
      console.log(chalk.dim('Session history will be recorded as you use karma.'));
    } else {
      throw error;
    }
  }
}

/**
 * Sync current live sessions to database
 * Called periodically or on session end
 */
export async function syncSessionsToDB(): Promise<void> {
  const { discoverProjects } = await import('../discovery.js');
  const { parseSessionFile } = await import('../parser.js');
  const { MetricsAggregator } = await import('../aggregator.js');

  const db = getDB();
  const projects = await discoverProjects();

  for (const project of projects) {
    for (const session of project.sessions) {
      if (session.isAgent) continue; // Skip agents, they're saved with their parent

      // Parse and aggregate the session
      const entries = await parseSessionFile(session.filePath);
      const aggregator = new MetricsAggregator();

      for (const entry of entries) {
        aggregator.processEntry(entry, session);
      }

      const metrics = aggregator.getSessionMetrics(session.sessionId);
      if (!metrics) continue;

      // Save to database
      db.saveSession(metrics);

      // Save agents
      const agents = aggregator.getSessionAgents(session.sessionId);
      for (const agent of agents) {
        db.saveAgent(agent);
      }
    }
  }
}
