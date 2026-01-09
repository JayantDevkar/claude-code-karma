# Agent Walkie-Talkie

Fast key-value cache communication layer for real-time agent coordination in Claude Code sessions.

## Overview

Walkie-Talkie enables agents to communicate status, progress, and messages without relying on bash/tail polling or context-heavy log parsing. It provides:

- **Real-time status tracking** - Know when agents start, complete, or fail
- **Parent-child awareness** - Agents know their hierarchy and can coordinate
- **Inter-agent messaging** - Direct communication between agents
- **Progress reporting** - Granular progress updates for long-running tasks
- **Zero-polling architecture** - Pub/sub notifications eliminate polling loops
- **Optional persistence** - Cache survives process restarts with WAL + snapshots

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                        Dashboard UI                              │
│                    (SSE: agent:status, agent:progress)           │
└─────────────────────────────────────────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────┐
│                      MetricsAggregator                           │
│                  (manages AgentRadio instances)                  │
└─────────────────────────────────────────────────────────────────┘
           │                                    │
           ▼                                    ▼
┌──────────────────────┐           ┌──────────────────────┐
│     AgentRadio       │           │    SocketServer      │
│   (high-level API)   │           │  (Unix domain IPC)   │
└──────────────────────┘           └──────────────────────┘
           │                                    │
           ▼                                    ▼
┌─────────────────────────────────────────────────────────────────┐
│                    CacheStore (interface)                        │
│          ┌─────────────────┬─────────────────────────┐          │
│          │ MemoryCacheStore│  PersistentCacheStore   │          │
│          │   (in-memory)   │   (WAL + Snapshots)     │          │
│          └─────────────────┴─────────────────────────┘          │
└─────────────────────────────────────────────────────────────────┘
                                │
                                ▼
┌──────────────────────┐           ┌──────────────────────┐
│   CLI (karma radio)  │◀─────────▶│    Claude Hooks      │
│    via SocketClient  │           │   (PreToolUse, etc)  │
└──────────────────────┘           └──────────────────────┘
```

## Components

### CacheStore (`cache-store.ts`)

In-memory key-value store with TTL, pattern matching, and pub/sub.

```typescript
import { MemoryCacheStore } from './walkie-talkie/cache-store.js';

const cache = new MemoryCacheStore();

// Basic operations
cache.set('agent:a1:status', { state: 'active' }, 300000); // 5min TTL
cache.get<AgentStatus>('agent:a1:status');
cache.delete('agent:a1:status');

// Pattern matching (* matches chars except colon)
cache.keys('agent:*:status');     // All agent statuses
cache.getMany('agent:*:progress'); // All progress updates

// Pub/sub
const unsubscribe = cache.subscribe('agent:*:status', (key, value) => {
  console.log(`Status changed: ${key}`, value);
});

// Cleanup
cache.destroy(); // Clears intervals and subscriptions
```

### PersistentCacheStore (`persistent-cache.ts`)

Durable cache store that survives process restarts using Write-Ahead Log (WAL) and periodic snapshots.

```typescript
import { PersistentCacheStore } from './walkie-talkie/persistent-cache.js';

const cache = new PersistentCacheStore({
  walPath: '/path/to/wal.log',
  snapshotPath: '/path/to/snapshot.json',
  snapshotInterval: 60000,  // Auto-snapshot every 60s (default)
  fsync: false,             // Set true for stronger durability
});

// Restore state from disk (call once at startup)
const { keysRestored, walEntriesReplayed } = await cache.restore();
console.log(`Restored ${keysRestored} keys, replayed ${walEntriesReplayed} WAL entries`);

// Use like MemoryCacheStore - all operations are automatically persisted
cache.set('agent:a1:status', { state: 'active' }, 300000);
cache.delete('agent:a1:status');

// Manual snapshot (also happens automatically)
await cache.snapshot();

