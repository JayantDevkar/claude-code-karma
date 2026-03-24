"""Tests for the SyncEvent domain model."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
from datetime import datetime, timezone
from domain.events import SyncEvent, SyncEventType


class TestSyncEventType:
    def test_all_18_event_types_exist(self):
        expected = [
            "team_created", "team_dissolved",
            "member_added", "member_activated", "member_removed", "member_auto_left",
            "project_shared", "project_removed",
            "subscription_offered", "subscription_accepted",
            "subscription_paused", "subscription_resumed", "subscription_declined",
            "direction_changed",
            "session_packaged", "session_received",
            "device_paired", "device_unpaired",
        ]
        actual_values = {e.value for e in SyncEventType}
        for name in expected:
            assert name in actual_values, f"Missing event type: {name}"

    def test_exactly_19_event_types(self):
        assert len(SyncEventType) == 19

    def test_event_type_is_str_enum(self):
        assert isinstance(SyncEventType.team_created, str)
        assert SyncEventType.team_created == "team_created"


class TestSyncEventCreation:
    def test_create_team_created_event(self):
        event = SyncEvent(
            event_type=SyncEventType.team_created,
            team_name="karma-team",
        )
        assert event.event_type == SyncEventType.team_created
        assert event.team_name == "karma-team"
        assert event.member_tag is None
        assert event.project_git_identity is None
        assert event.session_uuid is None
        assert event.detail is None
        assert event.created_at is not None

    def test_create_member_added_event_with_detail(self):
        event = SyncEvent(
            event_type=SyncEventType.member_added,
            team_name="karma-team",
            member_tag="ayush.laptop",
            detail={"device_id": "DEV-1", "added_by": "jayant.macbook"},
        )
        assert event.member_tag == "ayush.laptop"
        assert event.detail["device_id"] == "DEV-1"
        assert event.detail["added_by"] == "jayant.macbook"

    def test_create_session_packaged_event(self):
        event = SyncEvent(
            event_type=SyncEventType.session_packaged,
            team_name="t",
            member_tag="j.m",
            project_git_identity="owner/repo",
            session_uuid="abc-123",
            detail={"branches": ["main", "feature-x"]},
        )
        assert event.session_uuid == "abc-123"
        assert event.project_git_identity == "owner/repo"

    def test_create_subscription_accepted_event(self):
        event = SyncEvent(
            event_type=SyncEventType.subscription_accepted,
            team_name="t",
            member_tag="a.l",
            project_git_identity="o/r",
            detail={"direction": "both"},
        )
        assert event.detail["direction"] == "both"

    def test_create_direction_changed_event(self):
        event = SyncEvent(
            event_type=SyncEventType.direction_changed,
            team_name="t",
            member_tag="a.l",
            project_git_identity="o/r",
            detail={"old_direction": "both", "new_direction": "receive"},
        )
        assert event.detail["old_direction"] == "both"

    def test_create_device_paired_event(self):
        event = SyncEvent(
            event_type=SyncEventType.device_paired,
            team_name="t",
            detail={"device_id": "DEV-123"},
        )
        assert event.detail["device_id"] == "DEV-123"

    def test_create_member_auto_left_event(self):
        event = SyncEvent(
            event_type=SyncEventType.member_auto_left,
            team_name="t",
        )
        assert event.event_type == SyncEventType.member_auto_left


class TestSyncEventFrozen:
    def test_event_is_frozen(self):
        event = SyncEvent(
            event_type=SyncEventType.team_created,
            team_name="t",
        )
        with pytest.raises(Exception):
            event.team_name = "other"


class TestSyncEventOptionalFields:
    def test_all_optional_fields_default_none(self):
        event = SyncEvent(
            event_type=SyncEventType.team_dissolved,
            team_name="t",
        )
        assert event.member_tag is None
        assert event.project_git_identity is None
        assert event.session_uuid is None
        assert event.detail is None

    def test_team_name_is_optional(self):
        event = SyncEvent(
            event_type=SyncEventType.device_paired,
        )
        assert event.team_name is None

    def test_all_event_types_can_be_instantiated(self):
        for event_type in SyncEventType:
            event = SyncEvent(event_type=event_type, team_name="t")
            assert event.event_type == event_type
