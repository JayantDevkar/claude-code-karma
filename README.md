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
  <a href="https://www.python.org/"><img src="https://img.shields.io/badge/Python-3.10+-blue.svg" alt="Python 3.10+" /></a>
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

> **Warning: Claude Code only keeps session data for about 30 days.** Older JSONL files in `~/.claude/projects/` are automatically cleaned up. Since Karma reads directly from those files, deleted sessions will disappear from the dashboard too.

Claude Code Karma reads that local data and gives you a proper dashboard. No cloud. No accounts. No telemetry. Just your data, on your machine.

It works with both **Claude Code CLI** and **Claude Desktop** (Claude Code mode) sessions — any session that writes to `~/.claude/` shows up automatically.

## Features

### Session Browser

Browse all your Claude Code sessions in one place. Search by title, prompt, or slug. Filter by project. See live sessions at the top with real-time status badges — and a `>_` button that raises the terminal window a live session is running in.

<p align="center">
  <img src="docs/screenshots/sessions.png" alt="Session Browser" width="100%" />
</p>

### Session Timeline & Overview

Dive into any session to see exactly what happened — every prompt, tool call, thinking block, and response laid out chronologically. The overview tab shows key stats like message count, duration, model used, and which tools were called.

<p align="center">
  <img src="docs/screenshots/session-overview.png" alt="Session Overview" width="100%" />
</p>

<p align="center">
  <img src="docs/screenshots/session-timeline.png" alt="Session Timeline" width="100%" />
</p>

### Session Detail Tabs

Each session page has dedicated tabs that break down different aspects of what happened during the session.

**Tasks** — See all tasks Claude created and completed during the session, displayed in a flow view with status tracking.

<p align="center">
  <img src="docs/screenshots/session-tasks.png" alt="Session Tasks" width="100%" />
</p>

**Files** — Every file operation in a sortable table — reads, writes, edits — with timestamps, actors, and the tools that made each change.

<p align="center">
  <img src="docs/screenshots/session-files.png" alt="Session Files" width="100%" />
</p>

**Subagents** — Agents spawned during the session, grouped by type. Expand each to see message counts, tool calls, and what they were asked to do.

<p align="center">
  <img src="docs/screenshots/session-subagents.png" alt="Session Subagents" width="100%" />
</p>

**Skills** — Skills invoked via `/skill` commands during the session, with their source plugin and invocation count.

<p align="center">
  <img src="docs/screenshots/session-skills.png" alt="Session Skills" width="100%" />
</p>

**Shells** — Long-running background shells spawned during the session, with live status, the command each one ran, and runtime.

<p align="center">
  <img src="docs/screenshots/session-shells.png" alt="Session Shells" width="100%" />
</p>

**Analytics** — Per-session cost breakdown, token usage, cache hit rates, tool distribution with a donut chart, and a ranked list of every tool used.

<p align="center">
  <img src="docs/screenshots/session-analytics.png" alt="Session Analytics" width="100%" />
</p>

### Projects

See all your Claude Code workspaces organized by git repository. Each project card shows session count and when it was last active. Expand git repos to see individual project directories inside them.

<p align="center">
  <img src="docs/screenshots/projects.png" alt="Projects" width="100%" />
</p>

### Analytics

Track your token usage, costs, velocity trends, cache hit rates, and coding rhythm across all projects. See which models you use most and how your usage patterns change over time.

<p align="center">
  <img src="docs/screenshots/analytics.png" alt="Analytics Dashboard" width="100%" />
</p>

### Tools & MCP

See every tool Claude Code uses — built-in ones like Read, Edit, and Bash, plus any MCP integrations you've added (the **MCP** page in the nav). Grouped by server with call counts and session coverage. Switch to the Usage Analytics tab for activity trends and top tools over time.

<p align="center">
  <img src="docs/screenshots/tools.png" alt="Tools Browser" width="100%" />
</p>

<p align="center">
  <img src="docs/screenshots/tool-analytics.png" alt="Tool Usage Analytics" width="100%" />
</p>

Click into any tool for detailed stats — total calls, session count, main vs subagent split, usage trend over time, and a full session history.

<p align="center">
  <img src="docs/screenshots/tool-detail.png" alt="Tool Detail" width="100%" />
</p>

<p align="center">
  <img src="docs/screenshots/tool-history.png" alt="Tool History" width="100%" />
</p>

### Agents

Browse all your agents — built-in, custom, and plugin-provided. See total runs, token consumption, and filter by category to understand how your agent ecosystem is being used. The Usage Analytics view shows activity trends and your most-used agents.

<p align="center">
  <img src="docs/screenshots/agents.png" alt="Agents Browser" width="100%" />
</p>

<p align="center">
  <img src="docs/screenshots/agent-analytics.png" alt="Agent Usage Analytics" width="100%" />
</p>

Drill into any agent for run counts, token usage, average duration, usage trends, project breakdown, and a session history showing every time that agent was used.

