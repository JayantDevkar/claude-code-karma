/**
 * Parser unit tests
 * Phase 1: JSONL Parser tests
 */

import { describe, it, expect } from 'vitest';
import { join, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';
import {
  parseSessionFile,
  parseSession,
  extractSessionId,
  filterAssistantEntries,
  getTotalUsage,
  buildHierarchy,
  getModels,
  getToolUsageCounts,
} from '../src/parser.js';

const __dirname = dirname(fileURLToPath(import.meta.url));
const fixturesDir = join(__dirname, 'fixtures');

describe('parseSessionFile', () => {
  it('parses valid JSONL file correctly', async () => {
    const entries = await parseSessionFile(join(fixturesDir, 'valid-session.jsonl'));

    expect(entries).toHaveLength(5);
    expect(entries[0].type).toBe('user');
    expect(entries[1].type).toBe('assistant');
  });

  it('extracts token usage from assistant entries', async () => {
    const entries = await parseSessionFile(join(fixturesDir, 'valid-session.jsonl'));
    const assistant = entries.find(e => e.type === 'assistant' && e.usage);

    expect(assistant).toBeDefined();
    expect(assistant?.usage?.inputTokens).toBe(100);
    expect(assistant?.usage?.outputTokens).toBe(50);
  });

  it('handles malformed JSON gracefully', async () => {
    const entries = await parseSessionFile(join(fixturesDir, 'malformed-session.jsonl'));

    // Should skip malformed lines and return valid entries
    expect(entries).toHaveLength(2);
    expect(entries[0].type).toBe('user');
    expect(entries[1].type).toBe('assistant');
  });

  it('handles empty file', async () => {
    const entries = await parseSessionFile(join(fixturesDir, 'empty-session.jsonl'));

    expect(entries).toHaveLength(0);
  });

  it('skips non-user/assistant entry types', async () => {
    const entries = await parseSessionFile(join(fixturesDir, 'mixed-types-session.jsonl'));

    // Should skip file-history-snapshot and summary
    expect(entries).toHaveLength(2);
    expect(entries.every(e => e.type === 'user' || e.type === 'assistant')).toBe(true);
  });

  it('extracts tool calls correctly', async () => {
    const entries = await parseSessionFile(join(fixturesDir, 'valid-session.jsonl'));
    const withToolUse = entries.find(e => e.toolCalls.length > 0);

    expect(withToolUse).toBeDefined();
    expect(withToolUse?.toolCalls).toContain('Read');
  });

  it('detects thinking blocks', async () => {
    const entries = await parseSessionFile(join(fixturesDir, 'valid-session.jsonl'));
    const withThinking = entries.find(e => e.hasThinking);

    expect(withThinking).toBeDefined();
  });

  it('extracts cache tokens correctly', async () => {
    const entries = await parseSessionFile(join(fixturesDir, 'valid-session.jsonl'));
    const withCache = entries.find(e => e.usage?.cacheCreationTokens && e.usage.cacheCreationTokens > 0);

    expect(withCache).toBeDefined();
    expect(withCache?.usage?.cacheCreationTokens).toBe(1000);
    expect(withCache?.usage?.cacheReadTokens).toBe(50);
  });
});

describe('extractSessionId', () => {
  it('extracts UUID from file path', () => {
    const id = extractSessionId('/path/to/0074cde8-b763-45ee-be32-cfc80f965b4d.jsonl');
    expect(id).toBe('0074cde8-b763-45ee-be32-cfc80f965b4d');
  });

  it('handles non-UUID filenames', () => {
    const id = extractSessionId('/path/to/custom-session.jsonl');
    expect(id).toBe('custom-session');
  });
});

describe('parseSession', () => {
  it('returns complete ParsedSession', async () => {
    const session = await parseSession(join(fixturesDir, 'valid-session.jsonl'));

    expect(session.sessionId).toBe('valid-session');
    expect(session.entries).toHaveLength(5);
    expect(session.models.has('claude-sonnet-4-20250514')).toBe(true);
    expect(session.startTime).toBeInstanceOf(Date);
    expect(session.endTime).toBeInstanceOf(Date);
  });

  it('calculates total usage across all entries', async () => {
    const session = await parseSession(join(fixturesDir, 'valid-session.jsonl'));

    // Sum of all entries: 100+200+300 = 600 input, 50+100+75 = 225 output
    expect(session.totalUsage.inputTokens).toBe(600);
    expect(session.totalUsage.outputTokens).toBe(225);
  });
});

describe('filterAssistantEntries', () => {
  it('filters to only assistant entries with usage', async () => {
    const entries = await parseSessionFile(join(fixturesDir, 'valid-session.jsonl'));
    const filtered = filterAssistantEntries(entries);

    expect(filtered.every(e => e.type === 'assistant' && e.usage)).toBe(true);
    expect(filtered.length).toBeLessThan(entries.length);
  });
});

describe('getTotalUsage', () => {
  it('sums up all token usage', async () => {
    const entries = await parseSessionFile(join(fixturesDir, 'valid-session.jsonl'));
    const total = getTotalUsage(entries);

    expect(total.inputTokens).toBe(600);
    expect(total.outputTokens).toBe(225);
    expect(total.cacheReadTokens).toBe(150); // 0+50+100
    expect(total.cacheCreationTokens).toBe(1000);
  });

  it('returns zeros for empty entries', () => {
    const total = getTotalUsage([]);

    expect(total.inputTokens).toBe(0);
    expect(total.outputTokens).toBe(0);
  });
});

describe('buildHierarchy', () => {
  it('builds parent-child map', async () => {
    const entries = await parseSessionFile(join(fixturesDir, 'valid-session.jsonl'));
    const hierarchy = buildHierarchy(entries);

    // First user message should have the first assistant as child
    expect(hierarchy.get('a1111111-1111-1111-1111-111111111111')).toContain('b2222222-2222-2222-2222-222222222222');
  });
});

describe('getModels', () => {
  it('returns unique models used', async () => {
    const entries = await parseSessionFile(join(fixturesDir, 'valid-session.jsonl'));
    const models = getModels(entries);

    expect(models).toContain('claude-sonnet-4-20250514');
    expect(models.length).toBe(1);
  });

  it('handles multiple models', async () => {
    const entries = await parseSessionFile(join(fixturesDir, 'mixed-types-session.jsonl'));
    const models = getModels(entries);

    expect(models).toContain('claude-opus-4-5-20251101');
  });
});

describe('getToolUsageCounts', () => {
  it('counts tool usage', async () => {
    const entries = await parseSessionFile(join(fixturesDir, 'valid-session.jsonl'));
    const counts = getToolUsageCounts(entries);

    expect(counts.get('Read')).toBe(1);
  });

  it('returns empty map when no tools used', async () => {
    const entries = await parseSessionFile(join(fixturesDir, 'malformed-session.jsonl'));
    const counts = getToolUsageCounts(entries);

    expect(counts.size).toBe(0);
  });
});
