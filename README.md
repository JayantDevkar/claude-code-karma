# Claude Karma

[![License: Apache-2.0](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](https://www.apache.org/licenses/LICENSE-2.0)
[![Python 3.9+](https://img.shields.io/badge/Python-3.9+-blue.svg)](https://www.python.org/)
[![Node 18+](https://img.shields.io/badge/Node-18+-green.svg)](https://nodejs.org/)
[![SvelteKit 2](https://img.shields.io/badge/SvelteKit-2-FF3E00.svg)](https://kit.svelte.dev/)

A full-stack application for monitoring and analyzing Claude Code sessions. Parses Claude Code's local storage (`~/.claude/`) and visualizes session data through a web dashboard.

## Features

- **Session Browser** — View all projects and sessions with token usage, costs, and metadata
- **Timeline View** — Chronological event timeline for each session (messages, tool calls, subagents)
- **Live Sessions** — Real-time session status tracking via Claude Code hooks
- **Analytics** — Project-level and global usage analytics with trends
- **Subagent Tracking** — Monitor spawned agents and their activity
- **Tool Usage** — Analyze which tools are most frequently used
- **Agent & Skill Analytics** — Track agent performance and skill adoption
- **Hooks Browser** — View available Claude Code hooks and their schemas
- **Plugins Browser** — Explore installed plugins
- **Plans Browser** — Monitor plans and their execution status
- **Command Palette** — Quick navigation with Ctrl+K
- **Session Search** — Full-text search across all sessions
- **File History** — Track file changes across sessions
- **Archived Sessions** — View historical session data

## Project Structure

This is a true monorepo (no git submodules) with all components in a single repository:

```
claude-karma/
├── api/                    # FastAPI backend (Python) - port 8000
│   ├── models/            # Pydantic models for Claude Code data
│   ├── routers/           # API endpoints
│   ├── db/                # SQLite database
│   └── config.py          # Configuration
├── frontend/              # SvelteKit frontend (Svelte 5) - port 5173
│   ├── src/routes/        # Frontend pages
│   ├── src/lib/           # Components and utilities
│   └── tailwind.config.js # Tailwind configuration
├── captain-hook/          # Pydantic library for Claude Code hooks
│   └── captain_hook/      # Hook type definitions
└── hooks/                 # Hook scripts (symlinked to ~/.claude/hooks/)
    ├── live_session_tracker.py
    ├── session_title_generator.py
    └── plan_approval.py
```

## Quick Start

### Prerequisites

Verify you have the required tools:

```bash
python3 --version    # 3.9+
node --version       # 18+
npm --version        # 7+
git --version        # any version
```

### Installation

```bash
# Clone the repository
git clone https://github.com/JayantDevkar/claude-karma.git
cd claude-karma

# Start API (Terminal 1)
cd api
pip install -e ".[dev]"
pip install -r requirements.txt
uvicorn main:app --reload --port 8000

# Start Frontend (Terminal 2)
cd frontend
npm install
npm run dev
```

Open http://localhost:5173 to view the dashboard.

For detailed setup instructions including live session tracking, see [SETUP.md](./SETUP.md).

## Architecture

```
~/.claude/projects/{encoded-path}/{uuid}.jsonl
    ↓
API (models/ parses JSONL → Pydantic models)
    ↓
FastAPI endpoints (routers/) on port 8000
    ↓
SvelteKit frontend (src/routes/) on port 5173
```

### Data Flow

The application reads Claude Code's local storage and presents it through an interactive dashboard:

1. **Storage** — Claude Code writes session data to `~/.claude/projects/`
2. **Parsing** — API parses JSONL files into Pydantic models
3. **Database** — Metadata indexed in SQLite at `~/.claude_karma/metadata.db`
4. **API** — FastAPI serves endpoints for querying session data
5. **Frontend** — SvelteKit renders interactive visualizations

## API Endpoints

### Core Endpoints

| Endpoint | Description |
|----------|-------------|
| `GET /projects` | List all projects |
| `GET /projects/{encoded_name}` | Project details with sessions |
| `GET /sessions/{uuid}` | Session details |
| `GET /sessions/{uuid}/timeline` | Session event timeline |
| `GET /sessions/{uuid}/tools` | Tool usage breakdown |
| `GET /sessions/{uuid}/file-activity` | File operations |
| `GET /sessions/{uuid}/subagents` | Subagent activity |

### Analytics Endpoints

| Endpoint | Description |
|----------|-------------|
| `GET /analytics/projects/{encoded_name}` | Project analytics |
| `GET /analytics/dashboard` | Global dashboard metrics |

### Agents & Skills

| Endpoint | Description |
|----------|-------------|
| `GET /agents` | List all agents |
| `GET /agents/{name}` | Agent details |
| `GET /agents/usage` | Agent usage statistics |
| `GET /skills` | List all skills |

### Live Sessions

| Endpoint | Description |
|----------|-------------|
| `GET /live-sessions` | Real-time session state |

See [SETUP.md](./SETUP.md#live-sessions-tracking-optional) to enable live session tracking.

## Live Session Tracking

Enable real-time session monitoring by installing Claude Code hooks. Session states indicate the current status:

| State | Meaning |
|-------|---------|
| `LIVE` | Session actively running |
| `WAITING` | Waiting for user input |
| `STOPPED` | Agent finished, session open |
| `STALE` | User idle 60+ seconds |
| `ENDED` | Session terminated |

## Technology Stack

### Backend
- **Python 3.9+** — Runtime
- **FastAPI** — Web framework
- **Pydantic 2.x** — Data validation
- **SQLite** — Metadata database
- **pytest** — Testing framework
- **ruff** — Linting and formatting

### Frontend
- **SvelteKit 2** — Meta-framework
- **Svelte 5** — UI framework with runes
- **Tailwind CSS 4** — Styling
- **Chart.js 4** — Visualizations
- **bits-ui** — Accessible UI primitives
- **TypeScript** — Type safety

### Libraries
- **captain-hook** — Type-safe Pydantic models for Claude Code's 10 hook types

## Contributing

Contributions are welcome! Please see [CONTRIBUTING.md](./CONTRIBUTING.md) for guidelines on:

- Reporting bugs
- Suggesting features
- Development setup
- Code style
- Testing
- Pull request process

## License

This project is licensed under the Apache License 2.0. See [LICENSE](./LICENSE) for details.

## Questions?

- See [SETUP.md](./SETUP.md) for installation and configuration help
- Check [CLAUDE.md](./CLAUDE.md) for development guidance (Claude Code specific)
- Review existing [GitHub Issues](https://github.com/JayantDevkar/claude-karma/issues)

---

Built and maintained by [Jayant Devkar](https://github.com/JayantDevkar)
