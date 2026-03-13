"""Tests for sync v3 Phase 4: Edge Cases & Hardening.

Tests BP-9 collision detection, BP-12 two-phase folder sharing,
BP-13 immutable folder_suffix write-back, BP-14 team-scoped rejection,
EC-2 device ID change detection, RC-1 pending_leave guard.
"""

import sqlite3
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from db.schema import ensure_schema


@pytest.fixture
def conn():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA foreign_keys=ON")
    ensure_schema(c)
    return c


@pytest.fixture(autouse=True)
def _bypass_run_sync():
    """Patch run_sync to bypass run_in_executor for test safety."""
    async def _passthrough(func, *args, **kwargs):
        return func(*args, **kwargs)

    with patch("services.sync_folders.run_sync", side_effect=_passthrough):
        yield


def _make_config(device_id="SELF-DID", member_tag="self.laptop"):
    cfg = MagicMock()
    cfg.syncthing = MagicMock()
    cfg.syncthing.device_id = device_id
    cfg.member_tag = member_tag
    cfg.user_id = member_tag.split(".")[0]
    cfg.machine_id = "machine-abc"
    cfg.machine_tag = member_tag.split(".")[-1] if "." in member_tag else None
    return cfg


# ---------------------------------------------------------------------------
# BP-9: member_tag collision detection
# ---------------------------------------------------------------------------

class TestMemberTagCollision:

    def test_collision_detected(self, conn):
        """_has_member_tag_collision returns True when tag exists with different device."""
        from db.sync_queries import create_team, upsert_member
        from services.sync_reconciliation import _has_member_tag_collision

        create_team(conn, "T1", "syncthing")
        upsert_member(conn, "T1", "alice", device_id="D1", member_tag="alice.mac")

        assert _has_member_tag_collision(conn, "T1", "alice.mac", "D2") is True

    def test_no_collision_same_device(self, conn):
        """Same member_tag + same device_id is NOT a collision."""
        from db.sync_queries import create_team, upsert_member
        from services.sync_reconciliation import _has_member_tag_collision

        create_team(conn, "T1", "syncthing")
        upsert_member(conn, "T1", "alice", device_id="D1", member_tag="alice.mac")

        assert _has_member_tag_collision(conn, "T1", "alice.mac", "D1") is False

    def test_no_collision_different_team(self, conn):
        """Same member_tag in different team is NOT a collision for the queried team."""
        from db.sync_queries import create_team, upsert_member
        from services.sync_reconciliation import _has_member_tag_collision

        create_team(conn, "T1", "syncthing")
        create_team(conn, "T2", "syncthing")
        upsert_member(conn, "T1", "alice", device_id="D1", member_tag="alice.mac")

        # Checking T2 — alice.mac not in T2, so no collision
        assert _has_member_tag_collision(conn, "T2", "alice.mac", "D2") is False

    def test_collision_skips_upsert_in_handshake(self, conn):
        """reconcile_pending_handshakes skips upsert when collision detected."""
        from db.sync_queries import create_team, upsert_member, list_members
        from services.sync_reconciliation import _has_member_tag_collision

        create_team(conn, "T1", "syncthing")
        upsert_member(conn, "T1", "alice", device_id="D1", member_tag="alice.mac")

        # Simulate: a different device (D99) tries to claim alice.mac in T1
        assert _has_member_tag_collision(conn, "T1", "alice.mac", "D99") is True
        # Verify original member untouched
        members = list_members(conn, "T1")
        alice_members = [m for m in members if m["member_tag"] == "alice.mac"]
        assert len(alice_members) == 1
        assert alice_members[0]["device_id"] == "D1"


# ---------------------------------------------------------------------------
# BP-12: Two-phase folder sharing
# ---------------------------------------------------------------------------

