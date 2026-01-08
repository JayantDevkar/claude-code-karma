# Phase 3: Batch Operations

**Priority:** Low
**Complexity:** Low
**Estimated Files:** 3

## Problem Statement

From meta-testing: "Common pattern is: set status + report progress. Currently requires two CLI calls."

Agents frequently need to update both status and progress atomically.

## Goal

Enable single-call status + progress updates for efficiency.

## Implementation

### 1. CLI Enhancement

Extend `set-status` to include progress flags:

```bash
# Current (two calls)
karma radio set-status active
karma radio report-progress --percent 0 --message "Starting..."

# New (single call)
karma radio set-status active --percent 0 --message "Starting..."
karma radio set-status active --tool Read --percent 25 --message "Reading files"
```

### 2. AgentRadio Method

```typescript
interface SetStatusOptions {
  metadata?: Record<string, unknown>;
  progress?: ProgressUpdate;
}

setStatus(state: AgentState, options?: SetStatusOptions): void
```

### 3. Socket Handler

Update `set-status` handler to process progress if provided:

```typescript
case 'set-status':
  radio.setStatus(payload.state, {
    metadata: payload.metadata,
    progress: payload.progress
  });
  // Single atomic operation
```

## Files to Modify

| File | Change |
|------|--------|
| `src/walkie-talkie/agent-radio.ts` | Extend `setStatus()` signature |
| `src/walkie-talkie/socket-server.ts` | Update handler |
| `src/commands/radio.ts` | Add progress flags to `set-status` |

## Test Cases

```typescript
describe('setStatus with progress', () => {
  it('sets status without progress');
  it('sets status with progress atomically');
  it('merges metadata and sets progress');
  it('progress flags are optional');
});
```

## Acceptance Criteria

- [ ] `set-status active --percent 50` works
- [ ] `--message` flag works with status update
- [ ] `--tool` flag works with status update
- [ ] Backward compatible (flags optional)
- [ ] Single cache operation (atomic)

## Dependencies

None - additive change.

## Rollback

Flags are additive; no rollback needed.
