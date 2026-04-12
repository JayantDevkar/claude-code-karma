"""
Filesystem lifecycle hooks - CwdChanged, FileChanged.
"""

from __future__ import annotations

from typing import Literal
from pydantic import Field

from .base import BaseHook


# =============================================================================
# Filesystem Lifecycle Hooks
# =============================================================================

class CwdChangedHook(BaseHook):
    """
    Fires when the working directory changes during a session.

    Cannot block - purely observational.
    Use cases: tracking project navigation, environment switching, audit logs.
    """

    hook_event_name: Literal["CwdChanged"] = Field(
        default="CwdChanged",
        description="Always 'CwdChanged' for this hook type"
    )

    old_cwd: str = Field(
        ...,
        description="Previous working directory before the change"
    )

    new_cwd: str = Field(
        ...,
        description="New working directory after the change"
    )


class FileChangedHook(BaseHook):
    """
    Fires when an external file change is detected.

    Cannot block - purely observational.
    Use cases: cache invalidation, refresh prompts, change tracking.
    """

    hook_event_name: Literal["FileChanged"] = Field(
        default="FileChanged",
        description="Always 'FileChanged' for this hook type"
    )

    file_path: str = Field(
        ...,
        description="Absolute path to the file that changed"
    )

    file_name: str = Field(
        ...,
        description="Basename of the file that changed"
    )


__all__ = [
    "CwdChangedHook",
    "FileChangedHook",
]
