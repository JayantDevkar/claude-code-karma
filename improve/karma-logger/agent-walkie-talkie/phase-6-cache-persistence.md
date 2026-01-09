# Phase 6: Cache Persistence

**Priority:** Future
**Complexity:** High
**Estimated Files:** 3-4

## Problem Statement

From known limitations: "No persistence; cache clears on restart."

Long-running sessions lose agent state when:
- Dashboard restarts
- System reboots
- Process crashes

## Goal

Persist cache to disk for crash recovery and session continuity.

## Implementation

### 1. Persistence Strategy

Append-only log (WAL) for durability + periodic snapshots:

```
~/.karma/radio/
├── wal.log           # Append-only write log
├── snapshot.json     # Periodic full snapshot
└── snapshot.meta     # Snapshot metadata
```

### 2. WAL Format

```json
{"ts":1704700800000,"op":"set","key":"agent:a1:status","value":{...},"ttl":300000}
{"ts":1704700801000,"op":"del","key":"agent:a1:progress"}
{"ts":1704700802000,"op":"set","key":"agent:a2:status","value":{...},"ttl":300000}
```

### 3. PersistentCacheStore

Extend `MemoryCacheStore`:

```typescript
class PersistentCacheStore extends MemoryCacheStore {
  private wal: WriteStream;
  private snapshotInterval: NodeJS.Timer;

  constructor(options: {
    walPath: string;
    snapshotPath: string;
    snapshotInterval?: number; // default 60s
  });

  // Override set/delete to append to WAL
  set(key: string, value: unknown, ttl?: number): void {
    super.set(key, value, ttl);
    this.appendWAL({ op: 'set', key, value, ttl });
  }

  // Restore from snapshot + replay WAL
  async restore(): Promise<void>;

  // Create snapshot and truncate WAL
  async snapshot(): Promise<void>;
}
```

### 4. Startup Recovery

```typescript
// In aggregator initialization
if (options.enableRadio && options.persistRadio) {
  const cache = new PersistentCacheStore({ ... });
  await cache.restore(); // Restore previous state
}
```

### 5. Graceful Shutdown

```typescript
process.on('SIGTERM', async () => {
  await cache.snapshot(); // Final snapshot before exit
  process.exit(0);
});
```

## Files to Create/Modify

| File | Change |
|------|--------|
| `src/walkie-talkie/persistent-cache.ts` | New file |
| `src/walkie-talkie/types.ts` | Add persistence options |
| `src/aggregator.ts` | Use persistent cache when enabled |
| `src/commands/watch.ts` | Add `--persist-radio` flag |

## Data Integrity

- WAL is fsync'd after each write (configurable)
- Snapshot is atomic (write temp, rename)
- Corrupted WAL entries are skipped with warning
- TTL is recalculated on restore based on elapsed time

## Test Cases

```typescript
describe('PersistentCacheStore', () => {
  it('restores from snapshot');
  it('replays WAL after snapshot');
  it('handles corrupted WAL entries');
  it('expires TTL on restore');
  it('creates snapshot and truncates WAL');
  it('handles concurrent writes during snapshot');
});
```

## Acceptance Criteria

- [ ] Cache survives process restart
- [ ] TTL is honored after restore
- [ ] WAL is truncated after snapshot
- [ ] Graceful handling of corrupt data
- [ ] `--persist-radio` flag enables persistence
- [ ] Minimal impact on write performance (<5ms overhead)

## Performance Considerations

- WAL append is async with configurable fsync
- Snapshot runs in background thread
- Memory usage: 2x during snapshot (old + new)

## Dependencies

- Requires write access to `~/.karma/radio/`
- Node.js fs promises API

## Rollback

Disable with `--no-persist-radio`. Delete persistence files to start fresh.
