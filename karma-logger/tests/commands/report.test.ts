/**
 * Report command unit tests
 * Phase 6: Historical reporting tests
 */

import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import * as fs from 'fs';
import * as os from 'os';
import * as path from 'path';
import { KarmaDB } from '../../src/db.js';

// Use temporary directory for tests
const TEST_DB_DIR = path.join(os.tmpdir(), 'karma-report-test-' + process.pid);
const TEST_DB_PATH = path.join(TEST_DB_DIR, 'test.db');

// Mock the getDB function to use test database
vi.mock('../../src/db.js', async () => {
  const actual = await vi.importActual('../../src/db.js');
  let testDb: KarmaDB | null = null;

  return {
    ...actual,
    getDB: () => {
      if (!testDb) {
        testDb = new (actual as any).KarmaDB(TEST_DB_PATH);
      }
      return testDb;
    },
    closeDB: () => {
      if (testDb) {
        testDb.close();
        testDb = null;
      }
    },
    // Re-export KarmaDB for direct use in tests
    KarmaDB: (actual as any).KarmaDB,
  };
});

describe('report command', () => {
  let db: KarmaDB;
  let consoleOutput: string[] = [];
  const originalLog = console.log;

  beforeEach(() => {
    // Clean up any existing test database
    if (fs.existsSync(TEST_DB_PATH)) {
      fs.unlinkSync(TEST_DB_PATH);
    }
    if (fs.existsSync(TEST_DB_PATH + '-wal')) {
      fs.unlinkSync(TEST_DB_PATH + '-wal');
    }
    if (fs.existsSync(TEST_DB_PATH + '-shm')) {
      fs.unlinkSync(TEST_DB_PATH + '-shm');
    }

    // Create test database directly
    db = new KarmaDB(TEST_DB_PATH);

    // Capture console output
    consoleOutput = [];
    console.log = (...args) => {
      consoleOutput.push(args.map(a => String(a)).join(' '));
    };
  });

  afterEach(() => {
    console.log = originalLog;
    db.close();

    // Clean up test files
    try {
      if (fs.existsSync(TEST_DB_PATH)) fs.unlinkSync(TEST_DB_PATH);
      if (fs.existsSync(TEST_DB_PATH + '-wal')) fs.unlinkSync(TEST_DB_PATH + '-wal');
      if (fs.existsSync(TEST_DB_PATH + '-shm')) fs.unlinkSync(TEST_DB_PATH + '-shm');
      if (fs.existsSync(TEST_DB_DIR)) fs.rmdirSync(TEST_DB_DIR);
    } catch {
      // Ignore cleanup errors
    }
  });

  describe('session listing', () => {
    it('handles empty database gracefully', () => {
      const sessions = db.listSessions();
      expect(sessions).toEqual([]);
    });

    it('lists sessions in descending order by date', () => {
      db.saveSession(createMockSession({
        sessionId: 'older',
        startedAt: new Date('2026-01-01T10:00:00Z'),
      }));
      db.saveSession(createMockSession({
        sessionId: 'newer',
        startedAt: new Date('2026-01-02T10:00:00Z'),
      }));

      const sessions = db.listSessions();
      expect(sessions[0].id).toBe('newer');
      expect(sessions[1].id).toBe('older');
    });

    it('filters sessions by project', () => {
      db.saveSession(createMockSession({
        sessionId: 's1',
        projectName: 'project-alpha',
      }));
      db.saveSession(createMockSession({
        sessionId: 's2',
        projectName: 'project-beta',
      }));

      const sessions = db.listSessions({ project: 'alpha' });
      expect(sessions.length).toBe(1);
      expect(sessions[0].projectName).toBe('project-alpha');
    });
  });

  describe('session detail', () => {
    it('retrieves full session with agents', () => {
      const session = createMockSession();
      db.saveSession(session);

      db.saveAgent(createMockAgent(session.sessionId, {
        agentId: 'agent-1',
        agentType: 'explore',
      }));
      db.saveAgent(createMockAgent(session.sessionId, {
        agentId: 'agent-2',
        agentType: 'code-review',
      }));

      const detail = db.getSessionDetail(session.sessionId);
      expect(detail).not.toBeNull();
      expect(detail?.agents.length).toBe(2);
    });

    it('returns null for non-existent session', () => {
      const detail = db.getSessionDetail('non-existent-id');
      expect(detail).toBeNull();
    });
  });

  describe('date filtering', () => {
    it('filters sessions by since date', () => {
      db.saveSession(createMockSession({
        sessionId: 'old',
        startedAt: new Date('2025-12-01T10:00:00Z'),
      }));
      db.saveSession(createMockSession({
        sessionId: 'recent',
        startedAt: new Date('2026-01-05T10:00:00Z'),
      }));

      const sessions = db.listSessions({
        since: new Date('2026-01-01T00:00:00Z'),
      });

      expect(sessions.length).toBe(1);
      expect(sessions[0].id).toBe('recent');
    });

    it('filters sessions by until date', () => {
      db.saveSession(createMockSession({
        sessionId: 'old',
        startedAt: new Date('2025-12-15T10:00:00Z'),
      }));
      db.saveSession(createMockSession({
        sessionId: 'recent',
        startedAt: new Date('2026-01-05T10:00:00Z'),
      }));

      const sessions = db.listSessions({
        until: new Date('2026-01-01T00:00:00Z'),
      });

      expect(sessions.length).toBe(1);
      expect(sessions[0].id).toBe('old');
    });
  });

  describe('aggregation', () => {
    it('calculates totals across sessions', () => {
      db.saveSession(createMockSession({
        sessionId: 's1',
        tokensIn: 1000,
        tokensOut: 500,
        cost: { inputCost: 0.01, outputCost: 0.02, cacheReadCost: 0, cacheCreationCost: 0, total: 0.03, model: 'test' },
        agentCount: 2,
        toolCalls: 10,
      }));
      db.saveSession(createMockSession({
        sessionId: 's2',
        tokensIn: 2000,
        tokensOut: 1000,
        cost: { inputCost: 0.02, outputCost: 0.04, cacheReadCost: 0, cacheCreationCost: 0, total: 0.06, model: 'test' },
        agentCount: 3,
        toolCalls: 20,
      }));

      const totals = db.getTotals();
      expect(totals.sessions).toBe(2);
      expect(totals.tokensIn).toBe(3000);
      expect(totals.tokensOut).toBe(1500);
      expect(totals.costTotal).toBeCloseTo(0.09, 4);
      expect(totals.agentCount).toBe(5);
      expect(totals.toolCalls).toBe(30);
    });

    it('aggregates tool usage', () => {
      db.saveSession(createMockSession({
        sessionId: 's1',
        toolUsage: new Map([['Read', 10], ['Edit', 5]]),
      }));
      db.saveSession(createMockSession({
        sessionId: 's2',
        toolUsage: new Map([['Read', 20], ['Bash', 15]]),
      }));

      const topTools = db.getTopTools();
      expect(topTools[0]).toEqual({ tool: 'Read', count: 30 });
    });
  });

  describe('JSON output', () => {
    it('serializes session detail correctly', () => {
      const session = createMockSession({
        sessionId: 'test-session',
        projectName: 'my-project',
        tokensIn: 5000,
      });
      db.saveSession(session);

      const detail = db.getSessionDetail('test-session');
      const json = JSON.stringify(detail);

      expect(json).toContain('test-session');
      expect(json).toContain('my-project');
    });

    it('serializes session list correctly', () => {
      db.saveSession(createMockSession({ sessionId: 's1' }));
      db.saveSession(createMockSession({ sessionId: 's2' }));

      const sessions = db.listSessions();
      const json = JSON.stringify(sessions);

      expect(json).toContain('s1');
      expect(json).toContain('s2');
    });
  });

  describe('CSV output', () => {
    it('includes expected columns', () => {
      db.saveSession(createMockSession({
        sessionId: 'csv-test',
        projectName: 'csv-project',
        tokensIn: 1000,
        tokensOut: 500,
      }));

      const sessions = db.listSessions();
      const session = sessions[0];

      // Verify required fields exist
      expect(session.id).toBe('csv-test');
      expect(session.projectName).toBe('csv-project');
      expect(session.tokensIn).toBe(1000);
      expect(session.tokensOut).toBe(500);
      expect(session.startedAt).toBeInstanceOf(Date);
      expect(typeof session.duration).toBe('number');
      expect(typeof session.costTotal).toBe('number');
      expect(typeof session.agentCount).toBe('number');
    });
  });
});

