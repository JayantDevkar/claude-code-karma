# Phase 3: Extract Parser Core

**Status**: Pending
**Depends on**: Phase 2
**Parallel with**: Phase 4, Phase 5
**Unlocks**: Phase 6

## Objective

Extract the core streaming JSONL parser and normalization functions.

## Tasks

- [ ] Create `src/parser.ts` - Streaming JSONL parser
- [ ] Create `src/normalize.ts` - Entry normalization
- [ ] Create `src/guards.ts` - Type guard functions
- [ ] Update `src/index.ts` exports
- [ ] Verify build

## Source Mapping

From `karma-logger/src/parser.ts`:

| Function | Target File |
|----------|-------------|
| `isValidEntry()` | `guards.ts` |
| `isAssistantMessage()` | `guards.ts` |
| `normalizeUsage()` | `normalize.ts` |
| `normalizeEntry()` | `normalize.ts` |
| `parseLine()` | `parser.ts` |
| `parseSessionFile()` | `parser.ts` |
| `parseSession()` | `parser.ts` |
| `emptyUsage()` | `normalize.ts` |
| `addUsage()` | `normalize.ts` |

## Files to Create

### src/guards.ts

```typescript
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
```

### src/normalize.ts

```typescript
/**
 * Normalization functions for Claude Code log entries
 */

import type {
  RawLogEntry,
  AssistantMessage,
  TokenUsage,
  LogEntry,
  ContentBlock,
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
```

### src/parser.ts

```typescript
/**
 * Streaming JSONL parser for Claude Code session logs
 */

import { createReadStream } from 'node:fs';
import { createInterface } from 'node:readline';
import { basename } from 'node:path';

import type { RawLogEntry, LogEntry, ParsedSession } from './types/index.js';
import { isValidEntry } from './guards.js';
import { normalizeEntry, emptyUsage, addUsage } from './normalize.js';

/**
 * Parse a single JSONL line safely
 */
export function parseLine(line: string): RawLogEntry | null {
  try {
    const parsed = JSON.parse(line);
    if (isValidEntry(parsed)) {
      return parsed;
    }
    return null;
  } catch {
    return null;
  }
}

/**
 * Extract session ID from file path
 * Files are named like: 0074cde8-b763-45ee-be32-cfc80f965b4d.jsonl
 */
export function extractSessionId(filePath: string): string {
  const filename = basename(filePath, '.jsonl');
  const uuidPattern = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
  if (uuidPattern.test(filename)) {
    return filename;
  }
  return filename;
}

/**
 * Parse a JSONL session file and return normalized entries
 * Uses streaming to handle large files efficiently
 */
export async function parseSessionFile(filePath: string): Promise<LogEntry[]> {
  const entries: LogEntry[] = [];

  const rl = createInterface({
    input: createReadStream(filePath),
    crlfDelay: Infinity,
  });

  for await (const line of rl) {
    const raw = parseLine(line);
    if (raw) {
      entries.push(normalizeEntry(raw));
    }
  }

  return entries;
}

/**
 * Parse a session file and return a complete ParsedSession
 */
export async function parseSession(filePath: string): Promise<ParsedSession> {
  const entries = await parseSessionFile(filePath);
  const sessionId = extractSessionId(filePath);

  const projectPath = '';
  const models = new Set<string>();
  let totalUsage = emptyUsage();
  let startTime = new Date();
  let endTime = new Date();

  for (const entry of entries) {
    if (entry.model) {
      models.add(entry.model);
    }
    if (entry.usage) {
      totalUsage = addUsage(totalUsage, entry.usage);
    }
  }

  if (entries.length > 0) {
    startTime = entries[0].timestamp;
    endTime = entries[entries.length - 1].timestamp;
  }

  return {
    sessionId,
    projectPath,
    entries,
    startTime,
    endTime,
    models,
    totalUsage,
  };
}
```

### Update src/index.ts

Add to exports:

```typescript
// Parser
export { parseLine, parseSessionFile, parseSession, extractSessionId } from './parser.js';

// Normalization
export { normalizeEntry, normalizeUsage, emptyUsage, addUsage } from './normalize.js';

// Type guards
export { isValidEntry, isAssistantMessage } from './guards.js';
```

## Dependency Note

This phase depends on `extractors/` being available (Phase 4).

**Option A**: Implement Phase 4 first
**Option B**: Inline `extractToolCalls` and `hasThinkingContent` temporarily, refactor in Phase 4

Recommend **Option A** - complete Phase 4 first or in parallel.

## Validation

```bash
npm run build
# Test with a sample JSONL file
```

## Outputs

- [ ] `src/parser.ts` created
- [ ] `src/normalize.ts` created
- [ ] `src/guards.ts` created
- [ ] All functions exported from `index.ts`
- [ ] Build passes

## Estimated Effort

~30 minutes
