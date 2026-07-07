# CwdChanged Hook

Fires when Claude Code's working directory changes mid-session. Cannot block execution.

## When It Fires

- When the user `cd`s to a different directory
- When a tool changes the current working directory
- After git worktree switches that update the cwd

## Input JSON (via stdin)

```json
{
  "session_id": "abc123-def456",
  "transcript_path": "/Users/name/.claude/projects/hash/sessions/session-id.jsonl",
  "cwd": "/Users/me/new_project",
  "permission_mode": "default",
  "hook_event_name": "CwdChanged",

  "old_cwd": "/Users/me/old_project",
  "new_cwd": "/Users/me/new_project"
}
```

## Field Reference

### Common Fields

| Field | Type | Description |
|-------|------|-------------|
| `session_id` | string | Unique session identifier |
| `transcript_path` | string | Path to full conversation JSONL |
| `cwd` | string | Current working directory (matches `new_cwd` after the change) |
| `permission_mode` | enum | Current permission mode |
| `hook_event_name` | string | Always `"CwdChanged"` |

### CwdChanged-Specific Fields

| Field | Type | Description |
|-------|------|-------------|
| `old_cwd` | string | Previous working directory before the change |
| `new_cwd` | string | New working directory after the change |

## Output Options

CwdChanged **cannot block** — it is purely observational.

## Configuration Example

```yaml
hooks:
  CwdChanged:
    - command: |
        INPUT=$(cat)
        OLD=$(echo "$INPUT" | jq -r '.old_cwd')
        NEW=$(echo "$INPUT" | jq -r '.new_cwd')
        echo "$(date): $OLD -> $NEW" >> /tmp/cwd_history.log
      timeout: 2000
```

## Use Cases

1. **Navigation tracking** — record movement across projects
2. **Per-directory environment switching** — react to project context changes
3. **Audit logs** — capture working directory history for compliance

## Notes

- Cannot block execution (exit code is ignored)
- The base hook `cwd` field reflects the **new** directory after the change
