# Elicitation Hook

Fires when an MCP server requests structured input from the user. **CAN block** via exit code 2.

## When It Fires

- When an MCP tool invokes the `elicitation/create` MCP method to ask the user for structured input
- Before the elicitation dialog is shown to the user

## Input JSON (via stdin)

```json
{
  "session_id": "abc123-def456",
  "transcript_path": "/Users/name/.claude/projects/hash/sessions/session-id.jsonl",
  "cwd": "/path/to/current/directory",
  "permission_mode": "default",
  "hook_event_name": "Elicitation",

  "mcp_server": "github",
  "tool_name": "create_issue",
  "request": {
    "title": "string",
    "body": "string"
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
| `hook_event_name` | string | Always `"Elicitation"` |

### Elicitation-Specific Fields

| Field | Type | Description |
|-------|------|-------------|
| `mcp_server` | string | Name of the MCP server making the elicitation request |
| `tool_name` | string | Tool that triggered the elicitation request |
| `request` | object | The form/schema that the MCP server requested input for |

## Output Options

### Allow (default)
Exit code 0, no output. The elicitation dialog is shown to the user.

### Block Elicitation
Exit code 2 with stderr to prevent the dialog (useful for policy enforcement).

## Configuration Example

```yaml
hooks:
  Elicitation:
    - command: |
        INPUT=$(cat)
        SERVER=$(echo "$INPUT" | jq -r '.mcp_server')
        if [[ "$SERVER" == "untrusted-mcp" ]]; then
          echo "Blocked elicitation from $SERVER" >&2
          exit 2
        fi
      timeout: 2000
```

## Use Cases

1. **Policy enforcement** — block elicitations from untrusted MCP servers
2. **Audit logging** — record every elicitation request
3. **Auto-fill** — capture the request schema for future automation

## Notes

- Blocks via exit code 2
- Fires before `ElicitationResult` (which fires after the user responds)
