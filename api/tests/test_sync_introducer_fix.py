"""Tests for ensure_leader_introducers self-skip fix."""

import sqlite3
from unittest.mock import AsyncMock, MagicMock

import pytest

from db.schema import ensure_schema


@pytest.fixture
def conn():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA foreign_keys=ON")
    ensure_schema(c)
    return c


@pytest.mark.asyncio
async def test_ensure_leader_introducers_skips_self(conn):
    """Should not attempt to set introducer on own device."""
    from db.sync_queries import create_team

    create_team(conn, "acme", backend="syncthing", join_code="acme:jayant:LEADER-DID")

    mock_proxy = AsyncMock()

    from services.sync_reconciliation import ensure_leader_introducers
    count = await ensure_leader_introducers(mock_proxy, conn, own_device_id="LEADER-DID")

    # Should NOT have called set_device_introducer (skipped self)
    mock_proxy.set_device_introducer.assert_not_called()
    assert count == 0


@pytest.mark.asyncio
async def test_ensure_leader_introducers_sets_other_device(conn):
    """Should set introducer on a different device (not self)."""
    from db.sync_queries import create_team

    create_team(conn, "acme", backend="syncthing", join_code="acme:jayant:OTHER-DID")

    mock_proxy = AsyncMock()
    mock_proxy.set_device_introducer = MagicMock(return_value=True)

    from services.sync_reconciliation import ensure_leader_introducers
    count = await ensure_leader_introducers(mock_proxy, conn, own_device_id="MY-DID")

    mock_proxy.set_device_introducer.assert_called_once()
    assert count == 1
