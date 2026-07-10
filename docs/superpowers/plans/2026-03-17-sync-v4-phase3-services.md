# Sync v4 Phase 3: Business Logic — Services

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.
>
> **TDD SKILL:** Use `oh-my-claudecode:tdd` or `superpowers:test-driven-development` for every task.

**Goal:** Build the service layer that orchestrates domain models + repositories + Syncthing abstraction.

**Architecture:** Services are the only layer that combines domain models, repos, and Syncthing. Routers call services. Services call domain model methods for validation, repos for persistence, and Syncthing managers for P2P operations.

**Tech Stack:** Python 3.9+, Pydantic 2.x, SQLite, pytest, asyncio

**Spec:** `docs/superpowers/specs/2026-03-17-sync-v4-domain-models-design.md` (sections: Service Layer, Metadata Folder Structure, Session Packaging Integration, Cleanup Logic)

**Parent Plan:** `docs/superpowers/plans/2026-03-17-sync-v4-master.md`

**Depends on:** Phase 1 (domain + repos) + Phase 2 (Syncthing abstraction)

---

## Task Dependency Graph

```
Task 1 (MetadataService) ──→ Task 2 (TeamService)  ──→ Task 4 (ReconciliationService)
                          ──→ Task 3 (ProjectService) ──↗       │
                                                                 ▼
                                                        Task 5 (WatcherManager)
                                                                 │
                                                                 ▼
                                                        Task 6 (Integration)
```

---

### Task 1: MetadataService

**Files:**
- Create: `api/services/sync/metadata_service.py`
- Test: `api/tests/test_metadata_service.py`

**FIRST — other services depend on metadata read/write**

- [ ] **Step 1: Write failing tests**

```python
# api/tests/test_metadata_service.py
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import json
import pytest
from domain.team import Team
from domain.member import Member, MemberStatus
from domain.project import SharedProject
from domain.subscription import Subscription, SubscriptionStatus, SyncDirection
from services.sync.metadata_service import MetadataService


@pytest.fixture
def meta_base(tmp_path):
    return tmp_path / "karma-metadata"


@pytest.fixture
def service(meta_base):
    return MetadataService(meta_base=meta_base)


@pytest.fixture
def team():
    return Team(name="karma-team", leader_device_id="DEV-L", leader_member_tag="jayant.macbook")


@pytest.fixture
def leader():
    return Member(
        member_tag="jayant.macbook", team_name="karma-team",
        device_id="DEV-L", user_id="jayant", machine_tag="macbook",
        status=MemberStatus.ACTIVE,
    )


@pytest.fixture
def member():
    return Member(
        member_tag="ayush.laptop", team_name="karma-team",
        device_id="DEV-A", user_id="ayush", machine_tag="laptop",
        status=MemberStatus.ACTIVE,
    )


class TestWriteTeamState:
    def test_creates_team_json(self, service, team, leader):
        service.write_team_state(team, [leader])
        team_file = service._team_dir(team.name) / "team.json"
        assert team_file.exists()
        data = json.loads(team_file.read_text())
        assert data["name"] == "karma-team"
        assert data["created_by"] == "jayant.macbook"
        assert data["leader_device_id"] == "DEV-L"

    def test_creates_member_state_file(self, service, team, leader):
        service.write_team_state(team, [leader])
        member_file = service._team_dir(team.name) / "members" / "jayant.macbook.json"
        assert member_file.exists()
        data = json.loads(member_file.read_text())
        assert data["member_tag"] == "jayant.macbook"
        assert data["device_id"] == "DEV-L"


class TestWriteOwnState:
    def test_writes_projects_and_subscriptions(self, service, member):
        projects = [SharedProject(
            team_name="karma-team", git_identity="o/r", folder_suffix="o-r",
        )]
        subs = [Subscription(
            member_tag="ayush.laptop", team_name="karma-team",
            project_git_identity="o/r",
            status=SubscriptionStatus.ACCEPTED, direction=SyncDirection.BOTH,
        )]
        service.write_own_state("karma-team", "ayush.laptop", projects, subs)
        state_file = service._team_dir("karma-team") / "members" / "ayush.laptop.json"
        data = json.loads(state_file.read_text())
        assert len(data["projects"]) == 1
        assert data["projects"][0]["git_identity"] == "o/r"
        assert data["subscriptions"]["o/r"]["status"] == "accepted"
        assert data["subscriptions"]["o/r"]["direction"] == "both"


class TestWriteRemovalSignal:
    def test_creates_removal_file(self, service):
        service.write_removal_signal("karma-team", "ayush.laptop", removed_by="jayant.macbook")
        removal_file = service._team_dir("karma-team") / "removed" / "ayush.laptop.json"
        assert removal_file.exists()
        data = json.loads(removal_file.read_text())
        assert data["member_tag"] == "ayush.laptop"
        assert data["removed_by"] == "jayant.macbook"


class TestReadTeamMetadata:
    def test_reads_all_member_states(self, service, team, leader, member):
        service.write_team_state(team, [leader, member])
        states = service.read_team_metadata("karma-team")
        assert "jayant.macbook" in states
        assert "ayush.laptop" in states
        assert states["jayant.macbook"]["device_id"] == "DEV-L"

    def test_reads_removal_signals(self, service, team, leader):
        service.write_team_state(team, [leader])
        service.write_removal_signal("karma-team", "ayush.laptop", removed_by="jayant.macbook")
        states = service.read_team_metadata("karma-team")
        assert states.get("__removals", {}).get("ayush.laptop") is not None

    def test_empty_team_returns_empty(self, service):
        states = service.read_team_metadata("nonexistent")
        assert states == {}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd api && pytest tests/test_metadata_service.py -v`
