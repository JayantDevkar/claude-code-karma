# Architecture

Understanding how Claude Code Karma works internally.

## Data flow

```
Claude Code writes sessions to ~/.claude/projects/
        ↓
API reads JSONL files from disk
        ↓
API parses with Pydantic models
        ↓
API serves REST endpoints (JSON)
        ↓
Frontend fetches from API
        ↓
Browser displays dashboard

Hooks fire during Claude Code sessions
        ↓
Hooks write state to ~/.claude_karma/live-sessions/
        ↓
API reads live session state
        ↓
Dashboard shows real-time status

CLI watches for new sessions
        ↓
Sessions are packaged locally
        ↓
Syncthing syncs to team members
        ↓
Their dashboards show remote sessions
```

## System layers

### Data Parsing (API)
The API scans `~/.claude/projects/` for session JSONL files. When you request a session, it reads the file, parses it with Pydantic models, and returns JSON. Messages are loaded on-demand (lazy loading) so the API doesn't run out of memory with huge sessions.

### Visualization (Frontend)
The SvelteKit frontend runs in your browser. It fetches data from the API and renders interactive pages. Charts, tables, timelines — all powered by Chart.js and Tailwind CSS. Svelte 5 runes make the UI reactive.

### Real-Time Tracking (Hooks)
Claude Code executes hook scripts when sessions start, end, receive input, or run tools. Our hooks write state to `~/.claude_karma/live-sessions/`. The API reads these state files to tell the dashboard what's currently happening.

### Session Sync (CLI + Syncthing)
The `karma` CLI watches your projects for new sessions, packages them into a standard format, and tells Syncthing to sync them. Syncthing handles all the network communication.

## Repository structure

```
claude-code-karma/
├── api/                    # FastAPI backend
│   ├── main.py            # Server entry point
│   ├── models/            # Pydantic models for JSONL parsing
│   ├── routers/           # API route handlers
│   ├── db/                # SQLite schema and queries
│   └── tests/             # Pytest tests
├── frontend/              # SvelteKit web app
│   ├── src/routes/        # Pages and routes
│   ├── src/lib/           # Shared components and utilities
│   └── package.json
├── cli/karma/             # Karma CLI package
│   ├── main.py            # CLI entry point
│   ├── config.py          # Configuration loading
│   ├── syncthing.py       # Syncthing API client
│   ├── packager.py        # Session packaging
│   ├── watcher.py         # File watcher
│   └── tests/
├── hooks/                 # Production hook scripts
│   ├── live_session_tracker.py
│   ├── session_title_generator.py
│   └── plan_approval.py       # Reference only (not production)
├── captain-hook/          # Pydantic models for hooks
│   ├── captain_hook/      # Library source
│   └── tests/
└── docs/                  # Documentation
```

This is a monorepo — all code is in one git repository. The API, frontend, CLI, and hooks are independent and can be developed/deployed separately.

## Claude Code storage locations

The API reads from these locations:

| Data | Location |
|------|----------|
| Session files | `~/.claude/projects/{encoded-path}/{uuid}.jsonl` |
| Subagent sessions | `~/.claude/projects/{encoded-path}/{uuid}/subagents/agent-*.jsonl` |
| Tool outputs | `~/.claude/projects/{encoded-path}/{uuid}/tool-results/toolu_*.txt` |
| Debug logs | `~/.claude/debug/{uuid}.txt` |
| Live session state | `~/.claude_karma/live-sessions/{slug}.json` |
| Remote sessions | `~/.claude_karma/remote-sessions/{user-id}/{encoded-path}/` |
| Sync configuration | `~/.claude_karma/sync-config.json` |
| SQLite metadata | `~/.claude_karma/metadata.db` |

## API model hierarchy

All data is structured with Pydantic models. Here's the hierarchy:

```
Project
├── Session (one per JSONL file)
│   ├── Messages (UserMessage, AssistantMessage, FileHistorySnapshot, SummaryMessage)
│   ├── Subagents (spawned Task agents)
│   ├── ToolResults (large tool outputs)
│   └── TodoItems
└── Subagents (standalone agent-*.jsonl files)
```

All models are immutable (frozen) once created. This prevents bugs and makes caching safe.

## API endpoints

All endpoints are on the API server at `http://localhost:8000`.

**Projects:**
- `GET /projects` — List all projects
- `GET /projects/{name}` — Project details with all sessions

**Sessions:**
- `GET /sessions/{uuid}` — Session details
- `GET /sessions/{uuid}/timeline` — Event timeline
- `GET /sessions/{uuid}/tools` — Tool usage
- `GET /sessions/{uuid}/file-activity` — Files changed
- `GET /sessions/{uuid}/subagents` — Subagent activity

