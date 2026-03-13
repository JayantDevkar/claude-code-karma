"""Tests for sync v3 Phase 3: Cross-Team Safe Cleanup.

Tests pending-leave helpers, cleanup_syncthing_for_team (device subtraction),
cleanup_syncthing_for_member (declarative recompute), and the
compute_union_devices_excluding_team helper used in project-removal.
"""

import sqlite3
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from db.schema import ensure_schema


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def conn():
    """In-memory SQLite with current schema applied."""
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA foreign_keys=ON")
    ensure_schema(c)
    return c


@pytest.fixture(autouse=True)
def _bypass_run_sync():
    """Patch run_sync in sync_folders to bypass run_in_executor.

    run_sync uses loop.run_in_executor which puts MagicMock calls in a
    thread pool — not thread-safe and can deadlock. This fixture makes
    run_sync simply call the function directly.
    """
    async def _passthrough(func, *args, **kwargs):
        return func(*args, **kwargs)

    with patch("services.sync_folders.run_sync", side_effect=_passthrough):
        yield


def _make_config(device_id="SELF-DID", member_tag="self.laptop"):
    """Build a minimal config mock."""
    cfg = MagicMock()
    cfg.syncthing = MagicMock()
    cfg.syncthing.device_id = device_id
    cfg.member_tag = member_tag
    cfg.user_id = member_tag.split(".")[0]
    cfg.machine_id = "machine-abc"
    return cfg


def _setup_multi_team(conn):
    """Create the 4-team scenario used throughout Phase 3 tests.

    Teams / members / projects:
      T1: P1, P2  |  M1(m1.laptop/D1), M2(m2.desktop/D2)
      T2: P2, P3  |  M1(m1.laptop/D1), M3(m3.server/D3)
      T3: P1      |  M2(m2.desktop/D2), M3(m3.server/D3)
      T4: P2      |  M1(m1.laptop/D1), M4(m4.mini/D4)
    """
    from db.sync_queries import create_team, upsert_member, add_team_project

    for p in ["P1", "P2", "P3"]:
        conn.execute(
            "INSERT OR IGNORE INTO projects (encoded_name, git_identity) VALUES (?, ?)",
            (p, f"org/{p.lower()}"),
        )
    conn.commit()

    for t in ["T1", "T2", "T3", "T4"]:
        create_team(conn, t, "syncthing")

    devices = {"M1": "D1", "M2": "D2", "M3": "D3", "M4": "D4"}
    tags = {"M1": "m1.laptop", "M2": "m2.desktop", "M3": "m3.server", "M4": "m4.mini"}

    for m in ["M1", "M2"]:
        upsert_member(conn, "T1", tags[m], devices[m], member_tag=tags[m])
    for m in ["M1", "M3"]:
        upsert_member(conn, "T2", tags[m], devices[m], member_tag=tags[m])
    for m in ["M2", "M3"]:
        upsert_member(conn, "T3", tags[m], devices[m], member_tag=tags[m])
    for m in ["M1", "M4"]:
        upsert_member(conn, "T4", tags[m], devices[m], member_tag=tags[m])

    def suffix(p):
        return f"org-{p.lower()}"

    add_team_project(conn, "T1", "P1", git_identity="org/p1", folder_suffix=suffix("P1"))
    add_team_project(conn, "T1", "P2", git_identity="org/p2", folder_suffix=suffix("P2"))
    add_team_project(conn, "T2", "P2", git_identity="org/p2", folder_suffix=suffix("P2"))
    add_team_project(conn, "T2", "P3", git_identity="org/p3", folder_suffix=suffix("P3"))
    add_team_project(conn, "T3", "P1", git_identity="org/p1", folder_suffix=suffix("P1"))
    add_team_project(conn, "T4", "P2", git_identity="org/p2", folder_suffix=suffix("P2"))

    return devices, tags


# ---------------------------------------------------------------------------
# TestPendingLeaveHelpers
# ---------------------------------------------------------------------------

class TestPendingLeaveHelpers:
    """Tests for set_pending_leave and get_teams_with_pending_leave."""

    def test_set_pending_leave_marks_team(self, conn):
        from db.sync_queries import create_team, set_pending_leave

        create_team(conn, "T1", "syncthing")
        set_pending_leave(conn, "T1")

        row = conn.execute(
            "SELECT pending_leave FROM sync_teams WHERE name = 'T1'"
        ).fetchone()
        assert row is not None
        assert row["pending_leave"] is not None

    def test_get_teams_with_pending_leave_empty(self, conn):
        from db.sync_queries import create_team, get_teams_with_pending_leave

        create_team(conn, "T1", "syncthing")
        create_team(conn, "T2", "syncthing")

        result = get_teams_with_pending_leave(conn)
        assert result == []

    def test_get_teams_with_pending_leave_returns_marked(self, conn):
        from db.sync_queries import create_team, set_pending_leave, get_teams_with_pending_leave

        for t in ["T1", "T2", "T3"]:
            create_team(conn, t, "syncthing")

        set_pending_leave(conn, "T1")
        set_pending_leave(conn, "T3")

        result = get_teams_with_pending_leave(conn)
        names = {r["name"] for r in result}
        assert names == {"T1", "T3"}


