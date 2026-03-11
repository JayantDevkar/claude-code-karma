"""Tests for metadata folder reconciliation."""

import sqlite3
import json
from pathlib import Path
from unittest.mock import MagicMock, patch
import pytest

from db.schema import ensure_schema


@pytest.fixture
def conn():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA foreign_keys=ON")
    ensure_schema(c)
    return c


@pytest.fixture
def mock_config():
    config = MagicMock()
    config.user_id = "jayant"
    config.machine_id = "Mac-Mini"
    config.machine_tag = "mac-mini"
    config.member_tag = "jayant.mac-mini"
    config.syncthing = MagicMock()
    config.syncthing.device_id = "LEADER-DID"
    return config


def test_reconcile_discovers_new_member(conn, mock_config, tmp_path):
    """New member in metadata folder should be added to DB."""
    from db.sync_queries import create_team, upsert_member, list_members

    create_team(conn, "acme", backend="syncthing")
    upsert_member(conn, "acme", "jayant", device_id="LEADER-DID",
                  member_tag="jayant.mac-mini")

    # Write ayush's state to metadata folder
    meta_dir = tmp_path / "metadata-folders" / "acme"
    members_dir = meta_dir / "members"
    members_dir.mkdir(parents=True)
    (members_dir / "ayush.ayush-mac.json").write_text(json.dumps({
        "member_tag": "ayush.ayush-mac",
        "user_id": "ayush",
        "machine_id": "Ayush-Mac",
        "device_id": "AYUSH-DID",
    }))

    with patch("karma.config.KARMA_BASE", tmp_path):
        from services.sync_metadata_reconciler import reconcile_metadata_folder
        result = reconcile_metadata_folder(mock_config, conn, "acme")

    assert result["members_added"] == 1
    members = list_members(conn, "acme")
    ayush = [m for m in members if m["name"] == "ayush"]
    assert len(ayush) == 1
    assert ayush[0]["member_tag"] == "ayush.ayush-mac"


def test_reconcile_detects_self_removal(conn, mock_config, tmp_path):
    """If our member_tag has a removal signal, self_removed should be True."""
    from db.sync_queries import create_team

    create_team(conn, "acme", backend="syncthing")

    meta_dir = tmp_path / "metadata-folders" / "acme"
    removals_dir = meta_dir / "removals"
    removals_dir.mkdir(parents=True)
    (removals_dir / "jayant.mac-mini.json").write_text(json.dumps({
        "member_tag": "jayant.mac-mini",
        "device_id": "LEADER-DID",
        "removed_by": "admin.admin-pc",
        "removed_at": "2026-03-11T12:00:00Z",
    }))

    with patch("karma.config.KARMA_BASE", tmp_path):
        from services.sync_metadata_reconciler import reconcile_metadata_folder
        result = reconcile_metadata_folder(mock_config, conn, "acme")

    assert result["self_removed"] is True
    assert result["members_added"] == 0


def test_reconcile_skips_removed_members(conn, mock_config, tmp_path):
    """Members with removal signals should not be added to DB."""
    from db.sync_queries import create_team, upsert_member, list_members

    create_team(conn, "acme", backend="syncthing")
    upsert_member(conn, "acme", "jayant", device_id="LEADER-DID",
                  member_tag="jayant.mac-mini")

    meta_dir = tmp_path / "metadata-folders" / "acme"
    members_dir = meta_dir / "members"
    members_dir.mkdir(parents=True)
    removals_dir = meta_dir / "removals"
    removals_dir.mkdir(parents=True)

    # Write ayush's state
    (members_dir / "ayush.ayush-mac.json").write_text(json.dumps({
        "member_tag": "ayush.ayush-mac",
        "user_id": "ayush",
        "machine_id": "Ayush-Mac",
        "device_id": "AYUSH-DID",
    }))
    # But also a removal signal for ayush
    (removals_dir / "ayush.ayush-mac.json").write_text(json.dumps({
        "member_tag": "ayush.ayush-mac",
        "device_id": "AYUSH-DID",
        "removed_by": "jayant.mac-mini",
        "removed_at": "2026-03-11T12:00:00Z",
    }))

    with patch("karma.config.KARMA_BASE", tmp_path):
        from services.sync_metadata_reconciler import reconcile_metadata_folder
        result = reconcile_metadata_folder(mock_config, conn, "acme")

    assert result["members_added"] == 0
    members = list_members(conn, "acme")
    assert len(members) == 1  # only jayant


