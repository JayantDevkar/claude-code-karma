/**
 * Raw types as found in Claude Code JSONL files
 * These match the exact structure written by Claude Code
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

export interface UserMessage {
  role: 'user';
  content: string;
}

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