// Helper functions
function createMockSession(overrides: Partial<{
  sessionId: string;
  projectPath: string;
  projectName: string;
  startedAt: Date;
  lastActivity: Date;
  tokensIn: number;
  tokensOut: number;
  cacheReadTokens: number;
  cacheCreationTokens: number;
  cost: { inputCost: number; outputCost: number; cacheReadCost: number; cacheCreationCost: number; total: number; model: string };
  models: Set<string>;
  agentCount: number;
  toolCalls: number;
  toolUsage: Map<string, number>;
}> = {}) {
  return {
    sessionId: overrides.sessionId ?? `session-${Math.random().toString(36).substring(7)}`,
    projectPath: overrides.projectPath ?? '/test/project',
    projectName: overrides.projectName ?? 'test-project',
    startedAt: overrides.startedAt ?? new Date(),
    lastActivity: overrides.lastActivity ?? new Date(),
    tokensIn: overrides.tokensIn ?? 1000,
    tokensOut: overrides.tokensOut ?? 500,
    cacheReadTokens: overrides.cacheReadTokens ?? 200,
    cacheCreationTokens: overrides.cacheCreationTokens ?? 0,
    cost: overrides.cost ?? { inputCost: 0, outputCost: 0, cacheReadCost: 0, cacheCreationCost: 0, total: 0, model: 'test' },
    models: overrides.models ?? new Set(['claude-sonnet-4-20250514']),
    agentCount: overrides.agentCount ?? 0,
    toolCalls: overrides.toolCalls ?? 10,
    toolUsage: overrides.toolUsage ?? new Map([['Read', 5], ['Edit', 3]]),
  };
}

