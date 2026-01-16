# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Claude Karma is a full-stack application for monitoring and analyzing Claude Code sessions. It parses Claude Code's local storage (`~/.claude/`) and visualizes session data through a web dashboard.

## Repository Structure

This is a monorepo with three git submodules:

```
claude-karma/
├── api/                    # FastAPI backend (Python) - port 8000
├── frontend/               # SvelteKit frontend (Svelte 5) - port 5173
└── captain-hook/           # Claude Code hooks Pydantic library
```

Each submodule has its own `CLAUDE.md` with module-specific guidance.

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

# Lint & format
ruff check models/ tests/ routers/
ruff format models/ tests/ routers/
```

### Frontend (SvelteKit/Svelte 5)

```bash
cd frontend

npm install
npm run dev      # Dev server
npm run check    # Type check
npm run lint     # Lint
npm run build    # Production build
```

### Captain Hook

```bash
cd captain-hook
pytest tests/test_models.py -v
```

### Submodules

```bash
git submodule update --init --recursive  # Initialize
git submodule update --remote            # Update to latest
```

## Architecture

### Data Flow

```
~/.claude/projects/{encoded-path}/{uuid}.jsonl
    ↓
API (models/ parses JSONL → Pydantic models)
    ↓
FastAPI endpoints (routers/)
    ↓
SvelteKit frontend (src/routes/)
```

### Claude Code Storage Locations

| Data | Location |
|------|----------|
| Session JSONL | `~/.claude/projects/{encoded-path}/{uuid}.jsonl` |
| Subagents | `~/.claude/projects/{encoded-path}/{uuid}/subagents/agent-*.jsonl` |
| Tool Results | `~/.claude/projects/{encoded-path}/{uuid}/tool-results/toolu_*.txt` |
| Debug Logs | `~/.claude/debug/{uuid}.txt` |
| Todos | `~/.claude/todos/{uuid}-*.json` |

### Path Encoding

Project paths are encoded: leading `/` becomes `-`, all `/` become `-`
- `/Users/me/repo` → `-Users-me-repo`

### API Model Hierarchy

```
Project (entry point)
├── Session ({uuid}.jsonl)
│   ├── Message (UserMessage, AssistantMessage, FileHistorySnapshot)
│   ├── Agent (subagents/)
│   ├── ToolResult (tool-results/)
│   └── TodoItem
└── Agent (standalone: agent-{id}.jsonl)
```

### Key Patterns

**API:**
- Lazy Loading: Messages loaded via `iter_messages()` for large sessions
- Frozen Models: All Pydantic models use `ConfigDict(frozen=True)`

**Frontend:**
- Svelte 5 Runes: `$state()`, `$derived()`, `$effect()`, `$props()`
- URL State: Filters persisted via URL search params
- Design Tokens: CSS custom properties in `app.css`

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/projects` | List all projects |
| GET | `/projects/{encoded_name}` | Project details |
| GET | `/sessions/{uuid}` | Session details |
| GET | `/sessions/{uuid}/timeline` | Event timeline |
| GET | `/sessions/{uuid}/tools` | Tool usage |
| GET | `/sessions/{uuid}/file-activity` | File operations |
| GET | `/sessions/{uuid}/subagents` | Subagent activity |
| GET | `/analytics/projects/{encoded_name}` | Project analytics |

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

## MCP Integration

Plane MCP tools for project management:
- `mcp__plane-project-task-manager__list_projects`
- `mcp__plane-project-task-manager__list_work_items`
- `mcp__plane-project-task-manager__retrieve_work_item`
- `mcp__plane-project-task-manager__update_work_item`
