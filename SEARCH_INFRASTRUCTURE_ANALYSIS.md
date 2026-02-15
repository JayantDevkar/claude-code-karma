# Backend Search & Indexing Infrastructure Analysis

**Date**: 2026-02-14  
**Status**: Complete exploration (Planning phase)

---

## Executive Summary

The claude-karma backend has **comprehensive SQLite FTS5 infrastructure ALREADY IN PLACE**. The codebase is not asking "how do we add SQLite FTS5?" but rather "how do we leverage the existing schema, indexer, and query layer?"

### Key Finding
**All 5 components requested are already implemented:**
1. ✅ SQLite database (`api/db/`) with FTS5 virtual table
2. ✅ sessions-index.json caching via `session_title_cache.py`
3. ✅ Server-side search filtering via `session_filter.py`
4. ✅ Title caching system with disk persistence
5. ✅ Full-text search patterns (external content FTS5)

---

## File Priority & Dependency Map

### Tier 1: Core Database Layer (Must Read First)

#### 1. **`api/db/schema.py`** (316 lines)
**Purpose**: SQLite schema definitions with FTS5 virtual table  
**Why Critical**:
- Defines the `sessions` table (9 indices, 27 columns)
- Creates `sessions_fts` virtual table (external content FTS5)
- **Key insight**: FTS5 indexes on `uuid`, `slug`, `initial_prompt`, `session_titles`, `project_path`
- Uses 3 AFTER INSERT/UPDATE/DELETE triggers to keep FTS in sync
- Schema version 6 with migration support

**Key Components**:
```sql
-- External content FTS5 (content=sessions)
CREATE VIRTUAL TABLE sessions_fts USING fts5(
    uuid, slug, initial_prompt, session_titles, project_path,
    content=sessions, content_rowid=rowid
);

-- Keeps FTS synced via triggers on sessions table
```

**What You Need to Know**:
- `SCHEMA_VERSION = 6` — tracks applied migrations
- Supports projection columns for FTS queries
- If FTS becomes out of sync: `INSERT INTO sessions_fts(sessions_fts) VALUES('rebuild');`

---

#### 2. **`api/db/connection.py`** (189 lines)
**Purpose**: Reader/Writer connection pattern for concurrent access  
**Why Critical**:
- **Writer singleton**: Background indexer thread (exclusive, WAL mode)
- **Reader connections**: Per-request via FastAPI, read-only mode
- Separates reads from writes to avoid serialization under WAL mode

**Key Functions**:
- `get_writer_db()` — Opens singleton, applies WAL/PRAGMA, creates schema
- `create_read_connection()` — New read-only connection per request
- `get_read_db()` — FastAPI dependency (yields None if SQLite not ready)
- `sqlite_read()` — Context manager with auto-fallback to JSONL

**Pragmas Applied**:
```python
PRAGMA journal_mode=WAL              # Write-Ahead Logging
PRAGMA synchronous=NORMAL            # Fast commits
PRAGMA cache_size=-64000             # 64MB
PRAGMA mmap_size=268435456           # 256MB memory-map
PRAGMA busy_timeout=5000             # 5s lock timeout
```

**Why This Matters for FTS5**:
- WAL mode allows concurrent reads while writer indexes
- Fast pragmas keep FTS queries snappy
- Connection pooling prevents file descriptor exhaustion

---

#### 3. **`api/db/queries.py`** (1,200+ lines)
**Purpose**: FTS5 query functions + aggregation queries  
**Why Critical**:
- **`query_all_sessions()`** — Main search endpoint with FTS5 integration
- Handles 3 search scopes: `both`, `titles`, `prompts`
- FTS token sanitization to prevent SQL injection
- Status filtering (active/completed)
- Project options aggregation

