"""Tests for reconcile_introduced_devices auto_share_folders fix."""

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
async def test_reconcile_introduced_devices_calls_auto_share(conn, mock_config):
    """Introduced devices should get folders shared back (not just DB record)."""
    from db.sync_queries import create_team, upsert_member, add_team_project

    # Setup: team with one project, leader is a member
    create_team(conn, "acme", backend="syncthing")
    upsert_member(conn, "acme", "jayant", device_id="LEADER-DID")
    conn.execute(
        "INSERT INTO projects (encoded_name) VALUES (?)",
        ("-Users-test-proj",),
    )
    add_team_project(conn, "acme", "-Users-test-proj", path="/test", git_identity="org/proj")

    # Mock proxy: one introduced device NOT in karma DB
    mock_proxy = AsyncMock()
    mock_proxy.get_devices = MagicMock(return_value=[
        {"device_id": "AYUSH-DID", "name": "ayush", "is_self": False},
        {"device_id": "LEADER-DID", "name": "jayant", "is_self": True},
    ])
    mock_proxy.get_configured_folders = MagicMock(return_value=[
        {
            "id": "karma-join--ayush--acme",
            "type": "receiveonly",
            "devices": [{"deviceID": "AYUSH-DID"}, {"deviceID": "LEADER-DID"}],
        },
    ])

    with patch(
        "services.sync_reconciliation.auto_share_folders",
        new_callable=AsyncMock,
    ) as mock_share:
        from services.sync_reconciliation import reconcile_introduced_devices
        count = await reconcile_introduced_devices(mock_proxy, mock_config, conn)

    assert count == 1
    # KEY ASSERTION: auto_share_folders was called for the introduced device
    mock_share.assert_called_once_with(mock_proxy, mock_config, conn, "acme", "AYUSH-DID")
