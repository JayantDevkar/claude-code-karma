"""Tests for auto_accept exception handling fix."""

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


@pytest.fixture
def mock_config():
    config = MagicMock()
    config.user_id = "jayant"
    config.machine_id = "Mac-Mini"
    config.syncthing.device_id = "LEADER-DID"
    return config


@pytest.mark.asyncio
async def test_auto_accept_continues_after_add_device_failure(conn, mock_config):
    """If add_device fails (device already configured), should still add member + share folders."""
    from db.sync_queries import create_team, list_members

    create_team(conn, "acme", backend="syncthing", join_code="acme:jayant:LEADER-DID")

    mock_proxy = AsyncMock()
    # add_device raises (device already configured by introducer)
    mock_proxy.add_device = MagicMock(side_effect=Exception("device already exists"))
    mock_proxy.get_pending_devices = MagicMock(return_value={
        "AYUSH-DID": {"name": "ayush"},
    })
    mock_proxy.get_pending_folders = MagicMock(return_value={
        "karma-join--ayush--acme": {"offeredBy": {"AYUSH-DID": {}}},
    })
    mock_proxy.get_configured_folders = MagicMock(return_value=[])

    with patch("services.sync_reconciliation.should_auto_accept_device", return_value=True):
        with patch(
            "services.sync_reconciliation.auto_share_folders",
            new_callable=AsyncMock,
        ) as mock_share:
            from services.sync_reconciliation import auto_accept_pending_peers
            accepted, remaining = await auto_accept_pending_peers(mock_proxy, mock_config, conn)

    # Member should have been added despite add_device failure
    members = list_members(conn, "acme")
    ayush_members = [m for m in members if m["name"] == "ayush"]
    assert len(ayush_members) == 1, "ayush should be added to DB even if add_device fails"

    # auto_share_folders should have been called
    mock_share.assert_called_once()
