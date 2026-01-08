import { render, type Instance } from 'ink';
import React from 'react';
import { App } from './App.js';
import { AggregatorProvider } from './context/index.js';
import type { MetricsAggregator } from '../aggregator.js';

export interface TUIOptions {
  sessionId?: string;
  aggregator?: MetricsAggregator | null;
}

/**
 * Start the TUI dashboard
 * @param options.sessionId - Session ID to display
 * @param options.aggregator - MetricsAggregator instance for live metrics
 * @returns Ink instance for cleanup
 */
export function startTUI(options: TUIOptions = {}): Instance {
  const { sessionId, aggregator = null } = options;

  const app = React.createElement(App, { sessionId });
  const provider = React.createElement(AggregatorProvider, { aggregator, children: app });

  return render(provider);
}

export { App } from './App.js';
export * from './components/index.js';
export * from './hooks/index.js';
export * from './utils/index.js';
export { AggregatorProvider, useAggregator } from './context/index.js';
