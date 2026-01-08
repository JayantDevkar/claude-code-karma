import { useState, useEffect } from 'react';
import type { AgentTreeNode } from '../../aggregator.js';

interface AgentTreeState {
  root: AgentTreeNode | null;
  count: number;
}

const POLL_INTERVAL = 1000; // 1Hz refresh

/**
 * Hook to poll agent tree from aggregator
 */
export function useAgentTree(): AgentTreeState {
  const [tree, setTree] = useState<AgentTreeState>({
    root: null,
    count: 0,
  });

  useEffect(() => {
    // Simulated - replace with real aggregator connection
    const interval = setInterval(() => {
      // This would be: aggregator.getAgentTree(sessionId)
      setTree(prev => prev);
    }, POLL_INTERVAL);

    return () => clearInterval(interval);
  }, []);

  return tree;
}

/**
 * Hook with real aggregator connection
 */
export function useAgentTreeWithAggregator(
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
