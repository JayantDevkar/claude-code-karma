"""Output models for hook responses.

These models define the structure for data returned from hook scripts via stdout.
"""

from typing import Any, Dict, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field


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
