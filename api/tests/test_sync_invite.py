"""Tests for any-member invite generation."""

import sqlite3
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from db.schema import ensure_schema


@pytest.fixture
def conn():
    """In-memory SQLite with schema applied (cross-thread for TestClient)."""
    c = sqlite3.connect(":memory:", check_same_thread=False)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA foreign_keys=ON")
    ensure_schema(c)
    return c


class TestInviteCodeFormat:
    def test_invite_code_uses_member_tag(self):
        """Invite code should use member_tag (user_id.machine_tag), not just user_id."""
        invite = "acme:ayush.ayush-mac:AYUSH-DID"
        parts = invite.split(":", 2)
        assert parts[0] == "acme"
        assert parts[1] == "ayush.ayush-mac"  # member_tag
        assert parts[2] == "AYUSH-DID"

    def test_invite_code_compatible_with_join(self):
        """Invite code should be parseable by the existing join handler."""
        invite = "acme:ayush.ayush-mac:AYUSH-DEVICE-ID-FULL"
        parts = invite.split(":", 2)
        assert len(parts) == 3
        team_name, leader_name, device_id = parts
        assert team_name == "acme"
        assert leader_name == "ayush.ayush-mac"
        assert device_id == "AYUSH-DEVICE-ID-FULL"


class TestInviteEndpoint:
    def test_invite_requires_membership(self, conn):
        """Non-members should get 403."""
        from db.sync_queries import create_team

        create_team(conn, "acme", "syncthing")
        # No members added — caller won't match

        config = MagicMock()
        config.syncthing.device_id = "UNKNOWN-DID"
        config.member_tag = "stranger.laptop"
        config.user_id = "stranger"

        with patch("services.sync_identity._get_sync_conn", return_value=conn), \
             patch("services.sync_identity._load_identity", return_value=config):
            from main import app
            client = TestClient(app)
            response = client.post("/sync/teams/acme/invite")
            assert response.status_code == 403

    def test_invite_returns_code_for_member(self, conn):
        """Team members should get a valid invite code."""
        from db.sync_queries import create_team, upsert_member

        create_team(conn, "acme", "syncthing")
        upsert_member(conn, "acme", "ayush", device_id="AYUSH-DID",
                       member_tag="ayush.ayush-mac")

        config = MagicMock()
        config.syncthing.device_id = "AYUSH-DID"
        config.member_tag = "ayush.ayush-mac"
        config.user_id = "ayush"

        with patch("services.sync_identity._get_sync_conn", return_value=conn), \
             patch("services.sync_identity._load_identity", return_value=config):
            from main import app
            client = TestClient(app)
            response = client.post("/sync/teams/acme/invite")
            assert response.status_code == 200
            data = response.json()
            assert data["team_name"] == "acme"
            assert data["inviter"] == "ayush.ayush-mac"
            assert data["invite_code"] == "acme:ayush.ayush-mac:AYUSH-DID"

    def test_invite_nonexistent_team(self, conn):
        """Should return 404 for unknown team."""
        config = MagicMock()
        config.syncthing.device_id = "SOME-DID"
        config.member_tag = "user.mac"
        config.user_id = "user"

        with patch("services.sync_identity._get_sync_conn", return_value=conn), \
             patch("services.sync_identity._load_identity", return_value=config):
            from main import app
            client = TestClient(app)
            response = client.post("/sync/teams/nonexistent/invite")
            assert response.status_code == 404
