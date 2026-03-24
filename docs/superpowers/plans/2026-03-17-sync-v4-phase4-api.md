# Sync v4 Phase 4: API + Integration — Routers, Cleanup, E2E

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.
>
> **TDD SKILL:** Use `oh-my-claudecode:tdd` or `superpowers:test-driven-development` for every task.

**Goal:** Build thin FastAPI routers, delete old v3 files, and run end-to-end smoke tests.

**Architecture:** Routers validate input and delegate to services. No business logic in routers. 4 routers replace 7 from v3.

**Tech Stack:** FastAPI, pytest, httpx (TestClient)

**Spec:** `docs/superpowers/specs/2026-03-17-sync-v4-domain-models-design.md` (sections: API Endpoints, File Layout, Deleted Files)

**Parent Plan:** `docs/superpowers/plans/2026-03-17-sync-v4-master.md`

**Depends on:** Phase 3 (all services)

---

## Task Dependency Graph

```
Tasks 1-4 (Routers) ─── ALL PARALLEL ───→ Task 5 (Registration) → Task 6 (Delete old) → Task 7 (E2E)
```

---

### Task 1: sync_teams Router

**Files:**
- Rewrite: `api/routers/sync_teams.py`
- Test: `api/tests/api/test_sync_teams_router.py`

**CAN PARALLEL with Tasks 2-4**

- [ ] **Step 1: Write failing tests**

```python
# api/tests/api/test_sync_teams_router.py
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import sqlite3
import pytest
from unittest.mock import MagicMock, AsyncMock, patch
from fastapi.testclient import TestClient


@pytest.fixture
def mock_services():
    """Mock all service dependencies."""
    team_svc = MagicMock()
    team_svc.create_team = AsyncMock()
    team_svc.add_member = AsyncMock()
    team_svc.remove_member = AsyncMock()
    team_svc.dissolve_team = AsyncMock()
    return {"team_service": team_svc}


class TestCreateTeam:
    def test_create_team_returns_201(self, mock_services):
        from domain.team import Team
        mock_services["team_service"].create_team.return_value = Team(
            name="karma", leader_device_id="D", leader_member_tag="j.m",
        )
        # Test via TestClient against the router
        # Assert 201 status, response body has team name

    def test_create_team_missing_name_returns_422(self, mock_services):
        # Missing required field → 422


class TestListTeams:
    def test_list_returns_all_teams(self, mock_services):
        # GET /sync/teams → list of teams


class TestGetTeam:
    def test_get_team_returns_detail(self, mock_services):
        # GET /sync/teams/{name} → team with members, projects, subs

    def test_get_nonexistent_returns_404(self, mock_services):
        # 404


class TestAddMember:
    def test_add_member_with_pairing_code(self, mock_services):
        # POST /sync/teams/{name}/members { pairing_code: "..." }
        # PairingService.validate_code called
        # TeamService.add_member called

    def test_add_member_non_leader_returns_403(self, mock_services):
        # AuthorizationError → 403


class TestRemoveMember:
    def test_remove_member_returns_200(self, mock_services):
        # DELETE /sync/teams/{name}/members/{tag}

    def test_remove_non_leader_returns_403(self, mock_services):
        # 403


class TestDissolveTeam:
    def test_dissolve_returns_200(self, mock_services):
        # DELETE /sync/teams/{name}

    def test_dissolve_non_leader_returns_403(self, mock_services):
        # 403
```

- [ ] **Step 2: Run tests to verify they fail**

- [ ] **Step 3: Implement router**

```python
# api/routers/sync_teams.py
"""Sync Teams + Members router — thin delegation to TeamService."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from domain.team import AuthorizationError

router = APIRouter(prefix="/sync", tags=["sync-teams"])


# --- Request/Response schemas ---

class CreateTeamRequest(BaseModel):
    name: str

class AddMemberRequest(BaseModel):
    pairing_code: str

class TeamResponse(BaseModel):
    name: str
    leader_member_tag: str
    status: str
    created_at: str

class MemberResponse(BaseModel):
    member_tag: str
    device_id: str
    status: str
    connected: bool = False


# --- Endpoints ---

@router.post("/teams", status_code=201)
async def create_team(req: CreateTeamRequest):
    """Create a new team. Caller becomes the leader."""
    # Get identity from SyncConfig
    # Call team_service.create_team()
    # Return TeamResponse
    ...

@router.get("/teams")
async def list_teams():
    """List all teams."""
    ...

@router.get("/teams/{name}")
async def get_team(name: str):
    """Team detail with members, projects, subscriptions."""
    ...

@router.delete("/teams/{name}")
async def dissolve_team(name: str):
    """Dissolve a team. Leader only."""
    ...

@router.post("/teams/{name}/members")
async def add_member(name: str, req: AddMemberRequest):
    """Add member via pairing code. Leader only."""
    # PairingService.validate_code(req.pairing_code)
    # TeamService.add_member()
    ...

@router.delete("/teams/{name}/members/{tag}")
async def remove_member(name: str, tag: str):
    """Remove a member. Leader only."""
    ...

@router.get("/teams/{name}/members")
async def list_members(name: str):
    """List team members with connection status."""
    ...
```

