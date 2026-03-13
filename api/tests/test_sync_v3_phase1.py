"""Tests for sync v3 Phase 1: Declarative Device Lists.

Tests the foundation layer: union device queries, set_folder_devices,
compute_and_apply_device_lists, and v18 schema migration.
"""

import sqlite3
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from db.schema import ensure_schema


@pytest.fixture
def conn():
    """In-memory SQLite with v18 schema applied."""
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA foreign_keys=ON")
    ensure_schema(c)
    return c


def _setup_multi_team(conn):
    """Set up the 4-team test scenario from the architecture doc.

    Teams and members:
      T1: M1(jayant.macbook), M2(jayant.mac-mini), M3(alice.laptop)
      T2: M1(jayant.macbook), M2(jayant.mac-mini)
      T3: M2(jayant.mac-mini), M3(alice.laptop), M4(bruce.mac-mini)
      T4: M1(jayant.macbook), M4(bruce.mac-mini)

    Projects:
      T1: P1, P2
      T2: P2, P3
      T3: P1, P3
      T4: P2
    """
    from db.sync_queries import create_team, upsert_member, add_team_project

    # Projects (FK requirement)
    for p in ["P1", "P2", "P3"]:
        conn.execute(
            "INSERT OR IGNORE INTO projects (encoded_name, git_identity) VALUES (?, ?)",
            (p, f"org/{p.lower()}"),
        )
    conn.commit()

    # Teams
    for t in ["T1", "T2", "T3", "T4"]:
        create_team(conn, t, "syncthing")

    # Members with member_tags
    devices = {
        "M1": "DEVICE-M1-AAAA",
        "M2": "DEVICE-M2-BBBB",
        "M3": "DEVICE-M3-CCCC",
        "M4": "DEVICE-M4-DDDD",
    }
    tags = {
        "M1": "jayant.macbook",
        "M2": "jayant.mac-mini",
        "M3": "alice.laptop",
        "M4": "bruce.mac-mini",
    }

    # Use the full member_tag as the name to avoid same-username collisions across
    # devices. upsert_member deletes rows where (team, name) maps to a different
    # device_id, so two devices owned by "jayant" would clobber each other if we
    # passed only the user portion of the tag.
    # T1: M1, M2, M3
    for m in ["M1", "M2", "M3"]:
        upsert_member(conn, "T1", tags[m], devices[m], member_tag=tags[m])
    # T2: M1, M2
    for m in ["M1", "M2"]:
        upsert_member(conn, "T2", tags[m], devices[m], member_tag=tags[m])
    # T3: M2, M3, M4
    for m in ["M2", "M3", "M4"]:
        upsert_member(conn, "T3", tags[m], devices[m], member_tag=tags[m])
    # T4: M1, M4
    for m in ["M1", "M4"]:
        upsert_member(conn, "T4", tags[m], devices[m], member_tag=tags[m])

    # Compute suffix from git_identity
    def suffix(p):
        return f"org-{p.lower()}"

    # Projects with folder_suffix
    add_team_project(conn, "T1", "P1", git_identity="org/p1", folder_suffix=suffix("P1"))
    add_team_project(conn, "T1", "P2", git_identity="org/p2", folder_suffix=suffix("P2"))
    add_team_project(conn, "T2", "P2", git_identity="org/p2", folder_suffix=suffix("P2"))
    add_team_project(conn, "T2", "P3", git_identity="org/p3", folder_suffix=suffix("P3"))
    add_team_project(conn, "T3", "P1", git_identity="org/p1", folder_suffix=suffix("P1"))
    add_team_project(conn, "T3", "P3", git_identity="org/p3", folder_suffix=suffix("P3"))
    add_team_project(conn, "T4", "P2", git_identity="org/p2", folder_suffix=suffix("P2"))

    return devices, tags


