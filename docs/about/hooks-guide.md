# Hooks Guide

How Claude Code hooks work and how to enable real-time session tracking.

## What are Claude Code hooks?

Hooks are scripts that Claude Code automatically executes when events happen during a session. They run in the Claude Code process and can either observe events or actively block them.

You register hooks in Claude Code's `settings.json`. They can be written in any language. Claude Code Karma's hooks are Python scripts.

## The 10 hook types

Claude Code defines 10 hook event types. Here are the main ones:

| Hook | Fires When | Can Block? |
|------|-----------|------------|
| **SessionStart** | Session begins | No |
| **SessionEnd** | Session ends | No |
| **UserPromptSubmit** | User submits a message | Yes |
| **PostToolUse** | Tool call completes | No |
| **PreToolUse** | Before tool executes | Yes |
| **Stop** | Main agent stops | No |
| **SubagentStart** | Task agent spawns | No |
| **SubagentStop** | Task agent stops | No |
| **PreCompact** | Before context compaction | No |
| **PermissionRequest** | Permission dialog appears | Yes |

Blocking hooks can return a response that prevents the action. Non-blocking hooks can only observe.

## Production Hooks in Claude Code Karma

Claude Code Karma ships two production hooks:

### 1. live_session_tracker.py

**Purpose:** Track session state in real time.

**Events handled:** SessionStart, SessionEnd, Stop, SubagentStart, SubagentStop, PostToolUse, UserPromptSubmit, Notification

**What it does:**
- Tracks the session state machine (STARTING → LIVE → WAITING → STOPPED → ENDED)
- Writes state to `~/.claude_karma/live-sessions/{slug}.json`
- API reads this to show live session status in the dashboard

**State machine:**
- **STARTING** — Session has begun, no user message yet
- **LIVE** — Actively processing (tool calls, responses)
- **WAITING** — Waiting for user input
- **STOPPED** — Main agent has stopped
- **STALE** — No heartbeat for 30+ minutes
- **ENDED** — Session formally ended

### 2. session_title_generator.py

**Purpose:** Generate descriptive titles for sessions.

**Event handled:** SessionEnd

**How it works:**
1. Checks for git commits made during the session
2. If commits exist, derives the title from commit messages
3. If no commits, calls Claude Haiku to generate a title from the session summary

Titles appear in the session browser and dashboard so you can quickly find sessions.

### 3. plan_approval.py (Reference Only)

This script is kept as a reference implementation but is **not production-ready**. It requires API endpoints for plan approval that haven't been implemented yet. Do not register this hook — it will block all ExitPlanMode calls. We'll document it when the approval feature is built.

## Captain-Hook Library

The `captain-hook/` directory contains a standalone Python library with type-safe Pydantic models for all 10 hook types.

**Use it to parse hook events:**

```python
from captain_hook import parse_hook_event, PreToolUseHook

# Parse any hook event
hook = parse_hook_event(json_data)

# Type-narrowed access
if isinstance(hook, PreToolUseHook):
    tool_name = hook.tool_name
    tool_input = hook.tool_input
```

See the captain-hook README for the full API reference.

## Installing Hooks

### Step 1: Symlink the Hook Scripts

```bash
ln -s /path/to/claude-karma/hooks/live_session_tracker.py ~/.claude/hooks/
ln -s /path/to/claude-karma/hooks/session_title_generator.py ~/.claude/hooks/
```

(Symlinks are recommended — they stay in sync with the repo.)

### Step 2: Register in settings.json

Add hook registrations to `~/.claude/settings.json`. The hooks need to be registered for specific events:

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
    ]
  }
}
```

The `timeout` value is in milliseconds. If a hook exceeds its timeout, Claude Code kills it and continues.

## Writing Custom Hooks

Hooks receive event data as JSON on stdin and can optionally write a JSON response to stdout.

**Basic structure:**

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

**Using captain-hook for type safety:**

```python
import sys
import json
from captain_hook import parse_hook_event, PreToolUseHook

def main():
    event = parse_hook_event(json.loads(sys.stdin.read()))

    if isinstance(event, PreToolUseHook):
        if event.tool_name == "Bash" and "rm -rf" in event.tool_input.get("command", ""):
            print(json.dumps({"action": "deny", "reason": "Destructive command blocked"}))

if __name__ == "__main__":
    main()
```

## Verification

After installation, verify hooks are working by checking the **Hooks** page in the dashboard. You should see hook execution logs and recent events.

Also check the live sessions page — if hooks are working, you should see real-time session state for active sessions.
