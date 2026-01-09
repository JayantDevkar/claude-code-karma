/**
 * API Route Handlers for Dashboard
 * Phase 5: REST endpoints for session metrics
 * Phase 2 (Historical): Project and historical data endpoints
 * Phase 5 (Walkie-Talkie): Radio API endpoints for agent status
 */

import { Hono } from 'hono';
import type { MetricsAggregator } from '../aggregator.js';
import { sseManager } from './sse.js';
import { getDB } from '../db.js';
import type { AgentStatus, CacheStore } from '../walkie-talkie/types.js';
import { RUNNING_THRESHOLD_MS } from './config.js';

/**
 * Create API routes bound to an aggregator
 */
export function createApiRoutes(aggregator: MetricsAggregator): Hono {
  const api = new Hono();

  /**
   * GET /api/session
   * Current session metrics (first active session)
   */
  api.get('/session', (c) => {
    const sessions = aggregator.getAllSessions();

    if (sessions.length === 0) {
      return c.json({
        sessionId: null,
        metrics: {
          tokensIn: 0,
          tokensOut: 0,
          cost: 0,
        },
        agents: [],
        startedAt: null,
      });
    }

    // Return the most recently active session
    const session = sessions.sort(
      (a, b) => b.lastActivity.getTime() - a.lastActivity.getTime()
    )[0];

    const tree = aggregator.getAgentTree(session.sessionId);

    return c.json({
      sessionId: session.sessionId,
      projectName: session.projectName,
      projectPath: session.projectPath,
      metrics: {
        tokensIn: session.tokensIn,
        tokensOut: session.tokensOut,
        cost: session.cost.total,
        cacheRead: session.cacheReadTokens,
        cacheCreation: session.cacheCreationTokens,
        toolCalls: session.toolCalls,
      },
      agents: tree,
      startedAt: session.startedAt.toISOString(),
      lastActivity: session.lastActivity.toISOString(),
      models: Array.from(session.models),
    });
  });

  /**
   * GET /api/session/:id
   * Specific session metrics by ID
   */
  api.get('/session/:id', (c) => {
    const sessionId = c.req.param('id');
    const session = aggregator.getSessionMetrics(sessionId);

    if (!session) {
      return c.json({ error: 'Session not found' }, 404);
    }

    const tree = aggregator.getAgentTree(sessionId);
    const now = Date.now();
    const isRunning = session.status === 'active' &&
      (now - session.lastActivity.getTime()) < RUNNING_THRESHOLD_MS;

    return c.json({
      sessionId: session.sessionId,
      projectName: session.projectName,
      projectPath: session.projectPath,
      metrics: {
        tokensIn: session.tokensIn,
        tokensOut: session.tokensOut,
        cost: session.cost.total,
        cacheRead: session.cacheReadTokens,
        cacheCreation: session.cacheCreationTokens,
        toolCalls: session.toolCalls,
      },
      agents: tree,
      startedAt: session.startedAt.toISOString(),
      lastActivity: session.lastActivity.toISOString(),
      endedAt: session.endedAt?.toISOString(),
      isRunning,
      status: session.status,
      models: Array.from(session.models),
      toolUsage: Object.fromEntries(session.toolUsage),
    });
  });

  /**
   * GET /api/sessions
   * List all sessions (historical data)
   * Query: limit (default: 10), filter (all|active|completed)
   */
  api.get('/sessions', (c) => {
    const limit = parseInt(c.req.query('limit') || '10', 10);
    const filter = c.req.query('filter') || 'all';
    const now = Date.now();

    let sessions = aggregator.getAllSessions();

    // Apply filter
    if (filter === 'active') {
      sessions = sessions.filter(s => 
        s.status === 'active' && (now - s.lastActivity.getTime()) < RUNNING_THRESHOLD_MS
      );
    } else if (filter === 'completed') {
      sessions = sessions.filter(s => 
        s.status === 'ended' || (now - s.lastActivity.getTime()) >= RUNNING_THRESHOLD_MS
      );
    }

    // Sort by last activity, most recent first
    const sorted = sessions
      .sort((a, b) => b.lastActivity.getTime() - a.lastActivity.getTime())
      .slice(0, limit);

    return c.json({
      sessions: sorted.map((s) => {
        const isRunning = s.status === 'active' && 
          (now - s.lastActivity.getTime()) < RUNNING_THRESHOLD_MS;
        return {
          id: s.sessionId,
          projectName: s.projectName,
          projectPath: s.projectPath,
          agentCount: s.agentCount,
          tokensTotal: s.tokensIn + s.tokensOut,
          tokensIn: s.tokensIn,
          tokensOut: s.tokensOut,
          cost: s.cost.total,
          startedAt: s.startedAt.toISOString(),
          lastActivity: s.lastActivity.toISOString(),
          endedAt: s.endedAt?.toISOString(),
          isRunning,
          status: s.status,
          models: Array.from(s.models),
        };
      }),
      total: sessions.length,
    });
  });

  /**
   * GET /api/totals
   * Aggregated totals across all sessions
   */
  api.get('/totals', (c) => {
    const totals = aggregator.getTotals();

    return c.json({
      sessions: totals.sessions,
      agents: totals.agents,
      tokensIn: totals.tokensIn,
      tokensOut: totals.tokensOut,
      tokensTotal: totals.tokensIn + totals.tokensOut,
      cacheRead: totals.cacheReadTokens,
      cacheCreation: totals.cacheCreationTokens,
      cost: totals.totalCost,
      toolCalls: totals.toolCalls,
    });
  });

  /**
   * GET /api/health
   * Health check endpoint
   */
  api.get('/health', (c) => {
    return c.json({
      status: 'ok',
      clients: sseManager.getClientCount(),
      sessions: aggregator.getAllSessions().length,
      timestamp: new Date().toISOString(),
    });
  });

  // ============================================
  // Historical Dashboard Routes (Phase 2)
  // ============================================

  /**
   * GET /api/projects
   * List all projects with aggregated metrics
   */
  api.get('/projects', (c) => {
    try {
      const db = getDB();
      const projects = db.listProjects();
      return c.json(projects);
    } catch (err) {
      console.error('Error listing projects:', err);
      return c.json({ error: 'Internal error' }, 500);
    }
  });

  /**
   * GET /api/projects/:name
   * Get project detail with sessions
   */
  api.get('/projects/:name', (c) => {
    try {
      const name = decodeURIComponent(c.req.param('name'));
      const db = getDB();
      const detail = db.getProjectSummary(name);
      if (!detail) {
        return c.json({ error: 'Project not found' }, 404);
      }
      return c.json(detail);
    } catch (err) {
      console.error('Error getting project:', err);
      return c.json({ error: 'Internal error' }, 500);
    }
  });

  /**
   * GET /api/projects/:name/history
   * Get daily metrics for a project
   * Query: days (optional, default: 30)
   */
  api.get('/projects/:name/history', (c) => {
    try {
      const name = decodeURIComponent(c.req.param('name'));
      const days = parseInt(c.req.query('days') || '30', 10) || 30;
      const db = getDB();
      const metrics = db.getDailyMetrics(name, days);
      return c.json(metrics);
    } catch (err) {
      console.error('Error getting project history:', err);
      return c.json({ error: 'Internal error' }, 500);
    }
  });

  /**
   * GET /api/totals/history
   * Get daily metrics across all projects
   * Query: days (optional, default: 30)
   */
  api.get('/totals/history', (c) => {
    try {
      const days = parseInt(c.req.query('days') || '30', 10) || 30;
      const db = getDB();
      const metrics = db.getDailyMetrics(undefined, days);
      return c.json(metrics);
    } catch (err) {
      console.error('Error getting totals history:', err);
      return c.json({ error: 'Internal error' }, 500);
    }
  });

  // ============================================
  // Radio API Routes (Phase 5 Walkie-Talkie)
  // ============================================

  /**
   * GET /api/radio/agents
   * Get all agent statuses from radio cache
   */
  api.get('/radio/agents', (c) => {
    const statuses = aggregator.getAgentStatuses();
    if (statuses.size === 0 && !aggregator.getCache()) {
      return c.json({ error: 'Radio not enabled' }, 503);
    }

    return c.json(Object.fromEntries(statuses));
  });

  /**
   * GET /api/radio/agent/:id
   * Get specific agent status
   */
  api.get('/radio/agent/:id', (c) => {
    const agentId = c.req.param('id');
    const status = aggregator.getAgentStatus(agentId);

    if (!status) {
      return c.json({ error: 'Agent not found' }, 404);
    }

    return c.json(status);
  });

  /**
   * GET /api/radio/session/:id/tree
   * Build and return agent hierarchy tree for a session
   */
  api.get('/radio/session/:id/tree', (c) => {
    const cache = aggregator.getCache();
    const sessionId = c.req.param('id');

    if (!cache) {
      return c.json({ error: 'Radio not enabled' }, 503);
    }

    const agentIds = cache.get<string[]>(`session:${sessionId}:agents`) || [];

    // Handle case where session has no agents
    if (agentIds.length === 0) {
      return c.json({
        sessionId,
        tree: [],
        totalAgents: 0,
        maxDepth: 0,
      });
    }

    const { tree, maxDepth } = buildAgentTree(agentIds, cache);

    return c.json({
      sessionId,
      tree,
      totalAgents: agentIds.length,
      maxDepth,
    });
  });

  return api;
}

