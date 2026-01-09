import { describe, it, expect } from 'vitest';
import { join, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';
import {
  parseSessionFile,
  extractToolCalls,
  hasThinkingContent,
  extractThinkingText,
  getToolUsageCounts,
} from '../src/index.js';
import type { ContentBlock } from '../src/index.js';

const __dirname = dirname(fileURLToPath(import.meta.url));
const FIXTURES = join(__dirname, 'fixtures');

describe('extractToolCalls', () => {
  it('extracts tool names from content', () => {
    const content: ContentBlock[] = [
      { type: 'tool_use', id: '1', name: 'Read', input: {} },
      { type: 'text', text: 'done' },
      { type: 'tool_use', id: '2', name: 'Write', input: {} },
    ];
    expect(extractToolCalls(content)).toEqual(['Read', 'Write']);
  });

  it('returns empty array for no tools', () => {
    const content: ContentBlock[] = [{ type: 'text', text: 'hello' }];
    expect(extractToolCalls(content)).toEqual([]);
  });

  it('returns empty array for empty content', () => {
    expect(extractToolCalls([])).toEqual([]);
  });

  it('handles mixed content types', () => {
    const content: ContentBlock[] = [
      { type: 'thinking', thinking: 'hmm...' },
      { type: 'tool_use', id: '1', name: 'Bash', input: { command: 'ls' } },
      { type: 'text', text: 'result' },
    ];
    expect(extractToolCalls(content)).toEqual(['Bash']);
  });
});

describe('hasThinkingContent', () => {
  it('detects thinking blocks', () => {
    const content: ContentBlock[] = [
      { type: 'thinking', thinking: 'hmm...' },
      { type: 'text', text: 'answer' },
    ];
    expect(hasThinkingContent(content)).toBe(true);
  });

  it('returns false when no thinking', () => {
    const content: ContentBlock[] = [{ type: 'text', text: 'answer' }];
    expect(hasThinkingContent(content)).toBe(false);
  });

  it('returns false for empty content', () => {
    expect(hasThinkingContent([])).toBe(false);
  });

  it('detects thinking among multiple blocks', () => {
    const content: ContentBlock[] = [
      { type: 'text', text: 'before' },
      { type: 'thinking', thinking: 'analysis...' },
      { type: 'tool_use', id: '1', name: 'Read', input: {} },
      { type: 'text', text: 'after' },
    ];
    expect(hasThinkingContent(content)).toBe(true);
  });
});

describe('extractThinkingText', () => {
  it('extracts thinking text from blocks', () => {
    const content: ContentBlock[] = [
      { type: 'thinking', thinking: 'First thought' },
      { type: 'text', text: 'answer' },
      { type: 'thinking', thinking: 'Second thought' },
    ];
    expect(extractThinkingText(content)).toEqual(['First thought', 'Second thought']);
  });

  it('returns empty array when no thinking', () => {
    const content: ContentBlock[] = [{ type: 'text', text: 'answer' }];
    expect(extractThinkingText(content)).toEqual([]);
  });
});

describe('getToolUsageCounts', () => {
  it('counts tool usage across entries', async () => {
    const entries = await parseSessionFile(join(FIXTURES, 'with-tools.jsonl'));
    const counts = getToolUsageCounts(entries);
    expect(counts.get('Read')).toBe(1);
  });

  it('returns empty map for entries without tools', async () => {
    const entries = await parseSessionFile(join(FIXTURES, 'with-thinking.jsonl'));
    const counts = getToolUsageCounts(entries);
    expect(counts.size).toBe(0);
  });

  it('counts multiple uses of same tool', () => {
    const entries = [
      {
        type: 'assistant' as const,
        uuid: 'a1',
        parentUuid: null,
        sessionId: 's1',
        timestamp: new Date(),
        toolCalls: ['Read', 'Write', 'Read'],
        hasThinking: false,
      },
      {
        type: 'assistant' as const,
        uuid: 'a2',
        parentUuid: 'a1',
        sessionId: 's1',
        timestamp: new Date(),
        toolCalls: ['Read', 'Bash'],
        hasThinking: false,
      },
    ];
    const counts = getToolUsageCounts(entries);
    expect(counts.get('Read')).toBe(3);
    expect(counts.get('Write')).toBe(1);
    expect(counts.get('Bash')).toBe(1);
  });
});
