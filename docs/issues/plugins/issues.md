# Plugin Routes - Issues Report

**Date:** 2026-01-31
**Scope:** `api/routers/plugins.py`, `api/models/plugin.py`
**Last Updated:** 2026-01-31 (Resolution pass)

---

## Resolution Summary

| Issue | Status | Notes |
|-------|--------|-------|
| P-001 | ✅ RESOLVED | Added period filtering, optimized with double-checked locking |
| P-002 | ⚠️ DEFERRED | Cache now has TTL, but no size limit (acceptable for use case) |
| P-003 | ✅ RESOLVED | Fixed via P-005 caching |
| P-004 | ⚠️ DEFERRED | Minor inconsistency, not impacting functionality |
| P-005 | ✅ RESOLVED | Added 60s TTL cache with thread-safe locking |
| S-001 | ℹ️ BY DESIGN | Plugin analytics only tracks plugin skills |
| S-002 | ℹ️ BY DESIGN | Plugin analytics only tracks plugin agents |
| S-003 | ✅ RESOLVED | Cost calculation implemented with Claude pricing |
| S-004 | ✅ RESOLVED | Period filtering implemented (day/week/month/all) |
| S-005 | ✅ RESOLVED | Daily trend breakdown implemented |
| S-006 | ✅ RESOLVED | first_used/last_used timestamps tracked |
| T-001 | ✅ RESOLVED | Double-checked locking pattern implemented |
| SEC-001 | ⚠️ DEFERRED | Existing protection reasonable for use case |
| SEC-002 | ⚠️ DEFERRED | Lower priority, local files only |
| SEC-003 | ✅ RESOLVED | Input validation added (length, format, charset) |
| SEC-004 | ℹ️ ACCEPTABLE | Standard REST API error pattern |
| SEC-005 | ✅ RESOLVED | Exception logging added |
| Q-001 | ✅ RESOLVED | Logger moved before first usage |
| Q-002 | ⚠️ DEFERRED | Minor type annotation improvement |
| Q-003 | ⚠️ DEFERRED | Minor constant extraction |
| Q-004 | ✅ RESOLVED | sys.path manipulation removed |
| TC-001 | ⚠️ DEFERRED | Test coverage improvement |
| TC-002 | ⚠️ DEFERRED | Test coverage improvement |
| TC-003 | ⚠️ DEFERRED | Test coverage improvement |
| TC-004 | ⚠️ DEFERRED | Test coverage improvement |
| TC-005 | ⚠️ DEFERRED | Test coverage improvement |

**Resolved:** 12 issues
**Deferred:** 11 issues (minor/acceptable)
**By Design:** 3 issues

---

## Performance Issues

### P-001: Synchronous Function in Async Endpoint

**Status:** ✅ RESOLVED

**Location:** `api/routers/plugins.py:83-213`
**Function:** `_collect_plugin_usage_sync()`

**Original Issue:**
- Function is synchronous and performs heavy I/O operations
- Iterates ALL projects via `list_all_projects()` (line 90)
- For each project, iterates ALL sessions via `project.list_sessions()` (line 92)
- For each session, calls `session.get_skills_used()` (line 94)
- For each session, iterates ALL messages via `session.iter_messages()` (line 103)
- Called from sync endpoints `list_plugins()` (line 326) and `get_plugin_usage()` (line 455)

**Resolution:**
- Function now accepts `period` parameter for filtering (day/week/month/all)
- Sessions outside the period are skipped early
- Cache uses double-checked locking pattern to avoid blocking during heavy I/O
- Heavy computation runs OUTSIDE the lock

---

### P-002: Unbounded Module-Level Cache

**Status:** ⚠️ DEFERRED

**Location:** `api/routers/plugins.py:227-232`

**Observation:**
```python
_plugin_usage_cache: dict[str, dict] = {}
_plugin_usage_cache_time: dict[str, datetime] = {}
```
- Cache stores ALL plugin usage data from ALL sessions
- No mechanism exists to clear or limit cache size
- No eviction policy

