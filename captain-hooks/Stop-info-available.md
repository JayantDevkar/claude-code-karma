# Stop Hook

Fires when the main Claude agent finishes responding. Can force Claude to continue working.

## When It Fires

- When Claude completes a response and stops
- Before control returns to the user
- Does NOT fire for subagents (see SubagentStop)

## Input JSON (via stdin)

```json
{
  "session_id": "abc123-def456",
  "transcript_path": "/Users/name/.claude/projects/hash/sessions/session-id.jsonl",
  "cwd": "/path/to/current/directory",
  "permission_mode": "default",
  "hook_event_name": "Stop",

  "stop_hook_active": false
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
| `hook_event_name` | string | Always `"Stop"` |

### Stop-Specific Fields

| Field | Type | Description |
|-------|------|-------------|
| `stop_hook_active` | boolean | `true` if Claude is already continuing due to a previous Stop hook |

## Understanding stop_hook_active

This field prevents infinite loops:

- `false` (first stop): Claude finished naturally
- `true` (subsequent stop): Claude finished after being told to continue

When `stop_hook_active` is `true`, the hook should generally NOT force another continue, or you risk an infinite loop.

## Output Options

### Allow Stop (default)
Exit code 0, no output - Claude stops normally.

### Force Continue
Return JSON to make Claude continue:
```json
{
  "hookSpecificOutput": {
    "decision": "continue",
    "reason": "Task not yet complete - tests still failing"
  }
}
```

### Conditional Continue
```bash
INPUT=$(cat)
ACTIVE=$(echo "$INPUT" | jq -r '.stop_hook_active')

if [ "$ACTIVE" = "false" ]; then
  # Check if work is complete
  if ! npm test > /dev/null 2>&1; then
    echo '{"hookSpecificOutput": {"decision": "continue", "reason": "Tests are still failing"}}'
  fi
fi
```

## Configuration Examples

### Basic Stop Logging
```yaml
hooks:
  Stop:
    - command: |
        INPUT=$(cat)
        SESSION=$(echo "$INPUT" | jq -r '.session_id')
        echo "[$(date)] Agent stopped: $SESSION" >> /tmp/claude-stops.log
      timeout: 2000
```

### Continue Until Tests Pass
```yaml
hooks:
  Stop:
    - command: |
        INPUT=$(cat)
        ACTIVE=$(echo "$INPUT" | jq -r '.stop_hook_active')

        # Only check on first stop to prevent infinite loop
        if [ "$ACTIVE" = "false" ]; then
          if ! npm test > /dev/null 2>&1; then
            echo '{"hookSpecificOutput": {"decision": "continue", "reason": "Tests are failing - please fix them"}}'
          fi
        fi
      timeout: 30000
```

### Continue Until Build Succeeds
```yaml
hooks:
  Stop:
    - command: |
        INPUT=$(cat)
        ACTIVE=$(echo "$INPUT" | jq -r '.stop_hook_active')

        if [ "$ACTIVE" = "false" ]; then
          if ! npm run build > /dev/null 2>&1; then
            echo '{"hookSpecificOutput": {"decision": "continue", "reason": "Build is failing - please fix compilation errors"}}'
          fi
        fi
      timeout: 60000
```

### Status Tracking (Karma Radio)
```yaml
hooks:
  Stop:
    - command: |
        INPUT=$(cat)
        export KARMA_SESSION_ID=$(echo "$INPUT" | jq -r '.session_id')
        karma radio set-status completed --message "Session completed"
      timeout: 5000
```

### Continue if TODO Items Remain
```yaml
hooks:
  Stop:
    - command: |
        INPUT=$(cat)
        ACTIVE=$(echo "$INPUT" | jq -r '.stop_hook_active')
        TRANSCRIPT=$(echo "$INPUT" | jq -r '.transcript_path')

        if [ "$ACTIVE" = "false" ]; then
          # Check if there are uncompleted TODOs in the transcript
          # This is a simplified check - real implementation would parse JSONL
          PENDING=$(grep -c '"status":"pending"' "$TRANSCRIPT" 2>/dev/null || echo "0")
          if [ "$PENDING" -gt 0 ]; then
            echo "{\"hookSpecificOutput\": {\"decision\": \"continue\", \"reason\": \"$PENDING TODO items still pending\"}}"
          fi
        fi
      timeout: 5000
```

### Prompt-Based Continue Decision (LLM)
```yaml
hooks:
  Stop:
    - type: "prompt"
      prompt: |
        Claude has stopped working. Review the session to determine if the task is complete.

        Session context:
        $ARGUMENTS

        Consider:
        - Was the original request fulfilled?
        - Are there any obvious next steps Claude should take?
        - Did Claude stop prematurely?

        If the task seems incomplete, respond with decision: "continue" and explain why.
        If complete, respond with decision: "stop".
```

### Notify User on Stop
```yaml
hooks:
  Stop:
    - command: |
        # macOS notification when Claude finishes
        osascript -e 'display notification "Claude finished working" with title "Claude Code"'
      timeout: 2000
```

### Check Lint Before Stopping
```yaml
hooks:
  Stop:
    - command: |
        INPUT=$(cat)
        ACTIVE=$(echo "$INPUT" | jq -r '.stop_hook_active')

        if [ "$ACTIVE" = "false" ]; then
          # Check if there are lint errors in modified files
          LINT_ERRORS=$(npm run lint 2>&1 | grep -c "error" || echo "0")
          if [ "$LINT_ERRORS" -gt 0 ]; then
            echo "{\"hookSpecificOutput\": {\"decision\": \"continue\", \"reason\": \"Found $LINT_ERRORS lint errors - please fix them\"}}"
          fi
        fi
      timeout: 30000
```

### Time-Limited Continue
```yaml
hooks:
  Stop:
    - command: |
        INPUT=$(cat)
        ACTIVE=$(echo "$INPUT" | jq -r '.stop_hook_active')
        SESSION=$(echo "$INPUT" | jq -r '.session_id')

        # Track how many times we've continued
        COUNT_FILE="/tmp/claude-continue-$SESSION"
        COUNT=$(cat "$COUNT_FILE" 2>/dev/null || echo "0")

        if [ "$ACTIVE" = "false" ] && [ "$COUNT" -lt 3 ]; then
          # Some condition to continue
          if [ -f ".claude-continue" ]; then
            echo $((COUNT + 1)) > "$COUNT_FILE"
            echo '{"hookSpecificOutput": {"decision": "continue", "reason": "Continue marker present"}}'
          fi
        fi
      timeout: 5000
```

## Use Cases

1. **Quality Gates** - Continue until tests/lint/build pass
2. **Task Completion** - Continue until all TODOs are done
3. **Autonomous Agents** - Let Claude work through complex tasks
4. **Status Tracking** - Update external systems when Claude stops
5. **Notifications** - Alert user when work completes
6. **Loop Prevention** - Use `stop_hook_active` to prevent infinite loops

## Notes

- **CRITICAL**: Always check `stop_hook_active` to prevent infinite loops
- Only the first hook returning `continue` takes effect
- Long-running checks should have appropriate timeouts
- Timeout default: 60 seconds
- Use sparingly - forcing continue can lead to runaway sessions
- Consider max iteration limits for safety
- Prompt-based hooks use Haiku for evaluation
