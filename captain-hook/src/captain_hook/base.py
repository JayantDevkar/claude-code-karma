"""
Captain Hook - Base Models

Extensible type-safe base models for Claude Code hook events.
Designed for future-proofing: new fields can be added without breaking existing code.

This module provides:
- Literal type definitions for hook enumerations
- BaseHook class with common fields present in every hook type

Usage:
    from captain_hook.base import BaseHook, PermissionMode, HookEventName

    class MyCustomHook(BaseHook):
        custom_field: str
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


# =============================================================================
# Enums / Literal Types
# =============================================================================

PermissionMode = Literal["default", "plan", "acceptEdits", "dontAsk", "bypassPermissions"]

HookEventName = Literal[
    # Tool lifecycle
    "PreToolUse",
    "PostToolUse",
    "PostToolUseFailure",
    # User interaction
    "UserPromptSubmit",
    "PermissionRequest",
    "PermissionDenied",
    "Notification",
    "Elicitation",
    "ElicitationResult",
    # Session lifecycle
    "SessionStart",
    "SessionEnd",
    # Agent control
    "Stop",
    "SubagentStart",
    "SubagentStop",
    # Context
    "PreCompact",
    "InstructionsLoaded",
    # Setup
    "Setup",
    # Filesystem
    "CwdChanged",
    "FileChanged",
    # Agent teams (experimental)
    "TaskCreated",
    "TaskCompleted",
    "TeammateIdle",
    # Worktree lifecycle
    "WorktreeCreate",
    "WorktreeRemove",
]

SetupTrigger = Literal["init", "maintenance"]

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
# Exports
# =============================================================================

__all__ = [
    # Base
    "BaseHook",
    # Enums
    "PermissionMode",
    "HookEventName",
    "SessionStartSource",
    "SessionEndReason",
    "PreCompactTrigger",
    "NotificationType",
    "SetupTrigger",
]
