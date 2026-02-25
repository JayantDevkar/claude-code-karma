"""
Context Management Hooks

Hook models for context-related events like compaction.
"""

from __future__ import annotations

from typing import Literal
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


__all__ = [
    "PreCompactHook",
]
