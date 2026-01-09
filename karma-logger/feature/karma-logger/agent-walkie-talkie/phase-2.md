# Phase 2: Agent Radio

## Objective

High-level API for agent-to-agent communication. Wraps CacheStore with agent-aware semantics.

## Dependencies

- **Phase 1**: CacheStore must be complete

## Deliverables

```
src/walkie-talkie/
├── agent-radio.ts       # AgentRadioImpl class
└── types.ts             # Add AgentRadio types

tests/walkie-talkie/
└── agent-radio.test.ts  # Full test coverage
```

## Tasks

### 2.1 Define Agent Types (`types.ts`)

```typescript
type AgentState = 'pending' | 'active' | 'waiting' | 'completed' | 'failed' | 'cancelled';

interface AgentStatus {
  agentId: string;
  sessionId: string;       // Agent's own session (if spawned)
  rootSessionId: string;   // Root session for metrics aggregation
  state: AgentState;
  startedAt: string;
  updatedAt: string;
  parentId: string | null;
  parentType: 'session' | 'agent';  // Clarify parent relationship type
  agentType: string;
  model: string;
  metadata: Record<string, unknown>;
}

interface ProgressUpdate {
  tool?: string;
  step?: string;
  percent?: number;
  message?: string;
}

interface AgentRadio {
  readonly agentId: string;
  readonly sessionId: string;
  readonly parentId: string | null;

  // Status
  setStatus(state: AgentState, metadata?: Record<string, unknown>): void;
  getStatus(): AgentStatus;

  // Progress
  reportProgress(progress: ProgressUpdate): void;

  // Results
  publishResult(result: unknown): void;

  // Listeners
  onAgentStatus(agentId: string, cb: (status: AgentStatus) => void): () => void;
  onChildStatus(cb: (agentId: string, status: AgentStatus) => void): () => void;
  onSiblingStatus(cb: (agentId: string, status: AgentStatus) => void): () => void;

  // Queries
  getParentStatus(): AgentStatus | null;
  getChildStatuses(): Map<string, AgentStatus>;
  getSiblingStatuses(): Map<string, AgentStatus>;
  waitForAgent(agentId: string, state: AgentState, timeoutMs?: number): Promise<AgentStatus>;

  // Messaging
  send(targetAgentId: string, message: unknown): void;
  onMessage(cb: (fromAgentId: string, message: unknown) => void): () => void;

  // Cleanup
  destroy(): void;
}
```

### 2.2 Key Schema

```
agent:{agentId}:status      → AgentStatus
agent:{agentId}:progress    → ProgressUpdate
agent:{agentId}:result      → Final result
session:{rootSessionId}:agents   → string[] (agent IDs in session)
agent:{agentId}:inbox       → Message[]
```

**Design Decision:** Simplified key schema without nesting under `session:*:agent:*`.
- AgentStatus contains `rootSessionId` for session lookup
- Simpler patterns for Phase 5 subscription: `agent:*:status`
- Session agent list still scoped by rootSessionId

### 2.3 Implement AgentRadioImpl (`agent-radio.ts`)

| Method | Logic |
|--------|-------|
| `constructor` | Register in session agents list, set initial 'pending' status |
| `setStatus` | Update `agent:{id}:status`, preserve startedAt |
| `getStatus` | Read from cache |
| `getParentStatus` | Read parent's status if parentId exists, else null |
| `reportProgress` | Write to `agent:{id}:progress` with 1min TTL |
| `publishResult` | Write to `agent:{id}:result`, set status 'completed' |
| `onChildStatus` | Subscribe `agent:*:status`, filter parentId === self |
| `getChildStatuses` | Query all agents in session, filter by parentId |
| `waitForAgent` | Check current + subscribe with timeout Promise |
| `send` | Append to target's inbox |
| `onMessage` | Subscribe to own inbox, track lastIndex |
| `destroy` | Call all unsubscribers |

**Note:** Consider extending EventEmitter for consistency with MetricsAggregator:
- `on('child:status', handler)` instead of `onChildStatus(handler)`
- `on('sibling:status', handler)` instead of `onSiblingStatus(handler)`

### 2.4 TTL Strategy

| Key Type | TTL | Rationale |
|----------|-----|-----------|
| Status | 5 min | Actively updated |
| Progress | 1 min | Rapid updates |
| Result | 10 min | Parent retrieval window |
| Session agents | 1 hour | Session lifetime |
| Inbox | 5 min | Message buffer |

### 2.5 Write Tests (`agent-radio.test.ts`)

```typescript
describe('AgentRadioImpl', () => {
  describe('status management', () => {
    test('sets initial pending status on creation');
    test('updates status preserving startedAt');
    test('getStatus returns current state');
  });

  describe('progress', () => {
    test('reportProgress writes timestamped update');
    test('progress has short TTL');
  });

  describe('results', () => {
    test('publishResult stores data');
    test('publishResult sets status to completed');
  });

  describe('parent-child relationships', () => {
    test('registers in session agent list');
    test('getChildStatuses returns only children');
    test('onChildStatus fires for child updates only');
  });

  describe('sibling awareness', () => {
    test('getSiblingStatuses excludes self');
    test('onSiblingStatus fires for siblings only');
  });

  describe('waitForAgent', () => {
    test('resolves immediately if state matches');
    test('resolves when state changes');
    test('rejects on timeout');
  });

  describe('messaging', () => {
    test('send appends to target inbox');
    test('onMessage receives new messages');
    test('message has from/timestamp metadata');
  });

  describe('cleanup', () => {
    test('destroy removes all subscriptions');
  });
});
```

## Acceptance Criteria

- [x] Status lifecycle: pending → active → completed/failed
- [x] Parent can list and monitor children
- [x] Siblings can discover each other
- [x] `waitForAgent` with timeout works
- [x] Direct messaging between agents
- [x] No dangling subscriptions after destroy()

## Implementation Status: COMPLETED ✅

**Completed:** 2026-01-08

**Files Created:**
- `src/walkie-talkie/types.ts` - Extended with AgentState, AgentStatus, ProgressUpdate, AgentMessage, AgentRadio types
- `src/walkie-talkie/agent-radio.ts` - AgentRadioImpl class (~290 lines)
- `src/walkie-talkie/index.ts` - Updated exports
- `tests/walkie-talkie/agent-radio.test.ts` - 29 tests, all passing

**Key Implementation Details:**
- TTL Strategy: Status 5min, Progress 1min, Result 10min, Session agents 1hr, Inbox 5min
- Default wait timeout: 30 seconds
- Pattern-based pub/sub for status subscriptions
- Message inbox with append-only semantics
- Clean destroy() with full subscription and data cleanup

## Edge Cases

| Case | Handling |
|------|----------|
| No parent (root agent) | parentId = null |
| Agent already completed | waitForAgent resolves immediately |
| Send to non-existent agent | Creates inbox (no error) |
| Multiple children | All tracked correctly |
| Rapid status updates | Last write wins |

## Integration Points

- CacheStore (Phase 1) — all data storage
- Aggregator (Phase 5) — will consume AgentRadio

### MetricsAggregator Mapping

| AgentRadio Event | MetricsAggregator Method | Notes |
|------------------|--------------------------|-------|
| setStatus('active') | processAgentEntry() | Update lastActivity |
| reportProgress() | recordActivity() | Convert to ActivityEntry |
| publishResult() | endSession() if root | Trigger persistence |

## Estimated Complexity

- Lines of code: ~200
- Test lines: ~250
- Risk: Medium (async timing in waitForAgent)
