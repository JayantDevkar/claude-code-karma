# Phase 1: JSONL Parser

**Status:** Complete
**Estimated Effort:** Medium
**Dependencies:** Phase 0
**Deliverable:** Streaming parser that extracts metrics from Claude Code logs

---

## Objective

Build a robust JSONL parser that can read Claude Code session files and extract token usage, model info, and agent hierarchy data.

---

## Tasks

### 1.1 Define Data Types
```typescript
// src/types.ts additions
interface LogEntry {
  type: 'user' | 'assistant' | 'system';
  timestamp: string;
  uuid: string;
  parentUuid?: string;
  model?: string;
  usage?: TokenUsage;
  message?: MessageContent;
}

interface TokenUsage {
  input_tokens: number;
  output_tokens: number;
  cache_read_input_tokens?: number;
  cache_creation_input_tokens?: number;
}

interface ParsedSession {
  sessionId: string;
  projectPath: string;
  entries: LogEntry[];
  agents: Map<string, AgentInfo>;
}
```

### 1.2 Implement Core Parser
- [ ] Create `src/parser.ts`
- [ ] Use `readline` for streaming
- [ ] Handle malformed JSON gracefully
- [ ] Extract agent ID from file path

### 1.3 Build Entry Processor
- [ ] Filter for assistant messages with usage
- [ ] Extract model identifier
- [ ] Parse parentUuid for hierarchy
- [ ] Accumulate tool usage

### 1.4 Create Test Fixtures
- [ ] Copy sample JSONL from `~/.claude/projects/`
- [ ] Create `tests/fixtures/` with anonymized data
- [ ] Include edge cases: malformed, empty, large

### 1.5 Write Unit Tests
- [ ] Test: Parse valid entry
- [ ] Test: Handle malformed JSON
- [ ] Test: Extract token counts correctly
- [ ] Test: Build agent hierarchy

---

## Key Code

```typescript
// src/parser.ts
export async function parseSessionFile(
  filePath: string
): Promise<LogEntry[]> {
  const entries: LogEntry[] = [];
  const rl = readline.createInterface({
    input: fs.createReadStream(filePath),
    crlfDelay: Infinity,
  });

  for await (const line of rl) {
    try {
      const entry = JSON.parse(line);
      if (isValidEntry(entry)) {
        entries.push(normalizeEntry(entry));
      }
    } catch {
      // Skip malformed lines
    }
  }
  return entries;
}
```

---

## Acceptance Criteria

1. Parser extracts all token usage from sample file
2. Malformed lines don't crash the parser
3. Agent hierarchy correctly reconstructed
4. Tests pass with 100% coverage on parser module

---

## Exit Condition

Phase complete when `parseSessionFile()` returns accurate data for 3+ real Claude Code session files.
