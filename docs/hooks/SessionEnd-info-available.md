# SessionEnd Hook

Fires when a Claude Code session ends. Used for cleanup, logging, and final state persistence.

## When It Fires

- When user exits Claude Code (`Ctrl+C`, `exit`, closing terminal)
- When `/clear` command is used (before clearing)
- When user logs out
- When session times out or terminates

## Input JSON (via stdin)

```json
{
  "session_id": "abc123-def456",
  "transcript_path": "/Users/name/.claude/projects/hash/sessions/session-id.jsonl",
  "cwd": "/path/to/current/directory",
  "permission_mode": "default",
  "hook_event_name": "SessionEnd",

  "reason": "prompt_input_exit"
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
| `hook_event_name` | string | Always `"SessionEnd"` |

### SessionEnd-Specific Fields

| Field | Type | Description |
|-------|------|-------------|
| `reason` | enum | Why the session ended |

### Reason Values

| Value | Description |
|-------|-------------|
| `prompt_input_exit` | User exited via prompt (Ctrl+C, exit command) |
| `clear` | User ran `/clear` command |
| `logout` | User logged out of Claude |
| `other` | Other termination (timeout, crash, etc.) |

## Output Options

SessionEnd hooks are primarily for side effects (logging, cleanup). Output is generally not used.

### Silent Cleanup
```bash
# Cleanup with no output
rm -f /tmp/session-*.tmp 2>/dev/null
exit 0
```

### Logging
```bash
INPUT=$(cat)
SESSION=$(echo "$INPUT" | jq -r '.session_id')
REASON=$(echo "$INPUT" | jq -r '.reason')
echo "[$(date)] Session $SESSION ended: $REASON" >> ~/.claude-sessions.log
```

## Configuration Examples

### Basic Session Logging
```yaml
hooks:
  SessionEnd:
    - command: |
        INPUT=$(cat)
        SESSION=$(echo "$INPUT" | jq -r '.session_id')
        REASON=$(echo "$INPUT" | jq -r '.reason')
        TRANSCRIPT=$(echo "$INPUT" | jq -r '.transcript_path')

        echo "[$(date '+%Y-%m-%d %H:%M:%S')] Session ended" >> /tmp/claude-sessions.log
        echo "  ID: $SESSION" >> /tmp/claude-sessions.log
        echo "  Reason: $REASON" >> /tmp/claude-sessions.log
        echo "  Transcript: $TRANSCRIPT" >> /tmp/claude-sessions.log
        echo "" >> /tmp/claude-sessions.log
      timeout: 5000
```

### Status Tracking (Karma Radio)
```yaml
hooks:
  SessionEnd:
    - command: |
        INPUT=$(cat)
        export KARMA_SESSION_ID=$(echo "$INPUT" | jq -r '.session_id')
        REASON=$(echo "$INPUT" | jq -r '.reason')
        karma radio set-status completed --message "Session ended: $REASON"
      timeout: 5000
```

### Cleanup Temporary Files
```yaml
hooks:
  SessionEnd:
    - command: |
        INPUT=$(cat)
        SESSION=$(echo "$INPUT" | jq -r '.session_id')

        # Clean up session-specific temp files
        rm -f "/tmp/claude-$SESSION-"* 2>/dev/null
        rm -f "/tmp/hooks-$SESSION.log" 2>/dev/null
      timeout: 3000
```

### Archive Transcript
```yaml
hooks:
  SessionEnd:
    - command: |
        INPUT=$(cat)
        TRANSCRIPT=$(echo "$INPUT" | jq -r '.transcript_path')
        SESSION=$(echo "$INPUT" | jq -r '.session_id')

        if [ -f "$TRANSCRIPT" ]; then
          ARCHIVE_DIR="$HOME/.claude-archives"
          mkdir -p "$ARCHIVE_DIR"
          cp "$TRANSCRIPT" "$ARCHIVE_DIR/session-$SESSION-$(date +%Y%m%d).jsonl"
        fi
      timeout: 10000
