# Phase 1: Core Cache (CacheStore)

## Objective

Build an in-memory key:value store with TTL and pub/sub. Foundation for all agent communication.

## Deliverables

```
src/walkie-talkie/
├── cache-store.ts       # MemoryCacheStore class
├── types.ts             # CacheStore interface, key schemas
└── index.ts             # Re-export CacheStore

tests/walkie-talkie/
└── cache-store.test.ts  # Full test coverage
```

## Tasks

### 1.1 Define Types (`types.ts`)

```typescript
interface CacheStore {
  set(key: string, value: unknown, ttlMs?: number): void;
  get<T>(key: string): T | null;
  delete(key: string): boolean;
  keys(pattern: string): string[];
  getMany(pattern: string): Map<string, unknown>;
  subscribe(pattern: string, cb: (key: string, value: unknown) => void): () => void;
  publish(key: string, value: unknown): void;
  clear(): void;
  stats(): CacheStats;
  destroy(): void;  // Cleanup intervals and subscriptions
}

interface CacheStats {
  keys: number;
  subscribers: number;
  memoryBytes: number;
}
```

### 1.2 Implement MemoryCacheStore (`cache-store.ts`)

| Method | Complexity | Notes |
|--------|------------|-------|
| `set()` | O(1) | Store value with expiry timestamp |
| `get()` | O(1) | Return null if expired |
| `delete()` | O(1) | Remove key |
| `keys()` | O(n) | Glob pattern → RegExp |
| `getMany()` | O(n) | Batch retrieval |
| `subscribe()` | O(1) | Add callback to pattern map |
| `publish()` | O(m) | Notify m matching subscribers |

**Internal Structure:**
```typescript
private store: Map<string, { value: unknown; expiresAt: number }>;
private subscribers: Map<string, Set<Callback>>;
private cleanupInterval: NodeJS.Timeout;
// destroy() clears cleanupInterval and removes all subscribers
```

### 1.3 Pattern Matching

Convert glob patterns to RegExp:
- `*` → `.*`
- `agent:*:status` matches `agent:abc:status`
- Escape special chars: `.+^${}()|[]\`

### 1.4 TTL & Eviction

- `ttlMs = undefined` → default TTL (5 min / 300,000ms)
- `ttlMs = -1` → infinite (never expires)
- `ttlMs = 0` → expire immediately (edge case)
- Cleanup interval: 5 seconds
- Eviction: Lazy (on get) + periodic sweep

### 1.5 Write Tests (`cache-store.test.ts`)

```typescript
describe('MemoryCacheStore', () => {
  describe('basic operations', () => {
    test('set and get value');
    test('return null for missing key');
    test('delete existing key');
    test('delete returns false for missing key');
  });

  describe('TTL', () => {
    test('value expires after TTL');
    test('ttlMs=-1 creates non-expiring entry');
    test('periodic eviction runs');
  });

  describe('pattern matching', () => {
    test('keys() with wildcard');
    test('getMany() returns matching entries');
    test('complex patterns: agent:*:status');
  });

  describe('pub/sub', () => {
    test('subscriber notified on set');
    test('pattern subscription matches');
    test('unsubscribe stops notifications');
    test('multiple subscribers same pattern');
    test('subscriber callback throws error - other subscribers still called');
  });

  describe('stats', () => {
    test('reports key count');
    test('reports subscriber count');
  });

  describe('cleanup', () => {
    test('destroy() cleans up intervals');
  });
});
```

## Acceptance Criteria

- [ ] All CRUD operations work correctly
- [ ] TTL expiration tested with fake timers
- [ ] Glob patterns match expected keys
- [ ] Pub/sub delivers to matching subscribers
- [ ] `destroy()` cleans up intervals
- [ ] No memory leaks in subscriber cleanup
- [ ] p99 latency <1ms for set/get/delete (excluding pattern operations)
  - Note: `keys()`, `getMany()`, `publish()` are O(n) and may exceed 1ms with many keys

## Edge Cases

| Case | Handling |
|------|----------|
| Set same key twice | Overwrite, reset TTL |
| Get expired key | Return null, delete lazily |
| Subscribe empty pattern | Match all keys |
| Publish without subscribers | No-op |
| Destroy while callbacks pending | Cancel all |
| Subscriber throws error | Catch, log, continue other subscribers |

## Dependencies

- None (pure TypeScript)

## Estimated Complexity

- Lines of code: ~150
- Test lines: ~200
- Risk: Low (isolated, well-defined)
