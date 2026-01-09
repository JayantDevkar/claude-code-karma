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

- [x] `set-status active --percent 50` works
- [x] `--message` flag works with status update
- [x] `--tool` flag works with status update
- [x] Backward compatible (flags optional)
- [x] Single cache operation (atomic)

## Dependencies

None - additive change.

## Rollback

Flags are additive; no rollback needed.

## Implementation Notes

### Files Modified

1. **`src/walkie-talkie/types.ts`**
   - Added `SetStatusOptions` interface with optional `metadata` and `progress` fields
   - Updated `AgentRadio.setStatus()` signature to accept `SetStatusOptions | Record<string, unknown>`

2. **`src/walkie-talkie/agent-radio.ts`**
   - Updated `setStatus()` to detect new `SetStatusOptions` format vs legacy metadata format
   - Detection logic: checks if `progress` is an object OR if only `metadata`/`progress` keys exist
   - When progress is provided, calls `reportProgress()` atomically after setting status
   - Maintains full backward compatibility with legacy `setStatus(state, metadata)` calls

3. **`src/walkie-talkie/socket-server.ts`**
   - Updated `set-status` handler to extract `progress` from request args
   - Passes progress to `setStatus()` using the new `SetStatusOptions` format

4. **`src/commands/radio.ts`**
   - Added `--percent <num>` flag to set-status command
   - Added `--message <text>` flag to set-status command
   - Updated `--tool` description to note it also sets progress.tool
   - Handler builds `progress` object when any progress flags are provided

### Tests Added

Added new test suite "setStatus with progress (batch operations)" in `tests/walkie-talkie/agent-radio.test.ts`:
- `sets status without progress (backward compatible)`
- `sets status with progress atomically`
- `merges metadata and sets progress`
- `progress flags are optional`
- `getFullStatus returns combined status and progress from batch operation`
- `maintains backward compatibility with legacy metadata format`

### Usage Examples

```bash
# Set status with progress in a single call
karma radio set-status active --percent 50 --message "Processing..."

# With tool name
karma radio set-status active --tool Read --percent 25 --message "Reading files"

# All flags together
karma radio set-status active --tool Bash --percent 75 --message "Running tests" --metadata '{"phase": 2}'

# Backward compatible (no progress)
karma radio set-status active
karma radio set-status active --metadata '{"key": "value"}'
```

## Completion

**Date:** 2026-01-08
**Status:** Complete
**Tests:** All 147 walkie-talkie tests passing
