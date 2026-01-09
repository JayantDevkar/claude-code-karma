# PostToolUse Hook

Fires **after** a tool has completed execution. Cannot block or modify - used for logging, notifications, and providing feedback to Claude.

## When It Fires

- After any tool completes (success or failure)
- After MCP tool calls complete
- Tool has already executed - cannot be undone

## Input JSON (via stdin)

```json
{
  "session_id": "abc123-def456",
  "transcript_path": "/Users/name/.claude/projects/hash/sessions/session-id.jsonl",
  "cwd": "/path/to/current/directory",
  "permission_mode": "default",
  "hook_event_name": "PostToolUse",

  "tool_name": "Write",
  "tool_use_id": "toolu_01ABC123",
  "tool_input": {
    "file_path": "/path/to/file.ts",
    "content": "file content..."
  },
  "tool_response": "Successfully wrote 150 lines to /path/to/file.ts"
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
| `hook_event_name` | string | Always `"PostToolUse"` |

### PostToolUse-Specific Fields

| Field | Type | Description |
|-------|------|-------------|
| `tool_name` | string | Name of the tool that was called |
| `tool_use_id` | string | Unique identifier for this tool call |
| `tool_input` | object | The original input parameters |
| `tool_response` | string | The tool's output/result |

## Tool Response Examples

### Write Tool Success
```json
{
  "tool_name": "Write",
  "tool_response": "Successfully wrote 45 lines to /path/to/file.ts"
}
```

### Write Tool Error
```json
{
  "tool_name": "Write",
  "tool_response": "Error: Permission denied: /etc/hosts"
}
```

### Bash Tool Success
```json
{
  "tool_name": "Bash",
  "tool_input": {
    "command": "npm run build"
  },
  "tool_response": "> project@1.0.0 build\n> tsc\n\nCompiled successfully."
}
```

### Bash Tool Error
```json
{
  "tool_name": "Bash",
  "tool_input": {
    "command": "npm run build"
  },
  "tool_response": "Error: Command failed with exit code 1\nTypeError: Cannot read property 'x' of undefined"
}
```

### Read Tool
```json
{
  "tool_name": "Read",
  "tool_response": "     1→import { foo } from './bar';\n     2→\n     3→export function main() {\n..."
}
```

### Glob Tool
```json
{
  "tool_name": "Glob",
  "tool_response": "Found 15 files:\n/src/index.ts\n/src/utils.ts\n..."
}
```

### Grep Tool
```json
{
  "tool_name": "Grep",
  "tool_response": "/src/auth.ts:15: export function authenticate()\n/src/auth.ts:42: export function validateToken()"
}
```

### Task Tool (Subagent)
```json
{
  "tool_name": "Task",
  "tool_response": "Agent completed: Found 3 authentication files in /src/auth/..."
}
```

### MCP Tool
```json
{
  "tool_name": "mcp__plane-project-task-manager__list_work_items",
  "tool_response": "{\"items\": [...], \"total\": 25}"
}
```

## Output Options

### Provide Feedback to Claude
stdout is passed back as context:
```bash
echo "Note: This file was also modified by another process"
```

### Silent Logging
```bash
INPUT=$(cat)
echo "$INPUT" >> /tmp/tool-history.jsonl
# No stdout = no feedback to Claude
```

### JSON Feedback
```json
{
  "hookSpecificOutput": {
    "additionalContext": "Warning: Build succeeded but with 3 deprecation warnings"
  }
}
```

## Configuration Examples

### Basic Logging
```yaml
hooks:
  PostToolUse:
    - command: |
        INPUT=$(cat)
        echo "$INPUT" >> /tmp/claude-tools.jsonl
      timeout: 2000
```

### Track File Changes
```yaml
hooks:
  PostToolUse:
    - command: |
        INPUT=$(cat)
        TOOL=$(echo "$INPUT" | jq -r '.tool_name')
        FILE=$(echo "$INPUT" | jq -r '.tool_input.file_path // "N/A"')
        RESULT=$(echo "$INPUT" | jq -r '.tool_response' | head -c 100)
        echo "[$(date)] $TOOL: $FILE -> $RESULT" >> /tmp/file-changes.log
      match_tools: ["Write", "Edit"]
      timeout: 2000
```

### Error Detection & Notification
```yaml
hooks:
  PostToolUse:
    - command: |
        INPUT=$(cat)
        RESPONSE=$(echo "$INPUT" | jq -r '.tool_response')
        if echo "$RESPONSE" | grep -qiE 'error|failed|exception'; then
          TOOL=$(echo "$INPUT" | jq -r '.tool_name')
          osascript -e "display notification \"$TOOL failed\" with title \"Claude Code\""
        fi
      timeout: 3000
```

### Build Result Feedback
```yaml
hooks:
  PostToolUse:
    - command: |
        INPUT=$(cat)
        CMD=$(echo "$INPUT" | jq -r '.tool_input.command // ""')
        RESPONSE=$(echo "$INPUT" | jq -r '.tool_response')

        if echo "$CMD" | grep -q 'npm run build'; then
          WARNINGS=$(echo "$RESPONSE" | grep -c 'warning' || echo "0")
          if [ "$WARNINGS" -gt 0 ]; then
            echo "Build completed with $WARNINGS warnings - consider fixing these"
          fi
        fi
      match_tools: ["Bash"]
      timeout: 5000
```

### Status Reporting (Karma Radio)
```yaml
hooks:
  PostToolUse:
    - command: |
        INPUT=$(cat)
        export KARMA_SESSION_ID=$(echo "$INPUT" | jq -r '.session_id')
        TOOL=$(echo "$INPUT" | jq -r '.tool_name')
        karma radio report-progress --message "Completed $TOOL"
      timeout: 5000
```

### MCP Call Analytics
```yaml
hooks:
  PostToolUse:
    - command: |
        INPUT=$(cat)
        TOOL=$(echo "$INPUT" | jq -r '.tool_name')
        if [[ "$TOOL" == mcp__* ]]; then
          SERVER=$(echo "$TOOL" | cut -d'_' -f3)
          echo "[$(date)] MCP call to $SERVER" >> /tmp/mcp-usage.log
        fi
      timeout: 2000
```

## Use Cases

1. **Audit Logging** - Record all tool executions for compliance
2. **Error Monitoring** - Detect and alert on failures
3. **Progress Tracking** - Update external status systems
4. **Analytics** - Track tool usage patterns
5. **Feedback Loop** - Provide context back to Claude
6. **File Change Tracking** - Monitor what Claude modifies
7. **Build Monitoring** - Track test/build results

## Notes

- Cannot block or modify - tool already executed
- stdout feeds back to Claude as context (use sparingly)
- stderr shown to user in verbose mode
- Timeout default: 60 seconds
- Runs synchronously before Claude continues
- `tool_response` can be very large for Read/Grep operations
- Consider truncating large responses in logs
