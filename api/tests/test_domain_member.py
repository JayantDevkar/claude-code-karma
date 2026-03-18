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
        member_tag="alice.macbook",
        team_name="team-abc",
        user_id="alice",
        machine_tag="macbook",
        device_id="DEVICE123",
    )
    defaults.update(kwargs)
    return Member(**defaults)


class TestMemberModel:
    def test_create_member_defaults(self):
        m = make_member()
        assert m.member_tag == "alice.macbook"
        assert m.team_name == "team-abc"
        assert m.user_id == "alice"
        assert m.machine_tag == "macbook"
        assert m.device_id == "DEVICE123"
        assert m.status == MemberStatus.ADDED
        assert isinstance(m.added_at, datetime)
        assert m.added_at.tzinfo is not None
        assert isinstance(m.updated_at, datetime)
        assert m.updated_at.tzinfo is not None

    def test_member_is_frozen(self):
        m = make_member()
        with pytest.raises(Exception):
            m.user_id = "changed"

    def test_is_active_false_when_added(self):
        m = make_member()
        assert m.is_active is False

    def test_is_active_true_when_active(self):
        m = make_member()
        activated = m.activate()
        assert activated.is_active is True

    def test_is_active_false_when_removed(self):
        m = make_member()
        removed = m.remove()
        assert removed.is_active is False

    def test_from_member_tag_classmethod(self):
        m = Member.from_member_tag(
            member_tag="bob.desktop",
            team_name="team-abc",
            device_id="DEVICE456",
        )
        assert m.user_id == "bob"
        assert m.machine_tag == "desktop"
        assert m.member_tag == "bob.desktop"

    def test_from_member_tag_no_dot_raises(self):
        with pytest.raises(ValueError, match="must contain a dot"):
            Member.from_member_tag(
                member_tag="nodot",
                team_name="team-abc",
                device_id="DEVICE000",
            )

    def test_from_member_tag_with_dot_in_machine_tag(self):
        # user_id cannot contain dots per spec — first dot splits user.machine
        m = Member.from_member_tag(
            member_tag="alice.work.laptop",
            team_name="team-abc",
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
