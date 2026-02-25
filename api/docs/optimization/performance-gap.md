# Performance Gap Analysis: SQLite Optimization Implementation

**Reviewed**: 2026-02-13
**Scope**: All commits implementing `docs/performance-optimization.md` (Phase 1-4)
**Files Audited**: `db/schema.py`, `db/connection.py`, `db/indexer.py`, `db/queries.py`, `config.py`, `parallel.py`, `routers/agent_analytics.py`, `routers/agents.py`, `routers/sessions.py`, `routers/analytics.py`, `routers/skills.py`, `routers/plans.py`, `routers/plugins.py`

---

## Summary

| Severity | Count |
|----------|-------|
| HIGH | 3 |
| MEDIUM | 4 |
| LOW | 3 |

---

## HIGH Severity

### H1. Silent Exception Swallowing in `parallel.py`

**Location**: `parallel.py` — `process_items_parallel()`

```python
results = await asyncio.gather(*tasks, return_exceptions=True)
return [r for r in results if not isinstance(r, Exception)]
```

**Problem**: Corrupted JSONL files, permission errors, or OOM during parsing are silently discarded. The caller receives a shorter result list with no indication that data was lost. No log entry, no metric, no error flag in the response.

**Impact**: Users see incomplete analytics with no warning. Debugging is impossible since there is no trace of the failure.

**Fix**:
```python
results = await asyncio.gather(*tasks, return_exceptions=True)
successes = []
for i, r in enumerate(results):
    if isinstance(r, Exception):
        logger.warning("Failed to process item %d: %s", i, r)
    else:
        successes.append(r)
return successes
```

Optionally return `(successes, errors)` tuple so callers can decide whether partial data is acceptable or should trigger a warning header.

---

### H2. Non-Atomic Readiness Check in Agent Analytics

**Location**: `routers/agent_analytics.py` — `_get_agent_usage_sqlite()`

```python
if not is_db_ready():
    return None
conn = create_read_connection()     # gap: indexer could be mid-rebuild
data = query_agent_usage(conn)      # may return partial/stale data
```

**Problem**: Between the readiness check and the actual query, the background indexer thread could be mid-`sync_all_projects()`. WAL mode prevents blocking, but queries during a rebuild may return stale session counts or missing recent data.

**Impact**: Intermittent data inconsistencies, especially right after server startup or when many new sessions appear at once.

**Fix**: Accept eventual consistency but add visibility:
- Add `X-Index-Age: <seconds>` response header so the frontend can show a staleness indicator
- Track `_last_sync_complete` timestamp in the indexer module
- Alternatively, use a read snapshot by starting an explicit `BEGIN` transaction before the query

---

### H3. N+1 Query in Skills JSONL Fallback

**Location**: `routers/skills.py` — `get_skill_usage()` and `get_skill_sessions()` fallback paths

```python
# Fallback when SQLite unavailable
for project in list_all_projects():            # N projects
    for session in project.list_sessions():     # M sessions each
        skills = session.get_skills_used()      # parses full JSONL per session
```

**Problem**: When SQLite is unavailable, the skills endpoints degenerate to O(P x S x M) — the same sequential scan that the optimization was meant to eliminate. No parallel processing, no batching. This is the only aggregate endpoint whose fallback path was never parallelized.

**Impact**: Skills endpoints go from <50ms (SQLite) to 10+ seconds (fallback) with no middle ground.

**Fix**: Apply the same `process_items_parallel()` with 16-worker concurrency that agent analytics uses. Even without SQLite, parallel I/O would cut fallback time by ~5-10x.

---

## MEDIUM Severity

### M1. In-Memory Filtering After Full Dataset Load

**Location**: `routers/agents.py` — `list_agent_usage()`

```python
response = await collect_all_agent_usage()  # loads ALL agent types from DB
agents = list(response.agents)              # full copy

if category:
    agents = [a for a in agents if a.category == category]  # Python filter
if search:
    agents = [a for a in agents if search.lower() in a.subagent_type.lower()]
```

