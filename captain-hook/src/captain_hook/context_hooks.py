"""
Context Management Hooks

Hook models for context-related events like compaction and instruction loading.
"""

from __future__ import annotations

from typing import List, Literal, Optional
from pydantic import Field

from .base import BaseHook, PreCompactTrigger


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


class InstructionsLoadedHook(BaseHook):
    """CLAUDE.md or rules file loaded. Cannot block execution."""

    hook_event_name: Literal["InstructionsLoaded"] = Field(
        default="InstructionsLoaded",
        description="Always 'InstructionsLoaded' for this hook type"
    )

    file_path: str = Field(
        ...,
        description="Path to the CLAUDE.md / rules file that was loaded"
    )

    memory_type: str = Field(
        ...,
        description="Category of memory loaded (e.g., 'project', 'user', 'plugin', 'managed')"
    )

    load_reason: str = Field(
        ...,
        description="Why the file was loaded (e.g., 'startup', 'import', 'glob_match')"
    )

    globs: List[str] = Field(
        default_factory=list,
        description="Glob patterns associated with the load (when triggered by globs)"
    )

    trigger_file_path: Optional[str] = Field(
        default=None,
        description="File that triggered the load (for imports/glob matches)"
    )

    parent_file_path: Optional[str] = Field(
        default=None,
        description="Parent CLAUDE.md that imported this one (for nested imports)"
    )


__all__ = [
    "PreCompactHook",
    "InstructionsLoadedHook",
]
