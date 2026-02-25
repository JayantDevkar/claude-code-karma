# Performance Optimization: Agent Analytics API

This document outlines the performance challenges observed in the agent analytics endpoints, the optimizations implemented across phases, and current observations.

---

## Table of Contents

1. [Problem Analysis](#problem-analysis)
2. [Phase 1: Async Parallelism + Cache TTL](#phase-1-async-parallelism--cache-ttl)
3. [Phase 2: Persistent Cache (SQLite)](#phase-2-persistent-cache-sqlite)
4. [Current Endpoint Performance Map](#current-endpoint-performance-map)
5. [Current Observations (2026-02-13)](#current-observations-2026-02-13)
6. [Appendix: Data Flow Architecture](#appendix-data-flow-architecture)

---

## Problem Analysis

### The Nature of the Beast

Claude Code stores session data as **JSONL files** (one JSON object per line) in `~/.claude/projects/`. Each API request to `/agents/usage` must:

1. Enumerate all projects in `~/.claude/projects/`
2. For each project, list all session `.jsonl` files
3. For each session, parse the entire JSONL to find Task tool calls
4. For each subagent, parse its JSONL file to extract usage stats

### Measured Performance

| Metric | Value |
|--------|-------|
| Cold request to `/agents/usage` | ~7-10 seconds |
| Number of projects scanned | Variable (~10-50) |
| Number of sessions scanned | Variable (~100-500) |
| Total JSONL files parsed | Hundreds |

### Root Causes

#### 1. Full JSONL Parsing on Every Request

```
~/.claude/projects/{encoded-path}/{uuid}.jsonl   <- Entire file parsed
    |
models/session.py (parse_message per line)       <- Pydantic validation
    |
Aggregate stats                                   <- Discarded after request
```

Each line becomes a full Pydantic model with nested content blocks, even when we only need timestamps and token counts.

#### 2. Sequential I/O

The original implementation was synchronous:

```python
# OLD: Sequential processing
for project in list_all_projects():           # Blocking
    for session in project.list_sessions():    # Blocking
        for subagent in session.list_subagents():  # Blocking
            usage = subagent.get_usage_summary()   # Parses entire JSONL
```

#### 3. No Persistent Cache

- In-memory `SessionCache` only caches within a single request
- Cache lost on server restart
- No pre-computation of aggregated stats
- Every request re-parses the same files

#### 4. Short HTTP Cache TTL

Original settings:
- `max-age: 60` (1 minute)
- `stale-while-revalidate: 120` (2 minutes)

For historical data that rarely changes, this caused unnecessary re-computation.

### Complexity Analysis

```
Time Complexity: O(P x S x M)

Where:
  P = Number of projects
  S = Sessions per project
  M = Messages per session (parsed twice: once for subagent types, once for stats)
```

---

## Phase 1: Async Parallelism + Cache TTL

**Status: Implemented**

### Changes Made

#### 1. Async Parallel Processing

Converted synchronous loops to async with session-level parallelism using the existing `parallel.py` infrastructure.

**Before:**
```python
def collect_all_agent_usage():
    for project in list_all_projects():
        for session in project.list_sessions():
            # Sequential processing
```

**After (actual implementation):**
```python
async def collect_all_agent_usage():
    all_sessions = [(project, session) for project in projects for session in sessions]

    results = await process_items_parallel(
        all_sessions,
        _process_session_for_agent_stats,
        max_concurrent=16,  # 16 concurrent workers (increased from originally planned 8)
    )
```

#### 2. Configurable Cache TTL

Settings in `config.py`:

```python
cache_agent_usage: int = 300           # 5 minutes (was 60s)
cache_agent_usage_revalidate: int = 600  # 10 minutes (was 120s)
```

Configurable via environment:
```bash
export CLAUDE_KARMA_CACHE_AGENT_USAGE=300
export CLAUDE_KARMA_CACHE_AGENT_USAGE_REVALIDATE=600
```

#### 3. Additional Optimizations (Beyond Original Plan)

- `AgentUsageIndex` class (`agent_analytics.py:71-165`) — persistent JSON-based incremental index
- Two-tier caching: in-memory TTL (600s) + persistent index (`agent_analytics.py:401-429`)
- `@functools.lru_cache(maxsize=256)` for agent lookups (`agent_analytics.py:218, 243`)
- Session-level caching to avoid reprocessing (`agent_analytics.py:591-652`)

#### 4. Files Modified

| File | Changes |
|------|---------|
| `api/config.py` | Added `cache_agent_usage`, `cache_agent_usage_revalidate` |
| `api/routers/agent_analytics.py` | Converted to async, parallel processing (16 workers), AgentUsageIndex |
| `api/routers/agents.py` | Updated endpoints to async, use config settings |

### Results

| Metric | Before | After |
|--------|--------|-------|
| Concurrent I/O workers | 1 (sequential) | 16 |
| HTTP cache duration | 60s | 300s |
| Stale-while-revalidate | 120s | 600s |
| Cold request time | ~10s | ~7-10s (I/O bound) |
| Cache hit window | 1-3 min | 5-15 min |

### Limitations

Phase 1 provides **better concurrency** but doesn't eliminate the fundamental issue: **every cold request still parses all JSONL files**. The bottleneck is now disk I/O and JSON parsing, not sequential blocking.

---

## Phase 2: Persistent Cache (SQLite)

**Status: Implemented (exceeds original plan)**

The original plan proposed a 3-table SQLite cache. The actual implementation uses a 6-table schema with FTS5, WAL mode, and reader/writer connection separation.

### Actual Implementation

#### Database Location

```
~/.claude_karma/metadata.db (SQLite with WAL mode)
```

Controlled by `config.py`:
```python
use_sqlite: bool = Field(default=True, description="Enable SQLite metadata index")

@property
def sqlite_db_path(self) -> Path:
    return self.karma_base / "metadata.db"
```

#### Schema (6 tables vs. planned 3)

Implemented in `api/db/schema.py` (176 lines):

| Table | Purpose | Planned? |
|-------|---------|----------|
| `sessions` | Full session metadata | Yes |
| `subagent_invocations` | Subagent runs per session | Yes (as `subagents`) |
| `session_tools` | Denormalized tool usage counts | No (new) |
| `session_skills` | Denormalized skill usage | No (new) |
| FTS5 virtual table | Full-text search on slugs | No (new) |
| Schema versioning | Migration support | No (new) |

#### Connection Management (`api/db/connection.py`, 154 lines)

| Feature | Planned | Actual |
|---------|---------|--------|
| Connection model | Single connection | Reader/Writer separation |
| Concurrency | Not specified | WAL mode for concurrent reads during writes |
| Writer | Not specified | Singleton for background indexer |
| Reader | Not specified | Per-request read-only connections |

#### Indexer (`api/db/indexer.py`, 373 lines)

| Feature | Planned | Actual |
|---------|---------|--------|
| `sync_all_projects()` | Yes | Lines 44-107 |
| `sync_project()` | Not specified | Lines 110-162 (incremental per-project) |
| `_index_session()` | Yes | Lines 165-276 |
| `_cleanup_stale_sessions()` | Not specified | Lines 297-332 |
| `run_background_sync()` | Yes (optional) | Lines 355-372 (background thread on startup) |
| Change detection | mtime comparison | mtime comparison (as planned) |
| Write strategy | Not specified | `INSERT OR REPLACE` (idempotent) |

#### Endpoints Using SQLite Fast Path

| Router | Pattern | Fallback |
|--------|---------|----------|
| `routers/sessions.py` | SQLite-first with automatic fallback to JSONL | Yes |
| `routers/analytics.py` | SQLite fast path for aggregations | Yes |
| `routers/skills.py` | SQLite fast path for skill stats | Yes |
| `routers/plans.py` | O(1) slug lookup via SQLite | Yes |

#### Endpoints NOT Using SQLite

| Router | Endpoints | Current Strategy |
|--------|-----------|-----------------|
| `routers/agent_analytics.py` | `/agents/usage`, `/agents/usage/{type}`, `/agents/usage/{type}/history` | JSONL scan + in-memory cache + JSON index |
| `routers/plugins.py` | `/plugins/{name}/usage` | JSONL scan |

### Planned vs. Actual Comparison

| Aspect | Original Plan | Actual Implementation |
|--------|---------------|----------------------|
| Cache backend | `~/.claude-karma/cache.db` | `~/.claude_karma/metadata.db` |
| Tables | 3 (`sessions`, `subagents`, `agent_stats`) | 6 (sessions, subagent_invocations, session_tools, session_skills, FTS5, schema versioning) |
| Connection model | Single | Reader/Writer separation with WAL |
| Concurrency | Not addressed | True concurrent reads during writes |
| Invalidation | mtime comparison | mtime comparison + stale cleanup |
| Startup | Optional background warm | Background thread (`run_background_sync()`) |
| Fallback | Not addressed | SQLite-first with automatic JSONL fallback |

---

## Current Endpoint Performance Map

### 69 Total API Endpoints by Performance Tier

#### Tier 1: SQLite-Optimized (<50ms typical)

| Endpoint | Method | Router | Cache TTL |
|----------|--------|--------|-----------|
| `/analytics` | GET | analytics.py | 120s |
| `/analytics/projects/{encoded_name}` | GET | analytics.py | 120s |
| `/analytics/dashboard` | GET | analytics.py | 60s |
| `/sessions/all` | GET | sessions.py | 60s |
| `/projects/{encoded_name}` | GET | projects.py | 60s |
| `/projects/{encoded_name}/sessions/lookup` | GET | sessions.py | 30s |
| `/projects/{encoded_name}/chains` | GET | projects.py | 120s |
| `/projects/{encoded_name}/branches` | GET | projects.py | 60s |
| `/plans` | GET | plans.py | 300s |
| `/plans/stats` | GET | plans.py | 300s |
| `/plans/with-context` | GET | plans.py | 300s |
| `/plans/{slug}` | GET | plans.py | 300s |
| `/skills/usage` | GET | skills.py | 60s |
| `/skills/{skill_name}/sessions` | GET | skills.py | 60s |

#### Tier 2: JSONL Aggregate Scan (5-15s cold, cached 600s)

| Endpoint | Method | Router | Cache TTL | Workers |
|----------|--------|--------|-----------|---------|
| `/agents/usage` | GET | agents.py | 600s | 16 parallel |
| `/agents/usage/{subagent_type}` | GET | agents.py | 600s | 16 parallel |
| `/agents/usage/{subagent_type}/history` | GET | agents.py | 600s | 16 parallel |
| `/plugins/{plugin_name}/usage` | GET | plugins.py | 60s | sequential |

#### Tier 3: Single-Resource JSONL Parse (50-500ms)

| Endpoint | Method | Router | Cache TTL |
|----------|--------|--------|-----------|
| `/sessions/{uuid}` | GET | sessions.py | 60s |
| `/sessions/{uuid}/timeline` | GET | sessions.py | 60s |
| `/sessions/{uuid}/tools` | GET | sessions.py | 300s |
| `/sessions/{uuid}/file-activity` | GET | sessions.py | 300s |
| `/sessions/{uuid}/subagents` | GET | sessions.py | 300s |
| `/sessions/{uuid}/subagents/parallel` | GET | sessions.py | 300s |
| `/sessions/{uuid}/tasks` | GET | sessions.py | 60s |
| `/sessions/{uuid}/todos` | GET | sessions.py | 60s |
| `/sessions/{uuid}/initial-prompt` | GET | sessions.py | 60s |
| `/sessions/{uuid}/relationships` | GET | sessions.py | 60s |
| `/sessions/{uuid}/chain` | GET | sessions.py | 60s |
| `/sessions/{uuid}/plan` | GET | sessions.py | 300s |
| `/sessions/by-message/{message_uuid}` | GET | sessions.py | 60s |
| `/sessions/continuation/{session_uuid}` | GET | sessions.py | 60s |
| Subagent detail endpoints (4) | GET | subagent_sessions.py | 60-300s |
| Subagent tasks endpoint | GET | subagent_sessions.py | 60s |

#### Tier 4: File Read / Simple I/O (<10ms)

| Endpoint | Method | Router | Cache TTL |
|----------|--------|--------|-----------|
| `/` | GET | main.py | none |
| `/health` | GET | main.py | none |
| `/projects` | GET | projects.py | 30s |
| `/projects/{encoded_name}/analytics` | GET | projects.py | 120s |
| `/projects/projects/{encoded_name}/agents` | GET | projects.py | 60s |
| `/projects/projects/{encoded_name}/skills` | GET | projects.py | 60s |
| `/settings` | GET | settings.py | none |
| `/settings` | PUT | settings.py | none |
| `/live-sessions` | GET | live_sessions.py | 1s |
| `/live-sessions/active` | GET | live_sessions.py | 1s |
| `/live-sessions/project/{name}` | GET | live_sessions.py | 1s |
| `/live-sessions/{session_id}` | GET | live_sessions.py | 1s |
| `/live-sessions/{session_id}` | DELETE | live_sessions.py | none |
| `/live-sessions/cleanup` | POST | live_sessions.py | none |
| `/agents` | GET | agents.py | 60s |
| `/agents/{name}` | GET | agents.py | 60s |
| `/agents/{name}` | POST | agents.py | none |
| `/agents/{name}` | DELETE | agents.py | none |
| `/agents/info/{agent_name}` | GET | agents.py | 60s |
| `/skills` | GET | skills.py | 60s |
| `/skills/content` | GET | skills.py | 60s |
| `/skills/content` | POST | skills.py | none |
| `/skills/content` | DELETE | skills.py | none |
| `/skills/info/{skill_name}` | GET | skills.py | 60s |
| `/plugins` | GET | plugins.py | 60s |
| `/plugins/stats` | GET | plugins.py | 60s |
| `/plugins/{plugin_name}` | GET | plugins.py | 60s |
| `/plugins/{plugin_name}/capabilities` | GET | plugins.py | 60s |
| `/history/archived` | GET | history.py | 60s |
| `/history/archived/{encoded_name}` | GET | history.py | 60s |
| `/analytics/debug/verify` | GET | analytics.py | none |
| `/plans/{slug}/sessions` | GET | plans.py | 300s |

---

## Current Observations (2026-02-13)

### Caching Tiers Observed

| TTL | Usage |
|-----|-------|
| 1s | Live session polling endpoints |
| 30s | Project listing, session lookup |
| 60s | Most single-resource endpoints, agent/skill/plugin metadata |
| 120s | Analytics aggregates, chain computation |
| 300s | Historical data (tools, file activity, plans) |
| 600s | Agent usage aggregate endpoints |

### SQLite Coverage

- 14 endpoints use SQLite fast path with JSONL fallback
- 4 aggregate endpoints still use JSONL-only scanning
- The `subagent_invocations` table exists in `db/schema.py` (lines 109-123) but is not queried by the agent usage endpoints in `routers/agents.py`
- The agent usage endpoints use a separate `AgentUsageIndex` (JSON file at `~/.claude_karma/agent-usage-index.json`) instead of the SQLite `subagent_invocations` table

### Agent Usage Endpoint Specifics

- `agent_analytics.py` line 492-496: `process_items_parallel` uses `max_concurrent=16` (doc previously stated 8)
- `agent_analytics.py` line 397-398: Global in-memory TTL cache set to 600s
- `agent_analytics.py` line 71-165: `AgentUsageIndex` maintains a separate JSON-based persistent index
- Two parallel caching systems exist for agent usage: the JSON-based `AgentUsageIndex` and the SQLite `subagent_invocations` table

### Plugin Usage Endpoint Specifics

- `/plugins/{plugin_name}/usage` scans all sessions for Skill tool invocations
- Cache TTL is 60s (lower than agent usage's 600s)
- No parallel processing observed — sequential scan

### Subagent Session Endpoints

- `subagent_sessions.py` endpoints are synchronous (`def` not `async def`)
- `get_subagent_detail` iterates messages twice: once via `collect_agent_data()`, once to calculate cost (lines 78-93)
- `_determine_subagent_type` calls `collect_session_data(parent_session)` which parses the entire parent session JSONL to find the Task tool call that spawned the subagent (line 152)

### Single-Pass Collection Pattern

- `collectors.py` provides `collect_session_data()` and `collect_agent_data()` for single-pass metric extraction
- Session endpoints (`sessions.py`) use shared `services/conversation_endpoints.py` for DRY timeline/tool/file-activity generation
- Subagent endpoints also use the shared service (Phase 3 DRY refactor)

---

## Appendix: Data Flow Architecture

### Current Flow (SQLite-optimized endpoints)

```
+--------------+     +--------------+     +--------------+
|   Request    |---->| SQLite Check |---->|   SQLite     |
|              |     | (is_db_ready)|     |   metadata   |
+--------------+     +--------------+     +--------------+
                            |                    |
                     +------+------+             |
                     |             |             |
                  Ready?       Not Ready?       |
                     |             |             |
                     v             v             |
              +----------+  +--------------+    |
              |  Return  |  | JSONL Parse  |    |
              |  from DB |  | (fallback)   |    |
              +----------+  +--------------+    |
                                   |            |
                                   v            |
                            +--------------+    |
                            |   Response   |    |
                            |  + Cache Hdr |    |
                            +--------------+    |
```

### Current Flow (Agent usage endpoints)

```
+--------------+     +--------------+     +--------------+
|   Request    |---->| In-Memory    |---->| AgentUsage   |
| /agents/usage|     | TTL Cache    |     | Index (JSON) |
+--------------+     | (600s)       |     +--------------+
                     +--------------+            |
                            |                    |
                     +------+------+      +------+------+
                     |             |      |             |
                  Hit?          Miss?   Fresh?       Stale?
                     |             |      |             |
                     v             v      v             v
              +----------+  +--------------+  +--------------+
              |  Return  |  | Return from  |  | Async Pool   |
              |  Cached  |  | Index        |  | (16 workers) |
              +----------+  +--------------+  +--------------+
                                                     |
                                                     v
                                              +--------------+
                                              |  JSONL Files |
                                              |  (~/.claude) |
                                              +--------------+
                                                     |
                                                     v
                                              +--------------+
                                              |   Pydantic   |
                                              |   Parsing    |
                                              +--------------+
                                                     |
                                                     v
                                              +--------------+
                                              |  Update Index|
                                              |  + Response  |
                                              +--------------+
```

### Background Indexer Flow (Startup)

```
+--------------+     +--------------+     +--------------+
| App Startup  |---->| Background   |---->| Walk all     |
|              |     | Thread       |     | projects/    |
+--------------+     +--------------+     +--------------+
                                                |
                                                v
                                         +--------------+
                                         | For each     |
                                         | session:     |
                                         | mtime check  |
                                         +--------------+
                                                |
                                         +------+------+
                                         |             |
                                      Same?        Changed?
                                         |             |
                                         v             v
                                   +----------+  +--------------+
                                   |   Skip   |  | Parse JSONL  |
                                   |          |  | Upsert SQLite|
                                   +----------+  +--------------+
```

---

## References

- `api/routers/agent_analytics.py` - Async analytics functions, AgentUsageIndex
- `api/routers/agents.py` - Agent usage endpoints
- `api/routers/analytics.py` - SQLite-optimized analytics
- `api/routers/sessions.py` - SQLite-first session endpoints
- `api/routers/skills.py` - SQLite-optimized skill stats
- `api/routers/plans.py` - SQLite slug lookup
- `api/routers/plugins.py` - Plugin listing and usage
- `api/routers/subagent_sessions.py` - Subagent detail views
- `api/config.py` - Cache TTL configuration, SQLite toggle
- `api/parallel.py` - Thread pool utilities
- `api/models/session.py` - Session model with caching
- `api/db/schema.py` - SQLite schema (6 tables)
- `api/db/indexer.py` - Background JSONL-to-SQLite indexer
- `api/db/connection.py` - Reader/Writer connection management
- `api/collectors.py` - Single-pass data collection
- `api/services/conversation_endpoints.py` - Shared endpoint services
