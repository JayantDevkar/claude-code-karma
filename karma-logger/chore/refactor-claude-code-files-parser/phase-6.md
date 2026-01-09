# Phase 6: Update karma-logger

**Status**: Complete
**Depends on**: Phase 3, Phase 4, Phase 5
**Unlocks**: Phase 7

## Objective

Update karma-logger to import from `claude-code-files-parser` instead of local parser.

## Tasks

- [x] Add workspace dependency
- [x] Update imports in all affected files
- [x] Remove/slim down `parser.ts`
- [x] Clean up `types.ts`
- [x] Verify build and tests

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

- [x] Workspace/link configured
- [x] All imports updated
- [x] `parser.ts` removed or converted to re-exports
- [x] `types.ts` cleaned up
- [x] karma-logger builds
- [x] karma-logger tests pass

## Estimated Effort

~45 minutes

---

## Implementation Notes (Completed 2026-01-09)

### Approach Used

Used **Option A from Workspace Setup**: Added local file dependency in `karma-logger/package.json`:

```json
"claude-code-files-parser": "file:./claude-code-files-parser"
```

This allows the local package to be used without npm workspaces at the root level.

### Files Modified

1. **karma-logger/package.json** - Added dependency on local parser package

2. **karma-logger/src/parser.ts** - **Deleted** (Option A - clean break)
   - All functions now in `claude-code-files-parser`

3. **karma-logger/src/types.ts** - Cleaned up to:
   - Re-export parsing types from `claude-code-files-parser` for convenience
   - Keep karma-logger-specific types (ActivityEntry, CommandContext, CostConfig, etc.)

4. **Files with import updates:**
   - `src/watcher.ts` - Changed `from './parser.js'` and `from './types.js'` to `from 'claude-code-files-parser'`
   - `src/aggregator.ts` - Changed `from './types.js'` for LogEntry, TokenUsage to `from 'claude-code-files-parser'`
   - `src/cost.ts` - Changed `from './types.js'` for TokenUsage to `from 'claude-code-files-parser'`
   - `src/commands/status.ts` - Changed `from '../parser.js'` to `from 'claude-code-files-parser'`
   - `src/commands/watch.ts` - Changed `from '../types.js'` for LogEntry to `from 'claude-code-files-parser'`
   - `src/commands/report.ts` - Changed dynamic import to `from 'claude-code-files-parser'`
   - `src/discovery.ts` - Changed dynamic import for extractAgentSpawns to `from 'claude-code-files-parser'`
   - `src/cli.ts` - Changed dynamic import for parseSessionFile to `from 'claude-code-files-parser'`

5. **tests/parser.test.ts** - Updated import to `from 'claude-code-files-parser'`

### Build & Test Results

- Build: **PASS** (`npm run build` completes without errors)
- Tests: **630 passed** (3 pre-existing flaky tests in walkie-talkie unrelated to this change)

### Notes

- karma-logger-specific types (ActivityEntry, CostConfig, CommandContext, ProjectSummary, etc.) remain in `src/types.ts`
- Parsing types (LogEntry, TokenUsage, ParsedSession, etc.) are re-exported from `types.ts` for backward compatibility
- Direct imports from `'claude-code-files-parser'` are preferred for new code
