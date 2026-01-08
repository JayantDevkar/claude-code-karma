/**
 * Metrics Aggregator for Claude Code sessions
 * Phase 3: In-memory metrics store with real-time aggregation
 * Phase 6.1: Session lifecycle management (FLAW-005)
 */

import { EventEmitter } from 'events';
import type { LogEntry, TokenUsage, ActivityEntry } from './types.js';
import { calculateCost, addCosts, emptyCostBreakdown, type CostBreakdown } from './cost.js';
import type { SessionInfo } from './discovery.js';
import type { LogWatcher } from './watcher.js';

// Re-export ActivityEntry for consumers
export type { ActivityEntry } from './types.js';

/**
 * Session status for lifecycle management
 */
export type SessionStatus = 'active' | 'ended';

/**
 * Aggregated metrics for a session
 */
export interface SessionMetrics {
  sessionId: string;
  projectPath: string;
  projectName: string;
  startedAt: Date;
  lastActivity: Date;
  endedAt?: Date;
  status: SessionStatus;
  tokensIn: number;
  tokensOut: number;
  cacheReadTokens: number;
  cacheCreationTokens: number;
  cost: CostBreakdown;
  models: Set<string>;
  agentCount: number;
  toolCalls: number;
  toolUsage: Map<string, number>;
  entryCount: number;
  assistantEntries: number;
}

/**
 * Metrics for a single agent
 */
export interface AgentMetrics {
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
  toolsUsed: Set<string>;
  toolCalls: number;
  entryCount: number;
}

/**
 * Node in the agent tree
 */
export interface AgentTreeNode {
  id: string;
  type: string;
  model: string;
  metrics: AgentMetrics;
  children: AgentTreeNode[];
}

/**
 * Create empty token usage
 */
function emptyUsage(): TokenUsage {
  return {
    inputTokens: 0,
    outputTokens: 0,
    cacheReadTokens: 0,
    cacheCreationTokens: 0,
  };
}

/**
 * Create empty session metrics
 */
function createEmptySessionMetrics(sessionId: string, projectPath: string, projectName: string): SessionMetrics {
  return {
    sessionId,
    projectPath,
    projectName,
    startedAt: new Date(),
    lastActivity: new Date(),
    endedAt: undefined,
    status: 'active',
    tokensIn: 0,
    tokensOut: 0,
    cacheReadTokens: 0,
    cacheCreationTokens: 0,
    cost: emptyCostBreakdown(),
    models: new Set(),
    agentCount: 0,
    toolCalls: 0,
    toolUsage: new Map(),
    entryCount: 0,
    assistantEntries: 0,
  };
}

/**
 * Create empty agent metrics
 */
function createEmptyAgentMetrics(agentId: string, sessionId: string, parentId?: string): AgentMetrics {
  return {
    agentId,
    sessionId,
    parentId,
    agentType: 'unknown',
    model: 'unknown',
    startedAt: new Date(),
    lastActivity: new Date(),
    tokensIn: 0,
    tokensOut: 0,
    cacheReadTokens: 0,
    cacheCreationTokens: 0,
    cost: emptyCostBreakdown(),
    toolsUsed: new Set(),
    toolCalls: 0,
    entryCount: 0,
  };
}

/**
 * Events emitted by MetricsAggregator
 */
export interface MetricsAggregatorEvents {
  'session:ended': (session: SessionMetrics) => void;
  'session:inactive': (sessionIds: string[]) => void;
  'activity': (entry: ActivityEntry) => void;
}

/**
 * Default maximum size for in-memory activity buffer (ring buffer style)
 */
const DEFAULT_ACTIVITY_BUFFER_SIZE = 1000;

/**
 * Metrics aggregator that accumulates usage across sessions and agents
 * Extends EventEmitter for session lifecycle events
 * Phase 6.3: Activity buffer for persistent activity tracking (FLAW-006)
 */
export class MetricsAggregator extends EventEmitter {
  private sessions: Map<string, SessionMetrics> = new Map();
  private agents: Map<string, AgentMetrics> = new Map();
  private sessionAgents: Map<string, Set<string>> = new Map(); // sessionId -> agentIds

  // Activity buffer (FLAW-006)
  private activityBuffer: ActivityEntry[] = [];
  private activityBufferMaxSize: number;

  constructor(options?: { activityBufferSize?: number }) {
    super();
    this.activityBufferMaxSize = options?.activityBufferSize ?? DEFAULT_ACTIVITY_BUFFER_SIZE;
  }

