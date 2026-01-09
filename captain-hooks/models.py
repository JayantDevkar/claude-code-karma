"""
Claude Code Hooks - Pydantic Models

Extensible type-safe models for all Claude Code hook events.
Designed for future-proofing: new fields can be added without breaking existing code.

Usage:
    import json
    from models import parse_hook_event, HookEvent

    # Parse any hook event from stdin
    data = json.loads(sys.stdin.read())
    hook = parse_hook_event(data)

    # Type-narrow based on hook type
    if isinstance(hook, PreToolUseHook):
        print(f"Tool: {hook.tool_name}")
"""

from __future__ import annotations

from typing import Any, Dict, Literal, Optional, Union
from pydantic import BaseModel, Field, ConfigDict


# =============================================================================
# Enums / Literal Types
# =============================================================================

PermissionMode = Literal["default", "plan", "acceptEdits", "dontAsk", "bypassPermissions"]

HookEventName = Literal[
    "PreToolUse",
    "PostToolUse",
    "UserPromptSubmit",
    "SessionStart",
    "SessionEnd",
    "Stop",
    "SubagentStop",
    "PreCompact",
    "PermissionRequest",
    "Notification",
]

SessionStartSource = Literal["startup", "resume", "clear", "compact"]

SessionEndReason = Literal["prompt_input_exit", "clear", "logout", "other"]

PreCompactTrigger = Literal["auto", "manual"]

NotificationType = Literal["permission_prompt", "idle_prompt", "auth_success", "elicitation_dialog"]


# =============================================================================
# Base Hook Class
# =============================================================================

class BaseHook(BaseModel):
    """
    Base class for all Claude Code hook events.

    Contains common fields present in every hook type.
    Configured with extra='allow' to accept unknown fields for forward compatibility.
    """

    model_config = ConfigDict(extra="allow")

    session_id: str = Field(
        ...,
        description="Unique identifier for the current Claude Code session"
    )

    transcript_path: str = Field(
        ...,
        description="Absolute path to the conversation JSONL transcript file"
    )

    cwd: str = Field(
        ...,
        description="Current working directory when the hook fired"
    )

    permission_mode: str = Field(
        ...,
        description="Current permission mode: default, plan, acceptEdits, dontAsk, or bypassPermissions"
    )

    hook_event_name: str = Field(
        ...,
        description="Name of the hook event type"
    )


# =============================================================================
# Tool-Related Hooks
# =============================================================================

class PreToolUseHook(BaseHook):
    """
    Fires before a tool is executed.

    Can block execution (exit code 2) or modify tool inputs via JSON output.
    Use cases: security validation, input sanitization, audit logging.
    """

    hook_event_name: Literal["PreToolUse"] = Field(
        default="PreToolUse",
        description="Always 'PreToolUse' for this hook type"
    )

    tool_name: str = Field(
        ...,
        description="Name of the tool being called (e.g., 'Write', 'Bash', 'mcp__server__tool')"
    )

    tool_use_id: str = Field(
        ...,
        description="Unique identifier for this specific tool invocation"
    )

    tool_input: Dict[str, Any] = Field(
        default_factory=dict,
        description="Tool-specific input parameters (schema varies by tool_name)"
    )


class PostToolUseHook(BaseHook):
    """
    Fires after a tool completes execution.

    Cannot block or modify - purely observational.
    Use cases: logging, metrics, notifications, state tracking.
    """

    hook_event_name: Literal["PostToolUse"] = Field(
        default="PostToolUse",
        description="Always 'PostToolUse' for this hook type"
    )

    tool_name: str = Field(
        ...,
        description="Name of the tool that was called"
    )

    tool_use_id: str = Field(
        ...,
        description="Unique identifier for this tool call"
    )

    tool_input: Dict[str, Any] = Field(
        default_factory=dict,
        description="The original input parameters passed to the tool"
    )

    tool_response: str = Field(
        ...,
        description="The tool's output/result or error message"
    )


# =============================================================================
# User Interaction Hooks
# =============================================================================

