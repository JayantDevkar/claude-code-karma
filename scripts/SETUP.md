# Live Session Tracking Setup

Track Claude Code session states in real-time using hooks.

## Session States

| State | Description |
|-------|-------------|
| `LIVE` | Session actively running (tool execution, prompt processing) |
| `WAITING` | Claude needs user input (AskUserQuestion, permission dialog) |
| `STOPPED` | Agent finished but session still open |
| `STALE` | User has been idle for 60+ seconds |
| `ENDED` | Session terminated |

## Quick Setup

### 1. Install the tracker script

```bash
# Create bin directory
mkdir -p ~/.local/bin

# Copy the tracker script
cp live_session_tracker.py ~/.local/bin/claude-karma-tracker
chmod +x ~/.local/bin/claude-karma-tracker
```

### 2. Configure hooks (choose one method)

#### Option A: Project-level hooks (recommended)

Copy `hooks.yaml` to your project's `.claude/` directory:

```bash
# In any project you want to track
mkdir -p .claude
cp /path/to/claude-karma/api/scripts/hooks.yaml .claude/hooks.yaml
```

The `hooks.yaml` uses the `cat |` pattern to pipe hook data to the tracker:

```yaml
hooks:
  SessionStart:
    - command: |
        cat | python3 ~/.local/bin/claude-karma-tracker
      timeout: 2000

  UserPromptSubmit:
    - command: |
        cat | python3 ~/.local/bin/claude-karma-tracker
      timeout: 2000

  PostToolUse:
    - command: |
        cat | python3 ~/.local/bin/claude-karma-tracker
      timeout: 2000

  Notification:
    - command: |
        cat | python3 ~/.local/bin/claude-karma-tracker
      timeout: 2000

  Stop:
    - command: |
        cat | python3 ~/.local/bin/claude-karma-tracker
      timeout: 2000

  SubagentStart:
    - command: |
        cat | python3 ~/.local/bin/claude-karma-tracker
      timeout: 2000

  SubagentStop:
    - command: |
        cat | python3 ~/.local/bin/claude-karma-tracker
      timeout: 2000

  SessionEnd:
    - command: |
        cat | python3 ~/.local/bin/claude-karma-tracker
      timeout: 2000
```

#### Option B: Global hooks (all projects)

Add to `~/.claude/settings.json`:

```json
{
  "hooks": {
    "SessionStart": [{ "command": "cat | python3 ~/.local/bin/claude-karma-tracker", "timeout": 2000 }],
    "UserPromptSubmit": [{ "command": "cat | python3 ~/.local/bin/claude-karma-tracker", "timeout": 2000 }],
    "PostToolUse": [{ "command": "cat | python3 ~/.local/bin/claude-karma-tracker", "timeout": 2000 }],
    "Notification": [{ "command": "cat | python3 ~/.local/bin/claude-karma-tracker", "timeout": 2000 }],
    "Stop": [{ "command": "cat | python3 ~/.local/bin/claude-karma-tracker", "timeout": 2000 }],
    "SessionEnd": [{ "command": "cat | python3 ~/.local/bin/claude-karma-tracker", "timeout": 2000 }],
    "SubagentStart": [{ "command": "cat | python3 ~/.local/bin/claude-karma-tracker", "timeout": 2000 }],
    "SubagentStop": [{ "command": "cat | python3 ~/.local/bin/claude-karma-tracker", "timeout": 2000 }]
  }
}
```

## How It Works

Session state is written to `~/.claude_karma/live-sessions/{slug}.json`:

```json
{
  "session_id": "abc123-def456",
  "slug": "eager-stirring-moore",
  "session_ids": ["abc123-def456"],
  "state": "LIVE",
  "cwd": "/path/to/project",
  "transcript_path": "/Users/.../.claude/projects/.../session.jsonl",
  "permission_mode": "default",
  "last_hook": "PostToolUse",
  "updated_at": "2026-01-18T04:30:00.000000+00:00",
  "started_at": "2026-01-18T04:00:00.000000+00:00",
  "end_reason": null,
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
      "transcript_path": "~/.claude/projects/-Users-me-repo/abc123/subagents/agent-abc123.jsonl",
      "started_at": "2026-01-28T12:30:00Z",
      "completed_at": "2026-01-28T12:35:00Z"
    }
  }
}
```

## Hook → State Mapping

| Hook | State | Condition |
|------|-------|-----------|
| `SessionStart` | STARTING | Always (session started, JSONL may not exist yet) |
| `UserPromptSubmit` | LIVE | Always (prompt submitted, actively processing) |
| `PostToolUse` | LIVE | Always (indicates active work) |
| `Notification` | WAITING | When `notification_type` is `permission_prompt` (needs input) |
| `Notification` | STALE | When `notification_type` is `idle_prompt` (user idle 60s+, only if not WAITING) |
| `Stop` | STOPPED | When `stop_hook_active` is `false` |
| `SubagentStart` | - | Adds subagent entry with status `running` |
| `SubagentStop` | - | Updates subagent entry with status `completed` |
| `SessionEnd` | ENDED | Always (includes `end_reason`) |

## API Endpoints

The Claude Karma API exposes these endpoints for live session data:

| Endpoint | Description |
|----------|-------------|
| `GET /live-sessions` | List all tracked sessions |
| `GET /live-sessions/active` | List active (non-ended) sessions |
| `GET /live-sessions/{session_id}` | Get specific session state |
| `DELETE /live-sessions/{session_id}` | Clean up ended session |

## Known Limitations

- `elicitation_dialog` notification type doesn't fire for `AskUserQuestion` tool calls
- See [anthropics/claude-code#13830](https://github.com/anthropics/claude-code/issues/13830) for feature request

## Troubleshooting

### Check if hooks are firing

Add debug logging to the tracker:

```python
# Add after imports in live_session_tracker.py
def log_debug(msg):
    with open(Path.home() / ".claude_karma" / "hooks-debug.log", "a") as f:
        f.write(f"{datetime.now():%H:%M:%S} {msg}\n")
```

### Verify state files

```bash
# List all session states
ls ~/.claude_karma/live-sessions/

# View current session
cat ~/.claude_karma/live-sessions/*.json | jq .

# Watch for changes
watch -n1 'cat ~/.claude_karma/live-sessions/*.json | jq .'
```
