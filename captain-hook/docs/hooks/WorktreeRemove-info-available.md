# WorktreeRemove Hook

Fires when a git worktree is removed. Cannot block execution.

## When It Fires

- After Claude Code removes a git worktree (e.g., session cleanup, `/worktree remove` slash command)

## Input JSON (via stdin)

```json
{
  "session_id": "abc123-def456",
  "transcript_path": "/Users/name/.claude/projects/hash/sessions/session-id.jsonl",
  "cwd": "/path/to/current/directory",
  "permission_mode": "default",
  "hook_event_name": "WorktreeRemove",

  "worktree_path": "/Users/me/.claude-worktrees/repo/feat-auth",
  "worktree_name": "feat-auth"
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
| `hook_event_name` | string | Always `"WorktreeRemove"` |

### WorktreeRemove-Specific Fields

| Field | Type | Description |
|-------|------|-------------|
| `worktree_path` | string | Absolute path to the worktree being removed |
| `worktree_name` | string | Name of the worktree being removed |

## Output Options

WorktreeRemove **cannot block** — it is purely observational.

## Configuration Example

```yaml
hooks:
  WorktreeRemove:
    - command: |
        INPUT=$(cat)
        PATH_=$(echo "$INPUT" | jq -r '.worktree_path')
        echo "$(date): Removed $PATH_" >> /tmp/worktree_removals.log
      timeout: 2000
```

## Use Cases

1. **Cleanup verification** — log every removed worktree
2. **External cleanup** — drop derived caches, indexes, or DB rows tied to the worktree
3. **Telemetry** — measure worktree lifetime

## Notes

- Cannot block execution (exit code is ignored)
- Fires after the worktree's git metadata is removed
