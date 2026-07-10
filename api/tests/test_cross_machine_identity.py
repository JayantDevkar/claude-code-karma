"""Regression tests for the two bugs found in the real two-machine walkthrough:
raw-URL identities at share time, and packaging resolving the LEADER's
encoded_name instead of the local machine's."""
import sqlite3
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

_api = Path(__file__).resolve().parent.parent
if str(_api) not in sys.path:
    sys.path.insert(0, str(_api))

from db.schema import ensure_schema


@pytest.fixture
def conn():
    c = sqlite3.connect(":memory:", check_same_thread=False)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA foreign_keys=ON")
    ensure_schema(c)
    return c


def _seed_team(conn, leader_device="DEV-L"):
    conn.execute(
        "INSERT INTO sync_teams (name, leader_device_id, leader_member_tag, team_id) "
        "VALUES ('crew', ?, 'lead.mac', 'tid')", (leader_device,))
    conn.execute(
        "INSERT INTO sync_members (team_name, member_tag, device_id, user_id, machine_tag, status) "
        "VALUES ('crew', 'lead.mac', 'DEV-L', 'lead', 'mac', 'active')")


@pytest.mark.asyncio
async def test_share_project_normalizes_raw_url(conn):
    from services.sync.project_service import ProjectService
    _seed_team(conn)
    svc = ProjectService(
        projects=__import__('repositories.project_repo', fromlist=['ProjectRepository']).ProjectRepository(),
        subs=__import__('repositories.subscription_repo', fromlist=['SubscriptionRepository']).SubscriptionRepository(),
        members=__import__('repositories.member_repo', fromlist=['MemberRepository']).MemberRepository(),
        teams=__import__('repositories.team_repo', fromlist=['TeamRepository']).TeamRepository(),
        folders=MagicMock(ensure_outbox_folder=AsyncMock()),
        metadata=MagicMock(),
        events=MagicMock(log=MagicMock()),
    )
    project = await svc.share_project(
        conn, team_name="crew", by_device="DEV-L",
        git_identity="https://github.com/Owner/Repo-Name.git",
    )
    assert project.git_identity == "owner/repo-name"
    assert ":" not in project.folder_suffix and "/" not in project.folder_suffix


def test_packaging_resolves_local_encoded_name(conn):
    """sync_projects carries the SHARER's encoded_name; packaging must prefer
    the local project index mapping for the same git identity."""
    from services.sync.packaging_service import PackagingService
    _seed_team(conn)
    conn.execute(
        "INSERT INTO sync_members (team_name, member_tag, device_id, user_id, machine_tag, status) "
        "VALUES ('crew', 'me.laptop', 'DEV-ME', 'me', 'laptop', 'active')")
    conn.execute(
        "INSERT INTO sync_projects (team_name, git_identity, encoded_name, folder_suffix) "
        "VALUES ('crew', 'owner/repo', '-Users-LEADER-path-repo', 'owner-repo')")
    conn.execute(
        "INSERT INTO sync_subscriptions (member_tag, team_name, project_git_identity, status, direction) "
        "VALUES ('me.laptop', 'crew', 'owner/repo', 'accepted', 'both')")
    # local index knows this identity under MY path
    conn.execute(
        "INSERT INTO projects (encoded_name, project_path, git_identity, jsonl_mtime) "
        "VALUES ('-Users-me-code-repo', '/Users/me/code/repo', 'owner/repo', 0)"
        if 'jsonl_mtime' in [r[1] for r in conn.execute("PRAGMA table_info(projects)")] else
        "INSERT INTO projects (encoded_name, project_path, git_identity) "
        "VALUES ('-Users-me-code-repo', '/Users/me/code/repo', 'owner/repo')")
    svc = PackagingService(member_tag="me.laptop", user_id="me", machine_id="laptop", device_id="DEV-ME")
    results = svc.resolve_packagable_projects(conn, team_name="crew")
    assert len(results) == 1
    assert results[0]["encoded_name"] == "-Users-me-code-repo", results[0]
