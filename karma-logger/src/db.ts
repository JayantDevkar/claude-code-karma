/**
 * SQLite Database Module for Karma Logger
 * Phase 6: Persistence layer for session history
 */

import Database from 'better-sqlite3';
import * as fs from 'fs';
import * as path from 'path';
import * as os from 'os';
import type { CostBreakdown } from './cost.js';

// ============================================
// Types
// ============================================

/**
 * Session record for database storage
 */
export interface SessionRecord {
  id: string;
  projectPath: string;
  projectName: string;
  startedAt: string; // ISO 8601
  endedAt: string | null;
  models: string; // JSON array
  tokensIn: number;
  tokensOut: number;
  cacheReadTokens: number;
  cacheCreationTokens: number;
  costTotal: number;
  costInput: number;
  costOutput: number;
  costCacheRead: number;
  costCacheCreation: number;
  agentCount: number;
  toolCalls: number;
  toolUsage: string; // JSON object
}

/**
 * Agent record for database storage
 */
export interface AgentRecord {
  id: string;
  sessionId: string;
  parentId: string | null;
  agentType: string;
  model: string;
  startedAt: string;
  endedAt: string | null;
  tokensIn: number;
  tokensOut: number;
  cacheReadTokens: number;
  cacheCreationTokens: number;
  costTotal: number;
  toolsUsed: string; // JSON array
  toolCalls: number;
}

/**
 * Session summary for list views
 */
export interface SessionSummary {
  id: string;
  projectName: string;
  startedAt: Date;
  endedAt: Date | null;
  duration: number; // minutes
  costTotal: number;
  tokensIn: number;
  tokensOut: number;
  agentCount: number;
}

/**
 * Options for listing sessions
 */
export interface ListOptions {
  limit?: number;
  offset?: number;
  project?: string;
  since?: Date;
  until?: Date;
}

// ============================================
// Database Class
// ============================================

/**
 * SQLite database wrapper for karma session data
 */
export class KarmaDB {
  private db: Database.Database;
  private dbPath: string;

  constructor(dbPath?: string) {
    this.dbPath = dbPath ?? path.join(os.homedir(), '.karma', 'karma.db');

    // Ensure directory exists
    const dir = path.dirname(this.dbPath);
    if (!fs.existsSync(dir)) {
      fs.mkdirSync(dir, { recursive: true });
    }

    this.db = new Database(this.dbPath);
    this.db.pragma('journal_mode = WAL');
    this.migrate();
  }

  /**
   * Run database migrations
   */
  private migrate(): void {
    // Create sessions table
    this.db.exec(`
      CREATE TABLE IF NOT EXISTS sessions (
        id TEXT PRIMARY KEY,
        project_path TEXT NOT NULL,
        project_name TEXT NOT NULL,
        started_at TEXT NOT NULL,
        ended_at TEXT,
        models TEXT DEFAULT '[]',
        tokens_in INTEGER DEFAULT 0,
        tokens_out INTEGER DEFAULT 0,
        cache_read_tokens INTEGER DEFAULT 0,
        cache_creation_tokens INTEGER DEFAULT 0,
        cost_total REAL DEFAULT 0,
        cost_input REAL DEFAULT 0,
        cost_output REAL DEFAULT 0,
        cost_cache_read REAL DEFAULT 0,
        cost_cache_creation REAL DEFAULT 0,
        agent_count INTEGER DEFAULT 0,
        tool_calls INTEGER DEFAULT 0,
        tool_usage TEXT DEFAULT '{}'
      );

      CREATE INDEX IF NOT EXISTS idx_sessions_project ON sessions(project_name);
      CREATE INDEX IF NOT EXISTS idx_sessions_started ON sessions(started_at);
    `);

    // Create agents table
    this.db.exec(`
      CREATE TABLE IF NOT EXISTS agents (
        id TEXT PRIMARY KEY,
        session_id TEXT NOT NULL,
        parent_id TEXT,
        agent_type TEXT,
        model TEXT,
        started_at TEXT NOT NULL,
        ended_at TEXT,
        tokens_in INTEGER DEFAULT 0,
        tokens_out INTEGER DEFAULT 0,
        cache_read_tokens INTEGER DEFAULT 0,
        cache_creation_tokens INTEGER DEFAULT 0,
        cost_total REAL DEFAULT 0,
        tools_used TEXT DEFAULT '[]',
        tool_calls INTEGER DEFAULT 0,
        FOREIGN KEY (session_id) REFERENCES sessions(id)
      );

      CREATE INDEX IF NOT EXISTS idx_agents_session ON agents(session_id);
    `);

    // Create schema version table for future migrations
    this.db.exec(`
      CREATE TABLE IF NOT EXISTS schema_version (
        version INTEGER PRIMARY KEY,
        applied_at TEXT NOT NULL
      );
    `);

    // Record initial migration if not present
    const version = this.db.prepare('SELECT MAX(version) as v FROM schema_version').get() as { v: number | null };
    if (version.v === null) {
      this.db.prepare('INSERT INTO schema_version (version, applied_at) VALUES (?, ?)').run(1, new Date().toISOString());
    }
  }

