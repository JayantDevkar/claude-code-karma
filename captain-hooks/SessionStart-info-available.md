# SessionStart Hook

Fires when a Claude Code session begins or resumes. Used for initialization, environment setup, and loading context.

## When It Fires

- When Claude Code starts a new session
- When a session is resumed
- After context is cleared (`/clear`)
- After context compaction

## Input JSON (via stdin)

```json
{
  "session_id": "abc123-def456",
  "transcript_path": "/Users/name/.claude/projects/hash/sessions/session-id.jsonl",
  "cwd": "/path/to/current/directory",
  "permission_mode": "default",
  "hook_event_name": "SessionStart",

  "source": "startup"
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
| `hook_event_name` | string | Always `"SessionStart"` |

### SessionStart-Specific Fields

| Field | Type | Description |
|-------|------|-------------|
| `source` | enum | Why the session started |

### Source Values

| Value | Description |
|-------|-------------|
| `startup` | Fresh session start |
| `resume` | Resuming an existing session |
| `clear` | After `/clear` command |
| `compact` | After context compaction |

## Special Environment Variables

### CLAUDE_ENV_FILE

**Only available in SessionStart hooks.** Path to a file where you can write environment variables that persist for the entire session.

```bash
# Write env vars to CLAUDE_ENV_FILE
echo "NODE_VERSION=18" >> "$CLAUDE_ENV_FILE"
echo "API_KEY=xxx" >> "$CLAUDE_ENV_FILE"
```

These variables are available in all subsequent Bash tool calls.

### CLAUDE_PROJECT_DIR

Absolute path to the project root (where Claude Code was started).

### CLAUDE_CODE_REMOTE

`true` if running via web interface, `false` for local CLI.

## Output Options

### Add Initial Context
stdout is added to conversation context:
```bash
echo "Project: $(basename $(pwd))"
echo "Branch: $(git branch --show-current 2>/dev/null || echo 'N/A')"
echo "Node: $(node -v 2>/dev/null || echo 'N/A')"
```

### Add Context via JSON
```json
{
  "hookSpecificOutput": {
    "additionalContext": "Welcome! This is a TypeScript project using React 18."
  }
}
```

### Set Environment Variables
```bash
# Using CLAUDE_ENV_FILE
if [ -n "$CLAUDE_ENV_FILE" ]; then
  echo "PROJECT_NAME=$(basename $(pwd))" >> "$CLAUDE_ENV_FILE"
  echo "GIT_BRANCH=$(git branch --show-current 2>/dev/null)" >> "$CLAUDE_ENV_FILE"
fi
```

## Configuration Examples

### Basic Project Info
```yaml
hooks:
  SessionStart:
    - command: |
        echo "=== Session Started ==="
        echo "Project: $(basename $(pwd))"
        echo "Directory: $(pwd)"
        echo "Time: $(date)"
        echo ""
      timeout: 5000
```

### Git Context
```yaml
hooks:
  SessionStart:
    - command: |
        if git rev-parse --git-dir > /dev/null 2>&1; then
          echo "Git Repository:"
          echo "- Branch: $(git branch --show-current)"
          echo "- Last commit: $(git log -1 --format='%h %s')"
          echo "- Status: $(git status --short | wc -l | tr -d ' ') changed files"
          echo ""
        fi
      timeout: 5000
```

### Node.js Project Setup
```yaml
hooks:
  SessionStart:
    - command: |
        if [ -f "package.json" ]; then
          echo "Node.js Project:"
          echo "- Name: $(jq -r '.name' package.json)"
          echo "- Version: $(jq -r '.version' package.json)"
          echo "- Node: $(node -v 2>/dev/null || echo 'not found')"
          echo ""

          # Set up environment
          if [ -n "$CLAUDE_ENV_FILE" ]; then
            echo "NODE_ENV=development" >> "$CLAUDE_ENV_FILE"
          fi
        fi
      timeout: 5000
