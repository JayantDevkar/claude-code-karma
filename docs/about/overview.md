# Claude Code Karma — Overview

## What is Claude Code Karma?

Claude Code Karma is a full-stack monitoring and analytics dashboard for [Claude Code](https://docs.anthropic.com/en/docs/claude-code) sessions. It parses Claude Code's local storage (`~/.claude/`), extracts structured data from raw JSONL session files, and presents it through an interactive web dashboard. It also enables sharing sessions across distributed teams via IPFS or Syncthing.

## The Problem

Claude Code stores all session data locally as raw JSONL files scattered across `~/.claude/projects/`. These files contain rich information — conversations, tool calls, token usage, subagent activity, file operations — but are effectively invisible to the user. There is no built-in way to:

- Browse past sessions across projects
- Track token usage and costs over time
- Monitor live sessions in real time
- Analyze tool usage patterns or agent behavior
- Replay conversations or inspect timelines
- Share sessions with freelancers or distributed teams

Claude Code Karma makes all of this accessible through a single dashboard and adds cross-system session sharing for teams.

## Who Is It For?

- **Claude Code power users** who run dozens of sessions daily and want visibility into their usage
- **Developers** who want to understand how Claude Code interacts with their codebase
- **Teams** evaluating Claude Code adoption and needing usage analytics
- **Teams with freelancers** who want to monitor work across multiple machines
- **Hook developers** building on Claude Code's extensibility layer

## Key Capabilities

### Local Monitoring

- **Session Browser** — Browse, search, and filter all sessions across every project
- **Timeline View** — Chronological event stream with messages, tool calls, and subagent activity
- **Conversation Playback** — Full conversation viewer with user and assistant messages
- **Token and Cost Tracking** — Per-session and aggregate token usage with cost estimates
- **File Activity Tracking** — See which files were read, written, or modified
- **Live Session Monitoring** — Real-time session state via Claude Code hooks
- **Analytics Dashboards** — Project-level and global analytics with charts
- **Agent and Skill Analytics** — Track subagent spawning patterns and skill usage
- **MCP Tool Tracking** — Monitor MCP tool discovery and invocation
- **Session Chains** — Detect and link related or resumed sessions
- **Command Palette** — Quick navigation with Ctrl+K

### Cross-System Session Sharing

- **IPFS Backend** — Distribute sessions to large teams via content-addressable storage with tamper-evident audit trails
- **Syncthing Backend** — Auto-sync sessions in real time for small trusted teams with simpler setup
- **Remote Sessions Browser** — View sessions from all team members in a unified dashboard
- **Team Management** — Create and manage teams with backend-specific configuration (IPFS or Syncthing per team)
- **CLI Tool** — `karma` command for initializing sync, managing projects, and viewing status
- **Feedback & Annotations** — Project owners can leave per-session notes that sync back to freelancers

## Tech Stack

| Layer | Technology |
|-------|-----------
| Backend | Python 3.9+, FastAPI, Pydantic 2.x, aiofiles |
| Frontend | SvelteKit 2, Svelte 5 (runes), Tailwind CSS 4, Chart.js 4, bits-ui |
| CLI | Python 3.9+, Click, requests, watchdog |
| Hooks | captain-hook (Pydantic models for Claude Code's 10 hook types) |
| Tooling | ruff (Python), eslint/prettier (JS), pytest, vitest |

## Architecture

Claude Code Karma is a monorepo with all components in a single repository:

| Directory | Description | Port |
|-----------|-------------|------|
| `api/` | FastAPI backend — parses JSONL, serves REST endpoints, reads remote sessions | 8000 |
| `frontend/` | SvelteKit dashboard — visualizes session data and team collaboration | 5173 |
| `cli/karma/` | Python CLI for session sync management (IPFS or Syncthing) | — |
| `captain-hook/` | Pydantic library — type-safe models for Claude Code hooks | — |
| `hooks/` | Production hook scripts for live tracking and automation | — |

## Learn More

- [Quick Start](quick-start.md) — Get up and running in 5 minutes
- [Features](features.md) — Full feature showcase
- [Architecture](architecture.md) — Technical deep dive
- [Hooks Guide](hooks-guide.md) — Claude Code hooks and how Claude Code Karma uses them
- [API Reference](api-reference.md) — Complete endpoint documentation