```

### Calculate Session Statistics
```yaml
hooks:
  SessionEnd:
    - command: |
        INPUT=$(cat)
        TRANSCRIPT=$(echo "$INPUT" | jq -r '.transcript_path')
        SESSION=$(echo "$INPUT" | jq -r '.session_id')

        if [ -f "$TRANSCRIPT" ]; then
          MESSAGES=$(wc -l < "$TRANSCRIPT")
          TOOLS=$(grep -c '"tool_use"' "$TRANSCRIPT" 2>/dev/null || echo "0")

          echo "[$(date)] Session $SESSION stats:" >> ~/.claude-stats.log
          echo "  Messages: $MESSAGES" >> ~/.claude-stats.log
          echo "  Tool calls: $TOOLS" >> ~/.claude-stats.log
        fi
      timeout: 5000
```

### Notify on Exit
```yaml
hooks:
  SessionEnd:
    - command: |
        INPUT=$(cat)
        REASON=$(echo "$INPUT" | jq -r '.reason')

        # macOS notification
        osascript -e "display notification \"Session ended: $REASON\" with title \"Claude Code\""
      timeout: 3000
```

### Conditional Cleanup by Reason
```yaml
hooks:
  SessionEnd:
    - command: |
        INPUT=$(cat)
        REASON=$(echo "$INPUT" | jq -r '.reason')

        case "$REASON" in
          clear)
            # User clearing context - preserve some state
            echo "Context cleared, state preserved" >> /tmp/claude.log
            ;;
          logout)
            # Full logout - clean everything
            rm -rf /tmp/claude-* 2>/dev/null
            ;;
          prompt_input_exit)
            # Normal exit - light cleanup
            ;;
          other)
            # Unexpected exit - log for debugging
            echo "[WARN] Unexpected session termination" >> /tmp/claude-errors.log
            ;;
        esac
      timeout: 5000
```

### Git Status Snapshot
```yaml
hooks:
  SessionEnd:
    - command: |
        INPUT=$(cat)
        SESSION=$(echo "$INPUT" | jq -r '.session_id')

        # Capture git state at session end
        if git rev-parse --git-dir > /dev/null 2>&1; then
          mkdir -p ~/.claude-git-snapshots
          git status --short > ~/.claude-git-snapshots/"$SESSION-end.txt"
          git log -1 --format="%H %s" >> ~/.claude-git-snapshots/"$SESSION-end.txt"
        fi
      timeout: 5000
```

### Send Analytics
```yaml
hooks:
  SessionEnd:
    - command: |
        INPUT=$(cat)
        SESSION=$(echo "$INPUT" | jq -r '.session_id')
        REASON=$(echo "$INPUT" | jq -r '.reason')

        # Send to analytics endpoint (non-blocking)
        curl -s -X POST "https://your-analytics.com/sessions" \
          -H "Content-Type: application/json" \
          -d "{\"session\": \"$SESSION\", \"reason\": \"$REASON\", \"ended\": \"$(date -u +%Y-%m-%dT%H:%M:%SZ)\"}" \
          > /dev/null 2>&1 &
      timeout: 2000
```

## Use Cases

1. **Session Logging** - Record session duration, outcomes
2. **Cleanup** - Remove temporary files, reset state
3. **Archival** - Backup transcripts for later analysis
4. **Statistics** - Calculate tool usage, message counts
5. **Notifications** - Alert when sessions end
6. **State Persistence** - Save session state for future resume
7. **Analytics** - Send usage data to external systems

## Notes

- Runs synchronously during shutdown
- Keep hooks fast to avoid slow exits
- Use background processes (`&`) for slow operations
- `reason` helps differentiate cleanup strategies
- Cannot prevent session from ending
- Timeout default: 60 seconds (but keep it short)
- `transcript_path` file still exists during hook execution
