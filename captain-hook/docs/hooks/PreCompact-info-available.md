# PreCompact Hook

Fires before context compaction occurs. Used to preserve important information or log compaction events.

## When It Fires

- Before automatic context compaction (when context exceeds limits)
- Before manual compaction (user triggers `/compact`)
- Before Claude summarizes and truncates conversation history

## Input JSON (via stdin)

```json
{
  "session_id": "abc123-def456",
  "transcript_path": "/Users/name/.claude/projects/hash/sessions/session-id.jsonl",
  "cwd": "/path/to/current/directory",
  "permission_mode": "default",
  "hook_event_name": "PreCompact",

  "trigger": "auto",
  "custom_instructions": ""
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
| `hook_event_name` | string | Always `"PreCompact"` |

### PreCompact-Specific Fields

| Field | Type | Description |
|-------|------|-------------|
| `trigger` | enum | What triggered compaction |
| `custom_instructions` | string | User-provided compaction instructions |

### Trigger Values

| Value | Description |
|-------|-------------|
| `auto` | Automatic compaction (context limit reached) |
| `manual` | User triggered via `/compact` command |

## Understanding Context Compaction

When Claude's context window fills up:
1. PreCompact hook fires
2. Claude summarizes the conversation
3. Old messages are truncated
4. Session continues with summary + recent context

This hook lets you:
- Log when compaction happens
- Extract important info before it's summarized
- Save full transcript backup

## Output Options

### Silent (default)
Exit code 0, no output needed.

### Add Context to Preserve
stdout can suggest what to preserve:
```bash
echo "Important: Remember the database schema changes discussed earlier"
```

### JSON Output
```json
{
  "hookSpecificOutput": {
    "additionalContext": "Key decisions: 1) Using PostgreSQL, 2) Auth via JWT"
  }
}
```

## Configuration Examples

### Log Compaction Events
```yaml
hooks:
  PreCompact:
    - command: |
        INPUT=$(cat)
        SESSION=$(echo "$INPUT" | jq -r '.session_id')
        TRIGGER=$(echo "$INPUT" | jq -r '.trigger')
        echo "[$(date)] Compaction triggered ($TRIGGER) for session $SESSION" >> /tmp/compaction.log
      timeout: 2000
```

### Backup Transcript Before Compaction
```yaml
hooks:
  PreCompact:
    - command: |
        INPUT=$(cat)
        SESSION=$(echo "$INPUT" | jq -r '.session_id')
        TRANSCRIPT=$(echo "$INPUT" | jq -r '.transcript_path')

        if [ -f "$TRANSCRIPT" ]; then
          BACKUP_DIR="$HOME/.claude-backups"
          mkdir -p "$BACKUP_DIR"
          cp "$TRANSCRIPT" "$BACKUP_DIR/pre-compact-$SESSION-$(date +%Y%m%d%H%M%S).jsonl"
          echo "Transcript backed up before compaction"
        fi
      timeout: 10000
```

### Extract Key Information
```yaml
hooks:
  PreCompact:
    - command: |
        INPUT=$(cat)
        TRANSCRIPT=$(echo "$INPUT" | jq -r '.transcript_path')

        # Extract and preserve important patterns
        if [ -f "$TRANSCRIPT" ]; then
          echo "=== Pre-Compaction Summary ==="

          # Count tool usage
          TOOLS=$(grep -c '"tool_use"' "$TRANSCRIPT" 2>/dev/null || echo "0")
          echo "Tool calls in session: $TOOLS"

          # Find mentioned files
          FILES=$(grep -oE '"file_path":"[^"]*"' "$TRANSCRIPT" | sort -u | head -10)
          if [ -n "$FILES" ]; then
            echo "Key files discussed:"
            echo "$FILES" | sed 's/"file_path":"//g' | sed 's/"//g' | sed 's/^/  - /'
          fi
        fi
      timeout: 10000
```

### Conditional by Trigger
```yaml
hooks:
  PreCompact:
    - command: |
        INPUT=$(cat)
        TRIGGER=$(echo "$INPUT" | jq -r '.trigger')
        CUSTOM=$(echo "$INPUT" | jq -r '.custom_instructions')

        case "$TRIGGER" in
          auto)
            echo "Auto-compaction: Context limit reached"
            # Maybe send notification for long sessions
            ;;
          manual)
            echo "Manual compaction requested"
            if [ -n "$CUSTOM" ]; then
              echo "Custom instructions: $CUSTOM"
            fi
            ;;
        esac
      timeout: 3000
```

### Preserve Decision Log
```yaml
hooks:
  PreCompact:
    - command: |
        INPUT=$(cat)
        SESSION=$(echo "$INPUT" | jq -r '.session_id')

        # Save a decisions file that survives compaction
        DECISIONS_FILE="$HOME/.claude-decisions/$SESSION.md"
        mkdir -p "$(dirname "$DECISIONS_FILE")"

        echo "# Session Decisions - $(date)" >> "$DECISIONS_FILE"
        echo "" >> "$DECISIONS_FILE"

        # This output goes to Claude's context
        echo "Note: Key decisions saved to $DECISIONS_FILE"
        echo "Review this file if context about earlier decisions is needed."
      timeout: 5000
```

### Calculate Session Statistics
```yaml
hooks:
  PreCompact:
    - command: |
        INPUT=$(cat)
        TRANSCRIPT=$(echo "$INPUT" | jq -r '.transcript_path')
        SESSION=$(echo "$INPUT" | jq -r '.session_id')

        if [ -f "$TRANSCRIPT" ]; then
          LINES=$(wc -l < "$TRANSCRIPT")
          SIZE=$(du -h "$TRANSCRIPT" | cut -f1)

          echo "[$(date)] Pre-compact stats for $SESSION:" >> /tmp/session-stats.log
          echo "  Lines: $LINES" >> /tmp/session-stats.log
          echo "  Size: $SIZE" >> /tmp/session-stats.log
        fi
      timeout: 3000
```

### Status Update
```yaml
hooks:
  PreCompact:
    - command: |
        INPUT=$(cat)
        export KARMA_SESSION_ID=$(echo "$INPUT" | jq -r '.session_id')
        karma radio report-progress --message "Context compacting..."
      timeout: 3000
```

### Notify on Auto-Compaction
```yaml
hooks:
  PreCompact:
    - command: |
        INPUT=$(cat)
        TRIGGER=$(echo "$INPUT" | jq -r '.trigger')

        if [ "$TRIGGER" = "auto" ]; then
          # macOS notification
          osascript -e 'display notification "Context being compacted - long session" with title "Claude Code"'
        fi
      timeout: 2000
```

## Use Cases

1. **Transcript Backup** - Save full conversation before summarization
2. **Statistics** - Track session length and compaction frequency
3. **Key Info Extraction** - Pull out important data before it's lost
4. **Notifications** - Alert on long-running sessions
5. **Debug Logging** - Track when/why compaction happens
6. **Decision Preservation** - Save important decisions to external files

## Notes

- Cannot prevent compaction - hook is informational
- Full transcript available via `transcript_path`
- `custom_instructions` only populated for manual compaction with custom text
- stdout added to context (may influence summary)
- Timeout default: 60 seconds
- Keep hooks fast - compaction is time-sensitive
- Transcript may be large - be careful with full reads
