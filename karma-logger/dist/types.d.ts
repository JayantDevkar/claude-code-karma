/**
 * Core TypeScript interfaces for karma-logger
 * Phase 1: JSONL Parser types based on actual Claude Code log format
 */
/**
 * Token usage from Claude API response
 */
export interface RawTokenUsage {
    input_tokens: number;
    output_tokens: number;
    cache_read_input_tokens?: number;
    cache_creation_input_tokens?: number;
    cache_creation?: {
        ephemeral_5m_input_tokens?: number;
        ephemeral_1h_input_tokens?: number;
    };
    service_tier?: string;
}
/**
 * Content block types in assistant messages
 */
export interface ThinkingBlock {
    type: 'thinking';
    thinking: string;
    signature?: string;
}
export interface ToolUseBlock {
    type: 'tool_use';
    id: string;
    name: string;
    input: Record<string, unknown>;
}
export interface TextBlock {
    type: 'text';
    text: string;
}
export type ContentBlock = ThinkingBlock | ToolUseBlock | TextBlock;
/**
 * Message structure for user entries
 */
export interface UserMessage {
    role: 'user';
    content: string;
}
/**
 * Message structure for assistant entries
 */
export interface AssistantMessage {
    model: string;
    id: string;
    type: 'message';
    role: 'assistant';
    content: ContentBlock[];
    stop_reason: string | null;
    stop_sequence: string | null;
    usage: RawTokenUsage;
}
/**
 * Raw log entry from Claude Code JSONL files
 */
export interface RawLogEntry {
    type: 'user' | 'assistant' | 'file-history-snapshot' | 'summary';
    uuid: string;
    parentUuid: string | null;
    sessionId: string;
    timestamp: string;
    cwd?: string;
    version?: string;
    gitBranch?: string;
    isSidechain?: boolean;
    userType?: 'external' | 'internal';
    message?: UserMessage | AssistantMessage;
    requestId?: string;
}
/**
 * Normalized token usage for aggregation
 */
export interface TokenUsage {
    inputTokens: number;
    outputTokens: number;
    cacheReadTokens: number;
    cacheCreationTokens: number;
}
/**
 * Parsed and normalized log entry
 */
export interface LogEntry {
    type: 'user' | 'assistant';
    uuid: string;
    parentUuid: string | null;
    sessionId: string;
    timestamp: Date;
    model?: string;
    usage?: TokenUsage;
    toolCalls: string[];
    hasThinking: boolean;
}
/**
 * Parsed session with all entries and metadata
 */
export interface ParsedSession {
    sessionId: string;
    projectPath: string;
    entries: LogEntry[];
    startTime: Date;
    endTime: Date;
    models: Set<string>;
    totalUsage: TokenUsage;
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
//# sourceMappingURL=types.d.ts.map