  // ============================================
  // Activity Buffer Methods (FLAW-006)
  // ============================================

  /**
   * Record an activity entry to the in-memory ring buffer
   * Emits 'activity' event when recorded
   */
  recordActivity(entry: ActivityEntry): void {
    this.activityBuffer.push(entry);

    // Ring buffer: remove oldest if exceeding max size
    if (this.activityBuffer.length > this.activityBufferMaxSize) {
      this.activityBuffer.shift();
    }

    this.emit('activity', entry);
  }

  /**
   * Get recent activity entries
   * @param limit Maximum number of entries to return (default: all)
   * @param sessionId Optional filter by session ID
   */
  getRecentActivity(limit?: number, sessionId?: string): ActivityEntry[] {
    let entries = this.activityBuffer;

    if (sessionId) {
      entries = entries.filter(e => e.sessionId === sessionId);
    }

    if (limit !== undefined && limit > 0) {
      return entries.slice(-limit);
    }

    return [...entries];
  }

  /**
   * Get activity count in buffer
   */
  getActivityCount(): number {
    return this.activityBuffer.length;
  }

  /**
   * Clear activity buffer (useful after persistence)
   */
  clearActivityBuffer(): void {
    this.activityBuffer = [];
  }

  /**
   * Get and clear activity buffer atomically
   * Used for batch persistence
   */
  drainActivityBuffer(): ActivityEntry[] {
    const entries = this.activityBuffer;
    this.activityBuffer = [];
    return entries;
  }

  /**
   * Process a new log entry
   */
  processEntry(entry: LogEntry, session: SessionInfo): void {
    // Get or create session metrics
    const sessionMetrics = this.getOrCreateSession(session);

    // Update timestamps
    if (entry.timestamp < sessionMetrics.startedAt) {
      sessionMetrics.startedAt = entry.timestamp;
    }
    if (entry.timestamp > sessionMetrics.lastActivity) {
      sessionMetrics.lastActivity = entry.timestamp;
    }

    sessionMetrics.entryCount++;

    // Process assistant entries with usage data
    if (entry.type === 'assistant' && entry.usage) {
      sessionMetrics.assistantEntries++;

      // Accumulate token counts
      sessionMetrics.tokensIn += entry.usage.inputTokens;
      sessionMetrics.tokensOut += entry.usage.outputTokens;
      sessionMetrics.cacheReadTokens += entry.usage.cacheReadTokens;
      sessionMetrics.cacheCreationTokens += entry.usage.cacheCreationTokens;

      // Track model
      if (entry.model) {
        sessionMetrics.models.add(entry.model);

        // Calculate cost for this entry
        const entryCost = calculateCost(entry.model, entry.usage);
        sessionMetrics.cost = addCosts(sessionMetrics.cost, entryCost);
      }

      // Track tool usage
      for (const tool of entry.toolCalls) {
        sessionMetrics.toolCalls++;
        const count = sessionMetrics.toolUsage.get(tool) ?? 0;
        sessionMetrics.toolUsage.set(tool, count + 1);
      }
    }

    // If this is an agent, also update agent metrics
    if (session.isAgent) {
      this.processAgentEntry(entry, session);
    }
  }

  /**
   * Process an entry for agent-specific metrics
   */
  private processAgentEntry(entry: LogEntry, session: SessionInfo): void {
    const agentMetrics = this.getOrCreateAgent(session);

    // Update timestamps
    if (entry.timestamp < agentMetrics.startedAt) {
      agentMetrics.startedAt = entry.timestamp;
    }
    if (entry.timestamp > agentMetrics.lastActivity) {
      agentMetrics.lastActivity = entry.timestamp;
    }

    agentMetrics.entryCount++;

    if (entry.type === 'assistant' && entry.usage) {
      agentMetrics.tokensIn += entry.usage.inputTokens;
      agentMetrics.tokensOut += entry.usage.outputTokens;
      agentMetrics.cacheReadTokens += entry.usage.cacheReadTokens;
      agentMetrics.cacheCreationTokens += entry.usage.cacheCreationTokens;

      if (entry.model) {
        agentMetrics.model = entry.model;
        const entryCost = calculateCost(entry.model, entry.usage);
        agentMetrics.cost = addCosts(agentMetrics.cost, entryCost);
      }

      for (const tool of entry.toolCalls) {
        agentMetrics.toolCalls++;
        agentMetrics.toolsUsed.add(tool);
      }
    }
  }

