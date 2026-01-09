/**
 * Type guards for Claude Code log entries
 */

import type { RawLogEntry, AssistantMessage } from './types/index.js';

/**
 * Type guard to check if entry is a valid user or assistant entry
 */
export function isValidEntry(entry: unknown): entry is RawLogEntry {
  if (typeof entry !== 'object' || entry === null) return false;
  const e = entry as Record<string, unknown>;
  return (
    (e.type === 'user' || e.type === 'assistant') &&
    typeof e.uuid === 'string' &&
    typeof e.sessionId === 'string' &&
    typeof e.timestamp === 'string'
  );
}

/**
 * Type guard to check if message is an assistant message with usage
 */
export function isAssistantMessage(msg: unknown): msg is AssistantMessage {
  if (typeof msg !== 'object' || msg === null) return false;
  const m = msg as Record<string, unknown>;
  return m.role === 'assistant' && typeof m.usage === 'object';
}
