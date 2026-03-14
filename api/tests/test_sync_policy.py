"""Tests for services/sync_policy.py — centralized sync policy evaluation."""

import sqlite3

import pytest

from db.schema import ensure_schema
from services.sync_policy import (
    _can_direction,
    should_auto_accept_device,
    should_receive_from,
    should_send_to,
)


@pytest.fixture
def conn():
    """In-memory SQLite with schema applied."""
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA foreign_keys=ON")
    ensure_schema(c)
    return c


# ── _can_direction truth table ────────────────────────────────────────


class TestCanDirection:
    def test_both_allows_send(self):
        assert _can_direction("both", "send") is True

    def test_both_allows_receive(self):
        assert _can_direction("both", "receive") is True

    def test_send_only_allows_send(self):
        assert _can_direction("send_only", "send") is True

    def test_send_only_blocks_receive(self):
        assert _can_direction("send_only", "receive") is False

    def test_receive_only_blocks_send(self):
        assert _can_direction("receive_only", "send") is False

    def test_receive_only_allows_receive(self):
        assert _can_direction("receive_only", "receive") is True

    def test_none_blocks_send(self):
        assert _can_direction("none", "send") is False

    def test_none_blocks_receive(self):
        assert _can_direction("none", "receive") is False


# ── should_auto_accept_device ─────────────────────────────────────────


class TestShouldAutoAcceptDevice:
    def test_returns_false_by_default(self, conn):
        """Default auto_accept_members is 'false' (deny by default)."""
        assert should_auto_accept_device(conn, "any-team") is False

    def test_returns_false_when_team_setting_is_false(self, conn):
        """Team-level override disables auto-accept."""
        from db.sync_queries import set_setting

        set_setting(conn, "team:acme", "auto_accept_members", "false")
        assert should_auto_accept_device(conn, "acme") is False


# ── should_send_to ────────────────────────────────────────────────────


class TestShouldSendTo:
    def test_returns_true_by_default(self, conn):
        """Default sync_direction is 'both', so send is allowed."""
        assert should_send_to(conn, "any-team") is True

    def test_returns_false_when_team_direction_is_receive_only(self, conn):
        from db.sync_queries import set_setting

        set_setting(conn, "team:acme", "sync_direction", "receive_only")
        assert should_send_to(conn, "acme") is False


# ── should_receive_from ───────────────────────────────────────────────


class TestShouldReceiveFrom:
    def test_returns_true_by_default(self, conn):
        """Default sync_direction is 'both', so receive is allowed."""
        assert should_receive_from(conn, "any-team") is True

    def test_returns_false_when_team_direction_is_send_only(self, conn):
        from db.sync_queries import set_setting

        set_setting(conn, "team:acme", "sync_direction", "send_only")
        assert should_receive_from(conn, "acme") is False


# ── Member-level override ────────────────────────────────────────────


class TestMemberLevelOverride:
    def test_member_send_only_overrides_team_both(self, conn):
        """Team allows both, but member restricted to send_only → receive blocked."""
        from db.sync_queries import set_setting

        set_setting(conn, "team:acme", "sync_direction", "both")
        set_setting(conn, "member:acme:DEV-ALICE", "sync_direction", "send_only")

        # Send still allowed (send_only permits send)
        assert should_send_to(conn, "acme", device_id="DEV-ALICE") is True
        # Receive blocked (send_only blocks receive)
        assert should_receive_from(conn, "acme", device_id="DEV-ALICE") is False
