"""Tests for the Team domain model."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
from datetime import datetime, timezone
from domain.team import Team, TeamStatus, AuthorizationError, InvalidTransitionError


def make_team(**kwargs):
    defaults = dict(
        team_id="team-abc",
        name="My Team",
        created_by="alice.macbook",
        leader_device="alice.macbook",
    )
    defaults.update(kwargs)
    return Team(**defaults)


class TestTeamModel:
    def test_create_team_defaults(self):
        team = make_team()
        assert team.team_id == "team-abc"
        assert team.name == "My Team"
        assert team.created_by == "alice.macbook"
        assert team.leader_device == "alice.macbook"
        assert team.status == TeamStatus.ACTIVE
        assert isinstance(team.created_at, datetime)
        assert team.created_at.tzinfo is not None

    def test_team_is_frozen(self):
        team = make_team()
        with pytest.raises(Exception):
            team.name = "changed"

    def test_is_leader_true(self):
        team = make_team(leader_device="alice.macbook")
        assert team.is_leader("alice.macbook") is True

    def test_is_leader_false(self):
        team = make_team(leader_device="alice.macbook")
        assert team.is_leader("bob.desktop") is False

    def test_dissolve_by_leader(self):
        team = make_team()
        dissolved = team.dissolve(by_device="alice.macbook")
        assert dissolved.status == TeamStatus.DISSOLVED
        assert dissolved.team_id == team.team_id

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
        updated = team.add_member("bob.desktop", by_device="alice.macbook")
        assert "bob.desktop" in updated.member_devices

    def test_add_member_by_non_leader_raises(self):
        team = make_team()
        with pytest.raises(AuthorizationError):
            team.add_member("bob.desktop", by_device="bob.desktop")

    def test_add_member_already_present_is_idempotent(self):
        team = make_team()
        updated = team.add_member("bob.desktop", by_device="alice.macbook")
        updated2 = updated.add_member("bob.desktop", by_device="alice.macbook")
        assert updated2.member_devices.count("bob.desktop") == 1

    def test_remove_member_by_leader(self):
        team = make_team()
        updated = team.add_member("bob.desktop", by_device="alice.macbook")
        removed = updated.remove_member("bob.desktop", by_device="alice.macbook")
        assert "bob.desktop" not in removed.member_devices

    def test_remove_member_by_non_leader_raises(self):
        team = make_team()
        updated = team.add_member("bob.desktop", by_device="alice.macbook")
        with pytest.raises(AuthorizationError):
            updated.remove_member("bob.desktop", by_device="carol.laptop")

    def test_member_devices_default_empty(self):
        team = make_team()
        assert team.member_devices == []

    def test_team_status_enum_values(self):
        assert TeamStatus.ACTIVE.value == "active"
        assert TeamStatus.DISSOLVED.value == "dissolved"


class TestAuthorizationError:
    def test_is_exception(self):
        err = AuthorizationError("not allowed")
        assert isinstance(err, Exception)
        assert str(err) == "not allowed"


class TestInvalidTransitionError:
    def test_is_exception(self):
        err = InvalidTransitionError("bad transition")
        assert isinstance(err, Exception)
        assert str(err) == "bad transition"