```

### NVM Version Switching
```yaml
hooks:
  SessionStart:
    - command: |
        if [ -f ".nvmrc" ]; then
          REQUIRED_VERSION=$(cat .nvmrc)

          # Capture current environment
          BEFORE_ENV=$(env | sort)

          # Load nvm and switch version
          export NVM_DIR="$HOME/.nvm"
          [ -s "$NVM_DIR/nvm.sh" ] && . "$NVM_DIR/nvm.sh"
          nvm use "$REQUIRED_VERSION" > /dev/null 2>&1

          # Write changed vars to CLAUDE_ENV_FILE
          if [ -n "$CLAUDE_ENV_FILE" ]; then
            AFTER_ENV=$(env | sort)
            diff <(echo "$BEFORE_ENV") <(echo "$AFTER_ENV") | \
              grep '^>' | sed 's/^> //' >> "$CLAUDE_ENV_FILE"
          fi

          echo "Using Node $(node -v) from .nvmrc"
        fi
      timeout: 10000
```

### Load Recent Issues
```yaml
hooks:
  SessionStart:
    - command: |
        echo "Recent GitHub Issues:"
        gh issue list --limit 5 --state open 2>/dev/null || echo "GitHub CLI not available"
        echo ""
      timeout: 15000
```

### Status Tracking (Karma Radio)
```yaml
hooks:
  SessionStart:
    - command: |
        INPUT=$(cat)
        export KARMA_SESSION_ID=$(echo "$INPUT" | jq -r '.session_id')
        export KARMA_AGENT_ID=$(echo "$INPUT" | jq -r '.session_id')
        karma radio set-status pending --message "Session started"
      timeout: 5000
```

### Conditional by Source
```yaml
hooks:
  SessionStart:
    - command: |
        INPUT=$(cat)
        SOURCE=$(echo "$INPUT" | jq -r '.source')

        case "$SOURCE" in
          startup)
            echo "Fresh session - loading full context..."
            # Heavy initialization
            ;;
          resume)
            echo "Resuming session - minimal context..."
            # Light refresh
            ;;
          clear)
            echo "Context cleared - resetting state..."
            ;;
          compact)
            echo "Context compacted - preserving key info..."
            ;;
        esac
      timeout: 5000
```

### Load Project-Specific Config
```yaml
hooks:
  SessionStart:
    - command: |
        # Load project-specific Claude config
        if [ -f ".claude-project.json" ]; then
          CONFIG=$(cat .claude-project.json)
          echo "Project Configuration:"
          echo "$CONFIG" | jq -r 'to_entries | .[] | "- \(.key): \(.value)"'
          echo ""
        fi
      timeout: 3000
```

### Set Up Virtual Environment (Python)
```yaml
hooks:
  SessionStart:
    - command: |
        if [ -f "requirements.txt" ] || [ -f "pyproject.toml" ]; then
          if [ -d ".venv" ]; then
            echo "Python Virtual Environment detected"
            if [ -n "$CLAUDE_ENV_FILE" ]; then
              echo "VIRTUAL_ENV=$(pwd)/.venv" >> "$CLAUDE_ENV_FILE"
              echo "PATH=$(pwd)/.venv/bin:\$PATH" >> "$CLAUDE_ENV_FILE"
            fi
          fi
        fi
      timeout: 5000
```

## Use Cases

1. **Environment Setup** - Set Node version, Python venv, env vars
2. **Project Context** - Load project info, git status, dependencies
3. **Issue Integration** - Fetch open issues/PRs at session start
4. **State Restoration** - Resume tracking systems, load saved state
5. **Conditional Init** - Different setup for startup vs resume
6. **Team Config** - Load shared team settings/conventions

## Notes

- `CLAUDE_ENV_FILE` is **only** available in SessionStart hooks
- Environment vars written to `CLAUDE_ENV_FILE` persist for session
- stdout is added to Claude's context
- Runs synchronously before session is interactive
- Timeout default: 60 seconds
- Consider using `source` to differentiate initialization levels
- Heavy initialization should be in `startup` only
