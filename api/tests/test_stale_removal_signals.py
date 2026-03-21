"""Tests for stale removal signal cleanup on team re-creation."""
import json
import sqlite3
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest
from pathlib import Path

from services.sync.metadata_service import MetadataService


@pytest.fixture
def meta_base(tmp_path):
    return tmp_path / "metadata-folders"


@pytest.fixture
def metadata(meta_base):
    meta_base.mkdir()
    return MetadataService(meta_base)


def test_purge_stale_removals_clears_old_signals(metadata, meta_base):
    """purge_stale_removals() should delete all files in removed/ dir."""
    team_dir = meta_base / "karma-meta--test-team"
    removed_dir = team_dir / "removed"
    removed_dir.mkdir(parents=True)

    # Plant a stale removal signal
    stale = {"member_tag": "alice.mac-mini", "removed_by": "bob.macbook", "removed_at": "2026-03-01T00:00:00+00:00"}
    (removed_dir / "alice.mac-mini.json").write_text(json.dumps(stale))

    metadata.purge_stale_removals("test-team")

    assert not list(removed_dir.glob("*.json")), "Stale removal signals should be purged"
    assert removed_dir.exists(), "removed/ directory itself should still exist"


def test_purge_stale_removals_noop_when_no_dir(metadata):
    """purge_stale_removals() should not fail if removed/ doesn't exist."""
    metadata.purge_stale_removals("nonexistent-team")  # Should not raise


def test_purge_stale_removals_preserves_members(metadata, meta_base):
    """purge_stale_removals() should NOT touch members/ directory."""
    team_dir = meta_base / "karma-meta--test-team"
    members_dir = team_dir / "members"
    removed_dir = team_dir / "removed"
    members_dir.mkdir(parents=True)
    removed_dir.mkdir(parents=True)

    (members_dir / "alice.mac-mini.json").write_text('{"member_tag": "alice.mac-mini"}')
    (removed_dir / "alice.mac-mini.json").write_text('{"member_tag": "alice.mac-mini"}')

    metadata.purge_stale_removals("test-team")

    assert (members_dir / "alice.mac-mini.json").exists(), "Members should be untouched"
    assert not (removed_dir / "alice.mac-mini.json").exists(), "Removal signal should be purged"


# ------------------------------------------------------------------
# TeamService integration test
# ------------------------------------------------------------------

from services.sync.team_service import TeamService


@pytest.fixture
def team_service(metadata):
    teams = MagicMock()
    members = MagicMock()
    projects = MagicMock()
    subs = MagicMock()
    events = MagicMock()
    devices = MagicMock()
    folders = AsyncMock()
    return TeamService(teams, members, projects, subs, events, devices, metadata, folders)


@pytest.fixture
def conn():
    c = sqlite3.connect(":memory:")
    return c


@pytest.mark.asyncio
async def test_create_team_purges_stale_removal_signals(team_service, meta_base, conn):
    """TeamService.create_team() should purge stale removal signals."""
    # Plant a stale removal signal from a prior team with the same name
    team_dir = meta_base / "karma-meta--recycled-team"
    removed_dir = team_dir / "removed"
    removed_dir.mkdir(parents=True)
    (removed_dir / "victim.mac-mini.json").write_text(
        json.dumps({"member_tag": "victim.mac-mini", "removed_by": "leader.macbook", "removed_at": "2026-03-01T00:00:00+00:00"})
    )

    await team_service.create_team(
        conn,
        name="recycled-team",
        leader_member_tag="leader.macbook",
        leader_device_id="DEVICE-ID-123",
    )

    assert not list(removed_dir.glob("*.json")), "Stale signals should be purged after create_team"