**Problem**: Loads the entire agent usage dataset into Python memory, then filters in-memory with multiple list comprehension passes. Filtering is not pushed to SQL.

**Impact**: Unnecessary memory allocation and serialization overhead. Tolerable at current scale (~50 agent types) but does not scale.

**Fix**: Add `category` and `search` parameters to `query_agent_usage()` in `db/queries.py`:
```sql
SELECT ... FROM subagent_invocations
WHERE (:category IS NULL OR subagent_type IN (SELECT ...))
  AND (:search IS NULL OR subagent_type LIKE '%' || :search || '%')
GROUP BY subagent_type
```

---

### M2. LRU Cache on Filesystem State Never Invalidated

**Location**: `routers/agent_analytics.py` — `determine_agent_category()`

```python
@functools.lru_cache(maxsize=256)
def determine_agent_category(subagent_type: str) -> str:
    if (custom_agents_dir / f"{subagent_type}.md").exists():
        return "custom"
    ...
```

**Problem**: Once cached, the category for an agent type persists until process restart. If a user creates or deletes `~/.claude/agents/my-agent.md`, the categorization remains stale indefinitely — `lru_cache` has no TTL and frequently-accessed entries may never be evicted.

**Impact**: Agent categorization can be permanently wrong after agent file changes until server restart.

**Fix**: Replace `functools.lru_cache` with `cachetools.TTLCache` (already a project dependency) with a 60-second TTL:
```python
from cachetools import TTLCache, cached
_category_cache = TTLCache(maxsize=256, ttl=60)

@cached(_category_cache)
def determine_agent_category(subagent_type: str) -> str:
    ...
```

---

### M3. Broad `except Exception` in All SQLite Router Fallbacks

**Location**: All SQLite-optimized routers (`sessions.py`, `analytics.py`, `skills.py`, `plans.py`)

```python
try:
    result = query_analytics(conn, ...)
except Exception:
    result = None  # silently fall through to JSONL
```

**Problem**: Catches everything including `TypeError`, `KeyError`, `AttributeError`, and other programming errors. A bug in `queries.py` silently falls back to the slow JSONL path, masking the root cause. The bug may go unnoticed for weeks while users experience degraded performance.

**Impact**: Programming errors in the SQLite query layer are invisible. Performance regressions appear as "SQLite not working" rather than the actual bug.

**Fix**: Catch `sqlite3.Error` specifically. Let programming errors propagate:
```python
try:
    result = query_analytics(conn, ...)
except sqlite3.Error as e:
    logger.warning("SQLite query failed, falling back to JSONL: %s", e)
    result = None
```

---

### M4. DELETE + INSERT Gap for Tools/Skills During Indexing

**Location**: `db/indexer.py` — `_index_session()`

```python
conn.execute("DELETE FROM session_tools WHERE session_uuid = ?", (uuid,))
for tool_name, count in tools.items():
    conn.execute("INSERT INTO session_tools VALUES (?, ?, ?)", (uuid, tool_name, count))
```

**Problem**: This two-step operation temporarily removes all tool records for a session. Under WAL mode, a concurrent reader could observe a session with zero tools during the microsecond gap between DELETE and INSERT.

**Impact**: Low probability but violates the expectation that WAL provides consistent snapshots. A reader hitting this window sees a session with `tool_count = 0`.

**Fix**: Use `INSERT OR REPLACE` directly, then clean up removed tools:
```python
for tool_name, count in tools.items():
    conn.execute(
        "INSERT OR REPLACE INTO session_tools VALUES (?, ?, ?)",
        (uuid, tool_name, count)
    )
# Remove tools no longer present
if tools:
    placeholders = ",".join("?" * len(tools))
    conn.execute(
        f"DELETE FROM session_tools WHERE session_uuid = ? AND tool_name NOT IN ({placeholders})",
        (uuid, *tools.keys())
    )
else:
    conn.execute("DELETE FROM session_tools WHERE session_uuid = ?", (uuid,))
```

---

## LOW Severity

### L1. Double JSON Parsing for `models_used` in Analytics