# ---------------------------------------------------------------------------
# TestCleanupForTeamLeave
# ---------------------------------------------------------------------------

class TestCleanupForTeamLeave:
    """Tests for cleanup_syncthing_for_team (v3 device subtraction).

    The function calls proxy.get_configured_folders once per project
    in Phase A (inner loop), then once more for Phase B (handshake/metadata).
    T2 has 2 projects → 3 total calls to get_configured_folders.
    """

    @pytest.mark.asyncio
    async def test_device_subtraction_not_folder_deletion(self, conn):
        """Leaving T2: M1's P2 outbox is shared by T1+T2+T4 → NOT deleted."""
        from services.sync_folders import cleanup_syncthing_for_team
        from services.folder_id import build_outbox_id

        devices, tags = _setup_multi_team(conn)
        config = _make_config(device_id="SELF-DID", member_tag="self.laptop")

        m1_p2_outbox = build_outbox_id("m1.laptop", "org-p2")

        proxy = MagicMock()
        # T2 has P2 and P3 — Phase A loops over both; Phase B is one more.
        proxy.get_configured_folders.side_effect = [
            [{"id": m1_p2_outbox}],  # Phase A, project P2
            [],                       # Phase A, project P3
            [],                       # Phase B
        ]
        proxy.set_folder_devices.return_value = {"added": [], "removed": ["D3"]}
        proxy.remove_folder.return_value = None
        proxy.remove_device.return_value = None

        await cleanup_syncthing_for_team(proxy, config, conn, "T2")

        proxy.set_folder_devices.assert_called()
        removed_folder_args = [c.args[0] for c in proxy.remove_folder.call_args_list]
        assert m1_p2_outbox not in removed_folder_args, (
            f"remove_folder was called for {m1_p2_outbox} — expected device subtraction only"
        )

    @pytest.mark.asyncio
    async def test_folder_deleted_when_no_other_team_claims(self, conn):
        """Leaving T2: M3's P3 outbox has no other team claims → folder deleted."""
        from services.sync_folders import cleanup_syncthing_for_team
        from services.folder_id import build_outbox_id

        devices, tags = _setup_multi_team(conn)
        config = _make_config(device_id="SELF-DID", member_tag="self.laptop")

        m3_p3_outbox = build_outbox_id("m3.server", "org-p3")

        proxy = MagicMock()
        proxy.get_configured_folders.side_effect = [
            [],                        # Phase A, project P2
            [{"id": m3_p3_outbox}],    # Phase A, project P3
            [],                        # Phase B
        ]
        proxy.remove_folder.return_value = None
        proxy.set_folder_devices.return_value = {"added": [], "removed": []}
        proxy.remove_device.return_value = None

        with patch(
            "services.sync_folders.compute_union_devices_excluding_team",
            return_value=set(),
        ):
            await cleanup_syncthing_for_team(proxy, config, conn, "T2")

        removed_folder_args = [c.args[0] for c in proxy.remove_folder.call_args_list]
        assert m3_p3_outbox in removed_folder_args, (
            "remove_folder should be called for folder with no remaining team claims"
        )

    @pytest.mark.asyncio
    async def test_handshake_and_metadata_folders_always_removed(self, conn):
        """Handshake and metadata folders for the team are always removed."""
        from services.sync_folders import cleanup_syncthing_for_team
        from services.folder_id import build_handshake_id
        from services.sync_metadata import build_metadata_folder_id

        devices, tags = _setup_multi_team(conn)
        config = _make_config(device_id="SELF-DID", member_tag="self.laptop")

        hs_id = build_handshake_id("self.laptop", "T2")
        meta_id = build_metadata_folder_id("T2")

        proxy = MagicMock()
        proxy.get_configured_folders.side_effect = [
            [],                                   # Phase A, project P2
            [],                                   # Phase A, project P3
            [{"id": hs_id}, {"id": meta_id}],    # Phase B
        ]
        proxy.remove_folder.return_value = None
        proxy.remove_device.return_value = None
        proxy.set_folder_devices.return_value = {"added": [], "removed": []}

        await cleanup_syncthing_for_team(proxy, config, conn, "T2")

        removed = {c.args[0] for c in proxy.remove_folder.call_args_list}
        assert hs_id in removed, f"Handshake folder {hs_id} was not removed"
        assert meta_id in removed, f"Metadata folder {meta_id} was not removed"

    @pytest.mark.asyncio
    async def test_device_removed_only_if_not_in_other_teams(self, conn):
        """M4 only in T4 → D4 removed. M1 in T1+T2 → D1 NOT removed.

        Note: M3 is in T2 AND T3, so leaving T2 would NOT remove D3.
        M4 is the only device exclusively in one team (T4), with 1 project.
        """
        from services.sync_folders import cleanup_syncthing_for_team

        devices, tags = _setup_multi_team(conn)
        config = _make_config(device_id="SELF-DID", member_tag="self.laptop")

        proxy = MagicMock()
        # T4 has 1 project (P2): 1 Phase A + 1 Phase B = 2 calls
        proxy.get_configured_folders.side_effect = [[], []]
        proxy.remove_folder.return_value = None
        proxy.remove_device.return_value = None
        proxy.set_folder_devices.return_value = {"added": [], "removed": []}

        await cleanup_syncthing_for_team(proxy, config, conn, "T4")

        removed_devices = {c.args[0] for c in proxy.remove_device.call_args_list}
        assert devices["M4"] in removed_devices, "M4 is only in T4 → device must be removed"
        assert devices["M1"] not in removed_devices, "M1 is in T1+T2 → device must NOT be removed"

    @pytest.mark.asyncio
    async def test_sets_pending_leave(self, conn):
        """pending_leave column is set after calling cleanup_syncthing_for_team."""
        from services.sync_folders import cleanup_syncthing_for_team

        _setup_multi_team(conn)
        config = _make_config(device_id="SELF-DID", member_tag="self.laptop")

        proxy = MagicMock()
        # T1 has 2 projects (P1, P2): 2 Phase A + 1 Phase B = 3 calls
        proxy.get_configured_folders.side_effect = [[], [], []]
        proxy.remove_folder.return_value = None
        proxy.remove_device.return_value = None
        proxy.set_folder_devices.return_value = {"added": [], "removed": []}

        await cleanup_syncthing_for_team(proxy, config, conn, "T1")

        row = conn.execute(
            "SELECT pending_leave FROM sync_teams WHERE name = 'T1'"
        ).fetchone()
        assert row is not None
        assert row["pending_leave"] is not None


