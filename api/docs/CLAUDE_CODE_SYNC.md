# Claude Code Data Sync - Implementation Guide

> **Purpose**: This document outlines changes needed to keep Claude Karma in sync with Claude Code's evolving data structures (versions 2.1.3 → 2.1.17+).

## Background

Claude Karma parses Claude Code's local storage (`~/.claude/`) to provide session analytics and visualization. As Claude Code evolves, new data structures are introduced that we need to support for accurate and efficient data display.

**Key Finding**: Claude Code now maintains pre-computed metadata that we were previously calculating ourselves by parsing JSONL files. Using these indexes provides ~10x performance improvement for list views.

---

## Implementation Status

| Phase | Feature | API Status | Frontend Status |
|-------|---------|------------|-----------------|
| 1 | Sessions Index | ✅ Complete | ⏳ Pending |
| 2 | Tasks System | ✅ Complete | ⏳ Pending |
| 3 | Plans Directory | ✅ Complete | ⏳ Pending |
| 4 | Plugins | ✅ Complete | ⏳ Pending |

---

## Phase 1: Sessions Index (API ✅ IMPLEMENTED)

### What Changed in Claude Code

Claude Code now maintains a `sessions-index.json` file in each project directory:

```
~/.claude/projects/{encoded-path}/sessions-index.json
```

This file contains pre-computed metadata for all sessions, eliminating the need to parse individual JSONL files for list views.

### Key Discovery: `summary` Field

Claude Code generates automatic session summaries! This is more useful than showing the truncated first prompt because:
- It describes what the session accomplished
- It's contextual and concise
- Examples: "SQLite vs Valkey Database Selection Analysis", "Agent deployment & backlog orchestration"

### API Implementation

**Files:**
- `api/models/session_index.py` - `SessionIndex` and `SessionIndexEntry` models
- `api/schemas.py` - Added `summary` field to `SessionSummary`

**Available Data** (via existing `/projects/{encoded_name}` endpoint):

The `SessionSummary` schema now includes:
```typescript
interface SessionSummary {
  uuid: string;
  slug: string;
  start_time: string;        // ISO datetime
  duration_seconds: number;
  message_count: number;
  initial_prompt: string;    // First 500 chars of user's first message
  summary: string | null;    // NEW: Claude's auto-generated summary
  project_encoded_name: string;
  // ... other fields
}
```

### Frontend Work Needed

1. **Display `summary` field** in session list views (e.g., `/projects/[encoded_name]`)
   - Show `summary` when available, fall back to `initial_prompt` if null
   - Summary is more descriptive: "Implemented user authentication" vs "help me add login..."

2. **Consider UI updates:**
   - Session cards could show summary as primary text
   - Tooltip or secondary line for initial_prompt

---

## Phase 2: Tasks System (API ✅ IMPLEMENTED)

### What Changed in Claude Code (v2.1.16)

Claude Code introduced a new Tasks system that replaces/augments the legacy Todos:

```
~/.claude/tasks/{session-uuid}/
├── 1.json
├── 2.json
└── 3.json
```

### Key Differences from Todos

| Aspect | Legacy Todos | New Tasks |
|--------|--------------|-----------|
| Location | `~/.claude/todos/{uuid}-*.json` | `~/.claude/tasks/{uuid}/` |
| Structure | Array in single file | Individual files per task |
| Fields | `content`, `status` | `subject`, `description`, `blocks`, `blockedBy` |
| Dependencies | None | Full dependency graph |

### API Implementation

**Files:**
- `api/models/task.py` - `Task` model with dependency tracking
- `api/routers/sessions.py` - Added tasks endpoint
- `api/schemas.py` - `TaskSchema`

**Endpoint:** `GET /sessions/{uuid}/tasks`

**Response Schema:**
```typescript
interface Task {
  id: string;
  subject: string;           // Brief task title
  description: string;       // Detailed description
  status: "pending" | "in_progress" | "completed";
  active_form: string | null; // Present-tense verb form (e.g., "Writing tests")
  blocks: string[];          // Task IDs this task blocks
  blocked_by: string[];      // Task IDs blocking this task
}
```