- [ ] **Step 4: Run tests, iterate, commit**

```bash
git add api/routers/sync_teams.py api/tests/api/test_sync_teams_router.py
git commit -m "feat(sync-v4): rewrite sync_teams router — teams + members"
```

---

### Task 2: sync_projects Router

**Files:**
- Rewrite: `api/routers/sync_projects.py`
- Test: `api/tests/api/test_sync_projects_router.py`

**CAN PARALLEL with Tasks 1, 3-4**

Endpoints:
- `POST /sync/teams/{name}/projects` — share project
- `DELETE /sync/teams/{name}/projects/{git_identity}` — remove project
- `GET /sync/teams/{name}/projects` — list team projects
- `POST /sync/subscriptions/{team}/{project}/accept` — accept with direction
- `POST /sync/subscriptions/{team}/{project}/pause` — pause
- `POST /sync/subscriptions/{team}/{project}/resume` — resume
- `POST /sync/subscriptions/{team}/{project}/decline` — decline
- `PATCH /sync/subscriptions/{team}/{project}/direction` — change direction
- `GET /sync/subscriptions` — list my subscriptions

- [ ] **Step 1-4: Write tests, implement, commit**

Follow same pattern as Task 1. Router delegates to `ProjectService`.

```bash
git commit -m "feat(sync-v4): rewrite sync_projects router — sharing + subscriptions"
```

---

### Task 3: sync_pairing Router

**Files:**
- Create: `api/routers/sync_pairing.py`
- Test: `api/tests/api/test_sync_pairing_router.py`

**CAN PARALLEL with Tasks 1-2, 4**

Endpoints:
- `GET /sync/pairing/code` — generate my pairing code
- `POST /sync/pairing/validate` — validate a code (preview)
- `GET /sync/devices` — connected devices with status

- [ ] **Step 1-4: Write tests, implement, commit**

```bash
git commit -m "feat(sync-v4): add sync_pairing router — pairing codes + device status"
```

---

### Task 4: sync_system Router

**Files:**
- Simplify: `api/routers/sync_system.py`
- Test: `api/tests/api/test_sync_system_router.py`

**CAN PARALLEL with Tasks 1-3**

Endpoints:
- `GET /sync/status` — Syncthing running, version, device_id
- `POST /sync/initialize` — first-time setup
- `POST /sync/reconcile` — trigger manual reconciliation

- [ ] **Step 1-4: Write tests, implement, commit**

```bash
git commit -m "feat(sync-v4): simplify sync_system router"
```

---

### Task 5: Router Registration + Test Conftest

**Files:**
- Modify: `api/main.py` (register new routers, remove old)
- Create/Modify: `api/tests/api/conftest.py` (shared fixtures for router tests)

**SEQUENTIAL — after Tasks 1-4**

- [ ] **Step 1: Update main.py**

Remove old router imports:
```python
# DELETE these imports:
# from routers.sync_members import router as sync_members_router
# from routers.sync_pending import router as sync_pending_router
# from routers.sync_devices import router as sync_devices_router
# from routers.sync_operations import router as sync_operations_router

# KEEP/UPDATE these:
from routers.sync_teams import router as sync_teams_router
from routers.sync_projects import router as sync_projects_router
from routers.sync_pairing import router as sync_pairing_router
from routers.sync_system import router as sync_system_router
```

Register new routers, remove old `app.include_router()` calls.

- [ ] **Step 2: Create shared test conftest**

```python
# api/tests/api/conftest.py additions
@pytest.fixture
def mock_sync_config():
    """Mock SyncConfig for router tests."""
    config = MagicMock()
    config.user_id = "jayant"
    config.machine_tag = "macbook"
    config.member_tag = "jayant.macbook"
    config.syncthing_api_key = "test-key"
    config.syncthing_api_url = "http://localhost:8384"
    return config
```

- [ ] **Step 3: Verify all routers load**

Run: `cd api && python -c "from main import app; print('OK')"`
Expected: `OK`

