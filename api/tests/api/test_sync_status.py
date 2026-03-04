"""Tests for sync status API endpoints."""

import json

import pytest
from fastapi.testclient import TestClient

from main import app

client = TestClient(app)


class TestSyncStatus:
    def test_sync_status_no_config(self, tmp_path, monkeypatch):
        monkeypatch.setattr(
            "routers.sync_status.SYNC_CONFIG_PATH",
            tmp_path / "nonexistent.json",
        )
        resp = client.get("/sync/status")
        assert resp.status_code == 200
        data = resp.json()
        assert data["configured"] is False

    def test_sync_status_with_config(self, tmp_path, monkeypatch):
        config_path = tmp_path / "sync-config.json"
        config_path.write_text(json.dumps({
            "user_id": "alice",
            "machine_id": "mac",
            "teams": {
                "beta": {
                    "backend": "syncthing",
                    "projects": {"app": {"path": "/app", "encoded_name": "-app"}},
                    "members": {},
                }
            },
            "projects": {},
            "team": {},
        }))
        monkeypatch.setattr("routers.sync_status.SYNC_CONFIG_PATH", config_path)
        resp = client.get("/sync/status")
        assert resp.status_code == 200
        data = resp.json()
        assert data["configured"] is True
        assert data["user_id"] == "alice"
        assert "beta" in data["teams"]

    def test_sync_teams_endpoint(self, tmp_path, monkeypatch):
        config_path = tmp_path / "sync-config.json"
        config_path.write_text(json.dumps({
            "user_id": "alice",
            "machine_id": "mac",
            "teams": {
                "alpha": {"backend": "ipfs", "projects": {}, "members": {}},
                "beta": {"backend": "syncthing", "projects": {}, "members": {}},
            },
            "projects": {},
            "team": {},
        }))
        monkeypatch.setattr("routers.sync_status.SYNC_CONFIG_PATH", config_path)
        resp = client.get("/sync/teams")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["teams"]) == 2

    def test_sync_status_corrupt_config(self, tmp_path, monkeypatch):
        config_path = tmp_path / "sync-config.json"
        config_path.write_text("not valid json{{{")
        monkeypatch.setattr("routers.sync_status.SYNC_CONFIG_PATH", config_path)
        resp = client.get("/sync/status")
        assert resp.status_code == 200
        data = resp.json()
        assert data["configured"] is False

    def test_sync_teams_no_config(self, tmp_path, monkeypatch):
        monkeypatch.setattr(
            "routers.sync_status.SYNC_CONFIG_PATH",
            tmp_path / "nonexistent.json",
        )
        resp = client.get("/sync/teams")
        assert resp.status_code == 200
        data = resp.json()
        assert data["teams"] == []
