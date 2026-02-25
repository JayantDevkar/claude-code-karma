# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Captain Hook is a type-safe Pydantic model library for Claude Code hook events. It provides models for all 10 hook types that fire during Claude Code sessions, with forward compatibility via `extra="allow"` configuration.

## Commands

```bash
# Run all tests
pytest tests/test_models.py -v

# Run specific test class
pytest tests/test_models.py::TestPreToolUseHook -v

# Run with coverage
pytest tests/test_models.py --cov=src/captain_hook

# Verify imports work
python3 -c "from captain_hook import parse_hook_event, PreToolUseHook"
```

## Architecture

The codebase follows a modular package structure under `src/captain_hook/`:

- **`base.py`** - Foundation: `BaseHook` class with 5 common fields (`session_id`, `transcript_path`, `cwd`, `permission_mode`, `hook_event_name`) and all Literal type definitions
- **`__init__.py`** - Entry point: exports all models, contains `parse_hook_event()` dispatcher and `HOOK_TYPE_MAP` registry
- **Hook modules** - Grouped by category:
  - `tool_hooks.py` - PreToolUseHook, PostToolUseHook
  - `user_hooks.py` - UserPromptSubmitHook, PermissionRequestHook, NotificationHook
  - `session_hooks.py` - SessionStartHook, SessionEndHook
  - `agent_hooks.py` - StopHook, SubagentStopHook
  - `context_hooks.py` - PreCompactHook
- **`outputs.py`** - Response models for hooks that return JSON (PreToolUseOutput, StopOutput, PermissionRequestOutput)

The root `models.py` is a backward compatibility layer that re-exports from `src.captain_hook`.

## Key Patterns

**Parsing hook events:**
```python
from captain_hook import parse_hook_event
hook = parse_hook_event(json_data)  # Returns typed hook based on hook_event_name
```

**All hooks inherit from BaseHook** and use `ConfigDict(extra="allow")` for forward compatibility.

**Hook capabilities vary:**
- Can block (exit code 2): PreToolUse, UserPromptSubmit, PermissionRequest
- Can modify input: PreToolUse
- Can modify environment: SessionStart
- Can force continuation: Stop, SubagentStop

## Documentation

Each hook type has detailed documentation in `docs/hooks/[HookName]-info-available.md` describing all available fields and behaviors.
