"""
Worktree lifecycle hooks - WorktreeCreate, WorktreeRemove.
"""

from __future__ import annotations

from typing import Literal
from pydantic import Field

from .base import BaseHook


# =============================================================================
# Worktree Lifecycle Hooks
# =============================================================================

class WorktreeCreateHook(BaseHook):
    """Worktree is about to be created. CAN override worktreePath via HTTP hook response."""

    hook_event_name: Literal["WorktreeCreate"] = Field(
        default="WorktreeCreate",
        description="Always 'WorktreeCreate' for this hook type"
    )

    worktree_name: str = Field(
        ...,
        description="The chosen or generated name for the new worktree"
    )

    base_ref: str = Field(
        ...,
        description="Git ref the worktree branches from (e.g., 'main', 'origin/develop')"
    )


class WorktreeRemoveHook(BaseHook):
    """Worktree removed. Cannot block execution."""

    hook_event_name: Literal["WorktreeRemove"] = Field(
        default="WorktreeRemove",
        description="Always 'WorktreeRemove' for this hook type"
    )

    worktree_path: str = Field(
        ...,
        description="Absolute path to the worktree being removed"
    )

    worktree_name: str = Field(
        ...,
        description="Name of the worktree being removed"
    )


__all__ = [
    "WorktreeCreateHook",
    "WorktreeRemoveHook",
]
