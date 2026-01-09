/**
 * Thinking block detection in Claude Code content
 */

import type { ContentBlock } from '../types/index.js';

/**
 * Check if content contains thinking blocks
 */
export function hasThinkingContent(content: ContentBlock[]): boolean {
  return content.some(block => block.type === 'thinking');
}

/**
 * Extract thinking text from content blocks
 */
export function extractThinkingText(content: ContentBlock[]): string[] {
  return content
    .filter(block => block.type === 'thinking')
    .map(block => (block as { thinking: string }).thinking);
}
