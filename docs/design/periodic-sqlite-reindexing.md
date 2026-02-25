# Periodic SQLite Re-indexing

> Background timer that keeps the SQLite index fresh with newly created and modified sessions.

## Problem

The SQLite indexer runs **once at API startup** and never again. Sessions created after the API launches are not in the database until the next restart or manual `POST /admin/reindex`. This causes:

1. **Stale search results** — New sessions don't appear in search/listing until restart
2. **Missing chain data** — `session_leaf_refs` and `message_uuids` tables are incomplete for new sessions, breaking `leaf_uuid`-based chain detection
3. **JSONL fallback overhead** — API endpoints fall back to expensive JSONL parsing for data not in SQLite
4. **Blocked future features** — Real-time `leafUuid`-based handoff detection (Layer 3) requires fresh `message_uuids` data

## Current State

### Indexing Architecture

```
API Startup
    │
    ▼
run_background_sync()          ← daemon thread, runs ONCE
    │
    ├─ sync_all_projects()     ← walks ~/.claude/projects/
    │   ├─ sync_project()      ← per-project, compares mtime
    │   │   └─ _index_session()  ← parses JSONL → SQLite upsert
    │   ├─ _cleanup_stale_sessions()
    │   └─ _update_project_summaries()
    │
    └─ _ready.set()            ← signals API to use SQLite path
```

### What gets indexed per session

| Table | Data | Query Use |
|-------|------|-----------|
| `sessions` | UUID, slug, project, timestamps, tokens, cost, models | Listing, search, analytics |
| `session_tools` | Tool name → count | Tool usage analytics |
| `session_skills` | Skill name → count | Skill usage analytics |
| `session_commands` | Command name → count | Command analytics |
| `message_uuids` | Message UUID → session UUID (428K+ rows) | Chain detection via leaf_uuid |
| `session_leaf_refs` | Session → leaf_uuid references (2,367 rows) | Chain detection |
| `subagent_invocations` | Agent type, tokens, cost, duration | Agent analytics |
| `subagent_tools` | Tool usage per subagent invocation | Agent tool breakdown |
| `projects` | Aggregated project summaries | Project listing |

### Incremental by design

The indexer already supports incremental syncing:
```python
# Skip if mtime hasn't changed
if uuid in db_mtimes and abs(db_mtimes[uuid] - current_mtime) < 0.001:
    stats["skipped"] += 1
    continue
```

Only sessions with changed `st_mtime` are re-parsed. This makes repeated runs cheap.

### Performance baseline

From startup logs (typical run on this machine):
- ~1400 sessions across all projects
- Full initial index: ~15-30 seconds
- Incremental re-index (no changes): < 1 second (all skipped by mtime)
- Incremental re-index (10 changed files): ~2-3 seconds

## Design

### Background Timer

```python
async def periodic_reindex(interval_seconds: int = 300):
    """Re-index changed sessions every N seconds."""
    while True:
        await asyncio.sleep(interval_seconds)
        try:
            conn = get_writer_db()
            stats = sync_all_projects(conn)
            logger.info("Periodic reindex: %s", stats)
        except Exception as e:
            logger.warning("Periodic reindex failed: %s", e)
```

Runs as an `asyncio` background task in the API lifespan, alongside the live session reconciler.

### Why asyncio task wrapping a thread

`sync_all_projects()` is synchronous (heavy file I/O + SQLite writes). Options:

| Approach | Pros | Cons |
|----------|------|------|
| `asyncio.to_thread()` | Non-blocking, clean | Requires Python 3.9+ (we have it) |
| Daemon thread with `time.sleep` | Simple, current pattern | Not coordinated with async lifespan |
| `asyncio.run_in_executor()` | Non-blocking | More boilerplate |

**Selected:** `asyncio.to_thread(sync_all_projects, conn)` inside an async loop. Keeps the event loop free while the indexer does I/O.

### Parameters

| Parameter | Value | Rationale |
|-----------|-------|-----------|
| Interval | 300s (5 min) | Balances freshness vs CPU cost. Incremental runs are cheap (<1s when few changes). |
| Initial delay | Skip first run | The startup indexer already handles the initial sync. First periodic run at T+5min. |
| Lock | Existing `_indexing_lock` | Prevents overlapping runs (already implemented in `sync_all_projects`) |

### Integration with startup indexer

```
T=0s    API starts
        └─ run_background_sync() in daemon thread (existing)
T=15s   Initial index complete, _ready.set()
T=300s  First periodic reindex (incremental, fast)
T=600s  Second periodic reindex
...
```

The startup indexer and periodic reindexer share the same `_indexing_lock`, so they can't overlap.

## Benefits Unlocked

### Immediate

1. **Fresh session listings** — New sessions appear in search within 5 minutes instead of never
2. **Fresh analytics** — Token costs, tool usage, model distribution stay current
3. **Reduced JSONL fallback** — Fewer expensive file-parsing operations

### For Live Session Reconciler (Layer 1)

4. **No direct dependency** — The reconciler uses filesystem mtime, not SQLite. But fresh SQLite enables richer chain info on the dashboard.

### For Future leafUuid Detection (Layer 3)

5. **Fresh `message_uuids`** — Parent session's message UUIDs are in SQLite within 5 minutes of being written
6. **Fresh `session_leaf_refs`** — Child session's leaf references are indexed, enabling instant chain queries
7. **Enables hook-based detection** — At `UserPromptSubmit`, query `message_uuids` to find parent session → mark as ended in real-time

## Implementation

### Files to modify

| File | Change |
|------|--------|
| `api/main.py` | Add periodic reindex task to lifespan |
| `api/db/indexer.py` | Add `run_periodic_sync(interval)` function (thin wrapper) |

### Existing code reuse

Almost everything is already built:
- `sync_all_projects()` — incremental by mtime, handles all tables
- `_indexing_lock` — prevents overlapping runs
- `_last_sync_complete` — tracks last sync timestamp
- `get_last_health()` — exposes metrics

The only new code is the async timer loop and its integration into the API lifespan.

### Monitoring

- Existing log: `"Index sync complete: N total, N indexed, N skipped, N errors in Xs"`
- `GET /health` already exposes `db.ready` and health metrics
- Add `last_periodic_sync` timestamp to health response

## Open Questions

1. **Interval tuning** — 5 minutes is a starting point. Could be configurable via `Settings`. For heavy usage, 2 minutes might be better. For light usage, 10 minutes saves resources.

2. **Should we expose a manual trigger?** — `POST /admin/reindex` already exists. Should the periodic task also run on-demand (e.g., when a new session is detected via live session hooks)?

3. **Hook-triggered incremental index** — Instead of (or in addition to) a timer, we could trigger a single-session index when `SessionEnd` hook fires. This would give near-instant freshness for completed sessions. But adds coupling between hooks and the DB layer.

4. **WAL checkpoint frequency** — With more frequent writes, the WAL file may grow. Should we add periodic `PRAGMA wal_checkpoint(PASSIVE)` calls?
