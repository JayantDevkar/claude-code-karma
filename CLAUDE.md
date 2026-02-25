# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**Claude Karma** is a full-stack application for monitoring and analyzing Claude Code sessions. It parses Claude Code's local storage (`~/.claude/`) and visualizes session data through a web dashboard.

## Quick Start

```bash
# Clone (no submodule init needed — this is a monorepo)
git clone https://github.com/JayantDevkar/claude-karma.git
cd claude-karma

# Start API (terminal 1)
cd api
pip install -e ".[dev]" && pip install -r requirements.txt
uvicorn main:app --reload --port 8000

# Start frontend (terminal 2)
cd frontend
npm install && npm run dev
```

Open http://localhost:5173 to view the dashboard.

## Repository Structure

This is a monorepo with all components in a single repository:

```
claude-karma/
├── api/                    # FastAPI backend (Python) - port 8000
├── frontend/               # SvelteKit frontend (Svelte 5) - port 5173
├── captain-hook/           # Claude Code hooks Pydantic library
└── hooks/                  # Hook scripts (symlinked from ~/.claude/hooks/)
    ├── live_session_tracker.py    # Tracks live session state across hook events
    ├── session_title_generator.py # Generates session titles via Haiku on SessionEnd
    └── plan_approval.py           # Handles ExitPlanMode permission requests
```

Each directory has its own `CLAUDE.md` with module-specific guidance.

## Commands

### API (Python/FastAPI)

```bash
cd api

# Run server
uvicorn main:app --reload --port 8000

# Run all tests
pytest

# Run specific test file
pytest tests/test_session.py -v

# Run API endpoint tests
pytest tests/api/ -v

# Run with coverage
pytest --cov=models --cov=routers

# Lint & format
ruff check models/ tests/ routers/
ruff format models/ tests/ routers/
```

### Frontend (SvelteKit/Svelte 5)

```bash
cd frontend

npm install           # Install dependencies
npm run dev           # Dev server (port 5173)
npm run check         # Type check
npm run lint          # Lint
npm run format        # Format
npm run build         # Production build
```

### Captain Hook

```bash
cd captain-hook
pytest tests/test_models.py -v
```

## Architecture

### Data Flow

```
~/.claude/projects/{encoded-path}/{uuid}.jsonl
    ↓
API (models/ parses JSONL → Pydantic models)
    ↓
FastAPI endpoints (routers/) on port 8000
    ↓
SvelteKit frontend (src/routes/) on port 5173
```

### Claude Code Storage Locations

| Data | Location |
|------|----------|
| Session JSONL | `~/.claude/projects/{encoded-path}/{uuid}.jsonl` |
| Subagents | `~/.claude/projects/{encoded-path}/{uuid}/subagents/agent-*.jsonl` |
| Tool Results | `~/.claude/projects/{encoded-path}/{uuid}/tool-results/toolu_*.txt` |
| Debug Logs | `~/.claude/debug/{uuid}.txt` |
| Todos | `~/.claude/todos/{uuid}-*.json` |
| Live Sessions | `~/.claude_karma/live-sessions/{slug}.json` |

### Path Encoding

Project paths are encoded: leading `/` becomes `-`, all `/` become `-`
- `/Users/me/repo` → `-Users-me-repo`

### API Model Hierarchy

```
Project (entry point)
├── Session ({uuid}.jsonl)
│   ├── Message (UserMessage, AssistantMessage, FileHistorySnapshot, SummaryMessage)
│   ├── Agent (subagents/)
│   ├── ToolResult (tool-results/)
│   └── TodoItem
└── Agent (standalone: agent-{id}.jsonl)
```

### Key Patterns

**API:**
- Lazy Loading: Messages loaded via `iter_messages()` for large sessions
- Frozen Models: All Pydantic models use `ConfigDict(frozen=True)`
- Session Chains: Related sessions detected via `leaf_uuid` or slug matching
- Compaction Detection: Sessions with `SummaryMessage` are compacted

