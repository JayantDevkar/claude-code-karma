"""
Claude Code Hooks - Pydantic Models (Compatibility Layer)

This file provides backward compatibility for existing code.
New code should import from `captain_hook` package instead:

    from captain_hook import parse_hook_event, PreToolUseHook

This module re-exports all symbols from the refactored package structure.
"""

# Re-export everything from the captain_hook package
from src.captain_hook import (
    # Base
    BaseHook,
    HookEvent,
    parse_hook_event,
    HOOK_TYPE_MAP,
    # Hook Types
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
    # New hook types (v2.1.83 - v2.1.92)
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
    # Output Types
    HookOutput,
    PreToolUseOutput,
    StopOutput,
    PermissionRequestOutput,
    PermissionDeniedOutput,
    # Enums
    PermissionMode,
    HookEventName,
    SessionStartSource,
    SessionEndReason,
    PreCompactTrigger,
    NotificationType,
    SetupTrigger,
)

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