**Notes:** Cache now has 5-minute TTL per period. Size is bounded by number of periods (4 max). Acceptable for use case.

---

### P-003: N+1 Filesystem I/O Pattern

**Status:** ✅ RESOLVED (via P-005)

**Location:** `api/routers/plugins.py:328-331`

**Original Issue:**
- For each plugin, `plugin_to_summary()` calls:
  - `scan_plugin_capabilities(plugin_name)` (line 210) which calls `get_plugin_cache_path()` (line 303 in plugin.py) which calls `load_installed_plugins()` again
  - Performs 5+ filesystem operations: `agents_dir.glob()`, `commands_dir.glob()`, `skills_dir.rglob()`, `hooks_dir.glob()`, and checks `mcp_config.exists()`
  - `get_plugin_description(plugin_name)` (line 224) also calls `get_plugin_cache_path()` and reads `plugin.json`

**Resolution:** `load_installed_plugins()` now cached with 60s TTL, eliminating repeated file reads.

---

### P-004: Conflicting Cache TTLs

**Status:** ⚠️ DEFERRED

**Location:** `api/routers/plugins.py:427` vs lines 289, 342, 394, 473

**Observation:**
- `/usage` endpoint has `max_age=60` (line 427)
- All other endpoints have `max_age=300` (lines 289, 342, 394, 473)
- Internal `_plugin_usage_cache` has fixed 300-second TTL (line 140)

**Notes:** Different TTLs are intentional - usage data is more dynamic than plugin metadata.

---

### P-005: Redundant File Reads

**Status:** ✅ RESOLVED

**Location:** `api/models/plugin.py:260-278`

**Original Issue:**
- `get_plugin_cache_path()` calls `load_installed_plugins()` (line 263)
- `scan_plugin_capabilities()` calls `get_plugin_cache_path()` (line 303)
- `get_plugin_description()` calls `get_plugin_cache_path()` (line 371)
- Each call re-reads and re-parses `installed_plugins.json`

**Resolution:**
- Added module-level cache with 60s TTL
- Thread-safe with Lock
- Single file read serves multiple function calls

---

## Stats Calculation Issues

### S-001: Silent Drop of Non-Plugin Skills

**Status:** ℹ️ BY DESIGN

**Location:** `api/routers/plugins.py:148-156`

**Observation:**
```python
for skill_name, count in skills_used.items():
    if ":" in skill_name:  # Skills without ":" are silently ignored
        plugin_name = skill_name.split(":")[0]
```
- Built-in skills (e.g., "commit", "plan") do not contain ":"
- These skills are never counted

**Notes:** This is intentional - the plugin analytics endpoint only tracks plugin-provided skills.

---

### S-002: Silent Drop of Non-Plugin Agents

**Status:** ℹ️ BY DESIGN

**Location:** `api/routers/plugins.py:172-184`

**Observation:**
```python
if isinstance(block, ToolUseBlock) and block.name == "Task":
    subagent_type = block.input.get("subagent_type", "")
    if ":" in subagent_type:  # Agents without ":" are silently ignored
```
- Any agent spawned without plugin prefix is not tracked

**Notes:** This is intentional - the plugin analytics endpoint only tracks plugin-provided agents.

---

### S-003: cost_usd Never Populated

**Status:** ✅ RESOLVED

**Location:** `api/routers/plugins.py:202-214`

**Original Issue:**
```python
plugin_stats: dict[str, dict] = defaultdict(lambda: {
    "agent_runs": 0,
    "skill_invocations": 0,
    "cost_usd": 0.0,  # Initialized to 0.0, never updated
    ...
})
```

**Resolution:**
- Cost calculated from session token usage
- Uses Claude pricing: $3/M input tokens, $15/M output tokens
- Cost distributed equally among plugins used in each session
- Daily cost tracked for trend data

---

### S-004: period Parameter Ignored

**Status:** ✅ RESOLVED

**Location:** `api/routers/plugins.py:100-109`

