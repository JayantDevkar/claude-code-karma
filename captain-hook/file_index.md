# Captain Hook - File Index

Complete directory structure and file reference for the Claude Code Hooks library.

---

## Directory Structure

```
captain-hook/
├── docs/
│   └── hooks/                          # Hook documentation
│       ├── PreToolUse-info-available.md
│       ├── PostToolUse-info-available.md
│       ├── UserPromptSubmit-info-available.md
│       ├── SessionStart-info-available.md
│       ├── SessionEnd-info-available.md
│       ├── Stop-info-available.md
│       ├── SubagentStop-info-available.md
│       ├── PreCompact-info-available.md
│       ├── PermissionRequest-info-available.md
│       └── Notification-info-available.md
│
├── src/
│   └── captain_hook/                   # Main package
│       ├── __init__.py                 # Package exports & parse_hook_event()
│       ├── base.py                     # BaseHook class & type definitions
│       ├── tool_hooks.py               # PreToolUseHook, PostToolUseHook
│       ├── user_hooks.py               # UserPromptSubmitHook, PermissionRequestHook, NotificationHook
│       ├── session_hooks.py            # SessionStartHook, SessionEndHook
│       ├── agent_hooks.py              # StopHook, SubagentStopHook
│       ├── context_hooks.py            # PreCompactHook
│       └── outputs.py                  # HookOutput, PreToolUseOutput, StopOutput, PermissionRequestOutput
│
├── tests/
│   ├── __init__.py
│   └── test_models.py                  # 113 comprehensive tests
│
├── models.py                           # Backward compatibility layer
├── README.md                           # Main documentation
├── file_index.md                       # This file
├── VERIFICATION_REPORT.md              # Verification report
├── LICENSE                             # Apache 2.0 License
└── .gitignore
```

---

## Source Files Reference

### Core Package (`src/captain_hook/`)

| File | Purpose | Key Exports |
|------|---------|-------------|
| `__init__.py` | Package entry point, union types, parser | `parse_hook_event()`, `HookEvent`, `HOOK_TYPE_MAP` |
| `base.py` | Base class and type definitions | `BaseHook`, `PermissionMode`, `HookEventName`, etc. |
| `tool_hooks.py` | Tool execution hooks | `PreToolUseHook`, `PostToolUseHook` |
| `user_hooks.py` | User interaction hooks | `UserPromptSubmitHook`, `PermissionRequestHook`, `NotificationHook` |
| `session_hooks.py` | Session lifecycle hooks | `SessionStartHook`, `SessionEndHook` |
| `agent_hooks.py` | Agent control hooks | `StopHook`, `SubagentStopHook` |
| `context_hooks.py` | Context management hooks | `PreCompactHook` |
| `outputs.py` | Response models | `HookOutput`, `PreToolUseOutput`, `StopOutput`, `PermissionRequestOutput` |

---

## Hook Types Quick Reference

| Hook Class | Module | Can Block? | Can Modify? |
|------------|--------|------------|-------------|
| `PreToolUseHook` | `tool_hooks.py` | Yes | Yes (input) |
| `PostToolUseHook` | `tool_hooks.py` | No | No |
| `UserPromptSubmitHook` | `user_hooks.py` | Yes | No |
| `PermissionRequestHook` | `user_hooks.py` | Yes | No |
| `NotificationHook` | `user_hooks.py` | No | No |
| `SessionStartHook` | `session_hooks.py` | No | Yes (env) |
| `SessionEndHook` | `session_hooks.py` | No | No |
| `StopHook` | `agent_hooks.py` | No | Yes (continue) |
| `SubagentStopHook` | `agent_hooks.py` | No | Yes (continue) |
| `PreCompactHook` | `context_hooks.py` | No | No |

---

## Documentation Files (`docs/hooks/`)

| File | Corresponding Class | Description |
|------|---------------------|-------------|
| `PreToolUse-info-available.md` | `PreToolUseHook` | Tool pre-execution hook details |
| `PostToolUse-info-available.md` | `PostToolUseHook` | Tool post-execution hook details |
| `UserPromptSubmit-info-available.md` | `UserPromptSubmitHook` | User input handling hook |
| `SessionStart-info-available.md` | `SessionStartHook` | Session initialization hook |
| `SessionEnd-info-available.md` | `SessionEndHook` | Session termination hook |
| `Stop-info-available.md` | `StopHook` | Main agent stop hook |
| `SubagentStop-info-available.md` | `SubagentStopHook` | Subagent completion hook |
| `PreCompact-info-available.md` | `PreCompactHook` | Context compaction hook |
| `PermissionRequest-info-available.md` | `PermissionRequestHook` | Permission dialog hook |
| `Notification-info-available.md` | `NotificationHook` | System notification hook |

---

## Import Patterns

### Recommended (New Code)

```python
from captain_hook import parse_hook_event, PreToolUseHook, StopOutput

# Or import from specific modules
from captain_hook.base import BaseHook, PermissionMode
from captain_hook.tool_hooks import PreToolUseHook, PostToolUseHook
from captain_hook.outputs import PreToolUseOutput
```

### Legacy (Backward Compatible)

```python
from models import parse_hook_event, PreToolUseHook
```

---

## Type Definitions (`base.py`)

| Type | Values |
|------|--------|
| `PermissionMode` | `"default"`, `"plan"`, `"acceptEdits"`, `"dontAsk"`, `"bypassPermissions"` |
| `HookEventName` | `"PreToolUse"`, `"PostToolUse"`, `"UserPromptSubmit"`, `"SessionStart"`, `"SessionEnd"`, `"Stop"`, `"SubagentStop"`, `"PreCompact"`, `"PermissionRequest"`, `"Notification"` |
| `SessionStartSource` | `"startup"`, `"resume"`, `"clear"`, `"compact"` |
| `SessionEndReason` | `"prompt_input_exit"`, `"clear"`, `"logout"`, `"other"` |
| `PreCompactTrigger` | `"auto"`, `"manual"` |
| `NotificationType` | `"permission_prompt"`, `"idle_prompt"`, `"auth_success"`, `"elicitation_dialog"` |

---

## Testing

```bash
# Run all tests
pytest tests/test_models.py -v

# Run specific test class
pytest tests/test_models.py::TestPreToolUseHook -v

# Run with coverage
pytest tests/test_models.py --cov=src/captain_hook
```

---

*Last updated: January 2025*
