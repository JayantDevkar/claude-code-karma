"""Tests for the Team domain model."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
from datetime import datetime, timezone
from domain.team import Team, TeamStatus, AuthorizationError, InvalidTransitionError
from domain.member import Member


def make_team(**kwargs):
    defaults = dict(
        name="My Team",
        leader_device_id="alice.macbook",
        leader_member_tag="alice.macbook",
    )
    defaults.update(kwargs)
    return Team(**defaults)


def make_member(member_tag="bob.desktop", team_name="My Team", device_id="DEVICE456", **kwargs):
    user_id, machine_tag = member_tag.split(".", 1)
    return Member(
        member_tag=member_tag,
        team_name=team_name,
        device_id=device_id,
        user_id=user_id,
        machine_tag=machine_tag,
        **kwargs,
    )


class TestTeamModel:
    def test_create_team_defaults(self):
        team = make_team()
        assert team.name == "My Team"
        assert team.leader_device_id == "alice.macbook"
        assert team.leader_member_tag == "alice.macbook"
        assert team.status == TeamStatus.ACTIVE
        assert isinstance(team.created_at, datetime)
        assert team.created_at.tzinfo is not None

    def test_team_is_frozen(self):
        team = make_team()
        with pytest.raises(Exception):
            team.name = "changed"

    def test_is_leader_true(self):
        team = make_team(leader_device_id="alice.macbook")
        assert team.is_leader("alice.macbook") is True

    def test_is_leader_false(self):
        team = make_team(leader_device_id="alice.macbook")
        assert team.is_leader("bob.desktop") is False

    def test_dissolve_by_leader(self):
        team = make_team()
        dissolved = team.dissolve(by_device="alice.macbook")
        assert dissolved.status == TeamStatus.DISSOLVED
        assert dissolved.name == team.name

    def test_dissolve_by_non_leader_raises(self):
        team = make_team()
        with pytest.raises(AuthorizationError):
            team.dissolve(by_device="bob.desktop")

    def test_dissolve_already_dissolved_raises(self):
        team = make_team()
        dissolved = team.dissolve(by_device="alice.macbook")
        with pytest.raises(InvalidTransitionError):
            dissolved.dissolve(by_device="alice.macbook")

    def test_add_member_by_leader(self):
        team = make_team()
        member = make_member()
        returned = team.add_member(member, by_device="alice.macbook")
        assert returned.member_tag == "bob.desktop"

    def test_add_member_by_non_leader_raises(self):
        team = make_team()
        member = make_member()
        with pytest.raises(AuthorizationError):
            team.add_member(member, by_device="bob.desktop")

    def test_add_member_returns_member(self):
        team = make_team()
        member = make_member()
        result = team.add_member(member, by_device="alice.macbook")
        assert isinstance(result, Member)
        assert result.member_tag == member.member_tag

    def test_remove_member_by_leader(self):
        team = make_team()
        member = make_member()
        removed = team.remove_member(member, by_device="alice.macbook")
        from domain.member import MemberStatus
        assert removed.status == MemberStatus.REMOVED

    def test_remove_member_by_non_leader_raises(self):
        team = make_team()
        member = make_member()
        with pytest.raises(AuthorizationError):
            team.remove_member(member, by_device="carol.laptop")

    def test_remove_member_returns_removed_member(self):
        team = make_team()
        member = make_member()
        result = team.remove_member(member, by_device="alice.macbook")
        assert isinstance(result, Member)
        from domain.member import MemberStatus
        assert result.status == MemberStatus.REMOVED

    def test_team_status_enum_values(self):
        assert TeamStatus.ACTIVE.value == "active"
        assert TeamStatus.DISSOLVED.value == "dissolved"


    def test_add_member_on_dissolved_team_raises(self):
        team = make_team()
        dissolved = team.dissolve(by_device="alice.macbook")
        member = make_member()
        with pytest.raises(InvalidTransitionError, match="dissolved"):
            dissolved.add_member(member, by_device="alice.macbook")

    def test_remove_member_on_dissolved_team_raises(self):
        team = make_team()
        dissolved = team.dissolve(by_device="alice.macbook")
        member = make_member()
        with pytest.raises(InvalidTransitionError, match="dissolved"):
            dissolved.remove_member(member, by_device="alice.macbook")


class TestAuthorizationError:
    def test_is_exception(self):
        err = AuthorizationError("not allowed")
        assert isinstance(err, Exception)
        assert str(err) == "not allowed"


class TestInvalidTransitionError:
    def test_is_value_error(self):
        err = InvalidTransitionError("bad transition")
        assert isinstance(err, ValueError)
        assert str(err) == "bad transition"
