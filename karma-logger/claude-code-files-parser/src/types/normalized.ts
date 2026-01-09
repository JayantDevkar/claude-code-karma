/**
 * Normalized types for internal use after parsing
 * These are the cleaned-up versions used by consumers
 */

export interface TokenUsage {
  inputTokens: number;
  outputTokens: number;
  cacheReadTokens: number;
  cacheCreationTokens: number;
}

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

export interface ParsedSession {
  sessionId: string;
  projectPath: string;
  entries: LogEntry[];
  startTime: Date;
  endTime: Date;
  models: Set<string>;
  totalUsage: TokenUsage;
}
