# Captain Hooks - Claude Code Hooks Reference

Complete documentation for all Claude Code hook types and the information available to each.

## Overview

Claude Code hooks are shell commands or LLM prompts that execute at specific points during a session. All hooks receive JSON input via **stdin**.

## Hook Types

| Hook | When It Fires | Can Block? | Can Modify? |
|------|---------------|------------|-------------|
| [PreToolUse](./PreToolUse-info-available.md) | Before tool execution | Yes | Yes (input) |
| [PostToolUse](./PostToolUse-info-available.md) | After tool execution | No | No |
| [UserPromptSubmit](./UserPromptSubmit-info-available.md) | When user sends message | Yes | No |
| [SessionStart](./SessionStart-info-available.md) | Session begins/resumes | No | Yes (env) |
| [SessionEnd](./SessionEnd-info-available.md) | Session ends | No | No |
| [Stop](./Stop-info-available.md) | Main agent finishes | No | Yes (continue) |
| [SubagentStop](./SubagentStop-info-available.md) | Subagent finishes | No | Yes (continue) |
| [PreCompact](./PreCompact-info-available.md) | Before context compaction | No | No |
| [PermissionRequest](./PermissionRequest-info-available.md) | Permission dialog shown | Yes | No |
| [Notification](./Notification-info-available.md) | System notification | No | No |

## Common Fields (All Hooks)

Every hook receives these base fields:

```json
{
  "session_id": "string",
  "transcript_path": "string",
  "cwd": "string",
  "permission_mode": "string",
  "hook_event_name": "string"
}
```

| Field | Type | Description |
|-------|------|-------------|
| `session_id` | string | Unique identifier for the current session |
| `transcript_path` | string | Absolute path to conversation JSONL file |
| `cwd` | string | Current working directory |
| `permission_mode` | enum | `default`, `plan`, `acceptEdits`, `dontAsk`, `bypassPermissions` |
| `hook_event_name` | string | Name of the hook event being fired |

## Environment Variables

| Variable | Availability | Description |
|----------|--------------|-------------|
| `CLAUDE_PROJECT_DIR` | All hooks | Absolute path to project root |
| `CLAUDE_CODE_REMOTE` | All hooks | `true` if running via web, `false` for CLI |
| `CLAUDE_ENV_FILE` | SessionStart only | File path to persist env vars |

## Hook Configuration

Hooks are defined in `.claude/hooks.yaml`:

```yaml
hooks:
  PreToolUse:
    - command: "your-script.sh"
      timeout: 5000
      match_tools: ["Write", "Edit"]  # optional filter

    - type: "prompt"  # LLM-powered hook
      prompt: "Should this tool run? $ARGUMENTS"
```

## Exit Codes

| Code | Meaning | Behavior |
|------|---------|----------|
| 0 | Success | Hook passes, stdout available for context |
| 2 | Block | Action blocked, stderr shown to user |
| Other | Error | Non-blocking, stderr shown in verbose mode |

## JSON Output Control

Hooks can return JSON to control behavior:

```json
{
  "hookSpecificOutput": {
    "permissionDecision": "allow",
    "permissionDecisionReason": "Auto-approved by policy",
    "updatedInput": { ... },
    "additionalContext": "string",
    "decision": "continue",
    "reason": "Task not complete",
    "suppressOutput": true,
    "systemMessage": "Warning shown to user"
  }
}
```

## Hook Configuration

Hooks use **`matcher`** (regex pattern) to filter which tools trigger them:

```yaml
hooks:
  PreToolUse:
    - matcher: "Bash"           # Exact match
    - matcher: "Edit|Write"     # Multiple tools (regex OR)
    - matcher: "mcp__.*"        # All MCP tools
    - matcher: ""               # All tools (empty = match all)
```

## Execution Behavior

- **Parallelization**: All matching hooks run in parallel
- **Deduplication**: Identical commands are automatically deduplicated
- **Timeout**: Default 60s for commands, 30s for prompt-based hooks

---

*Last updated: January 2025*
*Claude Code version: Latest*
