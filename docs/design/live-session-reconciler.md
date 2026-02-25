# Live Session Reconciler

> Periodic background task that detects and resolves stuck live sessions.

## Problem

When a Claude Code session hands off to a new session (e.g., to execute an approved plan), the parent session **no longer fires a `SessionEnd` hook**. The parent's live session state stays stuck at `LIVE` with a frozen `updated_at`, displaying as "idle" on the dashboard indefinitely.

**Example:** Session `b57f6418` (`clever-jumping-bear`) — stuck at `state=LIVE, last_hook=UserPromptSubmit`, idle for 98 minutes, showing "idle" when it should show "ended".

## Root Cause

Claude Code changed behavior — previously fired `SessionEnd` for the parent before spawning a child session. Now the parent just goes silent. The hook-based live session tracker (`live_session_tracker.py`) only updates state when hooks arrive, so silence = frozen state.

## Detection Approaches Evaluated

### A. Heuristic timeout (`LIVE + idle > 5min → ENDED`)
- **Rejected.** False-positives legitimate idle sessions where user walked away.

### B. Hook-based at `SessionStart` (same project + idle = handoff)
- **Rejected.** Could false-positive parallel sessions for the same project.

### C. Hook-based at `UserPromptSubmit` via `leafUuid`
- Read first 10 lines of new session's JSONL for `leafUuid` (context-loading summaries).
- If present → definitively a handoff.
- **Problem:** Mapping `leafUuid` (message UUID) → parent session UUID requires SQLite, which is stale (one-shot indexing at API startup). Viable as future enhancement once periodic re-indexing exists.

### D. Periodic reconciliation via filesystem mtime (selected)
- Background task checks live session state files every N seconds.
- For each stuck session, checks if a **newer JSONL** exists in the same project directory.
- Newer file = concrete filesystem-level evidence that the session was replaced.
- **No false positives.** Self-healing. No JSONL content parsing needed.

## Key Observations

### Why mtime comparison is accurate

When Session A hands off to Session B:
1. Session A's JSONL stops being written to (no more hooks → no more messages)
2. Session B's JSONL is created and actively written to
3. `Session_B.mtime > Session_A.mtime` is a concrete, filesystem-level signal
4. Only requires `stat()` calls — no file content parsing

### Live session state file format

```
~/.claude_karma/live-sessions/{slug}.json
```
```json
{
  "session_id": "b57f6418-...",
  "slug": "clever-jumping-bear",
  "state": "LIVE",
  "transcript_path": "~/.claude/projects/{encoded}/{uuid}.jsonl",
  "updated_at": "2026-02-15T18:26:53Z",
  "last_hook": "UserPromptSubmit"
}
```

The `transcript_path` gives us the JSONL file path and project directory.

## Design

### Algorithm

```
Every 60 seconds:

for each state_file in ~/.claude_karma/live-sessions/*.json:
    if state NOT IN (LIVE, STOPPED, STALE):
        continue  # Already ended or starting

    if idle_seconds < 120:
        continue  # Still fresh, give it time

    project_dir = transcript_path.parent
    session_jsonl = Path(transcript_path)
    session_mtime = session_jsonl.stat().st_mtime

    # Check if a NEWER session JSONL exists in the same project
    newer_exists = any(
        f.stat().st_mtime > session_mtime
        for f in project_dir.glob("*.jsonl")
        if f.stem != session_uuid and not f.name.startswith("agent-")
    )

    if newer_exists:
        mark_as_ended(end_reason="session_handoff", last_hook="Reconciler")
```

### Edge Cases

| Scenario | Behavior | Why it's safe |
|----------|----------|---------------|
| Parallel sessions (both active) | Both receiving hooks → neither idle > 120s → not touched | Idle threshold protects active sessions |
| User walked away (no new session) | No newer JSONL in project → not touched | Requires concrete evidence of replacement |
| Session resumed (same slug) | Hook tracker handles via slug-based files | Reconciler only acts on different session UUIDs |
| API restart during handoff | Reconciler catches it on next run | Self-healing by design |
| Very long-running session (big build) | JSONL still being written → mtime stays fresh → session's own JSONL is the "newest" | mtime comparison is relative, not absolute |

### Parameters

| Parameter | Value | Rationale |
|-----------|-------|-----------|
| Check interval | 60s | Frequent enough to catch stuck sessions quickly, light enough to not waste cycles |
| Idle threshold | 120s | 2 minutes — long enough for slow operations (builds, large file reads), short enough to not leave sessions stuck for long |
| End reason | `"session_handoff"` | Distinguishes from normal `SessionEnd` hook endings |
| Last hook value | `"Reconciler"` | Makes it clear this was auto-detected, not hook-driven |

## Implementation

### Where it runs

In `api/main.py` lifespan — as a background `asyncio` task that runs alongside the API. Cancelled on shutdown.

### Files to modify

| File | Change |
|------|--------|
| `api/main.py` | Add reconciler background task to lifespan |
| `api/services/session_reconciler.py` | New file — reconciliation logic |
| `hooks/live_session_tracker.py` | Revert `end_stale_sessions_for_project` (replaced by reconciler) |

### Dependencies

- `pathlib` for filesystem stat
- `json` for reading state files
- Reuses `write_state_atomic` from `live_session_tracker.py` for safe state updates (or direct JSON write since we're in the API process, not a hook)

### Monitoring

- Log each reconciled session: `"Reconciler: ended session {slug} (idle {idle}s, replaced by newer JSONL)"`
- Expose count via `/live-sessions` response or `/health` endpoint
- `end_reason="session_handoff"` queryable in state files

## Open Questions

1. **Should the reconciler also clean up very old state files?** Currently `POST /live-sessions/cleanup-old` handles sessions > 3 hours old. The reconciler could subsume this.

2. **Should we also check JSONL content (first 10 lines for `leafUuid`)?** This would confirm the handoff definitively but adds I/O. The mtime check alone seems sufficient and is faster.

3. **Dashboard UX** — Should "auto-ended (handoff)" display differently from "ended"? The `end_reason` field supports this.
