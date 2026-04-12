"""Agent Teams lifecycle hooks (experimental - gated on CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1)."""

from __future__ import annotations

from typing import Literal, Optional
from pydantic import Field

from .base import BaseHook


# =============================================================================
# Agent Teams Lifecycle Hooks
# =============================================================================

class TaskCreatedHook(BaseHook):
    """Task created in an agent team. CAN block via {"continue": false}."""

    hook_event_name: Literal["TaskCreated"] = Field(
        default="TaskCreated",
        description="Always 'TaskCreated' for this hook type"
    )

    task_id: str = Field(
        ...,
        description="Unique identifier for the created task"
    )

    task_subject: str = Field(
        ...,
        description="Short subject/title of the task"
    )

    task_description: Optional[str] = Field(
        default=None,
        description="Longer task description (if provided)"
    )

    teammate_name: Optional[str] = Field(
        default=None,
        description="Name of the teammate the task is assigned to (if any)"
    )

    team_name: str = Field(
        ...,
        description="Name of the team where the task was created"
    )


class TaskCompletedHook(BaseHook):
    """Task completed in an agent team. CAN block via {"continue": false}."""

    hook_event_name: Literal["TaskCompleted"] = Field(
        default="TaskCompleted",
        description="Always 'TaskCompleted' for this hook type"
    )

    task_id: str = Field(
        ...,
        description="Unique identifier for the completed task"
    )

    task_subject: str = Field(
        ...,
        description="Short subject/title of the task"
    )

    task_description: Optional[str] = Field(
        default=None,
        description="Longer task description (if provided)"
    )

    teammate_name: Optional[str] = Field(
        default=None,
        description="Name of the teammate that completed the task (if any)"
    )

    team_name: str = Field(
        ...,
        description="Name of the team where the task was completed"
    )


class TeammateIdleHook(BaseHook):
    """Teammate became idle (awaiting task). CAN block via exit 2."""

    hook_event_name: Literal["TeammateIdle"] = Field(
        default="TeammateIdle",
        description="Always 'TeammateIdle' for this hook type"
    )

    agent_id: str = Field(
        ...,
        description="Unique identifier for the idle agent"
    )

    agent_type: str = Field(
        ...,
        description="Type of the idle agent"
    )

    team_name: Optional[str] = Field(
        default=None,
        description="Name of the team the agent belongs to (if any)"
    )


__all__ = [
    "TaskCreatedHook",
    "TaskCompletedHook",
    "TeammateIdleHook",
]