<p align="center">
  <img src="docs/screenshots/agent-detail.png" alt="Agent Detail" width="100%" />
</p>

<p align="center">
  <img src="docs/screenshots/agent-history.png" alt="Agent History" width="100%" />
</p>

### Hooks

Visualize all your Claude Code hooks organized by lifecycle phase — session start/end, tool use, agent lifecycle, and permissions. See which hooks can block execution and how many registrations each event has.

<p align="center">
  <img src="docs/screenshots/hooks.png" alt="Hooks Browser" width="100%" />
</p>

### Plugins

View all installed Claude Code plugins with their agents, skills, and commands. Filter between official and community plugins. See version info and when each was last updated.

<p align="center">
  <img src="docs/screenshots/plugins.png" alt="Plugins Browser" width="100%" />
</p>

Click into any plugin to see everything it provides — agents, skills, commands, MCP tools, and hooks — along with usage analytics showing activity trends and top-used components.

<p align="center">
  <img src="docs/screenshots/plugin-detail.png" alt="Plugin Detail" width="100%" />
</p>

<p align="center">
  <img src="docs/screenshots/plugin-analytics.png" alt="Plugin Usage Analytics" width="100%" />
</p>

### Skills

Track which skills are invoked across sessions, grouped by plugin or shown individually. Click into any skill for usage stats, context split (main vs subagent), and a full session history showing every time that skill was used.

<p align="center">
  <img src="docs/screenshots/skill-detail.png" alt="Skill Detail with History" width="100%" />
</p>

### Ticket Linking (Linear / Jira / GitHub Issues)

Attach your Claude Code sessions to the tickets they were about. Karma stays read-only — it stores the link and caches the title/status, but never writes back to your ticket provider.

Three ways to link:

- **Paste a URL or key** into the Tickets section on any session page
- **Type `/link-ticket-to-session ABC-123`** (or ask the agent in natural language) in any Claude Code session — uses your Linear / Atlassian / GitHub MCP server to fetch the title
- **Auto-detect from your branch name** — opt-in `SessionStart` hook that watches for keys like `feat/LINEAR-123-foo` and links silently in the background

Then browse:

- A `/tickets` index showing every ticket touched, filterable by provider and project
- A ticket detail page listing every session linked to a given ticket
- A **Tickets tab on every project page** that aggregates across all checkouts of the same git repo — so a ticket linked from `claude-karma/frontend/` also shows on the main `claude-karma` project

**Tickets Index** — All linked tickets in a filterable table. Switch between All, Issues, and PRs on GitHub.

<p align="center">
  <img src="docs/screenshots/tickets-index.png" alt="Tickets Index" width="100%" />
</p>

**Filter by Provider** — GitHub shows sub-pill filtering ([All N] [Issues N] [PRs N]) to toggle between categories.

<p align="center">
  <img src="docs/screenshots/tickets-github-prs.png" alt="GitHub Issues and PRs Filter" width="100%" />
</p>

**Ticket Detail** — View a ticket with all linked sessions. Cross-project rollup shows "N sessions · M projects" with tabs per project.

<p align="center">
  <img src="docs/screenshots/ticket-detail.png" alt="Ticket Detail with Cross-Project Rollup" width="100%" />
</p>

**Project Tickets Tab** — Every project page has a Tickets tab that aggregates across all git identity checkouts, so the same ticket appears even if linked from different branch directories.

<p align="center">
  <img src="docs/screenshots/project-tickets-tab.png" alt="Project Tickets Tab" width="100%" />
</p>

### And More

- **Tickets across providers** — Link sessions to Linear, Jira, and GitHub Issues in a unified interface
- **Plans Browser** — View implementation plans and their execution status
- **Command Palette** — Quick navigation with `Ctrl+K` / `Cmd+K`
- **Full-text Search** — Search across session titles, prompts, and slugs
- **Live Sessions** — Real-time monitoring via Claude Code hooks
- **Open Terminal** — One click brings the terminal running a live session to the front (exact tab for macOS Terminal/iTerm2, exact pane in tmux)

## Quick Start

```bash
# Clone the repository
git clone https://github.com/JayantDevkar/claude-code-karma.git
cd claude-code-karma

# Start API (Terminal 1)
cd api
pip install -e ".[dev]" && pip install -r requirements.txt
uvicorn main:app --reload --port 8020

# Start Frontend (Terminal 2)
cd frontend
npm install && npm run dev
```

Open **http://localhost:5180** to view the dashboard.

**This only gets you the historical dashboard.** Karma's core feature — live session tracking as sessions actually run — needs one more step, [Tier 2 in SETUP.md](./SETUP.md#tier-2-live-monitoring-core-feature). Install through Tier 2 by default; the rest of SETUP.md's tiers are optional polish on top.

## Desktop App (macOS & Windows)

Two terminals every time gets old. Install a desktop icon that starts both servers for you and opens the dashboard:

```bash
python3 scripts/install_karma_app.py           # macOS: /Applications/Karma.app
                                               # Windows: a Desktop shortcut
python3 scripts/install_karma_app.py --dock    # macOS: also pin it to the Dock
python3 scripts/install_karma_app.py --uninstall
```

Click the icon and Karma starts whichever servers aren't already running, then opens the dashboard. The first launch after a reboot has to compile the frontend (a minute or two), so it posts a "Starting Karma…" desktop notification straight away — the click never looks like it did nothing — and opens the dashboard once the servers answer.

Nothing is hardcoded: the installer works out your repo location from its own path and finds a Python interpreter on the machine, so a clone anywhere works.

**Optional: start at login.** Toggle it in **Settings → Desktop App**, or:

```bash
python3 scripts/install_karma_app.py --autostart      # on
python3 scripts/install_karma_app.py --no-autostart   # off
```

This adds a launchd agent (macOS) or a Startup-folder entry (Windows) so the servers are already up when you log in — the dashboard is simply always there, with no icon to click first. It costs roughly **150–350 MB** of memory and almost no CPU while idle.

It's also what makes a browser-installed Karma work on its own: a PWA is only a window and cannot start servers, so with autostart you never need the launcher icon at all.

macOS notifies you that a background item was added and lists it under **System Settings → General → Login Items**; Windows shows it in **Task Manager → Startup**. Karma reads that state back from disk, so turning it off there is reflected in the dashboard too.

> **Windows notes.** SmartScreen may warn the first time, and Windows will show a firewall prompt when the servers first bind their ports — allow it for private networks. The shortcut runs via `pythonw.exe`, so no console window flashes.

## How It Works

Claude Code already saves everything locally — sessions, tool calls, token counts — as JSONL files in `~/.claude/`. Claude Code Karma simply reads those files and serves them through a local dashboard.

```
~/.claude/projects/  →  FastAPI (port 8020)  →  SvelteKit (port 5180)
   your data              parses & serves          visualizes it
```

Nothing leaves your machine. The API reads your local files, indexes metadata in a local SQLite database, and the frontend renders it all in the browser.

## Project Structure

```
claude-code-karma/
├── api/                    # FastAPI backend (Python) — port 8020
│   ├── models/             # Pydantic models for Claude Code data
│   ├── routers/            # API endpoints
│   └── services/           # Business logic
├── frontend/               # SvelteKit frontend (Svelte 5) — port 5180
│   ├── src/routes/         # Pages
│   └── src/lib/            # Components and utilities
├── captain-hook/           # Pydantic library for Claude Code hooks
└── hooks/                  # Hook scripts (symlinked to ~/.claude/hooks/)
    ├── live_session_tracker.py
    ├── session_title_generator.py
    └── plan_approval.py
```

## Live Session Tracking

This is Karma's core feature — without it, Karma is just a historical viewer. Enable real-time session monitoring by installing Claude Code hooks. See [Tier 2 in SETUP.md](./SETUP.md#tier-2-live-monitoring-core-feature) for setup instructions.

Live sessions also get an **"open terminal"** button (on the session page, the home strip, and `/sessions`) that raises the terminal window the session is running in — Karma runs locally, so the API can ask the OS window manager directly. macOS Terminal.app and iTerm2 get the exact window/tab, tmux gets the exact pane, other macOS terminals are raised app-level, and Linux needs X11 with `xdotool` or `wmctrl`. Design details in [docs/feature/open-terminal/spec.md](./docs/feature/open-terminal/spec.md).

| State | Meaning |
|-------|---------|
| `LIVE` | Session actively running |
| `WAITING` | Waiting for user input |
| `STOPPED` | Agent finished, session open |
| `STALE` | User idle 60+ seconds |
| `ENDED` | Session terminated |

## Technology Stack

### Backend
- **Python 3.10+** with **FastAPI** and **Pydantic 2.x**
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
| `POST /live-sessions/{id}/focus-terminal` | Raise the session's terminal window |

### Tickets

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/sessions/{uuid}/tickets` | Link a ticket to a session |
| `GET` | `/sessions/{uuid}/tickets` | List tickets linked to a session |
| `DELETE` | `/sessions/{uuid}/tickets/{id}` | Unlink a ticket from a session |
| `GET` | `/tickets` | List all tickets (filters: provider, project, q) |
| `GET` | `/tickets/{provider}/{key}` | Get ticket details |
| `GET` | `/tickets/{provider}/{key}/sessions` | Sessions linked to a ticket |
| `PUT` | `/tickets/{provider}/{key}` | Refresh metadata from MCP |
| `POST` | `/admin/repair-github-urls` | Repair stale `/issues/` URLs to `/pull/` |

### System Cron

| Endpoint | Description |
|----------|-------------|
| `GET /cron/system` | Host OS crontab (user crontab, `/etc/crontab`, `/etc/cron.d/*`, run-parts), grouped by origin |

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