// Graceful shutdown
await cache.close();
```

**Storage location:** `~/.karma/radio/`
- `wal.log` - Write-ahead log (append-only)
- `snapshot.json` - Periodic full cache dump

**Recovery algorithm:**
1. Load snapshot if exists
2. Replay WAL entries after snapshot timestamp
3. Recalculate TTLs (expired entries are skipped)
4. Start periodic snapshot timer

### AgentRadio (`agent-radio.ts`)

High-level API for agent-to-agent communication with parent-child awareness.

```typescript
import { AgentRadioImpl } from './walkie-talkie/agent-radio.js';

const radio = new AgentRadioImpl(
  cache,
  'agent-123',      // agentId
  'session-456',    // sessionId
  'session-456',    // rootSessionId
  'parent-789',     // parentId (null if root)
  'agent',          // parentType: 'session' | 'agent'
  'task',           // agentType
  'claude-sonnet-4' // model
);

// Status management
radio.setStatus('active', { tool: 'Read' });
radio.setStatus('completed');

// Progress reporting
radio.reportProgress({ tool: 'Bash', percent: 50, message: 'Running tests...' });

// Publish final result
radio.publishResult({ files_modified: 3, tests_passed: true });

// Family awareness
const parent = radio.getParentStatus();
const children = radio.getChildStatuses();
const siblings = radio.getSiblingStatuses();

// Wait for agent
const status = await radio.waitForAgent('other-agent', 'completed', 30000);

// Messaging
radio.send('other-agent', { type: 'request', data: '...' });
radio.onMessage((from, msg) => console.log(`Message from ${from}:`, msg));

// Subscriptions
radio.onChildStatus((agentId, status) => { /* child updated */ });
radio.onSiblingStatus((agentId, status) => { /* sibling updated */ });

// Cleanup
radio.destroy();
```

### CLI Commands (`karma radio`)

Command-line interface for hook integration.

```bash
# Required environment variables
export KARMA_AGENT_ID="agent-123"
export KARMA_SESSION_ID="session-456"
export KARMA_PARENT_ID="parent-789"     # optional
export KARMA_AGENT_TYPE="task"          # optional
export KARMA_MODEL="claude-sonnet-4"    # optional

# Set status
karma radio set-status active
karma radio set-status active --tool Read
karma radio set-status completed --metadata '{"files": 3}'

# Report progress
karma radio report-progress --tool Bash --percent 50 --message "Running..."

# Publish result
karma radio publish-result ./result.json

# Get status
karma radio get-status                  # Self
karma radio get-status --agent other-1  # Specific agent

# Wait for agent (subscription-based, instant notifications)
karma radio wait-for agent-2 completed --timeout 30000

# Wait for agent (polling fallback)
karma radio wait-for agent-2 completed --timeout 30000 --poll

# Messaging
karma radio send agent-2 '{"type": "request"}'
karma radio listen
karma radio listen --agent agent-2
```

**Exit Codes:**
- `0` - Success
- `1` - Timeout or operation failure
- `2` - Error (missing env, invalid args, server error)

All output is JSON for machine parsing.

## Key Schema

```
agent:{agentId}:status    → AgentStatus    (TTL: 5 min)
agent:{agentId}:progress  → ProgressUpdate (TTL: 1 min)
agent:{agentId}:result    → unknown        (TTL: 10 min)
agent:{agentId}:inbox     → AgentMessage[] (TTL: 5 min)
session:{sessionId}:agents → string[]      (TTL: 1 hour)
```

## Data Types

### AgentState

```typescript
type AgentState = 'pending' | 'active' | 'waiting' | 'completed' | 'failed' | 'cancelled';
```

### AgentStatus

```typescript
interface AgentStatus {
  agentId: string;
  sessionId: string;
  rootSessionId: string;
  state: AgentState;
  startedAt: string;      // ISO 8601
  updatedAt: string;      // ISO 8601
  parentId: string | null;
  parentType: 'session' | 'agent';
  agentType: string;
  model: string;
  metadata: Record<string, unknown>;
}
```

### ProgressUpdate

```typescript
interface ProgressUpdate {
  tool?: string;
  step?: string;
  percent?: number;       // 0-100
  message?: string;
}
```

## Integration with Aggregator

Enable radio support when creating the aggregator:

```typescript
// Basic radio (in-memory, clears on restart)
const aggregator = new MetricsAggregator({ enableRadio: true });

