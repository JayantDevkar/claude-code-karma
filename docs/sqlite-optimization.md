# SQLite Optimization Roadmap

Comprehensive plan for replacing JSONL scanning with SQLite lookups across all API endpoints, following the pattern established in `/sessions/all` (Phase 0+1) and `/plans/` (Phase 2).

---

## Table of Contents

1. [Background](#background)
2. [SQLite Schema (Current)](#sqlite-schema-current)
3. [Pattern: SQLite-First with JSONL Fallback](#pattern-sqlite-first-with-jsonl-fallback)
4. [Already Optimized](#already-optimized)
5. [Phase 1: Global Aggregation Endpoints](#phase-1-global-aggregation-endpoints)
6. [Phase 2: Project-Level Endpoints](#phase-2-project-level-endpoints)
7. [Phase 3: Agent Analytics (Indexer Extension)](#phase-3-agent-analytics-indexer-extension)
8. [New db/queries.py Functions Needed](#new-dbqueriespy-functions-needed)
9. [Implementation Checklist](#implementation-checklist)

---

## Background

Claude Karma API parses Claude Code's local JSONL files to serve session data. Many endpoints currently scan **all** sessions across **all** projects on every request, parsing JSONL files to extract metadata that is already available in SQLite.

The SQLite index (`db/`) was introduced in commits `2a532b5` and `516290e` to cache session metadata. The indexer runs on startup in a background thread and incrementally syncs JSONL changes via mtime comparison.

### The Problem

| Endpoint | Current Behavior | Time |
|----------|------------------|------|
| `/analytics` | Parses every JSONL file for token/tool/model stats | 1-5s |
| `/analytics/dashboard` | Calls `_get_stats_for_period()` up to 3x, each scanning all projects | 1-3s |
| `/skills/usage` | Iterates ALL projects x ALL sessions, calls `get_skills_used()` | 2-5s |
| `/projects/{name}` | Loads all sessions with `list_sessions()`, builds summaries | 0.5-2s |
| `/agents/usage` | Parallel JSONL scan of all sessions + subagent files | 3-10s |

### The Solution

Replace JSONL scanning with SQL queries against the pre-built SQLite index. All required data is already indexed (or can be with minor indexer additions).

---

## SQLite Schema (Current)

```sql
-- Core session metadata
CREATE TABLE sessions (
    uuid TEXT PRIMARY KEY,
    slug TEXT,
    project_encoded_name TEXT NOT NULL,
    project_path TEXT,
    start_time TEXT,
    end_time TEXT,
    message_count INTEGER DEFAULT 0,
    duration_seconds REAL,
    input_tokens INTEGER DEFAULT 0,
    output_tokens INTEGER DEFAULT 0,
    cache_creation_tokens INTEGER DEFAULT 0,
    cache_read_tokens INTEGER DEFAULT 0,
    total_cost REAL DEFAULT 0,
    initial_prompt TEXT,
    git_branch TEXT,
    models_used TEXT,          -- JSON array: ["claude-opus-4-5-...", ...]
    session_titles TEXT,       -- JSON array
    is_continuation_marker INTEGER DEFAULT 0,
    was_compacted INTEGER DEFAULT 0,
    compaction_count INTEGER DEFAULT 0,
    file_snapshot_count INTEGER DEFAULT 0,
    subagent_count INTEGER DEFAULT 0,
    jsonl_mtime REAL NOT NULL,
    jsonl_size INTEGER DEFAULT 0,
    indexed_at TEXT DEFAULT (datetime('now'))
);

-- Indexes
CREATE INDEX idx_sessions_project ON sessions(project_encoded_name);
CREATE INDEX idx_sessions_start ON sessions(start_time DESC);
CREATE INDEX idx_sessions_slug ON sessions(slug);
CREATE INDEX idx_sessions_branch ON sessions(project_encoded_name, git_branch);

-- FTS5 for search
CREATE VIRTUAL TABLE sessions_fts USING fts5(
    uuid, slug, initial_prompt, session_titles, project_path,
    content=sessions, content_rowid=rowid
);

-- Tool usage per session
CREATE TABLE session_tools (
    session_uuid TEXT NOT NULL,
    tool_name TEXT NOT NULL,
    count INTEGER DEFAULT 1,
    PRIMARY KEY (session_uuid, tool_name)
);

-- Skill usage per session
CREATE TABLE session_skills (
    session_uuid TEXT NOT NULL,
    skill_name TEXT NOT NULL,
    count INTEGER DEFAULT 1,
    PRIMARY KEY (session_uuid, skill_name)
);

-- Subagent invocations
CREATE TABLE subagent_invocations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_uuid TEXT NOT NULL,
    agent_id TEXT NOT NULL,
    subagent_type TEXT,
    input_tokens INTEGER DEFAULT 0,
    output_tokens INTEGER DEFAULT 0,
    cost_usd REAL DEFAULT 0,
    duration_seconds REAL DEFAULT 0,
    started_at TEXT
);

-- Tool usage per subagent invocation
CREATE TABLE subagent_tools (
    invocation_id INTEGER NOT NULL,
    tool_name TEXT NOT NULL,
    count INTEGER DEFAULT 1,
    PRIMARY KEY (invocation_id, tool_name),
    FOREIGN KEY (invocation_id) REFERENCES subagent_invocations(id) ON DELETE CASCADE
);

-- Project summary (derived)
CREATE TABLE projects (
    encoded_name TEXT PRIMARY KEY,
    project_path TEXT,
    session_count INTEGER DEFAULT 0,
    last_activity TEXT,
    updated_at TEXT DEFAULT (datetime('now'))
);
```

### What's Populated vs Not

| Table | Populated by Indexer | Notes |
|-------|---------------------|-------|
| `sessions` | Yes | Full metadata from `_index_session()` |
| `session_tools` | Yes | Tool name + count per session |
| `session_skills` | Yes | Skill name + count per session |
| `subagent_invocations` | **Yes** | Populated with type, tokens, cost, duration |
| `subagent_tools` | **Yes** | Tool name + count per subagent invocation |
| `projects` | Yes | Derived from `_update_project_summaries()` |

---

## Pattern: SQLite-First with JSONL Fallback

Every optimized endpoint follows this pattern (established in `routers/plans.py`):

```python
from config import settings

@router.get("/example")
def my_endpoint():
    # SQLite fast path
    if settings.use_sqlite:
        try:
            from db.indexer import is_db_ready
            if is_db_ready():
                return _my_endpoint_sqlite(...)
        except Exception as e:
            logger.warning("SQLite query failed, falling back: %s", e)

    # JSONL fallback (existing code, unchanged)
    return _my_endpoint_jsonl(...)
```

Key principles:
- SQLite path is primary — agent analytics endpoints are now SQLite-only
- Other endpoints retain JSONL fallback for compatibility
- `is_db_ready()` checks that the background indexer has completed its initial sync
- `settings.use_sqlite` is a config toggle (default: True)

---

## Already Optimized

| Endpoint | Commit | Technique |
|----------|--------|-----------|
| `GET /sessions/all` | `2a532b5` | `query_all_sessions()` — paginated SQL with FTS5 search, status counts |
| `GET /plans/with-context` | `516290e` | `query_sessions_by_slugs()` — batch slug lookup, single query for all plans |
| `GET /plans/{slug}/context` | `516290e` | `query_session_by_slug()` — O(1) indexed slug lookup |
| `GET /plans/{slug}/sessions` | `516290e` | SQLite for creator lookup, raw-bytes pre-filter for related sessions |

---

## Phase 1: Global Aggregation Endpoints

These scan ALL sessions across ALL projects. Highest impact optimizations.

### 1.1 `GET /analytics/dashboard`

**File:** `routers/analytics.py` — `get_dashboard_stats()` (line 596)

**Current:** Calls `_get_stats_for_period()` up to 3 times (today → yesterday → this week). Each call iterates all projects, loads sessions with `list_sessions_filtered()`, sums durations.

**SQLite replacement:**

```sql
-- Single query replaces 3x full project scans
SELECT
    COUNT(*) as session_count,
    COUNT(DISTINCT project_encoded_name) as projects_active,
    SUM(duration_seconds) as total_duration
FROM sessions
WHERE start_time BETWEEN :start AND :end
```

**New query function:** `query_dashboard_stats(conn, start_dt, end_dt) -> dict | None`

**Estimated speedup:** 100x (3 SQL queries vs 3 full JSONL scans)

---

### 1.2 `GET /analytics` and `GET /analytics/projects/{name}`

**File:** `routers/analytics.py` — `get_global_analytics()` (line 83), `get_project_analytics()` (line 163)

**Current:** Loads all sessions, calls `session.get_usage_summary()`, `session.get_models_used()`, `session.get_tools_used()` per session. Falls back from SessionIndexEntry but index lacks token/tool data.

**SQLite replacement:**

```sql
-- Session aggregates
SELECT
    COUNT(*) as total_sessions,
    SUM(input_tokens) as total_input,
    SUM(output_tokens) as total_output,
    SUM(total_cost) as total_cost,
    SUM(duration_seconds) as total_duration,
    SUM(cache_read_tokens) as cache_read,
    SUM(cache_creation_tokens + cache_read_tokens + input_tokens) as cacheable
FROM sessions
WHERE (:project IS NULL OR project_encoded_name = :project)
  AND (:start IS NULL OR start_time >= :start)
  AND (:end IS NULL OR start_time <= :end)

-- Tool aggregates (separate query)
SELECT tool_name, SUM(count) as total
FROM session_tools st
JOIN sessions s ON st.session_uuid = s.uuid
WHERE (:project IS NULL OR s.project_encoded_name = :project)
  AND (:start IS NULL OR s.start_time >= :start)
GROUP BY tool_name

-- Models used (needs JSON parsing in Python)
SELECT models_used FROM sessions
WHERE models_used IS NOT NULL
  AND (:project IS NULL OR project_encoded_name = :project)

-- Sessions by date (for temporal heatmap)
SELECT
    start_time
FROM sessions
WHERE start_time IS NOT NULL
  AND (:project IS NULL OR project_encoded_name = :project)
```

**New query function:** `query_analytics(conn, project=None, start_dt=None, end_dt=None, tz_offset=0) -> dict`

**Notes:**
- `models_used` is stored as JSON array string — parse in Python, aggregate with Counter
- Temporal heatmap still needs per-session start_time — but just the timestamp, no JSONL parse
- Work mode distribution derived from tool aggregates

**Estimated speedup:** 100-1000x

---

### 1.3 `GET /skills/usage`

**File:** `routers/skills.py` — `get_skill_usage()` (line 420)

**Current:** Iterates ALL projects, ALL sessions, calls `session.get_skills_used()` on every one. Pure O(projects x sessions) JSONL scan.

**SQLite replacement:**

```sql
SELECT
    sk.skill_name,
    SUM(sk.count) as total_count
FROM session_skills sk
JOIN sessions s ON sk.session_uuid = s.uuid
WHERE (:project IS NULL OR s.project_encoded_name = :project)
GROUP BY sk.skill_name
ORDER BY total_count DESC
LIMIT :limit
```

**New query function:** `query_skill_usage(conn, project=None, limit=50) -> list[dict]`

**Estimated speedup:** 1000x

---

### 1.4 `GET /skills/{name}/sessions`

**File:** `routers/skills.py` — `get_skill_sessions()` (line 477)

**Current:** Iterates ALL projects, ALL sessions to find those using a specific skill. Builds full `SessionSummary` for each match.

**SQLite replacement:**

```sql
SELECT
    s.uuid, s.slug, s.project_encoded_name, s.message_count,
    s.start_time, s.end_time, s.duration_seconds,
    s.models_used, s.subagent_count, s.initial_prompt,
    s.git_branch, s.session_titles
FROM sessions s
JOIN session_skills sk ON s.uuid = sk.session_uuid
WHERE sk.skill_name = :skill_name
ORDER BY s.start_time DESC
LIMIT :limit OFFSET :offset
```

**New query function:** `query_sessions_by_skill(conn, skill_name, limit=100, offset=0) -> dict`

**Estimated speedup:** 500x

---

## Phase 2: Project-Level Endpoints

These scan all sessions within a single project.

### 2.1 `GET /projects/{name}`

**File:** `routers/projects.py` — `get_project()` (line 230)

**Current:** Loads ALL sessions via `project.list_sessions()`, filters empty ones, builds chain info, calls `session_to_summary()` for each (parses JSONL for models_used, subagent_count, initial_prompt, etc.).

**SQLite replacement:**

```sql
-- Paginated session list
SELECT
    uuid, slug, message_count, start_time, end_time,
    duration_seconds, models_used, subagent_count,
    initial_prompt, git_branch, session_titles,
    is_continuation_marker, was_compacted
FROM sessions
WHERE project_encoded_name = :project
  AND message_count > 0
ORDER BY start_time DESC
LIMIT :limit OFFSET :offset

-- Total count
SELECT COUNT(*) FROM sessions
WHERE project_encoded_name = :project AND message_count > 0
```

**New query function:** `query_project_sessions(conn, project, limit=None, offset=0) -> dict`

**Notes:**
- Chain info can be derived from slug grouping: `SELECT slug, COUNT(*) FROM sessions WHERE project_encoded_name = ? AND slug IS NOT NULL GROUP BY slug HAVING COUNT(*) > 1`
- `session_to_summary()` maps directly to SQLite columns

**Estimated speedup:** 50x

---

### 2.2 `GET /projects/{name}/branches`

**File:** `routers/projects.py` — `get_project_branches()` (line 555)

**Current:** Loads ALL sessions, calls `session.get_git_branches()` per session, manually aggregates branch data.

**SQLite replacement:**

```sql
SELECT
    git_branch as name,
    COUNT(*) as session_count,
    MAX(COALESCE(end_time, start_time)) as last_active
FROM sessions
WHERE project_encoded_name = :project
  AND git_branch IS NOT NULL
GROUP BY git_branch
ORDER BY last_active DESC
```

Active branch detection: the branch(es) from the most recent session.

```sql
SELECT git_branch FROM sessions
WHERE project_encoded_name = :project
ORDER BY start_time DESC
LIMIT 1
```

**New query function:** `query_project_branches(conn, project) -> dict`

**Estimated speedup:** 50x

---

### 2.3 `GET /projects/{name}/chains`

**File:** `routers/projects.py` — `get_project_chains()` (line 443)

**Current:** Loads ALL sessions, groups by slug, builds chain nodes with initial prompts and compaction counts.

**SQLite replacement:**

```sql
-- Get all sessions for slugs that have >1 session (chains)
SELECT
    uuid, slug, start_time, end_time,
    was_compacted, is_continuation_marker,
    message_count, initial_prompt, compaction_count
FROM sessions
WHERE project_encoded_name = :project
  AND slug IN (
      SELECT slug FROM sessions
      WHERE project_encoded_name = :project AND slug IS NOT NULL
      GROUP BY slug HAVING COUNT(*) > 1
  )
ORDER BY slug, start_time ASC
```

**New query function:** `query_project_chains(conn, project) -> dict`

**Estimated speedup:** 50x

---

### 2.4 `GET /projects/{name}/sessions/lookup`

**File:** `routers/projects.py` — `lookup_session()` (line 298)

**Current:** Has fast paths for UUID file check, but slug lookup builds a cache by parsing ALL JSONL files. The `_build_slug_cache()` function calls `Session.from_path()` on every JSONL.

**SQLite replacement:**

```sql
-- Slug match
SELECT uuid, slug, project_encoded_name, project_path,
       message_count, start_time, end_time, initial_prompt
FROM sessions
WHERE slug = :identifier AND project_encoded_name = :project
ORDER BY start_time DESC
LIMIT 1

-- UUID prefix match
SELECT uuid, slug, project_encoded_name, project_path,
       message_count, start_time, end_time, initial_prompt
FROM sessions
WHERE uuid LIKE :prefix_pattern AND project_encoded_name = :project
LIMIT 1
```

**New query function:** `query_session_lookup(conn, project, identifier) -> dict | None`

**Estimated speedup:** 10x (replaces in-memory slug cache)

---

## Phase 3: Agent Analytics (Indexer Extension)

The `subagent_invocations` table exists in the schema but the indexer does not populate it. This phase extends the indexer and replaces the custom `AgentUsageIndex` JSON file.

### 3.1 Extend `db/indexer.py` — `_index_session()`

Add subagent indexing after the existing tool/skill indexing:

```python
# Upsert subagent invocations
conn.execute("DELETE FROM subagent_invocations WHERE session_uuid = ?", (uuid,))
subagents_dir = jsonl_path.parent / uuid / "subagents"
if subagents_dir.exists():
    for agent_path in subagents_dir.glob("agent-*.jsonl"):
        agent = Agent.from_path(agent_path)
        # Extract subagent_type from parent session's Task tool calls
        subagent_type = _get_subagent_type(session, agent.agent_id)
        if subagent_type:
            usage = agent.get_usage_summary()
            duration = 0.0
            if agent.start_time and agent.end_time:
                duration = (agent.end_time - agent.start_time).total_seconds()
            conn.execute(
                """INSERT INTO subagent_invocations
                   (session_uuid, agent_id, subagent_type, input_tokens,
                    output_tokens, cost_usd, duration_seconds, started_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (uuid, agent.agent_id, subagent_type, usage.total_input,
                 usage.output_tokens, usage.calculate_cost(), duration,
                 agent.start_time.isoformat() if agent.start_time else None),
            )
```

**Note:** This makes indexing slower (parses subagent JSONL files) but runs in the background thread. The incremental mtime check means only changed sessions are re-indexed.

---

### 3.2 `GET /agents/usage`

**File:** `routers/agents.py` + `routers/agent_analytics.py`

**Current:** `collect_all_agent_usage()` → `_collect_all_agent_usage_impl()` with its own `AgentUsageIndex` JSON file, parallel JSONL processing with 16 workers.

**SQLite replacement:**

```sql
SELECT
    subagent_type,
    COUNT(*) as total_runs,
    SUM(cost_usd) as total_cost,
    SUM(input_tokens) as total_input,
    SUM(output_tokens) as total_output,
    AVG(duration_seconds) as avg_duration,
    MIN(started_at) as first_used,
    MAX(started_at) as last_used,
    COUNT(DISTINCT s.project_encoded_name) as projects_count
FROM subagent_invocations si
JOIN sessions s ON si.session_uuid = s.uuid
GROUP BY subagent_type
ORDER BY total_runs DESC
```

**New query function:** `query_agent_usage(conn) -> list[dict]`

---

### 3.3 `GET /agents/usage/{type}` and `GET /agents/usage/{type}/history`

**SQLite replacement:**

```sql
-- Detail
SELECT
    COUNT(*) as total_runs,
    SUM(cost_usd) as total_cost,
    SUM(input_tokens) as total_input,
    SUM(output_tokens) as total_output,
    AVG(duration_seconds) as avg_duration,
    MIN(started_at) as first_used,
    MAX(started_at) as last_used
FROM subagent_invocations
WHERE subagent_type = :type

-- History (paginated)
SELECT
    si.agent_id, si.session_uuid, s.project_encoded_name,
    si.started_at, si.duration_seconds,
    si.input_tokens, si.output_tokens, si.cost_usd
FROM subagent_invocations si
JOIN sessions s ON si.session_uuid = s.uuid
WHERE si.subagent_type = :type
ORDER BY si.started_at DESC
LIMIT :limit OFFSET :offset

-- Projects used in
SELECT DISTINCT s.project_encoded_name
FROM subagent_invocations si
JOIN sessions s ON si.session_uuid = s.uuid
WHERE si.subagent_type = :type
```

**New query functions:** `query_agent_detail(conn, subagent_type)`, `query_agent_history(conn, subagent_type, limit, offset)`

---

## New db/queries.py Functions Needed

Summary of all new query functions to add to `db/queries.py`:

| Function | Phase | Used By |
|----------|-------|---------|
| `query_dashboard_stats(conn, start_dt, end_dt)` | 1 | `/analytics/dashboard` |
| `query_analytics(conn, project, start_dt, end_dt)` | 1 | `/analytics`, `/analytics/projects/{name}` |
| `query_skill_usage(conn, project, limit)` | 1 | `/skills/usage` |
| `query_sessions_by_skill(conn, skill_name, limit, offset)` | 1 | `/skills/{name}/sessions` |
| `query_project_sessions(conn, project, limit, offset)` | 2 | `/projects/{name}` |
| `query_project_branches(conn, project)` | 2 | `/projects/{name}/branches` |
| `query_project_chains(conn, project)` | 2 | `/projects/{name}/chains` |
| `query_session_lookup(conn, project, identifier)` | 2 | `/projects/{name}/sessions/lookup` |
| `query_agent_usage(conn)` | 3 | `/agents/usage` |
| `query_agent_detail(conn, subagent_type)` | 3 | `/agents/usage/{type}` |
| `query_agent_history(conn, subagent_type, limit, offset)` | 3 | `/agents/usage/{type}/history` |

---

## Implementation Checklist

### Phase 1 — Global Aggregation (no schema changes)

- [x] Add `query_dashboard_stats()` to `db/queries.py`
- [x] Add SQLite fast path to `routers/analytics.py:get_dashboard_stats()`
- [x] Add `query_analytics()` to `db/queries.py` (with tool/model aggregation)
- [x] Add SQLite fast path to `routers/analytics.py:get_global_analytics()`
- [x] Add SQLite fast path to `routers/analytics.py:get_project_analytics()`
- [x] Add `query_skill_usage()` to `db/queries.py`
- [x] Add SQLite fast path to `routers/skills.py:get_skill_usage()`
- [x] Add `query_sessions_by_skill()` to `db/queries.py`
- [x] Add SQLite fast path to `routers/skills.py:get_skill_sessions()`
- [x] Add tests for all new query functions in `tests/test_db.py`
- [x] Add API endpoint tests in `tests/api/`

### Phase 2 — Project-Level Endpoints (no schema changes)

- [x] Add `query_project_sessions()` to `db/queries.py`
- [x] Add SQLite fast path to `routers/projects.py:get_project()`
- [x] Add `query_project_branches()` to `db/queries.py`
- [x] Add SQLite fast path to `routers/projects.py:get_project_branches()`
- [x] Add `query_project_chains()` to `db/queries.py`
- [x] Add SQLite fast path to `routers/projects.py:get_project_chains()`
- [x] Add `query_session_lookup()` to `db/queries.py`
- [x] Add SQLite fast path to `routers/projects.py:lookup_session()`
- [x] Tests for all new queries and endpoints

### Phase 3 — Agent Analytics (indexer extension)

- [x] Extend `db/indexer.py:_index_session()` to populate `subagent_invocations`
- [x] Add `query_agent_usage()` to `db/queries.py`
- [x] Add SQLite fast path to `routers/agent_analytics.py:collect_all_agent_usage()`
- [x] Add `query_agent_detail()` to `db/queries.py`
- [x] Add SQLite fast path to `routers/agent_analytics.py:get_agent_detail()`
- [x] Add `query_agent_history()` to `db/queries.py`
- [x] Add SQLite fast path to `routers/agent_analytics.py:get_agent_history()`
- [x] Tests for indexer extension and all new queries
- [x] Consider deprecating `AgentUsageIndex` JSON file after SQLite stabilizes

### Phase 4 — Completion & Cleanup

- [x] Add missing Phase 3 query tests (`TestAgentUsageQuery`, `TestAgentDetailQuery`, `TestAgentHistoryQuery`)
- [x] Schema extension: `subagent_tools` table with v1→v2 migration
- [x] Indexer extension: populate `subagent_tools` with per-invocation tool usage
- [x] Update `query_agent_detail()` with `top_tools` from `subagent_tools`
- [x] Deprecate `AgentUsageIndex` — removed ~750 lines of JSONL fallback code
- [x] DB health monitoring: `_log_db_health()` + `/health` endpoint SQLite status
- [x] Benchmarking script: `benchmarks/bench_endpoints.py`
- [x] Documentation updates

### Post-Implementation

- [x] Benchmark before/after for each endpoint
- [x] Monitor SQLite index size and sync time (via `/health` endpoint)
- [x] Document any new config flags in `config.py`
