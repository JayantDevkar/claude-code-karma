# Architecture

Technical overview of Claude Karma's system design, data flow, and key patterns.

---

## System Diagram

```
~/.claude/projects/{encoded-path}/{uuid}.jsonl
~/.claude/projects/{encoded-path}/{uuid}/subagents/agent-*.jsonl
~/.claude/projects/{encoded-path}/{uuid}/tool-results/toolu_*.txt
~/.claude/todos/{uuid}-*.json
~/.claude_karma/live-sessions/{slug}.json
        |
        v
+---------------------------------------+
|           API (FastAPI, port 8000)     |
|                                        |
|  models/   — JSONL parsing, Pydantic   |
|  routers/  — REST endpoints            |
|  utils.py  — path encoding, helpers    |
+---------------------------------------+
        |
        v  (JSON over HTTP)
+---------------------------------------+
|      Frontend (SvelteKit, port 5173)   |
|                                        |
|  src/routes/   — pages & layouts       |
|  src/lib/      — components, stores    |
|  Svelte 5 runes, Tailwind CSS 4       |
+---------------------------------------+
        |
        v
    Browser (dashboard UI)

+---------------------------------------+
|     Hooks (Claude Code integration)    |
|                                        |
|  live_session_tracker.py               |
|  session_title_generator.py            |
|  plan_approval.py                      |
+---------------------------------------+
        |
        v
  ~/.claude_karma/live-sessions/*.json
```

---

## Three Layers

### 1. Data Parsing Layer (API)

The API reads Claude Code's local file system and parses raw JSONL into structured Pydantic models. It discovers projects by scanning `~/.claude/projects/`, reads session files lazily, and serves parsed data through REST endpoints.

### 2. Visualization Layer (Frontend)

The SvelteKit frontend fetches data from the API and renders interactive dashboards. It uses Svelte 5 runes for reactivity, Tailwind CSS 4 for styling, Chart.js for visualizations, and bits-ui for accessible UI primitives.

### 3. Real-Time Tracking Layer (Hooks)

Claude Code hook scripts fire during session events and write state to `~/.claude_karma/live-sessions/`. The API reads these state files to serve live session data. Hooks run in the Claude Code process and require no separate daemon.

---

## Monorepo Structure

```
claude-karma/
├── api/                    # FastAPI backend (Python)
│   ├── models/             # Pydantic models for JSONL parsing
│   ├── routers/            # FastAPI route handlers
│   ├── tests/              # pytest test suite
│   └── main.py             # Application entry point
├── frontend/               # SvelteKit frontend (Svelte 5)
│   ├── src/routes/         # Page routes
│   ├── src/lib/            # Shared components, stores, utils
│   └── static/             # Static assets
├── captain-hook/           # Pydantic hook models library
│   ├── captain_hook/       # Library source
│   └── tests/              # Model tests
├── hooks/                  # Production hook scripts
│   ├── live_session_tracker.py
│   ├── session_title_generator.py
│   └── plan_approval.py
└── docs/                   # Documentation
```

---

## Claude Code Storage Locations

Claude Karma reads from these locations on disk:

| Data | Location |
|------|----------|
| Session JSONL | `~/.claude/projects/{encoded-path}/{uuid}.jsonl` |
| Subagent sessions | `~/.claude/projects/{encoded-path}/{uuid}/subagents/agent-*.jsonl` |
| Tool result outputs | `~/.claude/projects/{encoded-path}/{uuid}/tool-results/toolu_*.txt` |
| Debug logs | `~/.claude/debug/{uuid}.txt` |
| Todo items | `~/.claude/todos/{uuid}-*.json` |
| Live session state | `~/.claude_karma/live-sessions/{slug}.json` |

---

## Path Encoding

Claude Code encodes project paths for use as directory names. The encoding replaces the leading `/` with `-` and all subsequent `/` characters with `-`:

| Original Path | Encoded |
|---------------|---------|
| `/Users/me/repo` | `-Users-me-repo` |
| `/home/dev/my-project` | `-home-dev-my-project` |

The API decodes these paths when presenting project names to the frontend.

---

## API Model Hierarchy

```
Project (entry point — one per encoded path)
├── Session ({uuid}.jsonl — one per conversation)
│   ├── Message
│   │   ├── UserMessage
│   │   ├── AssistantMessage
│   │   ├── FileHistorySnapshot
│   │   └── SummaryMessage (indicates compaction)
│   ├── Agent (subagents/ — spawned Task agents)
│   ├── ToolResult (tool-results/ — large tool outputs)
│   └── TodoItem (todos/ — task lists)
└── Agent (standalone: agent-{id}.jsonl)
```

All models are Pydantic v2 with `ConfigDict(frozen=True)` for immutability.

---

## Key Patterns

### Lazy Loading

Session messages are not loaded into memory at discovery time. The `iter_messages()` generator reads and yields JSONL lines on demand, keeping memory usage constant regardless of session size.

### Frozen Pydantic Models

All data models use `frozen=True` configuration. Once parsed, objects are immutable. This prevents accidental mutation and enables safe caching.

### Session Chains

Related sessions are detected via two mechanisms:
1. **leaf_uuid** — When a session is resumed, the new session references the original via `leaf_uuid`
2. **Slug matching** — Sessions within the same project that share temporal proximity are linked

### Compaction Detection

When Claude Code compacts a session's context window, it inserts a `SummaryMessage` containing the compressed history. Claude Karma detects these messages and flags the session as compacted in the UI.

### Async File I/O

The API uses `aiofiles` for non-blocking file reads. Since all data comes from the local filesystem (not a database), async I/O prevents session parsing from blocking the event loop.

---

## Tech Stack Details

### Backend

| Component | Technology | Purpose |
|-----------|-----------|---------|
| Framework | FastAPI | Async web framework with OpenAPI docs |
| Validation | Pydantic 2.x | Data parsing and serialization |
| File I/O | aiofiles | Non-blocking filesystem access |
| Testing | pytest | Unit and integration tests |
| Linting | ruff | Python linting and formatting |
| Runtime | Python 3.9+ | Minimum supported version |

### Frontend

| Component | Technology | Purpose |
|-----------|-----------|---------|
| Framework | SvelteKit 2 | Full-stack Svelte framework |
| UI Library | Svelte 5 | Runes-based reactivity ($state, $derived, $effect) |
| Styling | Tailwind CSS 4 | Utility-first CSS |
| Charts | Chart.js 4 | Data visualizations |
| UI Primitives | bits-ui | Accessible component library |
| Icons | lucide-svelte | Icon set |
| Language | TypeScript | Type safety |
| Adapter | adapter-node | Node.js deployment |
