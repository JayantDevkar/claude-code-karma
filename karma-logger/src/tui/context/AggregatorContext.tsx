/**
 * React Context for MetricsAggregator
 * Phase 2: Provides aggregator access to all TUI components
 */

import React, { createContext, useContext } from 'react';
import type { MetricsAggregator } from '../../aggregator.js';

/**
 * Context value type for aggregator provider
 */
export interface AggregatorContextValue {
  aggregator: MetricsAggregator | null;
  sessionId: string | null;
}

/**
 * Aggregator context for dependency injection
 */
export const AggregatorContext = createContext<AggregatorContextValue | null>(null);

/**
 * Provider props
 */
interface AggregatorProviderProps {
  aggregator: MetricsAggregator | null;
  sessionId?: string | null;
  children?: React.ReactNode;
}

/**
 * Provider component for aggregator context
 */
export const AggregatorProvider: React.FC<AggregatorProviderProps> = ({
  aggregator,
  sessionId = null,
  children
}) => {
  return (
    <AggregatorContext.Provider value={{ aggregator, sessionId }}>
      {children}
    </AggregatorContext.Provider>
  );
};

/**
 * Hook to access the aggregator from context
 */
export function useAggregator(): MetricsAggregator | null {
  const context = useContext(AggregatorContext);
  return context?.aggregator ?? null;
}

/**
 * Hook to access the session ID from context
 */
export function useSessionId(): string | null {
  const context = useContext(AggregatorContext);
  return context?.sessionId ?? null;
}
