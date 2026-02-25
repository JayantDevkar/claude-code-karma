# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**Claude Karma API** — FastAPI backend for monitoring and analyzing Claude Code sessions. Parses Claude Code's local storage (`~/.claude/`) and exposes REST endpoints for the SvelteKit frontend.

## Quick Start

```bash
# Install dependencies
pip install -e ".[dev]"
pip install -r requirements.txt

# Run API server
uvicorn main:app --reload --port 8000
```

## Commands

```bash
# Development
uvicorn main:app --reload --port 8000      # Run dev server

# Testing
pytest                                      # Run all tests
pytest tests/test_session.py -v            # Single test file
pytest tests/api/ -v                       # API tests only
pytest --cov=models --cov=routers          # With coverage

# Linting & Formatting
ruff check models/ tests/ routers/         # Lint
ruff format models/ tests/ routers/        # Format

# Utilities
python session_story.py /path/to/project   # Generate session report
python session_story.py /path/to/project --session-uuid abc123
```

## Architecture

### Directory Structure

```
api/
├── main.py              # FastAPI app entry point
├── config.py            # Settings (CLAUDE_DIR, KARMA_DIR paths)
├── schemas.py           # Pydantic response schemas
├── routers/             # API route handlers
│   ├── projects.py      # Project listing and details
│   ├── sessions.py      # Session data, timeline, tools
│   ├── analytics.py     # Project/session analytics
│   ├── agents.py        # Agent listing
│   ├── agent_analytics.py # Agent usage analytics
│   ├── skills.py        # Skill usage tracking
│   ├── history.py       # File history endpoints
│   ├── live_sessions.py # Real-time session tracking
│   ├── subagent_sessions.py # Subagent session details
│   └── settings.py      # User settings
├── services/            # Business logic layer
│   ├── session_relationships.py  # Chain detection
│   └── tool_results.py           # Tool result handling
├── middleware/          # HTTP middleware
│   └── caching.py       # Response caching
├── models/              # Pydantic models for parsing
│   ├── project.py       # Project entry point
│   ├── session.py       # Session conversation
│   ├── agent.py         # Subagent conversations
│   ├── message.py       # Message types
│   ├── content.py       # Content blocks
│   ├── usage.py         # Token stats
│   ├── live_session.py  # Real-time state
│   ├── session_relationship.py  # Chain links
│   └── compaction_detector.py   # Compaction detection
└── tests/               # Pytest test suite
```

### Model Hierarchy

```
Project (entry point)
├── Session ({uuid}.jsonl)
│   ├── Message (UserMessage, AssistantMessage, FileHistorySnapshot, SummaryMessage)
│   ├── Agent (subagents in {uuid}/subagents/)
│   ├── ToolResult ({uuid}/tool-results/toolu_*.txt)
│   └── TodoItem (~/.claude/todos/{uuid}-*.json)
└── Agent (standalone: agent-{id}.jsonl)
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

Project paths are URL-encoded: leading `/` becomes `-`, all `/` become `-`
- `/Users/me/repo` → `-Users-me-repo`

## Key Patterns

### Lazy Loading
Messages loaded via `iter_messages()` to avoid memory issues with large sessions. Access `session.messages` for list, `session.iter_messages()` for generator.

### Frozen Models
All Pydantic models use `ConfigDict(frozen=True)` for immutability. Tests must catch `ValidationError` for mutation attempts.

### Session Chains
Related sessions detected via:
- `leaf_uuid` in summary messages (95% confidence)
- Slug matching (85% confidence)

### Compaction Detection
Sessions with `SummaryMessage` indicate compacted/resumed conversations. Use `CompactionDetector` to identify.

### Live Sessions
Real-time state tracked in `~/.claude_karma/live-sessions/{slug}.json` via Claude Code hooks (captain-hook library).

## API Endpoints

| Route Prefix | Description |
|--------------|-------------|
| `/projects` | Project listing, details, sessions |
| `/sessions` | Session data, timeline, tools, file activity |
| `/analytics` | Project/session analytics, usage stats |
| `/agents` | Agent listing and subagent sessions |
| `/live-sessions` | Real-time session state |
| `/history` | File history snapshots |
| `/settings` | User preferences |
| `/skills` | Skill usage tracking |

### Key Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/projects` | List all projects |
| GET | `/projects/{encoded_name}` | Project details with sessions |
| GET | `/sessions/{uuid}` | Session details |
| GET | `/sessions/{uuid}/timeline` | Event timeline |
| GET | `/sessions/{uuid}/tools` | Tool usage breakdown |
| GET | `/sessions/{uuid}/file-activity` | File operations |
| GET | `/sessions/{uuid}/subagents` | Subagent activity |
| GET | `/analytics/projects/{encoded_name}` | Project analytics |

## Core Classes

| Class | File | Purpose |
|-------|------|---------|
| `Project` | `models/project.py` | Entry point, encodes/decodes paths, lists sessions |
| `Session` | `models/session.py` | Main conversation, aggregates usage stats |
| `Agent` | `models/agent.py` | Both standalone and subagent conversations |
| `parse_message()` | `models/message.py` | Parses UserMessage, AssistantMessage, etc. |
| `parse_content_block()` | `models/content.py` | Parses TextBlock, ToolUseBlock, etc. |
| `TokenUsage` | `models/usage.py` | Token stats with `__add__` for aggregation |
| `LiveSession` | `models/live_session.py` | Real-time session state from hooks |
| `SessionRelationship` | `models/session_relationship.py` | Chain links between sessions |
| `CompactionDetector` | `models/compaction_detector.py` | Identifies compacted sessions |

## Testing

Tests use pytest fixtures in `tests/conftest.py` that create temporary `~/.claude` directory structures with sample JSONL data.

```bash
# Run specific test categories
pytest tests/test_session.py       # Model tests
pytest tests/api/                  # Endpoint tests
pytest -k "test_usage"             # Tests matching pattern
```

## Dependencies

- **Python 3.9+**
- **FastAPI** - Web framework
- **Pydantic 2.x** - Data validation
- **aiofiles** - Async file I/O
- **cachetools** - Response caching
- **pytest** - Testing framework
- **ruff** - Linting and formatting
