"""
Captain Hook - Claude Code Hooks Library

Extensible type-safe Pydantic models for all Claude Code hook events.
Designed for forward compatibility: new fields can be added without breaking existing code.

Usage:
    import json
    from captain_hook import parse_hook_event, PreToolUseHook

    # Parse any hook event from stdin
    data = json.loads(sys.stdin.read())
    hook = parse_hook_event(data)

    # Type-narrow based on hook type
    if isinstance(hook, PreToolUseHook):
        print(f"Tool: {hook.tool_name}")
"""

from __future__ import annotations

from typing import Any, Dict, Union

# =============================================================================
# Base and Types
# =============================================================================

from .base import (
    BaseHook,
    PermissionMode,
    HookEventName,
    SessionStartSource,
    SessionEndReason,
    PreCompactTrigger,
    NotificationType,
    SetupTrigger,
)

# =============================================================================
# Hook Types
# =============================================================================

from .tool_hooks import PreToolUseHook, PostToolUseHook, PostToolUseFailureHook
from .user_hooks import (
    UserPromptSubmitHook,
    PermissionRequestHook,
    NotificationHook,
    PermissionDeniedHook,
    ElicitationHook,
    ElicitationResultHook,
)
from .session_hooks import SessionStartHook, SessionEndHook
from .agent_hooks import StopHook, SubagentStopHook, SubagentStartHook
from .context_hooks import PreCompactHook, InstructionsLoadedHook
from .setup_hooks import SetupHook
from .fs_hooks import CwdChangedHook, FileChangedHook
from .team_hooks import TaskCreatedHook, TaskCompletedHook, TeammateIdleHook
from .worktree_hooks import WorktreeCreateHook, WorktreeRemoveHook

# =============================================================================
# Output Models
# =============================================================================

from .outputs import (
    HookOutput,
    PreToolUseOutput,
    StopOutput,
    PermissionRequestOutput,
    PermissionDeniedOutput,
)

# =============================================================================
# Discriminated Union for Parsing
# =============================================================================

HookEvent = Union[
    PreToolUseHook,
    PostToolUseHook,
    PostToolUseFailureHook,
    UserPromptSubmitHook,
    SessionStartHook,
    SessionEndHook,
    StopHook,
    SubagentStartHook,
    SubagentStopHook,
    PreCompactHook,
    PermissionRequestHook,
    NotificationHook,
    SetupHook,
    InstructionsLoadedHook,
    PermissionDeniedHook,
    ElicitationHook,
    ElicitationResultHook,
    CwdChangedHook,
    FileChangedHook,
    TaskCreatedHook,
    TaskCompletedHook,
    TeammateIdleHook,
    WorktreeCreateHook,
    WorktreeRemoveHook,
]

# Mapping from hook_event_name to class for dynamic parsing
HOOK_TYPE_MAP: Dict[str, type[BaseHook]] = {
    "PreToolUse": PreToolUseHook,
    "PostToolUse": PostToolUseHook,
    "PostToolUseFailure": PostToolUseFailureHook,
    "UserPromptSubmit": UserPromptSubmitHook,
    "SessionStart": SessionStartHook,
    "SessionEnd": SessionEndHook,
    "Stop": StopHook,
    "SubagentStart": SubagentStartHook,
    "SubagentStop": SubagentStopHook,
    "PreCompact": PreCompactHook,
    "PermissionRequest": PermissionRequestHook,
    "Notification": NotificationHook,
    "Setup": SetupHook,
    # New in v2.1.83-v2.1.92
    "InstructionsLoaded": InstructionsLoadedHook,
    "PermissionDenied": PermissionDeniedHook,
    "Elicitation": ElicitationHook,
    "ElicitationResult": ElicitationResultHook,
    "CwdChanged": CwdChangedHook,
    "FileChanged": FileChangedHook,
    "TaskCreated": TaskCreatedHook,
    "TaskCompleted": TaskCompletedHook,
    "TeammateIdle": TeammateIdleHook,
    "WorktreeCreate": WorktreeCreateHook,
    "WorktreeRemove": WorktreeRemoveHook,
}


def parse_hook_event(data: Dict[str, Any]) -> HookEvent:
    """
    Parse a hook event dictionary into the appropriate typed model.

    Args:
        data: Raw JSON data from stdin containing hook_event_name

    Returns:
        Typed hook instance (PreToolUseHook, PostToolUseHook, etc.)

    Raises:
        ValueError: If hook_event_name is missing or unknown
        ValidationError: If required fields are missing

    Example:
        >>> data = {"hook_event_name": "PreToolUse", "session_id": "...", ...}
        >>> hook = parse_hook_event(data)
        >>> isinstance(hook, PreToolUseHook)
        True
    """
    hook_name = data.get("hook_event_name")

    if not hook_name:
        raise ValueError("Missing 'hook_event_name' in hook data")

    hook_class = HOOK_TYPE_MAP.get(hook_name)

    if not hook_class:
        # Fall back to BaseHook for unknown types (forward compatibility)
        return BaseHook.model_validate(data)

    return hook_class.model_validate(data)


# =============================================================================
# Exports
# =============================================================================

__all__ = [
    # Base
    "BaseHook",
    "HookEvent",
    "parse_hook_event",
    "HOOK_TYPE_MAP",
    # Hook Types
    "PreToolUseHook",
    "PostToolUseHook",
    "PostToolUseFailureHook",
    "UserPromptSubmitHook",
    "SessionStartHook",
    "SessionEndHook",
    "StopHook",
    "SubagentStartHook",
    "SubagentStopHook",
    "PreCompactHook",
    "PermissionRequestHook",
    "NotificationHook",
    "SetupHook",
    # New hook types (v2.1.83 - v2.1.92)
    "InstructionsLoadedHook",
    "PermissionDeniedHook",
    "ElicitationHook",
    "ElicitationResultHook",
    "CwdChangedHook",
    "FileChangedHook",
    "TaskCreatedHook",
    "TaskCompletedHook",
    "TeammateIdleHook",
    "WorktreeCreateHook",
    "WorktreeRemoveHook",
    # Output Types
    "HookOutput",
    "PreToolUseOutput",
    "StopOutput",
    "PermissionRequestOutput",
    "PermissionDeniedOutput",
    # Enums
    "PermissionMode",
    "HookEventName",
    "SessionStartSource",
    "SessionEndReason",
    "PreCompactTrigger",
    "NotificationType",
    "SetupTrigger",
]

__version__ = "0.1.0"