class TestComputeUnionDevices:
    """Tests for compute_union_devices (ADR-3 union query)."""

    def test_single_team_returns_all_members(self, conn):
        """Single team: union should return all team member devices."""
        from db.sync_queries import (
            create_team, upsert_member, add_team_project, compute_union_devices,
        )
        conn.execute("INSERT INTO projects (encoded_name) VALUES ('P1')")
        conn.commit()
        create_team(conn, "T1", "syncthing")
        upsert_member(conn, "T1", "alice", "DEV-A", member_tag="alice.mac")
        upsert_member(conn, "T1", "bob", "DEV-B", member_tag="bob.mac")
        add_team_project(conn, "T1", "P1", folder_suffix="proj-suffix")

        result = compute_union_devices(conn, "proj-suffix", "alice.mac")
        assert result == {"DEV-A", "DEV-B"}

    def test_multi_team_overlap_m1_p2(self, conn):
        """M1's outbox for P2 should include T1, T2, T4 devices (M1 is member of all three)."""
        from db.sync_queries import compute_union_devices

        devices, tags = _setup_multi_team(conn)

        result = compute_union_devices(conn, "org-p2", "jayant.macbook")
        # M1 is in T1(P2), T2(P2), T4(P2) — union of all members across those teams
        # T1 members: M1, M2, M3
        # T2 members: M1, M2
        # T4 members: M1, M4
        # Union: M1, M2, M3, M4
        assert result == {devices["M1"], devices["M2"], devices["M3"], devices["M4"]}

    def test_owner_scoping_prevents_leak(self, conn):
        """M4's outbox for P2 should NOT include T1/T2 devices (M4 not in T1 or T2)."""
        from db.sync_queries import compute_union_devices

        devices, tags = _setup_multi_team(conn)

        result = compute_union_devices(conn, "org-p2", "bruce.mac-mini")
        # M4 is only in T4(P2) — T1 and T2 also have P2 but M4 is NOT a member
        # T4 members: M1, M4
        assert result == {devices["M1"], devices["M4"]}

    def test_m2_p1_includes_t1_and_t3(self, conn):
        """M2's outbox for P1: M2 is in T1(P1) and T3(P1)."""
        from db.sync_queries import compute_union_devices

        devices, tags = _setup_multi_team(conn)

        result = compute_union_devices(conn, "org-p1", "jayant.mac-mini")
        # T1(P1) members: M1, M2, M3
        # T3(P1) members: M2, M3, M4
        # Union: M1, M2, M3, M4
        assert result == {devices["M1"], devices["M2"], devices["M3"], devices["M4"]}

    def test_empty_result_for_nonexistent_suffix(self, conn):
        """No team has this suffix — should return empty set."""
        from db.sync_queries import compute_union_devices

        _setup_multi_team(conn)
        result = compute_union_devices(conn, "nonexistent-suffix", "jayant.macbook")
        assert result == set()

    def test_m3_p2_scoped_to_t1_only(self, conn):
        """M3's outbox for P2: M3 is only in T1 which has P2 (not T2 or T4)."""
        from db.sync_queries import compute_union_devices

        devices, tags = _setup_multi_team(conn)

        result = compute_union_devices(conn, "org-p2", "alice.laptop")
        # M3 is in T1 which has P2. T2(P2) and T4(P2) don't have M3.
        # T1 members: M1, M2, M3
        assert result == {devices["M1"], devices["M2"], devices["M3"]}
        # NOT M4 — M3 is not in T4

    def test_excludes_empty_device_ids(self, conn):
        """Members with empty device_id should be excluded."""
        from db.sync_queries import (
            create_team, upsert_member, add_team_project, compute_union_devices,
        )
        conn.execute("INSERT INTO projects (encoded_name) VALUES ('P1')")
        conn.commit()
        create_team(conn, "T1", "syncthing")
        upsert_member(conn, "T1", "alice", "DEV-A", member_tag="alice.mac")
        upsert_member(conn, "T1", "ghost", "", member_tag="ghost.mac")
        add_team_project(conn, "T1", "P1", folder_suffix="proj-suffix")

        result = compute_union_devices(conn, "proj-suffix", "alice.mac")
        assert result == {"DEV-A"}

    def test_non_member_owner_returns_empty(self, conn):
        """Owner not in any team with this suffix — should return empty set."""
        from db.sync_queries import compute_union_devices

        _setup_multi_team(conn)
        # "outsider.device" is not a member of any team
        result = compute_union_devices(conn, "org-p1", "outsider.device")
        assert result == set()


