# SQLite Metadata Index — Implementation Guide

## Overview

The SQLite metadata index is a **derived cache layer** that sits between the raw JSONL session files (source of truth) and the API endpoints. It replaces multiple ad-hoc caching systems with a single, queryable database.

### Problem

The original architecture loaded all session data by scanning JSONL files on every request:

```
Request → Scan ~/.claude/projects/**/*.jsonl → Parse each file → Filter in Python → Respond
```

This caused:
- **2-5 second response times** for `/sessions/all` (1200+ sessions)
- **3 separate cache systems** with independent staleness bugs (`sessions-index.json`, `SessionTitleCache`, `AgentUsageIndex`)
- **No server-side search** — FTS was impossible without loading every file
- **Full data scans** for pagination (load all, then slice)

### Solution

SQLite as a derived metadata index:

```
Startup → Background thread syncs JSONL → SQLite
Request → SQL query → 1-5ms response
```

The JSONL files remain the source of truth. SQLite is rebuilt incrementally via mtime comparison — only changed files are re-indexed.

---

## Architecture

### Module Structure

```
api/db/
├── __init__.py      # Public API: get_db, close_db, sync_all_projects, is_db_ready
├── connection.py    # Singleton SQLite connection (WAL mode, performance pragmas)
├── schema.py        # DDL: 6 tables, FTS5, triggers, indexes, versioning
├── indexer.py       # JSONL → SQLite incremental sync engine
└── queries.py       # Query functions used by routers (Phase 1+)
```

### Database Location

```
~/.claude_karma/metadata.db        # Main database
~/.claude_karma/metadata.db-wal    # WAL journal (auto-managed)
~/.claude_karma/metadata.db-shm    # Shared memory (auto-managed)
```

### Connection Settings

| Pragma | Value | Why |
|--------|-------|-----|
| `journal_mode` | WAL | Concurrent reads during writes |
| `synchronous` | NORMAL | Safe with WAL, faster than FULL |
| `cache_size` | 64MB | Keeps hot pages in memory |
| `mmap_size` | 256MB | Memory-mapped I/O for reads |
| `busy_timeout` | 5000ms | Wait for locks instead of failing |

### Feature Flag

```bash
# Disable SQLite (falls back to JSONL everywhere)
CLAUDE_KARMA_USE_SQLITE=false uvicorn main:app

# Enable (default)
CLAUDE_KARMA_USE_SQLITE=true
```

---

## Schema (v1)

### Tables

#### `sessions` — Core session metadata
Primary table replacing `sessions-index.json` and in-memory session scanning.

| Column | Type | Description |
|--------|------|-------------|
| `uuid` | TEXT PK | Session UUID (JSONL filename stem) |
| `slug` | TEXT | Human-readable session slug |
| `project_encoded_name` | TEXT NOT NULL | Encoded project path (`-Users-me-repo`) |
| `project_path` | TEXT | Decoded original path (`/Users/me/repo`) |
| `start_time` | TEXT | ISO 8601 timestamp |
| `end_time` | TEXT | ISO 8601 timestamp |
| `message_count` | INTEGER | Total messages in session |
| `duration_seconds` | REAL | Session duration |
| `input_tokens` | INTEGER | Total input tokens |
| `output_tokens` | INTEGER | Total output tokens |
| `cache_creation_tokens` | INTEGER | Cache creation tokens |
| `cache_read_tokens` | INTEGER | Cache read tokens |
| `total_cost` | REAL | Computed USD cost |
| `initial_prompt` | TEXT | First user message (truncated to 500 chars) |
| `git_branch` | TEXT | Primary git branch |
| `models_used` | TEXT | JSON array of model IDs |
| `session_titles` | TEXT | JSON array of titles |
| `is_continuation_marker` | INTEGER | Boolean: continuation session |
| `was_compacted` | INTEGER | Boolean: had context compaction |
| `compaction_count` | INTEGER | Number of compactions |
| `file_snapshot_count` | INTEGER | File history snapshots |
| `subagent_count` | INTEGER | Number of subagent JSONL files |
| `jsonl_mtime` | REAL NOT NULL | File modification time (for incremental sync) |
| `jsonl_size` | INTEGER | File size in bytes |
| `indexed_at` | TEXT | When this row was last updated |