# ---------------------------------------------------------------------------
# TestCleanupForMemberRemoval
# ---------------------------------------------------------------------------

class TestCleanupForMemberRemoval:
    """Tests for cleanup_syncthing_for_member (v3 declarative recompute)."""

    @pytest.mark.asyncio
    async def test_recomputes_device_lists_for_team(self, conn):
        """compute_and_apply_device_lists is called with the team name."""
        from services.sync_folders import cleanup_syncthing_for_member

        devices, tags = _setup_multi_team(conn)
        config = _make_config(device_id="SELF-DID", member_tag="self.laptop")

        proxy = MagicMock()
        proxy.remove_folder.return_value = None
        proxy.remove_device.return_value = None
        proxy.set_folder_devices.return_value = {"added": [], "removed": []}

        with patch(
            "services.sync_folders.compute_and_apply_device_lists",
            new_callable=AsyncMock,
            return_value={"folders_updated": 2, "folders_deleted": 0, "errors": []},
        ) as mock_recompute:
            await cleanup_syncthing_for_member(
                proxy, config, conn, "T1", devices["M2"], tags["M2"]
            )

        mock_recompute.assert_called_once()
        assert mock_recompute.call_args.args[3] == "T1"

    @pytest.mark.asyncio
    async def test_inbox_deleted_when_no_other_team_claims(self, conn):
        """Member's inbox folder deleted when no other team claims it."""
        from services.sync_folders import cleanup_syncthing_for_member
        from services.folder_id import build_outbox_id

        devices, tags = _setup_multi_team(conn)
        config = _make_config(device_id="SELF-DID", member_tag="self.laptop")

        proxy = MagicMock()
        proxy.remove_folder.return_value = None
        proxy.remove_device.return_value = None
        proxy.set_folder_devices.return_value = {"added": [], "removed": []}

        m2_p1_inbox = build_outbox_id("m2.desktop", "org-p1")

        with patch(
            "services.sync_folders.compute_and_apply_device_lists",
            new_callable=AsyncMock,
            return_value={"folders_updated": 0, "folders_deleted": 0, "errors": []},
        ), patch(
            "services.sync_folders.compute_union_devices",
            return_value=set(),
        ):
            await cleanup_syncthing_for_member(
                proxy, config, conn, "T3", devices["M2"], tags["M2"]
            )

        removed = {c.args[0] for c in proxy.remove_folder.call_args_list}
        assert m2_p1_inbox in removed

    @pytest.mark.asyncio
    async def test_inbox_updated_when_other_team_claims(self, conn):
        """Member's inbox updated (not deleted) when another team claims it."""
        from services.sync_folders import cleanup_syncthing_for_member
        from services.folder_id import build_outbox_id

        devices, tags = _setup_multi_team(conn)
        config = _make_config(device_id="SELF-DID", member_tag="self.laptop")

        proxy = MagicMock()
        proxy.remove_folder.return_value = None
        proxy.remove_device.return_value = None
        proxy.set_folder_devices.return_value = {"added": [], "removed": ["D1"]}

        m2_p1_inbox = build_outbox_id("m2.desktop", "org-p1")

        with patch(
            "services.sync_folders.compute_and_apply_device_lists",
            new_callable=AsyncMock,
            return_value={"folders_updated": 1, "folders_deleted": 0, "errors": []},
        ), patch(
            "services.sync_folders.compute_union_devices",
            return_value={"D3", "SELF-DID"},
        ):
            await cleanup_syncthing_for_member(
                proxy, config, conn, "T1", devices["M2"], tags["M2"]
            )

        removed = {c.args[0] for c in proxy.remove_folder.call_args_list}
        assert m2_p1_inbox not in removed
        proxy.set_folder_devices.assert_called()

    @pytest.mark.asyncio
    async def test_device_removed_only_if_not_in_other_teams(self, conn):
        """M4 only in T4 → D4 removed. M1 in T1+T2 → D1 NOT removed."""
        from services.sync_folders import cleanup_syncthing_for_member

        devices, tags = _setup_multi_team(conn)
        config = _make_config(device_id="SELF-DID", member_tag="self.laptop")

        proxy = MagicMock()
        proxy.remove_folder.return_value = None
        proxy.remove_device.return_value = None
        proxy.set_folder_devices.return_value = {"added": [], "removed": []}

        # Case 1: M4 only in T4 → D4 removed
        with patch(
            "services.sync_folders.compute_and_apply_device_lists",
            new_callable=AsyncMock,
            return_value={"folders_updated": 0, "folders_deleted": 0, "errors": []},
        ), patch("services.sync_folders.compute_union_devices", return_value=set()):
            await cleanup_syncthing_for_member(
                proxy, config, conn, "T4", devices["M4"], tags["M4"]
            )

        removed_devices = {c.args[0] for c in proxy.remove_device.call_args_list}
        assert devices["M4"] in removed_devices, "M4 only in T4 → device must be removed"

        # Case 2: M1 in T1+T2+T4 → D1 NOT removed when leaving T4
        proxy.reset_mock()
        with patch(
            "services.sync_folders.compute_and_apply_device_lists",
            new_callable=AsyncMock,
            return_value={"folders_updated": 0, "folders_deleted": 0, "errors": []},
        ), patch("services.sync_folders.compute_union_devices", return_value=set()):
            await cleanup_syncthing_for_member(
                proxy, config, conn, "T4", devices["M1"], tags["M1"]
            )

        removed_devices2 = {c.args[0] for c in proxy.remove_device.call_args_list}
        assert devices["M1"] not in removed_devices2, (
            "M1 still in T1+T2 → device must NOT be removed"
        )


