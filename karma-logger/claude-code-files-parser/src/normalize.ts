/**
 * Normalization functions for Claude Code log entries
 */

import type {
  RawLogEntry,
  AssistantMessage,
  TokenUsage,
  LogEntry,
} from './types/index.js';
import { isAssistantMessage } from './guards.js';
import { extractToolCalls, hasThinkingContent } from './extractors/index.js';

/**
 * Create empty token usage
 */
export function emptyUsage(): TokenUsage {
  return {
    inputTokens: 0,
    outputTokens: 0,
    cacheReadTokens: 0,
    cacheCreationTokens: 0,
  };
}

/**
 * Add two token usages together
 */
export function addUsage(a: TokenUsage, b: TokenUsage): TokenUsage {
  return {
    inputTokens: a.inputTokens + b.inputTokens,
    outputTokens: a.outputTokens + b.outputTokens,
    cacheReadTokens: a.cacheReadTokens + b.cacheReadTokens,
    cacheCreationTokens: a.cacheCreationTokens + b.cacheCreationTokens,
  };
}

/**
 * Normalize raw usage to our internal format
 */
export function normalizeUsage(raw: AssistantMessage['usage']): TokenUsage {
  return {
    inputTokens: raw.input_tokens ?? 0,
    outputTokens: raw.output_tokens ?? 0,
    cacheReadTokens: raw.cache_read_input_tokens ?? 0,
    cacheCreationTokens: raw.cache_creation_input_tokens ?? 0,
  };
}

/**
 * Transform raw entry to normalized LogEntry
 */
export function normalizeEntry(raw: RawLogEntry): LogEntry {
  const entry: LogEntry = {
    type: raw.type as 'user' | 'assistant',
    uuid: raw.uuid,
    parentUuid: raw.parentUuid,
    sessionId: raw.sessionId,
    timestamp: new Date(raw.timestamp),
    toolCalls: [],
    hasThinking: false,
  };

  if (raw.type === 'assistant' && raw.message && isAssistantMessage(raw.message)) {
    entry.model = raw.message.model;
    entry.usage = normalizeUsage(raw.message.usage);
    entry.toolCalls = extractToolCalls(raw.message.content);
    entry.hasThinking = hasThinkingContent(raw.message.content);
  }

  return entry;
}
