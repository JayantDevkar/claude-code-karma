"""Team domain model.

A Team is a named group of devices that share Claude Code sessions via Syncthing.
All state transitions return new immutable instances.
"""
from __future__ import annotations

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
    """Immutable domain model representing a sync team."""

    model_config = ConfigDict(frozen=True)

    name: str
    leader_device_id: str
    leader_member_tag: str
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

        Calls member.remove() and returns the removed Member.

        Raises:
            InvalidTransitionError: if the team is not ACTIVE.
            AuthorizationError: if *by_device* is not the leader.
        """
        self._assert_active()
        if not self.is_leader(by_device):
            raise AuthorizationError(
                f"Device '{by_device}' is not the team leader and cannot remove members."
            )
        return member.remove()
