# Agent Walkie-Talkie

Fast key-value cache communication layer for real-time agent coordination in Claude Code sessions.

## Overview

Walkie-Talkie enables agents to communicate status, progress, and messages without relying on bash/tail polling or context-heavy log parsing. It provides:

- **Real-time status tracking** - Know when agents start, complete, or fail
- **Parent-child awareness** - Agents know their hierarchy and can coordinate
- **Inter-agent messaging** - Direct communication between agents
- **Progress reporting** - Granular progress updates for long-running tasks
- **Zero-polling architecture** - Pub/sub notifications eliminate polling loops

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
│                        CacheStore                                │
│            (in-memory KV with TTL, pattern matching, pub/sub)    │
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

# Wait for agent
karma radio wait-for agent-2 completed --timeout 30000

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
const aggregator = new MetricsAggregator({ enableRadio: true });

// Agents are automatically registered when discovered
// Access radio instances
const radio = aggregator.getAgentRadio('agent-123');

// Subscribe to status changes
aggregator.onAgentStatusChange((agentId, status) => {
  console.log(`Agent ${agentId} is now ${status.state}`);
});

// Get all statuses (for dashboard API)
const statuses = aggregator.getAgentStatuses();
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

## Hook Integration (Phase 4 - Deferred)

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
- **Timeout**: 5s per request

## Performance Characteristics

- **Cache operations**: O(1) get/set, O(n) pattern matching
- **Memory**: ~500 bytes per agent status
- **Latency**: <1ms p99 for all cache operations
- **Pub/sub**: Synchronous delivery, subscriber errors isolated

## Testing

```bash
# Run all walkie-talkie tests
npm test -- --run tests/walkie-talkie/

# Individual test files
npm test -- --run tests/walkie-talkie/cache-store.test.ts
npm test -- --run tests/walkie-talkie/agent-radio.test.ts
npm test -- --run tests/walkie-talkie/radio-client.test.ts
npm test -- --run tests/walkie-talkie/integration.test.ts
```

**Test coverage:**
- CacheStore: 50 tests (CRUD, TTL, patterns, pub/sub, edge cases)
- AgentRadio: 29 tests (status, progress, family, messaging)
- RadioClient: 34 tests (connection, timeout, concurrent requests)
- Integration: 24 tests (aggregator, socket server, API)

## File Structure

```
src/walkie-talkie/
├── index.ts          # Public exports
├── types.ts          # TypeScript interfaces
├── cache-store.ts    # CacheStore implementation
├── agent-radio.ts    # AgentRadio implementation
├── socket-server.ts  # Unix socket server (IPC)
├── socket-client.ts  # Unix socket client (CLI)
└── README.md         # This file

src/commands/
└── radio.ts          # CLI command implementation

tests/walkie-talkie/
├── cache-store.test.ts
├── agent-radio.test.ts
├── radio-client.test.ts
└── integration.test.ts
```

## Migration Path

1. **Opt-in** (current): `karma watch --enable-radio`
2. **Default-on**: Radio enabled by default, `--disable-radio` to opt out
3. **Always-on**: Radio as standard feature

## Known Limitations

- `wait-for` is currently polling-based, not true subscription
- Pattern matching uses `*` for single-segment only (no `**` for multi-segment)
- No persistence; cache clears on restart
- No distributed mode; single-process only

## Related Documentation

- [Phase Documentation](../feature/karma-logger/agent-walkie-talkie/)
- [Karma Logger README](../README.md)
