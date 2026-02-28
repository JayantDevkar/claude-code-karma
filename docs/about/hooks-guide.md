# Hooks Guide

How Claude Code hooks work and how Claude Karma uses them for live tracking, title generation, and plan approval.

---

## What Are Claude Code Hooks?

Hooks are scripts that Claude Code executes automatically when specific events occur during a session. They run synchronously in the Claude Code process and can either observe events passively or actively block them (returning `"deny"` to reject an action).

Hooks are registered in Claude Code's `settings.json` and can be written in any language. Claude Karma's hooks are written in Python.

---

## The 10 Hook Types

Claude Code defines 10 hook event types. The captain-hook library provides Pydantic models for all of them.

| Hook | Fires When | Can Block? | Common Use |
|------|-----------|------------|------------|
| **PreToolUse** | Before a tool is executed | Yes | Validate or deny tool calls |
| **PostToolUse** | After a tool completes | No | Log tool results, track file changes |
| **UserPromptSubmit** | User submits a message | Yes | Filter prompts, add context |
| **SessionStart** | Session begins | No | Initialize tracking state |
| **SessionEnd** | Session ends | No | Generate titles, finalize state |
| **Stop** | Main agent stops | No | Record completion status |
| **SubagentStop** | A subagent (Task) stops | No | Track subagent outcomes |
| **PreCompact** | Before context compaction | No | Capture pre-compaction state |
| **PermissionRequest** | Permission dialog appears | Yes | Auto-approve or gate actions |
| **Notification** | System notification | No | Forward or log notifications |

**Blocking hooks** (PreToolUse, UserPromptSubmit, PermissionRequest) can return a response that prevents the action from proceeding. Non-blocking hooks can only observe.

---

## Claude Karma's Production Hooks

Claude Karma ships three hook scripts in the `hooks/` directory.

### 1. live_session_tracker.py

**Purpose:** Tracks session state in real time across 8 hook events.

**Events handled:** SessionStart, SessionEnd, Stop, SubagentStart, SubagentStop, PostToolUse, UserPromptSubmit, Notification

**State machine:**

```
STARTING ──> LIVE ──> WAITING ──> STOPPED ──> ENDED
                 \                     |
                  \──> STALE          /
                   (no heartbeat)    /
                    \──────────────/
```

- **STARTING** — Session has begun, no user message yet
- **LIVE** — Actively processing (tool calls, responses)
- **WAITING** — Waiting for user input
- **STOPPED** — Main agent has stopped
- **STALE** — No heartbeat received within timeout
- **ENDED** — Session has formally ended

State is written to `~/.claude_karma/live-sessions/{slug}.json`. The API reads these files to serve the `/live-sessions` endpoint.

### 2. session_title_generator.py

**Purpose:** Automatically generates a descriptive title when a session ends.

**Event handled:** SessionEnd

**Title generation strategy:**
1. Check for git commits made during the session
2. If commits found, derive the title from commit messages
3. If no commits, call Claude Haiku to generate a title from the session summary

Titles are stored in session metadata and displayed in the session browser.

### 3. plan_approval.py

**Purpose:** Gates plan execution by intercepting ExitPlanMode permission requests.

**Event handled:** PermissionRequest (specifically `ExitPlanMode`)

When Claude Code enters plan mode and produces a plan, it fires a PermissionRequest before proceeding. This hook intercepts that request and can approve or deny execution based on configured rules or user preferences.

---

## captain-hook Library

The `captain-hook/` directory contains a standalone Python library providing type-safe Pydantic models for all 10 hook types.

### Usage

```python
from captain_hook import parse_hook_event, PreToolUseHook, SessionStartHook

# Parse any hook event from JSON
hook = parse_hook_event(json_data)

# Type-narrowed access
if isinstance(hook, PreToolUseHook):
    tool_name = hook.tool_name
    tool_input = hook.tool_input
```

### Model Structure

Each hook model inherits from a base and includes:
- `session_id` — UUID of the active session
- `project_path` — Encoded project path
- Hook-specific fields (tool name, message content, etc.)

The library validates all fields at parse time and raises clear errors for malformed hook data.

---

## Installing Hooks

### 1. Copy or Symlink Scripts

```bash
# Symlink (recommended — stays in sync with repo)
ln -s /path/to/claude-karma/hooks/live_session_tracker.py ~/.claude/hooks/
ln -s /path/to/claude-karma/hooks/session_title_generator.py ~/.claude/hooks/
ln -s /path/to/claude-karma/hooks/plan_approval.py ~/.claude/hooks/
```

### 2. Register in settings.json

Add hook registrations to your Claude Code settings file (`~/.claude/settings.json`):

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
      },
      {
        "hooks": [
          {
            "type": "command",
            "command": "python3 ~/.claude/hooks/session_title_generator.py",
            "timeout": 15000
          }
        ]
      }
    ],
    "PermissionRequest": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "python3 ~/.claude/hooks/plan_approval.py",
            "timeout": 10000
          }
        ]
      }
    ]
  }
}
```

The `timeout` value is in milliseconds. If a hook exceeds its timeout, Claude Code kills the process and continues without it.

---

## Writing Custom Hooks

Hooks receive event data as JSON on stdin and can optionally write a JSON response to stdout.

**Basic structure (Python):**

```python
import sys
import json

def main():
    event = json.loads(sys.stdin.read())
    hook_type = event.get("type")

    # Process the event
    # ...

    # For blocking hooks, optionally deny:
    # print(json.dumps({"action": "deny", "reason": "Not allowed"}))

if __name__ == "__main__":
    main()
```

**With captain-hook:**

```python
import sys
from captain_hook import parse_hook_event, PreToolUseHook

def main():
    event = parse_hook_event(json.loads(sys.stdin.read()))

    if isinstance(event, PreToolUseHook):
        if event.tool_name == "Bash" and "rm -rf" in event.tool_input.get("command", ""):
            print(json.dumps({"action": "deny", "reason": "Destructive command blocked"}))

if __name__ == "__main__":
    main()
```

See the captain-hook README in the `captain-hook/` directory for the full API reference.
