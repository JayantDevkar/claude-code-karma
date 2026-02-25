# PermissionRequest Hook

Fires when Claude shows a permission dialog to the user. Can automatically allow or deny actions.

## When It Fires

- When Claude needs permission for sensitive operations
- Before displaying the permission dialog to user
- Can intercept and respond automatically

## Input JSON (via stdin)

```json
{
  "session_id": "abc123-def456",
  "transcript_path": "/Users/name/.claude/projects/hash/sessions/session-id.jsonl",
  "cwd": "/path/to/current/directory",
  "permission_mode": "default",
  "hook_event_name": "PermissionRequest",

  "notification_type": "permission_prompt",
  "message": "Claude wants to run: npm run build"
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
| `hook_event_name` | string | Always `"PermissionRequest"` |

### PermissionRequest-Specific Fields

| Field | Type | Description |
|-------|------|-------------|
| `notification_type` | string | Type of permission request |
| `message` | string | The permission prompt text |

### Notification Types

| Type | Description |
|------|-------------|
| `permission_prompt` | General permission request |

## Output Options

### Show Dialog (default)
Exit code 0, no output - user sees the permission dialog.

### Auto-Allow
```json
{
  "hookSpecificOutput": {
    "permissionDecision": "allow"
  }
}
```

### Auto-Deny
```json
{
  "hookSpecificOutput": {
    "permissionDecision": "deny",
    "reason": "This operation is not permitted by policy"
  }
}
```

### Block with stderr
```bash
echo "Operation blocked by security policy" >&2
exit 2
```

## Configuration Examples

### Log All Permission Requests
```yaml
hooks:
  PermissionRequest:
    - command: |
        INPUT=$(cat)
        SESSION=$(echo "$INPUT" | jq -r '.session_id')
        MESSAGE=$(echo "$INPUT" | jq -r '.message')
        echo "[$(date)] Permission requested: $MESSAGE" >> /tmp/permissions.log
      timeout: 2000
```

### Auto-Allow Safe Commands
```yaml
hooks:
  PermissionRequest:
    - command: |
        INPUT=$(cat)
        MESSAGE=$(echo "$INPUT" | jq -r '.message')

        # Auto-allow common safe operations
        if echo "$MESSAGE" | grep -qE 'npm (run (build|test|lint)|install)'; then
          echo '{"hookSpecificOutput": {"permissionDecision": "allow"}}'
        elif echo "$MESSAGE" | grep -qE 'git (status|diff|log|branch)'; then
          echo '{"hookSpecificOutput": {"permissionDecision": "allow"}}'
        fi
        # If no output, shows normal dialog
      timeout: 2000
```

### Block Dangerous Operations
```yaml
hooks:
  PermissionRequest:
    - command: |
        INPUT=$(cat)
        MESSAGE=$(echo "$INPUT" | jq -r '.message')

        # Block dangerous patterns
        if echo "$MESSAGE" | grep -qE 'rm -rf|sudo|chmod 777|curl.*\|.*sh'; then
          echo '{"hookSpecificOutput": {"permissionDecision": "deny", "reason": "Blocked by security policy"}}'
        fi
      timeout: 2000
```

### Project-Specific Allow List
```yaml
hooks:
  PermissionRequest:
    - command: |
        INPUT=$(cat)
        MESSAGE=$(echo "$INPUT" | jq -r '.message')

        # Load project-specific allow list
        ALLOW_FILE=".claude-allowed-commands"
        if [ -f "$ALLOW_FILE" ]; then
          while IFS= read -r pattern; do
            if echo "$MESSAGE" | grep -qE "$pattern"; then
              echo '{"hookSpecificOutput": {"permissionDecision": "allow"}}'
              exit 0
            fi
          done < "$ALLOW_FILE"
        fi
      timeout: 3000
