# Phase 4: Subscription-Based Wait

**Priority:** Future
**Complexity:** High
**Estimated Files:** 5-7

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

- [ ] `wait-for` receives instant notification (no polling delay)
- [ ] Connection stays open for duration of wait
- [ ] Keep-alive prevents socket timeout
- [ ] Graceful degradation if subscription fails (fall back to polling)
- [ ] Resource cleanup on timeout/cancel

## Risks

- Longer-lived connections increase memory
- Need to handle socket disconnections gracefully
- Backward compatibility with polling mode

## Dependencies

- CacheStore pub/sub must be reliable
- Socket server must support long-lived connections

## Rollback

Add `--poll` flag to fall back to polling behavior.
