# Phase 2: Status + Progress Consolidation

**Status: Implemented**

**Priority:** Medium
**Complexity:** Low
**Estimated Files:** 3-4

## Problem Statement

From meta-testing: "Progress is stored at `agent:{id}:progress` but `get-status` only returns status. To see full agent state, need two queries."

Common pattern requires two CLI calls: one for status, one for progress.

## Goal

Reduce CLI calls by consolidating status and progress into a single response.

## Implementation

### 1. CLI Flag

Add `--include-progress` to `get-status`:

```bash
karma radio get-status                       # Status only
karma radio get-status --include-progress    # Status + Progress
karma radio get-status -p                    # Short flag
```

Output:
```json
{
  "agentId": "agent-123",
  "state": "active",
  "progress": {
    "tool": "Bash",
    "percent": 50,
    "message": "Running tests..."
  }
}
```

### 2. AgentRadio Method

Add to `src/walkie-talkie/agent-radio.ts`:

```typescript
interface GetStatusOptions {
  includeProgress?: boolean;
}

getStatus(options?: GetStatusOptions): AgentStatus & { progress?: ProgressUpdate }
```

Or simpler: `getFullStatus(): AgentStatusWithProgress`

### 3. Type Definition

```typescript
interface AgentStatusWithProgress extends AgentStatus {
  progress?: ProgressUpdate;
}
```

### 4. Socket Handler Update

Modify `get-status` handler to accept options:

```typescript
case 'get-status':
  const status = payload.includeProgress
    ? radio.getFullStatus()
    : radio.getStatus();
  return { status };
```

## Files to Modify

| File | Change |
|------|--------|
| `src/walkie-talkie/types.ts` | Add `AgentStatusWithProgress` |
| `src/walkie-talkie/agent-radio.ts` | Add `getFullStatus()` or modify `getStatus()` |
| `src/walkie-talkie/socket-server.ts` | Update handler |
| `src/commands/radio.ts` | Add `--include-progress` flag |

## Test Cases

```typescript
describe('getStatus with progress', () => {
  it('returns status only by default');
  it('includes progress when flag set');
  it('progress is undefined when no progress reported');
  it('returns latest progress update');
});
```

## Acceptance Criteria

- [x] `karma radio get-status -p` returns combined status+progress
- [x] Progress is omitted if none reported
- [x] Backward compatible (no flag = status only)
- [x] API endpoint supports `?includeProgress=true`

## Dependencies

None - additive change.

## Rollback

Flag is additive; no rollback needed.

---

## Implementation Notes

### Changes Made (2026-01-08)

1. **types.ts**: Added `AgentStatusWithProgress` interface extending `AgentStatus` with optional `progress?: ProgressUpdate`. Also added `getFullStatus(): AgentStatusWithProgress` to the `AgentRadio` interface.

2. **agent-radio.ts**: Implemented `getFullStatus()` method that:
   - Calls `getStatus()` to get current status
   - Fetches latest progress from cache (`agent:{id}:progress`)
   - Returns combined object with progress only if it exists

3. **socket-server.ts**: Updated `get-status` handler to:
   - Check for `includeProgress` boolean in request args
   - Use `getFullStatus()` for self when flag is true
   - Manually attach progress for other agents when querying with flag

4. **radio.ts (CLI)**: Added `-p, --include-progress` flag to `get-status` command that passes `includeProgress: true` to the socket request.

### Tests Added

Added 4 new test cases to `agent-radio.test.ts`:
- `returns status only when no progress reported`
- `includes progress when progress has been reported`
- `returns latest progress update`
- `progress becomes undefined after TTL expires`

Also updated interface compliance test to verify `getFullStatus` method exists.

### Test Results

All 141 walkie-talkie tests pass (137 original + 4 new).
