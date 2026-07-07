# TeammateIdle Hook

Fires when a teammate becomes idle (awaiting a task). **CAN block** via exit code 2.

> **Experimental:** This hook is gated on `CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1`.

## When It Fires

- When an Agent Teams teammate finishes its current task and has no queued work
- Useful for opportunistic task assignment

## Input JSON (via stdin)

```json
{
  "session_id": "abc123-def456",
  "transcript_path": "/Users/name/.claude/projects/hash/sessions/session-id.jsonl",
  "cwd": "/path/to/current/directory",
  "permission_mode": "default",
  "hook_event_name": "TeammateIdle",

  "agent_id": "agent_idle_001",
  "agent_type": "Explore",
  "team_name": "core-team"
}
```

## Field Reference

### Common Fields

| Field | Type | Description |
|-------|------|-------------|
| `session_id` | string | Unique session identifier |
| `transcript_path` | string | Path to full conversation JSONL |
| `cwd` | string | Current working directory |
| `permission_mode` | enum | Current permission mode |
| `hook_event_name` | string | Always `"TeammateIdle"` |

### TeammateIdle-Specific Fields

| Field | Type | Description |
|-------|------|-------------|
| `agent_id` | string | Unique identifier for the idle agent |
| `agent_type` | string | Type of the idle agent (e.g., `Explore`, `Plan`) |
| `team_name` | string \| null | Name of the team the agent belongs to (if any) |

## Output Options

### Allow Idle (default)
Exit code 0, no output.

### Block Idleness
Exit code 2 with stderr to keep the agent active (e.g., to dispatch new work).

## Configuration Example

```yaml
hooks:
  TeammateIdle:
    - command: ./scripts/maybe-dispatch-task.sh
      timeout: 5000
```

## Use Cases

1. **Opportunistic dispatch** — push queued work to idle teammates
2. **Telemetry** — track idle time per teammate
3. **Auto-shutdown** — block idleness only if there is no more work

## Notes

- Experimental — requires `CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1`
- Blocks via exit code 2
