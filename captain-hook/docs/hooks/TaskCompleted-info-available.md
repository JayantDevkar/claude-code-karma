# TaskCompleted Hook

Fires when a task is completed in an Agent Team. **CAN block** via `{"continue": false}`.

> **Experimental:** This hook is gated on `CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1`.

## When It Fires

- After a teammate marks a task as complete
- Before downstream consumers (other tasks, reviewers) are notified

## Input JSON (via stdin)

```json
{
  "session_id": "abc123-def456",
  "transcript_path": "/Users/name/.claude/projects/hash/sessions/session-id.jsonl",
  "cwd": "/path/to/current/directory",
  "permission_mode": "default",
  "hook_event_name": "TaskCompleted",

  "task_id": "task_002",
  "task_subject": "Add tests",
  "task_description": "Cover edge cases",
  "teammate_name": "Bob",
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
| `hook_event_name` | string | Always `"TaskCompleted"` |

### TaskCompleted-Specific Fields

| Field | Type | Description |
|-------|------|-------------|
| `task_id` | string | Unique identifier for the completed task |
| `task_subject` | string | Short subject/title of the task |
| `task_description` | string \| null | Longer task description (if provided) |
| `teammate_name` | string \| null | Name of the teammate that completed the task |
| `team_name` | string | Name of the team where the task was completed |

## Output Options

### Allow (default)
Exit code 0, no output.

### Block Completion
```json
{
  "continue": false,
  "stopReason": "Task completion blocked: missing required tests"
}
```

## Configuration Example

```yaml
hooks:
  TaskCompleted:
    - command: ./scripts/verify-task-done.sh
      timeout: 5000
```

## Use Cases

1. **Quality gates** — verify tests/lint pass before allowing completion
2. **External sync** — close issues in an external tracker
3. **Metrics** — record task throughput per teammate

## Notes

- Experimental — requires `CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1`
- Blocks via `{"continue": false}` in the JSON output