  /**
   * Register a new agent spawning
   */
  registerAgent(agent: SessionInfo, parentSession: SessionInfo): void {
    // Track agent under its parent session
    const sessionAgents = this.sessionAgents.get(parentSession.sessionId) ?? new Set();
    sessionAgents.add(agent.sessionId);
    this.sessionAgents.set(parentSession.sessionId, sessionAgents);

    // Update session's agent count
    const sessionMetrics = this.sessions.get(parentSession.sessionId);
    if (sessionMetrics) {
      sessionMetrics.agentCount = sessionAgents.size;
    }

    // Create agent metrics
    this.getOrCreateAgent(agent);
  }

  /**
   * Get or create session metrics
   */
  private getOrCreateSession(session: SessionInfo): SessionMetrics {
    // Use the parent session ID if this is an agent
    const sessionId = session.isAgent && session.parentSessionId
      ? session.parentSessionId
      : session.sessionId;

    let metrics = this.sessions.get(sessionId);

    if (!metrics) {
      metrics = createEmptySessionMetrics(
        sessionId,
        session.projectPath,
        session.projectName
      );
      this.sessions.set(sessionId, metrics);
    }

    return metrics;
  }

  /**
   * Get or create agent metrics
   */
  private getOrCreateAgent(session: SessionInfo): AgentMetrics {
    let metrics = this.agents.get(session.sessionId);

    if (!metrics) {
      metrics = createEmptyAgentMetrics(
        session.sessionId,
        session.parentSessionId ?? session.sessionId,
        session.parentSessionId
      );
      // Use agent type from session if available
      if (session.agentType) {
        metrics.agentType = session.agentType;
      }
      this.agents.set(session.sessionId, metrics);
    }

    return metrics;
  }

  /**
   * Get metrics for a session
   */
  getSessionMetrics(sessionId: string): SessionMetrics | undefined {
    return this.sessions.get(sessionId);
  }

  /**
   * Get metrics for an agent
   */
  getAgentMetrics(agentId: string): AgentMetrics | undefined {
    return this.agents.get(agentId);
  }

  /**
   * Get all sessions
   */
  getAllSessions(): SessionMetrics[] {
    return Array.from(this.sessions.values());
  }

  /**
   * Get all agents for a session
   */
  getSessionAgents(sessionId: string): AgentMetrics[] {
    const agentIds = this.sessionAgents.get(sessionId);
    if (!agentIds) return [];

    return Array.from(agentIds)
      .map(id => this.agents.get(id))
      .filter((m): m is AgentMetrics => m !== undefined);
  }

  /**
   * Build agent tree for a session
   */
  getAgentTree(sessionId: string): AgentTreeNode[] {
    const agents = this.getSessionAgents(sessionId);
    const roots: AgentTreeNode[] = [];

    // Build node map
    const nodeMap = new Map<string, AgentTreeNode>();

    for (const agent of agents) {
      nodeMap.set(agent.agentId, {
        id: agent.agentId,
        type: agent.agentType,
        model: agent.model,
        metrics: agent,
        children: [],
      });
    }

    // Build tree structure
    for (const agent of agents) {
      const node = nodeMap.get(agent.agentId)!;

      if (agent.parentId && nodeMap.has(agent.parentId)) {
        nodeMap.get(agent.parentId)!.children.push(node);
      } else {
        roots.push(node);
      }
    }

    return roots;
  }

  /**
   * Get aggregated totals across all sessions
   */
  getTotals(): {
    sessions: number;
    agents: number;
    tokensIn: number;
    tokensOut: number;
    cacheReadTokens: number;
    cacheCreationTokens: number;
    totalCost: number;
    toolCalls: number;
  } {
    let tokensIn = 0;
    let tokensOut = 0;
    let cacheReadTokens = 0;
    let cacheCreationTokens = 0;
    let totalCost = 0;
    let toolCalls = 0;
    let agents = 0;

    for (const session of this.sessions.values()) {
      tokensIn += session.tokensIn;
      tokensOut += session.tokensOut;
      cacheReadTokens += session.cacheReadTokens;
      cacheCreationTokens += session.cacheCreationTokens;
      totalCost += session.cost.total;
      toolCalls += session.toolCalls;
      agents += session.agentCount;
    }

    return {
      sessions: this.sessions.size,
      agents,
      tokensIn,
      tokensOut,
      cacheReadTokens,
      cacheCreationTokens,
      totalCost,
      toolCalls,
    };
  }

