# Phase 7: Testing & Validation

**Status**: Pending
**Depends on**: Phase 6
**Unlocks**: Done

## Objective

Add tests to the new package and validate the full integration.

## Tasks

- [ ] Create test fixtures (sample JSONL files)
- [ ] Write unit tests for parser
- [ ] Write unit tests for extractors
- [ ] Write unit tests for utilities
- [ ] Run karma-logger integration tests
- [ ] Manual smoke test

## Test Fixtures

### tests/fixtures/simple-session.jsonl

```jsonl
{"type":"user","uuid":"u1","parentUuid":null,"sessionId":"test-session","timestamp":"2025-01-09T10:00:00Z","message":{"role":"user","content":"Hello"}}
{"type":"assistant","uuid":"a1","parentUuid":"u1","sessionId":"test-session","timestamp":"2025-01-09T10:00:05Z","message":{"model":"claude-3-opus","id":"msg_1","type":"message","role":"assistant","content":[{"type":"text","text":"Hi there!"}],"stop_reason":"end_turn","stop_sequence":null,"usage":{"input_tokens":10,"output_tokens":5}}}
```

### tests/fixtures/with-tools.jsonl

```jsonl
{"type":"user","uuid":"u1","parentUuid":null,"sessionId":"test-session","timestamp":"2025-01-09T10:00:00Z","message":{"role":"user","content":"Read file.txt"}}
{"type":"assistant","uuid":"a1","parentUuid":"u1","sessionId":"test-session","timestamp":"2025-01-09T10:00:05Z","message":{"model":"claude-3-opus","id":"msg_1","type":"message","role":"assistant","content":[{"type":"tool_use","id":"tool_1","name":"Read","input":{"file_path":"file.txt"}}],"stop_reason":"tool_use","stop_sequence":null,"usage":{"input_tokens":20,"output_tokens":15,"cache_read_input_tokens":5}}}
```

### tests/fixtures/with-thinking.jsonl

```jsonl
{"type":"assistant","uuid":"a1","parentUuid":"u1","sessionId":"test-session","timestamp":"2025-01-09T10:00:05Z","message":{"model":"claude-3-opus","id":"msg_1","type":"message","role":"assistant","content":[{"type":"thinking","thinking":"Let me analyze this..."},{"type":"text","text":"Here's my answer"}],"stop_reason":"end_turn","stop_sequence":null,"usage":{"input_tokens":30,"output_tokens":25}}}
```

## Test Files

### tests/parser.test.ts

```typescript
import { describe, it, expect } from 'vitest';
import { join } from 'node:path';
import {
  parseSessionFile,
  parseSession,
  parseLine,
  extractSessionId,
} from '../src/index.js';

const FIXTURES = join(__dirname, 'fixtures');

describe('parseLine', () => {
  it('parses valid user entry', () => {
    const line = '{"type":"user","uuid":"u1","parentUuid":null,"sessionId":"s1","timestamp":"2025-01-09T10:00:00Z"}';
    const result = parseLine(line);
    expect(result).not.toBeNull();
    expect(result?.type).toBe('user');
    expect(result?.uuid).toBe('u1');
  });

  it('returns null for invalid JSON', () => {
    expect(parseLine('not json')).toBeNull();
  });

  it('returns null for missing required fields', () => {
    expect(parseLine('{"type":"user"}')).toBeNull();
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
});

describe('parseSession', () => {
  it('returns ParsedSession with aggregates', async () => {
    const session = await parseSession(join(FIXTURES, 'simple-session.jsonl'));
    expect(session.sessionId).toBe('simple-session');
    expect(session.entries).toHaveLength(2);
    expect(session.models.has('claude-3-opus')).toBe(true);
    expect(session.totalUsage.inputTokens).toBe(10);
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
});
```

### tests/extractors.test.ts