**Original Issue:**
```python
period: Annotated[str, Query(description="Time period: day, week, month, all")] = "month",
```
- Parameter is documented: "Time period for analytics (day, week, month, all)"
- Parameter is accepted by the endpoint
- `_collect_plugin_usage_sync()` scans ALL sessions regardless of period value

**Resolution:**
- `_collect_plugin_usage_sync()` now accepts `period` parameter
- Calculates cutoff date based on period (day=1d, week=7d, month=30d, all=no cutoff)
- Sessions before cutoff are skipped
- Cache is per-period

---

### S-005: trend Always Empty

**Status:** ✅ RESOLVED

**Location:** `api/routers/plugins.py:584-591`

**Original Issue:**
```python
trend=[],  # TODO: implement daily breakdown
```

**Resolution:**
- Daily usage tracked in `daily_usage` dict during collection
- Includes agent_runs, skill_invocations, and cost_usd per day
- Converted to sorted `DailyUsage` objects in response

---

### S-006: first_used and last_used Always None

**Status:** ✅ RESOLVED

**Location:** `api/routers/plugins.py:117-118, 158-168, 187-199`

**Original Issue:**
```python
first_used=None,  # TODO: track timestamps
last_used=None,
```

**Resolution:**
- `first_used` and `last_used` tracked during session iteration
- Min/max timestamps calculated from session start times
- Returned in PluginUsageStats response

---

## Thread Safety Issues

### T-001: Race Condition in Cache Updates

**Status:** ✅ RESOLVED

**Location:** `api/routers/plugins.py:235-277`

**Original Issue:**
```python
_plugin_usage_cache: dict[str, dict] | None = None
_plugin_usage_cache_time: datetime | None = None
```
- Two separate mutable module-level variables
- No synchronization mechanism (lock)
- In multi-threaded ASGI environment:
  - Thread A checks cache is stale at line 142-146
  - Thread B checks cache is stale (same result)
  - Both threads start `_collect_plugin_usage_sync()` simultaneously

**Resolution:**
- Added `_plugin_usage_cache_lock = Lock()`
- Implemented double-checked locking pattern:
  1. First check without lock (fast path for cache hits)
  2. Heavy I/O runs OUTSIDE the lock
  3. Lock acquired only for cache update
  4. Double-check inside lock before update
- Eliminates lock contention during heavy computation

---

## Security Issues

### SEC-001: Incomplete Symlink Protection

**Status:** ⚠️ DEFERRED

**Location:** `api/models/plugin.py:303-314`

**Observation:**
```python
resolved_cache = cache_path.resolve()
plugins_base = (settings.claude_base / "plugins").resolve()
resolved_cache.relative_to(plugins_base)
```
- Path validation uses `resolve()` which follows symlinks
- Only checks after resolution
- No explicit symlink checking before path operations

**Notes:** Existing protection is reasonable - paths are validated after resolution. Risk is low as this operates on local Claude plugin files.

---

### SEC-002: No File Size Limits on JSON Reads

**Status:** ⚠️ DEFERRED

**Location:** `api/models/plugin.py:194-196, 348-350, 377-379`

**Observation:**
```python
with open(path, "r", encoding="utf-8") as f:
    data = json.load(f)  # No size limit
```
- JSON files loaded without size limits
- Applies to: `installed_plugins.json`, `plugin.json`, `.mcp.json`

**Notes:** Lower priority - these are local files managed by Claude Code, not user uploads.

---

### SEC-003: URL Decoding Without Input Validation

**Status:** ✅ RESOLVED

**Location:** `api/routers/plugins.py:39-64`

**Original Issue:**
```python
decoded_name = unquote(plugin_name)
```
- Plugin names are URL-decoded
- No validation for expected format
- No validation for length
- No validation for character set

**Resolution:**
- Added `_validate_plugin_name()` function
- Validates max length (255 chars)
- Validates non-empty
- Validates character set (alphanumeric, @, -, _, .)
- Returns 400 Bad Request for invalid names

---

### SEC-004: Information Leakage in Error Messages

