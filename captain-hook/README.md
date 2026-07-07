# Captain Hook - Claude Code Hooks Library

Type-safe Pydantic models and complete documentation for all 24 Claude Code hook types.

## Overview

Claude Code hooks are shell commands or LLM prompts that execute at specific points during a session. All hooks receive JSON input via **stdin**. This library provides:

- **Type-safe Pydantic models** for all 24 hook types
- **Comprehensive documentation** for each hook
- **Forward compatibility** via `extra="allow"` configuration
- **238 tests** ensuring reliability

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
| [InstructionsLoaded](./docs/hooks/InstructionsLoaded-info-available.md) | CLAUDE.md / rules file loaded | No | No |
| [PermissionDenied](./docs/hooks/PermissionDenied-info-available.md) | Auto mode denied a tool call | No | Yes (retry) |
| [Elicitation](./docs/hooks/Elicitation-info-available.md) | MCP server requests structured input | Yes | No |
| [ElicitationResult](./docs/hooks/ElicitationResult-info-available.md) | User responds to elicitation | Yes | No |
| [CwdChanged](./docs/hooks/CwdChanged-info-available.md) | Working directory changed | No | No |
| [FileChanged](./docs/hooks/FileChanged-info-available.md) | External file change detected | No | No |
| [TaskCreated](./docs/hooks/TaskCreated-info-available.md) | Agent Teams task created (experimental) | Yes | No |
| [TaskCompleted](./docs/hooks/TaskCompleted-info-available.md) | Agent Teams task completed (experimental) | Yes | No |
| [TeammateIdle](./docs/hooks/TeammateIdle-info-available.md) | Teammate became idle (experimental) | Yes | No |
| [WorktreeCreate](./docs/hooks/WorktreeCreate-info-available.md) | Before git worktree creation | Yes | Yes (path via HTTP) |
| [WorktreeRemove](./docs/hooks/WorktreeRemove-info-available.md) | After git worktree removal | No | No |

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
│   ├── tool_hooks.py     # PreToolUseHook, PostToolUseHook, PostToolUseFailureHook
│   ├── user_hooks.py     # UserPromptSubmitHook, PermissionRequestHook, NotificationHook,
│   │                     #   PermissionDeniedHook, ElicitationHook, ElicitationResultHook
│   ├── session_hooks.py  # SessionStartHook, SessionEndHook
│   ├── agent_hooks.py    # StopHook, SubagentStartHook, SubagentStopHook
│   ├── context_hooks.py  # PreCompactHook, InstructionsLoadedHook
│   ├── setup_hooks.py    # SetupHook
│   ├── fs_hooks.py       # CwdChangedHook, FileChangedHook
│   ├── team_hooks.py     # TaskCreatedHook, TaskCompletedHook, TeammateIdleHook
│   ├── worktree_hooks.py # WorktreeCreateHook, WorktreeRemoveHook
│   └── outputs.py        # Response models
├── docs/hooks/           # Hook documentation
├── tests/                # Test suite (238 tests)
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
| `PostToolUseFailureHook` | PostToolUseFailure | `tool_name`, `tool_use_id`, `tool_input`, `error` |
| `UserPromptSubmitHook` | UserPromptSubmit | `prompt` |
| `SessionStartHook` | SessionStart | `source`, `model`, `agent_type` |
| `SessionEndHook` | SessionEnd | `reason` |
| `StopHook` | Stop | `stop_hook_active` |
| `SubagentStartHook` | SubagentStart | `agent_id`, `agent_type` |
| `SubagentStopHook` | SubagentStop | `stop_hook_active`, `agent_id`, `agent_transcript_path` |
| `PreCompactHook` | PreCompact | `trigger`, `custom_instructions` |
| `PermissionRequestHook` | PermissionRequest | `notification_type`, `message` |
| `NotificationHook` | Notification | `notification_type`, `message` |
| `SetupHook` | Setup | `trigger` |
| `InstructionsLoadedHook` | InstructionsLoaded | `file_path`, `memory_type`, `load_reason`, `globs` |
| `PermissionDeniedHook` | PermissionDenied | `tool_name`, `tool_use_id`, `reason`, `tool_input` |
| `ElicitationHook` | Elicitation | `mcp_server`, `tool_name`, `request` |
| `ElicitationResultHook` | ElicitationResult | `mcp_server`, `user_response` |
| `CwdChangedHook` | CwdChanged | `old_cwd`, `new_cwd` |
| `FileChangedHook` | FileChanged | `file_path`, `file_name` |
| `TaskCreatedHook` | TaskCreated | `task_id`, `task_subject`, `team_name`, `teammate_name` |
| `TaskCompletedHook` | TaskCompleted | `task_id`, `task_subject`, `team_name`, `teammate_name` |
| `TeammateIdleHook` | TeammateIdle | `agent_id`, `agent_type`, `team_name` |
| `WorktreeCreateHook` | WorktreeCreate | `worktree_name`, `base_ref` |
| `WorktreeRemoveHook` | WorktreeRemove | `worktree_path`, `worktree_name` |

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

238 tests covering:
- Base hook validation
- All 24 hook types (parametrized)
- Parser dispatch function
- Forward compatibility
- Output models (including the new `defer` permission decision and `PermissionDeniedOutput`)
- JSON serialization round-trips

---

*Last updated: January 2025*
*Claude Code version: Latest*