  /**
   * Save or update a session
   */
  saveSession(session: {
    sessionId: string;
    projectPath: string;
    projectName: string;
    startedAt: Date;
    lastActivity: Date;
    tokensIn: number;
    tokensOut: number;
    cacheReadTokens: number;
    cacheCreationTokens: number;
    cost: CostBreakdown;
    models: Set<string> | string[];
    agentCount: number;
    toolCalls: number;
    toolUsage: Map<string, number> | Record<string, number>;
  }): void {
    const models = Array.isArray(session.models)
      ? session.models
      : Array.from(session.models);

    const toolUsage = session.toolUsage instanceof Map
      ? Object.fromEntries(session.toolUsage)
      : session.toolUsage;

    const stmt = this.db.prepare(`
      INSERT INTO sessions (
        id, project_path, project_name, started_at, ended_at,
        models, tokens_in, tokens_out, cache_read_tokens, cache_creation_tokens,
        cost_total, cost_input, cost_output, cost_cache_read, cost_cache_creation,
        agent_count, tool_calls, tool_usage
      ) VALUES (
        @id, @projectPath, @projectName, @startedAt, @endedAt,
        @models, @tokensIn, @tokensOut, @cacheReadTokens, @cacheCreationTokens,
        @costTotal, @costInput, @costOutput, @costCacheRead, @costCacheCreation,
        @agentCount, @toolCalls, @toolUsage
      )
      ON CONFLICT(id) DO UPDATE SET
        ended_at = @endedAt,
        tokens_in = @tokensIn,
        tokens_out = @tokensOut,
        cache_read_tokens = @cacheReadTokens,
        cache_creation_tokens = @cacheCreationTokens,
        cost_total = @costTotal,
        cost_input = @costInput,
        cost_output = @costOutput,
        cost_cache_read = @costCacheRead,
        cost_cache_creation = @costCacheCreation,
        agent_count = @agentCount,
        tool_calls = @toolCalls,
        tool_usage = @toolUsage,
        models = @models
    `);

    stmt.run({
      id: session.sessionId,
      projectPath: session.projectPath,
      projectName: session.projectName,
      startedAt: session.startedAt.toISOString(),
      endedAt: session.lastActivity.toISOString(),
      models: JSON.stringify(models),
      tokensIn: session.tokensIn,
      tokensOut: session.tokensOut,
      cacheReadTokens: session.cacheReadTokens,
      cacheCreationTokens: session.cacheCreationTokens,
      costTotal: session.cost.total,
      costInput: session.cost.inputCost,
      costOutput: session.cost.outputCost,
      costCacheRead: session.cost.cacheReadCost,
      costCacheCreation: session.cost.cacheCreationCost,
      agentCount: session.agentCount,
      toolCalls: session.toolCalls,
      toolUsage: JSON.stringify(toolUsage),
    });
  }

