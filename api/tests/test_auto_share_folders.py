"""Tests for auto_share_folders() API function."""

import asyncio
import sqlite3
from pathlib import Path
from unittest.mock import MagicMock, AsyncMock, patch

import pytest

import sys

# Add API and CLI to path
API_PATH = Path(__file__).parent.parent
CLI_PATH = API_PATH.parent / "cli"
sys.path.insert(0, str(API_PATH))
sys.path.insert(0, str(CLI_PATH))

from db.schema import ensure_schema
from db.sync_queries import create_team, add_member, add_team_project


async def _fake_run_sync(func, *args, **kwargs):
    """Drop-in for run_sync that calls the function directly."""
    return func(*args, **kwargs)


def _make_db():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    ensure_schema(conn)
    return conn


def _make_config(user_id="alice", device_id="ALICE-DEVICE-ID"):
    config = MagicMock()
    config.user_id = user_id
    config.syncthing.device_id = device_id
    return config


def _make_proxy():
    proxy = MagicMock()
    proxy.add_folder = MagicMock(return_value={"ok": True})
    proxy.update_folder_devices = MagicMock(return_value={"ok": True})
    return proxy


@pytest.fixture
def db():
    return _make_db()


@pytest.fixture
def config():
    return _make_config()


@pytest.fixture
def proxy():
    return _make_proxy()


