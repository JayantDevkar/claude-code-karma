"""
Agent Control Hooks

Hook models for controlling agent behavior and flow.
"""

from __future__ import annotations

from typing import Literal
from pydantic import Field

from .base import BaseHook


# =============================================================================
# Agent Control Hooks
# =============================================================================

class StopHook(BaseHook):
    """
    Fires when the main Claude agent finishes responding.

    Can force continuation via JSON output {"decision": "continue"}.
    Use cases: task completion checks, automated workflows.
    """

    hook_event_name: Literal["Stop"] = Field(
        default="Stop",
        description="Always 'Stop' for this hook type"
    )

    stop_hook_active: bool = Field(
        ...,
        description="True if already continuing from a previous Stop hook, False if finished naturally"
    )


class SubagentStopHook(BaseHook):
    """
    Fires when a subagent (spawned via Task tool) finishes.

    Can force subagent continuation via JSON output.
    Use cases: subagent orchestration, task completion verification.
    """

    hook_event_name: Literal["SubagentStop"] = Field(
        default="SubagentStop",
        description="Always 'SubagentStop' for this hook type"
    )

    stop_hook_active: bool = Field(
        ...,
        description="True if subagent is already continuing from a previous hook"
    )

    agent_id: str = Field(
        ...,
        description="Unique identifier for the subagent that stopped"
    )

    agent_transcript_path: str = Field(
        ...,
        description="Path to subagent's JSONL transcript (e.g., ~/.claude/projects/.../subagents/agent-xxx.jsonl)"
    )


class SubagentStartHook(BaseHook):
    """
    Fires when a subagent (Task tool) is spawned.

    Provides agent_id and agent_type for tracking individual subagents.
    Use cases: subagent monitoring, orchestration, logging.
    """

    hook_event_name: Literal["SubagentStart"] = Field(
        default="SubagentStart",
        description="Always 'SubagentStart' for this hook type"
    )

    agent_id: str = Field(
        ...,
        description="Unique identifier for the subagent (e.g., 'agent-abc123')"
    )

    agent_type: str = Field(
        ...,
        description="Type of subagent: 'Bash', 'Explore', 'Plan', or custom agent name"
    )


__all__ = [
    "StopHook",
    "SubagentStopHook",
    "SubagentStartHook",
]
