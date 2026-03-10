"""Tests for reconcile_pending_handshakes — processing handshake folders
from already-paired devices signaling new team membership."""
from __future__ import annotations

import asyncio
import sqlite3
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from db.schema import ensure_schema
from db.sync_queries import (
    add_member,
    create_team,
    get_team,
    list_members,
    remove_member,
    upsert_member,
    was_member_removed,
    clear_member_removal,
)
from services.sync_reconciliation import reconcile_pending_handshakes


def _run(coro):
    """Run an async function synchronously."""
    return asyncio.get_event_loop().run_until_complete(coro)


@pytest.fixture
def conn():
    c = sqlite3.connect(":memory:", check_same_thread=False)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA foreign_keys=ON")
    ensure_schema(c)
    return c


@pytest.fixture
def config():
    cfg = MagicMock()
    cfg.user_id = "alice"
    cfg.machine_id = "alice-mac"
    cfg.syncthing.device_id = "ALICE-DEVICE-ID"
    return cfg


@pytest.fixture
def proxy():
    p = MagicMock()
    # Default: no pending folders, no configured devices
    p.get_pending_folders.return_value = {}
    p.get_devices.return_value = []
    p.dismiss_pending_folder_offer = MagicMock()
    return p


class TestReconcilePendingHandshakes:
    def test_no_pending_folders_returns_zero(self, proxy, config, conn):
        """When there are no pending folders, nothing to reconcile."""
        result = _run(reconcile_pending_handshakes(proxy, config, conn))
        assert result == 0

    def test_already_paired_device_new_team(self, proxy, config, conn):
        """Core scenario: device already paired (team1), offers handshake for team2."""
        # Setup: alice and bob are in team1
        create_team(conn, "team1", "syncthing")
        upsert_member(conn, "team1", "alice", device_id="ALICE-DEVICE-ID")
        upsert_member(conn, "team1", "bob", device_id="BOB-DEVICE-ID")

        # Bob offers a handshake for team2 (which alice created but bob isn't in yet)
        create_team(conn, "team2", "syncthing")
        upsert_member(conn, "team2", "alice", device_id="ALICE-DEVICE-ID")

        proxy.get_pending_folders.return_value = {
            "karma-join--bob--team2": {
                "offeredBy": {"BOB-DEVICE-ID": {"time": "2026-03-10T00:00:00Z"}}
            }
        }
        proxy.get_devices.return_value = [
            {"device_id": "ALICE-DEVICE-ID", "is_self": True},
            {"device_id": "BOB-DEVICE-ID", "is_self": False},
        ]

        result = _run(reconcile_pending_handshakes(proxy, config, conn))

        assert result == 1
        # Bob should now be in team2
        members = list_members(conn, "team2")
        member_names = {m["name"] for m in members}
        assert "bob" in member_names
        # Handshake should be dismissed
        proxy.dismiss_pending_folder_offer.assert_called_with(
            "karma-join--bob--team2", "BOB-DEVICE-ID"
        )

    def test_already_member_of_team_dismisses_only(self, proxy, config, conn):
        """If device is already in the team, just dismiss the handshake."""
        create_team(conn, "team1", "syncthing")
        upsert_member(conn, "team1", "alice", device_id="ALICE-DEVICE-ID")
        upsert_member(conn, "team1", "bob", device_id="BOB-DEVICE-ID")

        proxy.get_pending_folders.return_value = {
            "karma-join--bob--team1": {
                "offeredBy": {"BOB-DEVICE-ID": {"time": "2026-03-10T00:00:00Z"}}
            }
        }
        proxy.get_devices.return_value = [
            {"device_id": "ALICE-DEVICE-ID", "is_self": True},
            {"device_id": "BOB-DEVICE-ID", "is_self": False},
        ]

        result = _run(reconcile_pending_handshakes(proxy, config, conn))

        # No new memberships — bob is already in team1
        assert result == 0
        # But handshake should still be dismissed
        proxy.dismiss_pending_folder_offer.assert_called_once()

    def test_unpaired_device_skipped(self, proxy, config, conn):
        """Pending handshake from a device NOT in Syncthing's config is skipped."""
        create_team(conn, "team1", "syncthing")

        proxy.get_pending_folders.return_value = {
            "karma-join--charlie--team1": {
                "offeredBy": {"CHARLIE-DEVICE-ID": {"time": "2026-03-10T00:00:00Z"}}
            }
        }
        # Charlie is NOT in configured devices
        proxy.get_devices.return_value = [
            {"device_id": "ALICE-DEVICE-ID", "is_self": True},
        ]

        result = _run(reconcile_pending_handshakes(proxy, config, conn))
        assert result == 0
        proxy.dismiss_pending_folder_offer.assert_not_called()

    def test_self_device_skipped(self, proxy, config, conn):
        """Handshake from our own device is skipped."""
        create_team(conn, "team1", "syncthing")

        proxy.get_pending_folders.return_value = {
            "karma-join--alice--team1": {
                "offeredBy": {"ALICE-DEVICE-ID": {"time": "2026-03-10T00:00:00Z"}}
            }
        }
        proxy.get_devices.return_value = [
            {"device_id": "ALICE-DEVICE-ID", "is_self": True},
        ]

        result = _run(reconcile_pending_handshakes(proxy, config, conn))
        assert result == 0

    def test_team_auto_created_when_missing(self, proxy, config, conn):
        """If the team doesn't exist locally, it's created (like join code flow)."""
        # No teams exist locally. Bob (already paired from some other context)
        # offers a handshake for a team we've never seen.
        proxy.get_pending_folders.return_value = {
            "karma-join--bob--new-team": {
                "offeredBy": {"BOB-DEVICE-ID": {"time": "2026-03-10T00:00:00Z"}}
            }
        }
        proxy.get_devices.return_value = [
            {"device_id": "ALICE-DEVICE-ID", "is_self": True},
            {"device_id": "BOB-DEVICE-ID", "is_self": False},
        ]

        result = _run(reconcile_pending_handshakes(proxy, config, conn))

        assert result == 1
        # Team should be auto-created
        team = get_team(conn, "new-team")
        assert team is not None
        assert team["backend"] == "syncthing"
        # Self should be added as member
        members = list_members(conn, "new-team")
        member_names = {m["name"] for m in members}
        assert "alice" in member_names
        assert "bob" in member_names

    def test_non_handshake_folders_ignored(self, proxy, config, conn):
        """Only karma-join-- folders are processed; karma-out-- are ignored."""
        proxy.get_pending_folders.return_value = {
            "karma-out--bob--myproject": {
                "offeredBy": {"BOB-DEVICE-ID": {"time": "2026-03-10T00:00:00Z"}}
            }
        }
        proxy.get_devices.return_value = [
            {"device_id": "ALICE-DEVICE-ID", "is_self": True},
            {"device_id": "BOB-DEVICE-ID", "is_self": False},
        ]

        result = _run(reconcile_pending_handshakes(proxy, config, conn))
        assert result == 0

    def test_multiple_handshakes_from_different_teams(self, proxy, config, conn):
        """Process multiple handshakes from same device for different teams."""
        create_team(conn, "team1", "syncthing")
        upsert_member(conn, "team1", "alice", device_id="ALICE-DEVICE-ID")
        upsert_member(conn, "team1", "bob", device_id="BOB-DEVICE-ID")

        proxy.get_pending_folders.return_value = {
            "karma-join--bob--team-alpha": {
                "offeredBy": {"BOB-DEVICE-ID": {"time": "2026-03-10T00:00:00Z"}}
            },
            "karma-join--bob--team-beta": {
                "offeredBy": {"BOB-DEVICE-ID": {"time": "2026-03-10T00:01:00Z"}}
            },
        }
        proxy.get_devices.return_value = [
            {"device_id": "ALICE-DEVICE-ID", "is_self": True},
            {"device_id": "BOB-DEVICE-ID", "is_self": False},
        ]

        result = _run(reconcile_pending_handshakes(proxy, config, conn))

        assert result == 2
        assert get_team(conn, "team-alpha") is not None
        assert get_team(conn, "team-beta") is not None
        alpha_members = {m["name"] for m in list_members(conn, "team-alpha")}
        beta_members = {m["name"] for m in list_members(conn, "team-beta")}
        assert "bob" in alpha_members
        assert "bob" in beta_members

    def test_idempotent_on_second_run(self, proxy, config, conn):
        """Running twice with same pending data doesn't duplicate members."""
        proxy.get_pending_folders.return_value = {
            "karma-join--bob--team-x": {
                "offeredBy": {"BOB-DEVICE-ID": {"time": "2026-03-10T00:00:00Z"}}
            }
        }
        proxy.get_devices.return_value = [
            {"device_id": "ALICE-DEVICE-ID", "is_self": True},
            {"device_id": "BOB-DEVICE-ID", "is_self": False},
        ]

        # First run: creates team and adds bob
        result1 = _run(reconcile_pending_handshakes(proxy, config, conn))
        assert result1 == 1

        # Second run: bob is already a member, just dismisses
        result2 = _run(reconcile_pending_handshakes(proxy, config, conn))
        assert result2 == 0

        # Only one bob in team-x
        members = list_members(conn, "team-x")
        bob_entries = [m for m in members if m["name"] == "bob"]
        assert len(bob_entries) == 1

    def test_stale_handshake_after_removal_blocked(self, proxy, config, conn):
        """Removed member's stale handshake does NOT re-add them (Scenario 6)."""
        # Setup: alice and bob are in team2
        create_team(conn, "team1", "syncthing")
        create_team(conn, "team2", "syncthing")
        upsert_member(conn, "team1", "alice", device_id="ALICE-DEVICE-ID")
        upsert_member(conn, "team1", "bob", device_id="BOB-DEVICE-ID")
        upsert_member(conn, "team2", "alice", device_id="ALICE-DEVICE-ID")
        upsert_member(conn, "team2", "bob", device_id="BOB-DEVICE-ID")

        # Alice removes bob from team2
        remove_member(conn, "team2", "BOB-DEVICE-ID")
        assert was_member_removed(conn, "team2", "BOB-DEVICE-ID")

        # Bob's stale handshake re-appears
        proxy.get_pending_folders.return_value = {
            "karma-join--bob--team2": {
                "offeredBy": {"BOB-DEVICE-ID": {"time": "2026-03-10T00:00:00Z"}}
            }
        }
        proxy.get_devices.return_value = [
            {"device_id": "ALICE-DEVICE-ID", "is_self": True},
            {"device_id": "BOB-DEVICE-ID", "is_self": False},
        ]

        result = _run(reconcile_pending_handshakes(proxy, config, conn))

        # Should NOT re-add bob
        assert result == 0
        members = list_members(conn, "team2")
        assert not any(m["device_id"] == "BOB-DEVICE-ID" for m in members)
        # Handshake should still be dismissed (consume the stale signal)
        proxy.dismiss_pending_folder_offer.assert_called_once()

    def test_removed_then_rejoined_via_clear(self, proxy, config, conn):
        """After clear_member_removal, handshake reconciliation works again."""
        create_team(conn, "team1", "syncthing")
        upsert_member(conn, "team1", "alice", device_id="ALICE-DEVICE-ID")
        upsert_member(conn, "team1", "bob", device_id="BOB-DEVICE-ID")

        # Remove then clear (simulating re-join via join code)
        remove_member(conn, "team1", "BOB-DEVICE-ID")
        clear_member_removal(conn, "team1", "BOB-DEVICE-ID")

        proxy.get_pending_folders.return_value = {
            "karma-join--bob--team1": {
                "offeredBy": {"BOB-DEVICE-ID": {"time": "2026-03-10T00:00:00Z"}}
            }
        }
        proxy.get_devices.return_value = [
            {"device_id": "ALICE-DEVICE-ID", "is_self": True},
            {"device_id": "BOB-DEVICE-ID", "is_self": False},
        ]

        result = _run(reconcile_pending_handshakes(proxy, config, conn))

        # Should re-add bob (removal was explicitly cleared)
        assert result == 1
        members = list_members(conn, "team1")
        assert any(m["name"] == "bob" for m in members)
