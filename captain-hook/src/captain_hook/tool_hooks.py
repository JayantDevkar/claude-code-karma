"""
Claude Code Hooks - Tool-Related Hook Models

This module contains hook models for tool execution events:
- PreToolUseHook: Fires before a tool is executed
- PostToolUseHook: Fires after a tool completes execution
"""

from __future__ import annotations

from typing import Any, Dict, Literal, Optional
from pydantic import Field

from .base import BaseHook


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


class PostToolUseFailureHook(BaseHook):
    """
    Fires after a tool execution fails.

    Similar to PostToolUse but for failed tool calls.
    Use cases: error logging, retry logic, alerting.
    """

    hook_event_name: Literal["PostToolUseFailure"] = Field(
        default="PostToolUseFailure",
        description="Always 'PostToolUseFailure' for this hook type"
    )

    tool_name: str = Field(
        ...,
        description="Name of the tool that failed"
    )

    tool_input: Dict[str, Any] = Field(
        ...,
        description="Input parameters passed to the tool"
    )

    tool_use_id: str = Field(
        ...,
        description="Unique identifier for this tool call"
    )

    error: Optional[str] = Field(
        None,
        description="Error message or details about the failure"
    )


__all__ = [
    "PreToolUseHook",
    "PostToolUseHook",
    "PostToolUseFailureHook",
]
