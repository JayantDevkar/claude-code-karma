# Captain Hook - Claude Code Hooks Library

Type-safe Pydantic models and complete documentation for all Claude Code hook types.

## Overview

Claude Code hooks are shell commands or LLM prompts that execute at specific points during a session. All hooks receive JSON input via **stdin**. This library provides:

- **Type-safe Pydantic models** for all 10 hook types
- **Comprehensive documentation** for each hook
- **Forward compatibility** via `extra="allow"` configuration
- **113 tests** ensuring reliability

## Installation

```bash
pip install pydantic
```

## Quick Start

```python
import json
import sys
from captain_hook import parse_hook_event, PreToolUseHook

# Parse any hook event from stdin
data = json.loads(sys.stdin.read())
hook = parse_hook_event(data)

# Type-narrow based on hook type
if isinstance(hook, PreToolUseHook):
    print(f"Tool: {hook.tool_name}")
    print(f"Input: {hook.tool_input}")
```

## Hook Types

| Hook | When It Fires | Can Block? | Can Modify? |
|------|---------------|------------|-------------|
| [PreToolUse](./docs/hooks/PreToolUse-info-available.md) | Before tool execution | Yes | Yes (input) |
| [PostToolUse](./docs/hooks/PostToolUse-info-available.md) | After tool execution | No | No |
| [UserPromptSubmit](./docs/hooks/UserPromptSubmit-info-available.md) | When user sends message | Yes | No |
| [SessionStart](./docs/hooks/SessionStart-info-available.md) | Session begins/resumes | No | Yes (env) |
| [SessionEnd](./docs/hooks/SessionEnd-info-available.md) | Session ends | No | No |
| [Stop](./docs/hooks/Stop-info-available.md) | Main agent finishes | No | Yes (continue) |
| [SubagentStop](./docs/hooks/SubagentStop-info-available.md) | Subagent finishes | No | Yes (continue) |
| [PreCompact](./docs/hooks/PreCompact-info-available.md) | Before context compaction | No | No |
| [PermissionRequest](./docs/hooks/PermissionRequest-info-available.md) | Permission dialog shown | Yes | No |
| [Notification](./docs/hooks/Notification-info-available.md) | System notification | No | No |

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

## Project Structure

```
captain-hook/
├── src/captain_hook/     # Main package (modular design)
│   ├── base.py           # BaseHook class & type definitions
│   ├── tool_hooks.py     # PreToolUseHook, PostToolUseHook
│   ├── user_hooks.py     # UserPromptSubmitHook, PermissionRequestHook, NotificationHook
│   ├── session_hooks.py  # SessionStartHook, SessionEndHook
│   ├── agent_hooks.py    # StopHook, SubagentStopHook
│   ├── context_hooks.py  # PreCompactHook
│   └── outputs.py        # Response models
├── docs/hooks/           # Hook documentation
├── tests/                # Test suite (113 tests)
├── models.py             # Backward compatibility layer
└── file_index.md         # Complete file reference
```

## Python Models

Type-safe Pydantic models are available in the `captain_hook` package.

### Quick Start

```python
import json
import sys
from captain_hook import parse_hook_event, PreToolUseHook

# Parse any hook event from stdin
data = json.loads(sys.stdin.read())
hook = parse_hook_event(data)

# Type-narrow based on hook type
if isinstance(hook, PreToolUseHook):
    print(f"Tool: {hook.tool_name}")
    print(f"Input: {hook.tool_input}")
```

### Legacy Import (Backward Compatible)

```python
from models import parse_hook_event, PreToolUseHook
```

### Available Classes

| Class | Hook Type | Key Fields |
|-------|-----------|------------|
| `BaseHook` | All | `session_id`, `transcript_path`, `cwd`, `permission_mode` |
| `PreToolUseHook` | PreToolUse | `tool_name`, `tool_use_id`, `tool_input` |
| `PostToolUseHook` | PostToolUse | `tool_name`, `tool_use_id`, `tool_input`, `tool_response` |
| `UserPromptSubmitHook` | UserPromptSubmit | `prompt` |
| `SessionStartHook` | SessionStart | `source` |
| `SessionEndHook` | SessionEnd | `reason` |
| `StopHook` | Stop | `stop_hook_active` |
| `SubagentStopHook` | SubagentStop | `stop_hook_active` |
| `PreCompactHook` | PreCompact | `trigger`, `custom_instructions` |
| `PermissionRequestHook` | PermissionRequest | `notification_type`, `message` |
| `NotificationHook` | Notification | `notification_type` |

### Output Models

For hooks that return JSON responses:

```python
from models import PreToolUseOutput, StopOutput, PermissionRequestOutput

# Auto-approve a tool
output = PreToolUseOutput(
    hook_specific_output={
        "permissionDecision": "allow",
        "permissionDecisionReason": "Trusted directory"
    }
)
print(output.model_dump_json())
```

### Forward Compatibility

Models use `extra="allow"` to accept unknown fields, ensuring future schema changes don't break existing code:

```python
# Future fields are preserved
data["new_field_2026"] = "some_value"
hook = parse_hook_event(data)
assert hook.new_field_2026 == "some_value"
```

### Running Tests

```bash
pytest tests/test_models.py -v
```

113 tests covering:
- Base hook validation
- All 10 hook types (parametrized)
- Parser dispatch function
- Forward compatibility
- Output models
- JSON serialization round-trips

---

*Last updated: January 2025*
*Claude Code version: Latest*