**Indexes:** `project_encoded_name`, `start_time DESC`, `slug`, `(project_encoded_name, git_branch)`, `jsonl_mtime`

#### `sessions_fts` — Full-text search (FTS5)
Virtual table synced via triggers, enabling instant search across:
- `uuid`, `slug`, `initial_prompt`, `session_titles`, `project_path`

Sync triggers: `sessions_fts_insert`, `sessions_fts_delete`, `sessions_fts_update`

#### `session_tools` — Tool usage per session
| Column | Type | Description |
|--------|------|-------------|
| `session_uuid` | TEXT FK | References `sessions.uuid` |
| `tool_name` | TEXT | Tool name (Read, Write, Edit, etc.) |
| `count` | INTEGER | Times used in session |

Composite PK: `(session_uuid, tool_name)`. Cascades on session delete.

#### `session_skills` — Skill usage per session
Same structure as `session_tools` but for skills (commit, review-pr, etc.)

#### `subagent_invocations` — Subagent details
Replaces `AgentUsageIndex` for agent analytics.

| Column | Type | Description |
|--------|------|-------------|
| `id` | INTEGER PK | Auto-increment |
| `session_uuid` | TEXT FK | Parent session |
| `agent_id` | TEXT | Unique agent identifier |
| `subagent_type` | TEXT | Agent type (e.g., `oh-my-claudecode:executor`) |
| `input_tokens` | INTEGER | Agent's input tokens |
| `output_tokens` | INTEGER | Agent's output tokens |
| `cost_usd` | REAL | Agent's cost |
| `duration_seconds` | REAL | Agent execution time |
| `started_at` | TEXT | ISO 8601 timestamp |

#### `projects` — Derived project summaries
Pre-aggregated from `sessions` table during sync. Used for fast project filter dropdowns.

| Column | Type | Description |
|--------|------|-------------|
| `encoded_name` | TEXT PK | Encoded project path |
| `project_path` | TEXT | Decoded path |
| `session_count` | INTEGER | Sessions in project |
| `last_activity` | TEXT | Most recent session start |

### Schema Versioning

The `schema_version` table tracks applied migrations:

```sql
SELECT MAX(version) FROM schema_version;  -- Currently: 1
```

Future schema changes increment `SCHEMA_VERSION` in `schema.py` and add migration logic in `ensure_schema()`.

---

## Indexer

### How It Works

1. **Startup**: `main.py` spawns a daemon thread running `run_background_sync()`
2. **Walk**: Iterates `~/.claude/projects/*/` directories
3. **Compare**: For each `*.jsonl` file, compares `stat().st_mtime` against `sessions.jsonl_mtime`
4. **Skip**: If mtime matches (within 0.001s), skip
5. **Index**: If changed, parse via `Session.from_path()` and upsert all metadata
6. **Cleanup**: Remove DB entries for JSONL files that no longer exist on disk
7. **Summarize**: Rebuild `projects` table from aggregated session data
8. **Signal**: Set `_ready` event so request handlers know SQLite is available

### Performance

| Operation | Time | Notes |
|-----------|------|-------|
| Cold start (1286 sessions) | ~16s | One-time, background thread |
| Incremental sync (no changes) | ~0.05s | 342x faster than cold start |
| Incremental sync (9 changed) | ~0.06s | Only re-parses changed files |

### Resilience

- **Non-blocking**: API serves requests via JSONL fallback while indexing runs
- **Idempotent**: Uses `INSERT OR REPLACE`, safe to run repeatedly
- **Error-isolated**: Individual session errors are logged and skipped
- **Ready gating**: `is_db_ready()` returns `False` until first sync completes

---

## Completed Phases

### Phase 0: Foundation (db module)

**Goal**: Create the SQLite infrastructure with zero router changes.