class TestAutoShareFolders:
    def test_creates_outbox_and_inbox(self, db, config, proxy):
        """Adding a member creates outbox + inbox folders."""
        create_team(db, "team1")
        add_member(db, "team1", "bob", device_id="BOB-DEVICE-ID")
        db.execute(
            "INSERT OR IGNORE INTO projects (encoded_name, project_path) VALUES (?, ?)",
            ("-Users-alice-project-a", "/Users/alice/project-a"),
        )
        db.commit()
        add_team_project(db, "team1", "-Users-alice-project-a", "/Users/alice/project-a")

        from services.sync_folders import auto_share_folders

        with patch("services.sync_folders.run_sync", side_effect=_fake_run_sync):
            result = asyncio.get_event_loop().run_until_complete(
                auto_share_folders(proxy, config, db, "team1", "BOB-DEVICE-ID")
            )

        assert result["outboxes"] == 1
        assert result["inboxes"] == 1
        assert result["errors"] == []

    def test_no_projects_is_noop(self, db, config, proxy):
        """No projects means no folders created."""
        create_team(db, "team1")
        add_member(db, "team1", "bob", device_id="BOB-DEVICE-ID")

        from services.sync_folders import auto_share_folders

        with patch("services.sync_folders.run_sync", side_effect=_fake_run_sync):
            result = asyncio.get_event_loop().run_until_complete(
                auto_share_folders(proxy, config, db, "team1", "BOB-DEVICE-ID")
            )

        assert result["outboxes"] == 0
        assert result["inboxes"] == 0

    def test_existing_outbox_uses_update(self, db, config, proxy):
        """Existing outbox gets update_folder_devices, not add_folder."""
        create_team(db, "team1")
        add_member(db, "team1", "bob", device_id="BOB-DEVICE-ID")
        db.execute(
            "INSERT OR IGNORE INTO projects (encoded_name, project_path) VALUES (?, ?)",
            ("-Users-alice-project-a", "/Users/alice/project-a"),
        )
        db.commit()
        add_team_project(db, "team1", "-Users-alice-project-a", "/Users/alice/project-a")

        # update_folder_devices succeeds (folder exists)
        from services.sync_folders import auto_share_folders

        with patch("services.sync_folders.run_sync", side_effect=_fake_run_sync):
            result = asyncio.get_event_loop().run_until_complete(
                auto_share_folders(proxy, config, db, "team1", "BOB-DEVICE-ID")
            )

        # update_folder_devices should be called for outbox
        proxy.update_folder_devices.assert_called()
        assert result["outboxes"] == 1

    def test_update_fails_falls_back_to_add(self, db, config, proxy):
        """When update_folder_devices raises ValueError, falls back to add_folder."""
        create_team(db, "team1")
        add_member(db, "team1", "bob", device_id="BOB-DEVICE-ID")
        db.execute(
            "INSERT OR IGNORE INTO projects (encoded_name, project_path) VALUES (?, ?)",
            ("-Users-alice-project-a", "/Users/alice/project-a"),
        )
        db.commit()
        add_team_project(db, "team1", "-Users-alice-project-a", "/Users/alice/project-a")

        # update raises ValueError (folder not found), add_folder succeeds
        proxy.update_folder_devices.side_effect = ValueError("not found")

        from services.sync_folders import auto_share_folders

        with patch("services.sync_folders.run_sync", side_effect=_fake_run_sync):
            result = asyncio.get_event_loop().run_until_complete(
                auto_share_folders(proxy, config, db, "team1", "BOB-DEVICE-ID")
            )

        proxy.add_folder.assert_called()
        assert result["outboxes"] == 1

    def test_errors_collected_not_raised(self, db, config, proxy):
        """Errors are collected in the result, not raised."""
        create_team(db, "team1")
        add_member(db, "team1", "bob", device_id="BOB-DEVICE-ID")
        db.execute(
            "INSERT OR IGNORE INTO projects (encoded_name, project_path) VALUES (?, ?)",
            ("-Users-alice-project-a", "/Users/alice/project-a"),
        )
        db.commit()
        add_team_project(db, "team1", "-Users-alice-project-a", "/Users/alice/project-a")

        proxy.update_folder_devices.side_effect = ValueError("not found")
        proxy.add_folder.side_effect = RuntimeError("Syncthing error")

        from services.sync_folders import auto_share_folders

        with patch("services.sync_folders.run_sync", side_effect=_fake_run_sync):
            result = asyncio.get_event_loop().run_until_complete(
                auto_share_folders(proxy, config, db, "team1", "BOB-DEVICE-ID")
            )

        assert result["outboxes"] == 0
        assert len(result["errors"]) > 0

    def test_uses_git_identity_in_folder_id(self, db, config, proxy):
        """Folder ID uses git_identity when available."""
        create_team(db, "team1")
        add_member(db, "team1", "bob", device_id="BOB-DEVICE-ID")
        db.execute(
            "INSERT OR IGNORE INTO projects (encoded_name, project_path) VALUES (?, ?)",
            ("-Users-alice-project-a", "/Users/alice/project-a"),
        )
        db.commit()
        add_team_project(db, "team1", "-Users-alice-project-a", "/Users/alice/project-a",
                         git_identity="jayantdevkar/claude-karma")

        from services.sync_folders import auto_share_folders

        with patch("services.sync_folders.run_sync", side_effect=_fake_run_sync):
            result = asyncio.get_event_loop().run_until_complete(
                auto_share_folders(proxy, config, db, "team1", "BOB-DEVICE-ID")
            )

        # Check that the folder ID contains git identity suffix
        calls = proxy.update_folder_devices.call_args_list + proxy.add_folder.call_args_list
        folder_ids = [c[0][0] for c in calls if c[0]]
        assert any("jayantdevkar-claude-karma" in fid for fid in folder_ids)

    def test_multiple_projects(self, db, config, proxy):
        """Multiple projects each get outbox + inbox."""
        create_team(db, "team1")
        add_member(db, "team1", "bob", device_id="BOB-DEVICE-ID")
        for name, path in [
            ("-Users-alice-project-a", "/Users/alice/project-a"),
            ("-Users-alice-project-b", "/Users/alice/project-b"),
        ]:
            db.execute(
                "INSERT OR IGNORE INTO projects (encoded_name, project_path) VALUES (?, ?)",
                (name, path),
            )
            db.commit()
            add_team_project(db, "team1", name, path)

        from services.sync_folders import auto_share_folders

        with patch("services.sync_folders.run_sync", side_effect=_fake_run_sync):
            result = asyncio.get_event_loop().run_until_complete(
                auto_share_folders(proxy, config, db, "team1", "BOB-DEVICE-ID")
            )

        assert result["outboxes"] == 2
        assert result["inboxes"] == 2


