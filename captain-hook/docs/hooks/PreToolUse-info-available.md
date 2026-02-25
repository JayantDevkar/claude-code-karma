# PreToolUse Hook

Fires **before** a tool is executed. Can block execution or modify tool inputs.

## When It Fires

- Before any tool call (Read, Write, Edit, Bash, Glob, Grep, Task, etc.)
- Before MCP tool calls (`mcp__<server>__<tool>`)
- Can be filtered to specific tools using `match_tools`

## Input JSON (via stdin)

```json
{
  "session_id": "abc123-def456",
  "transcript_path": "/Users/name/.claude/projects/hash/sessions/session-id.jsonl",
  "cwd": "/path/to/current/directory",
  "permission_mode": "default",
  "hook_event_name": "PreToolUse",

  "tool_name": "Write",
  "tool_use_id": "toolu_01ABC123",
  "tool_input": {
    "file_path": "/path/to/file.ts",
    "content": "file content here..."
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
| `hook_event_name` | string | Always `"PreToolUse"` |

### PreToolUse-Specific Fields

| Field | Type | Description |
|-------|------|-------------|
| `tool_name` | string | Name of the tool being called |
| `tool_use_id` | string | Unique identifier for this tool call |
| `tool_input` | object | Tool-specific input parameters |

## Tool Input Examples

### Write Tool
```json
{
  "tool_name": "Write",
  "tool_input": {
    "file_path": "/absolute/path/to/file.ts",
    "content": "full file content..."
  }
}
```

### Edit Tool
```json
{
  "tool_name": "Edit",
  "tool_input": {
    "file_path": "/absolute/path/to/file.ts",
    "old_string": "original text",
    "new_string": "replacement text",
    "replace_all": false
  }
}
```

### Bash Tool
```json
{
  "tool_name": "Bash",
  "tool_input": {
    "command": "npm run build",
    "timeout": 120000,
    "description": "Build the project"
  }
}
```

### Read Tool
```json
{
  "tool_name": "Read",
  "tool_input": {
    "file_path": "/absolute/path/to/file.ts",
    "offset": 0,
    "limit": 2000
  }
}
```

### Glob Tool
```json
{
  "tool_name": "Glob",
  "tool_input": {
    "pattern": "**/*.ts",
    "path": "/project/src"
  }
}
```

### Grep Tool
```json
{
  "tool_name": "Grep",
  "tool_input": {
    "pattern": "function.*export",
    "path": "/project/src",
    "glob": "*.ts"
  }
}
```

### Task Tool (Subagent)
```json
{
  "tool_name": "Task",
  "tool_input": {
    "prompt": "Search for authentication code",
    "subagent_type": "Explore",
    "description": "Find auth code"
  }
}
```

### MCP Tool
```json
{
  "tool_name": "mcp__plane-project-task-manager__list_work_items",
  "tool_input": {
    "project_id": "abc-123",
    "per_page": 50
  }
}
```

## Output Options

### Allow (default)
Exit code 0, no output needed.

### Block Execution
Exit code 2:
```bash
echo "Blocked: Cannot write to protected file" >&2
exit 2
```

### Block with JSON
```json
{
  "hookSpecificOutput": {
    "decision": "block",
    "reason": "File is in protected directory"
  }
}
```

### Auto-Approve (skip permission dialog)
```json
{
  "hookSpecificOutput": {
    "permissionDecision": "allow"
  }
}
```

### Modify Tool Input
```json
{
  "hookSpecificOutput": {
    "permissionDecision": "allow",
    "updatedInput": {
      "file_path": "/sanitized/path/file.ts",
      "content": "modified content..."
    }
  }
}
```

### Deny Permission
```json
{
  "hookSpecificOutput": {
    "permissionDecision": "deny",
    "reason": "User policy prevents this action"
  }
}
```

## Configuration Examples

### Basic Command Hook
```yaml
hooks:
  PreToolUse:
    - command: |
        INPUT=$(cat)
        TOOL=$(echo "$INPUT" | jq -r '.tool_name')
        echo "Tool: $TOOL" >> /tmp/hooks.log
      timeout: 5000
```

### Filter by Tool Name (using matcher)
```yaml
hooks:
  PreToolUse:
    - matcher: "Write|Edit"
      hooks:
        - type: "command"
          command: "./scripts/validate-write.sh"
          timeout: 3000
```

### Block Dangerous Commands
```yaml
hooks:
  PreToolUse:
    - matcher: "Bash"
      hooks:
        - type: "command"
          command: |
            INPUT=$(cat)
            CMD=$(echo "$INPUT" | jq -r '.tool_input.command // ""')
            if echo "$CMD" | grep -qE 'rm -rf|sudo|chmod 777'; then
              echo "Dangerous command blocked" >&2
              exit 2
            fi
          timeout: 1000
```

### MCP Tool Matching
```yaml
hooks:
  PreToolUse:
    - matcher: "mcp__.*"  # regex pattern for all MCP tools
      hooks:
        - type: "command"
          command: "./scripts/log-mcp.sh"
          timeout: 2000
```

### Prompt-Based Hook (LLM)
```yaml
hooks:
  PreToolUse:
    - matcher: "Bash|Write"
      hooks:
        - type: "prompt"
          prompt: |
            Review this tool call for security issues:
            $ARGUMENTS

            Should this be allowed? Respond with decision and reason.
```

## Use Cases

1. **Security Auditing** - Log all file writes and bash commands
2. **Access Control** - Block writes to protected directories
3. **Input Sanitization** - Modify file paths or command arguments
4. **Auto-Approval** - Skip permission dialogs for trusted operations
5. **Rate Limiting** - Track and limit tool usage
6. **MCP Monitoring** - Log all external API calls

## Notes

- Timeout default: 60 seconds for commands, 30 seconds for prompt-based
- All matching hooks run **in parallel**
- Identical commands are **deduplicated** automatically
- First hook to exit 2 blocks the tool
- `updatedInput` must match tool's expected schema
- MCP tools use pattern `mcp__<server>__<tool>`
- Use `matcher` with regex patterns (e.g., `"Edit|Write"`, `"mcp__.*"`)