**Example Response:**
```json
[
  {
    "id": "1",
    "subject": "Phase 1: Discover project scope",
    "description": "Detailed description of what needs to be done",
    "active_form": "Discovering project scope",
    "status": "completed",
    "blocks": ["2", "3"],
    "blocked_by": []
  },
  {
    "id": "2",
    "subject": "Phase 2: Implement core feature",
    "description": "Build the main functionality",
    "active_form": "Implementing core feature",
    "status": "in_progress",
    "blocks": [],
    "blocked_by": ["1"]
  }
]
```

### Frontend Work Needed

1. **New endpoint to consume:** `GET /sessions/{uuid}/tasks`

2. **Task list component** for session detail view
   - Show subject, status, description
   - Status badges: pending (gray), in_progress (blue), completed (green)
   - `active_form` can be used for loading states

3. **Dependency visualization** (optional but valuable)
   - `blocks` and `blocked_by` form a DAG
   - Could show as: indented list, tree view, or simple graph
   - Blocked tasks could be visually dimmed

4. **Fallback:** Sessions without tasks will return empty array `[]`

---

## Phase 3: Plans Directory (API ✅ IMPLEMENTED)

### What Changed in Claude Code (v2.1.9)

Claude Code stores plan files created during "plan mode":

```
~/.claude/plans/{slug}.md
```

Example filenames: `abundant-dancing-newell.md`, `cheeky-foraging-wall.md`

### API Implementation

**Files:**
- `api/models/plan.py` - `Plan` model
- `api/routers/plans.py` - Plans endpoints
- `api/schemas.py` - `PlanSummary`, `PlanDetail`

**Endpoints:**

| Method | Endpoint | Response | Description |
|--------|----------|----------|-------------|
| GET | `/plans` | `PlanSummary[]` | List all plans |
| GET | `/plans/stats` | `object` | Aggregate statistics |
| GET | `/plans/{slug}` | `PlanDetail` | Single plan with content |

**PlanSummary Schema:**
```typescript
interface PlanSummary {
  slug: string;              // Plan identifier (filename without .md)
  title: string | null;      // Extracted from first h1 header
  preview: string;           // First 500 characters
  word_count: number;
  created: string;           // ISO datetime
  modified: string;          // ISO datetime
  size_bytes: number;
}
```

**PlanDetail Schema** (extends PlanSummary):
```typescript
interface PlanDetail extends PlanSummary {
  content: string;           // Full markdown content
}
```

**Stats Endpoint Response:**
```json
{
  "total_plans": 12,
  "total_words": 15420,
  "total_size_bytes": 98304,
  "oldest_plan": "ancient-plan-slug",
  "newest_plan": "latest-plan-slug"
}
```

### Frontend Work Needed

1. **New route:** `/plans` - Plans listing page
   - Fetch from `GET /plans`
   - Show title, preview, word count, dates
   - Sort by modified (newest first - API default)

2. **New route:** `/plans/[slug]` - Plan detail page
   - Fetch from `GET /plans/{slug}`
   - Render markdown content
   - Show metadata (created, modified, word count)

3. **Navigation:** Add "Plans" to sidebar/nav

4. **Optional:** Stats dashboard widget using `/plans/stats`

---

## Phase 4: Plugins (API ✅ IMPLEMENTED)

### What Changed in Claude Code (v2.1.14+)

Plugin installations are tracked:

```
~/.claude/plugins/installed_plugins.json
```

### API Implementation

**Files:**
- `api/models/plugin.py` - `PluginInstallation`, `InstalledPlugins` models
- `api/routers/plugins.py` - Plugin endpoints
- `api/schemas.py` - Plugin schemas

**Endpoints:**

| Method | Endpoint | Response | Description |
|--------|----------|----------|-------------|
| GET | `/plugins` | `PluginsOverview` | List all plugins with summary |
| GET | `/plugins/stats` | `object` | Aggregate statistics by scope |
| GET | `/plugins/{name}` | `PluginDetail` | Single plugin details |

**PluginsOverview Schema:**
```typescript
interface PluginsOverview {
  version: number;           // Plugin file schema version
  total_plugins: number;     // Unique plugin count
  total_installations: number; // Sum of all installations
  plugins: PluginSummary[];
}

interface PluginSummary {
  name: string;              // e.g., "github@claude-plugins-official"
  installation_count: number;
  scopes: string[];          // ["user", "project"]
  latest_version: string;
  latest_update: string;     // ISO datetime
}
```