class UserPromptSubmitHook(BaseHook):
    """
    Fires when the user submits a message before Claude processes it.

    Can block (exit code 2) to prevent processing.
    Use cases: input validation, content filtering, context injection.
    """

    hook_event_name: Literal["UserPromptSubmit"] = Field(
        default="UserPromptSubmit",
        description="Always 'UserPromptSubmit' for this hook type"
    )

    prompt: str = Field(
        ...,
        description="The full text of the user's submitted message"
    )


class PermissionRequestHook(BaseHook):
    """
    Fires when Claude shows a permission dialog to the user.

    Can auto-allow/deny via JSON output before dialog is shown.
    Use cases: policy enforcement, auto-approval rules, audit logging.
    """

    hook_event_name: Literal["PermissionRequest"] = Field(
        default="PermissionRequest",
        description="Always 'PermissionRequest' for this hook type"
    )

    notification_type: str = Field(
        ...,
        description="Type of permission request (e.g., 'permission_prompt')"
    )

    message: str = Field(
        ...,
        description="The permission prompt text describing the requested action"
    )


class NotificationHook(BaseHook):
    """
    Fires when Claude sends system notifications.

    Cannot block or modify - purely informational.
    Use cases: external notification routing, logging, alerts.
    """

    hook_event_name: Literal["Notification"] = Field(
        default="Notification",
        description="Always 'Notification' for this hook type"
    )

    notification_type: str = Field(
        ...,
        description="Type of notification: permission_prompt, idle_prompt, auth_success, elicitation_dialog"
    )


# =============================================================================
# Session Lifecycle Hooks
# =============================================================================

class SessionStartHook(BaseHook):
    """
    Fires when a Claude Code session begins or resumes.

    Can set environment variables via CLAUDE_ENV_FILE.
    Use cases: environment setup, state restoration, logging.
    """

    hook_event_name: Literal["SessionStart"] = Field(
        default="SessionStart",
        description="Always 'SessionStart' for this hook type"
    )

    source: SessionStartSource = Field(
        ...,
        description="Why session started: startup (fresh), resume (existing), clear (after /clear), compact (after compaction)"
    )


class SessionEndHook(BaseHook):
    """
    Fires when a Claude Code session ends.

    Cannot block - purely observational.
    Use cases: cleanup, final logging, state persistence, analytics.
    """

    hook_event_name: Literal["SessionEnd"] = Field(
        default="SessionEnd",
        description="Always 'SessionEnd' for this hook type"
    )

    reason: SessionEndReason = Field(
        ...,
        description="Why session ended: prompt_input_exit, clear, logout, or other"
    )


# =============================================================================
# Agent Control Hooks
# =============================================================================

class StopHook(BaseHook):
    """
    Fires when the main Claude agent finishes responding.

    Can force continuation via JSON output {"decision": "continue"}.
    Use cases: task completion checks, automated workflows.
    """

    hook_event_name: Literal["Stop"] = Field(
        default="Stop",
        description="Always 'Stop' for this hook type"
    )

    stop_hook_active: bool = Field(
        ...,
        description="True if already continuing from a previous Stop hook, False if finished naturally"
    )


class SubagentStopHook(BaseHook):
    """
    Fires when a subagent (spawned via Task tool) finishes.

    Can force subagent continuation via JSON output.
    Use cases: subagent orchestration, task completion verification.
    """

    hook_event_name: Literal["SubagentStop"] = Field(
        default="SubagentStop",
        description="Always 'SubagentStop' for this hook type"
    )

    stop_hook_active: bool = Field(
        ...,
        description="True if subagent is already continuing from a previous hook"
    )


# =============================================================================
# Context Management Hooks
# =============================================================================

class PreCompactHook(BaseHook):
    """
    Fires before context compaction occurs.

    Cannot block - purely observational.
    Use cases: preserve important data, log compaction events.
    """

    hook_event_name: Literal["PreCompact"] = Field(
        default="PreCompact",
        description="Always 'PreCompact' for this hook type"
    )

    trigger: PreCompactTrigger = Field(
        ...,
        description="What triggered compaction: 'auto' (context limit) or 'manual' (/compact command)"
    )

    custom_instructions: str = Field(
        default="",
        description="User-provided compaction instructions (only for manual with custom text)"
    )


