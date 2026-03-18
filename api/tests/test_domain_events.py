"""Tests for the SyncEvent domain model."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
from datetime import datetime, timezone
from domain.events import SyncEvent, SyncEventType


def make_event(**kwargs):
    defaults = dict(
        event_id="evt-001",
        team_id="team-abc",
        event_type=SyncEventType.team_created,
        actor_device="alice.macbook",
    )
    defaults.update(kwargs)
    return SyncEvent(**defaults)


class TestSyncEventType:
    def test_all_17_event_types_exist(self):
        expected = [
            "team_created",
            "team_dissolved",
            "member_added",
            "member_activated",
            "member_removed",
            "member_auto_left",
            "project_shared",
            "project_removed",
            "subscription_offered",
            "subscription_accepted",
            "subscription_paused",
            "subscription_resumed",
            "subscription_declined",
            "direction_changed",
            "session_packaged",
            "session_received",
            "device_paired",
            "device_unpaired",
        ]
        actual_values = {e.value for e in SyncEventType}
        for name in expected:
            assert name in actual_values, f"Missing event type: {name}"

    def test_exactly_18_event_types(self):
        assert len(SyncEventType) == 18

    def test_event_type_is_str_enum(self):
        assert isinstance(SyncEventType.team_created, str)
        assert SyncEventType.team_created == "team_created"

    def test_event_type_values_match_names(self):
        for member in SyncEventType:
            assert member.value == member.name


class TestSyncEventModel:
    def test_create_event_defaults(self):
        evt = make_event()
        assert evt.event_id == "evt-001"
        assert evt.team_id == "team-abc"
        assert evt.event_type == SyncEventType.team_created
        assert evt.actor_device == "alice.macbook"
        assert isinstance(evt.occurred_at, datetime)
        assert evt.occurred_at.tzinfo is not None

    def test_event_is_frozen(self):
        evt = make_event()
        with pytest.raises(Exception):
            evt.actor_device = "changed"

    def test_payload_default_is_none(self):
        evt = make_event()
        assert evt.payload is None

    def test_payload_can_be_dict(self):
        evt = make_event(payload={"project_id": "proj-001", "action": "shared"})
        assert evt.payload["project_id"] == "proj-001"

    def test_subject_id_default_is_none(self):
        evt = make_event()
        assert evt.subject_id is None

    def test_subject_id_can_be_set(self):
        evt = make_event(subject_id="member-001")
        assert evt.subject_id == "member-001"

    def test_all_event_types_can_be_used(self):
        for event_type in SyncEventType:
            evt = make_event(event_type=event_type)
            assert evt.event_type == event_type

    def test_occurred_at_explicit(self):
        ts = datetime(2026, 3, 17, 12, 0, 0, tzinfo=timezone.utc)
        evt = make_event(occurred_at=ts)
        assert evt.occurred_at == ts

    def test_team_dissolved_event(self):
        evt = make_event(event_type=SyncEventType.team_dissolved)
        assert evt.event_type == SyncEventType.team_dissolved

    def test_session_packaged_event_with_payload(self):
        evt = make_event(
            event_type=SyncEventType.session_packaged,
            subject_id="sess-uuid-123",
            payload={"session_uuid": "sess-uuid-123", "size_bytes": 4096},
        )
        assert evt.event_type == SyncEventType.session_packaged
        assert evt.subject_id == "sess-uuid-123"
        assert evt.payload["size_bytes"] == 4096

    def test_device_paired_event(self):
        evt = make_event(
            event_type=SyncEventType.device_paired,
            subject_id="bob.desktop",
        )
        assert evt.event_type == SyncEventType.device_paired

    def test_direction_changed_event(self):
        evt = make_event(
            event_type=SyncEventType.direction_changed,
            payload={"from": "both", "to": "send"},
        )
        assert evt.event_type == SyncEventType.direction_changed

    def test_member_auto_left_event(self):
        evt = make_event(event_type=SyncEventType.member_auto_left)
        assert evt.event_type.value == "member_auto_left"

    def test_subscription_offered_event(self):
        evt = make_event(event_type=SyncEventType.subscription_offered)
        assert evt.event_type.value == "subscription_offered"