Expected: FAIL

- [ ] **Step 3: Implement MetadataService**

```python
# api/services/sync/metadata_service.py
"""Metadata folder read/write for P2P team state synchronization.

Each team has a metadata folder (karma-meta--{team}). Members write their
own state files. Leader writes team.json and removal signals.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from domain.member import Member
    from domain.project import SharedProject
    from domain.subscription import Subscription
    from domain.team import Team


class MetadataService:
    def __init__(self, meta_base: Path):
        self.meta_base = meta_base

    def _team_dir(self, team_name: str) -> Path:
        return self.meta_base / f"karma-meta--{team_name}"

    def write_team_state(self, team: "Team", members: list["Member"]) -> None:
        """Write team.json + member state files to metadata folder."""
        team_dir = self._team_dir(team.name)
        team_dir.mkdir(parents=True, exist_ok=True)
        (team_dir / "members").mkdir(exist_ok=True)
        (team_dir / "removed").mkdir(exist_ok=True)

        # Write team.json
        team_data = {
            "name": team.name,
            "created_by": team.leader_member_tag,
            "leader_device_id": team.leader_device_id,
            "created_at": team.created_at.isoformat(),
        }
        (team_dir / "team.json").write_text(json.dumps(team_data, indent=2))

        # Write member state files
        for member in members:
            member_data = {
                "member_tag": member.member_tag,
                "device_id": member.device_id,
                "user_id": member.user_id,
                "machine_tag": member.machine_tag,
                "status": member.status.value,
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }
            member_file = team_dir / "members" / f"{member.member_tag}.json"
            member_file.write_text(json.dumps(member_data, indent=2))

    def write_own_state(
        self,
        team_name: str,
        member_tag: str,
        projects: list["SharedProject"],
        subscriptions: list["Subscription"],
    ) -> None:
        """Write own member state with projects and subscriptions."""
        team_dir = self._team_dir(team_name)
        (team_dir / "members").mkdir(parents=True, exist_ok=True)

        projects_data = [
            {
                "git_identity": p.git_identity,
                "folder_suffix": p.folder_suffix,
            }
            for p in projects
        ]
        subs_data = {
            s.project_git_identity: {
                "status": s.status.value,
                "direction": s.direction.value,
            }
            for s in subscriptions
        }
        state = {
            "member_tag": member_tag,
            "projects": projects_data,
            "subscriptions": subs_data,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        state_file = team_dir / "members" / f"{member_tag}.json"
        state_file.write_text(json.dumps(state, indent=2))

    def write_removal_signal(
        self, team_name: str, member_tag: str, *, removed_by: str
    ) -> None:
        """Write removal signal to metadata folder."""
        team_dir = self._team_dir(team_name)
        (team_dir / "removed").mkdir(parents=True, exist_ok=True)

        removal_data = {
            "member_tag": member_tag,
            "removed_by": removed_by,
            "removed_at": datetime.now(timezone.utc).isoformat(),
        }
        removal_file = team_dir / "removed" / f"{member_tag}.json"
        removal_file.write_text(json.dumps(removal_data, indent=2))

    def read_team_metadata(self, team_name: str) -> dict[str, dict]:
        """Read all member states and removal signals from metadata folder.

        Returns dict keyed by member_tag. Special key '__removals' contains removal signals.
        """
        team_dir = self._team_dir(team_name)
        if not team_dir.exists():
            return {}

        result: dict[str, dict] = {}

        # Read member states
        members_dir = team_dir / "members"
        if members_dir.exists():
            for f in members_dir.glob("*.json"):
                try:
                    data = json.loads(f.read_text())
                    tag = data.get("member_tag", f.stem)
                    result[tag] = data
                except (json.JSONDecodeError, KeyError):
                    continue

        # Read removal signals
        removed_dir = team_dir / "removed"
        if removed_dir.exists():
            removals = {}
            for f in removed_dir.glob("*.json"):
                try:
                    data = json.loads(f.read_text())
                    tag = data.get("member_tag", f.stem)
                    removals[tag] = data
                except (json.JSONDecodeError, KeyError):
                    continue
            if removals:
                result["__removals"] = removals

        return result
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd api && pytest tests/test_metadata_service.py -v`
Expected: ALL PASS

- [ ] **Step 5: Commit**

```bash
git add api/services/sync/metadata_service.py api/tests/test_metadata_service.py
git commit -m "feat(sync-v4): add MetadataService — read/write team metadata folders"
```

---

### Task 2: TeamService

**Files:**
- Create: `api/services/sync/team_service.py`
- Test: `api/tests/test_team_service.py`

