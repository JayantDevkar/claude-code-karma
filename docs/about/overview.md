# Claude Code Karma

Claude Code Karma is a dashboard for understanding what Claude Code has done on your machine. It reads the session files Claude Code stores locally and shows you everything in a web dashboard.

## The problem

Claude Code creates JSONL files with all your session data in `~/.claude/projects/`. These files contain everything — conversations, tool calls, files modified, tokens used — but Claude Code itself doesn't show them to you.

Karma makes this visible. You can browse sessions, see token usage, watch tools being called, replay conversations, and more. If you work in a team, you can also share sessions with freelancers across machines.

## What you can do

**Browse your work:**
- See all sessions across all projects
- Search and filter by project, date, or keywords
- Understand how long sessions took and how many tokens they used

**Analyze patterns:**
- Track token usage and costs over time
- See which tools Claude Code uses most
- Find which files change most frequently

**Watch sessions happen:**
- With hooks installed, see live session state (waiting, processing, done)
- Get automatic titles for sessions based on git commits or AI generation

**Share with your team:**
- Add freelancers to teams
- They sync their sessions via Syncthing (peer-to-peer)
- You see everything in one unified dashboard
- Leave feedback on work that syncs back to them

## Who is this for

- Power users who run Claude Code every day and want visibility into what happened
- Teams evaluating Claude Code and needing usage metrics
- Project owners managing freelancers on multiple machines
- Anyone building custom Claude Code hooks

## Tech stack

| Component | Tech |
|-----------|------|
| Backend | Python 3.9+, FastAPI, Pydantic |
| Frontend | SvelteKit, Svelte 5, Tailwind CSS, Chart.js |
| CLI | Python with Click |
| Hooks | Python scripts |
| Sync | Syncthing (peer-to-peer file sync) |

## Architecture at a glance

This is one repository with four parts:

| Part | Purpose | Port |
|------|---------|------|
| `api/` | Reads JSONL files and serves REST API | 8000 |
| `frontend/` | Web dashboard | 5173 |
| `cli/karma/` | Command-line tool for managing sync | — |
| `hooks/` | Scripts for real-time tracking | — |

Claude Code writes sessions to `~/.claude/projects/`. The API reads them and serves JSON. The frontend fetches from the API and displays everything. If you enable sync, the CLI watches for new sessions and packages them for Syncthing.

## Quick navigation

- **[Quick Start](quick-start.md)** — Get running in 5 minutes
- **[Features](features.md)** — See all the capabilities
- **[Architecture](architecture.md)** — How it works internally
- **[Hooks Guide](hooks-guide.md)** — Enable real-time tracking
- **[Syncing Sessions](syncing-sessions.md)** — Share sessions with your team
- **[API Reference](api-reference.md)** — For developers