def test_reconcile_skips_self(conn, mock_config, tmp_path):
    """Own member_tag in metadata should not be re-added."""
    from db.sync_queries import create_team, upsert_member, list_members

    create_team(conn, "acme", backend="syncthing")
    upsert_member(conn, "acme", "jayant", device_id="LEADER-DID",
                  member_tag="jayant.mac-mini")

    meta_dir = tmp_path / "metadata-folders" / "acme"
    members_dir = meta_dir / "members"
    members_dir.mkdir(parents=True)

    # Own state file
    (members_dir / "jayant.mac-mini.json").write_text(json.dumps({
        "member_tag": "jayant.mac-mini",
        "user_id": "jayant",
        "machine_id": "Mac-Mini",
        "device_id": "LEADER-DID",
    }))

    with patch("karma.config.KARMA_BASE", tmp_path):
        from services.sync_metadata_reconciler import reconcile_metadata_folder
        result = reconcile_metadata_folder(mock_config, conn, "acme")

    assert result["members_added"] == 0
    assert result["members_updated"] == 0


def test_reconcile_updates_existing_member(conn, mock_config, tmp_path):
    """Existing member with matching device_id gets identity updated."""
    from db.sync_queries import create_team, upsert_member, list_members

    create_team(conn, "acme", backend="syncthing")
    upsert_member(conn, "acme", "jayant", device_id="LEADER-DID",
                  member_tag="jayant.mac-mini")
    # Ayush exists but without member_tag
    upsert_member(conn, "acme", "ayush", device_id="AYUSH-DID")

    meta_dir = tmp_path / "metadata-folders" / "acme"
    members_dir = meta_dir / "members"
    members_dir.mkdir(parents=True)

    (members_dir / "ayush.ayush-mac.json").write_text(json.dumps({
        "member_tag": "ayush.ayush-mac",
        "user_id": "ayush",
        "machine_id": "Ayush-Mac",
        "device_id": "AYUSH-DID",
    }))

    with patch("karma.config.KARMA_BASE", tmp_path):
        from services.sync_metadata_reconciler import reconcile_metadata_folder
        result = reconcile_metadata_folder(mock_config, conn, "acme")

    assert result["members_updated"] == 1
    members = list_members(conn, "acme")
    ayush = [m for m in members if m["name"] == "ayush"]
    assert ayush[0]["member_tag"] == "ayush.ayush-mac"


def test_reconcile_missing_meta_dir(conn, mock_config, tmp_path):
    """If metadata dir doesn't exist, return empty results."""
    from db.sync_queries import create_team

    create_team(conn, "acme", backend="syncthing")

    with patch("karma.config.KARMA_BASE", tmp_path):
        from services.sync_metadata_reconciler import reconcile_metadata_folder
        result = reconcile_metadata_folder(mock_config, conn, "acme")

    assert result["members_added"] == 0
    assert result["self_removed"] is False


def test_reconcile_all_teams(conn, mock_config, tmp_path):
    """reconcile_all_teams_metadata iterates all teams."""
    from db.sync_queries import create_team, upsert_member

    create_team(conn, "acme", backend="syncthing")
    create_team(conn, "beta", backend="syncthing")
    upsert_member(conn, "acme", "jayant", device_id="LEADER-DID",
                  member_tag="jayant.mac-mini")
    upsert_member(conn, "beta", "jayant", device_id="LEADER-DID",
                  member_tag="jayant.mac-mini")

    # Write new member to acme metadata
    meta_dir = tmp_path / "metadata-folders" / "acme"
    members_dir = meta_dir / "members"
    members_dir.mkdir(parents=True)
    (members_dir / "bob.bob-pc.json").write_text(json.dumps({
        "member_tag": "bob.bob-pc",
        "user_id": "bob",
        "machine_id": "Bob-PC",
        "device_id": "BOB-DID",
    }))

    with patch("karma.config.KARMA_BASE", tmp_path):
        from services.sync_metadata_reconciler import reconcile_all_teams_metadata
        result = reconcile_all_teams_metadata(mock_config, conn)

    assert result["teams"] == 2
    assert result["members_added"] == 1
    assert result["self_removed_teams"] == []