**CAN PARALLEL with Task 3. Depends on Task 1.**

- [ ] **Step 1: Write failing tests**

Tests use in-memory SQLite + mocked Syncthing managers. Key test scenarios:

```python
# api/tests/test_team_service.py
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import sqlite3
import pytest
from unittest.mock import MagicMock, AsyncMock
from db.schema import ensure_schema
from domain.team import Team, TeamStatus, AuthorizationError
from domain.member import Member, MemberStatus
from domain.subscription import SubscriptionStatus
from repositories.team_repo import TeamRepository
from repositories.member_repo import MemberRepository
from repositories.project_repo import ProjectRepository
from repositories.subscription_repo import SubscriptionRepository
from repositories.event_repo import EventRepository
from services.sync.team_service import TeamService


@pytest.fixture
def conn():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA foreign_keys=ON")
    ensure_schema(c)
    return c


@pytest.fixture
def mock_devices():
    m = MagicMock()
    m.pair = AsyncMock()
    m.unpair = AsyncMock()
    return m


@pytest.fixture
def mock_metadata(tmp_path):
    from services.sync.metadata_service import MetadataService
    return MetadataService(meta_base=tmp_path / "meta")


@pytest.fixture
def mock_folders():
    m = MagicMock()
    m.remove_device_from_team_folders = AsyncMock()
    m.cleanup_team_folders = AsyncMock()
    return m


@pytest.fixture
def service(conn, mock_devices, mock_metadata, mock_folders):
    return TeamService(
        teams=TeamRepository(),
        members=MemberRepository(),
        projects=ProjectRepository(),
        subs=SubscriptionRepository(),
        events=EventRepository(),
        devices=mock_devices,
        metadata=mock_metadata,
        folders=mock_folders,
    )


class TestCreateTeam:
    @pytest.mark.asyncio
    async def test_creates_team_and_leader(self, service, conn):
        team = await service.create_team(
            conn, name="karma", leader_member_tag="jayant.macbook", leader_device_id="DEV-L",
        )
        assert team.status == TeamStatus.ACTIVE
        assert team.leader_member_tag == "jayant.macbook"

        # Leader is auto-active
        leader = service.members.get(conn, "karma", "jayant.macbook")
        assert leader is not None
        assert leader.status == MemberStatus.ACTIVE

    @pytest.mark.asyncio
    async def test_logs_team_created_event(self, service, conn):
        await service.create_team(
            conn, name="t", leader_member_tag="j.m", leader_device_id="D",
        )
        events = service.events.query(conn, team="t")
        assert any(e.event_type.value == "team_created" for e in events)


class TestAddMember:
    @pytest.mark.asyncio
    async def test_adds_member_and_pairs(self, service, conn, mock_devices):
        await service.create_team(
            conn, name="t", leader_member_tag="j.m", leader_device_id="DEV-L",
        )
        member = await service.add_member(
            conn, team_name="t", by_device="DEV-L",
            new_member_tag="a.l", new_device_id="DEV-A",
        )
        assert member.status == MemberStatus.ADDED
        mock_devices.pair.assert_called_once_with("DEV-A")

    @pytest.mark.asyncio
    async def test_creates_offered_subscriptions(self, service, conn):
        await service.create_team(
            conn, name="t", leader_member_tag="j.m", leader_device_id="DEV-L",
        )
        # Share a project first
        from domain.project import SharedProject
        project = SharedProject(team_name="t", git_identity="o/r", folder_suffix="o-r")
        service.projects.save(conn, project)

        await service.add_member(
            conn, team_name="t", by_device="DEV-L",
            new_member_tag="a.l", new_device_id="DEV-A",
        )
        subs = service.subs.list_for_member(conn, "a.l")
        assert len(subs) == 1
        assert subs[0].status == SubscriptionStatus.OFFERED

    @pytest.mark.asyncio
    async def test_non_leader_cannot_add(self, service, conn):
        await service.create_team(
            conn, name="t", leader_member_tag="j.m", leader_device_id="DEV-L",
        )
        with pytest.raises(AuthorizationError):
            await service.add_member(
                conn, team_name="t", by_device="DEV-OTHER",
                new_member_tag="a.l", new_device_id="DEV-A",
            )


class TestRemoveMember:
    @pytest.mark.asyncio
    async def test_removes_and_records(self, service, conn):
        await service.create_team(
            conn, name="t", leader_member_tag="j.m", leader_device_id="DEV-L",
        )
        await service.add_member(
            conn, team_name="t", by_device="DEV-L",
            new_member_tag="a.l", new_device_id="DEV-A",
        )
        removed = await service.remove_member(
            conn, team_name="t", by_device="DEV-L", member_tag="a.l",
        )
        assert removed.status == MemberStatus.REMOVED
        assert service.members.was_removed(conn, "t", "DEV-A")


class TestDissolveTeam:
    @pytest.mark.asyncio
    async def test_dissolves_and_cleans_up(self, service, conn, mock_folders):
        await service.create_team(
            conn, name="t", leader_member_tag="j.m", leader_device_id="DEV-L",
        )
        dissolved = await service.dissolve_team(conn, team_name="t", by_device="DEV-L")
        assert dissolved.status == TeamStatus.DISSOLVED
        mock_folders.cleanup_team_folders.assert_called_once()
        # Team deleted from DB
        assert service.teams.get(conn, "t") is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd api && pytest tests/test_team_service.py -v`
