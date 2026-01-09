# Phase 1d: Add --radio Flag to Dashboard Command

> **Priority:** High | **Complexity:** Low | **Type:** Code Implementation

## Objective

Expose `--radio` and `--persist-radio` flags in dashboard CLI command.

## Prerequisites

- Phase 1c complete (or can be done in parallel)

## Files to Modify

| File | Action |
|------|--------|
| `src/commands/dashboard.ts` | Add CLI flags |
| `src/dashboard/index.ts` | Pass options to server |

## Implementation

```typescript
// In dashboard command definition
.option('--radio', 'Enable radio agent coordination', false)
.option('--persist-radio', 'Enable persistent radio cache (WAL + snapshots)', false)

// Pass to server
await startServer({
  port,
  enableRadio: options.radio || options.persistRadio,
  persistRadio: options.persistRadio,
  // ...other options
});
```

## Acceptance Criteria

- [x] `karma dashboard --help` shows radio flags
- [x] `--radio` enables in-memory radio
- [x] `--persist-radio` enables WAL persistence
- [x] Flags work correctly together

**Status: COMPLETED** (2026-01-08)

## Testing

```bash
karma dashboard --help
karma dashboard --radio
karma dashboard --persist-radio
```

## Milestone: Phase 1 Complete

After this phase, `karma radio` CLI commands can communicate with running dashboard.

## Next Phase

→ Phase 2a: Session agent cache population