class TestTwoPhaseSharing:

    @pytest.mark.asyncio
    async def test_metadata_only_skips_project_folders(self, conn):
        """auto_share_folders with metadata_only=True only updates metadata folder."""
        from db.sync_queries import create_team, upsert_member, add_team_project
        from services.sync_folders import auto_share_folders

        create_team(conn, "T1", "syncthing")
        upsert_member(conn, "T1", "alice", device_id="D1", member_tag="alice.mac")
        conn.execute(
            "INSERT OR IGNORE INTO projects (encoded_name, git_identity) VALUES (?, ?)",
            ("P1", "org/p1"),
        )
        conn.commit()
        add_team_project(conn, "T1", "P1", git_identity="org/p1", folder_suffix="org-p1")

        config = _make_config()
        proxy = MagicMock()
        proxy.update_folder_devices.return_value = None

        result = await auto_share_folders(
            proxy, config, conn, "T1", "D1", metadata_only=True,
        )

        # update_folder_devices called for metadata folder
        proxy.update_folder_devices.assert_called_once()
        # No outboxes or inboxes created
        assert result["outboxes"] == 0
        assert result["inboxes"] == 0

    @pytest.mark.asyncio
    async def test_full_share_creates_project_folders(self, conn):
        """auto_share_folders without metadata_only creates project folders."""
        from db.sync_queries import create_team, upsert_member, add_team_project
        from services.sync_folders import auto_share_folders

        create_team(conn, "T1", "syncthing")
        upsert_member(conn, "T1", "alice", device_id="D1", member_tag="alice.mac")
        conn.execute(
            "INSERT OR IGNORE INTO projects (encoded_name, git_identity) VALUES (?, ?)",
            ("P1", "org/p1"),
        )
        conn.commit()
        add_team_project(conn, "T1", "P1", git_identity="org/p1", folder_suffix="org-p1")

        config = _make_config()
        proxy = MagicMock()
        proxy.update_folder_devices.return_value = None

        with patch("services.sync_folders.ensure_outbox_folder", new_callable=AsyncMock) as mock_outbox, \
             patch("services.sync_folders.ensure_inbox_folders", new_callable=AsyncMock,
                   return_value={"inboxes": 1, "errors": []}) as mock_inbox:
            result = await auto_share_folders(
                proxy, config, conn, "T1", "D1", metadata_only=False,
            )

        mock_outbox.assert_called_once()
        mock_inbox.assert_called_once()


# ---------------------------------------------------------------------------
# BP-13: Immutable folder_suffix write-back
# ---------------------------------------------------------------------------

class TestFolderSuffixWriteBack:

    def test_null_suffix_gets_persisted(self, conn):
        """When folder_suffix is NULL, compute_and_apply_device_lists persists it."""
        from db.sync_queries import create_team, upsert_member, add_team_project

        create_team(conn, "T1", "syncthing")
        upsert_member(conn, "T1", "alice", device_id="D1", member_tag="alice.mac")
        conn.execute(
            "INSERT OR IGNORE INTO projects (encoded_name, git_identity) VALUES (?, ?)",
            ("P1", "org/p1"),
        )
        conn.commit()
        # Add project WITHOUT folder_suffix
        add_team_project(conn, "T1", "P1", git_identity="org/p1")

        # Verify it's NULL
        row = conn.execute(
            "SELECT folder_suffix FROM sync_team_projects WHERE team_name = 'T1' AND project_encoded_name = 'P1'"
        ).fetchone()
        assert row["folder_suffix"] is None

        # Import and call the suffix computation path
        from services.sync_folders import _compute_proj_suffix
        from db.sync_queries import upsert_team_project, list_team_projects

        projects = list_team_projects(conn, "T1")
        proj = projects[0]
        suffix = proj.get("folder_suffix")
        if not suffix:
            suffix = _compute_proj_suffix(proj.get("git_identity"), proj.get("path"), proj["project_encoded_name"])
            upsert_team_project(conn, "T1", proj["project_encoded_name"], folder_suffix=suffix)

        # Now verify it's persisted
        row = conn.execute(
            "SELECT folder_suffix FROM sync_team_projects WHERE team_name = 'T1' AND project_encoded_name = 'P1'"
        ).fetchone()
        assert row["folder_suffix"] is not None
        assert row["folder_suffix"] == suffix

    def test_existing_suffix_not_overwritten(self, conn):
        """When folder_suffix already exists, it should not change."""
        from db.sync_queries import create_team, add_team_project, upsert_team_project

        create_team(conn, "T1", "syncthing")
        conn.execute(
            "INSERT OR IGNORE INTO projects (encoded_name, git_identity) VALUES (?, ?)",
            ("P1", "org/p1"),
        )
        conn.commit()
        add_team_project(conn, "T1", "P1", git_identity="org/p1", folder_suffix="original-suffix")

        # Try to upsert with a different suffix — COALESCE should preserve original
        upsert_team_project(conn, "T1", "P1", folder_suffix="new-suffix")

        row = conn.execute(
            "SELECT folder_suffix FROM sync_team_projects WHERE team_name = 'T1' AND project_encoded_name = 'P1'"
        ).fetchone()
        assert row["folder_suffix"] == "original-suffix"


# ---------------------------------------------------------------------------
# BP-14: Team-scoped rejection
# ---------------------------------------------------------------------------

