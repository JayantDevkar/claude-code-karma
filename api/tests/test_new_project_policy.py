"""Tests for the new-project policy layer (prefs, auto-accept, accept-all, inbox)."""

from __future__ import annotations

import sqlite3
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

_api_dir = Path(__file__).resolve().parent.parent
if str(_api_dir) not in sys.path:
    sys.path.insert(0, str(_api_dir))

from db.schema import ensure_schema
from domain.subscription import Subscription, SubscriptionStatus, SyncDirection


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
    config.user_id = "ayush"
    config.machine_tag = "mba"
    config.member_tag = "ayush.mba"
    config.syncthing = MagicMock()
    config.syncthing.device_id = "DEV-SELF"
    config.syncthing.api_key = "test-key"
    return config


def _seed_team(conn, name="crew"):
    conn.execute(
        "INSERT INTO sync_teams (name, leader_device_id, leader_member_tag, team_id) "
        "VALUES (?, 'DEV-L', 'leader.mac', 'tid')",
        (name,),
    )
    conn.execute(
        "INSERT INTO sync_members (team_name, member_tag, device_id, user_id, machine_tag, status) "
        "VALUES (?, 'ayush.mba', 'DEV-SELF', 'ayush', 'mba', 'active')",
        (name,),
    )


def _seed_offered_sub(conn, team="crew", git_identity="org/repo", member="ayush.mba"):
    conn.execute(
        "INSERT INTO sync_projects (team_name, git_identity, folder_suffix) "
        "VALUES (?, ?, ?)",
        (team, git_identity, git_identity.replace("/", "-")),
    )
    conn.execute(
        "INSERT INTO sync_subscriptions (member_tag, team_name, project_git_identity, status) "
        "VALUES (?, ?, ?, 'offered')",
        (member, team, git_identity),
    )


# ---------------------------------------------------------------------------
# Prefs endpoints
# ---------------------------------------------------------------------------


@pytest.fixture
def teams_client(conn, mock_config):
    from routers.sync_teams import router
    from routers.sync_deps import get_conn, get_read_conn, require_config

    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_conn] = lambda: conn
    app.dependency_overrides[get_read_conn] = lambda: conn
    app.dependency_overrides[require_config] = lambda: mock_config
    return TestClient(app)


class TestTeamPrefs:
    def test_defaults_when_unset(self, teams_client):
        resp = teams_client.get("/sync/teams/crew/prefs")
        assert resp.status_code == 200
        assert resp.json() == {
            "new_project_policy": "ask",
            "default_direction": "both",
        }

    def test_put_then_get_roundtrip(self, teams_client):
        resp = teams_client.put(
            "/sync/teams/crew/prefs",
            json={"new_project_policy": "auto_accept", "default_direction": "send"},
        )
        assert resp.status_code == 200
        resp = teams_client.get("/sync/teams/crew/prefs")
        assert resp.json() == {
            "new_project_policy": "auto_accept",
            "default_direction": "send",
        }

    def test_partial_update_preserves_other_field(self, teams_client):
        teams_client.put(
            "/sync/teams/crew/prefs",
            json={"new_project_policy": "receive_only", "default_direction": "receive"},
        )
        teams_client.put(
            "/sync/teams/crew/prefs",
            json={"new_project_policy": "ask"},
        )
        resp = teams_client.get("/sync/teams/crew/prefs")
        assert resp.json() == {
            "new_project_policy": "ask",
            "default_direction": "receive",
        }

    def test_invalid_policy_rejected(self, teams_client):
        resp = teams_client.put(
            "/sync/teams/crew/prefs", json={"new_project_policy": "yolo"}
        )
        assert resp.status_code == 400

    def test_invalid_direction_rejected(self, teams_client):
        resp = teams_client.put(
            "/sync/teams/crew/prefs", json={"default_direction": "sideways"}
        )
        assert resp.status_code == 400


# ---------------------------------------------------------------------------
# Accept-all endpoint
# ---------------------------------------------------------------------------


@pytest.fixture
def projects_client(conn, mock_config):
    from routers.sync_projects import router, get_project_svc
    from routers.sync_deps import get_conn, get_read_conn, require_config

    svc = MagicMock()

    async def fake_accept(c, *, member_tag, team_name, git_identity, direction):
        sub = Subscription(
            member_tag=member_tag,
            team_name=team_name,
            project_git_identity=git_identity,
            status=SubscriptionStatus.ACCEPTED,
            direction=direction,
        )
        c.execute(
            "UPDATE sync_subscriptions SET status='accepted', direction=? "
            "WHERE member_tag=? AND team_name=? AND project_git_identity=?",
            (direction.value, member_tag, team_name, git_identity),
        )
        return sub

    svc.accept_subscription = AsyncMock(side_effect=fake_accept)

    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_conn] = lambda: conn
    app.dependency_overrides[get_read_conn] = lambda: conn
    app.dependency_overrides[require_config] = lambda: mock_config
    app.dependency_overrides[get_project_svc] = lambda: svc
    return TestClient(app), svc


