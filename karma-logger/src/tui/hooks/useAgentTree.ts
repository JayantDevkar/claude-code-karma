import { useState, useEffect, useContext } from 'react';
import type { AgentTreeNode, MetricsAggregator } from '../../aggregator.js';
import { AggregatorContext } from '../context/AggregatorContext.js';
import { emptyCostBreakdown } from '../../cost.js';

/**
 * Agent tree state returned by hooks
 */
export interface AgentTreeState {
  root: AgentTreeNode | null;
  count: number;
}

/**
 * Poll interval for tree refresh (1Hz)
 */
const POLL_INTERVAL = 1000;

/**
 * Build a synthetic root node that represents the main session
 * and contains all spawned agents as children
 */
function buildRootNode(
  nodes: AgentTreeNode[],
  sessionId: string,
  aggregator: MetricsAggregator
): AgentTreeNode | null {
  const sessionMetrics = aggregator.getSessionMetrics(sessionId);
  if (!sessionMetrics && nodes.length === 0) {
    return null;
  }

  // Create synthetic main node
  const mainNode: AgentTreeNode = {
    id: sessionId,
    type: 'main',
    model: sessionMetrics?.models.values().next().value || 'sonnet',
    metrics: {
      agentId: sessionId,
      sessionId,
      agentType: 'main',
      model: sessionMetrics?.models.values().next().value || 'sonnet',
      startedAt: sessionMetrics?.startedAt || new Date(),
      lastActivity: sessionMetrics?.lastActivity || new Date(),
      tokensIn: sessionMetrics?.tokensIn || 0,
      tokensOut: sessionMetrics?.tokensOut || 0,
      cacheReadTokens: sessionMetrics?.cacheReadTokens || 0,
      cacheCreationTokens: sessionMetrics?.cacheCreationTokens || 0,
      cost: sessionMetrics?.cost || emptyCostBreakdown(),
      toolsUsed: new Set(),
      toolCalls: sessionMetrics?.toolCalls || 0,
      entryCount: sessionMetrics?.entryCount || 0,
    },
    children: nodes,
  };

  return mainNode;
}

/**
 * Hook to get agent tree from context-provided aggregator
 * Uses AggregatorContext for dependency injection
 */
export function useAgentTree(): AgentTreeState {
  const context = useContext(AggregatorContext);
  const [tree, setTree] = useState<AgentTreeState>({
    root: null,
    count: 0,
  });

  useEffect(() => {
    if (!context?.aggregator || !context?.sessionId) {
      return;
    }

    const { aggregator, sessionId } = context;

    const updateTree = () => {
      const nodes = aggregator.getAgentTree(sessionId);
      const root = buildRootNode(nodes, sessionId, aggregator);
      const sessionMetrics = aggregator.getSessionMetrics(sessionId);
      setTree({
        root,
        count: (sessionMetrics?.agentCount || 0) + 1, // +1 for main
      });
    };

    // Initial fetch
    updateTree();

    // Poll for updates
    const interval = setInterval(updateTree, POLL_INTERVAL);

    return () => clearInterval(interval);
  }, [context]);

  return tree;
}

/**
 * Hook with explicit aggregator and session ID
 * Use when not using AggregatorContext
 */
export function useAgentTreeWithAggregator(
  aggregator: MetricsAggregator,
  sessionId: string
): AgentTreeState {
  const [tree, setTree] = useState<AgentTreeState>(() => {
    const nodes = aggregator.getAgentTree(sessionId);
    const root = buildRootNode(nodes, sessionId, aggregator);
    const sessionMetrics = aggregator.getSessionMetrics(sessionId);
    return {
      root,
      count: (sessionMetrics?.agentCount || 0) + 1,
    };
  });

  useEffect(() => {
    const updateTree = () => {
      const nodes = aggregator.getAgentTree(sessionId);
      const root = buildRootNode(nodes, sessionId, aggregator);
      const sessionMetrics = aggregator.getSessionMetrics(sessionId);
      setTree({
        root,
        count: (sessionMetrics?.agentCount || 0) + 1,
      });
    };

    const interval = setInterval(updateTree, POLL_INTERVAL);
    return () => clearInterval(interval);
  }, [aggregator, sessionId]);

  return tree;
}

/**
 * Hook with callback-based tree fetching
 * For use cases where the tree is provided externally
 */
export function useAgentTreeWithCallbacks(
  getTree: () => AgentTreeNode[],
  getCount: () => number
): AgentTreeState {
  const [tree, setTree] = useState<AgentTreeState>(() => {
    const nodes = getTree();
    return {
      root: nodes[0] || null,
      count: getCount(),
    };
  });

  useEffect(() => {
    const interval = setInterval(() => {
      const nodes = getTree();
      setTree({
        root: nodes[0] || null,
        count: getCount(),
      });
    }, POLL_INTERVAL);

    return () => clearInterval(interval);
  }, [getTree, getCount]);

  return tree;
}
