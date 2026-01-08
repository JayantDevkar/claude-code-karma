/**
 * Dashboard Server unit tests
 * Phase 5: Web server with SSE and API routes
 */

import { describe, it, expect, beforeEach } from 'vitest';
import { createApp } from '../../src/dashboard/server.js';
import { MetricsAggregator } from '../../src/aggregator.js';
import type { LogEntry } from '../../src/types.js';
import type { SessionInfo } from '../../src/discovery.js';

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

describe('Dashboard Server', () => {
  let aggregator: MetricsAggregator;
  let app: ReturnType<typeof createApp>;

  beforeEach(() => {
    aggregator = new MetricsAggregator();
    app = createApp(aggregator);
  });

  describe('GET /api/health', () => {
    it('returns ok status', async () => {
      const res = await app.request('/api/health');
      expect(res.status).toBe(200);

      const data = await res.json();
      expect(data.status).toBe('ok');
      expect(data).toHaveProperty('clients');
      expect(data).toHaveProperty('sessions');
      expect(data).toHaveProperty('timestamp');
    });
  });

  describe('GET /api/session', () => {
    it('returns empty session when no data', async () => {
      const res = await app.request('/api/session');
      expect(res.status).toBe(200);

      const data = await res.json();
      expect(data.sessionId).toBeNull();
      expect(data.metrics.tokensIn).toBe(0);
      expect(data.metrics.tokensOut).toBe(0);
    });

    it('returns metrics when session exists', async () => {
      // Add a session
      const session = createMockSessionInfo();
      const entry = createMockEntry({
        model: 'claude-sonnet-4-20250514',
        usage: {
          inputTokens: 1000,
          outputTokens: 500,
          cacheReadTokens: 100,
          cacheCreationTokens: 50,
        },
      });
      aggregator.processEntry(entry, session);

      const res = await app.request('/api/session');
      expect(res.status).toBe(200);

      const data = await res.json();
      expect(data.sessionId).toBe('test-session-123');
      expect(data.metrics.tokensIn).toBe(1000);
      expect(data.metrics.tokensOut).toBe(500);
      expect(data.metrics.cacheRead).toBe(100);
    });
  });

  describe('GET /api/session/:id', () => {
    it('returns 404 for non-existent session', async () => {
      const res = await app.request('/api/session/non-existent');
      expect(res.status).toBe(404);

      const data = await res.json();
      expect(data.error).toBe('Session not found');
    });

    it('returns metrics for specific session', async () => {
      const session = createMockSessionInfo({ sessionId: 'specific-session' });
      const entry = createMockEntry({
        sessionId: 'specific-session',
        model: 'claude-sonnet-4-20250514',
        usage: {
          inputTokens: 2000,
          outputTokens: 1000,
          cacheReadTokens: 0,
          cacheCreationTokens: 0,
        },
      });
      aggregator.processEntry(entry, session);

      const res = await app.request('/api/session/specific-session');
      expect(res.status).toBe(200);

      const data = await res.json();
      expect(data.sessionId).toBe('specific-session');
      expect(data.metrics.tokensIn).toBe(2000);
    });
  });

  describe('GET /api/sessions', () => {
    it('returns empty list when no sessions', async () => {
      const res = await app.request('/api/sessions');
      expect(res.status).toBe(200);

      const data = await res.json();
      expect(data.sessions).toHaveLength(0);
      expect(data.total).toBe(0);
    });

    it('returns list of sessions', async () => {
      const session1 = createMockSessionInfo({ sessionId: 'session-1', projectName: 'project-1' });
      const session2 = createMockSessionInfo({ sessionId: 'session-2', projectName: 'project-2' });

      aggregator.processEntry(
        createMockEntry({
          sessionId: 'session-1',
          model: 'claude-sonnet-4-20250514',
          usage: { inputTokens: 100, outputTokens: 50, cacheReadTokens: 0, cacheCreationTokens: 0 },
        }),
        session1
      );

      aggregator.processEntry(
        createMockEntry({
          sessionId: 'session-2',
          model: 'claude-sonnet-4-20250514',
          usage: { inputTokens: 200, outputTokens: 100, cacheReadTokens: 0, cacheCreationTokens: 0 },
        }),
        session2
      );

      const res = await app.request('/api/sessions');
      expect(res.status).toBe(200);

      const data = await res.json();
      expect(data.sessions).toHaveLength(2);
      expect(data.total).toBe(2);
    });

    it('respects limit parameter', async () => {
      // Create 3 sessions
      for (let i = 1; i <= 3; i++) {
        const session = createMockSessionInfo({ sessionId: `session-${i}` });
        aggregator.processEntry(
          createMockEntry({
            sessionId: `session-${i}`,
            model: 'claude-sonnet-4-20250514',
            usage: { inputTokens: 100, outputTokens: 50, cacheReadTokens: 0, cacheCreationTokens: 0 },
          }),
          session
        );
      }

      const res = await app.request('/api/sessions?limit=2');
      const data = await res.json();
      expect(data.sessions).toHaveLength(2);
      expect(data.total).toBe(3);
    });
  });

  describe('GET /api/totals', () => {
    it('returns aggregated totals', async () => {
      const session = createMockSessionInfo();
      aggregator.processEntry(
        createMockEntry({
          model: 'claude-sonnet-4-20250514',
          usage: { inputTokens: 1000, outputTokens: 500, cacheReadTokens: 100, cacheCreationTokens: 50 },
          toolCalls: ['Read', 'Write'],
        }),
        session
      );

      const res = await app.request('/api/totals');
      expect(res.status).toBe(200);

      const data = await res.json();
      expect(data.sessions).toBe(1);
      expect(data.tokensIn).toBe(1000);
      expect(data.tokensOut).toBe(500);
      expect(data.tokensTotal).toBe(1500);
      expect(data.cacheRead).toBe(100);
      expect(data.cacheCreation).toBe(50);
      expect(data.toolCalls).toBe(2);
    });
  });

  describe('GET /', () => {
    it('returns HTML page', async () => {
      const res = await app.request('/');
      expect(res.status).toBe(200);

      const html = await res.text();
      expect(html).toContain('<!DOCTYPE html>');
      expect(html).toContain('Karma Dashboard');
    });

    it('serves dashboard HTML', async () => {
      const res = await app.request('/');
      const html = await res.text();
      // The dashboard now serves static HTML from public/index.html
      expect(html).toContain('Karma Dashboard');
      expect(html).toContain('Tokens In');
      expect(html).toContain('Recent Sessions');
    });
  });

  describe('GET /events (SSE)', () => {
    it('returns event stream headers', async () => {
      const res = await app.request('/events');
      expect(res.status).toBe(200);
      expect(res.headers.get('Content-Type')).toBe('text/event-stream');
      expect(res.headers.get('Cache-Control')).toBe('no-cache');
    });
  });

  describe('CORS', () => {
    it('allows cross-origin requests', async () => {
      const res = await app.request('/api/health', {
        headers: { Origin: 'http://localhost:3000' },
      });

      expect(res.headers.get('Access-Control-Allow-Origin')).toBe('*');
    });
  });
});
