"""
User Interaction Hooks

Hook models for user-facing events: prompt submission, permission requests,
notifications, denials, and MCP elicitations.
"""

from __future__ import annotations

from typing import Any, Dict, Literal, Optional
from pydantic import Field

from .base import BaseHook


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

    message: Optional[str] = Field(
        None,
        description="The notification message text (present for permission_prompt and idle_prompt)"
    )


class PermissionDeniedHook(BaseHook):
    """Auto mode denied a tool call. Cannot block execution."""

    hook_event_name: Literal["PermissionDenied"] = Field(
        default="PermissionDenied",
        description="Always 'PermissionDenied' for this hook type"
    )

    tool_name: str = Field(
        ...,
        description="Name of the tool whose call was denied"
    )

    tool_use_id: str = Field(
        ...,
        description="Unique identifier for the denied tool invocation"
    )

    reason: str = Field(
        ...,
        description="Denial reason string explaining why the tool call was rejected"
    )

    tool_input: Dict[str, Any] = Field(
        default_factory=dict,
        description="Original input parameters of the denied tool call"
    )


class ElicitationHook(BaseHook):
    """MCP server requested structured input from user. CAN block via exit 2."""

    hook_event_name: Literal["Elicitation"] = Field(
        default="Elicitation",
        description="Always 'Elicitation' for this hook type"
    )

    mcp_server: str = Field(
        ...,
        description="Name of the MCP server making the elicitation request"
    )

    tool_name: str = Field(
        ...,
        description="Tool that triggered the elicitation request"
    )

    request: Dict[str, Any] = Field(
        default_factory=dict,
        description="The form/schema that the MCP server requested input for"
    )


class ElicitationResultHook(BaseHook):
    """User responded to an MCP elicitation request. CAN block via exit 2."""

    hook_event_name: Literal["ElicitationResult"] = Field(
        default="ElicitationResult",
        description="Always 'ElicitationResult' for this hook type"
    )

    mcp_server: str = Field(
        ...,
        description="Name of the MCP server that originally requested the elicitation"
    )

    user_response: Dict[str, Any] = Field(
        default_factory=dict,
        description="The structured response provided by the user"
    )


__all__ = [
    "UserPromptSubmitHook",
    "PermissionRequestHook",
    "NotificationHook",
    "PermissionDeniedHook",
    "ElicitationHook",
    "ElicitationResultHook",
]