Expected: FAIL

- [ ] **Step 3: Implement TeamService**

```python
# api/services/sync/team_service.py
"""TeamService — team lifecycle + member management orchestration."""
from __future__ import annotations

import sqlite3
from typing import TYPE_CHECKING

from domain.team import Team
from domain.member import Member, MemberStatus
from domain.subscription import Subscription
from domain.events import SyncEvent, SyncEventType

if TYPE_CHECKING:
    from repositories.team_repo import TeamRepository
    from repositories.member_repo import MemberRepository
    from repositories.project_repo import ProjectRepository
    from repositories.subscription_repo import SubscriptionRepository
    from repositories.event_repo import EventRepository
    from services.syncthing.device_manager import DeviceManager
    from services.syncthing.folder_manager import FolderManager
    from services.sync.metadata_service import MetadataService


class TeamService:
    def __init__(
        self,
        teams: "TeamRepository",
        members: "MemberRepository",
        projects: "ProjectRepository",
        subs: "SubscriptionRepository",
        events: "EventRepository",
        devices: "DeviceManager",
        metadata: "MetadataService",
        folders: "FolderManager",
    ):
        self.teams = teams
        self.members = members
        self.projects = projects
        self.subs = subs
        self.events = events
        self.devices = devices
        self.metadata = metadata
        self.folders = folders

    async def create_team(
        self,
        conn: sqlite3.Connection,
        *,
        name: str,
        leader_member_tag: str,
        leader_device_id: str,
    ) -> Team:
        team = Team(
            name=name,
            leader_device_id=leader_device_id,
            leader_member_tag=leader_member_tag,
        )
        # Parse member_tag
        user_id, machine_tag = leader_member_tag.split(".", 1)
        leader = Member(
            member_tag=leader_member_tag,
            team_name=name,
            device_id=leader_device_id,
            user_id=user_id,
            machine_tag=machine_tag,
            status=MemberStatus.ACTIVE,
        )
        self.teams.save(conn, team)
        self.members.save(conn, leader)
        self.metadata.write_team_state(team, [leader])
        self.events.log(conn, SyncEvent(
            event_type=SyncEventType.TEAM_CREATED, team_name=name,
        ))
        return team

    async def add_member(
        self,
        conn: sqlite3.Connection,
        *,
        team_name: str,
        by_device: str,
        new_member_tag: str,
        new_device_id: str,
    ) -> Member:
        team = self.teams.get(conn, team_name)
        if team is None:
            raise ValueError(f"Team '{team_name}' not found")

        member = Member.from_member_tag(
            member_tag=new_member_tag,
            team_name=team_name,
            device_id=new_device_id,
        )
        added = team.add_member(member, by_device=by_device)  # auth check
        self.members.save(conn, added)
        await self.devices.pair(new_device_id)

        # Write metadata
        all_members = self.members.list_for_team(conn, team_name)
        self.metadata.write_team_state(team, all_members)

        # Create OFFERED subscriptions for all shared projects
        projects = self.projects.list_for_team(conn, team_name)
        for project in projects:
            if project.status.value == "shared":
                sub = Subscription(
                    member_tag=new_member_tag,
                    team_name=team_name,
                    project_git_identity=project.git_identity,
                )
                self.subs.save(conn, sub)

        self.events.log(conn, SyncEvent(
            event_type=SyncEventType.MEMBER_ADDED,
            team_name=team_name,
            member_tag=new_member_tag,
            detail={"device_id": new_device_id, "added_by": team.leader_member_tag},
        ))
        return added

    async def remove_member(
        self,
        conn: sqlite3.Connection,
        *,
        team_name: str,
        by_device: str,
        member_tag: str,
    ) -> Member:
        team = self.teams.get(conn, team_name)
        if team is None:
            raise ValueError(f"Team '{team_name}' not found")

        member = self.members.get(conn, team_name, member_tag)
        if member is None:
            raise ValueError(f"Member '{member_tag}' not found in team '{team_name}'")

        removed = team.remove_member(member, by_device=by_device)  # auth check
        self.members.save(conn, removed)
        self.members.record_removal(conn, team_name, removed.device_id, member_tag=member_tag)

        # Write removal signal
        self.metadata.write_removal_signal(team_name, member_tag, removed_by=team.leader_member_tag)

        # Remove device from folder device lists
        projects = self.projects.list_for_team(conn, team_name)
        suffixes = [p.folder_suffix for p in projects if p.status.value == "shared"]
        members = self.members.list_for_team(conn, team_name)
        tags = [m.member_tag for m in members]
        await self.folders.remove_device_from_team_folders(suffixes, tags, removed.device_id)

        # Check cross-team: only unpair if device not in other teams
        other_memberships = self.members.get_by_device(conn, removed.device_id)
        active_others = [m for m in other_memberships if m.team_name != team_name and m.is_active]
        if not active_others:
            await self.devices.unpair(removed.device_id)

        self.events.log(conn, SyncEvent(
            event_type=SyncEventType.MEMBER_REMOVED,
            team_name=team_name,
            member_tag=member_tag,
            detail={"device_id": removed.device_id, "removed_by": team.leader_member_tag},
        ))
        return removed

    async def dissolve_team(
        self,
        conn: sqlite3.Connection,
        *,
        team_name: str,
        by_device: str,
    ) -> Team:
        team = self.teams.get(conn, team_name)
        if team is None:
            raise ValueError(f"Team '{team_name}' not found")

        dissolved = team.dissolve(by_device=by_device)  # auth check

        # Cleanup Syncthing folders
        projects = self.projects.list_for_team(conn, team_name)
        members = self.members.list_for_team(conn, team_name)
        suffixes = [p.folder_suffix for p in projects]
        tags = [m.member_tag for m in members]
        await self.folders.cleanup_team_folders(suffixes, tags, team_name)

        # Delete team (CASCADE handles members, projects, subs)
        self.teams.delete(conn, team_name)

        self.events.log(conn, SyncEvent(
            event_type=SyncEventType.TEAM_DISSOLVED, team_name=team_name,
        ))
        return dissolved
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd api && pytest tests/test_team_service.py -v`
Expected: ALL PASS

