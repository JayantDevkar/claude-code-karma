# Architecture

Technical overview of Claude Code Karma's system design, data flow, and key patterns.

---

## System Diagram

```
~/.claude/projects/{encoded-path}/{uuid}.jsonl
~/.claude/projects/{encoded-path}/{uuid}/subagents/agent-*.jsonl
~/.claude/projects/{encoded-path}/{uuid}/tool-results/toolu_*.txt
~/.claude/todos/{uuid}-*.json
~/.claude_karma/live-sessions/{slug}.json
~/.claude_karma/remote-sessions/{user-id}/*
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

+---------------------------------------+
|      Sync Layer (Session Sharing)      |
|                                        |
|  CLI (karma):                          |
|  - karma init, karma team create       |
|  - karma project add                   |
|  - karma sync (IPFS) / karma watch     |
|  - karma pull / karma status           |
|                                        |
|  IPFS Backend:                         |
|  - Kubo daemon for publishing          |
|  - IPNS for versioning                 |
|                                        |
|  Syncthing Backend:                    |
|  - Syncthing daemon for sync           |
|  - Session watcher for packaging       |
+---------------------------------------+
        |
        v
  ~/.claude_karma/remote-sessions/  (both backends write here, API reads from here)
  ~/.claude_karma/sync-inbox/       (incoming feedback)
```

---

## Four Layers

### 1. Data Parsing Layer (API)

The API reads Claude Code's local file system and parses raw JSONL into structured Pydantic models. It discovers projects by scanning `~/.claude/projects/`, reads session files lazily, and serves parsed data through REST endpoints.

### 2. Visualization Layer (Frontend)

The SvelteKit frontend fetches data from the API and renders interactive dashboards. It uses Svelte 5 runes for reactivity, Tailwind CSS 4 for styling, Chart.js for visualizations, and bits-ui for accessible UI primitives.

### 3. Real-Time Tracking Layer (Hooks)

Claude Code hook scripts fire during session events and write state to `~/.claude_karma/live-sessions/`. The API reads these state files to serve live session data. Hooks run in the Claude Code process and require no separate daemon.

### 4. Session Sync Layer (CLI + Backends)

The `karma` CLI orchestrates cross-system session sharing via pluggable backends:

- **IPFS backend**: Publish sessions to IPFS, discover via IPNS, pull on-demand. Uses Kubo daemon.
- **Syncthing backend**: Package sessions locally, auto-sync bidirectionally via Syncthing mesh network.

Both backends write to the same format in `~/.claude_karma/remote-sessions/`, so the API reads them identically.

---

## Monorepo Structure

```
claude-code-karma/
├── api/                    # FastAPI backend (Python)
│   ├── models/             # Pydantic models for JSONL parsing
│   ├── routers/            # FastAPI route handlers
│   │   ├── sync_status.py  # /sync/* endpoints
│   │   └── remote_sessions.py # /users/* endpoints
│   ├── tests/              # pytest test suite
│   └── main.py             # Application entry point
├── frontend/               # SvelteKit frontend (Svelte 5)
│   ├── src/routes/         # Page routes
│   │   └── team/           # Team management UI
│   ├── src/lib/            # Shared components, stores, utils
│   └── static/             # Static assets
├── cli/karma/              # Karma CLI package (Python)
│   ├── main.py             # CLI entry point
│   ├── config.py           # Config models and loading
│   ├── sync.py             # Sync orchestration
│   ├── ipfs.py             # IPFS backend client
│   ├── syncthing.py        # Syncthing backend client
│   ├── packager.py         # Session packaging
│   ├── watcher.py          # Syncthing file watcher
│   └── tests/              # CLI tests
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

Claude Code Karma reads from and writes to these locations on disk:

| Data | Location |
|------|----------|
| Session JSONL | `~/.claude/projects/{encoded-path}/{uuid}.jsonl` |
| Subagent sessions | `~/.claude/projects/{encoded-path}/{uuid}/subagents/agent-*.jsonl` |
| Tool result outputs | `~/.claude/projects/{encoded-path}/{uuid}/tool-results/toolu_*.txt` |
| Debug logs | `~/.claude/debug/{uuid}.txt` |
| Todo items | `~/.claude/todos/{uuid}-*.json` |
| Live session state | `~/.claude_karma/live-sessions/{slug}.json` |
| Sync config | `~/.claude_karma/sync-config.json` |
| Incoming feedback | `~/.claude_karma/sync-inbox/{team}/{owner-id}/{encoded-path}/feedback/` |
| Remote sessions | `~/.claude_karma/remote-sessions/{user-id}/{encoded-path}/` |

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

## Sync Data Model

```
Manifest (per-project sync metadata)
├── version: int (format version, currently 1)
├── user_id: str (freelancer/contributor ID)
├── machine_id: str (unique per machine)
├── project_path: str (original filesystem path)
├── project_encoded: str (encoded path for filenames)
├── synced_at: datetime (ISO 8601 timestamp)
├── session_count: int (number of sessions included)
├── sync_backend: str ("ipfs" or "syncthing")
├── previous_cid: str (for IPFS: CID of previous sync)
└── sessions: list[SessionSummary]
    ├── uuid: str (session ID)
    ├── mtime: datetime (last modified)
    └── size_bytes: int (on-disk size)
```

Both IPFS and Syncthing backends produce identical manifest.json files, allowing the API to read them uniformly.

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

When Claude Code compacts a session's context window, it inserts a `SummaryMessage` containing the compressed history. Claude Code Karma detects these messages and flags the session as compacted in the UI.

### Async File I/O

The API uses `aiofiles` for non-blocking file reads. Since all data comes from the local filesystem (not a database), async I/O prevents session parsing from blocking the event loop.

### Pluggable Sync Backends

Both IPFS and Syncthing backends implement a common interface:
- `init()` — Initialize backend on machine
- `add_project()` — Register project for syncing
- `sync()` / `watch()` — Initiate sync (IPFS) or start watcher (Syncthing)
- `pull()` — Pull remote sessions (IPFS) or poll for changes (optional for Syncthing)
- `status()` — Show sync state

This abstraction allows users to switch backends or use multiple backends for different teams.

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

### CLI (Karma)

| Component | Technology | Purpose |
|-----------|-----------|---------|
| Framework | Click | Python CLI framework |
| Config | Pydantic | Configuration models and persistence |
| HTTP Client | requests | Syncthing/IPFS API communication |
| File Watching | watchdog | Filesystem event monitoring (Syncthing) |
| Runtime | Python 3.9+ | Minimum supported version |