```

### Time-Based Permissions
```yaml
hooks:
  PermissionRequest:
    - command: |
        INPUT=$(cat)
        MESSAGE=$(echo "$INPUT" | jq -r '.message')

        # Auto-allow during work hours, require approval otherwise
        HOUR=$(date +%H)
        if [ "$HOUR" -ge 9 ] && [ "$HOUR" -lt 18 ]; then
          # Work hours - auto-allow builds and tests
          if echo "$MESSAGE" | grep -qE 'npm run (build|test)'; then
            echo '{"hookSpecificOutput": {"permissionDecision": "allow"}}'
          fi
        fi
      timeout: 2000
```

### Prompt-Based Decision (LLM)
```yaml
hooks:
  PermissionRequest:
    - type: "prompt"
      prompt: |
        A permission is being requested:

        $ARGUMENTS

        Evaluate this request:
        - Is this a safe, routine development operation?
        - Could this cause damage if executed incorrectly?
        - Is this within normal development workflow?

        Respond with permissionDecision: "allow" or "deny" with reasoning.
```

### Notification for Denied Requests
```yaml
hooks:
  PermissionRequest:
    - command: |
        INPUT=$(cat)
        MESSAGE=$(echo "$INPUT" | jq -r '.message')

        # Block and notify for certain operations
        if echo "$MESSAGE" | grep -qE 'delete|remove|drop'; then
          osascript -e "display notification \"Blocked: $MESSAGE\" with title \"Claude Code Security\""
          echo '{"hookSpecificOutput": {"permissionDecision": "deny", "reason": "Destructive operations require manual approval"}}'
        fi
      timeout: 3000
```

### Auto-Allow in CI/Automation
```yaml
hooks:
  PermissionRequest:
    - command: |
        # In CI environments, auto-allow everything
        if [ -n "$CI" ] || [ -n "$GITHUB_ACTIONS" ]; then
          echo '{"hookSpecificOutput": {"permissionDecision": "allow"}}'
        fi
      timeout: 1000
```

### File Operation Permissions
```yaml
hooks:
  PermissionRequest:
    - command: |
        INPUT=$(cat)
        MESSAGE=$(echo "$INPUT" | jq -r '.message')

        # Auto-allow writes to specific directories
        if echo "$MESSAGE" | grep -qE 'Write.*/(src|test|lib)/'; then
          echo '{"hookSpecificOutput": {"permissionDecision": "allow"}}'
        fi

        # Block writes to sensitive locations
        if echo "$MESSAGE" | grep -qE 'Write.*/(\.|config|env|secret)'; then
          echo '{"hookSpecificOutput": {"permissionDecision": "deny", "reason": "Cannot write to sensitive files"}}'
        fi
      timeout: 2000
```

### Rate Limiting
```yaml
hooks:
  PermissionRequest:
    - command: |
        INPUT=$(cat)
        SESSION=$(echo "$INPUT" | jq -r '.session_id')

        # Track permission count
        COUNT_FILE="/tmp/permissions-$SESSION"
        COUNT=$(cat "$COUNT_FILE" 2>/dev/null || echo "0")
        echo $((COUNT + 1)) > "$COUNT_FILE"

        # After 20 permissions, require manual approval
        if [ "$COUNT" -gt 20 ]; then
          echo "[$(date)] Permission limit reached" >> /tmp/permissions.log
          # Don't auto-allow anymore - let user decide
        fi
      timeout: 2000
```

## Use Cases

1. **Auto-Approve Safe Operations** - Skip dialogs for routine tasks
2. **Block Dangerous Commands** - Prevent destructive operations
3. **Security Policy Enforcement** - Apply organization rules
4. **CI/Automation** - Enable unattended execution
5. **Audit Logging** - Track all permission requests
6. **Rate Limiting** - Limit auto-approvals
7. **Time-Based Rules** - Different policies for work hours

## Notes

- Hook decides before user sees dialog
- `permissionDecision: "allow"` skips the dialog entirely
- `permissionDecision: "deny"` rejects without user input
- No output = normal dialog shown
- Timeout default: 60 seconds
- Keep hooks fast - affects UX
- Consider security implications of auto-allow
- Prompt-based hooks use Haiku for evaluation
