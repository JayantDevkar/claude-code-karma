/**
 * Tool call extraction from Claude Code content blocks
 */

import type { ContentBlock, ToolUseBlock, LogEntry } from '../types/index.js';

/**
 * Extract tool call names from content blocks
 */
export function extractToolCalls(content: ContentBlock[]): string[] {
  return content
    .filter((block): block is ToolUseBlock => block.type === 'tool_use')
    .map(block => block.name);
}

/**
 * Get tool usage counts from entries
 */
export function getToolUsageCounts(entries: LogEntry[]): Map<string, number> {
  const counts = new Map<string, number>();

  for (const entry of entries) {
    for (const tool of entry.toolCalls) {
      counts.set(tool, (counts.get(tool) ?? 0) + 1);
    }
  }

  return counts;
}
