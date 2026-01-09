import { describe, it, expect } from 'vitest';
import { join, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';
import {
  parseSessionFile,
  parseSession,
  parseLine,
  extractSessionId,
} from '../src/index.js';

const __dirname = dirname(fileURLToPath(import.meta.url));
const FIXTURES = join(__dirname, 'fixtures');

describe('parseLine', () => {
  it('parses valid user entry', () => {
    const line = '{"type":"user","uuid":"u1","parentUuid":null,"sessionId":"s1","timestamp":"2025-01-09T10:00:00Z"}';
    const result = parseLine(line);
    expect(result).not.toBeNull();
    expect(result?.type).toBe('user');
    expect(result?.uuid).toBe('u1');
  });

  it('parses valid assistant entry', () => {
    const line = '{"type":"assistant","uuid":"a1","parentUuid":"u1","sessionId":"s1","timestamp":"2025-01-09T10:00:05Z","message":{"model":"claude-3-opus","id":"msg_1","type":"message","role":"assistant","content":[],"stop_reason":"end_turn","stop_sequence":null,"usage":{"input_tokens":10,"output_tokens":5}}}';
    const result = parseLine(line);
    expect(result).not.toBeNull();
    expect(result?.type).toBe('assistant');
  });

  it('returns null for invalid JSON', () => {
    expect(parseLine('not json')).toBeNull();
  });

  it('returns null for missing required fields', () => {
    expect(parseLine('{"type":"user"}')).toBeNull();
  });

  it('returns null for empty string', () => {
    expect(parseLine('')).toBeNull();
  });
});

describe('parseSessionFile', () => {
  it('parses simple session', async () => {
    const entries = await parseSessionFile(join(FIXTURES, 'simple-session.jsonl'));
    expect(entries).toHaveLength(2);
    expect(entries[0].type).toBe('user');
    expect(entries[1].type).toBe('assistant');
    expect(entries[1].model).toBe('claude-3-opus');
  });

  it('extracts token usage', async () => {
    const entries = await parseSessionFile(join(FIXTURES, 'simple-session.jsonl'));
    const assistant = entries[1];
    expect(assistant.usage?.inputTokens).toBe(10);
    expect(assistant.usage?.outputTokens).toBe(5);
  });

  it('parses tool usage entries', async () => {
    const entries = await parseSessionFile(join(FIXTURES, 'with-tools.jsonl'));
    expect(entries).toHaveLength(2);
    const assistant = entries[1];
    expect(assistant.toolCalls).toContain('Read');
    expect(assistant.usage?.cacheReadTokens).toBe(5);
  });

  it('parses entries with thinking', async () => {
    const entries = await parseSessionFile(join(FIXTURES, 'with-thinking.jsonl'));
    expect(entries).toHaveLength(1);
    expect(entries[0].hasThinking).toBe(true);
  });
});

describe('parseSession', () => {
  it('returns ParsedSession with aggregates', async () => {
    const session = await parseSession(join(FIXTURES, 'simple-session.jsonl'));
    expect(session.sessionId).toBe('simple-session');
    expect(session.entries).toHaveLength(2);
    expect(session.models.has('claude-3-opus')).toBe(true);
    expect(session.totalUsage.inputTokens).toBe(10);
  });

  it('sets start and end time from entries', async () => {
    const session = await parseSession(join(FIXTURES, 'simple-session.jsonl'));
    expect(session.startTime).toBeInstanceOf(Date);
    expect(session.endTime).toBeInstanceOf(Date);
    expect(session.endTime.getTime()).toBeGreaterThan(session.startTime.getTime());
  });
});

describe('extractSessionId', () => {
  it('extracts UUID from filename', () => {
    expect(extractSessionId('/path/to/abc123de-1234-5678-9abc-def012345678.jsonl'))
      .toBe('abc123de-1234-5678-9abc-def012345678');
  });

  it('returns filename as-is for non-UUID', () => {
    expect(extractSessionId('/path/to/my-session.jsonl')).toBe('my-session');
  });

  it('handles nested paths', () => {
    expect(extractSessionId('/a/b/c/d/session.jsonl')).toBe('session');
  });

  it('handles uppercase UUID', () => {
    expect(extractSessionId('/path/ABC123DE-1234-5678-9ABC-DEF012345678.jsonl'))
      .toBe('ABC123DE-1234-5678-9ABC-DEF012345678');
  });
});