class TestAcceptAll:
    def test_accepts_every_offered_sub(self, projects_client, conn):
        client, svc = projects_client
        _seed_team(conn)
        _seed_offered_sub(conn, git_identity="org/one")
        _seed_offered_sub(conn, git_identity="org/two")

        resp = client.post("/sync/subscriptions/crew/accept-all")
        assert resp.status_code == 200
        body = resp.json()
        assert len(body["accepted"]) == 2
        assert body["errors"] == []
        assert body["direction"] == "both"
        assert svc.accept_subscription.await_count == 2

    def test_direction_from_prefs(self, projects_client, conn):
        client, svc = projects_client
        _seed_team(conn)
        _seed_offered_sub(conn, git_identity="org/one")
        conn.execute(
            "INSERT INTO sync_team_prefs (team_name, new_project_policy, default_direction) "
            "VALUES ('crew', 'ask', 'receive')"
        )

        resp = client.post("/sync/subscriptions/crew/accept-all")
        assert resp.json()["direction"] == "receive"

    def test_explicit_direction_wins(self, projects_client, conn):
        client, svc = projects_client
        _seed_team(conn)
        _seed_offered_sub(conn, git_identity="org/one")

        resp = client.post(
            "/sync/subscriptions/crew/accept-all", json={"direction": "send"}
        )
        assert resp.json()["direction"] == "send"

    def test_skips_other_teams_and_states(self, projects_client, conn):
        client, svc = projects_client
        _seed_team(conn, "crew")
        _seed_team(conn, "other")
        _seed_offered_sub(conn, team="crew", git_identity="org/one")
        _seed_offered_sub(conn, team="other", git_identity="org/two")
        conn.execute(
            "UPDATE sync_subscriptions SET status='declined' "
            "WHERE project_git_identity='org/one'"
        )

        resp = client.post("/sync/subscriptions/crew/accept-all")
        assert resp.json()["accepted"] == []
        assert svc.accept_subscription.await_count == 0


# ---------------------------------------------------------------------------
# Reconciliation auto-accept policy
# ---------------------------------------------------------------------------


class TestApplyNewProjectPolicy:
    def _recon(self, conn):
        from repositories.event_repo import EventRepository
        from repositories.member_repo import MemberRepository
        from repositories.project_repo import ProjectRepository
        from repositories.subscription_repo import SubscriptionRepository
        from repositories.team_repo import TeamRepository
        from services.sync.reconciliation_service import ReconciliationService

        return ReconciliationService(
            teams=TeamRepository(),
            members=MemberRepository(),
            projects=ProjectRepository(),
            subs=SubscriptionRepository(),
            events=EventRepository(),
            devices=MagicMock(),
            folders=MagicMock(ensure_outbox_folder=AsyncMock(), ensure_inbox_folders=AsyncMock()),
            metadata=MagicMock(),
            my_member_tag="ayush.mba",
            my_device_id="DEV-SELF",
        )

    @pytest.mark.asyncio
    async def test_ask_policy_leaves_offered(self, conn):
        _seed_team(conn)
        _seed_offered_sub(conn)
        recon = self._recon(conn)
        await recon._apply_new_project_policy(conn, "crew", "org/repo")
        row = conn.execute(
            "SELECT status FROM sync_subscriptions WHERE project_git_identity='org/repo'"
        ).fetchone()
        assert row["status"] == "offered"

    @pytest.mark.asyncio
    async def test_no_prefs_row_leaves_offered(self, conn):
        _seed_team(conn)
        _seed_offered_sub(conn)
        recon = self._recon(conn)
        await recon._apply_new_project_policy(conn, "crew", "org/repo")
        row = conn.execute(
            "SELECT status FROM sync_subscriptions WHERE project_git_identity='org/repo'"
        ).fetchone()
        assert row["status"] == "offered"

    @pytest.mark.asyncio
    async def test_auto_accept_uses_default_direction(self, conn):
        _seed_team(conn)
        _seed_offered_sub(conn)
        conn.execute(
            "INSERT INTO sync_team_prefs (team_name, new_project_policy, default_direction) "
            "VALUES ('crew', 'auto_accept', 'send')"
        )
        recon = self._recon(conn)
        await recon._apply_new_project_policy(conn, "crew", "org/repo")
        row = conn.execute(
            "SELECT status, direction FROM sync_subscriptions "
            "WHERE project_git_identity='org/repo'"
        ).fetchone()
        assert row["status"] == "accepted"
        assert row["direction"] == "send"

    @pytest.mark.asyncio
    async def test_receive_only_forces_receive(self, conn):
        _seed_team(conn)
        _seed_offered_sub(conn)
        conn.execute(
            "INSERT INTO sync_team_prefs (team_name, new_project_policy, default_direction) "
            "VALUES ('crew', 'receive_only', 'both')"
        )
        recon = self._recon(conn)
        await recon._apply_new_project_policy(conn, "crew", "org/repo")
        row = conn.execute(
            "SELECT status, direction FROM sync_subscriptions "
            "WHERE project_git_identity='org/repo'"
        ).fetchone()
        assert row["status"] == "accepted"
        assert row["direction"] == "receive"

    @pytest.mark.asyncio
    async def test_accept_failure_leaves_offered(self, conn):
        _seed_team(conn)
        _seed_offered_sub(conn)
        conn.execute(
            "INSERT INTO sync_team_prefs (team_name, new_project_policy, default_direction) "
            "VALUES ('crew', 'auto_accept', 'both')"
        )
        recon = self._recon(conn)
        recon._project_service = MagicMock(side_effect=RuntimeError("boom"))
        # Must not raise — policy failures degrade to classic 'ask' behaviour
        await recon._apply_new_project_policy(conn, "crew", "org/repo")
        row = conn.execute(
            "SELECT status FROM sync_subscriptions WHERE project_git_identity='org/repo'"
        ).fetchone()
        assert row["status"] == "offered"
