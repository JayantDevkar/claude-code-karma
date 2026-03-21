"""Tests for sync_projects v4 router."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import sqlite3
from unittest.mock import MagicMock, AsyncMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from db.schema import ensure_schema
from domain.project import SharedProject, SharedProjectStatus
from domain.subscription import Subscription, SubscriptionStatus, SyncDirection
from domain.team import Team, AuthorizationError


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
    config.member_tag = "jayant.macbook"
    config.syncthing = MagicMock()
    config.syncthing.device_id = "DEV-SELF"
    return config


@pytest.fixture
def mock_project_svc():
    svc = MagicMock()
    svc.share_project = AsyncMock()
    svc.remove_project = AsyncMock()
    svc.accept_subscription = AsyncMock()
    svc.pause_subscription = AsyncMock()
    svc.resume_subscription = AsyncMock()
    svc.decline_subscription = AsyncMock()
    svc.change_direction = AsyncMock()
    return svc


@pytest.fixture
def client(conn, mock_config, mock_project_svc):
    from routers.sync_projects import router, get_project_svc
    from routers.sync_deps import get_conn, get_read_conn, require_config

    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_conn] = lambda: conn
    app.dependency_overrides[get_read_conn] = lambda: conn
    app.dependency_overrides[require_config] = lambda: mock_config
    app.dependency_overrides[get_project_svc] = lambda: mock_project_svc
    return TestClient(app)


class TestShareProject:
    def test_returns_201(self, client, mock_project_svc):
        mock_project_svc.share_project.return_value = SharedProject(
            team_name="karma",
            git_identity="jayantdevkar/claude-karma",
            folder_suffix="jayantdevkar-claude-karma",
        )
        resp = client.post(
            "/sync/teams/karma/projects",
            json={"git_identity": "jayantdevkar/claude-karma"},
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["git_identity"] == "jayantdevkar/claude-karma"
        assert data["folder_suffix"] == "jayantdevkar-claude-karma"
        mock_project_svc.share_project.assert_called_once()

    def test_auth_error_returns_403(self, client, mock_project_svc):
        mock_project_svc.share_project.side_effect = AuthorizationError("not leader")
        resp = client.post(
            "/sync/teams/karma/projects",
            json={"git_identity": "org/repo"},
        )
        assert resp.status_code == 403

    def test_missing_git_identity_returns_422(self, client):
        resp = client.post("/sync/teams/karma/projects", json={})
        assert resp.status_code == 422


class TestRemoveProject:
    def test_returns_200(self, client, mock_project_svc):
        mock_project_svc.remove_project.return_value = SharedProject(
            team_name="karma",
            git_identity="org/repo",
            folder_suffix="org-repo",
            status=SharedProjectStatus.REMOVED,
        )
        resp = client.delete("/sync/teams/karma/projects/org/repo")
        assert resp.status_code == 200
        assert resp.json()["ok"] is True
        assert resp.json()["status"] == "removed"

    def test_not_found_returns_404(self, client, mock_project_svc):
        mock_project_svc.remove_project.side_effect = ValueError("not found")
        resp = client.delete("/sync/teams/karma/projects/org/missing")
        assert resp.status_code == 404


class TestListProjects:
    def test_team_not_found(self, client):
        resp = client.get("/sync/teams/nonexistent/projects")
        assert resp.status_code == 404

    def test_returns_projects(self, client, conn):
        from repositories.team_repo import TeamRepository
        from repositories.project_repo import ProjectRepository

        TeamRepository().save(
            conn,
            Team(name="karma", leader_device_id="D", leader_member_tag="j.m"),
        )
        ProjectRepository().save(
            conn,
            SharedProject(
                team_name="karma",
                git_identity="org/repo",
                folder_suffix="org-repo",
            ),
        )
        resp = client.get("/sync/teams/karma/projects")
        assert resp.status_code == 200
        projects = resp.json()["projects"]
        assert len(projects) == 1
        assert projects[0]["git_identity"] == "org/repo"


class TestAcceptSubscription:
    def test_accept_with_direction(self, client, mock_project_svc):
        mock_project_svc.accept_subscription.return_value = Subscription(
            member_tag="jayant.macbook",
            team_name="karma",
            project_git_identity="org/repo",
            status=SubscriptionStatus.ACCEPTED,
            direction=SyncDirection.BOTH,
        )
        resp = client.post(
            "/sync/subscriptions/karma/org/repo/accept",
            json={"direction": "both"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "accepted"
        assert data["direction"] == "both"

    def test_invalid_direction_returns_400(self, client):
        resp = client.post(
            "/sync/subscriptions/karma/org/repo/accept",
            json={"direction": "invalid"},
        )
        assert resp.status_code == 400

    def test_not_found_returns_404(self, client, mock_project_svc):
        mock_project_svc.accept_subscription.side_effect = ValueError("not found")
        resp = client.post(
            "/sync/subscriptions/karma/org/repo/accept",
            json={"direction": "both"},
        )
        assert resp.status_code == 404


class TestPauseSubscription:
    def test_pause(self, client, mock_project_svc):
        mock_project_svc.pause_subscription.return_value = Subscription(
            member_tag="jayant.macbook",
            team_name="karma",
            project_git_identity="org/repo",
            status=SubscriptionStatus.PAUSED,
        )
        resp = client.post("/sync/subscriptions/karma/org/repo/pause")
        assert resp.status_code == 200
        assert resp.json()["status"] == "paused"


class TestResumeSubscription:
    def test_resume(self, client, mock_project_svc):
        mock_project_svc.resume_subscription.return_value = Subscription(
            member_tag="jayant.macbook",
            team_name="karma",
            project_git_identity="org/repo",
            status=SubscriptionStatus.ACCEPTED,
            direction=SyncDirection.BOTH,
        )
        resp = client.post("/sync/subscriptions/karma/org/repo/resume")
        assert resp.status_code == 200
        assert resp.json()["status"] == "accepted"


class TestDeclineSubscription:
    def test_decline(self, client, mock_project_svc):
        mock_project_svc.decline_subscription.return_value = Subscription(
            member_tag="jayant.macbook",
            team_name="karma",
            project_git_identity="org/repo",
            status=SubscriptionStatus.DECLINED,
        )
        resp = client.post("/sync/subscriptions/karma/org/repo/decline")
        assert resp.status_code == 200
        assert resp.json()["status"] == "declined"


class TestChangeDirection:
    def test_change(self, client, mock_project_svc):
        mock_project_svc.change_direction.return_value = Subscription(
            member_tag="jayant.macbook",
            team_name="karma",
            project_git_identity="org/repo",
            status=SubscriptionStatus.ACCEPTED,
            direction=SyncDirection.RECEIVE,
        )
        resp = client.patch(
            "/sync/subscriptions/karma/org/repo/direction",
            json={"direction": "receive"},
        )
        assert resp.status_code == 200
        assert resp.json()["direction"] == "receive"

    def test_invalid_direction_returns_400(self, client):
        resp = client.patch(
            "/sync/subscriptions/karma/org/repo/direction",
            json={"direction": "bad"},
        )
        assert resp.status_code == 400


class TestListSubscriptions:
    def test_returns_subs(self, client, conn):
        from repositories.team_repo import TeamRepository
        from repositories.member_repo import MemberRepository
        from repositories.project_repo import ProjectRepository
        from repositories.subscription_repo import SubscriptionRepository
        from domain.member import Member, MemberStatus

        TeamRepository().save(
            conn,
            Team(name="karma", leader_device_id="D", leader_member_tag="jayant.macbook"),
        )
        MemberRepository().save(
            conn,
            Member(
                member_tag="jayant.macbook", team_name="karma",
                device_id="D", user_id="jayant", machine_tag="macbook",
                status=MemberStatus.ACTIVE,
            ),
        )
        ProjectRepository().save(
            conn,
            SharedProject(
                team_name="karma",
                git_identity="org/repo",
                folder_suffix="org-repo",
            ),
        )
        SubscriptionRepository().save(
            conn,
            Subscription(
                member_tag="jayant.macbook",
                team_name="karma",
                project_git_identity="org/repo",
            ),
        )
        resp = client.get("/sync/subscriptions")
        assert resp.status_code == 200
        subs = resp.json()["subscriptions"]
        assert len(subs) == 1
        assert subs[0]["status"] == "offered"