**Frontend:**
- Svelte 5 Runes: `$state()`, `$derived()`, `$effect()`, `$props()`
- URL State: Filters persisted via URL search params
- Design Tokens: CSS custom properties in `app.css`
- Component Library: `bits-ui` for accessible primitives

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/projects` | List all projects |
| GET | `/projects/{encoded_name}` | Project details with sessions |
| GET | `/sessions/{uuid}` | Session details |
| GET | `/sessions/{uuid}/timeline` | Event timeline |
| GET | `/sessions/{uuid}/tools` | Tool usage |
| GET | `/sessions/{uuid}/file-activity` | File operations |
| GET | `/sessions/{uuid}/subagents` | Subagent activity |
| GET | `/analytics/projects/{encoded_name}` | Project analytics |
| GET | `/live-sessions` | Real-time session state |
| GET | `/agents` | Agent listing |
| GET | `/skills` | Skill usage |
| GET | `/history` | File history |
| GET | `/settings` | User preferences |

## Frontend Routes

| Route | Description |
|-------|-------------|
| `/` | Home page |
| `/projects` | Project listing |
| `/projects/[encoded_name]` | Project detail |
| `/projects/[encoded_name]/agents` | Project agents |
| `/projects/[encoded_name]/skills` | Project skills |
| `/agents` | Global agents view |
| `/analytics` | Global analytics |
| `/history` | File history |
| `/settings` | User settings |
| `/skills` | Global skills view |

## Captain Hook

Type-safe Pydantic models for Claude Code's 10 hook types:

| Hook | Fires | Can Block? |
|------|-------|------------|
| PreToolUse | Before tool | Yes |
| PostToolUse | After tool | No |
| UserPromptSubmit | User message | Yes |
| SessionStart/End | Session lifecycle | No |
| Stop/SubagentStop | Agent completion | No |
| PreCompact | Context compaction | No |
| PermissionRequest | Permission dialog | Yes |
| Notification | System notification | No |

```python
from captain_hook import parse_hook_event, PreToolUseHook
hook = parse_hook_event(json_data)
```

## Tech Stack

### Backend
- **Python 3.9+**
- **FastAPI** - Web framework
- **Pydantic 2.x** - Data validation
- **aiofiles** - Async file I/O
- **pytest** - Testing
- **ruff** - Linting/formatting

### Frontend
- **SvelteKit 2** with **adapter-node**
- **Svelte 5** with runes
- **Tailwind CSS 4**
- **Chart.js 4** - Visualizations
- **bits-ui** - UI primitives
- **lucide-svelte** - Icons
- **TypeScript**

## MCP Integration

Plane MCP tools for project management:
- `mcp__plane-project-task-manager__list_projects`
- `mcp__plane-project-task-manager__list_work_items`
- `mcp__plane-project-task-manager__retrieve_work_item`
- `mcp__plane-project-task-manager__update_work_item`

## Browser Automation

Use `agent-browser` CLI (Vercel) for browser automation instead of Playwright MCP. It's more token-efficient and optimized for LLM usage.

```bash
agent-browser open <url>       # Navigate to page
agent-browser snapshot -i      # Get interactive elements with refs (@e1, @e2)
agent-browser click @e1        # Click element by ref
agent-browser fill @e2 "text"  # Fill input field
agent-browser close            # Close browser
```

Workflow: `open` → `snapshot -i` → interact via refs → re-snapshot after changes → `close`

## Development Workflow

1. **API changes**: Modify `api/models/` or `api/routers/`, run tests with `pytest`
2. **Frontend changes**: Modify `frontend/src/`, type-check with `npm run check`
3. **Hook changes**: Modify `captain-hook/`, test with `pytest tests/test_models.py`
4. **Commit changes**: All changes committed directly in this monorepo

## Known Claude Code Bugs

- `classifyHandoffIfNeeded is not defined` — open bug in Claude Code. Task agents (subagents) may fail with this runtime error. Ignore it and proceed; the work is typically completed before the failure. Don't retry agents solely because of this error.
