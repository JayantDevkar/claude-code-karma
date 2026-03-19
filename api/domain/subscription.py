"""Subscription domain model.

A Subscription represents a member's opt-in/opt-out state for a shared project.
State machine:
  OFFERED → ACCEPTED (accept(direction))
  ACCEPTED → PAUSED (pause)
  PAUSED → ACCEPTED (resume)
  OFFERED|ACCEPTED|PAUSED → DECLINED (decline)
  DECLINED → OFFERED (reopen)
  change_direction: only allowed when ACCEPTED

All state transitions return new immutable instances.
"""
from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field

from domain.team import InvalidTransitionError


class SyncDirection(str, Enum):
    SEND = "send"
    RECEIVE = "receive"
    BOTH = "both"


class SubscriptionStatus(str, Enum):
    OFFERED = "offered"
    ACCEPTED = "accepted"
    PAUSED = "paused"
    DECLINED = "declined"


class Subscription(BaseModel):
    """Immutable domain model representing a member's subscription to a shared project."""

    model_config = ConfigDict(frozen=True)

    member_tag: str
    team_name: str
    project_git_identity: str
    status: SubscriptionStatus = SubscriptionStatus.OFFERED
    direction: SyncDirection = SyncDirection.BOTH
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )

    # ------------------------------------------------------------------
    # State transitions
    # ------------------------------------------------------------------

    def accept(self, direction: SyncDirection) -> "Subscription":
        """Transition OFFERED → ACCEPTED with the given direction.

        Raises:
            InvalidTransitionError: if status is not OFFERED.
        """
        if self.status != SubscriptionStatus.OFFERED:
            raise InvalidTransitionError(
                f"Cannot accept subscription in status '{self.status.value}'. "
                "Must be in OFFERED status."
            )
        return self.model_copy(update={
            "status": SubscriptionStatus.ACCEPTED,
            "direction": direction,
            "updated_at": datetime.now(timezone.utc),
        })

    def pause(self) -> "Subscription":
        """Transition ACCEPTED → PAUSED.

        Raises:
            InvalidTransitionError: if status is not ACCEPTED.
        """
        if self.status != SubscriptionStatus.ACCEPTED:
            raise InvalidTransitionError(
                f"Cannot pause subscription in status '{self.status.value}'. "
                "Must be in ACCEPTED status."
            )
        return self.model_copy(update={
            "status": SubscriptionStatus.PAUSED,
            "updated_at": datetime.now(timezone.utc),
        })

    def resume(self) -> "Subscription":
        """Transition PAUSED → ACCEPTED.

        Raises:
            InvalidTransitionError: if status is not PAUSED.
        """
        if self.status != SubscriptionStatus.PAUSED:
            raise InvalidTransitionError(
                f"Cannot resume subscription in status '{self.status.value}'. "
                "Must be in PAUSED status."
            )
        return self.model_copy(update={
            "status": SubscriptionStatus.ACCEPTED,
            "updated_at": datetime.now(timezone.utc),
        })

    def decline(self) -> "Subscription":
        """Transition any status except DECLINED → DECLINED.

        Raises:
            InvalidTransitionError: if already DECLINED.
        """
        if self.status == SubscriptionStatus.DECLINED:
            raise InvalidTransitionError(
                "Subscription is already declined."
            )
        return self.model_copy(update={
            "status": SubscriptionStatus.DECLINED,
            "updated_at": datetime.now(timezone.utc),
        })

    def reopen(self) -> "Subscription":
        """Transition DECLINED → OFFERED, allowing the member to reconsider.

        Raises:
            InvalidTransitionError: if status is not DECLINED.
        """
        if self.status != SubscriptionStatus.DECLINED:
            raise InvalidTransitionError(
                f"Cannot reopen subscription in status '{self.status.value}'. "
                "Must be in DECLINED status."
            )
        return self.model_copy(update={
            "status": SubscriptionStatus.OFFERED,
            "updated_at": datetime.now(timezone.utc),
        })

    def change_direction(self, direction: SyncDirection) -> "Subscription":
        """Change sync direction. Only allowed when ACCEPTED.

        Raises:
            InvalidTransitionError: if status is not ACCEPTED.
        """
        if self.status != SubscriptionStatus.ACCEPTED:
            raise InvalidTransitionError(
                f"Cannot change direction of subscription in status '{self.status.value}'. "
                "Must be in ACCEPTED status."
            )
        return self.model_copy(update={
            "direction": direction,
            "updated_at": datetime.now(timezone.utc),
        })
