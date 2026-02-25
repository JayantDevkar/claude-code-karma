# Claude Karma API Setup

FastAPI backend for monitoring and analyzing Claude Code sessions.

## Prerequisites

- **Python 3.10+**: `python3 --version`
- **pip**: `pip --version`
- **Claude Code 2.1.19+** (for SubagentStart/SubagentStop hooks)

## Quick Start

```bash
# Install dependencies
pip install -r requirements.txt

# Start API server
uvicorn main:app --reload --port 8000
```

The API runs at **http://localhost:8000**

Verify with:
```bash
curl http://localhost:8000/health
# {"status": "healthy"}
```

## Commands

```bash
# Development
uvicorn main:app --reload --port 8000      # Run with hot reload

# Testing
pytest                                      # Run all tests
pytest tests/api/ -v                        # API endpoint tests
pytest tests/test_session.py -v             # Model tests
pytest --cov=models --cov=routers           # With coverage

# Linting & Formatting
ruff check .                                # Lint
ruff format .                               # Format
```

## Hook Configuration

Claude Karma uses Claude Code hooks to track live session state and subagent activity.

### Install Hook Scripts

Create symlinks to the hook scripts (recommended for development):

```bash
# Create hooks directory
mkdir -p ~/.claude/hooks

# Symlink the tracker script
ln -sf "$(pwd)/scripts/live_session_tracker.py" ~/.claude/hooks/live_session_tracker.py

# Make executable
chmod +x scripts/live_session_tracker.py
```

Or copy for standalone installation:
```bash
cp scripts/live_session_tracker.py ~/.claude/hooks/
chmod +x ~/.claude/hooks/live_session_tracker.py
```

### Configure Claude Code Settings

Add the following to `~/.claude/settings.json`:

```json
{
  "hooks": {
    "SessionStart": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "python3 ~/.claude/hooks/live_session_tracker.py",
            "timeout": 5000
          }
        ]
      }
    ],
    "PostToolUse": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "python3 ~/.claude/hooks/live_session_tracker.py",
            "timeout": 5000
          }
        ]
      }
    ],
    "Notification": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "python3 ~/.claude/hooks/live_session_tracker.py",
            "timeout": 5000
          }
        ]
      }
    ],
    "Stop": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "python3 ~/.claude/hooks/live_session_tracker.py",
            "timeout": 5000
          }
        ]
      }
    ],
    "SessionEnd": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "python3 ~/.claude/hooks/live_session_tracker.py",
            "timeout": 5000
          }
        ]
      }
    ],
    "UserPromptSubmit": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "python3 ~/.claude/hooks/live_session_tracker.py",
            "timeout": 5000
          }
        ]
      }
    ],
    "SubagentStart": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "python3 ~/.claude/hooks/live_session_tracker.py",
            "timeout": 5000
          }
        ]
      }
    ],
    "SubagentStop": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "python3 ~/.claude/hooks/live_session_tracker.py",
            "timeout": 5000
          }
        ]
      }
    ]
  }
}
```

### Hook → State Mapping

| Hook | State | Description |
|------|-------|-------------|
| `SessionStart` | `STARTING` | Session started, JSONL may not exist yet |
| `UserPromptSubmit` | `LIVE` | Prompt submitted, actively processing |
| `PostToolUse` | `LIVE` | Tool completed, session actively working |
| `Notification` (permission_prompt) | `WAITING` | Claude needs user input |
| `Notification` (idle_prompt) | `STALE` | User has been idle 60+ seconds |
| `Stop` | `STOPPED` | Agent finished but session still open |
| `SessionEnd` | `ENDED` | Session terminated |
| `SubagentStart` | — | Adds running subagent to session |
| `SubagentStop` | — | Marks subagent as completed |

### Subagent Tracking

When Claude Code spawns a subagent (via the Task tool), the tracker captures:

- **agent_id**: Unique identifier (e.g., `agent-abc123`)
- **agent_type**: Type of subagent (`Bash`, `Explore`, `Plan`, custom)
- **status**: `running` or `completed`
- **transcript_path**: Path to subagent's JSONL transcript (when completed)
- **started_at**: When subagent started
- **completed_at**: When subagent finished

Example live session JSON with subagents:
```json
{
  "session_id": "a856beed-b427-4739-ad72-78eb9d104fe0",
  "slug": "eager-stirring-moore",
  "state": "LIVE",
  "subagents": {
    "agent-xyz789": {
      "agent_id": "agent-xyz789",
      "agent_type": "Explore",
      "status": "running",
      "transcript_path": null,
      "started_at": "2026-01-28T12:37:02Z",
      "completed_at": null
    },
    "agent-abc123": {
      "agent_id": "agent-abc123",
      "agent_type": "Bash",
      "status": "completed",
      "transcript_path": "~/.claude/projects/-Users-me-repo/sess/subagents/agent-abc123.jsonl",
      "started_at": "2026-01-28T12:30:00Z",
      "completed_at": "2026-01-28T12:35:00Z"
    }
  }
}
```