```typescript
import { describe, it, expect } from 'vitest';
import { join } from 'node:path';
import {
  parseSessionFile,
  extractToolCalls,
  hasThinkingContent,
  getToolUsageCounts,
} from '../src/index.js';

const FIXTURES = join(__dirname, 'fixtures');

describe('extractToolCalls', () => {
  it('extracts tool names from content', () => {
    const content = [
      { type: 'tool_use' as const, id: '1', name: 'Read', input: {} },
      { type: 'text' as const, text: 'done' },
      { type: 'tool_use' as const, id: '2', name: 'Write', input: {} },
    ];
    expect(extractToolCalls(content)).toEqual(['Read', 'Write']);
  });

  it('returns empty array for no tools', () => {
    const content = [{ type: 'text' as const, text: 'hello' }];
    expect(extractToolCalls(content)).toEqual([]);
  });
});

describe('hasThinkingContent', () => {
  it('detects thinking blocks', () => {
    const content = [
      { type: 'thinking' as const, thinking: 'hmm...' },
      { type: 'text' as const, text: 'answer' },
    ];
    expect(hasThinkingContent(content)).toBe(true);
  });

  it('returns false when no thinking', () => {
    const content = [{ type: 'text' as const, text: 'answer' }];
    expect(hasThinkingContent(content)).toBe(false);
  });
});

describe('getToolUsageCounts', () => {
  it('counts tool usage across entries', async () => {
    const entries = await parseSessionFile(join(FIXTURES, 'with-tools.jsonl'));
    const counts = getToolUsageCounts(entries);
    expect(counts.get('Read')).toBe(1);
  });
});
```

### tests/utils.test.ts

```typescript
import { describe, it, expect } from 'vitest';
import {
  filterAssistantEntries,
  getTotalUsage,
  buildHierarchy,
  getModels,
} from '../src/index.js';
import type { LogEntry } from '../src/index.js';

const mockEntries: LogEntry[] = [
  {
    type: 'user',
    uuid: 'u1',
    parentUuid: null,
    sessionId: 's1',
    timestamp: new Date(),
    toolCalls: [],
    hasThinking: false,
  },
  {
    type: 'assistant',
    uuid: 'a1',
    parentUuid: 'u1',
    sessionId: 's1',
    timestamp: new Date(),
    model: 'claude-3-opus',
    usage: { inputTokens: 10, outputTokens: 5, cacheReadTokens: 0, cacheCreationTokens: 0 },
    toolCalls: ['Read'],
    hasThinking: false,
  },
];

describe('filterAssistantEntries', () => {
  it('filters to assistant entries with usage', () => {
    const result = filterAssistantEntries(mockEntries);
    expect(result).toHaveLength(1);
    expect(result[0].type).toBe('assistant');
  });
});

describe('getTotalUsage', () => {
  it('sums token usage', () => {
    const total = getTotalUsage(mockEntries);
    expect(total.inputTokens).toBe(10);
    expect(total.outputTokens).toBe(5);
  });
});

describe('buildHierarchy', () => {
  it('builds parent-child map', () => {
    const hierarchy = buildHierarchy(mockEntries);
    expect(hierarchy.get('u1')).toEqual(['a1']);
  });
});

describe('getModels', () => {
  it('returns unique models', () => {
    const models = getModels(mockEntries);
    expect(models).toContain('claude-3-opus');
  });
});
```

## Run Tests

```bash
cd claude-code-files-parser
npm test
```

Expected output:
```
 ✓ tests/parser.test.ts (5 tests)
 ✓ tests/extractors.test.ts (4 tests)
 ✓ tests/utils.test.ts (4 tests)

 Test Files  3 passed
 Tests      13 passed
```

## Integration Validation

```bash
cd karma-logger

# Build
npm run build

# Run existing tests
npm test

# Manual smoke test
npm run dev -- status
npm run dev -- watch --help
```

## Smoke Test Checklist

- [ ] `karma status` shows session info
- [ ] `karma watch` starts without errors
- [ ] `karma report` generates output
- [ ] Dashboard loads (if applicable)
- [ ] No TypeScript errors in build

## Outputs

- [ ] Test fixtures created
- [ ] Parser tests pass
- [ ] Extractor tests pass
- [ ] Utility tests pass
- [ ] karma-logger tests pass
- [ ] Manual smoke test passes

## Estimated Effort

~40 minutes

## Post-Completion

After all phases complete:

1. Update `v0.md` status to "Completed"
2. Consider publishing to npm
3. Update karma-logger README if needed
4. Archive phase files or move to `docs/`
