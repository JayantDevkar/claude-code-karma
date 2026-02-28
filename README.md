<p align="center">
  <img src="docs/screenshots/banner.png" alt="Claude Code Karma" width="200" />
</p>

<h1 align="center">Claude Code Karma</h1>

<p align="center">
  <strong>Your Claude Code sessions deserve more than a terminal.</strong><br />
  A local-first, open-source dashboard that turns your <code>~/.claude/</code> data into a visual story — sessions, timelines, costs, and live activity, all on your machine.
</p>

<p align="center">
  <a href="https://www.apache.org/licenses/LICENSE-2.0"><img src="https://img.shields.io/badge/License-Apache%202.0-blue.svg" alt="License: Apache-2.0" /></a>
  <a href="https://www.python.org/"><img src="https://img.shields.io/badge/Python-3.9+-blue.svg" alt="Python 3.9+" /></a>
  <a href="https://nodejs.org/"><img src="https://img.shields.io/badge/Node-18+-green.svg" alt="Node 18+" /></a>
  <a href="https://kit.svelte.dev/"><img src="https://img.shields.io/badge/SvelteKit-2-FF3E00.svg" alt="SvelteKit 2" /></a>
</p>

<br />

<p align="center">
  <a href="docs/screenshots/home.png" target="_blank">
    <img src="docs/screenshots/home.png" alt="Claude Code Karma Dashboard" width="100%" />
  </a>
</p>

## Why Claude Code Karma?

If you use Claude Code, you already have a goldmine of data sitting in `~/.claude/` — every session, every tool call, every token. But it's all buried in JSONL files you'll never read.

> **⚠️ Important: Claude Code only retains session data for the last ~30 days by default.** Older JSONL files in `~/.claude/projects/` are automatically cleaned up by Claude Code. Since Claude Code Karma reads directly from those files, any sessions that Claude Code deletes will also disappear from the dashboard. There is currently no built-in way to preserve historical data beyond this retention window.

Claude Code Karma reads that local data and gives you a proper dashboard. No cloud. No accounts. No telemetry. Just your data, on your machine.

## Features

- **Session Browser** — Browse all sessions across projects with live status, search, and filters
- **Timeline View** — Chronological event timeline showing tool calls, thinking blocks, and responses
- **Live Sessions** — Real-time session monitoring via Claude Code hooks
- **Analytics** — Token usage, costs, velocity trends, cache hit rates, and coding rhythm
- **Subagent Tracking** — Monitor spawned agents and their activity within sessions
- **Tool & Skill Analytics** — Track which tools and skills are most used
- **Plans Browser** — View implementation plans and their execution status
- **Hooks & Plugins** — Browse installed Claude Code hooks and MCP plugins
- **Command Palette** — Quick navigation with `Ctrl+K` / `Cmd+K`
- **Full-text Search** — Search across session titles, prompts, and slugs

## Quick Start

```bash
# Clone the repository
git clone https://github.com/JayantDevkar/claude-code-karma.git
cd claude-code-karma

# Start API (Terminal 1)
cd api
pip install -e ".[dev]" && pip install -r requirements.txt
uvicorn main:app --reload --port 8000

# Start Frontend (Terminal 2)
cd frontend
npm install && npm run dev
```

Open **http://localhost:5173** to view the dashboard.

For detailed setup including live session tracking, see [SETUP.md](./SETUP.md).

## How It Works

Claude Code already saves everything locally — sessions, tool calls, token counts — as JSONL files in `~/.claude/`. Claude Code Karma simply reads those files and serves them through a local dashboard.

```
~/.claude/projects/  →  FastAPI (port 8000)  →  SvelteKit (port 5173)
   your data              parses & serves          visualizes it
```

Nothing leaves your machine. The API reads your local files, indexes metadata in a local SQLite database, and the frontend renders it all in the browser.

## Project Structure

```
claude-code-karma/
├── api/                    # FastAPI backend (Python) — port 8000
│   ├── models/             # Pydantic models for Claude Code data
│   ├── routers/            # API endpoints
│   └── services/           # Business logic
├── frontend/               # SvelteKit frontend (Svelte 5) — port 5173
│   ├── src/routes/         # Pages
│   └── src/lib/            # Components and utilities
├── captain-hook/           # Pydantic library for Claude Code hooks
└── hooks/                  # Hook scripts (symlinked to ~/.claude/hooks/)
    ├── live_session_tracker.py
    ├── session_title_generator.py
    └── plan_approval.py
```

## Live Session Tracking

Enable real-time session monitoring by installing Claude Code hooks. See [SETUP.md](./SETUP.md#live-sessions-tracking-optional) for setup instructions.

| State | Meaning |
|-------|---------|
| `LIVE` | Session actively running |
| `WAITING` | Waiting for user input |
| `STOPPED` | Agent finished, session open |
| `STALE` | User idle 60+ seconds |
| `ENDED` | Session terminated |

## Technology Stack

### Backend
- **Python 3.9+** with **FastAPI** and **Pydantic 2.x**
- **SQLite** for metadata indexing
- **pytest** for testing, **ruff** for linting

### Frontend
- **SvelteKit 2** with **Svelte 5** runes
- **Tailwind CSS 4** for styling
- **Chart.js 4** for visualizations
- **bits-ui** for accessible UI primitives
- **TypeScript** for type safety

### Libraries
- **captain-hook** — Type-safe Pydantic models for Claude Code's 10 hook types

## API Endpoints

<details>
<summary>View all endpoints</summary>

### Core

| Endpoint | Description |
|----------|-------------|
| `GET /projects` | List all projects |
| `GET /projects/{encoded_name}` | Project details with sessions |
| `GET /sessions/{uuid}` | Session details |
| `GET /sessions/{uuid}/timeline` | Session event timeline |
| `GET /sessions/{uuid}/tools` | Tool usage breakdown |
| `GET /sessions/{uuid}/file-activity` | File operations |
| `GET /sessions/{uuid}/subagents` | Subagent activity |

### Analytics

| Endpoint | Description |
|----------|-------------|
| `GET /analytics/projects/{encoded_name}` | Project analytics |
| `GET /analytics/dashboard` | Global dashboard metrics |

### Agents, Skills & Live Sessions

| Endpoint | Description |
|----------|-------------|
| `GET /agents` | List all agents |
| `GET /agents/{name}` | Agent details |
| `GET /skills` | List all skills |
| `GET /live-sessions` | Real-time session state |

</details>

## Contributing

Contributions are welcome! Please see [CONTRIBUTING.md](./CONTRIBUTING.md) for guidelines on:

- Reporting bugs
- Suggesting features
- Development setup
- Code style and testing
- Pull request process

## License

This project is licensed under the Apache License 2.0. See [LICENSE](./LICENSE) for details.

## Questions?

- See [SETUP.md](./SETUP.md) for installation and configuration help
- Check [CLAUDE.md](./CLAUDE.md) for development guidance
- Review existing [GitHub Issues](https://github.com/JayantDevkar/claude-code-karma/issues)

---

Built and maintained by [Jayant Devkar](https://github.com/JayantDevkar)
