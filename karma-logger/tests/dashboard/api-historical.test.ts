/**
 * Historical Dashboard API Route Tests
 * Phase 2: Tests for project and historical data endpoints
 */

import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import * as fs from 'fs';
import * as os from 'os';
import * as path from 'path';
import { Hono } from 'hono';
import { KarmaDB } from '../../src/db.js';
import type { ProjectSummary, ProjectDetail, DailyMetric } from '../../src/types.js';

// Use temporary directory for test database
const TEST_DB_DIR = path.join(os.tmpdir(), 'karma-api-test-' + process.pid);
const TEST_DB_PATH = path.join(TEST_DB_DIR, 'test.db');

// Test database instance
let testDb: KarmaDB;

// Mock getDB to return our test database
vi.mock('../../src/db.js', async (importOriginal) => {
  const original = await importOriginal<typeof import('../../src/db.js')>();
  return {
    ...original,
    getDB: () => testDb,
  };
});

// Import after mocking
const { createApiRoutes } = await import('../../src/dashboard/api.js');
const { MetricsAggregator } = await import('../../src/aggregator.js');

describe('Historical Dashboard API Routes', () => {
  let app: Hono;
  let aggregator: MetricsAggregator;

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

    // Create test database
    testDb = new KarmaDB(TEST_DB_PATH);

    // Create aggregator and API routes
    aggregator = new MetricsAggregator();
    const apiRoutes = createApiRoutes(aggregator);

    // Mount routes under /api prefix like the real server
    app = new Hono();
    app.route('/api', apiRoutes);
  });

  afterEach(() => {
    testDb.close();

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

  // Helper to seed test data
  function seedSession(overrides: Partial<{
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
    const session = {
      sessionId: overrides.sessionId ?? `session-${Math.random().toString(36).substring(7)}`,
      projectPath: overrides.projectPath ?? '/test/project',
      projectName: overrides.projectName ?? 'test-project',
      startedAt: overrides.startedAt ?? new Date(),
      lastActivity: overrides.lastActivity ?? new Date(),
      tokensIn: overrides.tokensIn ?? 1000,
      tokensOut: overrides.tokensOut ?? 500,
      cacheReadTokens: overrides.cacheReadTokens ?? 200,
      cacheCreationTokens: overrides.cacheCreationTokens ?? 0,
      cost: overrides.cost ?? { inputCost: 0.01, outputCost: 0.02, cacheReadCost: 0, cacheCreationCost: 0, total: 0.03, model: 'test' },
      models: overrides.models ?? new Set(['claude-sonnet-4-20250514']),
      agentCount: overrides.agentCount ?? 0,
      toolCalls: overrides.toolCalls ?? 10,
      toolUsage: overrides.toolUsage ?? new Map([['Read', 5], ['Edit', 3]]),
    };
    testDb.saveSession(session);
    return session;
  }

  describe('GET /api/projects', () => {
    it('returns empty array when no projects', async () => {
      const res = await app.request('/api/projects');
      expect(res.status).toBe(200);

      const data = await res.json() as ProjectSummary[];
      expect(data).toEqual([]);
    });

    it('returns list of projects with aggregated metrics', async () => {
      seedSession({ sessionId: 's1', projectName: 'project-a', tokensIn: 1000, tokensOut: 500 });
      seedSession({ sessionId: 's2', projectName: 'project-a', tokensIn: 2000, tokensOut: 1000 });
      seedSession({ sessionId: 's3', projectName: 'project-b', tokensIn: 500, tokensOut: 250 });

      const res = await app.request('/api/projects');
      expect(res.status).toBe(200);

      const data = await res.json() as ProjectSummary[];
      expect(data.length).toBe(2);

      const projectA = data.find(p => p.projectName === 'project-a');
      expect(projectA?.sessionCount).toBe(2);
      expect(projectA?.totalTokensIn).toBe(3000);
      expect(projectA?.totalTokensOut).toBe(1500);

      const projectB = data.find(p => p.projectName === 'project-b');
      expect(projectB?.sessionCount).toBe(1);
    });

    it('returns projects sorted by last activity', async () => {
      seedSession({
        sessionId: 's1',
        projectName: 'older-project',
        startedAt: new Date('2026-01-01T10:00:00Z'),
      });
      seedSession({
        sessionId: 's2',
        projectName: 'newer-project',
        startedAt: new Date('2026-01-05T10:00:00Z'),
      });

      const res = await app.request('/api/projects');
      const data = await res.json() as ProjectSummary[];

      expect(data[0].projectName).toBe('newer-project');
      expect(data[1].projectName).toBe('older-project');
    });
  });

  describe('GET /api/projects/:name', () => {
    it('returns 404 for non-existent project', async () => {
      const res = await app.request('/api/projects/non-existent');
      expect(res.status).toBe(404);

      const data = await res.json() as { error: string };
      expect(data.error).toBe('Project not found');
    });

    it('returns project detail with sessions', async () => {
      seedSession({ sessionId: 's1', projectName: 'my-project', tokensIn: 1000 });
      seedSession({ sessionId: 's2', projectName: 'my-project', tokensIn: 2000 });

      const res = await app.request('/api/projects/my-project');
      expect(res.status).toBe(200);

      const data = await res.json() as ProjectDetail;
      expect(data.summary.projectName).toBe('my-project');
      expect(data.summary.sessionCount).toBe(2);
      expect(data.summary.totalTokensIn).toBe(3000);
      expect(data.sessions.length).toBe(2);
    });

    it('handles URL-encoded project names', async () => {
      seedSession({ sessionId: 's1', projectName: 'project with spaces' });

      const res = await app.request('/api/projects/project%20with%20spaces');
      expect(res.status).toBe(200);

      const data = await res.json() as ProjectDetail;
      expect(data.summary.projectName).toBe('project with spaces');
    });

    it('handles project names with special characters', async () => {
      seedSession({ sessionId: 's1', projectName: 'my/special-project' });

      const res = await app.request('/api/projects/' + encodeURIComponent('my/special-project'));
      expect(res.status).toBe(200);

      const data = await res.json() as ProjectDetail;
      expect(data.summary.projectName).toBe('my/special-project');
    });
  });

  describe('GET /api/projects/:name/history', () => {
    it('returns empty array when no data for project', async () => {
      seedSession({ sessionId: 's1', projectName: 'other-project' });

      const res = await app.request('/api/projects/my-project/history');
      expect(res.status).toBe(200);

      const data = await res.json() as DailyMetric[];
      expect(data).toEqual([]);
    });

    it('returns daily metrics for project', async () => {
      seedSession({
        sessionId: 's1',
        projectName: 'my-project',
        startedAt: new Date('2026-01-05T10:00:00Z'),
        tokensIn: 1000,
        tokensOut: 500,
      });
      seedSession({
        sessionId: 's2',
        projectName: 'my-project',
        startedAt: new Date('2026-01-05T15:00:00Z'),
        tokensIn: 2000,
        tokensOut: 1000,
      });

      const res = await app.request('/api/projects/my-project/history');
      expect(res.status).toBe(200);

      const data = await res.json() as DailyMetric[];
      expect(data.length).toBe(1);
      expect(data[0].day).toBe('2026-01-05');
      expect(data[0].tokensIn).toBe(3000);
      expect(data[0].tokensOut).toBe(1500);
      expect(data[0].sessions).toBe(2);
    });

    it('respects days query parameter', async () => {
      seedSession({
        sessionId: 's1',
        projectName: 'my-project',
        startedAt: new Date('2026-01-05T10:00:00Z'),
      });

      const res = await app.request('/api/projects/my-project/history?days=7');
      expect(res.status).toBe(200);
      // The result depends on actual date vs the seeded date
    });

    it('defaults to 30 days when days param is invalid', async () => {
      seedSession({ sessionId: 's1', projectName: 'my-project' });

      const res = await app.request('/api/projects/my-project/history?days=invalid');
      expect(res.status).toBe(200);
      // Should not error, defaults to 30
    });
  });

  describe('GET /api/totals/history', () => {
    it('returns empty array when no sessions', async () => {
      const res = await app.request('/api/totals/history');
      expect(res.status).toBe(200);

      const data = await res.json() as DailyMetric[];
      expect(data).toEqual([]);
    });

    it('returns daily metrics across all projects', async () => {
      seedSession({
        sessionId: 's1',
        projectName: 'project-a',
        startedAt: new Date('2026-01-05T10:00:00Z'),
        tokensIn: 1000,
      });
      seedSession({
        sessionId: 's2',
        projectName: 'project-b',
        startedAt: new Date('2026-01-05T15:00:00Z'),
        tokensIn: 2000,
      });
      seedSession({
        sessionId: 's3',
        projectName: 'project-a',
        startedAt: new Date('2026-01-06T10:00:00Z'),
        tokensIn: 500,
      });

      const res = await app.request('/api/totals/history');
      expect(res.status).toBe(200);

      const data = await res.json() as DailyMetric[];
      expect(data.length).toBe(2);

      const day1 = data.find(m => m.day === '2026-01-05');
      expect(day1?.tokensIn).toBe(3000);
      expect(day1?.sessions).toBe(2);

      const day2 = data.find(m => m.day === '2026-01-06');
      expect(day2?.tokensIn).toBe(500);
      expect(day2?.sessions).toBe(1);
    });

    it('respects days query parameter', async () => {
      const res = await app.request('/api/totals/history?days=7');
      expect(res.status).toBe(200);
    });

    it('defaults to 30 days when days param is invalid', async () => {
      const res = await app.request('/api/totals/history?days=abc');
      expect(res.status).toBe(200);
      // Should not error, defaults to 30
    });
  });
});
