"""
Background shell + poll models.

Background shells are reconstructed from session JSONL by the indexer:
- Bash tool calls with `run_in_background: true`
- Monitor tool calls (streaming processes)

Each shell row is keyed by the spawn tool_use_id (always unique in Claude's
output) and folds in subsequent BashOutput polls and KillShell termination.
The poll rows store a 4KB output excerpt; the full content remains in JSONL
and is fetched on demand by the router.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field


class ShellToolName(str, Enum):
    """Which Claude Code tool spawned the process."""

    BASH = "Bash"
    MONITOR = "Monitor"


class ShellTerminationReason(str, Enum):
    """How a background shell ended. None means still running."""

    KILL = "kill"          # KillShell tool was called
    NATURAL = "natural"    # Process exited on its own; final BashOutput showed exit
    TIMEOUT = "timeout"    # Timeout reached without explicit termination
    SESSION_END = "session_end"  # Session ended while shell was alive


class ShellPoll(BaseModel):
    """
    One BashOutput call against a background shell.

    output_excerpt is the first 4KB of the returned chunk; output_truncated
    indicates whether the chunk was longer. Full content stays in JSONL.
    """

    model_config = ConfigDict(frozen=True, extra="allow")

    id: int = Field(..., description="DB primary key")
    polled_at: datetime = Field(..., description="When the BashOutput tool was called")
    filter_pattern: Optional[str] = Field(
        None, description="Optional regex passed to BashOutput.filter"
    )
    output_bytes: int = Field(0, description="Length of the full returned chunk in bytes")
    output_excerpt: Optional[str] = Field(
        None, description="First 4KB of returned chunk; None when chunk was empty"
    )
    output_truncated: bool = Field(
        False, description="True when the returned chunk exceeded 4KB and excerpt is partial"
    )
    tool_use_id: str = Field(..., description="toolu_... ID of the BashOutput call")


class BackgroundShell(BaseModel):
    """
    A single background shell or Monitor process, reconstructed from JSONL.

    The row's lifetime spans from the spawn tool_use until either KillShell,
    a natural exit detected in BashOutput, or the session ending. While the
    process is still running, terminated_at and terminated_by are both None;
    they are populated together when the shell closes (enforced by a DB
    coherence CHECK).
    """

    model_config = ConfigDict(frozen=True, extra="allow")

    id: int = Field(..., description="DB primary key")
    session_uuid: str = Field(..., description="Session that spawned this shell")
    tool_use_id: str = Field(
        ..., description="toolu_... ID of the spawn tool call (globally unique)"
    )
    shell_id: Optional[str] = Field(
        None,
        description=(
            "8-character shell_id returned by Claude in the tool_result. None for "
            "Monitor (which does not return a shell_id) or when the result has not "
            "yet been parsed."
        ),
    )
    tool_name: ShellToolName = Field(..., description="Bash or Monitor")
    command: str = Field(..., description="Shell command; truncated to 4KB at insert")
    command_truncated: bool = Field(
        False, description="True when the original command exceeded 4KB"
    )
    description: Optional[str] = Field(None, description="Optional spawn description")
    is_persistent: bool = Field(
        False, description="Monitor only: whether the process was marked persistent"
    )
    timeout_ms: Optional[int] = Field(
        None, description="Spawn-time timeout in milliseconds (None for unlimited)"
    )
    spawned_at: datetime = Field(..., description="Timestamp of the spawn tool_use message")
    terminated_at: Optional[datetime] = Field(
        None, description="None while running; set together with terminated_by on close"
    )
    terminated_by: Optional[ShellTerminationReason] = Field(
        None, description="Why the shell closed; None while running"
    )
    exit_code: Optional[int] = Field(
        None, description="Exit code if detectable from the natural-exit output"
    )
    poll_count: int = Field(0, description="Number of BashOutput calls against this shell")
    total_output_bytes: int = Field(
        0, description="Cumulative bytes returned across all polls"
    )
    last_output_at: Optional[datetime] = Field(
        None, description="Timestamp of the most recent BashOutput call"
    )
    spawn_message_uuid: Optional[str] = Field(
        None, description="UUID of the assistant message that contained the spawn tool_use"
    )

    polls: List[ShellPoll] = Field(
        default_factory=list,
        description="Populated by the per-session query helper; empty in list endpoints",
    )

    @property
    def is_running(self) -> bool:
        """True when the shell has not terminated."""
        return self.terminated_at is None

    @property
    def duration_seconds(self) -> Optional[float]:
        """Wall-clock lifetime; None while still running."""
        if self.terminated_at is None:
            return None
        return (self.terminated_at - self.spawned_at).total_seconds()