  /**
   * Clear all metrics
   */
  clear(): void {
    this.sessions.clear();
    this.agents.clear();
    this.sessionAgents.clear();
  }

  // ============================================
  // Session Lifecycle Management (FLAW-005)
  // ============================================

  /**
   * End a session by setting its endedAt timestamp and status
   * Emits 'session:ended' event with the session data
   */
  endSession(sessionId: string): boolean {
    const session = this.sessions.get(sessionId);
    if (!session) {
      return false;
    }

    // Already ended - no-op
    if (session.status === 'ended') {
      return true;
    }

    session.endedAt = new Date();
    session.status = 'ended';

    this.emit('session:ended', session);
    return true;
  }

  /**
   * Detect sessions that haven't had activity within the threshold period
   * @param thresholdMs Inactivity threshold in milliseconds (default: 5 minutes)
   * @returns Array of session IDs that are inactive
   */
  detectInactiveSessions(thresholdMs: number = 300000): string[] {
    const now = Date.now();
    const inactiveSessions: string[] = [];

    for (const session of this.sessions.values()) {
      // Only check active sessions
      if (session.status !== 'active') {
        continue;
      }

      const timeSinceActivity = now - session.lastActivity.getTime();
      if (timeSinceActivity > thresholdMs) {
        inactiveSessions.push(session.sessionId);
      }
    }

    // Emit event if inactive sessions detected
    if (inactiveSessions.length > 0) {
      this.emit('session:inactive', inactiveSessions);
    }

    return inactiveSessions;
  }

  /**
   * Get all active sessions (status === 'active')
   */
  getActiveSessions(): SessionMetrics[] {
    return Array.from(this.sessions.values()).filter(s => s.status === 'active');
  }

  /**
   * Get all ended sessions (status === 'ended')
   */
  getEndedSessions(): SessionMetrics[] {
    return Array.from(this.sessions.values()).filter(s => s.status === 'ended');
  }

  /**
   * Remove ended sessions from memory to free up resources
   * Returns the number of sessions cleared
   */
  clearEndedSessions(): number {
    const endedSessionIds: string[] = [];

    for (const session of this.sessions.values()) {
      if (session.status === 'ended') {
        endedSessionIds.push(session.sessionId);
      }
    }

    for (const sessionId of endedSessionIds) {
      // Remove session
      this.sessions.delete(sessionId);

      // Remove associated agents
      const agentIds = this.sessionAgents.get(sessionId);
      if (agentIds) {
        for (const agentId of agentIds) {
          this.agents.delete(agentId);
        }
        this.sessionAgents.delete(sessionId);
      }
    }

    return endedSessionIds.length;
  }

  /**
   * Export metrics as JSON-serializable object
   */
  export(): {
    sessions: Array<Omit<SessionMetrics, 'models' | 'toolUsage'> & { models: string[]; toolUsage: [string, number][] }>;
    agents: Array<Omit<AgentMetrics, 'toolsUsed'> & { toolsUsed: string[] }>;
  } {
    return {
      sessions: Array.from(this.sessions.values()).map(s => ({
        ...s,
        models: Array.from(s.models),
        toolUsage: Array.from(s.toolUsage.entries()),
      })),
      agents: Array.from(this.agents.values()).map(a => ({
        ...a,
        toolsUsed: Array.from(a.toolsUsed),
      })),
    };
  }
}

/**
 * Wire a watcher to an aggregator
 */
export function connectWatcherToAggregator(
  watcher: LogWatcher,
  aggregator: MetricsAggregator
): void {
  watcher.on('entry', (entry, session) => {
    aggregator.processEntry(entry, session);
  });

  watcher.on('agent:spawn', (agent, parentSession) => {
    aggregator.registerAgent(agent, parentSession);
  });
}

/**
 * Create a connected watcher and aggregator pair
 */
export function createMetricsSystem(options?: {
  projectPath?: string;
  processExisting?: boolean;
}): { watcher: LogWatcher; aggregator: MetricsAggregator } {
  // Import dynamically to avoid circular dependency
  const { LogWatcher } = require('./watcher.js');

  const watcher = new LogWatcher(options);
  const aggregator = new MetricsAggregator();

  connectWatcherToAggregator(watcher, aggregator);

  return { watcher, aggregator };
}
