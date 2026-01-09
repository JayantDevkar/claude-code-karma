# SubagentStop Hook

Fires when a subagent (spawned via Task tool) finishes. Can force the subagent to continue working.

## When It Fires

- When a subagent completes its task
- Before control returns to the parent agent
- Only fires for Task tool subagents, not the main agent

## Input JSON (via stdin)

```json
{
  "session_id": "abc123-def456",
  "transcript_path": "/Users/name/.claude/projects/hash/sessions/session-id.jsonl",
  "cwd": "/path/to/current/directory",
  "permission_mode": "default",
  "hook_event_name": "SubagentStop",

  "stop_hook_active": false
}
```

## Field Reference

### Common Fields

| Field | Type | Description |
|-------|------|-------------|
| `session_id` | string | Unique session identifier (same as parent) |
| `transcript_path` | string | Path to conversation JSONL |
| `cwd` | string | Current working directory |
| `permission_mode` | enum | Current permission mode |
| `hook_event_name` | string | Always `"SubagentStop"` |

### SubagentStop-Specific Fields

| Field | Type | Description |
|-------|------|-------------|
| `stop_hook_active` | boolean | `true` if subagent is already continuing from a previous hook |

## Difference from Stop Hook

| Aspect | Stop | SubagentStop |
|--------|------|--------------|
| Fires for | Main agent | Task subagents |
| Session ID | Main session | Same as parent |
| Scope | Entire conversation | Single subtask |

## Understanding stop_hook_active

Same as Stop hook - prevents infinite loops:

- `false`: Subagent finished naturally
- `true`: Subagent finished after being told to continue

## Output Options

### Allow Stop (default)
Exit code 0, no output - subagent stops normally.

### Force Continue
```json
{
  "hookSpecificOutput": {
    "decision": "continue",
    "reason": "Subagent needs to complete additional steps"
  }
}
```

## Configuration Examples

### Basic Logging
```yaml
hooks:
  SubagentStop:
    - command: |
        INPUT=$(cat)
        SESSION=$(echo "$INPUT" | jq -r '.session_id')
        echo "[$(date)] Subagent stopped: $SESSION" >> /tmp/subagent-stops.log
      timeout: 2000
```

### Continue Until Exploration Complete
```yaml
hooks:
  SubagentStop:
    - command: |
        INPUT=$(cat)
        ACTIVE=$(echo "$INPUT" | jq -r '.stop_hook_active')

        if [ "$ACTIVE" = "false" ]; then
          # Check if exploration subagent found enough results
          # This would need actual logic based on your use case
          RESULTS_FILE="/tmp/explore-results.json"
          if [ -f "$RESULTS_FILE" ]; then
            COUNT=$(jq '.results | length' "$RESULTS_FILE" 2>/dev/null || echo "0")
            if [ "$COUNT" -lt 5 ]; then
              echo '{"hookSpecificOutput": {"decision": "continue", "reason": "Need more search results - found only '$COUNT'"}}'
            fi
          fi
        fi
      timeout: 10000
```

### Status Tracking
```yaml
hooks:
  SubagentStop:
    - command: |
        INPUT=$(cat)
        export KARMA_SESSION_ID=$(echo "$INPUT" | jq -r '.session_id')
        karma radio report-progress --message "Subagent completed"
      timeout: 3000
```

### Prompt-Based Evaluation (LLM)
```yaml
hooks:
  SubagentStop:
    - type: "prompt"
      prompt: |
        A subagent has finished its task. Review whether the subtask was completed satisfactorily.

        Context:
        $ARGUMENTS

        Consider:
        - Did the subagent accomplish its assigned goal?
        - Is there additional work needed before returning to the parent?
        - Would continuing help or cause unnecessary work?

        Respond with decision: "continue" or "stop" with your reasoning.
```

### Count Subagent Iterations
```yaml
hooks:
  SubagentStop:
    - command: |
        INPUT=$(cat)
        SESSION=$(echo "$INPUT" | jq -r '.session_id')
        ACTIVE=$(echo "$INPUT" | jq -r '.stop_hook_active')

        COUNT_FILE="/tmp/subagent-count-$SESSION"
        COUNT=$(cat "$COUNT_FILE" 2>/dev/null || echo "0")
        echo $((COUNT + 1)) > "$COUNT_FILE"

        echo "[$(date)] Subagent iteration $((COUNT + 1)) (active: $ACTIVE)" >> /tmp/subagent.log

        # Optional: limit iterations
        if [ "$ACTIVE" = "false" ] && [ "$COUNT" -lt 2 ]; then
          # Your continue condition here
          :
        fi
      timeout: 3000
```

### Different Behavior by Subagent Type
```yaml
hooks:
  SubagentStop:
    - command: |
        INPUT=$(cat)
        ACTIVE=$(echo "$INPUT" | jq -r '.stop_hook_active')
        TRANSCRIPT=$(echo "$INPUT" | jq -r '.transcript_path')

        if [ "$ACTIVE" = "false" ]; then
          # Try to determine subagent type from recent transcript
          # This is a heuristic - actual implementation may vary
          LAST_TASK=$(tail -20 "$TRANSCRIPT" | grep -o '"subagent_type":"[^"]*"' | tail -1)

          if echo "$LAST_TASK" | grep -q "Explore"; then
            # Explore agents should be thorough
            echo '{"hookSpecificOutput": {"decision": "continue", "reason": "Ensure exploration is comprehensive"}}'
          fi
        fi
      timeout: 5000
```

### Quality Check Before Returning
```yaml
hooks:
  SubagentStop:
    - command: |
        INPUT=$(cat)
        ACTIVE=$(echo "$INPUT" | jq -r '.stop_hook_active')

        if [ "$ACTIVE" = "false" ]; then
          # Check if subagent made changes that need verification
          if git diff --quiet 2>/dev/null; then
            : # No changes, OK to stop
          else
            # Changes made - maybe verify them?
            CHANGED_FILES=$(git diff --name-only | wc -l)
            if [ "$CHANGED_FILES" -gt 0 ]; then
              echo "[$(date)] Subagent modified $CHANGED_FILES files" >> /tmp/subagent.log
            fi
          fi
        fi
      timeout: 5000
```

## Use Cases

1. **Thorough Exploration** - Ensure search agents find enough results
2. **Quality Control** - Verify subagent output before returning
3. **Progress Tracking** - Log subagent completions
4. **Iteration Control** - Limit or extend subagent work
5. **Multi-step Tasks** - Chain subagent operations
6. **Debugging** - Track subagent behavior in complex workflows

## Notes

- Same session_id as parent agent (not unique per subagent)
- **CRITICAL**: Check `stop_hook_active` to prevent infinite loops
- Subagent scope is narrower than main agent
- Keep hooks fast - affects overall response time
- No direct way to identify which specific subagent stopped
- Timeout default: 60 seconds
- Multiple subagents may trigger this sequentially