**FTS5 Search Implementation**:
```python
if search:
    # Sanitize tokens and build FTS5 MATCH expression
    raw_tokens = [t.strip() for t in search.split(",") if t.strip()][:7]
    tokens = [_sanitize_fts_token(t) for t in raw_tokens]
    
    if scope == "titles":
        fts_terms = " AND ".join(f'session_titles:{t}' for t in tokens)
    elif scope == "prompts":
        fts_terms = " AND ".join(f'(slug:{t} OR initial_prompt:{t})' for t in tokens)
    else:  # both
        fts_terms = " AND ".join(t for t in tokens)
    
    conditions.append(f"sessions_fts MATCH :fts_query")
    params["fts_query"] = fts_terms
```

**Key Helper Functions**:
- `_sanitize_fts_token()` — Strips FTS5 special chars, prevents injection
- `_query_project_options()` — Project filter dropdown (from projects table)
- `query_dashboard_stats()` — Date-range aggregation
- `query_analytics()` — Tool/model/cost rollups
- `query_session_chain()` — Session continuation chains

**Error Handling**:
```python
try:
    rows = conn.execute(query_sql, params).fetchall()
except sqlite3.OperationalError as e:
    logger.warning("FTS5 query error: %s", e)
    # Fallback to empty result set
    return {"sessions": [], "total": 0, ...}
```

---

### Tier 2: Indexing & Metadata Layer

#### 4. **`api/db/indexer.py`** (250+ lines)
**Purpose**: Background JSONL→SQLite sync daemon  
**Why Critical**:
- Runs on app startup, crawls `~/.claude/projects/`
- Detects changed JSONL files via mtime comparison
- Single-pass metadata extraction (no full Session parsing)
- Incremental: skips unchanged files
- Idempotent: safe to run multiple times

**Workflow**:
```
sync_all_projects()
  ├─ for each project_dir:
  │   └─ sync_project(conn, project_dir)
  │       ├─ Load db_mtimes for project
  │       └─ for each *.jsonl:
  │           ├─ Skip if mtime unchanged
  │           └─ _index_session(conn, path, mtime, size)
  ├─ _cleanup_stale_sessions(conn)
  └─ _update_project_summaries(conn)
```

**Key Metrics Tracked**:
- `is_db_ready()` — Readiness flag (used by title_cache fallback)
- `wait_for_ready(timeout)` — Block until initial index built
- `get_last_health()` — DB health metrics
- `get_last_sync_time()` — Timestamp of last successful sync

**Resilience**:
- Per-session try/except (skips errors, logs them)
- Non-blocking (background thread)
- Reuses Session model's `_load_metadata()` for extraction

---

#### 5. **`api/services/session_title_cache.py`** (400+ lines)
**Purpose**: Per-project in-memory title cache with disk persistence  
**Why Critical**:
- Avoids N+1 JSONL loads during search
- Singleton pattern with per-project threading locks
- Dual-source: SQLite (primary) + JSONL (fallback)
- Detects staleness via JSONL count comparison

**Caching Strategy**:
```python
class SessionTitleCache:
    _project_data: Dict[str, Dict[str, TitleEntry]]  # uuid -> {titles, slug, mtime}
    _project_locks: Dict[str, threading.Lock]         # Per-project locking
```

**Load Priority**:
1. Check in-memory cache
2. If stale (JSONL count changed >10%), rebuild
3. Prefer SQLite when available (fast)
4. Fall back to JSONL scanning (slow)
5. Persist result to disk at `~/.claude_karma/cache/titles/{encoded_name}.json`

**Key Methods**:
- `get_project_titles()` — Load all titles for project (lazy)
- `get_titles(encoded_name, uuid)` — Get titles for session
- `get_slug()` — Get session slug
- `set_title()` — Update cache + persist to disk
- `_is_stale()` — Check if rebuild needed
- `_build_from_sqlite()` — Extract titles from DB (preferred)
- `_build_from_jsonl()` — Scan JSONL files (fallback)
- `_extract_titles_lightweight()` — Line-by-line JSONL scan (fast)

