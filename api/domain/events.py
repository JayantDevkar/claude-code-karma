"""SyncEvent domain model.

A SyncEvent is an immutable audit record of something that happened within
a sync team. Events are append-only and never mutated after creation.
"""
from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, Optional

from pydantic import BaseModel, ConfigDict, Field


class SyncEventType(str, Enum):
    team_created = "team_created"
    team_dissolved = "team_dissolved"
    member_added = "member_added"
    member_activated = "member_activated"
    member_removed = "member_removed"
    member_auto_left = "member_auto_left"
    member_left = "member_left"
    project_shared = "project_shared"
    project_removed = "project_removed"
    subscription_offered = "subscription_offered"
    subscription_accepted = "subscription_accepted"
    subscription_paused = "subscription_paused"
    subscription_resumed = "subscription_resumed"
    subscription_declined = "subscription_declined"
    direction_changed = "direction_changed"
    session_packaged = "session_packaged"
    session_received = "session_received"
    device_paired = "device_paired"
    device_unpaired = "device_unpaired"


class SyncEvent(BaseModel):
    """Immutable audit record of a sync system event."""

    model_config = ConfigDict(frozen=True)

    event_type: SyncEventType
    team_name: Optional[str] = None
    member_tag: Optional[str] = None
    project_git_identity: Optional[str] = None
    session_uuid: Optional[str] = None
    detail: Optional[Dict[str, Any]] = None
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
