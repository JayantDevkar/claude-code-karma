# OpenCode Integration Design

**Date:** 2026-03-03
**Revised:** 2026-03-03 (v3 — addresses critic review gaps: complete router classification, verified data gaps from real DB, corrected part type mapping)
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
  "variant": "max"
}
```

**Token fields:** `input`, `output`, `reasoning`, `cache.read`, `cache.write` — richer than Claude Code. `cost` is pre-computed USD float.

**Mode & Agent Fields:** OpenCode has a multi-mode system analogous to oh-my-claudecode:
- `mode`: `"plan"`, `"build"`, or `"explore"` — orchestration mode
- `agent`: `"plan"`, `"build"`, or `"explore"` — agent handler (matches mode)
- `variant`: `"max"` or `null` — temperature/thinking variant (similar to thinking budget preference)

**Real data observed (from opencode.db):**
| mode | agent | modelID | variant | messages | notes |
|------|-------|---------|---------|----------|-------|
| plan | plan | claude-opus-4-5 | max | 25 | Strategic planning mode |
| build | build | big-pickle (OC) | max | 6 | Code building/execution |
| build | build | claude-opus-4-5 | (null) | 10 | Building with Opus, no variant |
| explore | explore | claude-opus-4-5 | (null) | 15 | Codebase exploration |
| (null) | (null) | (null) | (null) | 4 | Unstructured/raw mode (no mode selected) |

**Mode Semantics:**
- **plan**: Strategic thinking (like `plan` skill in OMC). Uses `variant: "max"` (extended thinking).
- **build**: Code execution & generation. Uses `variant: "max"` for complex tasks.
- **explore**: Codebase exploration & search. May skip variant (cost-optimized).
- **null**: Raw conversation without mode structure (early sessions or fallback).

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

#### 12 Part Types (discriminated on `data.type`)

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
| 13a | Session permissions | via session detail | `SessionTable.permission` JSON | Array of `{permission, pattern, action}` rules per tool |

### Partial Parity (build with limitations)

| # | Feature | Limitation | OpenCode Source |
|---|---------|-----------|-----------------|
| 14 | File activity | No explicit file operation tracking. Must infer from tool parts: `data.tool` in (`read`, `write`, `glob`, `grep`) + parse `data.state.input` for paths | `PartTable` type=tool |
| 15 | Timeline events | Can reconstruct from parts: text→response, tool→tool_call, reasoning→thinking, subtask→subagent_spawn, step-start/finish→step boundaries. **No** todo_update, command_invocation, skill_invocation events | `PartTable` ordered by `time_created` |
| 16 | Skills tracking | OpenCode has NO explicit skills system. Mode system exists (`plan`, `build`, `explore`) but differs from OMC. NO slash command inventory. Report skills as empty for OC sessions | `MessageTable.data.mode` (informational only) |
| 17 | Commands tracking | No slash command system implemented. `subtask` parts may have `data.command` field in future versions but currently unpopulated in real data. Report as empty for now | `PartTable` type=subtask (future use) |
| 18 | Modes tracking | OpenCode has mode system: `data.mode` ∈ {`"plan"`, `"build"`, `"explore"`, null}. NOT a skill equivalent, but useful for analytics. Expose as new `mode` field in session/message responses | `MessageTable.data.mode` |
| 19 | Session chains | OpenCode uses `parent_id` for subagent sessions, not continuation chains. No `leaf_uuid` / slug-based chain detection. Each session is standalone | `SessionTable.parent_id` |
| 20 | Models used | Extractable from `MessageTable.data.modelID` + `data.providerID`. Model IDs differ from Anthropic IDs (e.g. `big-pickle` via `opencode` provider). Also includes `variant` for thinking preference | `MessageTable.data` JSON |
| 21 | Git activity | `patch` parts track applied git patches (hash + files changed). Less granular than CC file-level tracking | `PartTable` type=patch |
| 22 | Plan mode | OC has plan mode (mode field on messages) but no standalone plan artifact files. 24 plan messages observed in real data. Show plan-mode conversation segments, not file-based plans | `MessageTable.data.mode = 'plan'` |
| 23 | Agent analytics | OC child sessions have full token data but cost is always $0. Agent types: `build`, `plan`, `explore` from `message.data.agent` | `SessionTable.parent_id` + `MessageTable.data` in child sessions |
| 24 | Subagent session detail | OC child sessions are full sessions with messages/parts/tools. Spawned via `task` tool in parent. Max depth = 1 level (hardcoded via permissions) | Child `SessionTable` rows via `parent_id` FK |

### Claude Code Only (N/A for OpenCode)

| # | Feature | Reason |
|---|---------|--------|
| 25 | Live sessions | Hook-driven (`~/.claude_karma/live-sessions/`). OpenCode has no hooks system |
| 26 | Hooks browser | OpenCode has no hook system |
| 27 | Plugins browser | OpenCode MCP servers configured differently (in `opencode.json`). Different discovery mechanism |
| 28 | File history snapshots | CC stores `FileHistorySnapshot` messages. OC has `snapshot` parts but they're filesystem hashes, not file content |
| 29 | Tool results (stored) | CC stores tool output in `tool-results/*.txt`. OC stores output inline in tool part `data.state.output` |
| 30 | Session index JSON | CC uses `sessions-index.json` for fast listing. OC already has SQLite (fast by default) |
| 31 | Desktop session linking | CC has Claude Desktop metadata in `~/Library/Application Support/Claude/`. Not applicable to OC |
| 32 | Session source (CLI/Desktop) | Existing `session_source` field distinguishes CLI vs Desktop. OC sessions are always CLI-equivalent |
| 33 | Plan approval hooks | CC-specific hook |
| 34 | Archived prompts (history.jsonl) | OC has no prompt preservation after session deletion. `time_archived` marks sessions archived (different feature) |
| 35 | Skills file browser | OC has no `~/.claude/skills/` equivalent. No YAML frontmatter skill files |
| 36 | Live session sub-statuses | Active/Waiting/Idle/Starting/Ended — hook-driven, OC has no hooks |

### OpenCode Only (new features)

| # | Feature | Source | Notes |
|---|---------|--------|-------|
| 37 | Step-level cost/tokens | `PartTable` type=step-finish | Per-step granularity not available in CC. Show as timeline enhancement |
| 38 | Session sharing | `SessionShareTable` | Public share URLs with secrets |
| 39 | Git patch tracking | `PartTable` type=patch | Git commit hashes + files per patch |
| 40 | Agent switch markers | `PartTable` type=agent | Tracks which agent is active at any point |
| 41 | API retry events | `PartTable` type=retry | Track API failures/retries |
| 42 | Permission rules | `PermissionTable` | Per-project tool permission config |

---

## Verified Data Gaps (from real DB analysis)

Findings verified against real OpenCode DB at `~/.local/share/opencode/opencode.db` (4 sessions, 63 messages, 286 parts).

### Git Branch Data — NOT AVAILABLE

OpenCode's SQLite DB contains zero git branch fields. The `project.vcs = "git"` is a type flag only. No column or JSON field in `session`, `message`, or `part` tables stores branch information.

**Mitigation:** Runtime inference via `git -C <directory> rev-parse --abbrev-ref HEAD` using the session's `directory` field. This only reflects the **current** branch at query time — historical branch attribution is impossible without external instrumentation.

**Impact:** Git branch filters and branch badges on session cards will show "unknown" for past OC sessions unless the directory still points to the same branch.

### Cost Data — ALWAYS $0

The `message.data.cost` field is present but **always 0.0** across all observed sessions. OpenCode does not populate cost from providers.

**Mitigation:** Compute cost externally from `data.tokens` + a model pricing lookup table. However, model IDs are OpenCode aliases (e.g., `big-pickle` via `opencode` provider), not standard Anthropic model IDs. A `modelID → pricing` mapping must be maintained.

**Impact:** Cost analytics for OC sessions will either be $0 (raw) or require a configurable pricing table. Mark cost as "estimated" in the UI for OC sessions.

### Part Types — Schema vs Reality

The design references 11 part types from OpenCode's TypeScript source. Only 6 exist in real data:

| Part Type | In Real DB? | Notes |
|-----------|------------|-------|
| `text` | Yes | |
| `reasoning` | Yes | |
| `tool` | Yes | 91 instances |
| `step-start` | Yes | |
| `step-finish` | Yes | |
| `patch` | Yes | 1 instance — hash is OC-internal, NOT a git commit hash |
| `subtask` | **No** | Subagents spawned via `task` tool + child session row instead |
| `agent` | **No** | Agent identity tracked via `message.data.agent` field instead |
| `compaction` | **No** | Compaction tracked via `session.time_compacting` timestamp instead |
| `file` | **No** | Not observed |
| `snapshot` | **No** | `step-start`/`step-finish` have snapshot hash refs |
| `retry` | **No** | Not observed |

**Impact:** Timeline event mapping for `subtask`, `agent`, `compaction`, `retry` part types should gracefully handle absence. Use message-level `agent` field and session-level `time_compacting` as fallbacks.

### Plan Mode — MODE, NOT ARTIFACT

OpenCode has plan mode (`message.data.mode = 'plan'`, 24 messages observed in 1 session). Unlike Claude Code's plan files in `~/.claude/plans/`, OpenCode's plans are embedded in the message conversation. There is no standalone plan file to display.

**Impact:** The Plans page can show OC plan-mode conversation segments filtered by `mode = 'plan'`, but the plan file viewer/download feature is CC-only.

### Subagent Architecture Differences

| Aspect | Claude Code | OpenCode |
|--------|-------------|----------|
| Storage | Separate `agent-*.jsonl` file | Child session row (same DB) |
| Spawn mechanism | Tool use → new JSONL | `task` tool → child session with `parent_id` |
| Agent type | Filename pattern | `message.data.agent` field (`build`, `plan`, `explore`) |
| Max depth | Multi-level | 1 level (hardcoded via permission deny rules) |
| Cost tracking | Available (`costUSD`) | Broken ($0 always) |
| Token tracking | Per-message in JSONL | Per-message in DB (input, output, reasoning, cache.read, cache.write) |

### Recommended Subagent Query

```sql
SELECT
    child.id as subagent_id,
    child.slug,
    child.title,
    child.parent_id,
    parent.slug as parent_slug,
    (child.time_updated - child.time_created) as duration_ms,
    (SELECT json_extract(data, '$.agent') FROM message
     WHERE session_id = child.id
     AND json_extract(data, '$.role') = 'assistant' LIMIT 1) as agent_type,
    (SELECT SUM(json_extract(data, '$.tokens.total')) FROM message
     WHERE session_id = child.id
     AND json_extract(data, '$.role') = 'assistant') as total_tokens,
    (SELECT COUNT(*) FROM part WHERE session_id = child.id
     AND json_extract(data, '$.type') = 'tool') as tool_count
FROM session child
JOIN session parent ON child.parent_id = parent.id
```

---

## OpenCode Modes, Agents & Skills System (NEW RESEARCH)

OpenCode has a built-in multi-mode orchestration system comparable to oh-my-claudecode's mode infrastructure.

### Three Execution Modes

| Mode | Purpose | Agent | Model Preference | Thinking | Real Usage |
|------|---------|-------|------------------|----------|-----------|
| **plan** | Strategic reasoning, requirements gathering, planning | plan | claude-opus-4-5 | Extended (variant="max") | 25 messages observed |
| **build** | Code generation, implementation, execution | build | big-pickle (OC proprietary) or claude-opus-4-5 | Max for complex (variant="max"), null for simple | 16 messages observed |
| **explore** | Codebase analysis, file discovery, search | explore | claude-opus-4-5 | No thinking (variant=null) | 15 messages observed |
| *(none)* | Unstructured conversation | *(implicit)* | *(varies)* | No thinking | 4 messages observed (legacy) |

**Implementation note:** Each mode message carries both `mode` and `agent` fields (currently always matching), but `agent` appears to be the more granular identifier.

### Skills & Commands

OpenCode does NOT have an explicit "skills" system like oh-my-claudecode. However:

1. **Slash commands in subtasks** (`subtask.command` field):
   - Commands are stored in `PartTable` entries with `type: "subtask"` and `data.command` field
   - These represent spawned subagents with explicit commands
   - **Current observation:** No slash commands found in real data (subtask parts exist but no `command` field populated)

2. **Project-level commands configuration** (`project.commands` field):
   - ProjectTable has a `commands` column (JSON-typed, currently null in real data)
   - Schema suggests: `{ start?: string }` — only startup command support
   - Not yet used for skill/command registration in observed sessions

3. **Tool access control** (`PermissionTable`):
   - Per-project tool permission rules (not per-command)
   - Cannot directly map to OMC's "skills" concept

**Mapping for claude-karma:**
- **Skills:** Report as empty for OpenCode (not supported)
- **Commands:** Only include subtask commands if `data.command` is present; otherwise skip
- **Modes:** Expose as new `mode` field in session/message detail (useful for analytics, but not searchable like OMC skills)

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
| `data.cost` | `cost` | Pre-computed USD — but **always $0** in real data (see Verified Data Gaps) |

### Derived Metrics (Verified Formulas)

| Metric | Formula | Notes |
|--------|---------|-------|
| Session duration | `session.time_updated - session.time_created` | Milliseconds. Range observed: 44s to 53min |
| Response latency | `data.time.completed - data.time.created` | Per assistant message, ms. Range: 4–56s |
| Cache hit rate | `cache_read / NULLIF(cache_read + input_tokens, 0) * 100` | Use NULLIF guard. Range: 0% (cold start) to 99.99% |
| Message count | `COUNT(*) FROM message WHERE session_id = ?` | Separate user/assistant via `json_extract(data, '$.role')` |
| Cost | **Cannot compute from DB** — `data.cost` always $0 | Requires external `modelID → pricing` mapping. Model IDs are OC aliases (e.g., `big-pickle`) |
| Tool count | `COUNT(*) FROM part WHERE session_id = ? AND json_extract(data, '$.type') = 'tool'` | 8 tool types observed: read, grep, bash, glob, question, write, todowrite, task |

### Message Metadata (Mode, Agent, Variant)

| OpenCode Field | Claude-Karma Field | Notes |
|----------------|-------------------|-------|
| `data.mode` | `mode` | `"plan"`, `"build"`, `"explore"`, or null — new field (CC has no equivalent) |
| `data.agent` | `agent` | Corresponds to mode; mostly redundant but track both |
| `data.variant` | `variant` | `"max"` (extended thinking) or null. New field for tracking thinking preference |
| `data.modelID` | `model` | Direct (e.g., `"big-pickle"`, `"claude-opus-4-5"`) |
| `data.providerID` | `provider` | Direct (e.g., `"opencode"`, `"anthropic"`) |

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

| Part Type | TimelineEvent Type | Verified in Real DB? | Fields |
|-----------|-------------------|---------------------|--------|
| `text` (in user msg) | `prompt` | Yes | timestamp from message |
| `text` (in assistant msg) | `response` | Yes | timestamp, text preview |
| `tool` | `tool_call` | Yes (91 instances) | tool name, status, duration, input/output preview |
| `reasoning` | `thinking` | Yes (38 instances) | duration from `time.start`→`time.end` |
| `subtask` | `subagent_spawn` | **No — use `task` tool parts instead** | agent name, prompt, description |
| `step-start` | `step_boundary` | Yes (56 instances) | snapshot ref (new event type) |
| `step-finish` | `step_boundary` | Yes (56 instances) | cost, tokens, finish reason (new event type) |
| `patch` | `git_patch` | Yes (1 instance — hash is OC-internal, not git commit) | hash, files changed (new event type) |
| `compaction` | `compaction` | **No — check `session.time_compacting` instead** | auto vs manual (new event type) |
| `agent` | `agent_switch` | **No — check `message.data.agent` field instead** | agent name (new event type) |
| `retry` | `api_retry` | **No — not observed** | attempt number, error (new event type) |

**New timeline event types** (`step_boundary`, `git_patch`, `compaction`, `agent_switch`, `api_retry`) are OpenCode-specific but could be useful for Claude Code too in the future. Types marked as not verified should gracefully handle absence — use the noted fallback fields instead.

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

**Schema change needed:** Add `data_source TEXT DEFAULT 'claude_code'` column to `sessions` table. Bump `SCHEMA_VERSION` (currently 8 → 9) in `api/db/connection.py` to trigger migration.

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
│   ├── commands.py            # MODIFIED — merge command data
│   ├── agent_analytics.py     # MODIFIED — index OC child sessions into subagent analytics
│   ├── subagent_sessions.py   # MODIFIED — support OC child sessions as subagent detail views
│   ├── plans.py               # PARTIAL — show OC plan-mode messages (no standalone plan files)
│   ├── skills.py              # MODIFIED — merge OC tool/command data into skills view
│   ├── admin.py               # MODIFIED — reindex endpoint includes OC sessions
│   ├── settings.py            # MODIFIED — OpenCode DB path configuration
│   ├── live_sessions.py       # UNCHANGED — CC-Only (hook-driven)
│   ├── hooks.py               # UNCHANGED — CC-Only
│   ├── plugins.py             # UNCHANGED — CC-Only (different plugin system)
│   ├── history.py             # UNCHANGED — CC-Only (no OC equivalent)
│   └── docs.py                # UNCHANGED — reads project docs, not data-source-specific
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

## Router Classification

Every router in `api/routers/` classified for OpenCode integration:

| Router | Status | Notes |
|--------|--------|-------|
| `projects.py` | MODIFIED | Merge results from both sources |
| `sessions.py` | MODIFIED | Merge results from both sources |
| `analytics.py` | MODIFIED | Aggregate across sources |
| `tools.py` | MODIFIED | Merge tool usage from both sources |
| `agents.py` | MODIFIED | Merge agent data from both sources |
| `commands.py` | MODIFIED | Merge command data |
| `skills.py` | MODIFIED | Merge skill/command data (partial — OC has no skill files, only `subtask.command` slash commands from `task` tool parts) |
| `agent_analytics.py` | MODIFIED | Index OC child sessions (via `parent_id`) into `subagent_invocations` table. OC provides tokens per subagent but cost is always $0. Agent types from `message.data.agent` field: `build`, `plan`, `explore` |
| `subagent_sessions.py` | MODIFIED | Support OC child sessions as subagents. OC child sessions have full messages/parts/tools queryable from the same SQLite DB via `parent_id` FK. Max depth = 1 level |
| `plans.py` | PARTIAL | OC has plan mode (`message.data.mode = 'plan'`), but no separate plan artifact files like CC's `~/.claude/plans/`. Plan content is embedded in message conversation. Can show plan-mode messages as "plans" but no standalone plan file viewer |
| `admin.py` | MODIFIED | `/admin/reindex` must also index OC sessions into metadata DB. Add `data_source` parameter to reindex endpoint |
| `live_sessions.py` | N/A (CC-Only) | Hook-driven, OC has no hooks system |
| `hooks.py` | N/A (CC-Only) | OC has no hook system |
| `plugins.py` | N/A (CC-Only) | OC uses `@opencode-ai/plugin` with separate config. No automatic discovery mechanism equivalent to CC's MCP JSON. Future phase could add OC plugin discovery from `opencode.json` |
| `docs.py` | UNCHANGED | Reads from project's own `docs/about/` directory — not data-source-specific. Works identically for both sources |
| `history.py` | N/A (CC-Only) | OC has no equivalent of `~/.claude/history.jsonl` for archived prompts. OC's `time_archived` on sessions is a different feature (marks session as archived, not prompt preservation after deletion) |
| `settings.py` | MODIFIED | Add OpenCode DB path config. Existing CC-specific settings (retention, permissions, plugins) remain CC-only |

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