/**
 * Agent tree node for hierarchy display
 */
interface AgentTreeNode {
  agent: AgentStatus;
  children: AgentTreeNode[];
  depth: number;
}

/**
 * Result of building agent tree
 */
interface AgentTreeResult {
  tree: AgentTreeNode[];
  maxDepth: number;
}

/**
 * Build agent hierarchy tree from agent IDs
 */
function buildAgentTree(agentIds: string[], cache: CacheStore): AgentTreeResult {
  const statuses: AgentStatus[] = [];

  for (const id of agentIds) {
    const status = cache.get<AgentStatus>(`agent:${id}:status`);
    if (status) {
      statuses.push(status);
    }
  }

  // If no valid statuses found, return empty tree
  if (statuses.length === 0) {
    return { tree: [], maxDepth: 0 };
  }

  let maxDepth = 0;

  // Find root agents (those without a parent or whose parent is not in this session)
  const agentIdSet = new Set(agentIds);
  const roots = statuses.filter(s => !s.parentId || !agentIdSet.has(s.parentId));

  function buildNode(status: AgentStatus, depth: number): AgentTreeNode {
    if (depth > maxDepth) {
      maxDepth = depth;
    }

    const children = statuses.filter(s => s.parentId === status.agentId);
    return {
      agent: status,
      children: children.map(child => buildNode(child, depth + 1)),
      depth,
    };
  }

  const tree = roots.map(root => buildNode(root, 0));

  return { tree, maxDepth };
}
