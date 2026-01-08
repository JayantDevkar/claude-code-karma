/**
 * Aggregator unit tests
 * Phase 3: Metrics aggregation tests
 */

import { describe, it, expect, beforeEach } from 'vitest';
import {
  MetricsAggregator,
  connectWatcherToAggregator,
} from '../src/aggregator.js';
import type { LogEntry } from '../src/types.js';
import type { SessionInfo } from '../src/discovery.js';

// Mock session info
const createMockSessionInfo = (overrides: Partial<SessionInfo> = {}): SessionInfo => ({
  sessionId: 'test-session-123',
  projectPath: 'Users-test-project',
  projectName: 'test-project',
  filePath: '/mock/path/session.jsonl',
  modifiedAt: new Date(),
  isAgent: false,
  ...overrides,
});

// Mock log entry
const createMockEntry = (overrides: Partial<LogEntry> = {}): LogEntry => ({
  type: 'assistant',
  uuid: `entry-${Math.random().toString(36).substring(7)}`,
  parentUuid: null,
  sessionId: 'test-session-123',
  timestamp: new Date(),
  toolCalls: [],
  hasThinking: false,
  ...overrides,
});

describe('MetricsAggregator', () => {
  let aggregator: MetricsAggregator;

  beforeEach(() => {
    aggregator = new MetricsAggregator();
  });

  describe('processEntry', () => {
    it('creates session metrics on first entry', () => {
      const session = createMockSessionInfo();
      const entry = createMockEntry({
        model: 'claude-sonnet-4-20250514',
        usage: {
          inputTokens: 1000,
          outputTokens: 500,
          cacheReadTokens: 200,
          cacheCreationTokens: 0,
        },
      });

      aggregator.processEntry(entry, session);

      const metrics = aggregator.getSessionMetrics(session.sessionId);
      expect(metrics).toBeDefined();
      expect(metrics?.sessionId).toBe(session.sessionId);
    });

    it('accumulates token usage correctly', () => {
      const session = createMockSessionInfo();

      const entry1 = createMockEntry({
        model: 'claude-sonnet-4-20250514',
        usage: {
          inputTokens: 1000,
          outputTokens: 500,
          cacheReadTokens: 0,
          cacheCreationTokens: 0,
        },
      });

      const entry2 = createMockEntry({
        model: 'claude-sonnet-4-20250514',
        usage: {
          inputTokens: 2000,
          outputTokens: 1000,
          cacheReadTokens: 500,
          cacheCreationTokens: 0,
        },
      });

      aggregator.processEntry(entry1, session);
      aggregator.processEntry(entry2, session);

      const metrics = aggregator.getSessionMetrics(session.sessionId);
      expect(metrics?.tokensIn).toBe(3000);
      expect(metrics?.tokensOut).toBe(1500);
      expect(metrics?.cacheReadTokens).toBe(500);
    });

    it('tracks multiple models used in session', () => {
      const session = createMockSessionInfo();

      const opusEntry = createMockEntry({
        model: 'claude-opus-4-5-20251101',
        usage: { inputTokens: 100, outputTokens: 50, cacheReadTokens: 0, cacheCreationTokens: 0 },
      });

      const sonnetEntry = createMockEntry({
        model: 'claude-sonnet-4-20250514',
        usage: { inputTokens: 100, outputTokens: 50, cacheReadTokens: 0, cacheCreationTokens: 0 },
      });

      aggregator.processEntry(opusEntry, session);
      aggregator.processEntry(sonnetEntry, session);

      const metrics = aggregator.getSessionMetrics(session.sessionId);
      expect(metrics?.models.size).toBe(2);
      expect(metrics?.models.has('claude-opus-4-5-20251101')).toBe(true);
      expect(metrics?.models.has('claude-sonnet-4-20250514')).toBe(true);
    });

    it('counts tool calls correctly', () => {
      const session = createMockSessionInfo();

      const entry = createMockEntry({
        model: 'claude-sonnet-4-20250514',
        usage: { inputTokens: 100, outputTokens: 50, cacheReadTokens: 0, cacheCreationTokens: 0 },
        toolCalls: ['Read', 'Write', 'Read'],
      });

      aggregator.processEntry(entry, session);

      const metrics = aggregator.getSessionMetrics(session.sessionId);
      expect(metrics?.toolCalls).toBe(3);
      expect(metrics?.toolUsage.get('Read')).toBe(2);
      expect(metrics?.toolUsage.get('Write')).toBe(1);
    });

    it('calculates cost accurately', () => {
      const session = createMockSessionInfo();

      const entry = createMockEntry({
        model: 'claude-sonnet-4-20250514',
        usage: {
          inputTokens: 1_000_000, // $3
          outputTokens: 100_000,  // $1.5
          cacheReadTokens: 0,
          cacheCreationTokens: 0,
        },
      });

      aggregator.processEntry(entry, session);

      const metrics = aggregator.getSessionMetrics(session.sessionId);
      expect(metrics?.cost.total).toBeCloseTo(4.5, 2);
    });

    it('ignores user entries for token counting', () => {
      const session = createMockSessionInfo();

      const userEntry = createMockEntry({
        type: 'user',
      });

      aggregator.processEntry(userEntry, session);

      const metrics = aggregator.getSessionMetrics(session.sessionId);
      expect(metrics?.tokensIn).toBe(0);
      expect(metrics?.assistantEntries).toBe(0);
      expect(metrics?.entryCount).toBe(1);
    });
  });

  describe('registerAgent', () => {
    it('increments agent count for session', () => {
      const parentSession = createMockSessionInfo({ sessionId: 'parent-123' });
      const agent = createMockSessionInfo({
        sessionId: 'agent-456',
        isAgent: true,
        parentSessionId: 'parent-123',
      });

      // First process parent session
      aggregator.processEntry(createMockEntry({ sessionId: 'parent-123' }), parentSession);

      // Then register agent
      aggregator.registerAgent(agent, parentSession);

      const metrics = aggregator.getSessionMetrics('parent-123');
      expect(metrics?.agentCount).toBe(1);
    });

    it('creates agent metrics', () => {
      const parentSession = createMockSessionInfo({ sessionId: 'parent-123' });
      const agent = createMockSessionInfo({
        sessionId: 'agent-456',
        isAgent: true,
        parentSessionId: 'parent-123',
      });

      aggregator.processEntry(createMockEntry({ sessionId: 'parent-123' }), parentSession);
      aggregator.registerAgent(agent, parentSession);

      const agentMetrics = aggregator.getAgentMetrics('agent-456');
      expect(agentMetrics).toBeDefined();
      expect(agentMetrics?.parentId).toBe('parent-123');
    });
  });

  describe('getSessionAgents', () => {
    it('returns all agents for a session', () => {
      const parentSession = createMockSessionInfo({ sessionId: 'parent-123' });
      const agent1 = createMockSessionInfo({
        sessionId: 'agent-1',
        isAgent: true,
        parentSessionId: 'parent-123',
      });
      const agent2 = createMockSessionInfo({
        sessionId: 'agent-2',
        isAgent: true,
        parentSessionId: 'parent-123',
      });

      aggregator.processEntry(createMockEntry({ sessionId: 'parent-123' }), parentSession);
      aggregator.registerAgent(agent1, parentSession);
      aggregator.registerAgent(agent2, parentSession);

      const agents = aggregator.getSessionAgents('parent-123');
      expect(agents).toHaveLength(2);
    });

    it('returns empty array for session without agents', () => {
      const agents = aggregator.getSessionAgents('non-existent');
      expect(agents).toHaveLength(0);
    });
  });

  describe('getAgentTree', () => {
    it('builds tree structure for agents', () => {
      const parentSession = createMockSessionInfo({ sessionId: 'parent-123' });
      const agent1 = createMockSessionInfo({
        sessionId: 'agent-1',
        isAgent: true,
        parentSessionId: 'parent-123',
      });

      aggregator.processEntry(createMockEntry({ sessionId: 'parent-123' }), parentSession);
      aggregator.registerAgent(agent1, parentSession);

      const tree = aggregator.getAgentTree('parent-123');
      expect(tree).toHaveLength(1);
      expect(tree[0].id).toBe('agent-1');
    });
  });

  describe('getAllSessions', () => {
    it('returns all tracked sessions', () => {
      const session1 = createMockSessionInfo({ sessionId: 'session-1' });
      const session2 = createMockSessionInfo({ sessionId: 'session-2' });

      aggregator.processEntry(createMockEntry({ sessionId: 'session-1' }), session1);
      aggregator.processEntry(createMockEntry({ sessionId: 'session-2' }), session2);

      const sessions = aggregator.getAllSessions();
      expect(sessions).toHaveLength(2);
    });
  });

  describe('getTotals', () => {
    it('aggregates totals across all sessions', () => {
      const session1 = createMockSessionInfo({ sessionId: 'session-1' });
      const session2 = createMockSessionInfo({ sessionId: 'session-2' });

      aggregator.processEntry(
        createMockEntry({
          sessionId: 'session-1',
          model: 'claude-sonnet-4-20250514',
          usage: { inputTokens: 1000, outputTokens: 500, cacheReadTokens: 0, cacheCreationTokens: 0 },
        }),
        session1
      );

      aggregator.processEntry(
        createMockEntry({
          sessionId: 'session-2',
          model: 'claude-sonnet-4-20250514',
          usage: { inputTokens: 2000, outputTokens: 1000, cacheReadTokens: 0, cacheCreationTokens: 0 },
        }),
        session2
      );

      const totals = aggregator.getTotals();
      expect(totals.sessions).toBe(2);
      expect(totals.tokensIn).toBe(3000);
      expect(totals.tokensOut).toBe(1500);
    });
  });

  describe('clear', () => {
    it('removes all tracked data', () => {
      const session = createMockSessionInfo();
      aggregator.processEntry(createMockEntry(), session);

      aggregator.clear();

      expect(aggregator.getAllSessions()).toHaveLength(0);
    });
  });

  describe('export', () => {
    it('returns JSON-serializable data', () => {
      const session = createMockSessionInfo();
      aggregator.processEntry(
        createMockEntry({
          model: 'claude-sonnet-4-20250514',
          usage: { inputTokens: 100, outputTokens: 50, cacheReadTokens: 0, cacheCreationTokens: 0 },
          toolCalls: ['Read'],
        }),
        session
      );

      const exported = aggregator.export();

      // Should be JSON-serializable (Sets converted to arrays)
      expect(() => JSON.stringify(exported)).not.toThrow();
      expect(exported.sessions[0].models).toBeInstanceOf(Array);
      expect(exported.sessions[0].toolUsage).toBeInstanceOf(Array);
    });
  });

  // ============================================
  // Session Lifecycle Management Tests (FLAW-005)
  // ============================================

  describe('session status tracking', () => {
    it('initializes new sessions with active status', () => {
      const session = createMockSessionInfo();
      aggregator.processEntry(createMockEntry(), session);

      const metrics = aggregator.getSessionMetrics(session.sessionId);
      expect(metrics?.status).toBe('active');
      expect(metrics?.endedAt).toBeUndefined();
    });
  });

  describe('endSession', () => {
    it('marks session as ended with timestamp', () => {
      const session = createMockSessionInfo();
      aggregator.processEntry(createMockEntry(), session);

      const result = aggregator.endSession(session.sessionId);

      expect(result).toBe(true);
      const metrics = aggregator.getSessionMetrics(session.sessionId);
      expect(metrics?.status).toBe('ended');
      expect(metrics?.endedAt).toBeInstanceOf(Date);
    });

    it('returns false for non-existent session', () => {
      const result = aggregator.endSession('non-existent-session');
      expect(result).toBe(false);
    });

    it('returns true when ending already-ended session (idempotent)', () => {
      const session = createMockSessionInfo();
      aggregator.processEntry(createMockEntry(), session);

      aggregator.endSession(session.sessionId);
      const result = aggregator.endSession(session.sessionId);

      expect(result).toBe(true);
    });

    it('emits session:ended event', () => {
      const session = createMockSessionInfo();
      aggregator.processEntry(createMockEntry(), session);

      let emittedSession: unknown = null;
      aggregator.on('session:ended', (s) => {
        emittedSession = s;
      });

      aggregator.endSession(session.sessionId);

      expect(emittedSession).toBeDefined();
      expect((emittedSession as { sessionId: string }).sessionId).toBe(session.sessionId);
    });
  });

  describe('detectInactiveSessions', () => {
    it('detects sessions inactive beyond threshold', () => {
      const session = createMockSessionInfo();
      // Process an entry to create the session
      aggregator.processEntry(createMockEntry(), session);

      // Manually backdate lastActivity to simulate inactivity
      // (lastActivity only moves forward from entry timestamps, so we need to
      // simulate time passing by adjusting the timestamp directly)
      const metrics = aggregator.getSessionMetrics(session.sessionId);
      if (metrics) {
        metrics.lastActivity = new Date(Date.now() - 600000); // 10 minutes ago
      }

      const inactive = aggregator.detectInactiveSessions(300000); // 5 min threshold

      expect(inactive).toContain(session.sessionId);
    });

    it('does not include recently active sessions', () => {
      const session = createMockSessionInfo();
      const recentEntry = createMockEntry({
        timestamp: new Date(), // now
      });
      aggregator.processEntry(recentEntry, session);

      const inactive = aggregator.detectInactiveSessions(300000);

      expect(inactive).not.toContain(session.sessionId);
    });

    it('does not include ended sessions', () => {
      const session = createMockSessionInfo();
      aggregator.processEntry(createMockEntry(), session);

      // Backdate lastActivity
      const metrics = aggregator.getSessionMetrics(session.sessionId);
      if (metrics) {
        metrics.lastActivity = new Date(Date.now() - 600000);
      }

      aggregator.endSession(session.sessionId);

      const inactive = aggregator.detectInactiveSessions(300000);

      expect(inactive).not.toContain(session.sessionId);
    });

    it('emits session:inactive event when sessions detected', () => {
      const session = createMockSessionInfo();
      aggregator.processEntry(createMockEntry(), session);

      // Backdate lastActivity
      const metrics = aggregator.getSessionMetrics(session.sessionId);
      if (metrics) {
        metrics.lastActivity = new Date(Date.now() - 600000);
      }

      let emittedIds: string[] = [];
      aggregator.on('session:inactive', (ids) => {
        emittedIds = ids;
      });

      aggregator.detectInactiveSessions(300000);

      expect(emittedIds).toContain(session.sessionId);
    });
  });

  describe('getActiveSessions', () => {
    it('returns only active sessions', () => {
      const session1 = createMockSessionInfo({ sessionId: 'active-1' });
      const session2 = createMockSessionInfo({ sessionId: 'ended-1' });

      aggregator.processEntry(createMockEntry({ sessionId: 'active-1' }), session1);
      aggregator.processEntry(createMockEntry({ sessionId: 'ended-1' }), session2);
      aggregator.endSession('ended-1');

      const active = aggregator.getActiveSessions();

      expect(active).toHaveLength(1);
      expect(active[0].sessionId).toBe('active-1');
    });
  });

  describe('getEndedSessions', () => {
    it('returns only ended sessions', () => {
      const session1 = createMockSessionInfo({ sessionId: 'active-1' });
      const session2 = createMockSessionInfo({ sessionId: 'ended-1' });

      aggregator.processEntry(createMockEntry({ sessionId: 'active-1' }), session1);
      aggregator.processEntry(createMockEntry({ sessionId: 'ended-1' }), session2);
      aggregator.endSession('ended-1');

      const ended = aggregator.getEndedSessions();

      expect(ended).toHaveLength(1);
      expect(ended[0].sessionId).toBe('ended-1');
    });
  });

  describe('clearEndedSessions', () => {
    it('removes ended sessions from memory', () => {
      const session1 = createMockSessionInfo({ sessionId: 'active-1' });
      const session2 = createMockSessionInfo({ sessionId: 'ended-1' });

      aggregator.processEntry(createMockEntry({ sessionId: 'active-1' }), session1);
      aggregator.processEntry(createMockEntry({ sessionId: 'ended-1' }), session2);
      aggregator.endSession('ended-1');

      const cleared = aggregator.clearEndedSessions();

      expect(cleared).toBe(1);
      expect(aggregator.getAllSessions()).toHaveLength(1);
      expect(aggregator.getSessionMetrics('ended-1')).toBeUndefined();
      expect(aggregator.getSessionMetrics('active-1')).toBeDefined();
    });

    it('removes associated agents when clearing ended sessions', () => {
      const parentSession = createMockSessionInfo({ sessionId: 'parent-ended' });
      const agent = createMockSessionInfo({
        sessionId: 'agent-child',
        isAgent: true,
        parentSessionId: 'parent-ended',
      });

      aggregator.processEntry(createMockEntry({ sessionId: 'parent-ended' }), parentSession);
      aggregator.registerAgent(agent, parentSession);
      aggregator.endSession('parent-ended');

      aggregator.clearEndedSessions();

      expect(aggregator.getSessionMetrics('parent-ended')).toBeUndefined();
      expect(aggregator.getAgentMetrics('agent-child')).toBeUndefined();
    });

    it('returns 0 when no ended sessions exist', () => {
      const session = createMockSessionInfo();
      aggregator.processEntry(createMockEntry(), session);

      const cleared = aggregator.clearEndedSessions();

      expect(cleared).toBe(0);
    });
  });
});

describe('connectWatcherToAggregator', () => {
  it('wires entry events to processEntry', () => {
    // This is tested via integration - just verify the function exists
    expect(typeof connectWatcherToAggregator).toBe('function');
  });
});
