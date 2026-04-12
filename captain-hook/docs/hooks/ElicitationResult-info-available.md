# ElicitationResult Hook

Fires when the user responds to an MCP elicitation request. **CAN block** via exit code 2.

## When It Fires

- After the user submits a response to an `elicitation/create` MCP request
- Before the response is returned to the MCP server

## Input JSON (via stdin)

```json
{
  "session_id": "abc123-def456",
  "transcript_path": "/Users/name/.claude/projects/hash/sessions/session-id.jsonl",
  "cwd": "/path/to/current/directory",
  "permission_mode": "default",
  "hook_event_name": "ElicitationResult",

  "mcp_server": "github",
  "user_response": {
    "title": "Bug report",
    "body": "Steps to reproduce..."
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
| `hook_event_name` | string | Always `"ElicitationResult"` |

### ElicitationResult-Specific Fields

| Field | Type | Description |
|-------|------|-------------|
| `mcp_server` | string | Name of the MCP server that originally requested the elicitation |
| `user_response` | object | The structured response provided by the user |

## Output Options

### Allow (default)
Exit code 0, no output. The response is delivered to the MCP server.

### Block Delivery
Exit code 2 with stderr to prevent the response from reaching the MCP server.

## Configuration Example

```yaml
hooks:
  ElicitationResult:
    - command: |
        INPUT=$(cat)
        SERVER=$(echo "$INPUT" | jq -r '.mcp_server')
        echo "User responded to $SERVER" >> /tmp/elicitations.log
      timeout: 2000
```

## Use Cases

1. **PII filtering** — block responses that contain sensitive data
2. **Audit logging** — capture user responses for review
3. **Validation** — reject malformed responses before they reach the MCP server

## Notes

- Blocks via exit code 2
- Fires after `Elicitation` (which fires before the dialog is shown)