// With persistence (survives restarts)
const aggregator = new MetricsAggregator({
  enableRadio: true,
  persistRadio: true  // Stores in ~/.karma/radio/
});

// Initialize radio (required for persistent mode)
await aggregator.initRadio();

// Agents are automatically registered when discovered
// Access radio instances
const radio = aggregator.getAgentRadio('agent-123');

// Subscribe to status changes
aggregator.onAgentStatusChange((agentId, status) => {
  console.log(`Agent ${agentId} is now ${status.state}`);
});

// Get all statuses (for dashboard API)
const statuses = aggregator.getAgentStatuses();

// Graceful shutdown (creates final snapshot if persistent)
await aggregator.destroy();
```

## Dashboard Integration

The dashboard receives real-time updates via Server-Sent Events:

```typescript
// SSE events
'agent:status'   → { agentId, status: AgentStatus }
'agent:progress' → { agentId, progress: ProgressUpdate }
```

API endpoints:

```
GET /api/radio/agents         → All agent statuses
GET /api/radio/agent/:id      → Single agent status
GET /api/radio/session/:id/tree → Agent hierarchy tree
```

## Hook Integration

Example Claude Code hook configuration:

```yaml
# .claude/hooks.yaml
hooks:
  PreToolUse:
    - command: |
        karma radio set-status active --tool "$TOOL_NAME"
      env:
        KARMA_AGENT_ID: "{{sessionId}}"
        KARMA_SESSION_ID: "{{rootSessionId}}"

  PostToolUse:
    - command: |
        karma radio report-progress --tool "$TOOL_NAME" --message "Completed"

  Stop:
    - command: |
        karma radio set-status completed
```

## Schema Validation

Optional metadata validation for type safety:

```typescript
import { SchemaRegistry } from './walkie-talkie/schema-registry.js';

const registry = new SchemaRegistry();

// Register custom schema
registry.register({
  agentType: 'my-agent',
  required: ['task_id'],
  properties: {
    task_id: { type: 'string' },
    priority: { type: 'number' }
  }
});

// Validate metadata
const result = registry.validate('my-agent', { task_id: '123' });
// { valid: true, errors: [] }
```

**Built-in schemas:** `task`, `explore`

**Validation modes:**
- `none` (default): No validation
- `warn`: Log warning, allow operation
- `strict`: Reject invalid metadata

**CLI usage:**
```bash
karma radio set-status active --metadata '{"tool":"Read"}' --validate strict
```

## Cache Persistence

Enable persistence to survive process restarts:

```bash
# Watch mode with persistence
karma watch --persist-radio

# Data stored in ~/.karma/radio/
#   wal.log        - Write-ahead log
#   snapshot.json  - Periodic snapshots
```

**How it works:**
1. **Write-Ahead Log (WAL)**: Every `set()` and `delete()` is appended to a log file
2. **Snapshots**: Full cache dump every 60 seconds (configurable)
3. **Recovery**: On startup, load snapshot + replay WAL entries
4. **TTL handling**: Expired entries are skipped during recovery

**Programmatic usage:**

```typescript
import { PersistentCacheStore } from './walkie-talkie/persistent-cache.js';

const cache = new PersistentCacheStore({
  walPath: '~/.karma/radio/wal.log',
  snapshotPath: '~/.karma/radio/snapshot.json',
  snapshotInterval: 60000,  // 60 seconds
  fsync: false,             // Set true for stronger guarantees
});

// Restore on startup
await cache.restore();

// Use normally - persistence is automatic
cache.set('key', 'value');

