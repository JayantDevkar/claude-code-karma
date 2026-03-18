"""Member domain model.

A Member represents a single device's participation in a Team.
member_tag = "{user_id}.{machine_tag}" uniquely identifies a device within a team.
All state transitions return new immutable instances.
"""
from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, computed_field

from domain.team import InvalidTransitionError


class MemberStatus(str, Enum):
    ADDED = "added"
    ACTIVE = "active"
    REMOVED = "removed"


class Member(BaseModel):
    """Immutable domain model representing a team member (device)."""

    model_config = ConfigDict(frozen=True)

    member_id: str
    team_id: str
    user_id: str
    machine_tag: str
    device_id: str
    status: MemberStatus = MemberStatus.ADDED
    joined_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )

    # ------------------------------------------------------------------
    # Derived properties
    # ------------------------------------------------------------------

    @computed_field  # type: ignore[misc]
    @property
    def member_tag(self) -> str:
        """Unique device identifier within a team: '{user_id}.{machine_tag}'."""
        return f"{self.user_id}.{self.machine_tag}"

    # ------------------------------------------------------------------
    # Class methods
    # ------------------------------------------------------------------

    @classmethod
    def from_member_tag(
        cls,
        *,
        member_tag: str,
        member_id: str,
        team_id: str,
        device_id: str,
        status: MemberStatus = MemberStatus.ADDED,
        joined_at: Optional[datetime] = None,
    ) -> "Member":
        """Create a Member by splitting *member_tag* on the first dot.

        Per spec: user_id cannot contain dots; first dot separates user from machine.
        """
        user_id, machine_tag = member_tag.split(".", 1)
        kwargs = dict(
            member_id=member_id,
            team_id=team_id,
            user_id=user_id,
            machine_tag=machine_tag,
            device_id=device_id,
            status=status,
        )
        if joined_at is not None:
            kwargs["joined_at"] = joined_at
        return cls(**kwargs)

    # ------------------------------------------------------------------
    # State transitions
    # ------------------------------------------------------------------

    def activate(self) -> "Member":
        """Transition ADDED → ACTIVE.

        Raises:
            InvalidTransitionError: if current status is not ADDED.
        """
        if self.status != MemberStatus.ADDED:
            raise InvalidTransitionError(
                f"Cannot activate member in status '{self.status.value}'. "
                "Member must be in ADDED status."
            )
        return self.model_copy(update={"status": MemberStatus.ACTIVE})

    def remove(self) -> "Member":
        """Transition ADDED|ACTIVE → REMOVED.

        Raises:
            InvalidTransitionError: if current status is REMOVED.
        """
        if self.status == MemberStatus.REMOVED:
            raise InvalidTransitionError(
                f"Member is already in REMOVED status."
            )
        return self.model_copy(update={"status": MemberStatus.REMOVED})
