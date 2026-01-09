# Phase 6: Update karma-logger

**Status**: Pending
**Depends on**: Phase 3, Phase 4, Phase 5
**Unlocks**: Phase 7

## Objective

Update karma-logger to import from `claude-code-files-parser` instead of local parser.

## Tasks

- [ ] Add workspace dependency
- [ ] Update imports in all affected files
- [ ] Remove/slim down `parser.ts`
- [ ] Clean up `types.ts`
- [ ] Verify build and tests

## Workspace Setup

### Option A: npm workspaces (recommended)

Add to root `package.json`:

```json
{
  "workspaces": [
    "karma-logger",
    "claude-code-files-parser"
  ]
}
```

Then in `karma-logger/package.json`:

```json
{
  "dependencies": {
    "claude-code-files-parser": "*"
  }
}
```

### Option B: npm link (for development)

```bash
cd claude-code-files-parser && npm link
cd ../karma-logger && npm link claude-code-files-parser
```

## Files to Update

### 1. karma-logger/src/aggregator.ts

**Before:**
```typescript
import { parseSessionFile, normalizeEntry } from './parser.js';
import type { LogEntry, TokenUsage } from './types.js';
```

**After:**
```typescript
import {
  parseSessionFile,
  normalizeEntry,
  extractAgentSpawns,
  type LogEntry,
  type TokenUsage,
  type AgentSpawnInfo,
} from 'claude-code-files-parser';
```

### 2. karma-logger/src/watcher.ts

**Before:**
```typescript
import { parseSessionFile } from './parser.js';
import type { LogEntry } from './types.js';
```

**After:**
```typescript
import { parseSessionFile, type LogEntry } from 'claude-code-files-parser';
```

### 3. karma-logger/src/db.ts

**Before:**
```typescript
import type { TokenUsage } from './types.js';
```

**After:**
```typescript
import type { TokenUsage } from 'claude-code-files-parser';
// Keep karma-logger-specific types from local types.ts
import type { SessionMetrics } from './types.js';
```

### 4. karma-logger/src/walkie-talkie/subagent-watcher.ts

Check for parser imports and update similarly.

### 5. karma-logger/src/commands/*.ts

Check all command files for parser/type imports.

## Files to Modify

### karma-logger/src/parser.ts

**Option A**: Delete entirely (if all functions extracted)

**Option B**: Keep as re-export facade

```typescript
/**
 * Re-exports from claude-code-files-parser
 * @deprecated Import directly from 'claude-code-files-parser'
 */
export * from 'claude-code-files-parser';
```

Recommend **Option A** - clean break.

### karma-logger/src/types.ts

Remove extracted types, keep karma-logger-specific:

```typescript
/**
 * karma-logger specific types
 * Core parsing types are in 'claude-code-files-parser'
 */

// Re-export parsing types for convenience
export type {
  TokenUsage,
  LogEntry,
  ParsedSession,
  RawLogEntry,
  ContentBlock,
} from 'claude-code-files-parser';

// karma-logger specific types below
export interface SessionMetrics {
  // ... keep as-is
}

export interface CostConfig {
  // ... keep as-is
}

// ... rest of karma-logger types
```

## Import Update Checklist

Run this to find all files needing updates:

```bash
cd karma-logger
grep -r "from './parser" src/
grep -r "from './types" src/
```

| File | Needs Update |
|------|--------------|
| `src/aggregator.ts` | Yes |
| `src/watcher.ts` | Yes |
| `src/db.ts` | Maybe |
| `src/converters.ts` | Maybe |
| `src/commands/watch.ts` | Check |
| `src/commands/report.ts` | Check |
| `src/walkie-talkie/*.ts` | Check |
| `src/tui/hooks/*.ts` | Check |

## Validation

```bash
cd karma-logger

# Install workspace deps
npm install

# Build
npm run build

# Run tests
npm test

# Manual test
npm run dev -- watch
```

## Rollback Plan

If issues arise:
1. Revert `package.json` changes
2. Keep local `parser.ts` and `types.ts`
3. Debug specific import issues

## Outputs

- [ ] Workspace/link configured
- [ ] All imports updated
- [ ] `parser.ts` removed or converted to re-exports
- [ ] `types.ts` cleaned up
- [ ] karma-logger builds
- [ ] karma-logger tests pass

## Estimated Effort

~45 minutes