# ---------------------------------------------------------------------------
# TestProjectRemovalCleanup
# ---------------------------------------------------------------------------

class TestProjectRemovalCleanup:
    """Tests for compute_union_devices_excluding_team in project removal."""

    def test_compute_union_excluding_team_for_project(self, conn):
        """M1's P2 outbox excluding T2 still sees T1+T4 devices."""
        from db.sync_queries import compute_union_devices_excluding_team

        devices, tags = _setup_multi_team(conn)

        result = compute_union_devices_excluding_team(conn, "org-p2", "T2", "m1.laptop")
        assert result == {devices["M1"], devices["M2"], devices["M4"]}
        assert devices["M3"] not in result

    def test_compute_union_excluding_last_team_returns_empty(self, conn):
        """P3 only in T2 — excluding T2 returns empty."""
        from db.sync_queries import compute_union_devices_excluding_team

        devices, tags = _setup_multi_team(conn)

        result = compute_union_devices_excluding_team(conn, "org-p3", "T2", "m1.laptop")
        assert result == set()

    def test_compute_union_excluding_preserves_owner_scope(self, conn):
        """M4 only in T4. Excluding T4 from M4's P2 returns empty."""
        from db.sync_queries import compute_union_devices_excluding_team

        devices, tags = _setup_multi_team(conn)

        result = compute_union_devices_excluding_team(conn, "org-p2", "T4", "m4.mini")
        assert result == set()
