# TaskCreated Hook

Fires when a task is created in an Agent Team. **CAN block** via `{"continue": false}`.

> **Experimental:** This hook is gated on `CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1`.

## When It Fires

- After a teammate creates a new task in the team's task list
- Before the task is dispatched to its assigned teammate

## Input JSON (via stdin)

```json
{
  "session_id": "abc123-def456",
  "transcript_path": "/Users/name/.claude/projects/hash/sessions/session-id.jsonl",
  "cwd": "/path/to/current/directory",
  "permission_mode": "default",
  "hook_event_name": "TaskCreated",

  "task_id": "task_001",
  "task_subject": "Refactor auth module",
  "task_description": "Split auth.py into smaller files",
  "teammate_name": "Alice",
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
| `hook_event_name` | string | Always `"TaskCreated"` |

### TaskCreated-Specific Fields

| Field | Type | Description |
|-------|------|-------------|
| `task_id` | string | Unique identifier for the created task |
| `task_subject` | string | Short subject/title of the task |
| `task_description` | string \| null | Longer task description (if provided) |
| `teammate_name` | string \| null | Name of the assignee teammate (if any) |
| `team_name` | string | Name of the team where the task was created |

## Output Options

### Allow (default)
Exit code 0, no output.

### Block Task Creation
```json
{
  "continue": false,
  "stopReason": "Task creation rejected by policy"
}
```

## Configuration Example

```yaml
hooks:
  TaskCreated:
    - command: ./scripts/audit-task-created.sh
      timeout: 3000
```

## Use Cases

1. **Task auditing** — log every created task for the team
2. **Policy enforcement** — block tasks that violate rules (e.g., assigning to a paused teammate)
3. **External tracking** — sync new tasks to an issue tracker

## Notes

- Experimental — requires `CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1`
- Blocks via `{"continue": false}` in the JSON output