function createMockAgent(sessionId: string, overrides: Partial<{
  agentId: string;
  parentId: string;
  agentType: string;
  model: string;
  startedAt: Date;
  lastActivity: Date;
  tokensIn: number;
  tokensOut: number;
  cacheReadTokens: number;
  cacheCreationTokens: number;
  cost: { inputCost: number; outputCost: number; cacheReadCost: number; cacheCreationCost: number; total: number; model: string };
  toolsUsed: Set<string>;
  toolCalls: number;
}> = {}) {
  return {
    agentId: overrides.agentId ?? `agent-${Math.random().toString(36).substring(7)}`,
    sessionId,
    parentId: overrides.parentId,
    agentType: overrides.agentType ?? 'explore',
    model: overrides.model ?? 'claude-sonnet-4-20250514',
    startedAt: overrides.startedAt ?? new Date(),
    lastActivity: overrides.lastActivity ?? new Date(),
    tokensIn: overrides.tokensIn ?? 500,
    tokensOut: overrides.tokensOut ?? 200,
    cacheReadTokens: overrides.cacheReadTokens ?? 100,
    cacheCreationTokens: overrides.cacheCreationTokens ?? 0,
    cost: overrides.cost ?? { inputCost: 0, outputCost: 0, cacheReadCost: 0, cacheCreationCost: 0, total: 0.01, model: 'test' },
    toolsUsed: overrides.toolsUsed ?? new Set(['Read', 'Grep']),
    toolCalls: overrides.toolCalls ?? 5,
  };
}
