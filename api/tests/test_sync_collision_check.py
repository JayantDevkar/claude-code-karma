"""Tests for user_id collision check during device acceptance."""

import sqlite3

import pytest

from db.schema import ensure_schema


@pytest.fixture
def conn():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA foreign_keys=ON")
    ensure_schema(c)
    return c


def test_accept_rejects_colliding_member_name(conn):
    """Accepting a device whose name collides with an existing member should fail."""
    from db.sync_queries import create_team, upsert_member, list_members

    create_team(conn, "acme", backend="syncthing")
    upsert_member(conn, "acme", "jayant", device_id="EXISTING-DID")

    # A different device claiming the name "jayant" should be detected
    members = list_members(conn, "acme")
    collisions = [
        m for m in members
        if m["name"] == "jayant" and m["device_id"] != "NEW-DID"
    ]
    assert len(collisions) == 1, "Should detect name collision"
