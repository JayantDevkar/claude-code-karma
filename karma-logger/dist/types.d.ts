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
    inputTokenCost: number;
    outputTokenCost: number;
    cacheReadCost: number;
    cacheCreationCost: number;
}
/**
 * Default Claude pricing (as of 2024)
 */
export declare const DEFAULT_COST_CONFIG: CostConfig;
/**
 * CLI command context
 */
export interface CommandContext {
    verbose: boolean;
    configPath?: string;
}
//# sourceMappingURL=types.d.ts.map