**PluginDetail Schema:**
```typescript
interface PluginDetail {
  name: string;
  installations: PluginInstallation[];
}

interface PluginInstallation {
  plugin_name: string;
  scope: string;             // "user" or "project"
  install_path: string;
  version: string;
  installed_at: string;      // ISO datetime
  last_updated: string;      // ISO datetime
}
```

**Stats Endpoint Response:**
```json
{
  "total_plugins": 3,
  "total_installations": 5,
  "version": 2,
  "by_scope": {
    "user": 3,
    "project": 2
  },
  "oldest_install": "2026-01-03T01:14:29.419Z",
  "newest_install": "2026-01-21T09:41:35.704Z"
}
```

### Frontend Work Needed

1. **New route:** `/plugins` - Plugins listing page
   - Fetch from `GET /plugins`
   - Show plugin name, installation count, scopes, version
   - Group by scope or show scope badges

2. **Plugin detail view** (optional)
   - Fetch from `GET /plugins/{name}`
   - Note: Plugin names contain `@` - use URL encoding

3. **Settings integration:** Could add plugins section to `/settings`

4. **Dashboard widget:** Plugin count/stats using `/plugins/stats`

---

## File Locations Reference

| Data | Location | API Status |
|------|----------|------------|
| Session JSONL | `~/.claude/projects/{path}/{uuid}.jsonl` | ✅ Supported |
| Sessions Index | `~/.claude/projects/{path}/sessions-index.json` | ✅ Phase 1 |
| Tasks | `~/.claude/tasks/{uuid}/` | ✅ Phase 2 |
| Legacy Todos | `~/.claude/todos/{uuid}-*.json` | ✅ Supported |
| Plans | `~/.claude/plans/{slug}.md` | ✅ Phase 3 |
| Plugins | `~/.claude/plugins/installed_plugins.json` | ✅ Phase 4 |
| Subagents | `~/.claude/projects/{path}/{uuid}/subagents/` | ✅ Supported |
| Tool Results | `~/.claude/projects/{path}/{uuid}/tool-results/` | ✅ Supported |
| Debug Logs | `~/.claude/debug/{uuid}.txt` | ✅ Supported |

---

## API Endpoints Summary (New)

| Method | Endpoint | Phase | Description |
|--------|----------|-------|-------------|
| GET | `/sessions/{uuid}/tasks` | 2 | Session tasks with dependencies |
| GET | `/plans` | 3 | List all plans |
| GET | `/plans/stats` | 3 | Plan statistics |
| GET | `/plans/{slug}` | 3 | Single plan detail |
| GET | `/plugins` | 4 | List all plugins |
| GET | `/plugins/stats` | 4 | Plugin statistics |
| GET | `/plugins/{name}` | 4 | Single plugin detail |

---

## Testing

```bash
# Test Phase 2: Tasks
curl http://localhost:8000/sessions/{session-uuid}/tasks | jq

# Test Phase 3: Plans
curl http://localhost:8000/plans | jq
curl http://localhost:8000/plans/stats | jq
curl http://localhost:8000/plans/{slug} | jq

# Test Phase 4: Plugins
curl http://localhost:8000/plugins | jq
curl http://localhost:8000/plugins/stats | jq
curl "http://localhost:8000/plugins/github%40claude-plugins-official" | jq
```

---

## References

- [Claude Code Changelog](https://github.com/anthropics/claude-code/blob/main/CHANGELOG.md)
- [Claude Code GitHub Releases](https://github.com/anthropics/claude-code/releases)
- Sessions index introduced in ~2.1.10
- Plans directory introduced in 2.1.9
- Plugins tracking introduced in 2.1.14
- Tasks system introduced in 2.1.16

---

## Git Commits

| Phase | Commit | Description |
|-------|--------|-------------|
| 1 | `8dbb553` | Sessions index support |
| 2 | `ed7e79d` | Tasks system support |
| 3 | `d95d673` | Plans directory support |
| 4 | `55ee419` | Plugins support |