  /**
   * Save or update an agent
   */
  saveAgent(agent: {
    agentId: string;
    sessionId: string;
    parentId?: string;
    agentType: string;
    model: string;
    startedAt: Date;
    lastActivity: Date;
    tokensIn: number;
    tokensOut: number;
    cacheReadTokens: number;
    cacheCreationTokens: number;
    cost: CostBreakdown;
    toolsUsed: Set<string> | string[];
    toolCalls: number;
  }): void {
    const toolsUsed = Array.isArray(agent.toolsUsed)
      ? agent.toolsUsed
      : Array.from(agent.toolsUsed);

    const stmt = this.db.prepare(`
      INSERT INTO agents (
        id, session_id, parent_id, agent_type, model,
        started_at, ended_at, tokens_in, tokens_out,
        cache_read_tokens, cache_creation_tokens, cost_total,
        tools_used, tool_calls
      ) VALUES (
        @id, @sessionId, @parentId, @agentType, @model,
        @startedAt, @endedAt, @tokensIn, @tokensOut,
        @cacheReadTokens, @cacheCreationTokens, @costTotal,
        @toolsUsed, @toolCalls
      )
      ON CONFLICT(id) DO UPDATE SET
        ended_at = @endedAt,
        tokens_in = @tokensIn,
        tokens_out = @tokensOut,
        cache_read_tokens = @cacheReadTokens,
        cache_creation_tokens = @cacheCreationTokens,
        cost_total = @costTotal,
        tools_used = @toolsUsed,
        tool_calls = @toolCalls
    `);

    stmt.run({
      id: agent.agentId,
      sessionId: agent.sessionId,
      parentId: agent.parentId ?? null,
      agentType: agent.agentType,
      model: agent.model,
      startedAt: agent.startedAt.toISOString(),
      endedAt: agent.lastActivity.toISOString(),
      tokensIn: agent.tokensIn,
      tokensOut: agent.tokensOut,
      cacheReadTokens: agent.cacheReadTokens,
      cacheCreationTokens: agent.cacheCreationTokens,
      costTotal: agent.cost.total,
      toolsUsed: JSON.stringify(toolsUsed),
      toolCalls: agent.toolCalls,
    });
  }

  /**
   * Get a session by ID
   */
  getSession(id: string): SessionRecord | null {
    const row = this.db.prepare(`
      SELECT
        id, project_path as projectPath, project_name as projectName,
        started_at as startedAt, ended_at as endedAt, models,
        tokens_in as tokensIn, tokens_out as tokensOut,
        cache_read_tokens as cacheReadTokens, cache_creation_tokens as cacheCreationTokens,
        cost_total as costTotal, cost_input as costInput, cost_output as costOutput,
        cost_cache_read as costCacheRead, cost_cache_creation as costCacheCreation,
        agent_count as agentCount, tool_calls as toolCalls, tool_usage as toolUsage
      FROM sessions WHERE id = ?
    `).get(id) as SessionRecord | undefined;

    return row ?? null;
  }

  /**
   * Get session with full detail including agents
   */
  getSessionDetail(id: string): {
    session: SessionRecord;
    agents: AgentRecord[];
  } | null {
    const session = this.getSession(id);
    if (!session) return null;

    const agents = this.db.prepare(`
      SELECT
        id, session_id as sessionId, parent_id as parentId,
        agent_type as agentType, model, started_at as startedAt,
        ended_at as endedAt, tokens_in as tokensIn, tokens_out as tokensOut,
        cache_read_tokens as cacheReadTokens, cache_creation_tokens as cacheCreationTokens,
        cost_total as costTotal, tools_used as toolsUsed, tool_calls as toolCalls
      FROM agents WHERE session_id = ?
      ORDER BY started_at ASC
    `).all(id) as AgentRecord[];

    return { session, agents };
  }

  /**
   * List sessions with optional filtering
   */
  listSessions(options: ListOptions = {}): SessionSummary[] {
    const { limit = 10, offset = 0, project, since, until } = options;

    let sql = `
      SELECT
        id,
        project_name as projectName,
        started_at as startedAt,
        ended_at as endedAt,
        cost_total as costTotal,
        tokens_in as tokensIn,
        tokens_out as tokensOut,
        agent_count as agentCount
      FROM sessions
      WHERE 1=1
    `;

    const params: unknown[] = [];

    if (project) {
      sql += ` AND project_name LIKE ?`;
      params.push(`%${project}%`);
    }

    if (since) {
      sql += ` AND started_at >= ?`;
      params.push(since.toISOString());
    }

    if (until) {
      sql += ` AND started_at <= ?`;
      params.push(until.toISOString());
    }

    sql += ` ORDER BY started_at DESC LIMIT ? OFFSET ?`;
    params.push(limit, offset);

    const rows = this.db.prepare(sql).all(...params) as Array<{
      id: string;
      projectName: string;
      startedAt: string;
      endedAt: string | null;
      costTotal: number;
      tokensIn: number;
      tokensOut: number;
      agentCount: number;
    }>;

    return rows.map(row => {
      const startedAt = new Date(row.startedAt);
      const endedAt = row.endedAt ? new Date(row.endedAt) : null;
      const duration = endedAt
        ? Math.round((endedAt.getTime() - startedAt.getTime()) / 60000)
        : 0;

      return {
        id: row.id,
        projectName: row.projectName,
        startedAt,
        endedAt,
        duration,
        costTotal: row.costTotal,
        tokensIn: row.tokensIn,
        tokensOut: row.tokensOut,
        agentCount: row.agentCount,
      };
    });
  }

