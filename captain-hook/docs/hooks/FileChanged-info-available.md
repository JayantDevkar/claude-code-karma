# FileChanged Hook

Fires when an external file change is detected by Claude Code's filesystem watcher. Cannot block execution.

## When It Fires

- When a file in the project tree is modified outside Claude Code
- When a watched file is created, edited, or deleted
- Used to keep Claude's view of the workspace in sync

## Input JSON (via stdin)

```json
{
  "session_id": "abc123-def456",
  "transcript_path": "/Users/name/.claude/projects/hash/sessions/session-id.jsonl",
  "cwd": "/Users/me/project",
  "permission_mode": "default",
  "hook_event_name": "FileChanged",

  "file_path": "/Users/me/project/src/main.py",
  "file_name": "main.py"
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
| `hook_event_name` | string | Always `"FileChanged"` |

### FileChanged-Specific Fields

| Field | Type | Description |
|-------|------|-------------|
| `file_path` | string | Absolute path to the file that changed |
| `file_name` | string | Basename of the file that changed |

## Output Options

FileChanged **cannot block** — it is purely observational.

## Configuration Example

```yaml
hooks:
  FileChanged:
    - command: |
        INPUT=$(cat)
        FILE=$(echo "$INPUT" | jq -r '.file_path')
        echo "External change: $FILE" >> /tmp/file_changes.log
      timeout: 2000
```

## Use Cases

1. **Cache invalidation** — refresh derived state when source files change
2. **Live-reload integrations** — coordinate with build watchers
3. **Conflict detection** — warn when external edits collide with Claude's pending changes

## Notes

- Cannot block execution (exit code is ignored)
- Fires per file, not per batch — multiple events may arrive in quick succession
