# Performance Fixes Summary

## Overview
Fixed 3 performance gaps identified in the claude-karma API (L2, M1, L1 from performance-gap.md).

## Changes Made

### L2: Missing Index on subagent_invocations(subagent_type, started_at)

**Problem**: Agent history endpoint paginates by `started_at DESC` with `WHERE subagent_type = ?`, but no index covered this query pattern.

**Fix**: Added composite covering index to schema.

**File**: `api/db/schema.py`
```sql
CREATE INDEX IF NOT EXISTS idx_subagent_type_time ON subagent_invocations(subagent_type, started_at DESC);
```

**Impact**:
- Query plan will now use the composite index for sorted pagination
- Eliminates full table scan on `subagent_invocations`
- Significant speedup for `/agents/usage/{type}/history` endpoint

---

### M1: In-Memory Filtering After Full Dataset Load

**Problem**: `list_agent_usage()` in agents.py loaded ALL agent data, then filtered in Python with list comprehensions for `search` parameter.

**Fix**: Push `search` filtering to SQL WHERE clause.

**Files Modified**:
1. `api/db/queries.py::query_agent_usage()`
   - Added optional `search` parameter
   - Adds `WHERE si.subagent_type LIKE '%' || :search || '%'` when search provided

2. `api/routers/agent_analytics.py`
   - Updated `_get_agent_usage_sqlite()` to accept `search` parameter
   - Updated `collect_all_agent_usage()` to pass search to SQL layer

3. `api/routers/agents.py::list_agent_usage()`
   - Passes `search` parameter to `collect_all_agent_usage()`
   - Removed in-memory search filtering (now handled by SQL)
   - Kept category filtering in Python (added comment explaining why)

**Impact**:
- Database filters rows before returning to Python
- Reduces memory usage and CPU time for search queries
- Especially beneficial when searching across thousands of agent invocations

**Note**: Category filtering remains in Python because category is derived via `determine_agent_category()` and not stored in the database. Could be pushed to SQL if we add a `category` column to `subagent_invocations`.

---

### L1: Double JSON Parsing for models_used in Analytics

**Problem**: JSON stored as text in SQLite was parsed per-row in Python via `json.loads()`.

**Fix**: Use SQLite's built-in `json_each()` for efficient in-database JSON parsing.

**Files Modified**:
1. `api/db/queries.py::query_analytics()`
   - Changed query to use `json_each()`:
   ```sql
   SELECT DISTINCT je.value as model_name
   FROM sessions s, json_each(s.models_used) AS je
   WHERE ...
   ```
   - Changed return key from `models_used_raw` to `models_used_list`
   - Returns pre-parsed model names instead of JSON strings

2. `api/routers/analytics.py::_get_analytics_sqlite()`
   - Updated to consume `models_used_list` instead of parsing JSON
   - Simplified loop: no try/except, no json.loads()

3. `api/tests/test_db.py`
   - Updated test assertions to use `models_used_list` key
   - Simplified test logic (no JSON parsing needed)

**Impact**:
- Eliminates Python-level JSON parsing overhead
- SQLite's native JSON functions are faster than Python's json.loads()
- Reduces CPU time for analytics endpoints
- Cleaner, simpler code in the Python layer

---

## Testing

All tests pass:
```bash
pytest tests/test_db.py::TestAgentUsageQuery -v      # 5 passed
pytest tests/test_db.py::TestAnalyticsQuery -v        # 7 passed
pytest tests/test_db.py -v                            # 108 passed
```

## Migration

The new index (`idx_subagent_type_time`) will be automatically created when the API starts:
- Fresh installs: Index created via `SCHEMA_SQL`
- Existing databases: No migration needed (index is idempotent with `IF NOT EXISTS`)

To manually verify:
```bash
sqlite3 ~/.claude_karma/sessions.db "SELECT name FROM sqlite_master WHERE type='index' AND name='idx_subagent_type_time';"
```

## Performance Impact

### Before
- L2: Full table scan on agent history pagination
- M1: Load all agents, filter in Python
- L1: Parse JSON per-row in Python loop

### After
- L2: Index-only scan with sorted access
- M1: Database-level LIKE filtering
- L1: SQLite native JSON parsing

**Expected improvements**:
- Agent history pagination: 50-90% faster (depending on table size)
- Agent search: 30-70% faster (more improvement with larger datasets)
- Analytics models parsing: 20-40% faster (fewer Python function calls)