**Lightweight JSONL Scanner** (key optimization):
```python
def _extract_titles_lightweight(jsonl_path):
    # Reads file line-by-line looking for:
    # - "type": "summary" entries (session titles)
    # - "slug" field (session slug)
    # Returns (titles, slug) WITHOUT full Session parsing
```

---

### Tier 3: Search & Filtering Layer

#### 6. **`api/services/session_filter.py`** (100+ lines)
**Purpose**: Unified session filtering logic  
**Why Critical**:
- Consolidates duplicate filter logic from routers
- Defines filter enums: `SearchScope`, `SessionStatus`
- Provides `determine_session_status()` helper
- **Active threshold**: 5 minutes (ACTIVE_THRESHOLD_SECONDS = 300)

**Filter Enums**:
```python
class SearchScope(str, Enum):
    BOTH = "both"      # Search titles + prompts
    TITLES = "titles"  # Search session titles only
    PROMPTS = "prompts"  # Search slug + initial_prompt + project_path

class SessionStatus(str, Enum):
    ALL = "all"        # No filter
    ACTIVE = "active"  # Last activity < 5 minutes
    COMPLETED = "completed"  # Last activity >= 5 minutes
    ERROR = "error"    # Requires JSONL parsing (future)
```

**SessionMetadata** (lightweight model):
```python
@dataclass
class SessionMetadata:
    uuid, encoded_name, project_path, message_count,
    start_time, end_time, slug, initial_prompt, git_branch,
    title, session_titles,
    _session  # Lazy loader
```

---

### Tier 4: API Integration Layer

#### 7. **`api/routers/sessions.py`** (Top 150 lines shown)
**Purpose**: HTTP endpoints that use SQLite queries  
**Why Critical**:
- **`/sessions`** (GET) — List all sessions with search/filter/pagination
- Integrates SQLite via `query_all_sessions()` or JSONL fallback
- HTTP caching via ETag/Last-Modified
- Returns `AllSessionsResponse` with sessions, totals, filter options

**Helper Functions**:
- `detect_command_source()` — Classify commands (plugin/project/user)
- `_enrich_chain_titles_by_slug()` — Propagate titles across slug siblings
- `_get_session_source()` — Detect if from Claude Desktop

---

#### 8. **`api/models/project.py`** (200+ lines shown)
**Purpose**: Project model + path encoding/decoding  
**Why Critical**:
- Path encoding: `/Users/me/repo` → `-Users-me-repo`
- `get_cached_jsonl_count()` — TTL-cached session count (prevents expensive glob)
- Used by title_cache staleness detection

**Threading Optimization**:
```python
_jsonl_count_cache: TTLCache = TTLCache(maxsize=1000, ttl=5.0)

def get_cached_jsonl_count(project_dir: Path) -> int:
    # Returns cached count with 5-second TTL
    # Prevents expensive glob() on every filter request
```

---

#### 9. **`api/models/session_index.py`** (Shown head)
**Purpose**: Parse Claude's `sessions-index.json` file  
**Why Critical**:
- Defines `SessionIndexEntry` (metadata per session)
- Provides property aliases: `uuid`, `start_time`, `end_time`, `initial_prompt`
- Fallback titles when SQLite not ready

---

## Database Schema Visual

```
~/.claude/projects/{encoded-name}/{uuid}.jsonl
    ↓ (Background indexer reads JSONL, extracts metadata)
    ↓
SQLite Database (at ~/.claude_karma/db.sqlite3)
    ├─ sessions (27 cols, 9 indices)
    │   └─ Core metadata: uuid, slug, project, start_time, message_count, cost, etc.
    │
    ├─ sessions_fts (Virtual FTS5 table, external content)
    │   └─ Full-text search over: uuid, slug, initial_prompt, session_titles, project_path
    │
    ├─ session_tools (tool_name → count, per session)
    ├─ session_skills (skill_name → count, per session)
    ├─ session_commands (command_name → count, per session)
    ├─ subagent_invocations (per-agent metrics)
    ├─ subagent_tools (tool_name → count, per invocation)
    ├─ message_uuids (message_uuid → session_uuid mapping)
    ├─ session_leaf_refs (leaf_uuid references for chain detection)
    └─ projects (Project summary cache)

    ↑ (Query layer reads SQLite)
    ↑
FastAPI Routes (/sessions, /analytics, /agents, /skills)
    ↑ (HTTP response with caching headers)
    ↑
Frontend (SvelteKit @ port 5173)
```

