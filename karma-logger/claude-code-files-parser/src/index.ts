// Claude Code Files Parser
// Streaming parser for Claude Code JSONL session logs

export const VERSION = '0.1.0';

// Types
export type {
  // Raw
  RawTokenUsage,
  ThinkingBlock,
  ToolUseBlock,
  TextBlock,
  ContentBlock,
  UserMessage,
  AssistantMessage,
  RawLogEntry,
  // Normalized
  TokenUsage,
  LogEntry,
  ParsedSession,
} from './types/index.js';

// Extractors
export {
  extractToolCalls,
  getToolUsageCounts,
  hasThinkingContent,
  extractThinkingText,
  extractAgentSpawns,
} from './extractors/index.js';
export type { AgentSpawnInfo } from './extractors/index.js';

// Parser
export { parseLine, parseSessionFile, parseSession, extractSessionId } from './parser.js';

// Normalization
export { normalizeEntry, normalizeUsage, emptyUsage, addUsage } from './normalize.js';

// Type guards
export { isValidEntry, isAssistantMessage } from './guards.js';

// Utilities
export {
  filterAssistantEntries,
  getTotalUsage,
  buildHierarchy,
  getModels,
  getSessionDuration,
  filterByTimeRange,
  groupBySession,
  findRootEntries,
  findEntryByUuid,
} from './utils.js';
