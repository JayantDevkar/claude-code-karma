# InstructionsLoaded Hook

Fires when Claude Code loads a CLAUDE.md or rules file into context. Cannot block execution.

## When It Fires

- On session startup as project/user/managed CLAUDE.md files are loaded
- When a CLAUDE.md uses `@import` to pull in another file
- When glob-matched rules files are activated for a path

## Input JSON (via stdin)

```json
{
  "session_id": "abc123-def456",
  "transcript_path": "/Users/name/.claude/projects/hash/sessions/session-id.jsonl",
  "cwd": "/path/to/current/directory",
  "permission_mode": "default",
  "hook_event_name": "InstructionsLoaded",

  "file_path": "/Users/me/repo/CLAUDE.md",
  "memory_type": "project",
  "load_reason": "startup",
  "globs": [],
  "trigger_file_path": null,
  "parent_file_path": null
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
| `hook_event_name` | string | Always `"InstructionsLoaded"` |

### InstructionsLoaded-Specific Fields

| Field | Type | Description |
|-------|------|-------------|
| `file_path` | string | Absolute path to the CLAUDE.md / rules file that was loaded |
| `memory_type` | string | Category: `project`, `user`, `plugin`, `managed` |
| `load_reason` | string | Why loaded: `startup`, `import`, `glob_match`, etc. |
| `globs` | string[] | Glob patterns associated with the load (when triggered by globs) |
| `trigger_file_path` | string \| null | File that triggered the load (for imports/glob matches) |
| `parent_file_path` | string \| null | Parent CLAUDE.md that imported this one |

## Output Options

InstructionsLoaded **cannot block** — it is purely observational. Stdout/stderr are logged but ignored.

## Configuration Example

```yaml
hooks:
  InstructionsLoaded:
    - command: |
        INPUT=$(cat)
        FILE=$(echo "$INPUT" | jq -r '.file_path')
        echo "Loaded instructions: $FILE" >> /tmp/instructions.log
      timeout: 2000
```

## Use Cases

1. **Audit logging** — track which rule files are active in each session
2. **Index building** — build a searchable map of project instructions
3. **Validation** — verify expected CLAUDE.md files were loaded
4. **Telemetry** — measure rule file usage across projects

## Notes

- Cannot block execution (exit code is ignored)
- Fires once per loaded file (multiple times per session)
- For nested imports, both `trigger_file_path` and `parent_file_path` are populated
