"""Tests for team metadata folder helpers."""

import json
from pathlib import Path
import pytest


def test_write_member_state(tmp_path):
    """Writing member state creates the correct JSON file."""
    from services.sync_metadata import write_member_state

    meta_dir = tmp_path / "karma-meta--acme"
    meta_dir.mkdir()

    write_member_state(
        meta_dir,
        member_tag="jayant.mac-mini",
        user_id="jayant",
        machine_id="Jayants-Mac-Mini",
        device_id="LEADER-DID",
        subscriptions={"jayantdevkar-claude-karma": True},
        sync_direction="both",
        session_limit="all",
    )

    state_file = meta_dir / "members" / "jayant.mac-mini.json"
    assert state_file.exists()

    data = json.loads(state_file.read_text())
    assert data["member_tag"] == "jayant.mac-mini"
    assert data["user_id"] == "jayant"
    assert data["device_id"] == "LEADER-DID"
    assert data["subscriptions"]["jayantdevkar-claude-karma"] is True
    assert "updated_at" in data


def test_write_removal_signal(tmp_path):
    """Writing a removal signal creates the correct JSON file."""
    from services.sync_metadata import write_removal_signal

    meta_dir = tmp_path / "karma-meta--acme"
    meta_dir.mkdir()

    write_removal_signal(
        meta_dir,
        removed_member_tag="ayush.ayush-mac",
        removed_device_id="AYUSH-DID",
        removed_by="jayant.mac-mini",
    )

    removal_file = meta_dir / "removals" / "ayush.ayush-mac.json"
    assert removal_file.exists()

    data = json.loads(removal_file.read_text())
    assert data["member_tag"] == "ayush.ayush-mac"
    assert data["removed_by"] == "jayant.mac-mini"
    assert "removed_at" in data


def test_write_team_info(tmp_path):
    """Writing team info creates team.json."""
    from services.sync_metadata import write_team_info

    meta_dir = tmp_path / "karma-meta--acme"
    meta_dir.mkdir()

    write_team_info(meta_dir, team_name="acme", created_by="jayant.mac-mini")

    team_file = meta_dir / "team.json"
    assert team_file.exists()

    data = json.loads(team_file.read_text())
    assert data["name"] == "acme"
    assert data["created_by"] == "jayant.mac-mini"


def test_read_all_member_states(tmp_path):
    """Reading member states discovers all member files."""
    from services.sync_metadata import write_member_state, read_all_member_states

    meta_dir = tmp_path / "karma-meta--acme"
    meta_dir.mkdir()

    write_member_state(meta_dir, member_tag="jayant.mac-mini", user_id="jayant",
                       machine_id="Mini", device_id="DID1")
    write_member_state(meta_dir, member_tag="ayush.ayush-mac", user_id="ayush",
                       machine_id="Mac", device_id="DID2")

    states = read_all_member_states(meta_dir)
    assert len(states) == 2
    tags = {s["member_tag"] for s in states}
    assert tags == {"jayant.mac-mini", "ayush.ayush-mac"}


def test_read_removal_signals(tmp_path):
    """Reading removal signals discovers all removal files."""
    from services.sync_metadata import write_removal_signal, read_removal_signals

    meta_dir = tmp_path / "karma-meta--acme"
    meta_dir.mkdir()

    write_removal_signal(meta_dir, removed_member_tag="ayush.ayush-mac",
                         removed_device_id="DID2", removed_by="jayant.mac-mini")

    removals = read_removal_signals(meta_dir)
    assert len(removals) == 1
    assert removals[0]["member_tag"] == "ayush.ayush-mac"


def test_read_team_info(tmp_path):
    """Reading team info returns creator."""
    from services.sync_metadata import write_team_info, read_team_info

    meta_dir = tmp_path / "karma-meta--acme"
    meta_dir.mkdir()
    write_team_info(meta_dir, team_name="acme", created_by="jayant.mac-mini")

    info = read_team_info(meta_dir)
    assert info["created_by"] == "jayant.mac-mini"


def test_is_removed(tmp_path):
    """Check if a specific member_tag has a removal signal."""
    from services.sync_metadata import write_removal_signal, is_removed

    meta_dir = tmp_path / "karma-meta--acme"
    meta_dir.mkdir()

    assert is_removed(meta_dir, "ayush.ayush-mac") is False

    write_removal_signal(meta_dir, removed_member_tag="ayush.ayush-mac",
                         removed_device_id="DID", removed_by="jayant.mac-mini")

    assert is_removed(meta_dir, "ayush.ayush-mac") is True


def test_validate_removal_authority(tmp_path):
    """Only the team creator can remove members."""
    from services.sync_metadata import write_team_info, validate_removal_authority

    meta_dir = tmp_path / "karma-meta--acme"
    meta_dir.mkdir()
    write_team_info(meta_dir, team_name="acme", created_by="jayant.mac-mini")

    assert validate_removal_authority(meta_dir, "jayant.mac-mini") is True
    assert validate_removal_authority(meta_dir, "ayush.ayush-mac") is False


def test_build_metadata_folder_id():
    """Build karma-meta--{team} folder ID."""
    from services.sync_metadata import build_metadata_folder_id

    assert build_metadata_folder_id("acme") == "karma-meta--acme"
    with pytest.raises(ValueError):
        build_metadata_folder_id("bad--name")


def test_parse_metadata_folder_id():
    """Parse karma-meta--{team} folder ID."""
    from services.sync_metadata import parse_metadata_folder_id

    assert parse_metadata_folder_id("karma-meta--acme") == "acme"
    assert parse_metadata_folder_id("karma-out--foo--bar") is None


def test_is_metadata_folder():
    """Check if a folder ID is a metadata folder."""
    from services.sync_metadata import is_metadata_folder

    assert is_metadata_folder("karma-meta--acme") is True
    assert is_metadata_folder("karma-out--foo--bar") is False


def test_read_empty_members_dir(tmp_path):
    """Reading from a non-existent members dir returns empty list."""
    from services.sync_metadata import read_all_member_states

    meta_dir = tmp_path / "karma-meta--acme"
    meta_dir.mkdir()
    assert read_all_member_states(meta_dir) == []


def test_read_team_info_missing(tmp_path):
    """Reading team.json from empty dir returns None."""
    from services.sync_metadata import read_team_info

    meta_dir = tmp_path / "karma-meta--acme"
    meta_dir.mkdir()
    assert read_team_info(meta_dir) is None
