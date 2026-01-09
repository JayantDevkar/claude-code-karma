# Phase 1c: Socket Cleanup on Shutdown

> **Priority:** High | **Complexity:** Low | **Type:** Code Implementation

## Objective

Ensure socket server is properly closed when dashboard shuts down.

## Prerequisites

- Phase 1b complete

## Files to Modify

| File | Action |
|------|--------|
| `src/dashboard/server.ts` | Add cleanup in shutdown handler |

## Implementation

```typescript
// In existing shutdown/cleanup handler
async function cleanup() {
  if (socketServer) {
    await socketServer.stop();
    socketServer = null;
  }
  // existing cleanup...
}

// Ensure signals are handled
process.on('SIGINT', cleanup);
process.on('SIGTERM', cleanup);
```

## Acceptance Criteria

- [x] Socket file removed on Ctrl+C
- [x] Socket file removed on SIGTERM
- [x] No orphan socket files after restart
- [x] Graceful shutdown logged

**Status: COMPLETED** (2026-01-08)

## Testing

```bash
# Start dashboard
karma dashboard --radio

# In another terminal
ls /tmp/karma-radio.sock  # should exist

# Press Ctrl+C on dashboard
ls /tmp/karma-radio.sock  # should not exist
```

## Next Phase

→ Phase 1d: Add --radio flag to dashboard command
