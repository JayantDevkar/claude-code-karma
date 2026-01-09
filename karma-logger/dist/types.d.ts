/**
 * Core TypeScript interfaces for karma-logger
 *
 * Parsing-related types are exported from 'claude-code-files-parser' package.
 * This file contains karma-logger specific types for aggregation, persistence, and UI.
 */
/**
 * Re-export parsing types for convenience.
 * Consumers can also import directly from 'claude-code-files-parser'.
 */
export type { RawTokenUsage, ThinkingBlock, ToolUseBlock, TextBlock, ContentBlock, UserMessage, AssistantMessage, RawLogEntry, TokenUsage, LogEntry, ParsedSession, } from 'claude-code-files-parser';
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
    lastActivity: string;
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
    day: string;
    tokensIn: number;
    tokensOut: number;
    cost: number;
    sessions: number;
}
//# sourceMappingURL=types.d.ts.map