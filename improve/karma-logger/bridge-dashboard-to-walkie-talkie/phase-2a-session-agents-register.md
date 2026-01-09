# Phase 2a: Populate Session Agents Cache on Register

> **Priority:** High | **Complexity:** Low | **Type:** Code Implementation | **Status:** ✅ COMPLETED

## Objective

When an agent registers, add its ID to the `session:{sessionId}:agents` cache key.

## Prerequisites

- Phase 1 complete (socket server running)

## Files to Modify

| File | Action |
|------|--------|
| `src/aggregator.ts` | Update `registerAgent()` method |

## Implementation

```typescript
// In registerAgent() method, after creating AgentRadio
if (this.cache) {
  const sessionKey = `session:${sessionId}:agents`;
  const agents = this.cache.get<string[]>(sessionKey) || [];
  if (!agents.includes(agentId)) {
    agents.push(agentId);
    this.cache.set(sessionKey, agents, 3600000); // 1 hour TTL
  }
}
```

## Acceptance Criteria

- [x] `session:{id}:agents` populated on agent registration
- [x] No duplicate agent IDs in list
- [x] TTL set appropriately (1 hour default)
- [x] Works with both memory and persistent cache

## Implementation Notes

**Completed:** 2026-01-09

Code added to `src/aggregator.ts` in `registerAgent()` method (lines 413-419):
```typescript
// Phase 2a: Populate session agents cache
const sessionKey = `session:${parentSession.sessionId}:agents`;
const agents = this.cache.get<string[]>(sessionKey) || [];
if (!agents.includes(agent.sessionId)) {
  agents.push(agent.sessionId);
  this.cache.set(sessionKey, agents, 3600000); // 1 hour TTL
}
```

## Testing

```bash
# Start dashboard with radio
karma dashboard --radio

# In another terminal, simulate agent registration
KARMA_AGENT_ID=test-1 KARMA_SESSION_ID=session-123 karma radio set-status idle

# Check via API
curl http://localhost:3333/api/radio/session/session-123/tree
```

## Next Phase

→ Phase 2b: Remove agent from cache on unregister
