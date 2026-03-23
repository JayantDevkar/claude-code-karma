"""Team domain model.

A Team is a named group of devices that share Claude Code sessions via Syncthing.
All state transitions return new immutable instances.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import TYPE_CHECKING

from pydantic import BaseModel, ConfigDict, Field

if TYPE_CHECKING:
    from domain.member import Member


class TeamStatus(str, Enum):
    ACTIVE = "active"
    DISSOLVED = "dissolved"


class AuthorizationError(Exception):
    """Raised when a device tries to perform an action it is not authorized for."""


class InvalidTransitionError(ValueError):
    """Raised when a state transition is not allowed from the current state."""


class Team(BaseModel):
    """Immutable domain model representing a sync team.

    ``team_id`` is a UUID that uniquely identifies a team *incarnation*.
    When a team is dissolved and re-created with the same name, the new
    team gets a fresh ``team_id``, allowing stale metadata (removal signals,
    folder offers) from the old incarnation to be detected and ignored.
    """

    model_config = ConfigDict(frozen=True)

    name: str
    leader_device_id: str
    leader_member_tag: str
    team_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    status: TeamStatus = TeamStatus.ACTIVE
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------

    def is_leader(self, device_id: str) -> bool:
        """Return True if *device_id* is the current team leader."""
        return self.leader_device_id == device_id

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
                f"Team '{self.name}' is already dissolved."
            )
        return self.model_copy(update={"status": TeamStatus.DISSOLVED})

    def _assert_active(self) -> None:
        """Raise if the team is not ACTIVE."""
        if self.status != TeamStatus.ACTIVE:
            raise InvalidTransitionError(
                f"Team '{self.name}' is {self.status.value}; operation requires ACTIVE status."
            )

    def add_member(self, member: "Member", *, by_device: str) -> "Member":
        """Add *member* to the team.  Only the leader may add members.

        Raises:
            InvalidTransitionError: if the team is not ACTIVE.
            AuthorizationError: if *by_device* is not the leader.
        """
        self._assert_active()
        if not self.is_leader(by_device):
            raise AuthorizationError(
                f"Device '{by_device}' is not the team leader and cannot add members."
            )
        return member

    def remove_member(self, member: "Member", *, by_device: str) -> "Member":
        """Remove *member* from the team.  Only the leader may remove members.

        The leader cannot remove themselves — they must dissolve the team instead.
        Calls member.remove() and returns the removed Member.

        Raises:
            InvalidTransitionError: if the team is not ACTIVE, or if
                trying to remove the leader.
            AuthorizationError: if *by_device* is not the leader.
        """
        self._assert_active()
        if not self.is_leader(by_device):
            raise AuthorizationError(
                f"Device '{by_device}' is not the team leader and cannot remove members."
            )
        if member.member_tag == self.leader_member_tag:
            raise InvalidTransitionError(
                f"Cannot remove the team leader. Use dissolve_team() instead."
            )
        return member.remove()
