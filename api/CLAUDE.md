# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**Claude Code Karma API** — FastAPI backend for monitoring and analyzing Claude Code sessions. Parses Claude Code's local storage (`~/.claude/`) and exposes REST endpoints for the SvelteKit frontend.

## Quick Start

```bash
# Install dependencies
pip install -e ".[dev]"
pip install -r requirements.txt

# Run API server
uvicorn main:app --reload --port 8020
```

## Commands

```bash
# Development
uvicorn main:app --reload --port 8020      # Run dev server

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
│   ├── conversation_endpoints.py # Timeline, tools and file-activity builders
│   ├── agent_registry.py         # Subagent names, types and colours (meta.json)
│   ├── timeline_parsing.py       # Text parsers for message and notification wrappers
│   └── tool_results.py           # Tool result handling
├── middleware/          # HTTP middleware
│   └── caching.py       # Response caching
├── models/              # Pydantic models for parsing
│   ├── project.py       # Project entry point
│   ├── session.py       # Session conversation
│   ├── agent.py         # Subagent conversations
│   ├── message.py       # Message types
│   ├── side_entries.py  # System notices and queued input (not messages)
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
│   ├── Side entry (SystemEntry, QueuedCommandEntry; read by iter_side_entries())
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

Project paths are encoded: every character except ASCII letters and digits becomes `-`; names over 200 characters are cut and get a hash suffix (`Project.encode_path`)
- `/Users/me/my_repo` → `-Users-me-my-repo`

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

### Who Sent a User Entry
Not every `type: user` entry is a prompt. `UserMessage.source` says who wrote it: `human`, `command`, `shell`, `peer_session` (another Claude session), `agent` (a teammate, team lead or coordinator), `task_notification`, `scheduled`, `skill_body`, `system_reminder`, `meta`, `compact_summary`, `local_command`, `interrupt` or `tool_result`. It is derived from the entry's structured fields (`origin`, `isMeta`, `sourceToolUseID`, `isCompactSummary`, `turnOrigin`); the start of the text is only a fallback for older sessions. `is_internal_message` is true when the entry came from another session, an agent or Claude Code.

### Side Entries
`system` notices and `queued_command` attachments are not conversation messages. `iter_side_entries()` in `models/side_entries.py` reads them as `SystemEntry` and `QueuedCommandEntry`. They are kept out of `iter_messages()`, so message counts and the indexer do not see them; the timeline builder reads both.

### Agent Registry
`services/agent_registry.py` reads the `agent-*.meta.json` next to each subagent JSONL (name, type, team, colour, model, description). The timeline, the subagents list and the agent detail use it to name agents. `collectors.resolve_subagent_type()` is the one rule for an agent's type: the spawn call's `subagent_type`, else a system agent's id prefix, else the type in its meta.json.

### Model Pricing
Prices (USD per 1M tokens) ship in `models/pricing.json` and load once at startup. Users override them in `~/.claude_karma/pricing.json` (or the path in `CLAUDE_KARMA_PRICING_OVERRIDE_PATH`), which has the same shape. An override entry under `models` replaces that model's whole entry, a new model ID is added, and `multipliers` merge per key. Invalid entries are logged and skipped. When the effective prices change, the indexer re-parses every session so stored costs match. It compares a fingerprint kept in the `index_meta` table.

```json
{"models": {"claude-sonnet-5-5": {"input": 2.0, "output": 10.0, "cache_read": 0.05}}}
```

### Live Sessions
Real-time state tracked in `~/.claude_karma/live-sessions/{slug}.json` via Claude Code hooks (captain-hook library).

## API Endpoints

| Route Prefix | Description |
|--------------|-------------|
| `/projects` | Project listing, details, sessions |
| `/sessions` | Session data, timeline, tools, file activity |
| `/analytics` | Project/session analytics, usage stats |
| `/agents` | Agent listing and subagent sessions |
| `/live-sessions` | Real-time session state (+ `POST /live-sessions/{id}/focus-terminal` to raise the session's terminal window) |
| `/history` | Archived prompts from cleaned-up sessions (`/history/archived`) |
| `/settings` | User preferences |
| `/skills` | Skill usage tracking |
| `/desktop-app` | Install/manage the native desktop launcher — `GET status`, `POST install`, `PUT autostart`, `DELETE install` (localhost-only) |

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
| GET | `/sessions/resolve/{short_id}` | Resolve a UUID/prefix to its project (short links) |
| POST | `/sessions/{uuid}/resume-in-terminal` | Focus if live, else launch `claude --resume` in a new terminal |

## Core Classes

| Class | File | Purpose |
|-------|------|---------|
| `Project` | `models/project.py` | Entry point, encodes/decodes paths, lists sessions |
| `Session` | `models/session.py` | Main conversation, aggregates usage stats |
| `Agent` | `models/agent.py` | Both standalone and subagent conversations |
| `parse_message()` | `models/message.py` | Parses UserMessage, AssistantMessage, etc. |
| `iter_side_entries()` | `models/side_entries.py` | Yields SystemEntry and QueuedCommandEntry (harness notices, queued input) |
| `build_agent_registry()` | `services/agent_registry.py` | Subagent names, types and colours from meta.json |
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

- **Python 3.10+**
- **FastAPI** - Web framework
- **Pydantic 2.x** - Data validation
- **aiofiles** - Async file I/O
- **cachetools** - Response caching
- **pytest** - Testing framework
- **ruff** - Linting and formatting