---

## Search Flow (From Frontend to FTS5)

```
Frontend: /sessions?search=autopilot&scope=titles&status=active
    ↓
GET /sessions router (routers/sessions.py)
    ↓
SQLite read connection (db/connection.py:create_read_connection)
    ↓
query_all_sessions(conn, search="autopilot", scope="titles", status="active")
    ├─ Build FTS5 MATCH expression: "session_titles:autopilot"
    ├─ Build status filter: julianday(now) - julianday(end_time) < threshold_days
    │
    └─ Execute SQL:
        SELECT * FROM sessions s
        JOIN sessions_fts ON sessions_fts.rowid = s.rowid
        WHERE sessions_fts MATCH 'session_titles:"autopilot"'
          AND status_filter_condition
        ORDER BY s.start_time DESC
        LIMIT 200 OFFSET 0
    ↓
Parse JSON fields (models_used, session_titles)
    ↓
Return AllSessionsResponse {
    sessions: [...],
    total: 42,
    status_counts: {active: 10, completed: 32},
    project_options: [...]
}
    ↓
Frontend renders with HTTP caching headers
```

---

## Key Implementation Patterns

### Pattern 1: FTS5 Token Sanitization
```python
# Prevents SQL injection via special FTS5 characters
def _sanitize_fts_token(token: str) -> str:
    sanitized = re.sub(r'[()\"\\*]', '', token)  # Strip special chars
    if ':' in sanitized and not re.match(r'^[a-zA-Z_]+:', sanitized):
        sanitized = sanitized.replace(':', '')
    return f'"{sanitized}"'  # Wrap in quotes
```

### Pattern 2: Graceful FTS5 Error Handling
```python
try:
    rows = conn.execute(query_sql, params).fetchall()
except sqlite3.OperationalError as e:
    logger.warning("FTS5 query error: %s", e)
    # Fallback to empty result (caller handles gracefully)
    return {"sessions": [], "total": 0, "status_counts": {...}}
```

### Pattern 3: Dual-Source Title Cache
```python
# 1. Try SQLite (fast)
if settings.use_sqlite:
    data = _build_from_sqlite(encoded_name)
    if data: return data

# 2. Fall back to JSONL scan (slow)
data = _build_from_jsonl(encoded_name)
return data
```

### Pattern 4: SQLite Ready Gate
```python
# Prevent 500 errors if indexer hasn't finished startup
from db.indexer import is_db_ready, wait_for_ready

@app.on_event("startup")
def startup():
    if settings.use_sqlite:
        wait_for_ready(timeout=30.0)  # Block startup if needed

# In endpoints:
if not is_db_ready():
    return jsonl_fallback()  # Use slow path if index not ready
```

---

## Configuration Points

### `api/config.py` (Settings)
- `use_sqlite: bool` — Enable/disable SQLite caching
- `sqlite_db_path: Path` — Database file location
- `projects_dir: Path` — Where Claude stores sessions
- `karma_base: Path` — Where claude-karma caches files

---

## Known Limitations & Future Work

1. **Error Status Detection**
   - Status enum includes `ERROR` but requires JSONL message parsing
   - Not yet implemented in queries (returns 0)

2. **FTS5 Rebuild**
   - If FTS becomes out of sync, manual rebuild needed:
     ```sql
     INSERT INTO sessions_fts(sessions_fts) VALUES('rebuild');
     ```
   - No automatic detection yet

3. **Concurrent Writes**
   - SQLite supports ONE writer (background indexer)
   - Multiple HTTP readers are OK (WAL mode)
   - If multiple processes try to index, second one bails gracefully

