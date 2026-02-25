# Notification Hook

Fires when Claude sends system notifications. Used to customize notification delivery or logging.

## When It Fires

- When Claude displays a notification to the user
- For various system events and prompts
- After the notification is triggered

## Input JSON (via stdin)

```json
{
  "session_id": "abc123-def456",
  "transcript_path": "/Users/name/.claude/projects/hash/sessions/session-id.jsonl",
  "cwd": "/path/to/current/directory",
  "permission_mode": "default",
  "hook_event_name": "Notification",

  "notification_type": "idle_prompt"
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
| `hook_event_name` | string | Always `"Notification"` |

### Notification-Specific Fields

| Field | Type | Description |
|-------|------|-------------|
| `notification_type` | string | Type of notification being sent |

### Notification Types

| Type | Description |
|------|-------------|
| `permission_prompt` | Permission dialog notification |
| `idle_prompt` | Claude is idle, waiting for input |
| `auth_success` | Authentication completed successfully |
| `elicitation_dialog` | Claude is asking user for input |

## Output Options

This hook is primarily for side effects (logging, custom notifications). Output is generally not used to modify behavior.

### Silent Logging
```bash
INPUT=$(cat)
TYPE=$(echo "$INPUT" | jq -r '.notification_type')
echo "[$(date)] Notification: $TYPE" >> /tmp/notifications.log
```

## Configuration Examples

### Log All Notifications
```yaml
hooks:
  Notification:
    - command: |
        INPUT=$(cat)
        SESSION=$(echo "$INPUT" | jq -r '.session_id')
        TYPE=$(echo "$INPUT" | jq -r '.notification_type')
        echo "[$(date)] [$SESSION] $TYPE" >> /tmp/claude-notifications.log
      timeout: 2000
```

### Custom macOS Notifications
```yaml
hooks:
  Notification:
    - command: |
        INPUT=$(cat)
        TYPE=$(echo "$INPUT" | jq -r '.notification_type')

        case "$TYPE" in
          idle_prompt)
            osascript -e 'display notification "Claude is ready for input" with title "Claude Code"'
            ;;
          auth_success)
            osascript -e 'display notification "Authentication successful" with title "Claude Code"'
            ;;
          permission_prompt)
            osascript -e 'display notification "Permission needed" with title "Claude Code" sound name "Ping"'
            ;;
        esac
      timeout: 3000
```

### Sound Alerts
```yaml
hooks:
  Notification:
    - command: |
        INPUT=$(cat)
        TYPE=$(echo "$INPUT" | jq -r '.notification_type')

        case "$TYPE" in
          idle_prompt)
            # Play sound when Claude is waiting
            afplay /System/Library/Sounds/Glass.aiff &
            ;;
          permission_prompt)
            # More urgent sound for permissions
            afplay /System/Library/Sounds/Ping.aiff &
            ;;
        esac
      timeout: 2000
```

### Slack/Discord Integration
```yaml
hooks:
  Notification:
    - command: |
        INPUT=$(cat)
        TYPE=$(echo "$INPUT" | jq -r '.notification_type')
        SESSION=$(echo "$INPUT" | jq -r '.session_id')

        # Send to Slack webhook for certain notifications
        if [ "$TYPE" = "permission_prompt" ]; then
          curl -s -X POST "$SLACK_WEBHOOK" \
            -H "Content-Type: application/json" \
            -d "{\"text\": \"Claude Code needs permission (session: $SESSION)\"}" \
            > /dev/null 2>&1 &
        fi
      timeout: 3000
```

### Terminal Bell
```yaml
hooks:
  Notification:
    - command: |
        INPUT=$(cat)
        TYPE=$(echo "$INPUT" | jq -r '.notification_type')

        if [ "$TYPE" = "idle_prompt" ]; then
          # Ring terminal bell
          printf '\a'
        fi
      timeout: 1000
```

### Status Tracking
```yaml
hooks:
  Notification:
    - command: |
        INPUT=$(cat)
        export KARMA_SESSION_ID=$(echo "$INPUT" | jq -r '.session_id')
        TYPE=$(echo "$INPUT" | jq -r '.notification_type')

        case "$TYPE" in
          idle_prompt)
            karma radio set-status waiting --message "Waiting for input"
            ;;
          permission_prompt)
            karma radio set-status waiting --message "Awaiting permission"
            ;;
        esac
      timeout: 3000
```

### Track Idle Time
```yaml
hooks:
  Notification:
    - command: |
        INPUT=$(cat)
        TYPE=$(echo "$INPUT" | jq -r '.notification_type')
        SESSION=$(echo "$INPUT" | jq -r '.session_id')

        if [ "$TYPE" = "idle_prompt" ]; then
          IDLE_FILE="/tmp/claude-idle-$SESSION"
          echo "$(date +%s)" > "$IDLE_FILE"
        fi
      timeout: 1000
```

### Focus Window (macOS)
```yaml
hooks:
  Notification:
    - command: |
        INPUT=$(cat)
        TYPE=$(echo "$INPUT" | jq -r '.notification_type')

        if [ "$TYPE" = "permission_prompt" ]; then
          # Bring Terminal to front for permissions
          osascript -e 'tell application "Terminal" to activate'
        fi
      timeout: 2000
```

### Email Alert for Long Waits
```yaml
hooks:
  Notification:
    - command: |
        INPUT=$(cat)
        TYPE=$(echo "$INPUT" | jq -r '.notification_type')
        SESSION=$(echo "$INPUT" | jq -r '.session_id')

        if [ "$TYPE" = "permission_prompt" ]; then
          # Record permission request time
          echo "$(date +%s)" > "/tmp/permission-wait-$SESSION"
        fi

        if [ "$TYPE" = "idle_prompt" ]; then
          # Check if we've been waiting for permission
          WAIT_FILE="/tmp/permission-wait-$SESSION"
          if [ -f "$WAIT_FILE" ]; then
            START=$(cat "$WAIT_FILE")
            NOW=$(date +%s)
            WAIT_TIME=$((NOW - START))

            # Alert if waiting more than 5 minutes
            if [ "$WAIT_TIME" -gt 300 ]; then
              echo "Claude waiting for permission for ${WAIT_TIME}s" | mail -s "Claude Code Alert" user@example.com
            fi
            rm -f "$WAIT_FILE"
          fi
        fi
      timeout: 5000
```

### Desktop Notification with Icon
```yaml
hooks:
  Notification:
    - command: |
        INPUT=$(cat)
        TYPE=$(echo "$INPUT" | jq -r '.notification_type')

        # Use terminal-notifier for richer notifications (brew install terminal-notifier)
        case "$TYPE" in
          idle_prompt)
            terminal-notifier -title "Claude Code" -message "Ready for input" -sound default 2>/dev/null || true
            ;;
          permission_prompt)
            terminal-notifier -title "Claude Code" -message "Permission required" -sound Ping 2>/dev/null || true
            ;;
        esac
      timeout: 3000
```

## Use Cases

1. **Custom Notifications** - Replace/enhance default notifications
2. **Sound Alerts** - Audio cues for different events
3. **Remote Alerts** - Slack/Discord/Email integration
4. **Focus Management** - Bring window to front when needed
5. **Status Tracking** - Update external monitoring systems
6. **Idle Tracking** - Monitor how long Claude is waiting
7. **Accessibility** - Alternative notification methods

## Notes

- Cannot prevent notification - hook is informational
- Runs after notification is triggered
- Keep hooks fast to not delay notifications
- Timeout default: 60 seconds
- Background processes (`&`) recommended for slow operations
- `notification_type` values may expand in future versions
- Sound/visual alerts should be unobtrusive