// Graceful shutdown
await cache.snapshot();  // Final snapshot
await cache.close();     // Close WAL
```

## TTL Strategy

| Data Type | TTL | Rationale |
|-----------|-----|-----------|
| Status | 5 min | Agents may go silent; stale status should expire |
| Progress | 1 min | Ephemeral; only latest matters |
| Result | 10 min | May be needed after completion |
| Inbox | 5 min | Messages consumed quickly |
| Session agents | 1 hr | Session reference; longer retention |

## Security

- **Socket permissions**: `0600` (owner-only read/write)
- **Socket path**: `/tmp/karma-radio.sock` (Unix) or named pipe (Windows)
- **Message size limit**: 64KB max per message
- **Connection limit**: 10 max concurrent connections
- **Timeout**: 5s per request (5min for subscription connections)

## Performance Characteristics

- **Cache operations**: O(1) get/set, O(n) pattern matching
- **Memory**: ~500 bytes per agent status
- **Latency**: <1ms p99 for all cache operations
- **Pub/sub**: Synchronous delivery, subscriber errors isolated
- **WAL append**: <5ms overhead (fire-and-forget, async)
- **Snapshot**: Background, non-blocking

## Testing

```bash
# Run all walkie-talkie tests
npm test -- tests/walkie-talkie/

# Individual test files
npm test -- tests/walkie-talkie/cache-store.test.ts
npm test -- tests/walkie-talkie/agent-radio.test.ts
npm test -- tests/walkie-talkie/radio-client.test.ts
npm test -- tests/walkie-talkie/persistent-cache.test.ts
```

**Test coverage (313 tests total):**
- CacheStore: 50 tests (CRUD, TTL, patterns, pub/sub, edge cases)
- AgentRadio: 45 tests (status, progress, family, messaging, discovery)
- RadioClient: 34 tests (connection, timeout, concurrent requests)
- Subscription: 13 tests (notifications, keep-alive, cleanup, fallback)
- SchemaRegistry: 51 tests (validation, types, modes, built-in schemas)
- Integration: 24 tests (aggregator, socket server, API)
- WAL: 33 tests (append, read, truncate, corruption handling)
- Snapshot: 26 tests (save, load, atomic writes, TTL preservation)
- PersistentCache: 37 tests (restore, recovery, TTL recalculation)

## File Structure

```
src/walkie-talkie/
├── index.ts             # Public exports
├── types.ts             # TypeScript interfaces
├── cache-store.ts       # MemoryCacheStore implementation
├── persistent-cache.ts  # PersistentCacheStore (WAL + Snapshot)
├── wal.ts               # Write-Ahead Log
├── snapshot.ts          # Snapshot Manager
├── agent-radio.ts       # AgentRadio implementation
├── schema-registry.ts   # Schema validation
├── socket-server.ts     # Unix socket server (IPC)
├── socket-client.ts     # Unix socket client (CLI)
└── README.md            # This file

src/commands/
└── radio.ts             # CLI command implementation

tests/walkie-talkie/
├── cache-store.test.ts
├── agent-radio.test.ts
├── radio-client.test.ts
├── schema-registry.test.ts
├── subscription.test.ts
├── integration.test.ts
├── wal.test.ts
├── snapshot.test.ts
└── persistent-cache.test.ts
```

## Implementation Phases

All phases are complete:

| Phase | Name | Description | Status |
|-------|------|-------------|--------|
| 1 | Agent Discovery | List all agents in a session | Done |
| 2 | Status + Progress | Consolidated status/progress API | Done |
| 3 | Batch Operations | Multi-key operations | Done |
| 4 | Subscription Wait | Zero-polling wait-for-agent | Done |
| 5 | Schema Validation | Metadata type safety | Done |
| 6 | Cache Persistence | WAL + Snapshots for durability | Done |

## Known Limitations

- Pattern matching uses `*` for single-segment only (no `**` for multi-segment)
- No distributed mode; single-process only
- Persistence is opt-in (`--persist-radio` flag)

## Related Documentation

- [Phase Documentation](../../../improve/karma-logger/agent-walkie-talkie/)
- [Karma Logger README](../../README.md)