class TestComputeUnionDevicesExcludingTeam:
    """Tests for compute_union_devices_excluding_team (cleanup variant)."""

    def test_exclude_team_subtracts_devices(self, conn):
        """Excluding T1 from M1's P2 should remove M3 (only in T1)."""
        from db.sync_queries import compute_union_devices_excluding_team

        devices, _ = _setup_multi_team(conn)

        result = compute_union_devices_excluding_team(conn, "org-p2", "T1", "jayant.macbook")
        # Without T1, remaining teams for M1+P2: T2(M1,M2), T4(M1,M4)
        # Union: M1, M2, M4 (M3 was only contributed by T1)
        assert result == {devices["M1"], devices["M2"], devices["M4"]}

    def test_exclude_last_team_returns_empty(self, conn):
        """Excluding the only team should return empty set."""
        from db.sync_queries import compute_union_devices_excluding_team

        devices, _ = _setup_multi_team(conn)

        # M4's P2 is only in T4
        result = compute_union_devices_excluding_team(conn, "org-p2", "T4", "bruce.mac-mini")
        assert result == set()

    def test_leave_t2_m1_p3_becomes_empty(self, conn):
        """M1 leaves T2 — P3 was only shared by T2 for M1, should be empty."""
        from db.sync_queries import compute_union_devices_excluding_team

        devices, _ = _setup_multi_team(conn)

        result = compute_union_devices_excluding_team(conn, "org-p3", "T2", "jayant.macbook")
        # M1 is not in T3 (which also has P3), so excluding T2 leaves nothing
        assert result == set()

    def test_exclude_nonexistent_team_same_as_no_exclusion(self, conn):
        """Excluding a team that has no claim on the suffix is a no-op."""
        from db.sync_queries import compute_union_devices, compute_union_devices_excluding_team

        devices, _ = _setup_multi_team(conn)

        base = compute_union_devices(conn, "org-p1", "jayant.mac-mini")
        excluding_ghost = compute_union_devices_excluding_team(conn, "org-p1", "GHOST_TEAM", "jayant.mac-mini")
        assert base == excluding_ghost


class TestSchemaV18Migration:
    """Tests for v18 schema changes."""

    def test_folder_suffix_column_exists(self, conn):
        """sync_team_projects should have folder_suffix column after migration."""
        cols = {r[1] for r in conn.execute("PRAGMA table_info(sync_team_projects)").fetchall()}
        assert "folder_suffix" in cols

    def test_pending_leave_column_exists(self, conn):
        """sync_teams should have pending_leave column after migration."""
        cols = {r[1] for r in conn.execute("PRAGMA table_info(sync_teams)").fetchall()}
        assert "pending_leave" in cols

    def test_rejected_folders_has_composite_pk(self, conn):
        """sync_rejected_folders should have (folder_id, team_name) PK."""
        # Same folder can be rejected in different teams
        conn.execute(
            "INSERT INTO sync_rejected_folders (folder_id, team_name) VALUES (?, ?)",
            ("karma-out--alice--p1", "T1"),
        )
        conn.execute(
            "INSERT INTO sync_rejected_folders (folder_id, team_name) VALUES (?, ?)",
            ("karma-out--alice--p1", "T2"),
        )
        conn.commit()
        rows = conn.execute(
            "SELECT * FROM sync_rejected_folders WHERE folder_id = 'karma-out--alice--p1'"
        ).fetchall()
        assert len(rows) == 2

    def test_folder_suffix_index_exists(self, conn):
        """idx_sync_team_projects_suffix should exist."""
        indexes = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='index' AND tbl_name='sync_team_projects'"
        ).fetchall()
        index_names = {r[0] for r in indexes}
        assert "idx_sync_team_projects_suffix" in index_names

    def test_schema_version_is_18(self, conn):
        """Schema version should be 18."""
        row = conn.execute("SELECT MAX(version) FROM schema_version").fetchone()
        assert row[0] == 18

    def test_member_tag_column_exists(self, conn):
        """sync_members should have member_tag column."""
        cols = {r[1] for r in conn.execute("PRAGMA table_info(sync_members)").fetchall()}
        assert "member_tag" in cols

    def test_machine_tag_column_exists(self, conn):
        """sync_members should have machine_tag column."""
        cols = {r[1] for r in conn.execute("PRAGMA table_info(sync_members)").fetchall()}
        assert "machine_tag" in cols


