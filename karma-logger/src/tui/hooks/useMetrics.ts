import { useState, useEffect, useCallback } from 'react';
import { useAggregator } from '../context/index.js';

export interface MetricsState {
  tokensIn: number;
  tokensOut: number;
  totalCost: number;
  cacheReadTokens: number;
  cacheCreationTokens: number;
  toolCalls: number;
  sessions: number;
  agents: number;
}

const POLL_INTERVAL = 1000; // 1Hz refresh

const EMPTY_METRICS: MetricsState = {
  tokensIn: 0,
  tokensOut: 0,
  totalCost: 0,
  cacheReadTokens: 0,
  cacheCreationTokens: 0,
  toolCalls: 0,
  sessions: 0,
  agents: 0,
};

/**
 * Hook to poll metrics from aggregator via context
 * Automatically connects to aggregator provided by AggregatorProvider
 */
export function useMetrics(): MetricsState {
  const aggregator = useAggregator();

  const getMetrics = useCallback((): MetricsState => {
    if (!aggregator) return EMPTY_METRICS;
    const totals = aggregator.getTotals();
    return {
      tokensIn: totals.tokensIn,
      tokensOut: totals.tokensOut,
      totalCost: totals.totalCost,
      cacheReadTokens: totals.cacheReadTokens,
      cacheCreationTokens: totals.cacheCreationTokens,
      toolCalls: totals.toolCalls,
      sessions: totals.sessions,
      agents: totals.agents,
    };
  }, [aggregator]);

  const [metrics, setMetrics] = useState<MetricsState>(getMetrics);

  useEffect(() => {
    // Initial fetch
    setMetrics(getMetrics());

    // Poll for updates
    const interval = setInterval(() => {
      setMetrics(getMetrics());
    }, POLL_INTERVAL);

    return () => clearInterval(interval);
  }, [getMetrics]);

  return metrics;
}

/**
 * Hook with real aggregator connection
 * Use this when aggregator is available as a singleton or via context
 */
export function useMetricsWithAggregator(
  getMetrics: () => MetricsState
): MetricsState {
  const [metrics, setMetrics] = useState<MetricsState>(getMetrics);

  useEffect(() => {
    const interval = setInterval(() => {
      setMetrics(getMetrics());
    }, POLL_INTERVAL);

    return () => clearInterval(interval);
  }, [getMetrics]);

  return metrics;
}