**Files created:**
- `api/db/__init__.py` — Module exports
- `api/db/connection.py` — Singleton connection with WAL + pragmas
- `api/db/schema.py` — DDL with 6 tables, FTS5, triggers, indexes
- `api/db/indexer.py` — mtime-based incremental JSONL-to-SQLite sync
- `api/tests/test_db.py` — 16 tests (schema, CRUD, FTS, aggregation)

**Files modified:**
- `api/config.py` — Added `use_sqlite` setting + `sqlite_db_path` property
- `api/main.py` — Background indexer thread on startup, `close_db()` on shutdown

**Verification:**
- 16/16 tests pass
- Cold index: 1286 sessions, 0 errors
- Incremental: 0.05s
- FTS search: working
- Existing test suite: 0 regressions

### Phase 1: `/sessions/all` endpoint

**Goal**: Wire the heaviest endpoint to SQLite with automatic fallback.

**Files created:**
- `api/db/queries.py` — `query_all_sessions()` with dynamic WHERE, FTS5 JOIN, pagination, status counting

**Files modified:**
- `api/routers/sessions.py` — `get_all_sessions()` now:
  1. Checks `settings.use_sqlite` and `is_db_ready()`
  2. Calls `_get_all_sessions_sqlite()` (SQLite path)
  3. On any exception, falls back to `_get_all_sessions_jsonl()` (original code)

**How the SQLite path works:**

```python
def get_all_sessions(...):
    if settings.use_sqlite:
        if is_db_ready():
            return _get_all_sessions_sqlite(...)   # Fast path
    return _get_all_sessions_jsonl(...)             # Fallback
```

The SQLite query function handles:
- **Filtering**: project, branch, date range via WHERE clauses
- **Search**: FTS5 MATCH with scope support (titles, prompts, both)
- **Status**: Active/completed computed via `julianday()` time math
- **Pagination**: SQL LIMIT/OFFSET with total count
- **Project options**: From precomputed `projects` table

**Performance (live, 1278 sessions):**

| Query | SQLite | JSONL (est.) | Speedup |
|-------|--------|-------------|---------|
| No filters (200 rows) | 3ms | 2-5s | ~1000x |
| FTS search | 0.8ms | 1-3s | ~2000x |
| Project filter | 2.1ms | 1-3s | ~1000x |
| Paginated (10 rows) | 0.5ms | same | ~5000x |

**Verification:**
- 67/67 tests pass (16 DB + 51 session API)
- Live endpoint: HTTP 200, correct response schema
- Pagination: correct page/total_pages calculation
- Search: FTS5 returns accurate results
- Filters: project, status, search all work
- Feature flag: `CLAUDE_KARMA_USE_SQLITE=false` disables cleanly

---

## Next Phases

### Phase 2: `/analytics` endpoint

**Goal**: Replace `_calculate_analytics_from_sessions()` with SQL aggregation.

**What it replaces**: The current analytics endpoint loads ALL sessions via `Session.from_path()` and computes aggregates in Python (total cost, token counts, session counts, tool/model breakdowns).

**SQL approach:**
```sql
-- Cost/token aggregation (instant)
SELECT COUNT(*), SUM(total_cost), SUM(input_tokens), SUM(output_tokens)
FROM sessions WHERE project_encoded_name = ?

-- Tool usage breakdown
SELECT tool_name, SUM(count) as total
FROM session_tools st
JOIN sessions s ON st.session_uuid = s.uuid
WHERE s.project_encoded_name = ?
GROUP BY tool_name ORDER BY total DESC

-- Model usage breakdown
-- Requires JSON extraction or a denormalized session_models table
```

**Files to modify:**
- `api/db/queries.py` — Add `query_project_analytics()` function
- `api/routers/analytics.py` — SQLite-first with JSONL fallback (same pattern as Phase 1)

**Expected impact**: Analytics endpoint goes from ~3-10s to <10ms.

### Phase 3: FTS5 search

**Goal**: Replace brute-force `SessionFilter.matches_metadata()` with FTS5.

**What it replaces**: `session_filter.py` currently loads session titles, prompts, and slugs then does Python string matching across all sessions.