- [ ] **Step 5: Commit**

```bash
git add api/services/sync/team_service.py api/tests/test_team_service.py
git commit -m "feat(sync-v4): add TeamService — team lifecycle + member management"
```

---

### Task 3: ProjectService

**Files:**
- Create: `api/services/sync/project_service.py`
- Test: `api/tests/test_project_service.py`

**CAN PARALLEL with Task 2. Depends on Task 1.**

- [ ] **Step 1: Write failing tests**

Key test scenarios:

```python
# api/tests/test_project_service.py
# Follow same fixture pattern as test_team_service.py

class TestShareProject:
    @pytest.mark.asyncio
    async def test_shares_project_and_creates_subscriptions(self, service, conn):
        # Setup: create team + add member first
        # Share project → SharedProject(SHARED) + Subscription(OFFERED) for each member

    @pytest.mark.asyncio
    async def test_non_leader_cannot_share(self, service, conn):
        # AuthorizationError

    @pytest.mark.asyncio
    async def test_requires_git_identity(self, service, conn):
        # ValueError if git_identity missing


class TestAcceptSubscription:
    @pytest.mark.asyncio
    async def test_accept_with_both_direction(self, service, conn):
        # sub OFFERED → ACCEPTED, direction=BOTH
        # FolderManager.ensure_outbox_folder called
        # FolderManager.ensure_inbox_folders called

    @pytest.mark.asyncio
    async def test_accept_receive_only(self, service, conn):
        # No outbox folder created, only inbox


class TestPauseResumeDecline:
    @pytest.mark.asyncio
    async def test_pause_subscription(self, service, conn):
        # ACCEPTED → PAUSED

    @pytest.mark.asyncio
    async def test_resume_subscription(self, service, conn):
        # PAUSED → ACCEPTED

    @pytest.mark.asyncio
    async def test_decline_subscription(self, service, conn):
        # any → DECLINED


class TestChangeDirection:
    @pytest.mark.asyncio
    async def test_change_to_receive_removes_outbox(self, service, conn):
        # direction BOTH → RECEIVE, FolderManager.remove_outbox_folder called

    @pytest.mark.asyncio
    async def test_change_to_send_only(self, service, conn):
        # direction BOTH → SEND


class TestRemoveProject:
    @pytest.mark.asyncio
    async def test_removes_project_and_declines_all_subs(self, service, conn):
        # SharedProject → REMOVED, all subs → DECLINED
        # FolderManager.cleanup_project_folders called
```

- [ ] **Step 2: Run tests to verify they fail**

- [ ] **Step 3: Implement ProjectService**