### Verify Hook Installation

```bash
# Check hooks directory
ls -la ~/.claude/hooks/

# Test the tracker manually
echo '{"hook_event_name": "SessionStart", "session_id": "test-123", "cwd": "/tmp", "transcript_path": "/tmp/test.jsonl"}' | python3 ~/.claude/hooks/live_session_tracker.py

# Check live sessions directory
ls ~/.claude_karma/live-sessions/
```

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/health` | Health check |
| GET | `/projects` | List all projects |
| GET | `/projects/{encoded_name}` | Project details with sessions |
| GET | `/sessions/{uuid}` | Session details |
| GET | `/sessions/{uuid}/timeline` | Session timeline events |
| GET | `/sessions/{uuid}/tools` | Tool usage breakdown |
| GET | `/sessions/{uuid}/file-activity` | File operations |
| GET | `/sessions/{uuid}/subagents` | Subagent activity |
| GET | `/analytics` | Global analytics |
| GET | `/analytics/projects/{encoded_name}` | Project analytics |
| GET | `/agents` | Agent listing |
| GET | `/skills` | Skill usage |
| GET | `/live-sessions` | Real-time session state (includes subagent tracking) |
| GET | `/live-sessions/active` | Active sessions only |

## Directory Structure

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
│   ├── live_sessions.py # Real-time session tracking
│   └── ...
├── services/            # Business logic layer
├── middleware/          # HTTP middleware (caching)
├── models/              # Pydantic models for parsing ~/.claude/
│   └── live_session.py  # LiveSessionState, SubagentState models
├── scripts/             # Hook scripts
│   └── live_session_tracker.py  # Session & subagent tracking
└── tests/               # Pytest test suite
```

## Data Sources

The API reads from Claude Code's local storage:

| Data | Location |
|------|----------|
| Projects | `~/.claude/projects/` |
| Sessions | `~/.claude/projects/{project}/{uuid}.jsonl` |
| Subagents | `~/.claude/projects/{project}/{uuid}/subagents/` |
| Tool Results | `~/.claude/projects/{project}/{uuid}/tool-results/` |
| Todos | `~/.claude/todos/{uuid}-*.json` |
| Debug Logs | `~/.claude/debug/{uuid}.txt` |
| Live Sessions | `~/.claude_karma/live-sessions/{slug}.json` |

## Troubleshooting

### API won't start

```bash
# Check Python version
python3 --version  # Should be 3.10+

# Reinstall dependencies
pip install -r requirements.txt
```

### Empty projects list

```bash
# Check Claude Code sessions exist
ls ~/.claude/projects/
ls ~/.claude/projects/-Users-*/
```

### Port already in use

```bash
lsof -ti:8000 | xargs kill -9
```

### Live sessions not updating

```bash
# Check hooks are configured
cat ~/.claude/settings.json | grep -A 5 "SubagentStart"

# Check live sessions directory exists
ls ~/.claude_karma/live-sessions/

# Check hook script is executable
ls -la ~/.claude/hooks/live_session_tracker.py

# Test hook manually
echo '{"hook_event_name": "PostToolUse", "session_id": "test", "cwd": "/tmp", "transcript_path": ""}' \
  | python3 ~/.claude/hooks/live_session_tracker.py
```

### Subagents not being tracked

Requires Claude Code 2.1.19+ for `SubagentStart` and `SubagentStop` hooks. Check your Claude Code version:

```bash
claude --version
```

## Dependencies

- **FastAPI** - Web framework
- **Pydantic 2.x** - Data validation
- **uvicorn** - ASGI server
- **aiofiles** - Async file I/O
- **cachetools** - Response caching
- **pytest** - Testing
- **ruff** - Linting/formatting

## Troubleshooting

### API won't start

```bash
# Check Python version
python3 --version  # Should be 3.10+

# Reinstall dependencies
pip install -r requirements.txt
```

### Empty projects list

```bash
# Check Claude Code sessions exist
ls ~/.claude/projects/
ls ~/.claude/projects/-Users-*/
```

### Port already in use

```bash
lsof -ti:8000 | xargs kill -9
```

## Dependencies

- **FastAPI** - Web framework
- **Pydantic 2.x** - Data validation
- **uvicorn** - ASGI server
- **aiofiles** - Async file I/O
- **cachetools** - Response caching
- **pytest** - Testing
- **ruff** - Linting/formatting
