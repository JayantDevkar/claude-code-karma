"""Team domain model.

A Team is a named group of devices that share Claude Code sessions via Syncthing.
All state transitions return new immutable instances.
"""
from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import List

from pydantic import BaseModel, ConfigDict, Field


class TeamStatus(str, Enum):
    ACTIVE = "active"
    DISSOLVED = "dissolved"


class AuthorizationError(Exception):
    """Raised when a device tries to perform an action it is not authorized for."""


class InvalidTransitionError(Exception):
    """Raised when a state transition is not allowed from the current state."""


class Team(BaseModel):
    """Immutable domain model representing a sync team."""

    model_config = ConfigDict(frozen=True)

    team_id: str
    name: str
    created_by: str
    leader_device: str
    status: TeamStatus = TeamStatus.ACTIVE
    member_devices: List[str] = Field(default_factory=list)
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------

    def is_leader(self, device: str) -> bool:
        """Return True if *device* is the current team leader."""
        return self.leader_device == device

    # ------------------------------------------------------------------
    # State transitions
    # ------------------------------------------------------------------

    def dissolve(self, *, by_device: str) -> "Team":
        """Dissolve the team.  Only the leader may dissolve.

        Raises:
            AuthorizationError: if *by_device* is not the leader.
            InvalidTransitionError: if the team is already dissolved.
        """
        if not self.is_leader(by_device):
            raise AuthorizationError(
                f"Device '{by_device}' is not the team leader and cannot dissolve the team."
            )
        if self.status == TeamStatus.DISSOLVED:
            raise InvalidTransitionError(
                f"Team '{self.team_id}' is already dissolved."
            )
        return self.model_copy(update={"status": TeamStatus.DISSOLVED})

    def add_member(self, device: str, *, by_device: str) -> "Team":
        """Add *device* to the team's member list.

        Idempotent — adding an already-present device is a no-op.

        Raises:
            AuthorizationError: if *by_device* is not the leader.
        """
        if not self.is_leader(by_device):
            raise AuthorizationError(
                f"Device '{by_device}' is not the team leader and cannot add members."
            )
        if device in self.member_devices:
            return self
        return self.model_copy(update={"member_devices": [*self.member_devices, device]})

    def remove_member(self, device: str, *, by_device: str) -> "Team":
        """Remove *device* from the team's member list.

        Raises:
            AuthorizationError: if *by_device* is not the leader.
        """
        if not self.is_leader(by_device):
            raise AuthorizationError(
                f"Device '{by_device}' is not the team leader and cannot remove members."
            )
        return self.model_copy(
            update={"member_devices": [d for d in self.member_devices if d != device]}
        )
