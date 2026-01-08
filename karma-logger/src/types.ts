/**
 * Core TypeScript interfaces for karma-logger
 */

/**
 * Represents a single log entry from Claude Code JSONL files
 */
export interface LogEntry {
  timestamp: string;
  type: 'request' | 'response' | 'tool_use' | 'tool_result' | 'error';
  sessionId: string;
  data: Record<string, unknown>;
}

/**
 * Token usage for a single interaction
 */
export interface TokenUsage {
  inputTokens: number;
  outputTokens: number;
  cacheReadTokens?: number;
  cacheCreationTokens?: number;
}

/**
 * Aggregated metrics for a session
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
