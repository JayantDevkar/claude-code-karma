# Agent Status Tracking Feature

## Overview

This feature adds real-time subagent tracking to Claude Karma, enabling monitoring of subagents (Task tool spawns) within live Claude Code sessions. It tracks when subagents start, their type, status, and when they complete.

## Related PRs

| Repository | PR | Title | Status |
|------------|-----|-------|--------|
| [captain-hook](https://github.com/JayantDevkar/captain-hook) | [#2](https://github.com/JayantDevkar/captain-hook/pull/2) | feat: add Claude Code 2.1.19 hooks support | Open |
| [ClaudeDashboard](https://github.com/the-non-expert/ClaudeDashboard) (frontend) | [#14](https://github.com/the-non-expert/ClaudeDashboard/pull/14) | feat: add subagent tracking types | Open |
| [dot-claude-files-parser](https://github.com/JayantDevkar/dot-claude-files-parser) (api) | [#15](https://github.com/JayantDevkar/dot-claude-files-parser/pull/15) | feat: add subagent tracking to live sessions | Open |

## Changes by Component

### 1. Captain Hook (Pydantic Hook Library)

**Files Changed:** 9 files (+191/-6 lines)

Added support for Claude Code 2.1.19 hooks:

#### New Hook Types
- **`SubagentStartHook`** - Fires when a subagent (Task tool) is spawned
  - `agent_id`: Unique identifier for the subagent (e.g., `agent-abc123`)
  - `agent_type`: Type of subagent (`Bash`, `Explore`, `Plan`, or custom)

- **`PostToolUseFailureHook`** - Fires after a tool execution fails
  - `tool_name`: Name of the tool that failed
  - `tool_input`: Input parameters passed to the tool
  - `tool_use_id`: Unique identifier for the tool call
  - `error`: Error message or details

- **`SetupHook`** - Fires when Claude Code is invoked with `--init`, `--init-only`, or `--maintenance` flags
  - `trigger`: What triggered the hook (`init` or `maintenance`)

#### Updated Hook Types
- **`SubagentStopHook`** - Added new fields:
  - `agent_id`: Unique identifier for the stopped subagent
  - `agent_transcript_path`: Path to subagent's JSONL transcript

- **`SessionStartHook`** - Added optional fields:
  - `model`: Model identifier (e.g., `claude-sonnet-4-20250514`)
  - `agent_type`: Agent type if started with `--agent` flag

- **`NotificationHook`** - Added:
  - `message`: The notification message text

#### Registry Update
- `HOOK_TYPE_MAP` now includes 13 total hooks (up from 10)

---

### 2. Frontend (SvelteKit)

**Files Changed:** 1 file (+15/-0 lines)

Added TypeScript types in `src/lib/api-types.ts`:

```typescript
export type SubagentStatus = 'running' | 'completed' | 'error';

export interface SubagentState {
    agent_id: string;
    agent_type: string;
    status: SubagentStatus;
    transcript_path: string | null;
    started_at: string;
    completed_at: string | null;
}
```

Extended `LiveSessionSummary` interface:
```typescript
export interface LiveSessionSummary {
    // ... existing fields ...

    // Subagent tracking
    subagents: Record<string, SubagentState>;
    active_subagent_count: number;
    total_subagent_count: number;
}
```

---

### 3. API (FastAPI/Python)

**Files Changed:** 2 files (+149/-1 lines)

#### Models (`models/live_session.py`)

Added subagent state models:

```python
class SubagentStatus(str, Enum):
    RUNNING = "running"
    COMPLETED = "completed"
    ERROR = "error"

class SubagentState(BaseModel):
    agent_id: str
    agent_type: str
    status: SubagentStatus
    transcript_path: Optional[str]
    started_at: datetime
    completed_at: Optional[datetime]
```

Extended `LiveSessionState`:
- Added `subagents: Dict[str, SubagentState]` field
- Added `active_subagent_count` property (counts running subagents)
- Added `total_subagent_count` property (total subagents)
- Updated `from_file()` to parse subagent datetime strings

#### Live Session Tracker (`scripts/live_session_tracker.py`)

Added hook handlers:

- **`add_subagent()`** - Handles `SubagentStart` hook
  - Creates new subagent entry with status `running`
  - Records `agent_id`, `agent_type`, and `started_at`

- **`complete_subagent()`** - Handles `SubagentStop` hook
  - Updates subagent status to `completed`
  - Records `completed_at` and `transcript_path`

- Updated `write_state()` to preserve subagents when updating session state

---

## Data Flow

```
SubagentStart Hook (Claude Code)
    ↓
live_session_tracker.py (add_subagent)
    ↓
~/.claude_karma/live-sessions/{slug}.json
    ↓
/live-sessions API endpoint
    ↓
Frontend LiveSessionSummary
```

## Live Session JSON Structure

After these changes, the live session state file includes:

```json
{
    "session_id": "sess_abc123",
    "state": "LIVE",
    "subagents": {
        "agent-xyz789": {
            "agent_id": "agent-xyz789",
            "agent_type": "Bash",
            "status": "running",
            "transcript_path": null,
            "started_at": "2026-01-24T21:37:02Z",
            "completed_at": null
        },
        "agent-abc123": {
            "agent_id": "agent-abc123",
            "agent_type": "Explore",
            "status": "completed",
            "transcript_path": "~/.claude/projects/-Users-me-repo/sess_abc123/subagents/agent-abc123.jsonl",
            "started_at": "2026-01-24T21:30:00Z",
            "completed_at": "2026-01-24T21:35:00Z"
        }
    }
}
```

## Usage

### Hook Configuration

To enable subagent tracking, configure Claude Code hooks in `~/.claude/settings.json`:

```json
{
    "hooks": {
        "SubagentStart": [
            {
                "matcher": "",
                "hooks": ["python /path/to/live_session_tracker.py"]
            }
        ],
        "SubagentStop": [
            {
                "matcher": "",
                "hooks": ["python /path/to/live_session_tracker.py"]
            }
        ]
    }
}
```

### Frontend Display

The frontend can now display:
- Number of active subagents per session
- Total subagent count
- Individual subagent details (type, status, duration)
- Links to subagent transcripts when available

## Testing

### Captain Hook Tests
```bash
cd captain-hook
pytest tests/test_models.py -v
```

Key test updates:
- Added test data for `SubagentStart`, `PostToolUseFailure`, and `Setup` hooks
- Updated `SubagentStop` test data with new fields
- Verified `HOOK_TYPE_MAP` contains all 13 hooks

### API Tests
```bash
cd api
pytest tests/ -v
```

## Dependencies

- Requires Claude Code 2.1.19+ for new hook support
- Python 3.9+
- Pydantic 2.x
