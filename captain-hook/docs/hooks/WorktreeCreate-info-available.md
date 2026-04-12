# WorktreeCreate Hook

Fires when a git worktree is about to be created. **CAN override** the worktree path via an HTTP hook response.

## When It Fires

- Before Claude Code creates a new git worktree (e.g., from Claude Desktop session creation, `/worktree` slash command, or tool invocation)

## Input JSON (via stdin)

```json
{
  "session_id": "abc123-def456",
  "transcript_path": "/Users/name/.claude/projects/hash/sessions/session-id.jsonl",
  "cwd": "/path/to/current/directory",
  "permission_mode": "default",
  "hook_event_name": "WorktreeCreate",

  "worktree_name": "feat-auth",
  "base_ref": "main"
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
| `hook_event_name` | string | Always `"WorktreeCreate"` |

### WorktreeCreate-Specific Fields

| Field | Type | Description |
|-------|------|-------------|
| `worktree_name` | string | The chosen or generated name for the new worktree |
| `base_ref` | string | Git ref the worktree branches from (e.g., `main`, `origin/develop`) |

## Output Options

### Allow Default Path
Exit code 0, no output.

### Override Worktree Path (HTTP hook only)
An HTTP hook can return:
```json
{
  "worktreePath": "/custom/location/worktrees/feat-auth"
}
```
to redirect where the worktree is created.

### Block Creation
Exit code 2 with stderr.

## Configuration Example

```yaml
hooks:
  WorktreeCreate:
    - type: "http"
      url: "https://hooks.example.com/worktree"
      timeout: 5000
```

## Use Cases

1. **Custom storage** — place worktrees on a faster disk or shared mount
2. **Naming conventions** — enforce a project-specific worktree layout
3. **Audit logging** — record every worktree creation

## Notes

- The `worktreePath` override is only honored from HTTP hook responses
- Command hooks can still observe and block via exit code 2