```python
# api/services/sync/project_service.py
"""ProjectService — project sharing + subscription management."""
from __future__ import annotations

import sqlite3
from typing import TYPE_CHECKING

from domain.project import SharedProject, derive_folder_suffix
from domain.subscription import Subscription, SyncDirection
from domain.events import SyncEvent, SyncEventType
from domain.team import AuthorizationError

if TYPE_CHECKING:
    from repositories.project_repo import ProjectRepository
    from repositories.subscription_repo import SubscriptionRepository
    from repositories.member_repo import MemberRepository
    from repositories.team_repo import TeamRepository
    from repositories.event_repo import EventRepository
    from services.syncthing.folder_manager import FolderManager
    from services.sync.metadata_service import MetadataService


class ProjectService:
    def __init__(self, projects, subs, members, teams, folders, metadata, events):
        self.projects = projects
        self.subs = subs
        self.members = members
        self.teams = teams
        self.folders = folders
        self.metadata = metadata
        self.events = events

    async def share_project(
        self, conn, *, team_name, by_device, git_identity, encoded_name=None,
    ) -> SharedProject:
        team = self.teams.get(conn, team_name)
        if not team or not team.is_leader(by_device):
            raise AuthorizationError("Only leader can share projects")
        if not git_identity:
            raise ValueError("git_identity is required (git-only projects)")

        project = SharedProject(
            team_name=team_name,
            git_identity=git_identity,
            encoded_name=encoded_name,
            folder_suffix=derive_folder_suffix(git_identity),
        )
        self.projects.save(conn, project)

        # Create OFFERED subscription for each active non-leader member
        for member in self.members.list_for_team(conn, team_name):
            if member.is_active and not team.is_leader(member.device_id):
                sub = Subscription(
                    member_tag=member.member_tag,
                    team_name=team_name,
                    project_git_identity=git_identity,
                )
                self.subs.save(conn, sub)

        # Create leader's outbox if they have the repo
        if encoded_name:
            await self.folders.ensure_outbox_folder(
                team.leader_member_tag, project.folder_suffix,
            )

        self.events.log(conn, SyncEvent(
            event_type=SyncEventType.PROJECT_SHARED,
            team_name=team_name,
            project_git_identity=git_identity,
        ))
        return project

    async def accept_subscription(
        self, conn, *, member_tag, team_name, git_identity, direction=SyncDirection.BOTH,
    ) -> Subscription:
        sub = self.subs.get(conn, member_tag, team_name, git_identity)
        if sub is None:
            raise ValueError("Subscription not found")

        accepted = sub.accept(direction)
        self.subs.save(conn, accepted)
        await self._apply_sync_direction(conn, accepted)

        self.events.log(conn, SyncEvent(
            event_type=SyncEventType.SUBSCRIPTION_ACCEPTED,
            team_name=team_name, member_tag=member_tag,
            project_git_identity=git_identity,
            detail={"direction": direction.value},
        ))
        return accepted

    async def _apply_sync_direction(self, conn, sub: Subscription) -> None:
        project = self.projects.get(conn, sub.team_name, sub.project_git_identity)
        if not project:
            return
        if sub.direction in (SyncDirection.SEND, SyncDirection.BOTH):
            await self.folders.ensure_outbox_folder(sub.member_tag, project.folder_suffix)
        if sub.direction in (SyncDirection.RECEIVE, SyncDirection.BOTH):
            # Accept inbox from each teammate who sends
            members = self.members.list_for_team(conn, sub.team_name)
            for m in members:
                if m.member_tag != sub.member_tag and m.is_active:
                    await self.folders.ensure_inbox_folder(
                        m.member_tag, project.folder_suffix, m.device_id,
                    )

    async def pause_subscription(self, conn, *, member_tag, team_name, git_identity):
        sub = self.subs.get(conn, member_tag, team_name, git_identity)
        paused = sub.pause()
        self.subs.save(conn, paused)
        self.events.log(conn, SyncEvent(
            event_type=SyncEventType.SUBSCRIPTION_PAUSED,
            team_name=team_name, member_tag=member_tag,
            project_git_identity=git_identity,
        ))
        return paused

    async def resume_subscription(self, conn, *, member_tag, team_name, git_identity):
        sub = self.subs.get(conn, member_tag, team_name, git_identity)
        resumed = sub.resume()
        self.subs.save(conn, resumed)
        await self._apply_sync_direction(conn, resumed)
        self.events.log(conn, SyncEvent(
            event_type=SyncEventType.SUBSCRIPTION_RESUMED,
            team_name=team_name, member_tag=member_tag,
            project_git_identity=git_identity,
        ))
        return resumed

    async def decline_subscription(self, conn, *, member_tag, team_name, git_identity):
        sub = self.subs.get(conn, member_tag, team_name, git_identity)
        declined = sub.decline()
        self.subs.save(conn, declined)
        self.events.log(conn, SyncEvent(
            event_type=SyncEventType.SUBSCRIPTION_DECLINED,
            team_name=team_name, member_tag=member_tag,
            project_git_identity=git_identity,
        ))
        return declined

    async def change_direction(self, conn, *, member_tag, team_name, git_identity, direction):
        sub = self.subs.get(conn, member_tag, team_name, git_identity)
        old_direction = sub.direction
        changed = sub.change_direction(direction)
        self.subs.save(conn, changed)

        project = self.projects.get(conn, team_name, git_identity)
        # Remove outbox if no longer sending
        if old_direction in (SyncDirection.SEND, SyncDirection.BOTH) and direction == SyncDirection.RECEIVE:
            await self.folders.remove_outbox_folder(member_tag, project.folder_suffix)
        # Ensure outbox if now sending
        if direction in (SyncDirection.SEND, SyncDirection.BOTH) and old_direction == SyncDirection.RECEIVE:
            await self.folders.ensure_outbox_folder(member_tag, project.folder_suffix)

        self.events.log(conn, SyncEvent(
            event_type=SyncEventType.DIRECTION_CHANGED,
            team_name=team_name, member_tag=member_tag,
            project_git_identity=git_identity,
            detail={"old_direction": old_direction.value, "new_direction": direction.value},
        ))
        return changed

    async def remove_project(self, conn, *, team_name, by_device, git_identity):
        team = self.teams.get(conn, team_name)
        if not team or not team.is_leader(by_device):
            raise AuthorizationError("Only leader can remove projects")

        project = self.projects.get(conn, team_name, git_identity)
        if not project:
            raise ValueError("Project not found")

        removed = project.remove()
        self.projects.save(conn, removed)

        # Decline all subscriptions
        subs = self.subs.list_for_project(conn, team_name, git_identity)
        for sub in subs:
            if sub.status.value != "declined":
                self.subs.save(conn, sub.decline())

        # Cleanup folders
        members = self.members.list_for_team(conn, team_name)
        tags = [m.member_tag for m in members]
        await self.folders.cleanup_project_folders(project.folder_suffix, tags)

        self.events.log(conn, SyncEvent(
            event_type=SyncEventType.PROJECT_REMOVED,
            team_name=team_name, project_git_identity=git_identity,
        ))
        return removed
```

