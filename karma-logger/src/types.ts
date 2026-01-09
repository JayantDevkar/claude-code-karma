/**
 * Core TypeScript interfaces for karma-logger
 *
 * Parsing-related types are exported from 'claude-code-files-parser' package.
 * This file contains karma-logger specific types for aggregation, persistence, and UI.
 */

// ============================================
// Re-exports from claude-code-files-parser
// ============================================

/**
 * Re-export parsing types for convenience.
 * Consumers can also import directly from 'claude-code-files-parser'.
 */
export type {
  // Raw types
  RawTokenUsage,
  ThinkingBlock,
  ToolUseBlock,
  TextBlock,
  ContentBlock,
  UserMessage,
  AssistantMessage,
  RawLogEntry,
  // Normalized types
  TokenUsage,
  LogEntry,
  ParsedSession,
} from 'claude-code-files-parser';

// ============================================
// Karma-Logger Specific Types
// ============================================

/**
 * Aggregated metrics for a session (legacy type from types.ts)
 * Note: aggregator.ts defines a more complete SessionMetrics interface
 */
export interface SessionMetrics {
  sessionId: string;
  startTime: Date;
  endTime?: Date;
  totalInputTokens: number;
  totalOutputTokens: number;
  totalCacheReadTokens: number;
  totalCacheCreationTokens: number;
  toolCalls: number;
  errors: number;
  estimatedCost: number;
}

/**
 * Cost calculation configuration
 */
export interface CostConfig {
  inputTokenCost: number;      // per 1M tokens
  outputTokenCost: number;     // per 1M tokens
  cacheReadCost: number;       // per 1M tokens
  cacheCreationCost: number;   // per 1M tokens
}

/**
 * Default Claude pricing (as of 2024)
 */
export const DEFAULT_COST_CONFIG: CostConfig = {
  inputTokenCost: 3.00,        // $3/1M input tokens
  outputTokenCost: 15.00,      // $15/1M output tokens
  cacheReadCost: 0.30,         // $0.30/1M cache read
  cacheCreationCost: 3.75,     // $3.75/1M cache creation
};

/**
 * CLI command context
 */
export interface CommandContext {
  verbose: boolean;
  configPath?: string;
}

// ============================================
// Activity Tracking Types (FLAW-006)
// ============================================

/**
 * Activity entry for persistent activity buffer
 * Tracks tool calls and results for replay after restart
 */
export interface ActivityEntry {
  timestamp: Date;
  sessionId: string;
  tool: string;
  type: 'tool_call' | 'result';
  agentId?: string;
  model?: string;
}

// ============================================
// Historical Dashboard Types (Phase 1)
// ============================================

/**
 * Aggregated project metrics for historical dashboard
 */
export interface ProjectSummary {
  projectName: string;
  sessionCount: number;
  activeDays: number;
  totalTokensIn: number;
  totalTokensOut: number;
  totalCost: number;
  lastActivity: string; // ISO 8601
}

/**
 * Project detail with summary and sessions list
 */
export interface ProjectDetail {
  summary: ProjectSummary;
  sessions: import('./db.js').SessionRecord[];
}

/**
 * Daily metrics rollup for trend charts
 */
export interface DailyMetric {
  day: string;       // YYYY-MM-DD
  tokensIn: number;
  tokensOut: number;
  cost: number;
  sessions: number;
}
