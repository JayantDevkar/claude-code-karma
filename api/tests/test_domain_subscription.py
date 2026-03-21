"""Tests for the Subscription domain model."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
from datetime import datetime, timezone
from domain.subscription import Subscription, SubscriptionStatus, SyncDirection
from domain.team import InvalidTransitionError


def make_sub(**kwargs):
    defaults = dict(
        member_tag="alice.macbook",
        team_name="team-abc",
        project_git_identity="owner/repo",
        direction=SyncDirection.BOTH,
    )
    defaults.update(kwargs)
    return Subscription(**defaults)


class TestSyncDirection:
    def test_enum_values(self):
        assert SyncDirection.SEND.value == "send"
        assert SyncDirection.RECEIVE.value == "receive"
        assert SyncDirection.BOTH.value == "both"


class TestSubscriptionStatus:
    def test_enum_values(self):
        assert SubscriptionStatus.OFFERED.value == "offered"
        assert SubscriptionStatus.ACCEPTED.value == "accepted"
        assert SubscriptionStatus.PAUSED.value == "paused"
        assert SubscriptionStatus.DECLINED.value == "declined"


class TestSubscriptionModel:
    def test_create_defaults(self):
        s = make_sub()
        assert s.member_tag == "alice.macbook"
        assert s.team_name == "team-abc"
        assert s.project_git_identity == "owner/repo"
        assert s.direction == SyncDirection.BOTH
        assert s.status == SubscriptionStatus.OFFERED
        assert isinstance(s.updated_at, datetime)
        assert s.updated_at.tzinfo is not None

    def test_subscription_is_frozen(self):
        s = make_sub()
        with pytest.raises(Exception):
            s.direction = SyncDirection.SEND

    # ------------------------------------------------------------------
    # accept: OFFERED → ACCEPTED
    # ------------------------------------------------------------------

    def test_accept_from_offered(self):
        s = make_sub()
        accepted = s.accept(SyncDirection.BOTH)
        assert accepted.status == SubscriptionStatus.ACCEPTED

    def test_accept_sets_direction(self):
        s = make_sub(direction=SyncDirection.BOTH)
        accepted = s.accept(SyncDirection.RECEIVE)
        assert accepted.direction == SyncDirection.RECEIVE

    def test_accept_from_paused_raises(self):
        s = make_sub()
        accepted = s.accept(SyncDirection.BOTH)
        paused = accepted.pause()
        with pytest.raises(InvalidTransitionError):
            paused.accept(SyncDirection.BOTH)

    def test_accept_from_accepted_raises(self):
        s = make_sub()
        accepted = s.accept(SyncDirection.BOTH)
        with pytest.raises(InvalidTransitionError):
            accepted.accept(SyncDirection.BOTH)

    def test_accept_from_declined_raises(self):
        s = make_sub()
        declined = s.decline()
        with pytest.raises(InvalidTransitionError):
            declined.accept(SyncDirection.BOTH)

    # ------------------------------------------------------------------
    # pause: ACCEPTED → PAUSED
    # ------------------------------------------------------------------

    def test_pause_from_accepted(self):
        s = make_sub()
        accepted = s.accept(SyncDirection.BOTH)
        paused = accepted.pause()
        assert paused.status == SubscriptionStatus.PAUSED

    def test_pause_from_offered_raises(self):
        s = make_sub()
        with pytest.raises(InvalidTransitionError):
            s.pause()

    def test_pause_from_paused_raises(self):
        s = make_sub()
        accepted = s.accept(SyncDirection.BOTH)
        paused = accepted.pause()
        with pytest.raises(InvalidTransitionError):
            paused.pause()

    # ------------------------------------------------------------------
    # resume: PAUSED → ACCEPTED
    # ------------------------------------------------------------------

    def test_resume_from_paused(self):
        s = make_sub()
        paused = s.accept(SyncDirection.BOTH).pause()
        resumed = paused.resume()
        assert resumed.status == SubscriptionStatus.ACCEPTED

    def test_resume_from_accepted_raises(self):
        s = make_sub()
        accepted = s.accept(SyncDirection.BOTH)
        with pytest.raises(InvalidTransitionError):
            accepted.resume()

    def test_resume_from_offered_raises(self):
        s = make_sub()
        with pytest.raises(InvalidTransitionError):
            s.resume()

    # ------------------------------------------------------------------
    # decline: any except DECLINED → DECLINED
    # ------------------------------------------------------------------

    def test_decline_from_offered(self):
        s = make_sub()
        declined = s.decline()
        assert declined.status == SubscriptionStatus.DECLINED

    def test_decline_from_accepted(self):
        s = make_sub()
        declined = s.accept(SyncDirection.BOTH).decline()
        assert declined.status == SubscriptionStatus.DECLINED

    def test_decline_from_paused(self):
        s = make_sub()
        declined = s.accept(SyncDirection.BOTH).pause().decline()
        assert declined.status == SubscriptionStatus.DECLINED

    def test_decline_from_declined_raises(self):
        s = make_sub()
        declined = s.decline()
        with pytest.raises(InvalidTransitionError):
            declined.decline()

    # ------------------------------------------------------------------
    # change_direction: only when ACCEPTED
    # ------------------------------------------------------------------

    def test_change_direction_when_accepted(self):
        s = make_sub(direction=SyncDirection.BOTH)
        accepted = s.accept(SyncDirection.BOTH)
        changed = accepted.change_direction(SyncDirection.SEND)
        assert changed.direction == SyncDirection.SEND
        assert changed.status == SubscriptionStatus.ACCEPTED

    def test_change_direction_when_offered_raises(self):
        s = make_sub()
        with pytest.raises(InvalidTransitionError):
            s.change_direction(SyncDirection.SEND)

    def test_change_direction_when_paused_raises(self):
        s = make_sub()
        paused = s.accept(SyncDirection.BOTH).pause()
        with pytest.raises(InvalidTransitionError):
            paused.change_direction(SyncDirection.SEND)

    def test_change_direction_when_declined_raises(self):
        s = make_sub()
        declined = s.decline()
        with pytest.raises(InvalidTransitionError):
            declined.change_direction(SyncDirection.SEND)
