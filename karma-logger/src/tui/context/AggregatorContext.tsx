/**
 * React Context for MetricsAggregator
 * Phase 2: Provides aggregator access to all TUI components
 */

import React, { createContext, useContext } from 'react';
import type { MetricsAggregator } from '../../aggregator.js';

interface AggregatorContextValue {
  aggregator: MetricsAggregator | null;
}

const AggregatorContext = createContext<AggregatorContextValue>({ aggregator: null });

interface AggregatorProviderProps {
  aggregator: MetricsAggregator | null;
  children?: React.ReactNode;
}

export const AggregatorProvider: React.FC<AggregatorProviderProps> = ({
  aggregator,
  children
}) => {
  return (
    <AggregatorContext.Provider value={{ aggregator }}>
      {children}
    </AggregatorContext.Provider>
  );
};

export function useAggregator(): MetricsAggregator | null {
  const { aggregator } = useContext(AggregatorContext);
  return aggregator;
}