- [ ] **Step 4: Run tests, iterate, commit**

Run: `cd api && pytest tests/test_project_service.py -v`

```bash
git add api/services/sync/project_service.py api/tests/test_project_service.py
git commit -m "feat(sync-v4): add ProjectService — sharing + subscriptions"
```

---

### Task 4: ReconciliationService

**Files:**
- Create: `api/services/sync/reconciliation_service.py`
- Test: `api/tests/test_reconciliation_service.py`

**SEQUENTIAL — after Tasks 2+3**

- [ ] **Step 1: Write failing tests**

Key test scenarios:

```python
# api/tests/test_reconciliation_service.py

class TestPhaseMetadata:
    def test_detects_removal_signal_and_auto_leaves(self):
        # Write removal signal for own member_tag in metadata
        # Run phase_metadata → team deleted from local DB

    def test_discovers_new_member_from_metadata(self):
        # Write unknown member state to metadata
        # Run phase_metadata → member registered as ADDED

    def test_discovers_new_project_creates_offered_sub(self):
        # Leader's metadata has project not in local DB
        # Run phase_metadata → SharedProject created + Subscription(OFFERED)

    def test_detects_removed_project_declines_sub(self):
        # Local DB has project, leader's metadata doesn't
        # Run phase_metadata → Subscription DECLINED


class TestPhaseMeshPair:
    def test_pairs_with_unpaired_active_members(self):
        # Active member with device not paired
        # Run phase_mesh_pair → DeviceManager.ensure_paired called

    def test_skips_removed_members(self):
        # Removed member
        # Run phase_mesh_pair → ensure_paired NOT called


class TestPhaseDeviceLists:
    def test_computes_union_and_applies(self):
        # 2 accepted subs for same suffix
        # Run phase_device_lists → FolderManager.set_folder_devices with both devices

    def test_excludes_receive_only_from_outbox_device_list(self):
        # Member with direction=RECEIVE should not get their device in others' outbox folders
```

- [ ] **Step 2-4: Implement and test**

