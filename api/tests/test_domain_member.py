"""Tests for the Member domain model."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
from datetime import datetime, timezone
from domain.member import Member, MemberStatus
from domain.team import InvalidTransitionError


def make_member(**kwargs):
    defaults = dict(
        member_id="member-001",
        team_id="team-abc",
        user_id="alice",
        machine_tag="macbook",
        device_id="DEVICE123",
    )
    defaults.update(kwargs)
    return Member(**defaults)


class TestMemberModel:
    def test_create_member_defaults(self):
        m = make_member()
        assert m.member_id == "member-001"
        assert m.team_id == "team-abc"
        assert m.user_id == "alice"
        assert m.machine_tag == "macbook"
        assert m.device_id == "DEVICE123"
        assert m.status == MemberStatus.ADDED
        assert isinstance(m.joined_at, datetime)
        assert m.joined_at.tzinfo is not None

    def test_member_is_frozen(self):
        m = make_member()
        with pytest.raises(Exception):
            m.user_id = "changed"

    def test_member_tag_derived_property(self):
        m = make_member(user_id="alice", machine_tag="macbook")
        assert m.member_tag == "alice.macbook"

    def test_from_member_tag_classmethod(self):
        m = Member.from_member_tag(
            member_tag="bob.desktop",
            member_id="member-002",
            team_id="team-abc",
            device_id="DEVICE456",
        )
        assert m.user_id == "bob"
        assert m.machine_tag == "desktop"
        assert m.member_tag == "bob.desktop"

    def test_from_member_tag_with_dot_in_user_id(self):
        # user_id cannot contain dots per spec — first dot splits user.machine
        m = Member.from_member_tag(
            member_tag="alice.work.laptop",
            member_id="member-003",
            team_id="team-abc",
            device_id="DEVICE789",
        )
        assert m.user_id == "alice"
        assert m.machine_tag == "work.laptop"

    def test_activate_from_added(self):
        m = make_member()
        assert m.status == MemberStatus.ADDED
        activated = m.activate()
        assert activated.status == MemberStatus.ACTIVE

    def test_activate_from_active_raises(self):
        m = make_member()
        active = m.activate()
        with pytest.raises(InvalidTransitionError):
            active.activate()

    def test_activate_from_removed_raises(self):
        m = make_member()
        removed = m.remove()
        with pytest.raises(InvalidTransitionError):
            removed.activate()

    def test_remove_from_added(self):
        m = make_member()
        removed = m.remove()
        assert removed.status == MemberStatus.REMOVED

    def test_remove_from_active(self):
        m = make_member()
        active = m.activate()
        removed = active.remove()
        assert removed.status == MemberStatus.REMOVED

    def test_remove_from_removed_raises(self):
        m = make_member()
        removed = m.remove()
        with pytest.raises(InvalidTransitionError):
            removed.remove()

    def test_member_status_enum_values(self):
        assert MemberStatus.ADDED.value == "added"
        assert MemberStatus.ACTIVE.value == "active"
        assert MemberStatus.REMOVED.value == "removed"