**Location**: `routers/analytics.py` — models aggregation

```python
# SQLite returns JSON strings:
"models_used_raw": ["[\"claude-opus\", \"claude-sonnet\"]", ...]

# Python then parses each:
all_models = set()
for raw in data["models_used_raw"]:
    all_models.update(json.loads(raw))
```

**Problem**: JSON stored as text in SQLite is round-tripped through Python's `json.loads()` per row. This could be done in a single SQL query.

**Fix**: Use SQLite's built-in `json_each()`:
```sql
SELECT DISTINCT je.value
FROM sessions, json_each(sessions.models_used) AS je
WHERE project_encoded_name = :project
```

---

### L2. Missing Index on `subagent_invocations.started_at`

**Location**: `db/schema.py` — `subagent_invocations` table

The agent history endpoint paginates by `started_at DESC`:
```sql
SELECT * FROM subagent_invocations
WHERE subagent_type = ?
ORDER BY started_at DESC
LIMIT ? OFFSET ?
```

Current indexes: `idx_subagent_session (session_uuid)`, `idx_subagent_type (subagent_type)`

**Problem**: No composite index covers the `WHERE subagent_type = ? ORDER BY started_at DESC` pattern. SQLite must filter by type, then sort the result set.

**Fix**: Add a composite covering index:
```sql
CREATE INDEX idx_subagent_type_time
ON subagent_invocations(subagent_type, started_at DESC);
```

This eliminates the sort step entirely — the index provides pre-sorted results.

---

### L3. Plugin Usage Endpoint Not Migrated to SQLite

**Location**: `routers/plugins.py` — `get_plugin_usage()`

**Problem**: The `session_skills` table already stores skill/plugin invocation counts per session. However, `/plugins/{name}/usage` still performs a full JSONL scan across all sessions to count plugin invocations. This is the last remaining aggregate endpoint without a SQLite fast path.

**Impact**: Plugin usage is the slowest aggregate endpoint (sequential JSONL scan, 60s cache TTL vs 600s for agent usage).

**Fix**: Query `session_skills` table directly:
```sql
SELECT s.project_encoded_name, s.start_time, sk.count
FROM session_skills sk
JOIN sessions s ON s.uuid = sk.session_uuid
WHERE sk.skill_name = :plugin_name
ORDER BY s.start_time DESC
```

---

## Architectural Notes

### Resolved: Dual Cache System

The `performance-optimization.md` doc noted two parallel caching systems for agent usage (SQLite `subagent_invocations` + JSON-based `AgentUsageIndex`). The current code uses SQLite exclusively — the JSON index has been removed. This is the correct outcome.

### Missing: Observability

No endpoint or log output tracks which code path was taken (SQLite vs JSONL fallback). When investigating performance issues, there is no way to determine if a slow response was caused by SQLite failure or JSONL fallback without reading application logs.

**Recommendation**: Add a `X-Data-Source: sqlite|jsonl` response header and a structured log entry on fallback events.

### Missing: SQLite Coverage for Subagent Detail Views

`routers/subagent_sessions.py` endpoints are synchronous (`def` not `async def`) and parse parent session JSONL to determine subagent type. The `subagent_invocations` table has this data but is not queried by these endpoints.

---

## Implementation Priority

| ID | Effort | Impact | Priority |
|----|--------|--------|----------|
| H1 | 5 min | Prevents invisible data loss | P0 |
| M3 | 15 min | Prevents bug masking | P0 |
| L2 | 2 min | Faster paginated history queries | P1 |
| M1 | 30 min | Lower memory, faster filtered queries | P1 |
| H3 | 30 min | 5-10x faster skills fallback | P1 |
| M4 | 20 min | Eliminates read-during-write gap | P2 |
| M2 | 10 min | Prevents stale agent categorization | P2 |
| L3 | 1 hr | Eliminates last JSONL-only aggregate scan | P2 |
| H2 | 15 min | Frontend staleness visibility | P2 |
| L1 | 15 min | Cleaner SQL, less Python overhead | P3 |