class TestFolderSuffixInCRUD:
    """Tests for folder_suffix in add_team_project and upsert_team_project."""

    def test_add_team_project_stores_suffix(self, conn):
        from db.sync_queries import create_team, add_team_project, list_team_projects

        create_team(conn, "T1", "syncthing")
        conn.execute("INSERT INTO projects (encoded_name) VALUES ('P1')")
        conn.commit()
        add_team_project(conn, "T1", "P1", git_identity="org/p1", folder_suffix="org-p1")

        projects = list_team_projects(conn, "T1")
        assert len(projects) == 1
        assert projects[0]["folder_suffix"] == "org-p1"

    def test_upsert_team_project_stores_suffix(self, conn):
        from db.sync_queries import create_team, upsert_team_project, list_team_projects

        create_team(conn, "T1", "syncthing")
        upsert_team_project(conn, "T1", "P1", git_identity="org/p1", folder_suffix="org-p1")

        projects = list_team_projects(conn, "T1")
        assert len(projects) == 1
        assert projects[0]["folder_suffix"] == "org-p1"

    def test_upsert_preserves_existing_suffix(self, conn):
        """COALESCE should preserve existing folder_suffix when new value is None."""
        from db.sync_queries import create_team, upsert_team_project, list_team_projects

        create_team(conn, "T1", "syncthing")
        upsert_team_project(conn, "T1", "P1", git_identity="org/p1", folder_suffix="org-p1")
        # Second upsert without folder_suffix should preserve it
        upsert_team_project(conn, "T1", "P1", git_identity="org/p1")

        projects = list_team_projects(conn, "T1")
        assert projects[0]["folder_suffix"] == "org-p1"

    def test_upsert_preserves_existing_suffix(self, conn):
        """BP-13: folder_suffix is immutable once set — upsert must NOT overwrite."""
        from db.sync_queries import create_team, upsert_team_project, list_team_projects

        create_team(conn, "T1", "syncthing")
        upsert_team_project(conn, "T1", "P1", git_identity="org/p1", folder_suffix="old-suffix")
        upsert_team_project(conn, "T1", "P1", git_identity="org/p1", folder_suffix="new-suffix")

        projects = list_team_projects(conn, "T1")
        assert projects[0]["folder_suffix"] == "old-suffix"

    def test_add_team_project_null_suffix_allowed(self, conn):
        """folder_suffix may be NULL (not all projects have it set yet)."""
        from db.sync_queries import create_team, add_team_project, list_team_projects

        create_team(conn, "T1", "syncthing")
        conn.execute("INSERT INTO projects (encoded_name) VALUES ('P1')")
        conn.commit()
        add_team_project(conn, "T1", "P1", git_identity="org/p1")

        projects = list_team_projects(conn, "T1")
        assert projects[0]["folder_suffix"] is None


class TestIsFolderRejectedTeamScoped:
    """Tests for team-scoped is_folder_rejected (BP-14 fix)."""

    def test_rejected_in_one_team_not_another(self, conn):
        from db.sync_queries import reject_folder, is_folder_rejected

        reject_folder(conn, "karma-out--alice--p1", team_name="T1")

        assert is_folder_rejected(conn, "karma-out--alice--p1", team_name="T1") is True
        assert is_folder_rejected(conn, "karma-out--alice--p1", team_name="T2") is False

    def test_without_team_name_matches_any(self, conn):
        from db.sync_queries import reject_folder, is_folder_rejected

        reject_folder(conn, "karma-out--alice--p1", team_name="T1")

        # Without team_name, should find the rejection
        assert is_folder_rejected(conn, "karma-out--alice--p1") is True

    def test_not_rejected_returns_false(self, conn):
        from db.sync_queries import is_folder_rejected

        assert is_folder_rejected(conn, "karma-out--bob--p2") is False
        assert is_folder_rejected(conn, "karma-out--bob--p2", team_name="T1") is False

    def test_reject_same_folder_multiple_teams(self, conn):
        from db.sync_queries import reject_folder, is_folder_rejected, list_rejected_folders

        reject_folder(conn, "karma-out--alice--p1", team_name="T1")
        reject_folder(conn, "karma-out--alice--p1", team_name="T2")

        assert is_folder_rejected(conn, "karma-out--alice--p1", team_name="T1") is True
        assert is_folder_rejected(conn, "karma-out--alice--p1", team_name="T2") is True

        t1_rejections = list_rejected_folders(conn, "T1")
        assert len(t1_rejections) == 1
        assert t1_rejections[0]["folder_id"] == "karma-out--alice--p1"

    def test_idempotent_reject(self, conn):
        """Calling reject_folder twice should not raise."""
        from db.sync_queries import reject_folder, is_folder_rejected

        reject_folder(conn, "karma-out--alice--p1", team_name="T1")
        reject_folder(conn, "karma-out--alice--p1", team_name="T1")  # should not raise

        assert is_folder_rejected(conn, "karma-out--alice--p1", team_name="T1") is True
