"""Tests for sync team CRUD endpoints (SQLite-backed)."""
from __future__ import annotations

import sqlite3
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).parent.parent))

from db.schema import ensure_schema


@pytest.fixture(autouse=True)
def _reset_singletons():
    """Reset router singletons between tests."""
    import services.sync_identity as mod
    mod._proxy = None
    mod._watcher = None
    yield
    mod._proxy = None
    mod._watcher = None


@pytest.fixture
def mock_db(tmp_path, monkeypatch):
    """In-memory SQLite with schema, patched into the router via get_writer_db."""
    conn = sqlite3.connect(":memory:", check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    ensure_schema(conn)

    monkeypatch.setattr("services.sync_identity._get_sync_conn", lambda: conn)

    # Provide identity config
    config_path = tmp_path / "sync-config.json"
    config_path.write_text('{"user_id": "jayant", "machine_id": "mac", "syncthing": {"device_id": "TEST-DEV-ID"}}')
    monkeypatch.setattr("karma.config.SYNC_CONFIG_PATH", config_path)

    # Clear identity TTL cache so tests get fresh config
    from services.sync_identity import _invalidate_identity_cache
    _invalidate_identity_cache()

    return conn


@pytest.fixture
def mock_no_config(tmp_path, monkeypatch):
    """No sync config file exists."""
    conn = sqlite3.connect(":memory:", check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    ensure_schema(conn)
    monkeypatch.setattr("services.sync_identity._get_sync_conn", lambda: conn)
    monkeypatch.setattr("karma.config.SYNC_CONFIG_PATH", tmp_path / "nope.json")

    # Clear identity TTL cache so tests get fresh config
    from services.sync_identity import _invalidate_identity_cache
    _invalidate_identity_cache()

    return conn


class TestCreateTeam:
    def test_create_team_success(self, mock_db):
        from main import app
        client = TestClient(app)

        resp = client.post("/sync/teams", json={
            "name": "frontend-team",
            "backend": "syncthing",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["ok"] is True
        assert data["name"] == "frontend-team"

        # Verify in DB
        row = mock_db.execute("SELECT * FROM sync_teams WHERE name = ?", ("frontend-team",)).fetchone()
        assert row is not None
        assert row["backend"] == "syncthing"

        # Verify creator added as member
        member = mock_db.execute(
            "SELECT * FROM sync_members WHERE team_name = ? AND name = ?",
            ("frontend-team", "jayant"),
        ).fetchone()
        assert member is not None, "Creator must be added as a member of their own team"

        # Verify event logged
        events = mock_db.execute("SELECT * FROM sync_events WHERE event_type = 'team_created'").fetchall()
        assert len(events) == 1

    def test_create_team_requires_init(self, mock_no_config):
        from main import app
        client = TestClient(app)
        resp = client.post("/sync/teams", json={
            "name": "test", "backend": "syncthing",
        })
        assert resp.status_code == 400

    def test_create_team_invalid_name(self, mock_db):
        from main import app
        client = TestClient(app)
        resp = client.post("/sync/teams", json={
            "name": "../evil", "backend": "syncthing",
        })
        assert resp.status_code == 400

    def test_create_team_duplicate(self, mock_db):
        mock_db.execute("INSERT INTO sync_teams (name, backend) VALUES (?, ?)", ("existing", "syncthing"))
        mock_db.commit()

        from main import app
        client = TestClient(app)
        resp = client.post("/sync/teams", json={
            "name": "existing", "backend": "syncthing",
        })
        assert resp.status_code == 409

    def test_create_team_invalid_backend(self, mock_db):
        from main import app
        client = TestClient(app)
        resp = client.post("/sync/teams", json={
            "name": "test", "backend": "dropbox",
        })
        assert resp.status_code == 400


class TestDeleteTeam:
    def test_delete_team_success(self, mock_db):
        mock_db.execute("INSERT INTO sync_teams (name, backend) VALUES (?, ?)", ("old-team", "syncthing"))
        mock_db.commit()

        from main import app
        client = TestClient(app)
        resp = client.delete("/sync/teams/old-team")
        assert resp.status_code == 200
        assert resp.json()["ok"] is True

        row = mock_db.execute("SELECT * FROM sync_teams WHERE name = ?", ("old-team",)).fetchone()
        assert row is None

    def test_delete_team_not_found(self, mock_db):
        from main import app
        client = TestClient(app)
        resp = client.delete("/sync/teams/nope")
        assert resp.status_code == 404
