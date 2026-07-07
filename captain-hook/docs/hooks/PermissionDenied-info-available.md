# PermissionDenied Hook

Fires when **auto mode** denies a tool call. Cannot block execution, but **can request a retry** via JSON output.

## When It Fires

- After Claude Code's auto-mode permission policy rejects a pending tool call
- Distinct from `PermissionRequest` (which fires before showing a dialog) and `PreToolUse` (which fires before any tool runs)

## Input JSON (via stdin)

```json
{
  "session_id": "abc123-def456",
  "transcript_path": "/Users/name/.claude/projects/hash/sessions/session-id.jsonl",
  "cwd": "/path/to/current/directory",
  "permission_mode": "default",
  "hook_event_name": "PermissionDenied",

  "tool_name": "Bash",
  "tool_use_id": "toolu_01ABC123",
  "reason": "Auto mode policy: dangerous command",
  "tool_input": {
    "command": "rm -rf /"
  }
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
| `hook_event_name` | string | Always `"PermissionDenied"` |

### PermissionDenied-Specific Fields

| Field | Type | Description |
|-------|------|-------------|
| `tool_name` | string | Name of the tool whose call was denied |
| `tool_use_id` | string | Unique identifier for the denied tool invocation |
| `reason` | string | Denial reason string explaining why the tool call was rejected |
| `tool_input` | object | Original input parameters of the denied tool call |

## Output Options

### Default (No Retry)
Exit code 0, no output. The denial stands and Claude is informed.

### Request Retry
```json
{
  "hookSpecificOutput": {
    "retry": true
  }
}
```

When `retry` is `true`, Claude Code will re-attempt the tool call (useful after a hook has fixed external state, e.g., re-authenticated, opened a port, etc.).

## Configuration Example

```yaml
hooks:
  PermissionDenied:
    - command: |
        INPUT=$(cat)
        REASON=$(echo "$INPUT" | jq -r '.reason')
        TOOL=$(echo "$INPUT" | jq -r '.tool_name')
        echo "Denied $TOOL: $REASON" >> /tmp/denied.log
      timeout: 2000
```

## Use Cases

1. **Audit denials** — log every blocked tool call for review
2. **Auto-recovery** — fix the underlying issue and request a retry
3. **Alerting** — notify operators when unsafe operations are attempted

## Notes

- Cannot block execution (the denial is already in effect)
- The `retry: true` output asks Claude to attempt the same call again
- Fires once per denied tool call