```python
# api/services/sync/reconciliation_service.py
"""3-phase reconciliation pipeline. Runs every 60s."""
from __future__ import annotations

import sqlite3
from typing import TYPE_CHECKING

from domain.member import Member, MemberStatus
from domain.subscription import Subscription, SubscriptionStatus, SyncDirection
from domain.events import SyncEvent, SyncEventType

if TYPE_CHECKING:
    from repositories.team_repo import TeamRepository
    from repositories.member_repo import MemberRepository
    from repositories.project_repo import ProjectRepository
    from repositories.subscription_repo import SubscriptionRepository
    from repositories.event_repo import EventRepository
    from services.syncthing.device_manager import DeviceManager
    from services.syncthing.folder_manager import FolderManager
    from services.sync.metadata_service import MetadataService


class ReconciliationService:
    def __init__(self, teams, members, projects, subs, events,
                 devices, folders, metadata, my_member_tag: str):
        self.teams = teams
        self.members = members
        self.projects = projects
        self.subs = subs
        self.events = events
        self.devices = devices
        self.folders = folders
        self.metadata = metadata
        self.my_member_tag = my_member_tag

    async def run_cycle(self, conn: sqlite3.Connection) -> None:
        """Run full 3-phase reconciliation for all teams."""
        for team in self.teams.list_all(conn):
            await self.phase_metadata(conn, team)
            await self.phase_mesh_pair(conn, team)
            await self.phase_device_lists(conn, team)

    async def phase_metadata(self, conn, team):
        """Phase 1: Read metadata, detect removals, discover members/projects."""
        states = self.metadata.read_team_metadata(team.name)
        if not states:
            return

        # Check removal signals
        removals = states.pop("__removals", {})
        if self.my_member_tag in removals:
            await self._auto_leave(conn, team)
            return

        # Discover new members
        for tag, state in states.items():
            existing = self.members.get(conn, team.name, tag)
            if existing is None and tag != self.my_member_tag:
                device_id = state.get("device_id")
                if device_id and not self.members.was_removed(conn, team.name, device_id):
                    new_member = Member.from_member_tag(
                        member_tag=tag, team_name=team.name, device_id=device_id,
                    )
                    activated = new_member.activate()
                    self.members.save(conn, activated)
            elif existing and existing.status == MemberStatus.ADDED:
                # Activate if we can see them in metadata (they've acknowledged)
                self.members.save(conn, existing.activate())

        # Discover/remove projects from leader's state
        leader_state = states.get(team.leader_member_tag, {})
        leader_projects = {p["git_identity"] for p in leader_state.get("projects", [])}
        local_projects = self.projects.list_for_team(conn, team.name)

        for lp in local_projects:
            if lp.git_identity not in leader_projects and lp.status.value == "shared":
                # Project removed by leader
                removed = lp.remove()
                self.projects.save(conn, removed)
                for sub in self.subs.list_for_project(conn, team.name, lp.git_identity):
                    if sub.status != SubscriptionStatus.DECLINED:
                        self.subs.save(conn, sub.decline())

    async def phase_mesh_pair(self, conn, team):
        """Phase 2: Pair with undiscovered team members."""
        members = self.members.list_for_team(conn, team.name)
        for member in members:
            if member.is_active and member.member_tag != self.my_member_tag:
                await self.devices.ensure_paired(member.device_id)

    async def phase_device_lists(self, conn, team):
        """Phase 3: Declarative device list sync for all project folders."""
        projects = self.projects.list_for_team(conn, team.name)
        for project in projects:
            if project.status.value != "shared":
                continue
            accepted = self.subs.list_accepted_for_suffix(conn, project.folder_suffix)
            # Devices that should have access: members with send|both direction
            desired = set()
            for sub in accepted:
                if sub.direction in (SyncDirection.SEND, SyncDirection.BOTH):
                    member = self.members.get(conn, sub.team_name, sub.member_tag)
                    if member and member.is_active:
                        desired.add(member.device_id)
            # Apply to all folders with this suffix
            # (both outbox and inbox folders for this project)
            from services.syncthing.folder_manager import build_outbox_folder_id
            members = self.members.list_for_team(conn, team.name)
            for m in members:
                folder_id = build_outbox_folder_id(m.member_tag, project.folder_suffix)
                await self.folders.set_folder_devices(folder_id, desired)

    async def _auto_leave(self, conn, team):
        """Clean up everything for this team on the local machine."""
        projects = self.projects.list_for_team(conn, team.name)
        members = self.members.list_for_team(conn, team.name)
        suffixes = [p.folder_suffix for p in projects]
        tags = [m.member_tag for m in members]
        await self.folders.cleanup_team_folders(suffixes, tags, team.name)

        # Unpair devices not in other teams
        for member in members:
            if member.member_tag == self.my_member_tag:
                continue
            others = self.members.get_by_device(conn, member.device_id)
            if len([o for o in others if o.team_name != team.name]) == 0:
                await self.devices.unpair(member.device_id)

        self.teams.delete(conn, team.name)
        self.events.log(conn, SyncEvent(
            event_type=SyncEventType.MEMBER_AUTO_LEFT, team_name=team.name,
        ))
```

- [ ] **Step 5: Commit**

```bash
git add api/services/sync/reconciliation_service.py api/tests/test_reconciliation_service.py
git commit -m "feat(sync-v4): add ReconciliationService — 3-phase pipeline"
```

---

### Task 5: WatcherManager Rewrite

**Files:**
- Modify: `api/services/watcher_manager.py` (rewrite sync-related portions)
- Test: `api/tests/test_watcher_manager_v4.py`

**SEQUENTIAL — after Task 4**

The WatcherManager runs the reconciliation service on a 60s timer and packages sessions based on subscriptions. Key changes from v3:
- Uses `ReconciliationService.run_cycle()` instead of 6 inline phases
- Session packaging gated by subscription direction (send|both only)
- Uses dedicated SQLite connection per timer thread (preserved from v3)

- [ ] **Step 1-5: Write tests, implement, commit**

Follow TDD pattern. Test that:
- Timer calls `reconciliation_service.run_cycle()` on tick
- Session packaging only runs for ACCEPTED subscriptions with send/both direction
- Thread-safe SQLite connection handling

```bash
git commit -m "feat(sync-v4): rewrite WatcherManager — uses ReconciliationService"
```

---

### Task 6: Phase 3 Integration Test

**Files:**
- Test: `api/tests/test_sync_v4_services.py`

**SEQUENTIAL — after all services**

- [ ] **Step 1: Write end-to-end service integration test**

Test the full flow: create team → add member → share project → accept subscription → run reconciliation → verify device lists.

Use in-memory SQLite + mocked Syncthing (DeviceManager, FolderManager). Verify domain model transitions, repo persistence, metadata file writes, and event logging all work together.

- [ ] **Step 2: Run and commit**

```bash
git add api/tests/test_sync_v4_services.py
git commit -m "test(sync-v4): add Phase 3 integration test — full service workflow"
```

---

## Phase 3 Completion Checklist

- [ ] MetadataService reads/writes team metadata folders
- [ ] TeamService handles create/add/remove/dissolve with auth
- [ ] ProjectService handles share/accept/pause/resume/decline/change-direction/remove
- [ ] ReconciliationService runs 3-phase pipeline
- [ ] WatcherManager rewritten to use ReconciliationService
- [ ] Integration test passes
- [ ] No regressions: `cd api && pytest -v`
