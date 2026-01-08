# Phase 4: Subscription-Based Wait

**Status:** IMPLEMENTED
**Implemented:** 2026-01-08
**Priority:** Future
**Complexity:** High
**Files Modified:** 6

## Problem Statement

From meta-testing: "Per README, `wait-for` is polling-based, not true subscription."

Current implementation polls at intervals, causing:
- Higher latency (poll interval delay)
- More CPU cycles for long waits
- Inefficient for many concurrent waits

## Goal

Replace polling with true socket-based subscriptions for instant notifications.

## Architecture

```
┌──────────────────┐         ┌──────────────────┐
│   CLI (wait-for) │         │   Socket Server  │
└────────┬─────────┘         └────────┬─────────┘
         │                            │
         │  1. subscribe(agentId)     │
         │ ─────────────────────────▶ │
         │                            │
         │  2. keep-alive (30s)       │ ◀──┐
         │ ◀───────────────────────── │    │
         │                            │    │ status change
         │  3. notification           │    │ detected
         │ ◀───────────────────────── │ ───┘
         │                            │
         │  4. unsubscribe            │
         │ ─────────────────────────▶ │
         │                            │
```

## Implementation

### 1. Socket Protocol Extension

Add subscription messages:

```typescript
// Client → Server
{ type: 'subscribe', agentId: string, targetState: AgentState }
{ type: 'unsubscribe', subscriptionId: string }

// Server → Client
{ type: 'subscribed', subscriptionId: string }
{ type: 'notification', subscriptionId: string, status: AgentStatus }
{ type: 'keep-alive' }
```

### 2. Server Subscription Manager

New class in `socket-server.ts`:

```typescript
class SubscriptionManager {
  private subscriptions: Map<string, Subscription>;

  subscribe(socket: Socket, agentId: string, targetState: AgentState): string;
  unsubscribe(subscriptionId: string): void;
  notify(agentId: string, status: AgentStatus): void;
}
```

### 3. CacheStore Integration

Connect subscriptions to cache pub/sub:

```typescript
cache.subscribe(`agent:${agentId}:status`, (key, status) => {
  subscriptionManager.notify(agentId, status);
});
```

### 4. CLI Client Update

Modify `wait-for` to use subscription mode:

```typescript
async waitFor(agentId: string, state: AgentState, timeout: number) {
  const { subscriptionId } = await this.send({ type: 'subscribe', agentId, state });

  return new Promise((resolve, reject) => {
    this.on('notification', (data) => {
      if (data.subscriptionId === subscriptionId) {
        resolve(data.status);
      }
    });

    setTimeout(() => reject(new Error('Timeout')), timeout);
  });
}
```

## Files to Modify

| File | Change |
|------|--------|
| `src/walkie-talkie/types.ts` | Add subscription message types |
| `src/walkie-talkie/socket-server.ts` | Add SubscriptionManager |
| `src/walkie-talkie/socket-client.ts` | Add subscription handling |
| `src/commands/radio.ts` | Update wait-for command |
| `tests/walkie-talkie/socket-server.test.ts` | Subscription tests |

## Test Cases

```typescript
describe('Subscription-based wait', () => {
  it('receives notification when target state reached');
  it('times out if state not reached');
  it('handles multiple concurrent subscriptions');
  it('cleans up subscription on disconnect');
  it('sends keep-alive for long waits');
  it('notifies immediately if already in target state');
});
```

## Acceptance Criteria

- [x] `wait-for` receives instant notification (no polling delay)
- [x] Connection stays open for duration of wait
- [x] Keep-alive prevents socket timeout (30s interval)
- [x] Graceful degradation if subscription fails (fall back to polling)
- [x] Resource cleanup on timeout/cancel

## Risks

- Longer-lived connections increase memory
- Need to handle socket disconnections gracefully
- Backward compatibility with polling mode

## Dependencies

- CacheStore pub/sub must be reliable
- Socket server must support long-lived connections

## Rollback

Add `--poll` flag to fall back to polling behavior.

---

## Implementation Summary (2026-01-08)

### Files Modified

| File | Lines Added | Changes |
|------|-------------|---------|
| `src/walkie-talkie/types.ts` | +38 | Added 6 subscription message types |
| `src/walkie-talkie/socket-server.ts` | +296 | Added SubscriptionManager class |
| `src/walkie-talkie/socket-client.ts` | +323 | Added `waitForAgent()` with subscription mode |
| `src/commands/radio.ts` | +33 | Added `--poll` flag support |
| `src/walkie-talkie/index.ts` | +11 | Exported new types and classes |
| `tests/walkie-talkie/subscription.test.ts` | NEW | 13 test cases |

### Key Components

1. **SubscriptionManager** (socket-server.ts)
   - Tracks subscriptions by ID and by socket
   - Sends keep-alive every 30s
   - Extends socket timeout to 5min for subscription connections
   - Auto-cleanup on disconnect/timeout/error
   - Immediate notification if already in target state

2. **RadioClient.waitForAgent()** (socket-client.ts)
   - `usePoll: false` (default) - Uses server push notifications
   - `usePoll: true` - Falls back to 500ms polling
   - Graceful degradation if subscription fails
   - Added `SubscriptionError` error class

3. **CLI wait-for command** (radio.ts)
   - Default: subscription mode
   - `--poll` flag: forces polling mode
   - Output includes `mode: 'subscription' | 'poll'`

### Test Coverage

All 160 walkie-talkie tests pass including 13 new subscription tests:
- Notification on target state reached
- Immediate notification if already in state
- Timeout handling
- Multiple concurrent subscriptions
- Cleanup on disconnect
- Keep-alive mechanism
- Poll mode fallback
- Graceful degradation
