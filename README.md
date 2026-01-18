# Claude Karma

A full-stack application for monitoring and analyzing Claude Code sessions. Parses Claude Code's local storage (`~/.claude/`) and visualizes session data through a web dashboard.

## Features

- **Session Browser** — View all projects and sessions with token usage, costs, and metadata
- **Timeline View** — Chronological event timeline for each session (messages, tool calls, subagents)
- **Live Sessions** — Real-time session status tracking via Claude Code hooks
- **Analytics** — Project-level and global usage analytics
- **Subagent Tracking** — Monitor spawned agents and their activity

## Project Structure

This is a monorepo with three git submodules:

```
claude-karma/
├── api/                    # FastAPI backend (Python) - port 8000
├── frontend/               # SvelteKit frontend (Svelte 5) - port 5173
└── captain-hook/           # Claude Code hooks Pydantic library
```

## Quick Start

```bash
# Clone with submodules
git clone --recursive https://github.com/JayantDevkar/claude-karma.git
cd claude-karma

# Start API (Terminal 1)
cd api
pip install -r requirements.txt
uvicorn main:app --reload --port 8000

# Start Frontend (Terminal 2)
cd frontend
npm install
npm run dev
```

Open http://localhost:5173 to view the dashboard.

See [SETUP.md](./SETUP.md) for detailed setup instructions including live session tracking.

## Architecture

```
~/.claude/projects/{encoded-path}/{uuid}.jsonl
    ↓
API (models/ parses JSONL → Pydantic models)
    ↓
FastAPI endpoints (routers/)
    ↓
SvelteKit frontend (src/routes/)
```

### Submodules

| Submodule | Description | Repository |
|-----------|-------------|------------|
| `api/` | FastAPI backend with Pydantic models for parsing Claude Code storage | [dot-claude-files-parser](https://github.com/JayantDevkar/dot-claude-files-parser) |
| `frontend/` | SvelteKit + Svelte 5 web dashboard | [ClaudeDashboard](https://github.com/the-non-expert/ClaudeDashboard) |
| `captain-hook/` | Type-safe Pydantic models for all 10 Claude Code hook types | [captain-hook](https://github.com/JayantDevkar/captain-hook) |

## API Endpoints

| Endpoint | Description |
|----------|-------------|
| `GET /projects` | List all projects |
| `GET /projects/{encoded_name}` | Project details with sessions |
| `GET /sessions/{uuid}` | Session details |
| `GET /sessions/{uuid}/timeline` | Session event timeline |
| `GET /sessions/{uuid}/tools` | Tool usage breakdown |
| `GET /live-sessions/active` | Currently active sessions |
| `GET /analytics/projects/{name}` | Project analytics |

## Live Session Tracking

Enable real-time session monitoring by installing Claude Code hooks. See [SETUP.md](./SETUP.md#live-sessions-tracking-optional) for configuration.

| State | Meaning |
|-------|---------|
| `LIVE` | Session actively running |
| `WAITING` | Waiting for user input |
| `STOPPED` | Agent finished, session open |
| `STALE` | User idle 60+ seconds |
| `ENDED` | Session terminated |

## License

MIT
