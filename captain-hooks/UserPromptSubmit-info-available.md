# UserPromptSubmit Hook

Fires when the user submits a message/prompt. Can block the message or add context.

## When It Fires

- When user presses Enter to submit a prompt
- Before Claude processes the message
- Does NOT fire for system messages or hook feedback

## Input JSON (via stdin)

```json
{
  "session_id": "abc123-def456",
  "transcript_path": "/Users/name/.claude/projects/hash/sessions/session-id.jsonl",
  "cwd": "/path/to/current/directory",
  "permission_mode": "default",
  "hook_event_name": "UserPromptSubmit",

  "prompt": "Please fix the bug in the authentication module"
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
| `hook_event_name` | string | Always `"UserPromptSubmit"` |

### UserPromptSubmit-Specific Fields

| Field | Type | Description |
|-------|------|-------------|
| `prompt` | string | The full text of the user's message |

## Prompt Examples

### Simple Command
```json
{
  "prompt": "Run the tests"
}
```

### Multi-line Prompt
```json
{
  "prompt": "I need to implement a new feature:\n\n1. Add user authentication\n2. Create login page\n3. Add session management"
}
```

### With File Reference
```json
{
  "prompt": "Fix the bug in @src/auth/login.ts"
}
```

### Slash Command
```json
{
  "prompt": "/commit"
}
```

## Output Options

### Allow (default)
Exit code 0, no output or empty stdout.

### Add Context
stdout is prepended to the conversation:
```bash
echo "Current git branch: $(git branch --show-current)"
echo "Last commit: $(git log -1 --oneline)"
```

### Add Context via JSON
```json
{
  "hookSpecificOutput": {
    "additionalContext": "Project status: 3 failing tests, last deploy: 2 hours ago"
  }
}
```

### Block the Message
Exit code 2:
```bash
echo "Message blocked: Please use /help for available commands" >&2
exit 2
```

### Block with JSON
```json
{
  "hookSpecificOutput": {
    "decision": "block",
    "reason": "This action requires administrator approval"
  }
}
```

## Configuration Examples

### Add Git Context
```yaml
hooks:
  UserPromptSubmit:
    - command: |
        echo "Git Status:"
        git status --short 2>/dev/null || echo "Not a git repo"
        echo ""
        echo "Recent commits:"
        git log --oneline -3 2>/dev/null || true
      timeout: 5000
```

### Add Project Context
```yaml
hooks:
  UserPromptSubmit:
    - command: |
        if [ -f "package.json" ]; then
          echo "Node project: $(jq -r '.name' package.json)"
          echo "Scripts: $(jq -r '.scripts | keys | join(", ")' package.json)"
        fi
      timeout: 3000
```

### Block Specific Keywords
```yaml
hooks:
  UserPromptSubmit:
    - command: |
        INPUT=$(cat)
        PROMPT=$(echo "$INPUT" | jq -r '.prompt')

        # Block requests for certain actions
        if echo "$PROMPT" | grep -qiE 'delete all|drop database|rm -rf /'; then
          echo "Dangerous operation blocked for safety" >&2
          exit 2
        fi
      timeout: 2000
```

### Log All Prompts
```yaml
hooks:
  UserPromptSubmit:
    - command: |
        INPUT=$(cat)
        SESSION=$(echo "$INPUT" | jq -r '.session_id')
        PROMPT=$(echo "$INPUT" | jq -r '.prompt')
        echo "[$(date)] [$SESSION] $PROMPT" >> /tmp/claude-prompts.log
      timeout: 1000
```

### Add Issue Context
```yaml
hooks:
  UserPromptSubmit:
    - command: |
        INPUT=$(cat)
        PROMPT=$(echo "$INPUT" | jq -r '.prompt')

        # If prompt mentions an issue number, fetch context
        ISSUE=$(echo "$PROMPT" | grep -oE '#[0-9]+' | head -1 | tr -d '#')
        if [ -n "$ISSUE" ]; then
          echo "Issue #$ISSUE context:"
          gh issue view "$ISSUE" --json title,body,state 2>/dev/null || true
        fi
      timeout: 10000
```

### Prompt-Based Validation (LLM)
```yaml
hooks:
  UserPromptSubmit:
    - type: "prompt"
      prompt: |
        Review this user request for safety and appropriateness:

        $ARGUMENTS

        Should this request be processed? Consider:
        - Does it request destructive operations?
        - Does it ask for sensitive data access?
        - Is it within normal development scope?

        Respond with your decision and reasoning.
```

### Add Time Context
```yaml
hooks:
  UserPromptSubmit:
    - command: |
        echo "Session context:"
        echo "- Time: $(date '+%Y-%m-%d %H:%M:%S %Z')"
        echo "- Working directory: $(pwd)"
        echo "- User: $(whoami)"
      timeout: 1000
```

### Inject Custom Instructions
```yaml
hooks:
  UserPromptSubmit:
    - command: |
        INPUT=$(cat)
        PROMPT=$(echo "$INPUT" | jq -r '.prompt')

        # Add team conventions for code changes
        if echo "$PROMPT" | grep -qiE 'fix|implement|add|create|update'; then
          echo "Reminder: Follow team conventions:"
          echo "- Use TypeScript strict mode"
          echo "- Add tests for new functions"
          echo "- Update CHANGELOG.md for user-facing changes"
        fi
      timeout: 2000
```

## Use Cases

1. **Context Enrichment** - Add git status, issue info, project state
2. **Safety Guardrails** - Block dangerous or inappropriate requests
3. **Audit Logging** - Record all user interactions
4. **Custom Instructions** - Inject project-specific guidance
5. **Issue Integration** - Auto-fetch issue details when referenced
6. **Environment Info** - Add time, user, and system context

## Notes

- Runs synchronously before Claude sees the prompt
- stdout is added to context (visible to Claude, not user)
- stderr with exit 2 is shown to user as block reason
- Timeout default: 60 seconds
- Multiple hooks run in order; context is accumulated
- First hook to exit 2 blocks the prompt
- Large context additions consume tokens
