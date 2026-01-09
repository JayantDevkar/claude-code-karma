# Phase 5: Extract Utilities

**Status**: Pending
**Depends on**: Phase 2
**Parallel with**: Phase 3, Phase 4
**Unlocks**: Phase 6

## Objective

Extract utility functions for session analysis and hierarchy building.

## Tasks

- [ ] Create `src/utils.ts`
- [ ] Update `src/index.ts` exports
- [ ] Verify build

## Source Mapping

From `karma-logger/src/parser.ts`:

| Function | Description |
|----------|-------------|
| `filterAssistantEntries()` | Filter to assistant messages with usage |
| `getTotalUsage()` | Sum token usage across entries |
| `buildHierarchy()` | Build parent-child UUID map |
| `getModels()` | Get unique models from entries |

Note: `extractSessionId()` is in `parser.ts` (Phase 3)

## Files to Create

### src/utils.ts

```typescript
/**
 * Utility functions for Claude Code session analysis
 */

import type { LogEntry, TokenUsage } from './types/index.js';
import { emptyUsage, addUsage } from './normalize.js';

/**
 * Filter entries to only assistant messages with usage data
 */
export function filterAssistantEntries(entries: LogEntry[]): LogEntry[] {
  return entries.filter(e => e.type === 'assistant' && e.usage);
}

/**
 * Get total token usage from entries
 */
export function getTotalUsage(entries: LogEntry[]): TokenUsage {
  return entries.reduce(
    (acc, entry) => entry.usage ? addUsage(acc, entry.usage) : acc,
    emptyUsage()
  );
}

/**
 * Build a parent-child hierarchy map from entries
 * Returns Map<parentUuid, childUuids[]>
 */
export function buildHierarchy(entries: LogEntry[]): Map<string, string[]> {
  const children = new Map<string, string[]>();

  for (const entry of entries) {
    if (entry.parentUuid) {
      const existing = children.get(entry.parentUuid) ?? [];
      existing.push(entry.uuid);
      children.set(entry.parentUuid, existing);
    }
  }

  return children;
}

/**
 * Get unique models used in entries
 */
export function getModels(entries: LogEntry[]): string[] {
  const models = new Set<string>();
  for (const entry of entries) {
    if (entry.model) {
      models.add(entry.model);
    }
  }
  return Array.from(models);
}

/**
 * Get session duration in milliseconds
 */
export function getSessionDuration(entries: LogEntry[]): number {
  if (entries.length < 2) return 0;
  const start = entries[0].timestamp.getTime();
  const end = entries[entries.length - 1].timestamp.getTime();
  return end - start;
}

/**
 * Get entries within a time range
 */
export function filterByTimeRange(
  entries: LogEntry[],
  start: Date,
  end: Date
): LogEntry[] {
  const startTime = start.getTime();
  const endTime = end.getTime();
  return entries.filter(e => {
    const time = e.timestamp.getTime();
    return time >= startTime && time <= endTime;
  });
}

/**
 * Group entries by session ID
 */
export function groupBySession(entries: LogEntry[]): Map<string, LogEntry[]> {
  const sessions = new Map<string, LogEntry[]>();

  for (const entry of entries) {
    const existing = sessions.get(entry.sessionId) ?? [];
    existing.push(entry);
    sessions.set(entry.sessionId, existing);
  }

  return sessions;
}

/**
 * Find root entries (entries with no parent)
 */
export function findRootEntries(entries: LogEntry[]): LogEntry[] {
  return entries.filter(e => e.parentUuid === null);
}

/**
 * Get entry by UUID
 */
export function findEntryByUuid(entries: LogEntry[], uuid: string): LogEntry | undefined {
  return entries.find(e => e.uuid === uuid);
}
```

### Update src/index.ts

Add to exports:

```typescript
// Utilities
export {
  filterAssistantEntries,
  getTotalUsage,
  buildHierarchy,
  getModels,
  getSessionDuration,
  filterByTimeRange,
  groupBySession,
  findRootEntries,
  findEntryByUuid,
} from './utils.js';
```

## Bonus Utilities Added

Beyond the original functions, added these useful utilities:

| Function | Purpose |
|----------|---------|
| `getSessionDuration()` | Calculate session length in ms |
| `filterByTimeRange()` | Filter entries by time window |
| `groupBySession()` | Group entries by session ID |
| `findRootEntries()` | Find conversation root entries |
| `findEntryByUuid()` | Lookup entry by UUID |

## Validation

```bash
npm run build
# All utility functions should be importable
```

## Outputs

- [ ] `src/utils.ts` created
- [ ] All functions exported from `index.ts`
- [ ] Build passes

## Estimated Effort

~20 minutes