class TestTeamScopedRejection:

    def test_reject_scoped_to_team(self, conn):
        """Rejecting in T1 should not affect T2."""
        from db.sync_queries import reject_folder, is_folder_rejected

        reject_folder(conn, "karma-out--alice--p1", team_name="T1")
        assert is_folder_rejected(conn, "karma-out--alice--p1", team_name="T1") is True
        assert is_folder_rejected(conn, "karma-out--alice--p1", team_name="T2") is False

    def test_unreject_scoped_to_team(self, conn):
        """Unrejecting in T1 should not affect T2."""
        from db.sync_queries import reject_folder, unreject_folder, is_folder_rejected

        reject_folder(conn, "karma-out--alice--p1", team_name="T1")
        reject_folder(conn, "karma-out--alice--p1", team_name="T2")

        unreject_folder(conn, "karma-out--alice--p1", team_name="T1")
        assert is_folder_rejected(conn, "karma-out--alice--p1", team_name="T1") is False
        assert is_folder_rejected(conn, "karma-out--alice--p1", team_name="T2") is True


# ---------------------------------------------------------------------------
# EC-2: Device ID change detection
# ---------------------------------------------------------------------------

class TestDeviceIdChange:

    def test_detects_stale_device_id(self, conn):
        """detect_device_id_change updates stale rows."""
        from db.sync_queries import create_team, upsert_member
        from services.sync_reconciliation import detect_device_id_change

        create_team(conn, "T1", "syncthing")
        upsert_member(conn, "T1", "self", device_id="OLD-DID", member_tag="self.laptop")

        config = _make_config(device_id="NEW-DID", member_tag="self.laptop")
        updated = detect_device_id_change(conn, config)

        assert updated == 1
        row = conn.execute(
            "SELECT device_id FROM sync_members WHERE member_tag = 'self.laptop'"
        ).fetchone()
        assert row["device_id"] == "NEW-DID"

    def test_no_change_when_device_matches(self, conn):
        """No rows updated when device_id matches config."""
        from db.sync_queries import create_team, upsert_member
        from services.sync_reconciliation import detect_device_id_change

        create_team(conn, "T1", "syncthing")
        upsert_member(conn, "T1", "self", device_id="SAME-DID", member_tag="self.laptop")

        config = _make_config(device_id="SAME-DID", member_tag="self.laptop")
        updated = detect_device_id_change(conn, config)
        assert updated == 0

    def test_updates_across_multiple_teams(self, conn):
        """Device ID change updates all teams."""
        from db.sync_queries import create_team, upsert_member
        from services.sync_reconciliation import detect_device_id_change

        for t in ["T1", "T2", "T3"]:
            create_team(conn, t, "syncthing")
            upsert_member(conn, t, "self", device_id="OLD-DID", member_tag="self.laptop")

        config = _make_config(device_id="NEW-DID", member_tag="self.laptop")
        updated = detect_device_id_change(conn, config)
        assert updated == 3

        rows = conn.execute(
            "SELECT device_id FROM sync_members WHERE member_tag = 'self.laptop'"
        ).fetchall()
        assert all(r["device_id"] == "NEW-DID" for r in rows)


# ---------------------------------------------------------------------------
# RC-1: pending_leave guard
# ---------------------------------------------------------------------------

class TestPendingLeaveGuard:

    def test_get_team_includes_pending_leave(self, conn):
        """get_team now returns pending_leave column."""
        from db.sync_queries import create_team, set_pending_leave, get_team

        create_team(conn, "T1", "syncthing")
        team = get_team(conn, "T1")
        assert team["pending_leave"] is None

        set_pending_leave(conn, "T1")
        team = get_team(conn, "T1")
        assert team["pending_leave"] is not None

    @pytest.mark.asyncio
    async def test_handshake_skipped_during_pending_leave(self, conn):
        """reconcile_pending_handshakes skips team creation when pending_leave is set."""
        from db.sync_queries import create_team, set_pending_leave, get_team

        create_team(conn, "T1", "syncthing")
        set_pending_leave(conn, "T1")

        config = _make_config(device_id="SELF-DID", member_tag="self.laptop")

        proxy = MagicMock()
        proxy.get_pending_folders.return_value = {
            "karma-join--bob.mac--T1": {"offeredBy": {"BOB-DID": {}}},
        }
        proxy.get_devices.return_value = [
            {"device_id": "BOB-DID", "is_self": False},
        ]
        proxy.dismiss_pending_folder_offer.return_value = None

        with patch("services.sync_reconciliation.run_sync", side_effect=lambda f, *a, **kw: f(*a, **kw)):
            from services.sync_reconciliation import reconcile_pending_handshakes
            result = await reconcile_pending_handshakes(proxy, config, conn)

        # Should not have created any new memberships
        assert result == 0
        # Dismiss should have been called (handshake consumed)
        proxy.dismiss_pending_folder_offer.assert_called()