**Analytics:**
- `GET /analytics/projects/{name}` — Project analytics
- `GET /agents` — Agent stats
- `GET /skills` — Skill usage
- `GET /tools` — MCP tool discovery

**Real-Time:**
- `GET /live-sessions` — Current session state (requires hooks)

**Sync:**
- `GET /sync/status` — Sync config, member tag, Syncthing status
- `GET /sync/detect` — Check if Syncthing is installed/running
- `POST /sync/init` — Initialize sync setup
- `GET /sync/teams` — List all teams
- `GET /sync/teams/{name}` — Team detail with members, projects, subscriptions
- `POST /sync/teams` — Create a team
- `POST /sync/teams/{name}/members` — Add member via pairing code
- `POST /sync/teams/{name}/projects` — Share a project
- `POST /sync/subscriptions/{team}/{git_identity}/accept` — Accept a subscription
- `GET /sync/pending-devices` — Pending Syncthing device requests
- `GET /sync/pending` — Pending folder offers from peers
- `GET /users` — List remote users
- `GET /users/{user}/projects` — Remote projects

**Misc:**
- `GET /history` — File history across sessions
- `GET /plans` — Plan browsing
- `GET /hooks` — Hook status

See [API Reference](api-reference.md) for complete documentation.

## Path encoding

Claude Code stores projects in directories with paths like `/Users/me/my-project`. These are encoded as directory names: `-Users-me-my-project`. The encoding:
- Replaces the leading `/` with `-`
- Replaces all other `/` with `-`

The API decodes these back to readable names in the dashboard.

## Tech stack details

### Backend
- **FastAPI** — Async web framework with automatic docs
- **Pydantic 2.x** — Data validation and serialization (all models frozen)
- **aiofiles** — Non-blocking file I/O
- **SQLite** — Session metadata and indexing
- **pytest** — Testing

### Frontend
- **SvelteKit 2** — Full-stack framework
- **Svelte 5** — UI with runes for reactivity
- **Tailwind CSS 4** — Styling
- **Chart.js 4** — Data visualizations
- **bits-ui** — Accessible UI primitives
- **TypeScript** — Type safety

### CLI
- **Click** — CLI framework
- **Pydantic** — Config models
- **requests** — HTTP client
- **watchdog** — File watching
- **requests-auth** — Syncthing API authentication

## Key design patterns

### Lazy Loading
Session messages aren't loaded all at once. The API uses a generator that reads JSONL lines on-demand. This keeps memory constant no matter how large the session is.

### Frozen Models
All Pydantic models use `frozen=True`. Once created, they can't be changed. This prevents bugs and makes caching safe.

### Session Chains
When a session is resumed, the new session references the old one. The API detects these chains and links them so you can see the full history of a task.

### Async I/O
The API uses `aiofiles` for non-blocking file reads. This prevents parsing one session from blocking requests for other data.

### SQLite Indexing
Session metadata is indexed in SQLite for fast queries. The API keeps the index in sync with the filesystem via background scanning.

## Live session state

Hooks write state to `~/.claude_karma/live-sessions/{slug}.json`. Example:

```json
{
  "session_id": "abc-123-def",
  "project": "/Users/me/repo",
  "status": "LIVE",
  "started_at": "2026-03-09T10:00:00Z",
  "last_activity": "2026-03-09T10:15:00Z",
  "message_count": 5,
  "tool_calls": 3
}
```

The API reads these files and merges them with historical data to show both current state and history.

## Session packaging for sync

When sessions are synced via Syncthing, they're packaged into this structure:

```
~/.claude_karma/remote-sessions/
├── alice/
│   └── -Users-alice-work-acme-app/
│       ├── manifest.json
│       └── sessions/
│           ├── uuid1.jsonl
│           ├── uuid1/subagents/agent-*.jsonl
│           ├── uuid1/tool-results/toolu_*.txt
│           └── uuid2.jsonl
```

The `manifest.json` contains metadata:

```json
{
  "version": 1,
  "user_id": "alice",
  "machine_id": "alice-macbook",
  "project_path": "/Users/alice/work/acme-app",
  "synced_at": "2026-03-09T14:30:00Z",
  "session_count": 5,
  "sync_backend": "syncthing",
  "sessions": [
    {
      "uuid": "abc-123-def",
      "mtime": "2026-03-09T14:20:00Z",
      "size_bytes": 45000
    }
  ]
}
```

The API reads this same format on every machine, regardless of how sessions arrived.