# =============================================================================
# Discriminated Union for Parsing
# =============================================================================

HookEvent = Union[
    PreToolUseHook,
    PostToolUseHook,
    UserPromptSubmitHook,
    SessionStartHook,
    SessionEndHook,
    StopHook,
    SubagentStopHook,
    PreCompactHook,
    PermissionRequestHook,
    NotificationHook,
]

# Mapping from hook_event_name to class for dynamic parsing
HOOK_TYPE_MAP: Dict[str, type[BaseHook]] = {
    "PreToolUse": PreToolUseHook,
    "PostToolUse": PostToolUseHook,
    "UserPromptSubmit": UserPromptSubmitHook,
    "SessionStart": SessionStartHook,
    "SessionEnd": SessionEndHook,
    "Stop": StopHook,
    "SubagentStop": SubagentStopHook,
    "PreCompact": PreCompactHook,
    "PermissionRequest": PermissionRequestHook,
    "Notification": NotificationHook,
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
# Hook Output Models (for hook responses)
# =============================================================================

class HookOutput(BaseModel):
    """Base model for hook script output (returned via stdout)."""

    model_config = ConfigDict(extra="allow")


class PreToolUseOutput(HookOutput):
    """Output schema for PreToolUse hooks."""

    class HookSpecificOutput(BaseModel):
        model_config = ConfigDict(extra="allow")

        permission_decision: Optional[Literal["allow", "deny"]] = Field(
            default=None,
            alias="permissionDecision",
            description="Auto-approve or deny the tool execution"
        )
        permission_decision_reason: Optional[str] = Field(
            default=None,
            alias="permissionDecisionReason",
            description="Reason for the permission decision"
        )
        updated_input: Optional[Dict[str, Any]] = Field(
            default=None,
            alias="updatedInput",
            description="Modified tool input parameters"
        )
        additional_context: Optional[str] = Field(
            default=None,
            alias="additionalContext",
            description="Extra context to add to the conversation"
        )

    hook_specific_output: Optional[HookSpecificOutput] = Field(
        default=None,
        alias="hookSpecificOutput"
    )


class StopOutput(HookOutput):
    """Output schema for Stop/SubagentStop hooks."""

    class HookSpecificOutput(BaseModel):
        model_config = ConfigDict(extra="allow")

        decision: Optional[Literal["continue", "stop"]] = Field(
            default=None,
            description="Whether to continue or stop the agent"
        )
        reason: Optional[str] = Field(
            default=None,
            description="Reason for the decision"
        )

    hook_specific_output: Optional[HookSpecificOutput] = Field(
        default=None,
        alias="hookSpecificOutput"
    )


class PermissionRequestOutput(HookOutput):
    """Output schema for PermissionRequest hooks."""

    class HookSpecificOutput(BaseModel):
        model_config = ConfigDict(extra="allow")

        permission_decision: Optional[Literal["allow", "deny"]] = Field(
            default=None,
            alias="permissionDecision",
            description="Auto-approve or deny the permission request"
        )
        permission_decision_reason: Optional[str] = Field(
            default=None,
            alias="permissionDecisionReason",
            description="Reason shown to user for the decision"
        )

    hook_specific_output: Optional[HookSpecificOutput] = Field(
        default=None,
        alias="hookSpecificOutput"
    )


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
    "UserPromptSubmitHook",
    "SessionStartHook",
    "SessionEndHook",
    "StopHook",
    "SubagentStopHook",
    "PreCompactHook",
    "PermissionRequestHook",
    "NotificationHook",
    # Output Types
    "HookOutput",
    "PreToolUseOutput",
    "StopOutput",
    "PermissionRequestOutput",
    # Enums
    "PermissionMode",
    "HookEventName",
    "SessionStartSource",
    "SessionEndReason",
    "PreCompactTrigger",
    "NotificationType",
]
