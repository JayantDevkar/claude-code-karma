"""
Session Lifecycle Hooks

Hooks for session start and end events in Claude Code.
"""

from __future__ import annotations

from typing import Literal, Optional
from pydantic import Field

from .base import BaseHook, SessionStartSource, SessionEndReason


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

    model: Optional[str] = Field(
        None,
        description="Model identifier when available (e.g., 'claude-sonnet-4-20250514')"
    )

    agent_type: Optional[str] = Field(
        None,
        description="Agent type if started with --agent flag (e.g., 'Explore', 'Plan')"
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
# Exports
# =============================================================================

__all__ = [
    "SessionStartHook",
    "SessionEndHook",
]
