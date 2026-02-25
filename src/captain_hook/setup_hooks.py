"""
Setup Hook

Hook model for repository setup and maintenance operations.
Fires when Claude Code is invoked with --init, --init-only, or --maintenance flags.
"""

from __future__ import annotations

from typing import Literal
from pydantic import Field

from .base import BaseHook


class SetupHook(BaseHook):
    """
    Fires when Claude Code is invoked with setup/maintenance flags.

    Triggers:
    - --init or --init-only: trigger="init"
    - --maintenance: trigger="maintenance"

    Use cases: dependency installation, migrations, periodic maintenance.
    Has access to CLAUDE_ENV_FILE for persisting environment variables.
    """

    hook_event_name: Literal["Setup"] = Field(
        default="Setup",
        description="Always 'Setup' for this hook type"
    )

    trigger: str = Field(
        ...,
        description="What triggered this hook: 'init' or 'maintenance'"
    )


__all__ = [
    "SetupHook",
]