4. **Schema Migrations**
   - Versioning in place (SCHEMA_VERSION = 6)
   - Incremental migrations exist (v1→v6)
   - Old migrations are idempotent

---

## Testing Considerations

### Unit Tests
- `api/tests/test_db.py` — SQLite connection + schema tests
- `api/tests/test_session_cache.py` — Title cache staleness detection

### Integration Test Points
1. FTS5 query with special characters (sanitization)
2. Scope filtering (titles/prompts/both)
3. Status filtering (active/completed)
4. Pagination (offset/limit)
5. Title cache rebuild when new sessions added
6. Fallback when SQLite not ready

---

## Dependency Graph

```
routers/sessions.py
├─ db/queries.py:query_all_sessions()
│  ├─ db/connection.py:create_read_connection()
│  ├─ db/schema.py (FTS5 definitions)
│  └─ services/session_filter.py (filter enums)
│
├─ services/session_title_cache.py:title_cache
│  ├─ db/indexer.py:is_db_ready()
│  ├─ models/project.py:get_cached_jsonl_count()
│  └─ db/queries.py (for SQLite fallback)
│
└─ services/session_filter.py
   └─ utils.py:normalize_timezone()
```

---

## Recommended Reading Order

For **understanding the full stack**:
1. Start: `db/schema.py` (understand the schema)
2. Then: `db/indexer.py` (understand how JSONL gets into DB)
3. Then: `db/queries.py` (understand FTS5 queries)
4. Then: `services/session_title_cache.py` (understand caching strategy)
5. Then: `routers/sessions.py` (understand HTTP integration)

For **implementing new features**:
- FTS5 search improvements → `db/queries.py`
- Title extraction → `services/session_title_cache.py`
- Indexing logic → `db/indexer.py`
- HTTP endpoints → `routers/sessions.py`

---

## File Sizes & Complexity

| File | Lines | Complexity | Purpose |
|------|-------|-----------|---------|
| `db/schema.py` | 316 | Medium | Schema + migrations |
| `db/connection.py` | 189 | Low | Connection pooling |
| `db/queries.py` | 1200+ | High | FTS5 + aggregation queries |
| `db/indexer.py` | 250+ | Medium | JSONL→SQLite sync |
| `services/session_title_cache.py` | 400+ | High | Title caching + fallback |
| `services/session_filter.py` | 100+ | Low | Filter enums |
| `routers/sessions.py` | 150+ shown | Medium | HTTP endpoints |
| `models/project.py` | 200+ shown | Medium | Path encoding + JSONL count |
| `models/session_index.py` | Partial | Low | Index schema |

**Total: ~2,800+ lines of search/indexing infrastructure**

---

## Summary: What's NOT Missing

✅ SQLite database exists  
✅ FTS5 virtual table exists with 3 trigger-based sync  
✅ Sessions-index.json parsing exists  
✅ Title caching with disk persistence exists  
✅ Server-side search filtering exists  
✅ Error handling for FTS5 failures exists  
✅ Fallback to JSONL when SQLite not ready exists  
✅ Background indexer thread exists  
✅ Reader/Writer connection separation exists  
✅ HTTP caching headers exist  

---

## Conclusion

**The backend already has a production-grade search & indexing infrastructure in place.** The 9 key files listed above provide:

1. **SQLite schema** with external content FTS5 virtual table
2. **Incremental indexer** that keeps DB in sync with JSONL files
3. **FTS5 query builder** with token sanitization and scope filtering
4. **Title cache** with disk persistence and staleness detection
5. **Reader/Writer separation** for concurrent access under WAL mode

The system is designed to be:
- **Non-blocking** (indexer runs in background)
- **Graceful** (falls back to JSONL if indexing fails)
- **Efficient** (incremental, 5-second TTL on counts, 64MB cache)
- **Maintainable** (schema versioning, migration support)

Any new search features should leverage these existing components rather than reinvent them.
