# Phase 6: Cache Persistence - Subphases

**Status:** **DONE**
**Overall Complexity:** High
**Parallelization Strategy:** 6.1 + 6.2 parallel, then 6.3, then 6.4

## Dependency Graph

```
Phase 6.1 (WAL) ─────┐
                     ├──▶ Phase 6.3 (Recovery) ──▶ Phase 6.4 (Integration)
Phase 6.2 (Snapshot) ┘
```

---

## Phase 6.1: Write-Ahead Log (WAL)

**Status:** **DONE**
**Complexity:** Medium
**Can parallelize with:** Phase 6.2

### Goal
Append-only log that records every cache mutation for durability.

### Implementation

```typescript
// src/walkie-talkie/wal.ts

interface WALEntry {
  ts: number;           // Unix timestamp ms
  op: 'set' | 'del';    // Operation type
  key: string;          // Cache key
  value?: unknown;      // Value (for 'set')
  ttl?: number;         // TTL in ms (for 'set')
}

class WriteAheadLog {
  constructor(walPath: string, options?: { fsync?: boolean });

  append(entry: WALEntry): Promise<void>;
  readAll(): AsyncGenerator<WALEntry>;
  truncate(): Promise<void>;
  close(): Promise<void>;
}
```

### Files
- `src/walkie-talkie/wal.ts` (new)
- `tests/walkie-talkie/wal.test.ts` (new)

### Test Cases
- Appends entries to file
- Reads entries back in order
- Handles corrupted entries gracefully
- Truncates file correctly
- Handles concurrent appends

---

## Phase 6.2: Snapshot Mechanism

**Status:** **DONE**
**Complexity:** Medium
**Can parallelize with:** Phase 6.1

### Goal
Periodic full dumps of cache state for faster recovery.

### Implementation

```typescript
// src/walkie-talkie/snapshot.ts

interface SnapshotMeta {
  createdAt: number;    // Unix timestamp ms
  keyCount: number;     // Number of keys
  walOffset: number;    // WAL position at snapshot time
}

class SnapshotManager {
  constructor(snapshotPath: string, metaPath: string);

  save(data: Map<string, { value: unknown; expiresAt: number | null }>): Promise<SnapshotMeta>;
  load(): Promise<{ data: Map<string, unknown>; meta: SnapshotMeta } | null>;
  exists(): boolean;
}
```

### Files
- `src/walkie-talkie/snapshot.ts` (new)
- `tests/walkie-talkie/snapshot.test.ts` (new)

### Test Cases
- Saves snapshot atomically (temp file + rename)
- Loads snapshot correctly
- Handles missing/corrupted snapshot
- Preserves TTL information

---

## Phase 6.3: Recovery Logic

**Status:** **DONE**
**Complexity:** Medium
**Depends on:** Phase 6.1, Phase 6.2

### Goal
Restore cache state from snapshot + WAL replay on startup.

### Implementation

```typescript
// src/walkie-talkie/persistent-cache.ts

class PersistentCacheStore extends MemoryCacheStore {
  constructor(options: {
    walPath: string;
    snapshotPath: string;
    snapshotInterval?: number;  // ms, default 60000
    fsync?: boolean;            // default false
  });

  async restore(): Promise<{ keysRestored: number; walEntriesReplayed: number }>;
  async snapshot(): Promise<void>;

  // Override set/delete to append to WAL
  set(key: string, value: unknown, ttl?: number): void;
  delete(key: string): boolean;
}
```

### Recovery Algorithm
1. Load snapshot if exists
2. Replay WAL entries after snapshot timestamp
3. Recalculate TTLs based on elapsed time
4. Start periodic snapshot timer

### Files
- `src/walkie-talkie/persistent-cache.ts` (new)
- `tests/walkie-talkie/persistent-cache.test.ts` (new)

### Test Cases
- Restores from snapshot only
- Restores from WAL only
- Restores from snapshot + WAL
- Handles TTL expiration on restore
- Handles corrupted WAL entries
- Periodic snapshot works

---

## Phase 6.4: Integration

**Status:** **DONE**
**Complexity:** Low
**Depends on:** Phase 6.3

### Goal
Wire PersistentCacheStore into aggregator and CLI.

### Implementation

```typescript
// In aggregator.ts
if (options.enableRadio && options.persistRadio) {
  this.cache = new PersistentCacheStore({
    walPath: path.join(os.homedir(), '.karma', 'radio', 'wal.log'),
    snapshotPath: path.join(os.homedir(), '.karma', 'radio', 'snapshot.json'),
  });
  await this.cache.restore();
}

// In watch.ts CLI
.option('--persist-radio', 'Enable radio cache persistence')
```

### Graceful Shutdown
```typescript
process.on('SIGTERM', async () => {
  if (cache instanceof PersistentCacheStore) {
    await cache.snapshot();
  }
  process.exit(0);
});
```

### Files
- `src/aggregator.ts` (modify)
- `src/commands/watch.ts` (modify)
- `src/walkie-talkie/index.ts` (export)

### Test Cases
- Aggregator uses persistent cache when flag set
- CLI flag works
- Graceful shutdown creates snapshot

---

## Acceptance Criteria (Full Phase 6)

- [x] WAL appends all cache mutations
- [x] Snapshot saves periodically
- [x] Cache survives process restart
- [x] TTL honored after restore
- [x] Corrupted data handled gracefully
- [x] `--persist-radio` flag works
- [x] Minimal performance impact (<5ms write overhead)

## Test Results

- **WAL tests:** 33 tests passing
- **Snapshot tests:** 26 tests passing
- **Persistent Cache tests:** 37 tests passing
- **Total walkie-talkie tests:** 313 tests passing across 9 test files