**Already built**: FTS5 virtual table + sync triggers exist from Phase 0. `query_all_sessions()` already uses FTS5. This phase just wires the remaining search surfaces (e.g., session detail search within a project).

**Files to modify:**
- `api/db/queries.py` — Add `search_sessions()` for project-scoped search
- `api/routers/projects.py` — Use SQLite search for project session listings

### Phase 4: Agent analytics

**Goal**: Replace `AgentUsageIndex` with `subagent_invocations` table queries.

**What it replaces**: `agent_analytics.py` scans ALL project dirs, loads JSONL files in parallel via `ProcessPoolExecutor`, builds an in-memory index, then caches to `~/.claude_karma/agent-usage-index.json`.

**Approach**: The `subagent_invocations` table is already in the schema but not yet populated by the indexer. Phase 4 adds:
1. Subagent JSONL parsing in `_index_session()`
2. SQL aggregation queries in `queries.py`
3. Router migration in `agent_analytics.py`

**Files to modify:**
- `api/db/indexer.py` — Parse subagent metadata during indexing
- `api/db/queries.py` — Add `query_agent_analytics()` function
- `api/routers/agent_analytics.py` — SQLite-first with fallback

### Phase 5: Retire old caches

**Goal**: Remove the legacy caching systems once all endpoints use SQLite.

**What gets removed:**
- `services/session_title_cache.py` — Replaced by FTS5
- `routers/agent_analytics.py` `AgentUsageIndex` class — Replaced by `subagent_invocations`
- `sessions-index.json` dependency in `models/session_index.py` — Replaced by `sessions` table
- Various `BoundedCache` instances that cached session lists

**Prerequisites**: All of Phases 1-4 must be complete and stable.

---

## Testing

### Running tests

```bash
cd api

# SQLite-specific tests
pytest tests/test_db.py -v

# Session endpoint tests (includes SQLite integration)
pytest tests/api/test_sessions.py -v

# All tests
pytest --ignore=tests/test_plugin.py -v
```

### Test structure

```
tests/test_db.py
├── TestSchema (4 tests)
│   ├── test_schema_version
│   ├── test_tables_exist
│   ├── test_idempotent
│   └── test_indexes_exist
├── TestSessionCRUD (5 tests)
│   ├── test_insert_and_query
│   ├── test_upsert
│   ├── test_project_filter
│   ├── test_ordering_by_start_time
│   └── test_cascade_delete
├── TestFTS (4 tests)
│   ├── test_search_by_prompt
│   ├── test_search_by_title
│   ├── test_search_by_slug
│   └── test_fts_update_trigger
└── TestAggregation (3 tests)
    ├── test_global_aggregation
    ├── test_per_project_aggregation
    └── test_tool_aggregation
```

### Adding tests for new phases

Each phase should add query-level tests to `tests/test_db.py` following the pattern:
1. Insert test data via `_insert_session()` helper
2. Call the query function from `db/queries.py`
3. Assert response shape and values

---

## Troubleshooting

### Database is corrupt or stale

```bash
# Delete and let it rebuild on next startup
rm ~/.claude_karma/metadata.db*
```

### SQLite path not activating

Check the logs on startup:
```
INFO - SQLite background indexing started
INFO - SQLite database ready (WAL mode)
INFO - Index sync complete: 1286 total, ...
```

If you see `"SQLite query failed, falling back to JSONL"`, check the warning message for the specific error.

### Force JSONL fallback

```bash
CLAUDE_KARMA_USE_SQLITE=false uvicorn main:app --reload --port 8000
```

### Verify database contents

```bash
cd api
python3 -c "
from db.connection import get_db
conn = get_db()
print('Sessions:', conn.execute('SELECT COUNT(*) FROM sessions').fetchone()[0])
print('Projects:', conn.execute('SELECT COUNT(*) FROM projects').fetchone()[0])
print('Tools:', conn.execute('SELECT COUNT(*) FROM session_tools').fetchone()[0])
print('FTS entries:', conn.execute('SELECT COUNT(*) FROM sessions_fts').fetchone()[0])
"
```
