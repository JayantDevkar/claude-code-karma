# OpenCode Integration Design

**Date:** 2026-03-03
**Revised:** 2026-03-03 (v2 — incorporates real schema research + feature parity review)
**Status:** Approved
**Goal:** Add OpenCode session support to claude-karma with maximum feature parity, unified views, and source badges.

## Context

OpenCode ([sst/opencode](https://github.com/sst/opencode)) is a popular open-source AI coding agent. It stores session data in a SQLite database (`opencode.db`) via Drizzle ORM, unlike Claude Code's JSONL file-per-session approach. This design adds OpenCode as a second data source in claude-karma.

## Approach: Abstraction Layer (SessionSource Protocol)

A common `SessionSource` protocol that both Claude Code (JSONL) and OpenCode (SQLite) parsers conform to. All models gain a `source` discriminator field. Routers merge results from both sources.

---

## OpenCode Storage Locations

| Purpose | Path |
|---------|------|
| SQLite DB | `~/.local/share/opencode/opencode.db` (or `$XDG_DATA_HOME/opencode/opencode.db`) |
| WAL/SHM | `opencode.db-wal`, `opencode.db-shm` (same dir) |
| Global config | `~/.config/opencode/opencode.json` |
| Project config | `<project>/opencode.json` + `<project>/.opencode/` |
| Auth | `~/.local/share/opencode/auth.json` |
| Logs | `~/.local/share/opencode/log/` |
| Snapshots | `~/.local/share/opencode/snapshot/` |
| Cache | `~/.cache/opencode/` |

---

## OpenCode SQLite Schema (8 tables)

> **Source of truth:** [sst/opencode session.sql.ts](https://github.com/sst/opencode/blob/dev/packages/opencode/src/session/session.sql.ts), [project.sql.ts](https://github.com/sst/opencode/blob/dev/packages/opencode/src/project/project.sql.ts), verified against real DB on disk.

### ProjectTable (`project`)

| Column | Type | Notes |
|--------|------|-------|
| `id` | TEXT PK | Derived from repo root commit hash |
| `worktree` | TEXT NOT NULL | Absolute path to repo root |
| `vcs` | TEXT | `"git"` or null |
| `name` | TEXT | Optional display name |
| `icon_url` | TEXT | Optional icon URL |
| `icon_color` | TEXT | Optional icon color |
| `time_created` | INTEGER | Unix timestamp ms |
| `time_updated` | INTEGER | Unix timestamp ms |
| `time_initialized` | INTEGER | When first initialized |
| `sandboxes` | TEXT (JSON) | `string[]` — sandbox IDs |
| `commands` | TEXT (JSON) | `{ start?: string }` |

### SessionTable (`session`)

| Column | Type | Notes |
|--------|------|-------|
| `id` | TEXT PK | Prefixed ID e.g. `ses_34cd8be60ffe...` |
| `project_id` | TEXT FK → project | CASCADE delete |
| `parent_id` | TEXT | FK to parent session (subagent relationship) |
| `slug` | TEXT NOT NULL | Human-readable slug e.g. `mighty-wolf` |
| `directory` | TEXT NOT NULL | Working directory |
| `title` | TEXT NOT NULL | Session title |
| `version` | TEXT NOT NULL | OpenCode version e.g. `1.2.15` |
| `share_url` | TEXT | Public share URL |
| `summary_additions` | INTEGER | Git diff stats post-compaction |
| `summary_deletions` | INTEGER | Git diff stats post-compaction |
| `summary_files` | INTEGER | Files changed count |
| `summary_diffs` | TEXT (JSON) | `FileDiff[]` array |
| `revert` | TEXT (JSON) | `{ messageID, partID?, snapshot?, diff? }` |
| `permission` | TEXT (JSON) | Permission ruleset |
| `time_created` | INTEGER | Unix timestamp ms |
| `time_updated` | INTEGER | Unix timestamp ms |
| `time_compacting` | INTEGER | Set while compaction in progress |
| `time_archived` | INTEGER | Set when session archived |

**Indexes:** `project_id`, `parent_id`

### MessageTable (`message`)

| Column | Type | Notes |
|--------|------|-------|
| `id` | TEXT PK | Prefixed ID e.g. `msg_cb32741b5001...` |
| `session_id` | TEXT FK → session | CASCADE delete |
| `time_created` | INTEGER | Unix timestamp ms |
| `time_updated` | INTEGER | Unix timestamp ms |
| `data` | TEXT (JSON) NOT NULL | **Full message payload** — discriminated union on `role` |

**Index:** `session_id`

**IMPORTANT:** Message metadata (role, tokens, cost, model, agent) is NOT in flat columns. It's inside the `data` JSON blob. All queries must use `json_extract(data, '$.field')`.

#### `data` JSON for `role: "user"`:
```json
{
  "role": "user",
  "time": { "created": 1772532220331 },
  "summary": {
    "diffs": [{ "file": "AGENTS.md", "before": "", "after": "...", "additions": 234, "deletions": 0, "status": "added" }]
  },
  "agent": "build",
  "model": { "providerID": "opencode", "modelID": "big-pickle" },
  "format": "...",
  "system": "...",
  "tools": { "read": true, "write": true },
  "variant": "..."
}
```

#### `data` JSON for `role: "assistant"`:
```json
{
  "role": "assistant",
  "time": { "created": 1772532220341, "completed": 1772532226237 },
  "parentID": "msg_cb32741a2001...",
  "modelID": "big-pickle",
  "providerID": "opencode",
  "mode": "build",
  "agent": "build",
  "path": { "cwd": "/Users/.../claude-karma", "root": "/Users/.../claude-karma" },
  "cost": 0.0,
  "tokens": {
    "total": 14045,
    "input": 78,
    "output": 140,
    "reasoning": 0,
    "cache": { "read": 510, "write": 13317 }
  },
  "finish": "tool-calls",
  "error": null,
  "summary": false,
  "variant": "..."
}
```

**Token fields:** `input`, `output`, `reasoning`, `cache.read`, `cache.write` — richer than Claude Code. `cost` is pre-computed USD float.

### PartTable (`part`)

| Column | Type | Notes |
|--------|------|-------|
| `id` | TEXT PK | Prefixed ID e.g. `prt_cb32753b1001...` |
| `message_id` | TEXT FK → message | CASCADE delete |
| `session_id` | TEXT NOT NULL | Denormalized for fast session queries |
| `time_created` | INTEGER | Unix timestamp ms |
| `time_updated` | INTEGER | Unix timestamp ms |
| `data` | TEXT (JSON) NOT NULL | **Full part payload** — discriminated union on `type` |

**Indexes:** `message_id`, `session_id`

#### 11 Part Types (discriminated on `data.type`)

| Type | Purpose | Key Fields in `data` |
|------|---------|---------------------|
| `text` | Text content | `text`, `synthetic?`, `ignored?`, `time?` |
| `reasoning` | Extended thinking | `text`, `metadata.anthropic.signature`, `time: {start, end}` |
| `tool` | Tool invocation + result | `tool` (name), `callID`, `state: { status, input, output, title, metadata, time }` |
| `step-start` | Beginning of AI step | `snapshot?` (filesystem snapshot ref) |
| `step-finish` | End of AI step | `reason`, `snapshot?`, `cost`, `tokens: {input, output, reasoning, cache}` |
| `file` | User-attached file content | `mime`, `filename?`, `url`, `source?: { type, path, ... }` |
| `snapshot` | Filesystem state snapshot | `snapshot` (hash reference) |
| `patch` | Git patch applied | `hash`, `files: ["/path/to/file"]` |
| `subtask` | Spawned subagent | `prompt`, `description`, `agent`, `model?`, `command?` |
| `compaction` | Context compaction event | `auto` (bool), `overflow?` (bool) |
| `agent` | Agent switch marker | `name`, `source?` |
| `retry` | API retry event | `attempt`, `error: { message, statusCode, ... }`, `time` |

#### Tool Part `state` Variants (discriminated on `status`):

| Status | Fields |
|--------|--------|
| `pending` | `input`, `raw` |
| `running` | `input`, `title?`, `metadata?`, `time: { start }` |
| `completed` | `input`, `output`, `title`, `metadata`, `time: { start, end, compacted? }`, `attachments?` |
| `error` | `input`, `error`, `metadata?`, `time: { start, end }` |

**Real completed tool example:**
```json
{
  "type": "tool",
  "callID": "call_function_3d6sbtueh7e1_1",
  "tool": "glob",
  "state": {
    "status": "completed",
    "input": { "pattern": "AGENTS.md" },
    "output": "No files found",
    "title": "",
    "metadata": { "count": 0, "truncated": false },
    "time": { "start": 1772532224953, "end": 1772532224980 }
  }
}
```

### TodoTable (`todo`)

| Column | Type | Notes |
|--------|------|-------|
| `session_id` | TEXT FK → session | CASCADE delete, part of composite PK |
| `content` | TEXT NOT NULL | Todo item text |
| `status` | TEXT NOT NULL | e.g. `pending`, `completed` |
| `priority` | TEXT NOT NULL | e.g. `high`, `medium`, `low` |
| `position` | INTEGER NOT NULL | Part of composite PK |
| `time_created` | INTEGER | Unix timestamp ms |
| `time_updated` | INTEGER | Unix timestamp ms |

### PermissionTable (`permission`)

| Column | Type | Notes |
|--------|------|-------|
| `project_id` | TEXT PK, FK → project | CASCADE delete |
| `time_created` | INTEGER | |
| `time_updated` | INTEGER | |
| `data` | TEXT (JSON) | Permission ruleset |

### SessionShareTable (`session_share`)

| Column | Type | Notes |
|--------|------|-------|
| `session_id` | TEXT PK, FK → session | CASCADE delete |
| `id` | TEXT NOT NULL | Share ID |
| `secret` | TEXT NOT NULL | Share secret |
| `url` | TEXT NOT NULL | Public URL |
| `time_created` | INTEGER | |
| `time_updated` | INTEGER | |

### ControlAccountTable (`control_account`)

| Column | Type | Notes |
|--------|------|-------|
| `email` | TEXT | Composite PK with `url` |
| `url` | TEXT | Account URL |
| `access_token` | TEXT | OAuth token |
| `refresh_token` | TEXT | OAuth refresh |
| `token_expiry` | INTEGER | |
| `active` | INTEGER | Boolean |

**Not relevant for session tracking — skip.**

---

## Feature Parity Matrix

Every claude-karma endpoint classified for OpenCode support.

### Full Parity (build for OpenCode)

| # | Feature | Claude-Karma Endpoint | OpenCode Data Source | Notes |
|---|---------|----------------------|---------------------|-------|
| 1 | Project listing | `GET /projects` | `ProjectTable` | Path-encode `worktree` field |
| 2 | Project detail | `GET /projects/{name}` | `ProjectTable` + `SessionTable` | |
| 3 | Session listing | `GET /sessions` | `SessionTable` | |
| 4 | Session detail | `GET /sessions/{uuid}` | `SessionTable` + `MessageTable` + `PartTable` | |
| 5 | Messages/conversation | via session detail | `MessageTable.data` (JSON) + `PartTable.data` (JSON) | |
| 6 | Token/cost tracking | via session detail | `MessageTable.data.tokens` + `data.cost` | Richer than CC: has cache.read/write |
| 7 | Tool usage overview | `GET /tools`, `GET /sessions/{uuid}/tools` | `PartTable` WHERE `data.type = 'tool'` | Tool name in `data.tool`, timing in `data.state.time` |
| 8 | Subagent tracking | `GET /sessions/{uuid}/subagents`, `GET /agents` | `SessionTable.parent_id` (session tree) | Child sessions via `parent_id` FK |
| 9 | Todo items | via session detail | `TodoTable` | Direct map: content, status, priority |
| 10 | Thinking blocks | via messages | `PartTable` WHERE `data.type = 'reasoning'` | Text + timing |
| 11 | Compaction detection | session flags | `PartTable` WHERE `data.type = 'compaction'` + `SessionTable.time_compacting` | |
| 12 | Analytics | `GET /analytics/projects/{name}` | Aggregate from all tables | sessions_by_date, cost, tokens, tools_used, models_used |
| 13 | Session archive | session flags | `SessionTable.time_archived` | |

### Partial Parity (build with limitations)

| # | Feature | Limitation | OpenCode Source |
|---|---------|-----------|-----------------|
| 14 | File activity | No explicit file operation tracking. Must infer from tool parts: `data.tool` in (`read`, `write`, `glob`, `grep`) + parse `data.state.input` for paths | `PartTable` type=tool |
| 15 | Timeline events | Can reconstruct from parts: text→response, tool→tool_call, reasoning→thinking, subtask→subagent_spawn, step-start/finish→step boundaries. **No** todo_update, command_invocation, skill_invocation events | `PartTable` ordered by `time_created` |
| 16 | Skills tracking | OpenCode has no concept of "skills". `subtask` parts may have a `command` field for slash commands. Map to `commands_used` only | `PartTable` type=subtask with `data.command` |
| 17 | Commands tracking | Only slash commands that spawn subtasks are trackable via `subtask.command`. No equivalent of Claude Code's text-detected commands | `PartTable` type=subtask |
| 18 | Session chains | OpenCode uses `parent_id` for subagent sessions, not continuation chains. No `leaf_uuid` / slug-based chain detection. Each session is standalone | `SessionTable.parent_id` |
| 19 | Models used | Extractable from `MessageTable.data.modelID` + `data.providerID`. Model IDs differ from Anthropic IDs (e.g. `big-pickle` via `opencode` provider) | `MessageTable.data` JSON |
| 20 | Git activity | `patch` parts track applied git patches (hash + files changed). Less granular than CC file-level tracking | `PartTable` type=patch |

### Claude Code Only (N/A for OpenCode)

| # | Feature | Reason |
|---|---------|--------|
| 21 | Live sessions | Hook-driven (`~/.claude_karma/live-sessions/`). OpenCode has no hooks system |
| 22 | Hooks browser | OpenCode has no hook system |
| 23 | Plugins browser | OpenCode MCP servers configured differently (in `opencode.json`). Different discovery mechanism |
| 24 | File history snapshots | CC stores `FileHistorySnapshot` messages. OC has `snapshot` parts but they're filesystem hashes, not file content |
| 25 | Tool results (stored) | CC stores tool output in `tool-results/*.txt`. OC stores output inline in tool part `data.state.output` |
| 26 | Session index JSON | CC uses `sessions-index.json` for fast listing. OC already has SQLite (fast by default) |
| 27 | Desktop session linking | CC has Claude Desktop metadata in `~/Library/Application Support/Claude/`. Not applicable to OC |
| 28 | Session source (CLI/Desktop) | Existing `session_source` field distinguishes CLI vs Desktop. OC sessions are always CLI-equivalent |
| 29 | Plan approval hooks | CC-specific hook |
| 30 | Docs browser | CC-specific |

### OpenCode Only (new features)

| # | Feature | Source | Notes |
|---|---------|--------|-------|
| 31 | Step-level cost/tokens | `PartTable` type=step-finish | Per-step granularity not available in CC. Show as timeline enhancement |
| 32 | Session sharing | `SessionShareTable` | Public share URLs with secrets |
| 33 | Git patch tracking | `PartTable` type=patch | Git commit hashes + files per patch |
| 34 | Agent switch markers | `PartTable` type=agent | Tracks which agent is active at any point |
| 35 | API retry events | `PartTable` type=retry | Track API failures/retries |
| 36 | Permission rules | `PermissionTable` | Per-project tool permission config |

---

## Data Model Mapping (Field-Level)

### Project

| OpenCode Field | Claude-Karma Field | Transform |
|----------------|-------------------|-----------|
| `project.id` | `encoded_name` | Path-encode `worktree` field (same dash-encoding: `/Users/me/repo` → `-Users-me-repo`) |
| `project.worktree` | `real_path` | Direct (absolute path) |
| `project.name` | `display_name` | Direct, fallback to basename of `worktree` |
| `project.vcs` | (new) | Expose or ignore |
| `project.time_created` | `created_at` | ms → ISO datetime |
| `project.time_updated` | `updated_at` | ms → ISO datetime |
| — | `source` | `"opencode"` |

### Session

| OpenCode Field | Claude-Karma Field | Transform |
|----------------|-------------------|-----------|
| `session.id` | `uuid` | Direct (string, not actual UUID but unique) |
| `session.slug` | `slug` | Direct |
| `session.title` | `title` | Direct |
| `session.directory` | `cwd` | Direct |
| `session.project_id` | `project_encoded_name` | Look up project, path-encode |
| `session.parent_id` | `parent_session_id` | Direct — maps to subagent relationship |
| `session.version` | `opencode_version` | New field (CC has no equivalent) |
| `session.time_created` | `created_at` | ms → ISO datetime |
| `session.time_updated` | `updated_at` | ms → ISO datetime |
| `session.time_archived` | `is_archived` | Non-null = archived |
| `session.time_compacting` | `is_compacting` | Non-null = compaction in progress |
| `session.summary_additions` | `summary.additions` | Direct |
| `session.summary_deletions` | `summary.deletions` | Direct |
| `session.summary_files` | `summary.files_changed` | Direct |
| Aggregate from messages | `total_cost` | Sum `data.cost` from assistant messages |
| Aggregate from messages | `total_tokens` | Sum `data.tokens` from assistant messages |
| Aggregate from messages | `models_used` | Unique `data.modelID` values |
| Count from parts | `tool_use_count` | Count parts WHERE `data.type = 'tool'` |
| — | `source` | `"opencode"` |
| — | `session_source` | `null` (not CLI/Desktop distinction) |

### Token Usage

| OpenCode Field | Claude-Karma Field | Notes |
|----------------|-------------------|-------|
| `data.tokens.input` | `input_tokens` | Direct |
| `data.tokens.output` | `output_tokens` | Direct |
| `data.tokens.reasoning` | `reasoning_tokens` | New field (CC doesn't expose separately) |
| `data.tokens.cache.read` | `cache_read_input_tokens` | Direct map to CC equivalent |
| `data.tokens.cache.write` | `cache_creation_input_tokens` | Direct map to CC equivalent |
| `data.tokens.total` | `total_tokens` | Computed or direct |
| `data.cost` | `cost` | Pre-computed USD. Do NOT re-compute from pricing table |

### Tool Usage

| OpenCode Field | Claude-Karma Field | Notes |
|----------------|-------------------|-------|
| `data.tool` | `tool_name` | Direct — e.g. `"glob"`, `"read"`, `"bash"` |
| `data.callID` | `tool_use_id` | Direct |
| `data.state.input` | `input` | JSON object with tool parameters |
| `data.state.output` | `output` | String result (for completed tools) |
| `data.state.status` | `status` | `pending`, `running`, `completed`, `error` |
| `data.state.time.start` | `started_at` | ms → ISO datetime |
| `data.state.time.end` | `ended_at` | ms → ISO datetime (completed/error only) |
| `end - start` | `duration_ms` | Computed |
| `data.state.metadata` | `metadata` | Tool-specific metadata (e.g. `{ count, truncated }` for glob) |
| — | `category` | Infer: all OC tools are "builtin" (no MCP plugin distinction yet) |

**Tools observed in real data:** `bash`, `glob`, `grep`, `question`, `read`, `task`, `todowrite`, `write`

### File Activity (inferred from tool parts)

| Tool Name | Operation | Path Source |
|-----------|-----------|-------------|
| `read` | `read` | `data.state.input.file_path` or similar |
| `write` | `write` | `data.state.input.file_path` |
| `glob` | `search` | `data.state.input.pattern` |
| `grep` | `search` | `data.state.input.pattern` |
| `bash` | Varies | Cannot reliably extract file paths |
| `patch` parts | `edit` | `data.files[]` array |

### Subagent/Agent Tracking

OpenCode uses **`parent_id` on SessionTable** for subagent hierarchy (not separate files):

| OpenCode | Claude-Karma | Notes |
|----------|-------------|-------|
| Session with `parent_id` | Agent/Subagent | Child session = subagent |
| `parent_id` value | `parent_session_uuid` | FK to parent session |
| Child session's messages | Agent's messages | Full conversation available |
| `subtask` part in parent | Agent spawn event | Contains `prompt`, `description`, `agent`, `model` |
| Message `data.agent` | `agent_name` | Which agent handled this message |

**Real example:** Session `swift-circuit` spawned `lucky-comet` (parent_id = swift-circuit's ID)

### Todo Items

| OpenCode Field | Claude-Karma Field | Notes |
|----------------|-------------------|-------|
| `todo.content` | `content` / `description` | Direct |
| `todo.status` | `status` | Direct (`pending`, `completed`, etc.) |
| `todo.priority` | `priority` | Direct (`high`, `medium`, `low`) |
| `todo.position` | `order` | Direct |
| `todo.session_id` | `session_uuid` | Direct |

---

## Naming Conflict: `source` vs `session_source`

The frontend already has `session_source?: 'desktop' | null` on SessionSummary (distinguishes CLI vs Claude Desktop sessions).

**Resolution:** Use a different field name for the data source:

| Field | Purpose | Values |
|-------|---------|--------|
| `session_source` (existing) | CLI vs Desktop origin | `'desktop'` / `null` |
| `data_source` (new) | Which AI tool produced the session | `'claude_code'` / `'opencode'` |

All models, API responses, and frontend types use `data_source` (not `source`) to avoid confusion.

---

## SessionSource Protocol (Revised)

```python
from typing import Protocol, Iterator, Literal

DataSourceType = Literal["claude_code", "opencode"]

class SessionSource(Protocol):
    source_name: DataSourceType

    # Core
    def list_projects(self) -> list[Project]: ...
    def get_project(self, identifier: str) -> Project | None: ...
    def list_sessions(self, project: str) -> list[Session]: ...
    def get_session(self, session_id: str) -> Session | None: ...
    def iter_messages(self, session_id: str) -> Iterator[Message]: ...

    # Detail endpoints
    def get_tool_usage(self, session_id: str) -> list[ToolUsage]: ...
    def get_file_activity(self, session_id: str) -> list[FileActivity]: ...
    def get_subagents(self, session_id: str) -> list[Agent]: ...
    def get_timeline(self, session_id: str) -> list[TimelineEvent]: ...
    def get_todos(self, session_id: str) -> list[TodoItem]: ...

    # Analytics
    def get_analytics(self, project: str) -> ProjectAnalytics: ...
    def get_models_used(self, session_id: str) -> list[str]: ...
```

Both `ClaudeCodeSource` and `OpenCodeSource` implement this. Methods that return empty results for a source (e.g., `get_todos()` returns `[]` if the source doesn't have todos) are valid.

---

## Timeline Event Mapping (New)

OpenCode parts → claude-karma TimelineEvent types:

| Part Type | TimelineEvent Type | Fields |
|-----------|-------------------|--------|
| `text` (in user msg) | `prompt` | timestamp from message |
| `text` (in assistant msg) | `response` | timestamp, text preview |
| `tool` | `tool_call` | tool name, status, duration, input/output preview |
| `reasoning` | `thinking` | duration from `time.start`→`time.end` |
| `subtask` | `subagent_spawn` | agent name, prompt, description |
| `step-start` | `step_boundary` | snapshot ref (new event type) |
| `step-finish` | `step_boundary` | cost, tokens, finish reason (new event type) |
| `patch` | `git_patch` | hash, files changed (new event type) |
| `compaction` | `compaction` | auto vs manual (new event type) |
| `agent` | `agent_switch` | agent name (new event type) |
| `retry` | `api_retry` | attempt number, error (new event type) |

**New timeline event types** (`step_boundary`, `git_patch`, `compaction`, `agent_switch`, `api_retry`) are OpenCode-specific but could be useful for Claude Code too in the future.

---

## SQLite Metadata DB Integration

Claude-karma uses `~/.claude_karma/metadata.db` for fast queries (session index, tool/skill/command tracking).

**Strategy:** Index OpenCode sessions into the same metadata DB.

| Metadata Table | OpenCode Support | Notes |
|---------------|-----------------|-------|
| `sessions` | Yes | Index OC sessions with `data_source = 'opencode'` |
| `session_tools` | Yes | Extract from tool parts |
| `session_skills` | Partial | Only `subtask.command` slash commands |
| `session_commands` | Partial | Same as skills |
| `subagent_invocations` | Yes | From `parent_id` relationships |
| `subagent_tools` | Yes | Tools used in child sessions |

**Schema change needed:** Add `data_source TEXT DEFAULT 'claude_code'` column to `sessions` table.

**Indexing approach:** On API startup or manual refresh, scan `opencode.db` and upsert into metadata DB. Use `time_updated` for incremental sync.

---

## New Files & Module Structure

### API

```
api/
├── models/
│   ├── source.py              # NEW — DataSourceType, SessionSource protocol
│   ├── opencode/              # NEW — OpenCode-specific parsers
│   │   ├── __init__.py
│   │   ├── database.py        # SQLite reader for opencode.db (connection, WAL mode)
│   │   ├── session.py         # SessionTable + MessageTable → our Session model
│   │   ├── message.py         # MessageTable.data + PartTable.data → our Message models
│   │   ├── project.py         # ProjectTable → our Project model
│   │   ├── tools.py           # tool-type parts → ToolUsage model
│   │   ├── timeline.py        # All part types → TimelineEvent list
│   │   ├── file_activity.py   # Tool parts → FileActivity (inferred)
│   │   └── todos.py           # TodoTable → TodoItem model
│   ├── project.py             # MODIFIED — add data_source field
│   ├── session.py             # MODIFIED — add data_source field
│   └── message.py             # MODIFIED — add data_source field
├── routers/
│   ├── projects.py            # MODIFIED — merge results from both sources
│   ├── sessions.py            # MODIFIED — merge results from both sources
│   ├── analytics.py           # MODIFIED — aggregate across sources
│   ├── tools.py               # MODIFIED — merge tool usage from both sources
│   ├── agents.py              # MODIFIED — merge agent data from both sources
│   └── commands.py            # MODIFIED — merge command data
├── db/
│   └── connection.py          # MODIFIED — add data_source column migration
└── utils.py                   # MODIFIED — add opencode DB path discovery
```

### Frontend

```
frontend/src/
├── lib/
│   ├── api-types.ts           # MODIFIED — add data_source field to all interfaces
│   ├── api.ts                 # MODIFIED — add data_source filter params
│   └── components/
│       ├── DataSourceBadge.svelte  # NEW — "Claude Code" / "OpenCode" badge
│       └── DataSourceFilter.svelte # NEW — filter toggle component
├── routes/
│   ├── projects/              # MODIFIED — show data source badges
│   ├── sessions/              # MODIFIED — show data source badges + filter
│   ├── tools/                 # MODIFIED — show data source badges
│   ├── agents/                # MODIFIED — show data source badges
│   └── settings/              # MODIFIED — OpenCode DB path config
```

---

## Router Merge Pattern

```python
from models.source import SessionSource, DataSourceType

sources: list[SessionSource] = [claude_code_source, opencode_source]

@router.get("/projects")
async def list_projects(data_source: DataSourceType | None = None):
    all_projects = []
    for s in sources:
        if data_source and s.source_name != data_source:
            continue
        all_projects.extend(s.list_projects())
    # Deduplicate by real_path (same project may exist in both sources)
    return deduplicate_projects(all_projects, merge_strategy="combine")
```

### Project Deduplication

When the same project path exists in both Claude Code and OpenCode:
- **Combine** into a single project entry with sessions from both sources
- Each session retains its `data_source` field
- Analytics aggregate across both sources for the combined project

---

## Frontend Source Filter

- Every list endpoint gains `?data_source=claude_code|opencode|all` (default `all`)
- Persisted in URL state like existing filters
- `DataSourceBadge.svelte`:
  - Claude Code: blue badge with CC icon
  - OpenCode: green badge with OC icon
- `DataSourceFilter.svelte`: toggle in list headers (All / Claude Code / OpenCode)

---

## OpenCode DB Connection Strategy

```python
import sqlite3
from pathlib import Path
import os

def get_opencode_db_path() -> Path | None:
    """Discover opencode.db path. Returns None if not found."""
    xdg = os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share")
    db_path = Path(xdg) / "opencode" / "opencode.db"
    return db_path if db_path.exists() else None

def connect_opencode_db(db_path: Path) -> sqlite3.Connection:
    """Read-only connection with WAL mode support."""
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")  # Support concurrent reads
    return conn
```

- **Read-only** via `?mode=ro` URI parameter
- **WAL mode** for concurrent reads while OpenCode writes
- **Connection pooling** — single connection reused across requests, reconnect on error
- **Lazy init** — don't connect until first OpenCode endpoint is called

---

## Key Design Decisions

1. **Read OpenCode's DB directly** — `sqlite3` stdlib, no SDK dependency
2. **Read-only access** — `?mode=ro` URI, never write to opencode.db
3. **Lazy loading** — only connect when OpenCode sessions requested
4. **Graceful degradation** — if opencode.db missing, OpenCode features silently disabled
5. **Path discovery** — `$XDG_DATA_HOME/opencode/opencode.db` → `~/.local/share/opencode/opencode.db`
6. **Backward compatible** — existing models default to `data_source="claude_code"`
7. **JSON extraction** — Use `json_extract()` in SQLite queries for message/part data
8. **Field naming** — Use `data_source` (not `source`) to avoid conflict with existing `session_source`
9. **Project deduplication** — Same path in both sources = combined project entry
10. **Metadata DB indexing** — OpenCode sessions indexed into `~/.claude_karma/metadata.db` for fast queries

---

## Implementation Phases

### Phase 1: Core Infrastructure
- `api/models/source.py` — `DataSourceType`, `SessionSource` protocol
- `api/models/opencode/database.py` — SQLite connection manager
- `api/models/opencode/project.py` — Project parser
- `api/models/opencode/session.py` — Session parser
- Add `data_source` field to existing models (default `"claude_code"`)
- **Acceptance:** Can list OpenCode projects and sessions via API

### Phase 2: Message & Tool Parsing
- `api/models/opencode/message.py` — Message JSON blob parser
- `api/models/opencode/tools.py` — Tool part parser
- `api/models/opencode/todos.py` — Todo parser
- Router merge for `/projects`, `/sessions`, `/sessions/{id}`, `/sessions/{id}/tools`
- **Acceptance:** Full session detail with messages, tools, todos for OC sessions

### Phase 3: Timeline, File Activity, Analytics
- `api/models/opencode/timeline.py` — All part types → TimelineEvent
- `api/models/opencode/file_activity.py` — Inferred file activity from tool parts
- Analytics aggregation across sources
- Agent/subagent tracking via `parent_id`
- **Acceptance:** Timeline, file activity, analytics work for OC sessions

### Phase 4: Frontend
- `DataSourceBadge.svelte`, `DataSourceFilter.svelte`
- `data_source` field on all TypeScript interfaces
- Filter support on all list pages
- Settings page: OpenCode DB path configuration
- **Acceptance:** Full UI support with badges, filters, combined views

### Phase 5: Metadata DB & Optimization
- Add `data_source` column to metadata DB
- Incremental sync from opencode.db → metadata.db
- Project deduplication logic
- **Acceptance:** Fast queries via metadata DB for OC sessions

---

## References

- [sst/opencode GitHub](https://github.com/sst/opencode) (source of truth for schema)
- [session.sql.ts](https://github.com/sst/opencode/blob/dev/packages/opencode/src/session/session.sql.ts) — Drizzle ORM table definitions
- [message-v2.ts](https://github.com/sst/opencode/blob/dev/packages/opencode/src/session/message-v2.ts) — MessageV2 type definitions (11 part types)
- [project.sql.ts](https://github.com/sst/opencode/blob/dev/packages/opencode/src/project/project.sql.ts) — Project table
- [db.ts](https://github.com/sst/opencode/blob/dev/packages/opencode/src/storage/db.ts) — DB location and config
- [DeepWiki: Session Management](https://deepwiki.com/sst/opencode/3.1-session-management)
- Real DB verified at `~/.local/share/opencode/opencode.db` (724KB, 4 sessions, 286 parts)