  /**
   * Get aggregate totals for a time period
   */
  getTotals(options: { since?: Date; until?: Date; project?: string } = {}): {
    sessions: number;
    costTotal: number;
    tokensIn: number;
    tokensOut: number;
    cacheReadTokens: number;
    agentCount: number;
    toolCalls: number;
  } {
    let sql = `
      SELECT
        COUNT(*) as sessions,
        COALESCE(SUM(cost_total), 0) as costTotal,
        COALESCE(SUM(tokens_in), 0) as tokensIn,
        COALESCE(SUM(tokens_out), 0) as tokensOut,
        COALESCE(SUM(cache_read_tokens), 0) as cacheReadTokens,
        COALESCE(SUM(agent_count), 0) as agentCount,
        COALESCE(SUM(tool_calls), 0) as toolCalls
      FROM sessions
      WHERE 1=1
    `;

    const params: unknown[] = [];

    if (options.project) {
      sql += ` AND project_name LIKE ?`;
      params.push(`%${options.project}%`);
    }

    if (options.since) {
      sql += ` AND started_at >= ?`;
      params.push(options.since.toISOString());
    }

    if (options.until) {
      sql += ` AND started_at <= ?`;
      params.push(options.until.toISOString());
    }

    const row = this.db.prepare(sql).get(...params) as {
      sessions: number;
      costTotal: number;
      tokensIn: number;
      tokensOut: number;
      cacheReadTokens: number;
      agentCount: number;
      toolCalls: number;
    };

    return row;
  }

  /**
   * Delete a session and its agents
   */
  deleteSession(id: string): boolean {
    const info = this.db.prepare('DELETE FROM agents WHERE session_id = ?').run(id);
    const sessionInfo = this.db.prepare('DELETE FROM sessions WHERE id = ?').run(id);
    return sessionInfo.changes > 0;
  }

  /**
   * Get top tools across all sessions
   */
  getTopTools(options: { limit?: number; since?: Date } = {}): Array<{ tool: string; count: number }> {
    const { limit = 10, since } = options;

    let sql = `SELECT tool_usage FROM sessions WHERE 1=1`;
    const params: unknown[] = [];

    if (since) {
      sql += ` AND started_at >= ?`;
      params.push(since.toISOString());
    }

    const rows = this.db.prepare(sql).all(...params) as Array<{ tool_usage: string }>;

    // Aggregate tool usage across sessions
    const toolCounts = new Map<string, number>();
    for (const row of rows) {
      const usage = JSON.parse(row.tool_usage) as Record<string, number>;
      for (const [tool, count] of Object.entries(usage)) {
        toolCounts.set(tool, (toolCounts.get(tool) ?? 0) + count);
      }
    }

    // Sort and return top tools
    return Array.from(toolCounts.entries())
      .sort((a, b) => b[1] - a[1])
      .slice(0, limit)
      .map(([tool, count]) => ({ tool, count }));
  }

  /**
   * Close the database connection
   */
  close(): void {
    this.db.close();
  }

  /**
   * Get database path
   */
  getPath(): string {
    return this.dbPath;
  }
}

/**
 * Get singleton database instance
 */
let _db: KarmaDB | null = null;

export function getDB(): KarmaDB {
  if (!_db) {
    _db = new KarmaDB();
  }
  return _db;
}

/**
 * Close singleton database
 */
export function closeDB(): void {
  if (_db) {
    _db.close();
    _db = null;
  }
}