- [ ] **Step 4: Commit**

```bash
git add api/main.py api/tests/api/conftest.py
git commit -m "feat(sync-v4): register v4 routers, remove v3 router imports"
```

---

### Task 6: Delete Old v3 Files

**SEQUENTIAL — after Task 5 (routers confirmed working)**

- [ ] **Step 1: Delete old router files**

```bash
cd api
rm -f routers/sync_members.py
rm -f routers/sync_pending.py
rm -f routers/sync_devices.py
rm -f routers/sync_operations.py
```

- [ ] **Step 2: Delete old service files**

```bash
rm -f services/sync_queries.py
rm -f services/sync_reconciliation.py
rm -f services/sync_folders.py
rm -f services/sync_metadata_reconciler.py
rm -f services/sync_metadata_writer.py
rm -f services/sync_identity.py
rm -f services/sync_policy.py
rm -f services/syncthing_proxy.py
rm -f db/sync_queries.py
```

- [ ] **Step 3: Delete old test files that test deleted code**

```bash
rm -f tests/test_sync_metadata_creation.py
rm -f tests/test_sync_settings_cleanup.py
rm -f tests/test_auto_share_folders.py
rm -f tests/test_sync_handshake_reconciliation.py
rm -f tests/test_phase4.py
rm -f tests/test_folder_id.py
rm -f tests/test_folder_id_v2.py
```

- [ ] **Step 4: Run full test suite to verify no import errors**