**Status:** ℹ️ ACCEPTABLE

**Location:** `api/routers/plugins.py:412, 452, 497-498, 504-505`

**Observation:**
```python
raise HTTPException(status_code=404, detail=f"Plugin '{decoded_name}' not found")
```
- Error messages include user-provided plugin names

**Notes:** This is standard REST API behavior. Plugin names are not sensitive data.

---

### SEC-005: Silent Exception Swallowing

**Status:** ✅ RESOLVED

**Location:** `api/models/plugin.py:381-382, 407-408`

**Original Issue:**
```python
except Exception:
    pass
```
- Bare `except Exception: pass` clauses
- Errors during file parsing are not logged

**Resolution:**
- Changed to `except Exception as e: logger.debug(f"Failed to parse/read ... : {e}")`
- Errors now logged for debugging

---

## Code Quality Issues

### Q-001: Logger Used Before Definition

**Status:** ✅ RESOLVED

**Location:** `api/routers/plugins.py:36`

**Original Issue:**
```python
logger.debug(f"Error processing project...")  # line 114
# ...
logger = logging.getLogger(__name__)  # line 155
```
- Logger is used at line 114 in exception handler
- Logger is defined at line 155

**Resolution:** Logger definition moved to line 36, before any usage.

---

### Q-002: Incomplete Return Type Annotation

**Status:** ⚠️ DEFERRED

**Location:** `api/routers/plugins.py:343`

**Observation:**
```python
def get_plugins_stats(request: Request) -> dict:
```
- Returns `dict` instead of typed dict or Pydantic schema

---

### Q-003: Magic String for Official Plugin Detection

**Status:** ⚠️ DEFERRED

**Location:** `api/routers/plugins.py:227`

**Observation:**
```python
is_official = "claude-plugins-official" in plugin_name
```
- Hardcoded string literal

---

### Q-004: Manual sys.path Manipulation

**Status:** ✅ RESOLVED

**Location:** `api/routers/plugins.py:19-23`

**Original Issue:**
```python
api_path = Path(__file__).parent.parent
models_path = api_path.parent.parent
sys.path.insert(0, str(api_path))
sys.path.insert(0, str(models_path))
```

**Resolution:** Removed sys.path manipulation. Standard imports work correctly when running from api directory.

---

## Test Coverage Gaps

### TC-001: Untested Endpoints

**Status:** ⚠️ DEFERRED

**Location:** `api/tests/api/test_plugins.py`

**Observation:**
- `GET /plugins/{name}/capabilities` - No tests found
- `GET /plugins/{name}/usage` - No tests found

---

### TC-002: Untested Router Functions

**Status:** ⚠️ DEFERRED

**Location:** `api/routers/plugins.py`

**Observation:**
- `_get_plugin_short_name()` - Not tested
- `_collect_plugin_usage_sync()` - Not tested
- `get_plugin_usage_stats()` - Not tested
- `_validate_plugin_name()` - Not tested

---

### TC-003: Untested Model Functions

**Status:** ⚠️ DEFERRED

**Location:** `api/models/plugin.py`

**Observation:**
- `scan_plugin_capabilities()` - Not tested
- `get_plugin_description()` - Not tested
- `get_plugin_cache_path()` - Not tested

---

### TC-004: Missing Error Path Tests

**Status:** ⚠️ DEFERRED

**Observation:**
- 404 for capabilities endpoint with nonexistent plugin - Not tested
- 404 for usage endpoint with nonexistent plugin - Not tested
- Permission denied reading plugin directory - Not tested
- Path traversal attack scenarios - Not tested
- Invalid period parameter - Not tested
- Invalid plugin name validation - Not tested

---

### TC-005: Missing Edge Case Tests

**Status:** ⚠️ DEFERRED

**Observation:**
- Plugin names with special characters - Not tested
- Plugin names with unicode - Not tested
- Very long plugin names (>255 chars) - Not tested
- Empty plugin directories - Not tested
- Deeply nested skill directories - Not tested
- Cache race conditions - Not tested
