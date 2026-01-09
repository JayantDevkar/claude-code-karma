# Phase 2b: Remove Agent from Session Cache on Unregister

> **Priority:** High | **Complexity:** Low | **Type:** Code Implementation | **Status:** ✅ COMPLETED

## Objective

When an agent unregisters or completes, remove it from the session agents list.

## Prerequisites

- Phase 2a complete

## Files to Modify

| File | Action |
|------|--------|
| `src/aggregator.ts` | Update `unregisterAgent()` method |

## Implementation

```typescript
// In unregisterAgent() method
if (this.cache) {
  const agent = this.agentRadios.get(agentId);
  if (agent) {
    const sessionKey = `session:${agent.sessionId}:agents`;
    const agents = this.cache.get<string[]>(sessionKey) || [];
    const filtered = agents.filter(id => id !== agentId);
    if (filtered.length > 0) {
      this.cache.set(sessionKey, filtered, 3600000);
    } else {
      this.cache.delete(sessionKey);
    }
  }
}
```

## Acceptance Criteria

- [x] Agent removed from session list on unregister
- [x] Empty session lists cleaned up (key deleted)
- [x] Completed/failed agents properly removed
- [x] No memory leaks in cache

## Implementation Notes

**Completed:** 2026-01-09

New method `unregisterAgent(agentId: string)` added to `src/aggregator.ts` (lines 423-450):
```typescript
/**
 * Unregister an agent and remove from session cache
 * Phase 2b: Remove agent from session agents cache
 */
unregisterAgent(agentId: string): void {
  // Phase 2b: Remove from session agents cache
  if (this.cache) {
    const radio = this.agentRadios.get(agentId);
    if (radio) {
      const sessionKey = `session:${radio.sessionId}:agents`;
      const agents = this.cache.get<string[]>(sessionKey) || [];
      const filtered = agents.filter(id => id !== agentId);
      if (filtered.length > 0) {
        this.cache.set(sessionKey, filtered, 3600000);
      } else {
        this.cache.delete(sessionKey);
      }
    }
  }

  // Clean up radio instance
  const radio = this.agentRadios.get(agentId);
  if (radio) {
    radio.setStatus('completed');
    radio.destroy();
    this.agentRadios.delete(agentId);
  }
}
```

## Testing

```bash
# Register agent
KARMA_AGENT_ID=test-1 KARMA_SESSION_ID=sess-1 karma radio set-status active

# Verify in list
curl http://localhost:3333/api/radio/session/sess-1/tree

# Complete agent
KARMA_AGENT_ID=test-1 KARMA_SESSION_ID=sess-1 karma radio set-status completed

# Verify removed or marked completed
curl http://localhost:3333/api/radio/session/sess-1/tree
```

## Milestone: Phase 2 Complete

After this phase, `/api/radio/session/:id/tree` returns accurate agent hierarchies.

## Next Phase

→ Phase 3a: Frontend SSE handlers
