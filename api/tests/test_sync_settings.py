"""Tests for sync settings CRUD in db/sync_queries.py."""

import sqlite3

import pytest

from db.schema import ensure_schema
from db.sync_queries import (
    delete_setting,
    get_effective_auto_accept,
    get_effective_setting,
    get_effective_sync_direction,
    get_setting,
    list_settings,
    set_setting,
)


@pytest.fixture
def conn():
    """In-memory SQLite with schema applied."""
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA foreign_keys=ON")
    ensure_schema(c)
    return c


# ── get_setting ───────────────────────────────────────────────────────


class TestGetSetting:
    def test_returns_none_for_missing(self, conn):
        assert get_setting(conn, "team:acme", "sync_direction") is None

    def test_returns_value_after_set(self, conn):
        set_setting(conn, "team:acme", "sync_direction", "send_only")
        assert get_setting(conn, "team:acme", "sync_direction") == "send_only"


# ── set_setting ───────────────────────────────────────────────────────


class TestSetSetting:
    def test_insert_returns_none_old_value(self, conn):
        old = set_setting(conn, "team:acme", "sync_direction", "both")
        assert old is None

    def test_update_returns_old_value(self, conn):
        set_setting(conn, "team:acme", "sync_direction", "both")
        old = set_setting(conn, "team:acme", "sync_direction", "send_only")
        assert old == "both"
        # Confirm new value persisted
        assert get_setting(conn, "team:acme", "sync_direction") == "send_only"


# ── delete_setting ────────────────────────────────────────────────────


class TestDeleteSetting:
    def test_removes_setting(self, conn):
        set_setting(conn, "team:acme", "sync_direction", "none")
        delete_setting(conn, "team:acme", "sync_direction")
        assert get_setting(conn, "team:acme", "sync_direction") is None

    def test_delete_nonexistent_is_noop(self, conn):
        # Should not raise
        delete_setting(conn, "team:acme", "sync_direction")


# ── list_settings ─────────────────────────────────────────────────────


class TestListSettings:
    def test_returns_all_matching_scope_prefix(self, conn):
        set_setting(conn, "team:acme", "sync_direction", "both")
        set_setting(conn, "team:acme", "auto_accept_members", "false")
        set_setting(conn, "team:beta", "sync_direction", "none")
        set_setting(conn, "member:acme:DEV-1", "sync_direction", "send_only")

        # "team:acme" prefix matches team:acme settings only
        results = list_settings(conn, "team:acme")
        assert len(results) == 2
        keys = {r["setting_key"] for r in results}
        assert keys == {"sync_direction", "auto_accept_members"}

    def test_returns_empty_for_no_match(self, conn):
        assert list_settings(conn, "team:nonexistent") == []

    def test_broader_prefix_matches_nested_scopes(self, conn):
        set_setting(conn, "member:acme:DEV-1", "sync_direction", "send_only")
        set_setting(conn, "member:acme:DEV-2", "sync_direction", "receive_only")

        results = list_settings(conn, "member:acme")
        assert len(results) == 2


# ── get_effective_setting cascade ─────────────────────────────────────


class TestGetEffectiveSetting:
    def test_defaults_when_nothing_set(self, conn):
        value, source = get_effective_setting(conn, "sync_direction")
        assert value == "both"
        assert source == "default"

    def test_auto_accept_default(self, conn):
        value, source = get_effective_setting(conn, "auto_accept_members")
        assert value == "true"
        assert source == "default"

    def test_team_overrides_default(self, conn):
        set_setting(conn, "team:acme", "sync_direction", "send_only")
        value, source = get_effective_setting(
            conn, "sync_direction", team_name="acme"
        )
        assert value == "send_only"
        assert source == "team"

    def test_member_overrides_team(self, conn):
        set_setting(conn, "team:acme", "sync_direction", "both")
        set_setting(conn, "member:acme:DEV-1", "sync_direction", "none")
        value, source = get_effective_setting(
            conn, "sync_direction", team_name="acme", device_id="DEV-1"
        )
        assert value == "none"
        assert source == "member"

    def test_device_global_overrides_default(self, conn):
        set_setting(conn, "device:DEV-1", "sync_direction", "receive_only")
        value, source = get_effective_setting(
            conn, "sync_direction", device_id="DEV-1"
        )
        assert value == "receive_only"
        assert source == "device"

    def test_team_beats_device_global(self, conn):
        """team:{team} is higher priority than device:{device}."""
        set_setting(conn, "device:DEV-1", "sync_direction", "receive_only")
        set_setting(conn, "team:acme", "sync_direction", "send_only")
        value, source = get_effective_setting(
            conn, "sync_direction", team_name="acme", device_id="DEV-1"
        )
        assert value == "send_only"
        assert source == "team"

    def test_member_beats_device_global(self, conn):
        """member:{team}:{device} is the highest priority."""
        set_setting(conn, "device:DEV-1", "sync_direction", "receive_only")
        set_setting(conn, "team:acme", "sync_direction", "send_only")
        set_setting(conn, "member:acme:DEV-1", "sync_direction", "none")
        value, source = get_effective_setting(
            conn, "sync_direction", team_name="acme", device_id="DEV-1"
        )
        assert value == "none"
        assert source == "member"


# ── Convenience wrappers ──────────────────────────────────────────────


class TestGetEffectiveSyncDirection:
    def test_returns_both_by_default(self, conn):
        assert get_effective_sync_direction(conn) == "both"

    def test_respects_team_override(self, conn):
        set_setting(conn, "team:acme", "sync_direction", "none")
        assert get_effective_sync_direction(conn, team_name="acme") == "none"


class TestGetEffectiveAutoAccept:
    def test_returns_true_by_default(self, conn):
        assert get_effective_auto_accept(conn, "any-team") is True

    def test_returns_false_when_set(self, conn):
        set_setting(conn, "team:acme", "auto_accept_members", "false")
        assert get_effective_auto_accept(conn, "acme") is False

    def test_returns_true_when_explicitly_true(self, conn):
        set_setting(conn, "team:acme", "auto_accept_members", "true")
        assert get_effective_auto_accept(conn, "acme") is True
