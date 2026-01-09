# Phase 2: Extract Types

**Status**: Pending
**Depends on**: Phase 1
**Unlocks**: Phase 3, Phase 4, Phase 5 (parallel)

## Objective

Extract Claude Code format types from `karma-logger/src/types.ts` into the new package.

## Tasks

- [ ] Create `src/types/raw.ts` - Types as found in JSONL files
- [ ] Create `src/types/normalized.ts` - Internal normalized types
- [ ] Create `src/types/index.ts` - Re-export all types
- [ ] Update `src/index.ts` to export types
- [ ] Verify build

## Source Analysis

From `karma-logger/src/types.ts`, extract these types:

### To `types/raw.ts` (lines 1-86)

```typescript
// Raw types - exactly as found in Claude Code JSONL files
- RawTokenUsage
- ThinkingBlock
- ToolUseBlock
- TextBlock
- ContentBlock (union)
- UserMessage
- AssistantMessage
- RawLogEntry
```

### To `types/normalized.ts` (lines 88-128)

```typescript
// Normalized types - for internal use after parsing
- TokenUsage
- LogEntry
- ParsedSession
```

### Keep in karma-logger (lines 130+)

```typescript
// karma-logger specific - DO NOT extract
- SessionMetrics
- CostConfig
- DEFAULT_COST_CONFIG
- CommandContext
- ActivityEntry
- ProjectSummary
- ProjectDetail
- DailyMetric
```

## Files to Create

### src/types/raw.ts

```typescript
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
```

### src/types/normalized.ts

```typescript
/**
 * Normalized types for internal use after parsing
 * These are the cleaned-up versions used by consumers
 */

export interface TokenUsage {
  inputTokens: number;
  outputTokens: number;
  cacheReadTokens: number;
  cacheCreationTokens: number;
}

export interface LogEntry {
  type: 'user' | 'assistant';
  uuid: string;
  parentUuid: string | null;
  sessionId: string;
  timestamp: Date;
  model?: string;
  usage?: TokenUsage;
  toolCalls: string[];
  hasThinking: boolean;
}

export interface ParsedSession {
  sessionId: string;
  projectPath: string;
  entries: LogEntry[];
  startTime: Date;
  endTime: Date;
  models: Set<string>;
  totalUsage: TokenUsage;
}
```

### src/types/index.ts

```typescript
// Raw types (as found in JSONL)
export type {
  RawTokenUsage,
  ThinkingBlock,
  ToolUseBlock,
  TextBlock,
  ContentBlock,
  UserMessage,
  AssistantMessage,
  RawLogEntry,
} from './raw.js';

// Normalized types (after parsing)
export type {
  TokenUsage,
  LogEntry,
  ParsedSession,
} from './normalized.js';
```

### Update src/index.ts

```typescript
export const VERSION = '0.1.0';

// Types
export type {
  // Raw
  RawTokenUsage,
  ThinkingBlock,
  ToolUseBlock,
  TextBlock,
  ContentBlock,
  UserMessage,
  AssistantMessage,
  RawLogEntry,
  // Normalized
  TokenUsage,
  LogEntry,
  ParsedSession,
} from './types/index.js';
```

## Validation

```bash
npm run build
# Verify dist/types/*.d.ts files are generated
# Verify no TypeScript errors
```

## Outputs

- [ ] `src/types/raw.ts` created
- [ ] `src/types/normalized.ts` created
- [ ] `src/types/index.ts` created
- [ ] Types exported from main `index.ts`
- [ ] Build passes

## Estimated Effort

~20 minutes
