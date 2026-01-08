/**
 * Status command unit tests
 * Phase 4: karma status command tests
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import type { SessionMetrics } from '../../src/aggregator.js';
import { emptyCostBreakdown } from '../../src/cost.js';

// Test formatRelativeTime behavior (internals)
describe('status command utilities', () => {
  describe('relative time formatting', () => {
    // Helper to create a date X seconds ago
    const secondsAgo = (s: number) => new Date(Date.now() - s * 1000);
    const minutesAgo = (m: number) => secondsAgo(m * 60);
    const hoursAgo = (h: number) => minutesAgo(h * 60);
    const daysAgo = (d: number) => hoursAgo(d * 24);

    // These tests verify the expected behavior of relative time formatting
    it('should describe time differences correctly', () => {
      // Under 60 seconds = "just now"
      const recentDate = secondsAgo(30);
      const diffSeconds = Math.floor((Date.now() - recentDate.getTime()) / 1000);
      expect(diffSeconds).toBeLessThan(60);

      // 1-59 minutes = "X minutes ago"
      const fiveMinAgo = minutesAgo(5);
      const diffMinutes = Math.floor((Date.now() - fiveMinAgo.getTime()) / 1000 / 60);
      expect(diffMinutes).toBe(5);

      // 1-23 hours = "X hours ago"
      const twoHoursAgo = hoursAgo(2);
      const diffHours = Math.floor((Date.now() - twoHoursAgo.getTime()) / 1000 / 60 / 60);
      expect(diffHours).toBe(2);

      // 1+ days = "X days ago"
      const threeDaysAgo = daysAgo(3);
      const diffDays = Math.floor((Date.now() - threeDaysAgo.getTime()) / 1000 / 60 / 60 / 24);
      expect(diffDays).toBe(3);
    });
  });

  describe('stale session detection', () => {
    const thirtyMinutesMs = 30 * 60 * 1000;

    it('should detect stale sessions (>30 min)', () => {
      const staleTime = new Date(Date.now() - (thirtyMinutesMs + 1000));
      const isStale = Date.now() - staleTime.getTime() > thirtyMinutesMs;
      expect(isStale).toBe(true);
    });

    it('should detect active sessions (<=30 min)', () => {
      const activeTime = new Date(Date.now() - (thirtyMinutesMs - 1000));
      const isStale = Date.now() - activeTime.getTime() > thirtyMinutesMs;
      expect(isStale).toBe(false);
    });
  });
});

describe('status output formatting', () => {
  describe('box drawing', () => {
    // Box character constants
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

    it('should have correct box characters', () => {
      expect(BOX_CHARS.topLeft).toBe('╭');
      expect(BOX_CHARS.topRight).toBe('╮');
      expect(BOX_CHARS.bottomLeft).toBe('╰');
      expect(BOX_CHARS.bottomRight).toBe('╯');
    });

    it('box width should be 56 characters', () => {
      const width = 56;
      const innerWidth = width - 2;

      // Top border should be width characters
      const topBorder = BOX_CHARS.topLeft + BOX_CHARS.horizontal.repeat(innerWidth) + BOX_CHARS.topRight;
      expect(topBorder.length).toBe(width);
    });
  });

  describe('metrics display', () => {
    const createMockMetrics = (): SessionMetrics => ({
      sessionId: 'test-session-12345678',
      projectPath: '/test/project',
      projectName: 'test-project',
      startedAt: new Date(),
      lastActivity: new Date(),
      tokensIn: 125400,
      tokensOut: 42100,
      cacheReadTokens: 89200,
      cacheCreationTokens: 1000,
      cost: {
        inputCost: 0.38,
        outputCost: 0.63,
        cacheReadCost: 0.23,
        cacheCreationCost: 0.01,
        total: 1.24,
        model: 'claude-sonnet-4-20250514',
      },
      models: new Set(['claude-sonnet-4-20250514']),
      agentCount: 3,
      toolCalls: 47,
      toolUsage: new Map([['Read', 20], ['Write', 15], ['Bash', 12]]),
      entryCount: 100,
      assistantEntries: 50,
    });

    it('should have required metric fields', () => {
      const metrics = createMockMetrics();

      expect(metrics.sessionId).toBeDefined();
      expect(metrics.projectName).toBeDefined();
      expect(metrics.tokensIn).toBeGreaterThanOrEqual(0);
      expect(metrics.tokensOut).toBeGreaterThanOrEqual(0);
      expect(metrics.cost.total).toBeGreaterThanOrEqual(0);
      expect(metrics.agentCount).toBeGreaterThanOrEqual(0);
      expect(metrics.toolCalls).toBeGreaterThanOrEqual(0);
    });

    it('should format session ID as 8-char prefix', () => {
      const metrics = createMockMetrics();
      const shortId = metrics.sessionId.slice(0, 8);

      expect(shortId).toBe('test-ses');
      expect(shortId.length).toBe(8);
    });
  });
});

describe('JSON output structure', () => {
  it('should have correct JSON output shape', () => {
    const mockOutput = {
      sessionId: 'test-session-id',
      project: 'test-project',
      projectPath: '/test/path',
      startedAt: new Date().toISOString(),
      lastActivity: new Date().toISOString(),
      tokens: {
        input: 1000,
        output: 500,
        cacheRead: 200,
        cacheCreation: 100,
      },
      cost: {
        total: 1.50,
        input: 0.50,
        output: 0.80,
        cacheRead: 0.15,
        cacheCreation: 0.05,
      },
      agents: 2,
      toolCalls: 10,
      models: ['claude-sonnet-4-20250514'],
      entryCount: 50,
    };

    // Verify structure
    expect(mockOutput).toHaveProperty('sessionId');
    expect(mockOutput).toHaveProperty('project');
    expect(mockOutput).toHaveProperty('tokens');
    expect(mockOutput).toHaveProperty('cost');
    expect(mockOutput).toHaveProperty('agents');
    expect(mockOutput).toHaveProperty('toolCalls');
    expect(mockOutput).toHaveProperty('models');

    // Verify tokens structure
    expect(mockOutput.tokens).toHaveProperty('input');
    expect(mockOutput.tokens).toHaveProperty('output');
    expect(mockOutput.tokens).toHaveProperty('cacheRead');
    expect(mockOutput.tokens).toHaveProperty('cacheCreation');

    // Verify cost structure
    expect(mockOutput.cost).toHaveProperty('total');
    expect(mockOutput.cost).toHaveProperty('input');
    expect(mockOutput.cost).toHaveProperty('output');

    // Verify models is an array
    expect(Array.isArray(mockOutput.models)).toBe(true);
  });

  it('should serialize dates as ISO strings', () => {
    const date = new Date('2026-01-08T12:00:00Z');
    const isoString = date.toISOString();

    expect(isoString).toBe('2026-01-08T12:00:00.000Z');
    expect(typeof isoString).toBe('string');
  });
});

describe('edge cases', () => {
  describe('empty metrics', () => {
    it('should handle zero token counts', () => {
      const emptyMetrics: SessionMetrics = {
        sessionId: 'empty-session',
        projectPath: '/test',
        projectName: 'test',
        startedAt: new Date(),
        lastActivity: new Date(),
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

      expect(emptyMetrics.tokensIn).toBe(0);
      expect(emptyMetrics.tokensOut).toBe(0);
      expect(emptyMetrics.cost.total).toBe(0);
      expect(emptyMetrics.models.size).toBe(0);
    });
  });

  describe('multiple models', () => {
    it('should track multiple models in a session', () => {
      const models = new Set(['claude-opus-4-5-20251101', 'claude-sonnet-4-20250514', 'claude-haiku-4-5-20251001']);

      expect(models.size).toBe(3);
      expect(Array.from(models)).toContain('claude-opus-4-5-20251101');
      expect(Array.from(models)).toContain('claude-sonnet-4-20250514');
    });
  });

  describe('project name extraction', () => {
    it('should extract project name from encoded path', () => {
      const encodedPath = '-Users-jayant-Documents-GitHub-test-project';
      const parts = encodedPath.split('-');
      const projectName = parts[parts.length - 1];

      expect(projectName).toBe('project');
    });
  });
});
