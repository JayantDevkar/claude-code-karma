"""Member domain model.

A Member represents a single device's participation in a Team.
member_tag = "{user_id}.{machine_tag}" uniquely identifies a device within a team.
All state transitions return new immutable instances.
"""
from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field

from domain.team import InvalidTransitionError


class MemberStatus(str, Enum):
    ADDED = "added"
    ACTIVE = "active"
    REMOVED = "removed"


class Member(BaseModel):
    """Immutable domain model representing a team member (device)."""

    model_config = ConfigDict(frozen=True)

    member_tag: str
    team_name: str
    device_id: str
    user_id: str
    machine_tag: str
    status: MemberStatus = MemberStatus.ADDED
    added_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )

    # ------------------------------------------------------------------
    # Derived properties
    # ------------------------------------------------------------------

    @property
    def is_active(self) -> bool:
        """Return True if the member is in ACTIVE status."""
        return self.status == MemberStatus.ACTIVE

    # ------------------------------------------------------------------
    # Class methods
    # ------------------------------------------------------------------

    @classmethod
    def from_member_tag(
        cls,
        *,
        member_tag: str,
        team_name: str,
        device_id: str,
        status: MemberStatus = MemberStatus.ADDED,
        added_at: Optional[datetime] = None,
        updated_at: Optional[datetime] = None,
    ) -> "Member":
        """Create a Member by splitting *member_tag* on the first dot.

        Per spec: user_id cannot contain dots; first dot separates user from machine.
        """
        if "." not in member_tag:
            raise ValueError(
                f"member_tag '{member_tag}' must contain a dot separating user_id and machine_tag"
            )
        user_id, machine_tag = member_tag.split(".", 1)
        kwargs: dict = dict(
            member_tag=member_tag,
            team_name=team_name,
            user_id=user_id,
            machine_tag=machine_tag,
            device_id=device_id,
            status=status,
        )
        if added_at is not None:
            kwargs["added_at"] = added_at
        if updated_at is not None:
            kwargs["updated_at"] = updated_at
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
        return self.model_copy(update={
            "status": MemberStatus.ACTIVE,
            "updated_at": datetime.now(timezone.utc),
        })

    def remove(self) -> "Member":
        """Transition ADDED|ACTIVE → REMOVED.

        Raises:
            InvalidTransitionError: if current status is REMOVED.
        """
        if self.status == MemberStatus.REMOVED:
            raise InvalidTransitionError(
                "Member is already in REMOVED status."
            )
        return self.model_copy(update={
            "status": MemberStatus.REMOVED,
            "updated_at": datetime.now(timezone.utc),
        })
