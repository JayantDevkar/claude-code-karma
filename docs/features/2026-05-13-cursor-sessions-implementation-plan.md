# Cursor Sessions — Backend Implementation Plan

**Issue:** [#71](https://github.com/JayantDevkar/claude-code-karma/issues/71)
**Companion research doc:** [`2026-05-13-cursor-sessions-integration.md`](./2026-05-13-cursor-sessions-integration.md)
**Branch:** `worktree-71-cursor-sessions-research`
**Owner:** backend
**Status:** draft (pre-implementation)

> **Decisions locked** (via 2026-05-13 design review):
> 1. **Full indexer** — materialize Cursor sessions + bubbles + tool calls into `metadata.db`. All endpoints read from our SQLite cache.
> 2. **List subfolder workspaces separately** (faithful to Cursor's workspace-hash model).
> 3. **v1 scope: 10 endpoints** — projects (×2), session detail, timeline, tools, file-activity, analytics, plans, MCP, agents, **skills (listing only with `tracking_unavailable` flag)**.
> 4. **Auto-detect**: if `state.vscdb` exists at the expected path, the indexer runs. No env var, no toggle.
>
> **Additional decisions (2026-05-13 Phase 3 design review):**
> 5. **Skills posture**: List definitions from `~/.cursor/skills-cursor/` + `~/.cursor/skills/`; surface `tracking_unavailable: true` flag. **No usage tracking** — Cursor 2.5.26 emits zero skill-invocation telemetry to disk (10 signals exhaustively checked).
> 6. **`session_tools.invocation_source` column added in v12** — PK becomes 3-tuple `(session_uuid, tool_name, invocation_source)`. Existing rows backfilled with `'main'`.
> 7. **Architecture: Option C — Pragmatic balanced** — self-contained `api/cursor/` package, ~8 `if source == 'cursor':` dispatch branches across 5 routers, MCP re-prefix trick (`mcp__{server}__{tool}`) reuses existing aggregation, 23 existing files untouched.
> 8. **Delivery: One big PR** — single ~1,800-line PR with full feature.
> 9. **v11 dependency**: blocks on `agent-coord-integration` (v11 substrate) merging to main. Our migration is **v12** (not v13 — sequence-strict).

## Status: implementation in progress (2026-05-13)

**Unblocked**: agent-coord-integration work is dropped, so we own the v11 slot.

**Done** (4 commits on this branch):
- ✅ `eacaf56` — v11 schema migration: 3-tuple `session_tools` PK + 6 new Cursor tables + `cursor_workspace_hash` column. 119 db tests pass.
- ✅ Cursor parser package `api/cursor/{paths,state_db,workspace,composer,bubble,tools,plans,mcp,skills,agents}.py`. End-to-end verified on real Cursor 2.5.26 data (1,098 sessions / 66k bubbles / 30k tool calls / 124 plans / 103 MCP servers / 1,988 MCP tools / 0 errors / 13.6s cold scan / 1.2s incremental).
- ✅ Cursor indexer `api/cursor/indexer.py` + `api/services/cursor_indexer_service.py` wired into FastAPI lifespan. Auto-detect: no-op if Cursor not installed.
- ✅ `9a051e8` — Router dispatch for `/projects` + `/projects/{cursor:<hash>}` + `/sessions/{uuid}` + `/sessions/{uuid}/{timeline,tools,file-activity}`. 1087 model+db tests still pass.

**Deferred to a follow-up commit on this same branch/PR**:
- `/analytics/projects/{cursor:<hash>}` — Cursor analytics rollup
- `/plans` — union with `cursor_plan` rows
- `/tools` (MCP overview) — append `cursor_mcp_*` descriptors
- `/agents` — append Cursor built-in agents (constant list)
- `/skills` — append Cursor skill definitions with `tracking_unavailable=True`
- Schema: `SkillItem.source` + `SkillItem.tracking_unavailable` + `McpToolDetail.arguments_schema` (additive Pydantic fields)
- Unit + integration tests for `api/cursor/` (target: ≥80% coverage)

---

## 1. Goals & Non-Goals

### Goals (v1)

- Cursor 2.5.26 sessions appear in claude-karma's existing `/projects`, `/sessions/*`, `/analytics`, `/plans`, `/tools`, `/agents` endpoints alongside Claude Code sessions.
- Source discrimination via the existing `sessions.session_source` column (new value: `'cursor'`).
- macOS first; Linux + Windows paths wired but not the priority test target.
- Zero behavior change for users who don't have Cursor installed.

### Non-Goals (v1)

- ❌ `/live-sessions/*` (Cursor has no hook substrate; we won't fake it)
- ❌ `/hooks/*` (Cursor has no hook API)
- ❌ `/skills/*` and `/commands/*` usage tracking (Cursor stores no invocation log)
- ❌ `/history/*` (VS Code Local History — defer to v2)
- ❌ Cursor 2.4 Subagents surfacing (storage works but no real data exists yet on 2.5.26)
- ❌ Frontend / UI work (separate workstream, designer-led)
- ❌ Write paths (POST/PUT/DELETE for Cursor data) — read-only mirror
- ❌ Cursor "Composer" model name normalization, cost calculation
- ❌ Cursor's `agentKv:blob:*` parallel record (we use `bubbleId` records as ground truth)

---

## 2. Architecture Overview

### 2.1 Module layout

```
api/
├── cursor/                                              # NEW PACKAGE
│   ├── __init__.py
│   ├── paths.py             # OS-specific path detection (~/.cursor, User/globalStorage)
│   ├── state_db.py          # WAL-safe sqlite open helpers (immutable=1)
│   ├── workspace.py         # workspaceStorage/<hash>/workspace.json scanner
│   ├── composer.py          # composerData parser (header)
│   ├── bubble.py            # bubbleId parser (messages)
│   ├── tools.py             # toolFormerData extractor + int→name registry
│   ├── plans.py             # ~/.cursor/plans/*.plan.md YAML+md parser
│   ├── mcp.py               # ~/.cursor/projects/*/mcps/*/* introspection
│   ├── agents.py            # built-in agent inventory (hardcoded, mode-driven)
│   └── indexer.py           # the main indexer loop (60s tick)
├── services/
│   └── cursor_indexer_service.py    # FastAPI startup hook + background worker
├── routers/
│   └── (dispatch-aware changes in projects.py, sessions.py, analytics.py, plans.py,
│        tools.py, agents.py — NO new router files)
├── models/
│   └── (no changes — existing schemas absorb both sources)
└── db/
    └── schema.py            # v12 migration: cursor_session_meta + indexer tables
```

### 2.2 Read path

```
HTTP request
   ↓
Existing router (projects.py / sessions.py / ...)
   ↓
Existing service (sqlite_read)
   ↓
metadata.db — joined query: SELECT ... WHERE session_source='cursor'
   ↓
Response (existing Pydantic schemas)
```

**Indexer (separate path, runs every 60s):**

```
Indexer tick
   ↓
1. paths.detect_cursor_install()  → bail if no state.vscdb
2. workspace.scan_workspaces()    → list (hash, folder_uri) pairs
3. composer.iter_composers()      → for each workspace, get composer IDs
4. composer.read_composer_data()  → upsert sessions + cursor_session_meta rows
5. bubble.iter_bubbles()          → upsert cursor_bubble rows for new bubbles only
6. tools.extract_tool_calls()     → upsert session_tools rows
7. plans.scan_plans()             → upsert cursor_plan rows
8. mcp.scan_mcp_descriptors()     → upsert cursor_mcp_server / cursor_mcp_tool rows
9. analytics.recompute_rollups()  → refresh cursor_analytics_daily view-table
```

### 2.3 Why full indexer (not on-demand)

Recap of the decision: **read-path simplicity wins.** Three concrete payoffs:

1. **No per-request SQLite-on-2.4-GB scans.** A `LIKE 'composerData:%'` over 186k keys is fast individually, but every `/projects`, `/sessions/all`, `/analytics/*` call would hit it. Materialized rows in `metadata.db` keep p99 latency flat regardless of Cursor DB size.
2. **Joins with existing tables Just Work.** `session_relationships`, `session_tools`, `subagent_invocations` already FK off `sessions.uuid`. With indexed rows, Cursor sessions inherit every existing query path for free.
3. **FTS5 free.** Cursor sessions get full-text search via the existing `sessions_fts` virtual table.

Cost: ~140 MB of `metadata.db` growth per active Cursor user (1300 composers × ~50 bubbles × ~2 KB indexed fields). Storage is cheap; query latency is not.

---

## 3. Database Schema — v12 Migration

> Migration follows the existing pattern in `api/db/schema.py` (already at v11 on `agent-coord-integration`). v12 lands **after** #67's v11 has merged into main.

### 3.1 Column additions

```sql
-- Cursor's workspaceStorage hash. Source of truth for workspace identity.
-- For Claude Code sessions: NULL.
ALTER TABLE sessions ADD COLUMN cursor_workspace_hash TEXT;

-- Partial index — small footprint, fast workspace → sessions lookups
CREATE INDEX IF NOT EXISTS idx_sessions_cursor_ws
    ON sessions(cursor_workspace_hash)
    WHERE cursor_workspace_hash IS NOT NULL;
```

### 3.2 New table: `cursor_session_meta`

Cursor-specific fields that don't map cleanly to `sessions` columns. One row per Cursor session.

```sql
CREATE TABLE IF NOT EXISTS cursor_session_meta (
    session_uuid              TEXT PRIMARY KEY,
    unified_mode              TEXT,    -- 'agent' | 'chat' | 'plan' | 'debug' | 'edit'
    force_mode                TEXT,
    agent_backend             TEXT,    -- 'cursor-agent' | '' | future...
    context_usage_percent     REAL,
    context_tokens_used       INTEGER,
    context_token_limit       INTEGER,
    is_agentic                INTEGER DEFAULT 0,
    is_archived               INTEGER DEFAULT 0,
    is_draft                  INTEGER DEFAULT 0,
    is_spec                   INTEGER DEFAULT 0,
    is_project                INTEGER DEFAULT 0,
    is_worktree               INTEGER DEFAULT 0,
    is_best_of_n_parent       INTEGER DEFAULT 0,
    is_best_of_n_subcomposer  INTEGER DEFAULT 0,
    parent_composer_id        TEXT,    -- for sub-composers: link upward
    created_on_branch         TEXT,
    referenced_plans_json     TEXT,    -- JSON array of plan slugs
    todos_json                TEXT,    -- JSON dump of composerData.todos[]
    sub_composer_ids_json     TEXT,    -- JSON array of subagent/sub composer IDs
    name                      TEXT,    -- composerData.name
    subtitle                  TEXT,    -- composerData.subtitle
    status                    TEXT,    -- 'completed' | 'aborted' | 'none'
    total_lines_added         INTEGER DEFAULT 0,
    total_lines_removed       INTEGER DEFAULT 0,
    added_files_count         INTEGER DEFAULT 0,
    removed_files_count       INTEGER DEFAULT 0,
    files_changed_count       INTEGER DEFAULT 0,
    indexed_at                INTEGER NOT NULL,
    FOREIGN KEY (session_uuid) REFERENCES sessions(uuid) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_cursor_meta_mode ON cursor_session_meta(unified_mode);
CREATE INDEX IF NOT EXISTS idx_cursor_meta_parent ON cursor_session_meta(parent_composer_id);
```

### 3.3 New table: `cursor_bubble`

Per-message storage. Bubble bodies stay as JSON; structured fields are extracted for indexing.

```sql
CREATE TABLE IF NOT EXISTS cursor_bubble (
    session_uuid        TEXT NOT NULL,
    bubble_id           TEXT NOT NULL,
    seq                 INTEGER NOT NULL,           -- order in fullConversationHeadersOnly
    bubble_type         INTEGER NOT NULL,            -- 1=user, 2=assistant
    capability_type     INTEGER,                     -- 15=tool_call, 30=thinking, NULL=plain
    created_at_ms       INTEGER,                     -- bubble.createdAt (string parsed)
    has_thinking        INTEGER DEFAULT 0,
    thinking_duration_ms INTEGER,
    has_tool_call       INTEGER DEFAULT 0,
    text_preview        TEXT,                        -- first 200 chars
    text_full           TEXT,                        -- full text (may be large)
    raw_json            TEXT,                        -- full bubble JSON for rare fields
    PRIMARY KEY (session_uuid, bubble_id),
    FOREIGN KEY (session_uuid) REFERENCES sessions(uuid) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_cursor_bubble_session_seq ON cursor_bubble(session_uuid, seq);
CREATE INDEX IF NOT EXISTS idx_cursor_bubble_type ON cursor_bubble(session_uuid, bubble_type);
```

### 3.4 Reuse existing `session_tools`

Tool calls go into the **existing** `session_tools` table — no new table needed. Indexer writes:

```sql
INSERT INTO session_tools (session_uuid, tool_name, tool_use_id, args_json, result_text,
                           invocation_source, ts_ms)
VALUES (?, ?, ?, ?, ?, 'cursor', ?)
```

`invocation_source='cursor'` distinguishes Cursor tool calls from Claude Code's. (The column already exists for the `'main'` vs `'subagent'` split — we add a third value.)

### 3.5 New table: `cursor_plan`

Parsed `~/.cursor/plans/*.plan.md` files.

```sql
CREATE TABLE IF NOT EXISTS cursor_plan (
    slug                TEXT PRIMARY KEY,           -- filename without .plan.md
    plan_id             TEXT,                        -- 8-hex suffix
    name                TEXT,
    overview            TEXT,
    todos_json          TEXT,                        -- YAML todos[] dumped as JSON
    body_md             TEXT,
    file_path           TEXT NOT NULL,
    file_mtime_ms       INTEGER NOT NULL,
    indexed_at          INTEGER NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_cursor_plan_id ON cursor_plan(plan_id);
```

### 3.6 New tables: `cursor_mcp_server`, `cursor_mcp_tool`

```sql
CREATE TABLE IF NOT EXISTS cursor_mcp_server (
    server_identifier   TEXT NOT NULL,
    workspace_hash      TEXT NOT NULL,               -- which workspace declares it
    server_name         TEXT,
    source              TEXT,                         -- 'plugin' | 'user' | 'builtin' (heuristic)
    file_path           TEXT NOT NULL,
    indexed_at          INTEGER NOT NULL,
    PRIMARY KEY (server_identifier, workspace_hash)
);

CREATE TABLE IF NOT EXISTS cursor_mcp_tool (
    server_identifier   TEXT NOT NULL,
    workspace_hash      TEXT NOT NULL,
    tool_name           TEXT NOT NULL,
    description         TEXT,
    arguments_json      TEXT,                         -- JSON Schema
    file_path           TEXT NOT NULL,
    indexed_at          INTEGER NOT NULL,
    PRIMARY KEY (server_identifier, workspace_hash, tool_name),
    FOREIGN KEY (server_identifier, workspace_hash)
        REFERENCES cursor_mcp_server(server_identifier, workspace_hash) ON DELETE CASCADE
);
```

### 3.7 FTS5 inclusion

Add Cursor sessions to the existing `sessions_fts` virtual table. The schema doesn't change — only the trigger logic needs to insert `cursor_bubble.text_full` along with Claude Code message content. Detail in §5.4.

### 3.8 Migration block (drop-in for `schema.py`)

```python
if current_version < 12:
    logger.info("Migrating → v12: Cursor session support")
    conn.executescript("""
        ALTER TABLE sessions ADD COLUMN cursor_workspace_hash TEXT;

        CREATE INDEX IF NOT EXISTS idx_sessions_cursor_ws
            ON sessions(cursor_workspace_hash)
            WHERE cursor_workspace_hash IS NOT NULL;

        -- (all CREATE TABLE statements from §3.2, 3.3, 3.5, 3.6)
    """)
    current_version = 12
```

---

## 4. Source-Discrimination Strategy

### 4.1 The `session_source` enum

Add `'cursor'` as a new value alongside the existing `'desktop'` and `NULL` (Claude Code default).

```python
# api/models/enums.py (new file, or extend existing constants)
class SessionSource(StrEnum):
    CLAUDE_CODE = "claude_code"    # explicit (writes 'claude_code' going forward)
    CURSOR = "cursor"
    DESKTOP = "desktop"            # existing (PR #37)
```

**Backwards compatibility:** `NULL` and missing values default to `claude_code`. A backfill migration in v12 sets `session_source = 'claude_code'` for all existing `NULL` rows (cosmetic — query logic already tolerates NULL).

### 4.2 Dispatch in routers

Existing routers stay shape-stable. They issue source-agnostic queries; the source column filters or joins as needed:

```python
# api/routers/sessions.py — GET /sessions/{uuid}
@router.get("/sessions/{uuid}")
def get_session(uuid: str) -> SessionDetail:
    row = sqlite_read_one(
        "SELECT session_source FROM sessions WHERE uuid = ?", (uuid,)
    )
    if not row:
        raise HTTPException(404)
    if row["session_source"] == "cursor":
        return get_cursor_session_detail(uuid)
    return get_claude_code_session_detail(uuid)  # existing logic, unchanged
```

No new query parameters required. Optional `?source=cursor` hint can be added later if there's a perf reason.

### 4.3 UUID safety

Cursor composerIds and Claude Code session UUIDs are both UUIDv4. Collision probability at our scale is effectively zero (see research doc Q4). The PRIMARY KEY constraint on `sessions.uuid` enforces uniqueness if collision ever did happen — first-writer wins, second insert fails loudly. Acceptable.

---

## 5. Endpoint-by-Endpoint Implementation

> All endpoints reuse existing Pydantic schemas. New code = service-layer dispatch only.

### 5.1 `GET /projects` and `GET /projects/{encoded_name}`

**File:** `api/routers/projects.py`

**Change:** `list_projects()` joins `sessions` grouped by `(session_source, project)`. For Cursor rows, `project` is derived from `cursor_workspace_hash → workspace.json.folder URI → real path`. Decoded display name = the basename of the folder URI's path.

```python
def list_projects() -> list[ProjectSummary]:
    rows = sqlite_read("""
        SELECT
            session_source,
            COALESCE(cursor_workspace_hash, project) AS key,
            project AS real_path,
            COUNT(*) AS session_count,
            MAX(ts_ms) AS last_active_ms
        FROM sessions
        GROUP BY session_source, key
    """)
    return [build_project_summary(r) for r in rows]
```

`encoded_name` for Cursor projects = the 16-hex `cursor_workspace_hash` (not the lossy `~/.cursor/projects/<encoded>/` form). Path-decoding is bypassed for Cursor — the workspace.json folder URI is the source of truth.

### 5.2 `GET /sessions/{uuid}`

**File:** `api/routers/sessions.py`

Dispatch to `cursor.composer.get_detail(uuid)` when `session_source='cursor'`. Returns `SessionDetail` populated from `cursor_session_meta` + `cursor_bubble` rows. Fields that don't map (e.g., compaction boundary count) return 0 / empty.

### 5.3 `GET /sessions/{uuid}/timeline`

**File:** `api/routers/sessions.py`

Walks `cursor_bubble` ORDER BY seq, emits `TimelineEvent`s. Event-type derivation:
- `bubble_type=1` → `user_message`
- `bubble_type=2, capability_type=30` → `thinking`
- `bubble_type=2, capability_type=15` → `tool_call` (with `session_tools` join for details)
- `bubble_type=2, capability_type IS NULL` → `assistant_message`

### 5.4 `GET /sessions/{uuid}/tools`

**File:** `api/routers/sessions.py`

Existing query against `session_tools` already works once Cursor rows are inserted with `invocation_source='cursor'`. Aggregate by `tool_name`, return `ToolUsageSummary[]`.

### 5.5 `GET /sessions/{uuid}/file-activity`

**File:** `api/routers/sessions.py`

Filter `session_tools` to file-op tools using a name allowlist:

```python
FILE_OP_TOOLS_CURSOR = {
    "read_file_v2", "read_file",
    "edit_file", "search_replace", "write_file", "create_file",
    "list_dir", "glob_file_search", "grep_search",
    "delete_file",
}
```

For each row, parse `args_json` per-tool to extract the file path (the path key varies — see §6.2). Return `FileActivity[]`.

### 5.6 `GET /analytics/projects/{encoded_name}`

**File:** `api/routers/analytics.py`

Existing aggregator already groups by source. Cursor data fills:
- `total_tokens` from sum of `cursor_session_meta.context_tokens_used`
- `tool_usage` from `session_tools` GROUP BY tool_name
- `time_heatmap` from `sessions.ts_ms` bucketed
- `model_usage` from `sessions.model` (populated from `composerData.modelConfig.modelName`)
- `cost` — **not populated for Cursor in v1** (we don't have unit pricing for Cursor's Composer or Claude-via-Cursor consumption); field stays 0/null

### 5.7 `GET /plans` and `GET /plans/{slug}`

**File:** `api/routers/plans.py`

New service-layer dispatch:
- Claude Code plans live in `~/.claude/plans/<slug>.md` (existing logic)
- Cursor plans live in `cursor_plan` table (populated by indexer from `~/.cursor/plans/*.plan.md`)

Both surface as `PlanSummary` / `PlanDetail`. `cursor_plan.todos_json` populates `PlanDetail.todos[]` directly.

Plan→session linkage: `cursor_session_meta.referenced_plans_json` ↔ `cursor_plan.plan_id` (the 8-hex suffix).

### 5.8 `GET /tools` (MCP overview) and `GET /tools/{server}/{tool}`

**File:** `api/routers/tools.py`

Reads `cursor_mcp_server` + `cursor_mcp_tool` for the static descriptor surface. Call counts come from `session_tools` joined on `tool_name`. Sessions list joined via `session_tools.session_uuid`.

**Note:** Cursor's MCP tool JSON ships full JSON Schema for arguments. We expose it via a NEW optional field on `McpToolDetail`:

```python
class McpToolDetail(BaseModel):
    # ... existing fields ...
    arguments_schema: dict[str, Any] | None = None    # NEW (Cursor populates; Claude Code stays None for v1)
```

Frontend can render schema for Cursor and skip for Claude Code.

### 5.9 `GET /agents`

**File:** `api/routers/agents.py`

Cursor has built-in agents only (Composer, Explore, Plan, Debug, Edit, Bash — derived from `unifiedMode` values). They're hardcoded in `api/cursor/agents.py` since there's no on-disk inventory. Surface them with `is_plugin=False, source='cursor-builtin'`.

`GET /agents/usage` for Cursor agents = `COUNT(*) FROM cursor_session_meta GROUP BY unified_mode`.

`POST/DELETE /agents/{name}` — Cursor agents are read-only; routes return 403 for `source='cursor-builtin'`. Existing Claude Code custom-agent CRUD unaffected.

---

## 6. Indexer Internals

### 6.1 Lifecycle

```python
# api/services/cursor_indexer_service.py
class CursorIndexerService:
    def __init__(self):
        self.installed = detect_cursor_install()
        self.last_full_scan_at = 0
        self.last_incremental_at = 0

    async def startup(self):
        if not self.installed:
            logger.info("Cursor not detected; indexer disabled")
            return
        await self.run_full_scan()           # blocking on startup, ~10s for 1300 composers
        asyncio.create_task(self.tick_loop()) # background incremental indexer

    async def tick_loop(self):
        while True:
            await asyncio.sleep(60)
            try:
                await self.run_incremental_scan()
            except Exception as e:
                logger.exception("Cursor indexer tick failed: %s", e)
```

Hook into FastAPI's `startup_event` in `main.py`. Run alongside the existing reconciliation timers (sync v3 pattern, `watcher_manager.py`).

### 6.2 Full vs incremental scan

| Operation | Full scan | Incremental scan |
|---|---|---|
| When | Startup; first run after gap > 1h | Every 60s |
| What | Walk every `composerData:*` + every `bubbleId:*` | Diff: only composers where `lastUpdatedAt` > `cursor_session_meta.indexed_at` |
| Cost | ~10s for 1300 composers / 70k bubbles on inspected machine | <500ms typical (only active composers update) |
| Lock posture | `?mode=ro&immutable=1` on global state.vscdb | Same |

**Incremental key:** `composerData.lastUpdatedAt` is the change-detection field. We compare against `cursor_session_meta.indexed_at` (which we stamp on insert/update). New composers are detected by `composerId NOT IN (SELECT session_uuid FROM cursor_session_meta)`.

### 6.3 Tool-call extraction (corrected from research)

```python
# api/cursor/tools.py
TOOL_INT_NAME_REGISTRY = {
    # Built from POC scan of 31,829 tool calls on 1334 composers
    40: "read_file_v2",
    38: None,            # edit family — use bubble.toolFormerData.name (varies)
    15: "run_terminal_command_v2",
    19: None,            # MCP tool — name from rawArgs.name or .toolName
    7:  None,            # older edit
    35: "todo_write",
    5:  "read_file",     # older
    41: None,            # grep family
    39: "list_dir",
    42: "glob_file_search",
    3:  "codebase_search",
    30: "read_multiple_files",
    9:  None,            # older grep
    43: "plan_tool",
}

def extract_tool_call(bubble: dict) -> dict | None:
    tfd = bubble.get("toolFormerData")    # TOP LEVEL — not bubble.capabilities
    if not tfd:
        return None
    return {
        "tool_name": tfd.get("name") or TOOL_INT_NAME_REGISTRY.get(tfd.get("tool")) or f"tool_{tfd.get('tool')}",
        "tool_use_id": tfd.get("toolCallId"),
        "args_json": tfd.get("rawArgs", "{}"),
        "result_text": tfd.get("result", ""),
        "status": tfd.get("status", "unknown"),
    }
```

**Per-tool file-path extractor** for `/sessions/{uuid}/file-activity`:

```python
def extract_file_path(tool_name: str, args_json: str) -> str | None:
    try:
        args = json.loads(args_json)
    except json.JSONDecodeError:
        return None
    return (
        args.get("path")          # read_file_v2
        or args.get("file_path")  # edit_file
        or args.get("target_file")# older read_file
        or args.get("relative_workspace_path")
    )
```

### 6.4 SQLite open posture (mandatory)

```python
# api/cursor/state_db.py
def open_state_db_readonly(path: Path) -> sqlite3.Connection:
    if not path.exists():
        raise FileNotFoundError(path)
    uri = f"file:{path}?mode=ro&immutable=1"
    con = sqlite3.connect(uri, uri=True, isolation_level=None)
    con.row_factory = sqlite3.Row
    return con
```

`immutable=1` skips WAL frames → no lock contention with running Cursor app, ≤60s staleness ceiling (acceptable).

### 6.5 Subagent edge (`subComposerIds` ∪ `subagentComposerIds`)

When indexing a composer, after upserting its row, also enqueue every ID in `subComposerIds` and `subagentComposerIds` for indexing as a child composer. Set `parent_composer_id` on the child's `cursor_session_meta` row. `GET /sessions/{uuid}/subagents` returns `SELECT * FROM cursor_session_meta WHERE parent_composer_id = ?`.

In v1 with Cursor 2.5.26: subagent count is mostly zero (only best-of-N pairs exist). Code is ready; data will flow if/when Cursor 2.4+ Subagents see use.

---

## 7. Cross-Platform Path Detection

```python
# api/cursor/paths.py
import platform
from pathlib import Path

def cursor_global_db_path() -> Path:
    home = Path.home()
    os_name = platform.system()
    if os_name == "Darwin":
        return home / "Library/Application Support/Cursor/User/globalStorage/state.vscdb"
    elif os_name == "Linux":
        return home / ".config/Cursor/User/globalStorage/state.vscdb"
    elif os_name == "Windows":
        appdata = Path(os.environ["APPDATA"])
        return appdata / "Cursor/User/globalStorage/state.vscdb"
    raise NotImplementedError(f"Unsupported OS: {os_name}")

def cursor_workspace_storage_dir() -> Path:
    return cursor_global_db_path().parent.parent / "workspaceStorage"

def cursor_user_dir() -> Path:
    return Path.home() / ".cursor"   # same on all three OSes

def detect_cursor_install() -> bool:
    try:
        return cursor_global_db_path().exists()
    except (KeyError, NotImplementedError):
        return False
```

**Windows special:** never round-trip `~/.cursor/projects/<encoded>/` back to a path. Always trust `workspace.json.folder` URI. The encoded form silently drops drive-letter colons and backslashes — lossy.

---

## 8. Phased Build Sequence (≈2.5 weeks)

### Phase 1 — Skeleton & schema (Day 1-2)

**Deliverables:**
- `api/cursor/__init__.py`, `paths.py`, `state_db.py`
- `api/db/schema.py` v12 migration (all CREATE TABLEs from §3)
- Migration tests (`tests/api/test_db_migration.py`): assert v11 → v12 idempotent
- Detection unit test: `test_detect_cursor_install` covers found / not-found

**Acceptance:** `pytest tests/api/test_db_migration.py` green; `from api.cursor.paths import detect_cursor_install` works.

### Phase 2 — Parsers (Day 3-5)

**Deliverables:**
- `api/cursor/workspace.py` — scan workspaceStorage, return `(hash, folder_uri)[]`
- `api/cursor/composer.py` — read `composerData:<id>`, return typed dict
- `api/cursor/bubble.py` — read `bubbleId:<comp>:<bid>`, parse fields
- `api/cursor/tools.py` — TOOL_INT_NAME_REGISTRY + extractor (§6.3)
- Test fixtures: copy ~50 KB slice of real state.vscdb into `tests/fixtures/cursor/state_sample.db` (one composer with 17 bubbles, manually anonymized if needed)

**Acceptance:** Given the fixture DB, parsers reproduce the POC validation output (17 bubbles in order, 9 tool calls extracted with correct names).

### Phase 3 — Indexer (Day 6-8)

**Deliverables:**
- `api/cursor/indexer.py` — full + incremental scan logic
- `api/services/cursor_indexer_service.py` — lifecycle (startup + 60s tick)
- Wire into `main.py` startup event
- Indexer test: run full scan against fixture DB, assert N sessions / N bubbles / N tool calls in metadata.db

**Acceptance:** Run API locally, verify `SELECT COUNT(*) FROM sessions WHERE session_source='cursor'` matches real composer count after first scan (~10s).

### Phase 4 — Router dispatch (Day 9-11)

**Deliverables:**
- Update `routers/projects.py` — union source-aware
- Update `routers/sessions.py` — dispatch on `session_source` for `/sessions/{uuid}`, `/timeline`, `/tools`, `/file-activity`
- Update `routers/analytics.py` — Cursor rollups
- API integration tests: `tests/api/test_cursor_endpoints.py` — fixture DB + assert each endpoint shape matches existing schemas

**Acceptance:** All 6 core endpoints (§5.1-5.5 + analytics) return Cursor data in identical shape to Claude Code responses.

### Phase 5 — Plans, MCP, Agents (Day 12-14)

**Deliverables:**
- `api/cursor/plans.py` — YAML+md parser → `cursor_plan` rows
- `api/cursor/mcp.py` — workspace-scoped MCP scan → `cursor_mcp_server` + `cursor_mcp_tool`
- `api/cursor/agents.py` — hardcoded built-in inventory
- Router updates: `plans.py`, `tools.py`, `agents.py`
- Add `arguments_schema` field to `McpToolDetail` (backwards compatible: optional)

**Acceptance:** `/plans`, `/tools`, `/agents` return merged Claude Code + Cursor results.

### Phase 6 — Polish (Day 15-17)

**Deliverables:**
- Backfill migration: set `session_source='claude_code'` for existing NULL rows
- Logging + metrics: indexer duration, scan size, error rate (use existing logger)
- Error handling pass: Cursor DB locked / corrupt / partially-deleted edge cases
- Documentation: update CLAUDE.md to mention Cursor support; new section in api/CLAUDE.md
- Manual QA: launch API, verify both Claude Code and Cursor data appear in `/projects`

**Acceptance:** Full QA run on the inspected machine: all 10 endpoints work; no regressions in Claude Code paths.

---

## 9. Testing Strategy

### 9.1 Unit tests (per parser file)

- `test_paths.py`: OS detection branches
- `test_workspace.py`: empty workspace.json, malformed folder URI, missing file
- `test_composer.py`: missing keys, null `name`, untitled composers
- `test_bubble.py`: missing toolFormerData, empty thinking, ISO-8601 createdAt parsing
- `test_tools.py`: unknown tool int, missing name, malformed rawArgs JSON

### 9.2 Integration tests

- **`test_indexer.py`**: full scan against `tests/fixtures/cursor/state_sample.db` (1 workspace, 3 composers, ~50 bubbles, ~20 tool calls). Assert sqlite row counts after run.
- **`test_incremental.py`**: stamp `cursor_session_meta.indexed_at` on a fixture; verify incremental scan skips it; mutate one composer's `lastUpdatedAt`; verify it's re-indexed.
- **`test_cursor_endpoints.py`**: each of the 10 endpoints with a populated metadata.db. Assert response schema matches existing Pydantic models.

### 9.3 Performance test

- **`test_indexer_perf.py`**: measure full-scan duration against a 1300-composer fixture. Assert < 30s on CI. (POC measured ~10s locally.)

### 9.4 Manual QA checklist (Phase 6)

- [ ] Fresh DB → API starts → `/projects` shows Claude Code + Cursor projects
- [ ] `/sessions/{cursor_uuid}` returns SessionDetail
- [ ] `/sessions/{cursor_uuid}/timeline` returns events in chronological order
- [ ] `/sessions/{cursor_uuid}/tools` shows tool-call breakdown with human-readable names
- [ ] `/sessions/{cursor_uuid}/file-activity` shows file paths for read/edit ops
- [ ] `/analytics/projects/{ws_hash}` returns token usage, mode breakdown
- [ ] `/plans` lists 124 Cursor plans + N Claude Code plans
- [ ] `/tools` lists MCP servers from Cursor's per-project descriptors
- [ ] `/agents` shows Cursor built-in modes (agent/chat/plan/debug/edit)
- [ ] Stop and restart Cursor: incremental scan picks up new composers within 60s
- [ ] Uninstall Cursor → restart API → no errors, Cursor endpoints quietly return empty

---

## 10. Risks & Mitigations

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| Cursor 3.x ships and breaks `cursorDiskKV` schema | Med | High | Lenient parsing (defaults for missing keys); version-detect via a `_v` field on composerData (already exists). Pin a feature flag for known-bad versions. |
| State.vscdb grows beyond 5 GB; full-scan too slow | Low | Med | Incremental-only after first scan. Cap full scans to every 24h. Skip composers older than 1 year. |
| Cursor adds encryption (the `blobEncryptionKey` field becomes real) | Low | High | We index `bubbleId` records (plaintext today), not `agentKv:blob:*`. If `bubbleId` ever encrypts, we degrade to empty bubble text but session list still works. |
| Tool int registry drifts (new tool ints in 2.6+) | High | Low | Fallback to `f"tool_{int}"` for unknowns; log distinct unknowns for triage. |
| `~/.cursor/projects/<encoded>/` paths collide on Windows | Med | Med | Already mitigated: we don't use the encoded form. workspace.json folder URI is the canonical lookup. |
| Indexer blocks API startup if Cursor DB is huge | Med | Med | Run startup scan in a background task; routes return empty Cursor results until first scan completes. Log "indexing in progress" state. |
| User has 100+ workspaces (slow workspaceStorage scan) | Low | Low | Sort by mtime desc, process recent first; bound list to most-recent N if scan exceeds 5s. |
| Concurrent Cursor write triggers WAL lock with non-immutable read | Low | Med | `immutable=1` is our default — no lock risk. |
| Migration v12 conflicts with someone else's pending v12 | Low | Med | Coordinate via PR review; if collision, bump to v13. (#67 just landed v11, so we're clear.) |

---

## 11. Out-of-Scope (Deferred to v2+)

- `/live-sessions/*` — Cursor lacks hook substrate. Would require filesystem polling; defer.
- `/skills/*` listing — feasible (frontmatter parse works) but no invocation history; defer for cohesion.
- `/history/*` — VS Code Local History parser; defer.
- `/hooks/*` — Cursor has no hook API; permanent no.
- Cursor's `agentKv:blob:*` raw LLM records — redundant with `bubbleId`; skip.
- Subagents UI for Cursor 2.4+ — code is ready; defer surfacing until real data flows.
- Linked / cross-IDE session chains (a Cursor session continuing a Claude Code session) — interesting product idea; defer.
- Cost calculation for Cursor — requires per-model pricing for Cursor's Composer + Claude-via-Cursor. Defer.
- AI-vs-human commit attribution from `ai-tracking/ai-code-tracking.db` `scored_commits` — high-value standalone surface, but separate feature.

---

## 12. Open Decisions (need answers before Phase 4)

1. **Path normalization for `/projects` keys.** Claude Code uses `encoded_name` (URL-safe path-encoded). For Cursor we'd use `cursor_workspace_hash`. **Decision needed:** does the existing `encoded_name` URL parameter in routers tolerate non-encoded values, or do we need a new URL parameter (e.g., `?workspace_hash=...`)? Recommend: add a discriminator suffix, e.g., `cursor:<hash>` vs `claude:-Users-...-repo` so the URL itself is parseable.

2. **Backfill `session_source='claude_code'` for existing rows.** Should the v12 migration backfill NULL → 'claude_code' for existing Claude Code sessions? Cosmetic — but cleaner JOINs. Recommend yes.

3. **Indexer cadence.** 60s tick chosen by analogy to sync v3's reconciliation timer. Alternatives: 30s (more freshness), 5min (less CPU). **Recommend:** 60s default, env var `KARMA_CURSOR_INDEX_INTERVAL_S` for override.

4. **Cursor 2.5.26 model name normalization.** `composerData.modelConfig.modelName` returns strings like `claude-4.5-opus-high-thinking`, `claude-opus-4-7-thinking-xhigh`, `gpt-5.3-codex`, `default`. These don't match claude-karma's canonical model names. **Decision needed:** ingest as-is, or normalize to a canonical taxonomy? Recommend: ingest as-is for v1; build a translation map in v2 once analytics consumers complain.

---

## 12.5 Unpause options (added 2026-05-13)

`agent-coord-integration` carries v11 + sync_rooms() indexer + /rooms dashboard (PRs #67, #68, #69). These haven't merged to main yet. Three ways forward:

1. **Wait (cleanest).** Let `agent-coord-integration` merge to main naturally. Resume this work when `origin/main` shows `SCHEMA_VERSION = 11`. Zero rebase risk; v12 migration block lands cleanly after v11.
2. **Rebase to `agent-coord-integration`.** Branch off `agent-coord-integration` instead of main. Lets implementation start immediately but creates an indirect dependency — our PR is conceptually downstream of three other PRs and shouldn't merge to main until they do.
3. **Number our migration v13.** Skip v11 in our own block. Lets us land regardless of merge order — but wastes one version number and makes the schema history non-contiguous if v11 stalls. Not recommended unless v11 is at risk of being abandoned.

## 13. Estimated Timeline (≈2.5 weeks, 1 engineer)

| Phase | Days | Cumulative |
|---|---|---|
| 1. Skeleton & schema | 2 | 2 |
| 2. Parsers | 3 | 5 |
| 3. Indexer | 3 | 8 |
| 4. Router dispatch (core 6) | 3 | 11 |
| 5. Plans/MCP/Agents | 3 | 14 |
| 6. Polish & QA | 3 | 17 |

Add ~3 days buffer for unknowns → **≈3 weeks** real-world.

---

## 14. Definition of Done (v1)

- [ ] All 10 endpoints return Cursor data when Cursor is installed
- [ ] Auto-detection works: no errors when Cursor is absent
- [ ] Indexer runs on startup + every 60s without manual intervention
- [ ] `metadata.db` migration v12 applies cleanly and is idempotent
- [ ] All existing Claude Code tests still pass
- [ ] New unit + integration tests cover the new modules (>80% coverage on `api/cursor/`)
- [ ] Manual QA checklist (§9.4) passes on at least one developer machine
- [ ] CLAUDE.md updated; no breaking changes to existing public APIs

---

## Appendix A — Sample SQL queries (operations team)

```sql
-- How many Cursor sessions are indexed?
SELECT COUNT(*) FROM sessions WHERE session_source = 'cursor';

-- Bubbles per session distribution
SELECT session_uuid, COUNT(*) AS bubble_count
FROM cursor_bubble GROUP BY session_uuid
ORDER BY bubble_count DESC LIMIT 20;

-- Top 10 tools used in Cursor sessions
SELECT tool_name, COUNT(*) AS calls
FROM session_tools WHERE invocation_source = 'cursor'
GROUP BY tool_name ORDER BY calls DESC LIMIT 10;

-- Sessions never picked up by incremental scan (debug)
SELECT s.uuid, s.ts_ms, csm.indexed_at
FROM sessions s LEFT JOIN cursor_session_meta csm ON s.uuid = csm.session_uuid
WHERE s.session_source = 'cursor' AND csm.indexed_at IS NULL;

-- Latest 5 active Cursor composers
SELECT uuid, project, ts_ms FROM sessions
WHERE session_source = 'cursor' ORDER BY ts_ms DESC LIMIT 5;
```

## Appendix B — Tool int → name registry (initial)

Built from POC scan of 31,829 tool calls across 1,334 composers on Cursor 2.5.26. Update via a separate migration when new ints appear.

| `tool` int | Canonical `name` | Notes |
|---:|---|---|
| 3 | codebase_search | semantic search |
| 5 | read_file | older shape (use `name` field on bubble) |
| 7 | edit_file | older edit (use `name` field) |
| 9 | grep_search | older grep |
| 15 | run_terminal_command_v2 | |
| 19 | (MCP call) | use `name` from rawArgs |
| 30 | read_multiple_files | |
| 35 | todo_write | |
| 38 | edit_file | newer edit shape |
| 39 | list_dir | |
| 40 | read_file_v2 | most common (6465 calls in sample) |
| 41 | grep_search | newer grep |
| 42 | glob_file_search | |
| 43 | plan_tool | plan create/update |

Unknown ints: fall back to `tool_<int>` string and log for triage.
