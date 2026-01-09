# Phase 1b: Start SocketServer Conditionally

> **Priority:** High | **Complexity:** Low | **Type:** Code Implementation

## Objective

Start the SocketServer when radio is enabled in MetricsAggregator.

## Prerequisites

- Phase 1a complete

## Files to Modify

| File | Action |
|------|--------|
| `src/dashboard/server.ts` | Add conditional start logic |

## Implementation

```typescript
// In startServer() after aggregator initialization
if (aggregator.isRadioEnabled()) {
  socketServer = new SocketServer(aggregator);
  await socketServer.start();
  console.log('Radio socket server started at /tmp/karma-radio.sock');
}
```

## Acceptance Criteria

- [x] SocketServer starts when `--radio` flag used
- [x] Socket file created at `/tmp/karma-radio.sock`
- [x] Console logs confirm startup
- [x] No startup when radio disabled

**Status: COMPLETED** (2026-01-08)

## Testing

```bash
# Start with radio enabled
karma dashboard --radio

# Verify socket exists
ls -la /tmp/karma-radio.sock
```

## Next Phase

→ Phase 1c: Socket cleanup on shutdown
