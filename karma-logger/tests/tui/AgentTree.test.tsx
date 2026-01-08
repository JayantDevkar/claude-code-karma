/**
 * AgentTree component unit tests
 * Phase 3: TUI agent hierarchy visualization tests
 */

import React from 'react';
import { describe, it, expect, beforeEach, vi } from 'vitest';
import { render } from 'ink-testing-library';
import { AgentTree } from '../../src/tui/components/AgentTree.js';
import type { AgentTreeNode, AgentMetrics } from '../../src/aggregator.js';
import type { CostBreakdown } from '../../src/cost.js';

/**
 * Helper to create mock cost breakdown
 */
function mockCost(total: number): CostBreakdown {
  return {
    inputCost: total * 0.4,
    outputCost: total * 0.4,
    cacheReadCost: total * 0.1,
    cacheCreationCost: total * 0.1,
    total,
    model: 'sonnet',
  };
}

/**
 * Helper to create mock agent metrics
 */
function mockMetrics(
  overrides: Partial<AgentMetrics> = {}
): AgentMetrics {
  return {
    agentId: 'test-agent',
    sessionId: 'test-session',
    agentType: 'explore',
    model: 'sonnet',
    startedAt: new Date(),
    lastActivity: new Date(), // Running by default
    tokensIn: 1000,
    tokensOut: 500,
    cacheReadTokens: 100,
    cacheCreationTokens: 50,
    cost: mockCost(0.015),
    toolsUsed: new Set(['Read', 'Grep']),
    toolCalls: 5,
    entryCount: 3,
    ...overrides,
  };
}

/**
 * Helper to create mock agent node
 */
function mockNode(
  overrides: Partial<AgentTreeNode> = {},
  metricsOverrides: Partial<AgentMetrics> = {}
): AgentTreeNode {
  return {
    id: overrides.id ?? 'test-agent',
    type: overrides.type ?? 'explore',
    model: overrides.model ?? 'sonnet',
    metrics: mockMetrics(metricsOverrides),
    children: overrides.children ?? [],
  };
}

describe('AgentTree', () => {
  beforeEach(() => {
    // Mock Date.now for consistent status derivation
    vi.useFakeTimers();
    vi.setSystemTime(new Date('2024-01-15T12:00:00Z'));
  });

  describe('Empty state', () => {
    it('shows "No active agents" when root is null', () => {
      const { lastFrame } = render(
        <AgentTree root={null} totalAgents={0} />
      );

      expect(lastFrame()).toContain('AGENT TREE');
      expect(lastFrame()).toContain('No active agents');
    });
  });

  describe('Tree structure', () => {
    it('renders root node with type and model', () => {
      const root = mockNode({
        type: 'main',
        model: 'opus',
      });

      const { lastFrame } = render(
        <AgentTree root={root} totalAgents={1} />
      );

      expect(lastFrame()).toContain('main');
      expect(lastFrame()).toContain('(opus)');
    });

    it('renders total agent count', () => {
      const root = mockNode({ type: 'main' });

      const { lastFrame } = render(
        <AgentTree root={root} totalAgents={5} />
      );

      expect(lastFrame()).toContain('total agents: 5');
    });

    it('renders child nodes with tree connectors', () => {
      const child1 = mockNode({ id: 'child1', type: 'explore-a3b' });
      const child2 = mockNode({ id: 'child2', type: 'plan-x7c' });

      const root = mockNode({
        type: 'main',
        children: [child1, child2],
      });

      const { lastFrame } = render(
        <AgentTree root={root} totalAgents={3} />
      );

      const frame = lastFrame()!;
      expect(frame).toContain('main');
      expect(frame).toContain('explore-a3b');
      expect(frame).toContain('plan-x7c');
      expect(frame).toContain('├──');
      expect(frame).toContain('└──');
    });

    it('renders nested children with proper indentation', () => {
      const grandchild = mockNode({ id: 'grandchild', type: 'grep-scan' });
      const child = mockNode({
        id: 'child',
        type: 'explore',
        children: [grandchild],
      });

      const root = mockNode({
        type: 'main',
        children: [child],
      });

      const { lastFrame } = render(
        <AgentTree root={root} totalAgents={3} />
      );

      const frame = lastFrame()!;
      expect(frame).toContain('main');
      expect(frame).toContain('explore');
      expect(frame).toContain('grep-scan');
    });
  });

  describe('Status indicators', () => {
    it('shows running indicator (⟳) for recently active agents', () => {
      const now = new Date();
      const root = mockNode(
        { type: 'main' },
        { lastActivity: now } // Just now = running
      );

      const { lastFrame } = render(
        <AgentTree root={root} totalAgents={1} />
      );

      // Running agents show progress bar instead of icon
      expect(lastFrame()).toContain('[');
      expect(lastFrame()).toContain('%');
    });

    it('shows complete indicator (✓) for idle agents', () => {
      const oldTime = new Date(Date.now() - 10000); // 10 seconds ago
      const root = mockNode(
        { type: 'main' },
        { lastActivity: oldTime }
      );

      const { lastFrame } = render(
        <AgentTree root={root} totalAgents={1} />
      );

      expect(lastFrame()).toContain('✓');
    });
  });

  describe('Cost display', () => {
    it('displays cost per agent', () => {
      const root = mockNode(
        { type: 'main' },
        { cost: mockCost(1.50) }
      );

      const { lastFrame } = render(
        <AgentTree root={root} totalAgents={1} />
      );

      expect(lastFrame()).toContain('$1.50');
    });

    it('formats small costs correctly', () => {
      const root = mockNode(
        { type: 'main' },
        { cost: mockCost(0.0123) }
      );

      const { lastFrame } = render(
        <AgentTree root={root} totalAgents={1} />
      );

      expect(lastFrame()).toContain('$0.012');
    });
  });

  describe('Progress bar', () => {
    it('shows progress bar for running agents', () => {
      const now = new Date();
      const root = mockNode(
        { type: 'main' },
        { lastActivity: now, entryCount: 5 }
      );

      const { lastFrame } = render(
        <AgentTree root={root} totalAgents={1} />
      );

      const frame = lastFrame()!;
      expect(frame).toContain('[');
      expect(frame).toContain('█');
      expect(frame).toContain('░');
      expect(frame).toContain('50%'); // 5 entries * 10 = 50%
    });

    it('caps progress at 90%', () => {
      const now = new Date();
      const root = mockNode(
        { type: 'main' },
        { lastActivity: now, entryCount: 20 }
      );

      const { lastFrame } = render(
        <AgentTree root={root} totalAgents={1} />
      );

      expect(lastFrame()).toContain('90%');
    });
  });

  describe('Display name fallback', () => {
    it('uses agent type as display name', () => {
      const root = mockNode({ id: 'abc12345def', type: 'explore' });

      const { lastFrame } = render(
        <AgentTree root={root} totalAgents={1} />
      );

      expect(lastFrame()).toContain('explore');
    });

    it('falls back to truncated ID when type is unknown', () => {
      const root = mockNode({ id: 'abc12345def', type: 'unknown' });

      const { lastFrame } = render(
        <AgentTree root={root} totalAgents={1} />
      );

      expect(lastFrame()).toContain('abc12345');
    });
  });
});
