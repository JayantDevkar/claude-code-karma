"""Tests for persistent folder rejection."""

import sqlite3

import pytest

from db.schema import ensure_schema


@pytest.fixture
def conn():
    """In-memory SQLite with schema applied."""
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA foreign_keys=ON")
    ensure_schema(c)
    return c


class TestRejectFolder:
    def test_reject_folder_persists(self, conn):
        """Rejecting a folder should persist in the DB."""
        from db.sync_queries import reject_folder, is_folder_rejected

        reject_folder(conn, "karma-out--ayush.mac--proj", team_name="acme")

        assert is_folder_rejected(conn, "karma-out--ayush.mac--proj") is True
        assert is_folder_rejected(conn, "karma-out--other--proj") is False

    def test_reject_folder_idempotent(self, conn):
        """Rejecting the same folder twice should not raise."""
        from db.sync_queries import reject_folder, is_folder_rejected

        reject_folder(conn, "karma-out--ayush.mac--proj", team_name="acme")
        reject_folder(conn, "karma-out--ayush.mac--proj", team_name="acme")

        assert is_folder_rejected(conn, "karma-out--ayush.mac--proj") is True

    def test_unreject_folder(self, conn):
        """Accepting a previously rejected folder should remove the rejection."""
        from db.sync_queries import reject_folder, unreject_folder, is_folder_rejected

        reject_folder(conn, "karma-out--ayush.mac--proj", team_name="acme")
        assert is_folder_rejected(conn, "karma-out--ayush.mac--proj") is True

        unreject_folder(conn, "karma-out--ayush.mac--proj")
        assert is_folder_rejected(conn, "karma-out--ayush.mac--proj") is False

    def test_unreject_nonexistent_is_noop(self, conn):
        """Unrejecting a folder that was never rejected should not raise."""
        from db.sync_queries import unreject_folder

        unreject_folder(conn, "karma-out--never-rejected--proj")  # no error

    def test_list_rejected_folders_by_team(self, conn):
        """Should list all rejected folders for a specific team."""
        from db.sync_queries import reject_folder, list_rejected_folders

        reject_folder(conn, "karma-out--a.mac--p1", team_name="acme")
        reject_folder(conn, "karma-out--b.mac--p2", team_name="acme")
        reject_folder(conn, "karma-out--c.mac--p3", team_name="other")

        acme_rejected = list_rejected_folders(conn, "acme")
        assert len(acme_rejected) == 2
        folder_ids = {r["folder_id"] for r in acme_rejected}
        assert folder_ids == {"karma-out--a.mac--p1", "karma-out--b.mac--p2"}

        other_rejected = list_rejected_folders(conn, "other")
        assert len(other_rejected) == 1
        assert other_rejected[0]["folder_id"] == "karma-out--c.mac--p3"

    def test_list_rejected_empty(self, conn):
        """Should return empty list when no folders rejected for team."""
        from db.sync_queries import list_rejected_folders

        assert list_rejected_folders(conn, "acme") == []
