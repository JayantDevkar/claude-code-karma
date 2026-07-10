"""Tests for sync_system v4 router."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import sqlite3
from unittest.mock import MagicMock, AsyncMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from db.schema import ensure_schema
from domain.team import Team


@pytest.fixture
def conn():
    c = sqlite3.connect(":memory:", check_same_thread=False)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA foreign_keys=ON")
    ensure_schema(c)
    return c


@pytest.fixture
def mock_config():
    config = MagicMock()
    config.user_id = "jayant"
    config.machine_id = "abc123"
    config.member_tag = "jayant.macbook"
    config.syncthing = MagicMock()
    config.syncthing.device_id = "DEV-SELF"
    config.syncthing.api_key = "test-key"
    return config


@pytest.fixture
def mock_recon_svc():
    svc = MagicMock()
    svc.run_cycle = AsyncMock()
    return svc


@pytest.fixture
def client(conn, mock_config, mock_recon_svc):
    from routers.sync_system import router, get_recon_svc
    from routers.sync_deps import get_conn, get_read_conn, get_optional_config, require_config

    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_conn] = lambda: conn
    app.dependency_overrides[get_read_conn] = lambda: conn
    app.dependency_overrides[get_optional_config] = lambda: mock_config
    app.dependency_overrides[require_config] = lambda: mock_config
    app.dependency_overrides[get_recon_svc] = lambda: mock_recon_svc
    return TestClient(app)


class TestStatus:
    def test_configured(self, client, conn):
        from repositories.team_repo import TeamRepository

        TeamRepository().save(
            conn,
            Team(name="karma", leader_device_id="D1", leader_member_tag="j.m"),
        )
        resp = client.get("/sync/status")
        assert resp.status_code == 200
        data = resp.json()
        assert data["configured"] is True
        assert data["user_id"] == "jayant"
        assert data["member_tag"] == "jayant.macbook"
        team_names = [t["name"] for t in data["teams"]]
        assert "karma" in team_names

    def test_not_configured(self, conn):
        from routers.sync_system import router
        from routers.sync_deps import get_conn, get_read_conn, get_optional_config

        app = FastAPI()
        app.include_router(router)
        app.dependency_overrides[get_conn] = lambda: conn
        app.dependency_overrides[get_read_conn] = lambda: conn
        app.dependency_overrides[get_optional_config] = lambda: None

        c = TestClient(app)
        resp = c.get("/sync/status")
        assert resp.status_code == 200
        assert resp.json() == {"configured": False}


class TestReconcile:
    def test_ok(self, client, mock_recon_svc):
        resp = client.post("/sync/reconcile")
        assert resp.status_code == 200
        assert resp.json()["ok"] is True
        mock_recon_svc.run_cycle.assert_called_once()

    def test_failure_returns_500(self, client, mock_recon_svc):
        mock_recon_svc.run_cycle.side_effect = RuntimeError("boom")
        resp = client.post("/sync/reconcile")
        assert resp.status_code == 500