Run: `cd api && pytest -v`
Expected: ALL PASS (some old tests removed, new tests should all pass)

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "chore(sync-v4): delete v3 sync files — replaced by domain model architecture"
```

---

### Task 7: End-to-End Smoke Test

**Files:**
- Test: `api/tests/test_sync_v4_e2e.py`

**SEQUENTIAL — final task**

- [ ] **Step 1: Write E2E smoke test**

```python
# api/tests/test_sync_v4_e2e.py
"""End-to-end smoke test: full sync v4 stack from router to domain model."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import sqlite3
import pytest
from unittest.mock import MagicMock, AsyncMock
from db.schema import ensure_schema

# Import all layers to verify they connect
from domain.team import Team, TeamStatus
from domain.member import Member, MemberStatus
from domain.project import SharedProject, derive_folder_suffix
from domain.subscription import Subscription, SubscriptionStatus, SyncDirection
from domain.events import SyncEvent, SyncEventType
from repositories.team_repo import TeamRepository
from repositories.member_repo import MemberRepository
from repositories.project_repo import ProjectRepository
from repositories.subscription_repo import SubscriptionRepository
from repositories.event_repo import EventRepository
from services.sync.team_service import TeamService
from services.sync.project_service import ProjectService
from services.sync.pairing_service import PairingService
from services.sync.metadata_service import MetadataService
from services.sync.reconciliation_service import ReconciliationService


@pytest.fixture
def conn():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA foreign_keys=ON")
    ensure_schema(c)
    return c


@pytest.fixture
def meta_base(tmp_path):
    return tmp_path / "meta"


@pytest.fixture
def stack(conn, meta_base):
    """Build full service stack with mocked Syncthing."""
    devices = MagicMock()
    devices.pair = AsyncMock()
    devices.unpair = AsyncMock()
    devices.ensure_paired = AsyncMock()

    folders = MagicMock()
    folders.ensure_outbox_folder = AsyncMock()
    folders.ensure_inbox_folder = AsyncMock()
    folders.set_folder_devices = AsyncMock()
    folders.remove_outbox_folder = AsyncMock()
    folders.remove_device_from_team_folders = AsyncMock()
    folders.cleanup_team_folders = AsyncMock()
    folders.cleanup_project_folders = AsyncMock()

    repos = {
        "teams": TeamRepository(),
        "members": MemberRepository(),
        "projects": ProjectRepository(),
        "subs": SubscriptionRepository(),
        "events": EventRepository(),
    }
    metadata = MetadataService(meta_base=meta_base)

    team_svc = TeamService(
        **repos, devices=devices, metadata=metadata, folders=folders,
    )
    project_svc = ProjectService(
        **repos, folders=folders, metadata=metadata,
    )
    recon_svc = ReconciliationService(
        **repos, devices=devices, folders=folders,
        metadata=metadata, my_member_tag="jayant.macbook",
    )
    pairing_svc = PairingService()

    return {
        "team_svc": team_svc,
        "project_svc": project_svc,
        "recon_svc": recon_svc,
        "pairing_svc": pairing_svc,
        "devices": devices,
        "folders": folders,
        **repos,
    }


class TestFullE2EFlow:
    """Tests the complete user journey from spec Flow 1-5."""

    @pytest.mark.asyncio
    async def test_complete_sync_lifecycle(self, conn, stack):
        team_svc = stack["team_svc"]
        project_svc = stack["project_svc"]
        pairing_svc = stack["pairing_svc"]

        # Flow 1: Leader creates team
        team = await team_svc.create_team(
            conn, name="karma", leader_member_tag="jayant.macbook",
            leader_device_id="DEV-L",
        )
        assert team.status == TeamStatus.ACTIVE

        # Leader shares project
        project = await project_svc.share_project(
            conn, team_name="karma", by_device="DEV-L",
            git_identity="jayantdevkar/claude-karma",
            encoded_name="-Users-jayant-GitHub-claude-karma",
        )
        assert project.git_identity == "jayantdevkar/claude-karma"

        # Flow 2: Member generates pairing code, leader adds them
        code = pairing_svc.generate_code("ayush.laptop", "DEV-A")
        info = pairing_svc.validate_code(code)
        assert info.member_tag == "ayush.laptop"

        member = await team_svc.add_member(
            conn, team_name="karma", by_device="DEV-L",
            new_member_tag=info.member_tag, new_device_id=info.device_id,
        )
        assert member.status == MemberStatus.ADDED
        stack["devices"].pair.assert_called_with("DEV-A")

        # Verify subscription was auto-created
        subs = stack["subs"].list_for_member(conn, "ayush.laptop")
        assert len(subs) == 1
        assert subs[0].status == SubscriptionStatus.OFFERED

        # Flow 3: Member accepts project
        accepted = await project_svc.accept_subscription(
            conn, member_tag="ayush.laptop", team_name="karma",
            git_identity="jayantdevkar/claude-karma", direction=SyncDirection.BOTH,
        )
        assert accepted.status == SubscriptionStatus.ACCEPTED
        assert accepted.direction == SyncDirection.BOTH
        stack["folders"].ensure_outbox_folder.assert_called()
        stack["folders"].ensure_inbox_folder.assert_called()

        # Flow 5: Member changes to receive-only
        changed = await project_svc.change_direction(
            conn, member_tag="ayush.laptop", team_name="karma",
            git_identity="jayantdevkar/claude-karma",
            direction=SyncDirection.RECEIVE,
        )
        assert changed.direction == SyncDirection.RECEIVE
        stack["folders"].remove_outbox_folder.assert_called()

        # Flow 4: Leader removes member
        removed = await team_svc.remove_member(
            conn, team_name="karma", by_device="DEV-L", member_tag="ayush.laptop",
        )
        assert removed.status == MemberStatus.REMOVED

        # Verify events logged
        events = stack["events"].query(conn, team="karma")
        event_types = [e.event_type.value for e in events]
        assert "team_created" in event_types
        assert "project_shared" in event_types
        assert "member_added" in event_types
        assert "subscription_accepted" in event_types
        assert "direction_changed" in event_types
        assert "member_removed" in event_types
```

- [ ] **Step 2: Run E2E test**

Run: `cd api && pytest tests/test_sync_v4_e2e.py -v`
Expected: ALL PASS

- [ ] **Step 3: Run full test suite**

Run: `cd api && pytest -v`
Expected: ALL PASS

- [ ] **Step 4: Commit**

```bash
git add api/tests/test_sync_v4_e2e.py
git commit -m "test(sync-v4): add E2E smoke test — complete sync lifecycle"
```

---

## Phase 4 Completion Checklist

- [ ] 4 routers implemented (sync_teams, sync_projects, sync_pairing, sync_system)
- [ ] Routers registered in main.py
- [ ] Old v3 files deleted (13 files)
- [ ] Old v3 tests deleted
- [ ] E2E smoke test passes
- [ ] Full test suite passes: `cd api && pytest -v`
- [ ] All Phase 4 code committed

---

## v4 Implementation Complete Checklist

After all 4 phases:

- [ ] **Phase 1:** Domain models + schema v19 + repositories
- [ ] **Phase 2:** Syncthing client + device/folder managers + pairing service
- [ ] **Phase 3:** TeamService + ProjectService + MetadataService + ReconciliationService + WatcherManager
- [ ] **Phase 4:** Routers + cleanup + E2E test
- [ ] **Full test suite green:** `cd api && pytest -v`
- [ ] **No v3 sync code remains** (all replaced or deleted)
- [ ] **Code review passed:** Use `superpowers:requesting-code-review`
- [ ] **Ready for PR:** Use `commit-commands:commit-push-pr` to open PR against main
