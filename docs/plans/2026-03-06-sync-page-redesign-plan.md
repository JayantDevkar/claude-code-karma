# Sync Page Redesign — Full Web UI Control

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Replace the current partial sync page with a complete web UI that gives users full Syncthing control — from setup to team management to live sync — without ever touching the CLI.

**Architecture:** Three layers of changes: (1) New API endpoints in `api/routers/sync_status.py` and a new `api/services/watcher_manager.py` for in-process watcher management, (2) Updated frontend with onboarding wizard + 4-tab dashboard (Overview, Members, Projects, Activity), (3) New TypeScript types and server load functions. The CLI `karma` commands remain untouched — the web UI calls the same `SyncConfig` / `SyncthingClient` code via new API endpoints.

**Tech Stack:** Python/FastAPI (API), SvelteKit/Svelte 5 with runes (frontend), Pydantic (config models), existing `SyncthingClient` and `SessionWatcher`/`SessionPackager` from CLI.

---

## Phase 1: API — Team CRUD & Member Management

New endpoints that wrap the CLI's team/member/project logic into HTTP calls.

### Task 1: Team CRUD endpoints

**Files:**
- Modify: `api/routers/sync_status.py` (add new routes)
- Test: `api/tests/test_sync_team_crud.py` (create)

**Step 1: Write failing tests**

```python
# api/tests/test_sync_team_crud.py
"""Tests for sync team CRUD endpoints."""
from __future__ import annotations
import json
from unittest.mock import patch, MagicMock
import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def mock_sync_config(tmp_path, monkeypatch):
    """Provide a fresh SyncConfig for each test."""
    import sys
    cli_path = str(tmp_path / "cli")
    # Ensure karma.config is importable with tmp paths
    config_path = tmp_path / "sync-config.json"
    monkeypatch.setenv("KARMA_SYNC_CONFIG_PATH", str(config_path))
    monkeypatch.setenv("KARMA_BASE", str(tmp_path))
    return config_path


class TestCreateTeam:
    def test_create_team_success(self, mock_sync_config, tmp_path):
        """POST /sync/teams creates a new team in sync-config.json."""
        # Pre-create a valid config
        mock_sync_config.write_text(json.dumps({
            "user_id": "jayant",
            "machine_id": "mac",
            "teams": {},
            "syncthing": {"api_url": "http://127.0.0.1:8384"}
        }))

        from main import app
        client = TestClient(app)

        resp = client.post("/sync/teams", json={
            "name": "frontend-team",
            "backend": "syncthing"
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["ok"] is True
        assert data["name"] == "frontend-team"

        # Verify persisted
        saved = json.loads(mock_sync_config.read_text())
        assert "frontend-team" in saved["teams"]
        assert saved["teams"]["frontend-team"]["backend"] == "syncthing"

    def test_create_team_requires_init(self):
        """POST /sync/teams returns 400 if not initialized."""
        from main import app
        client = TestClient(app)
        # With no config file, should fail
        resp = client.post("/sync/teams", json={
            "name": "test", "backend": "syncthing"
        })
        assert resp.status_code == 400

    def test_create_team_invalid_name(self, mock_sync_config):
        """POST /sync/teams rejects invalid team names."""
        mock_sync_config.write_text(json.dumps({
            "user_id": "jayant", "teams": {},
            "syncthing": {"api_url": "http://127.0.0.1:8384"}
        }))
        from main import app
        client = TestClient(app)
        resp = client.post("/sync/teams", json={
            "name": "../evil", "backend": "syncthing"
        })
        assert resp.status_code == 400


class TestDeleteTeam:
    def test_delete_team_success(self, mock_sync_config):
        mock_sync_config.write_text(json.dumps({
            "user_id": "jayant",
            "teams": {"old-team": {"backend": "syncthing", "projects": {}}},
            "syncthing": {}
        }))
        from main import app
        client = TestClient(app)
        resp = client.delete("/sync/teams/old-team")
        assert resp.status_code == 200

    def test_delete_team_not_found(self, mock_sync_config):
        mock_sync_config.write_text(json.dumps({
            "user_id": "jayant", "teams": {}, "syncthing": {}
        }))
        from main import app
        client = TestClient(app)
        resp = client.delete("/sync/teams/nope")
        assert resp.status_code == 404
```

**Step 2: Run tests to verify they fail**

Run: `cd api && pytest tests/test_sync_team_crud.py -v`
Expected: FAIL — endpoints don't exist yet

**Step 3: Implement team CRUD endpoints**

Add to `api/routers/sync_status.py`:

```python
class CreateTeamRequest(BaseModel):
    name: str
    backend: str = "syncthing"


@router.post("/teams")
async def sync_create_team(req: CreateTeamRequest) -> Any:
    """Create a new sync group."""
    if not ALLOWED_PROJECT_NAME.match(req.name) or len(req.name) > 64:
        raise HTTPException(400, "Invalid team name")
    if req.backend not in ("syncthing", "ipfs"):
        raise HTTPException(400, "Invalid backend")

    config, SyncConfig, _ = await run_sync(_load_sync_config)
    if config is None:
        raise HTTPException(400, "Not initialized. Set up sync first.")

    if req.name in config.model_dump().get("teams", {}):
        raise HTTPException(409, f"Team '{req.name}' already exists")

    from karma.config import TeamConfig
    team_cfg = TeamConfig(backend=req.backend, projects={})
    teams = dict(config.teams)
    teams[req.name] = team_cfg
    updated = config.model_copy(update={"teams": teams})
    await run_sync(updated.save)

    return {"ok": True, "name": req.name, "backend": req.backend}


@router.delete("/teams/{team_name}")
async def sync_delete_team(team_name: str) -> Any:
    """Delete a sync group."""
    if not ALLOWED_PROJECT_NAME.match(team_name):
        raise HTTPException(400, "Invalid team name")

    config, _, _ = await run_sync(_load_sync_config)
    if config is None:
        raise HTTPException(400, "Not initialized")

    data = config.model_dump()
    if team_name not in data.get("teams", {}):
        raise HTTPException(404, f"Team '{team_name}' not found")

    teams = dict(config.teams)
    del teams[team_name]
    updated = config.model_copy(update={"teams": teams})
    await run_sync(updated.save)

    return {"ok": True, "name": team_name}
```

**Step 4: Run tests to verify they pass**

Run: `cd api && pytest tests/test_sync_team_crud.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add api/routers/sync_status.py api/tests/test_sync_team_crud.py
git commit -m "feat(api): add team CRUD endpoints — POST/DELETE /sync/teams"
```

---

### Task 2: Team member management endpoints

**Files:**
- Modify: `api/routers/sync_status.py`
- Modify: `api/services/syncthing_proxy.py` (add `auto_share_folders`, `accept_pending_folders`)
- Test: `api/tests/test_sync_members.py` (create)

**Step 1: Write failing tests**

```python
# api/tests/test_sync_members.py
"""Tests for sync team member management endpoints."""
from __future__ import annotations
import json
from unittest.mock import patch, MagicMock
import pytest
from fastapi.testclient import TestClient


def _base_config(tmp_path):
    return {
        "user_id": "jayant",
        "machine_id": "mac",
        "teams": {
            "my-team": {
                "backend": "syncthing",
                "projects": {},
                "syncthing_members": {},
                "ipfs_members": {},
            }
        },
        "syncthing": {
            "api_url": "http://127.0.0.1:8384",
            "api_key": "test-key",
            "device_id": "MY-DEVICE-ID",
        },
    }


class TestAddMember:
    def test_add_member_success(self, tmp_path, monkeypatch):
        config_path = tmp_path / "sync-config.json"
        config_path.write_text(json.dumps(_base_config(tmp_path)))
        monkeypatch.setenv("KARMA_SYNC_CONFIG_PATH", str(config_path))

        from main import app
        client = TestClient(app)

        with patch("services.syncthing_proxy.SyncthingClient") as mock_cls:
            mock_st = MagicMock()
            mock_st.is_running.return_value = True
            mock_st.add_device.return_value = None
            mock_st.get_pending_folders.return_value = {}
            mock_st._get_config.return_value = {"devices": [], "folders": []}
            mock_cls.return_value = mock_st

            resp = client.post("/sync/teams/my-team/members", json={
                "name": "alice",
                "device_id": "ALICE-DEVICE-ID-123"
            })

        assert resp.status_code == 200
        data = resp.json()
        assert data["ok"] is True
        assert data["name"] == "alice"

        # Verify persisted in config
        saved = json.loads(config_path.read_text())
        members = saved["teams"]["my-team"]["syncthing_members"]
        assert "alice" in members
        assert members["alice"]["syncthing_device_id"] == "ALICE-DEVICE-ID-123"

    def test_add_member_team_not_found(self, tmp_path, monkeypatch):
        config_path = tmp_path / "sync-config.json"
        config_path.write_text(json.dumps(_base_config(tmp_path)))
        monkeypatch.setenv("KARMA_SYNC_CONFIG_PATH", str(config_path))

        from main import app
        client = TestClient(app)
        resp = client.post("/sync/teams/nope/members", json={
            "name": "alice", "device_id": "AAAA"
        })
        assert resp.status_code == 404


class TestRemoveMember:
    def test_remove_member_success(self, tmp_path, monkeypatch):
        cfg = _base_config(tmp_path)
        cfg["teams"]["my-team"]["syncthing_members"]["alice"] = {
            "syncthing_device_id": "ALICE-ID"
        }
        config_path = tmp_path / "sync-config.json"
        config_path.write_text(json.dumps(cfg))
        monkeypatch.setenv("KARMA_SYNC_CONFIG_PATH", str(config_path))

        from main import app
        client = TestClient(app)

        with patch("services.syncthing_proxy.SyncthingClient") as mock_cls:
            mock_st = MagicMock()
            mock_st.is_running.return_value = True
            mock_cls.return_value = mock_st

            resp = client.delete("/sync/teams/my-team/members/alice")

        assert resp.status_code == 200
        saved = json.loads(config_path.read_text())
        assert "alice" not in saved["teams"]["my-team"]["syncthing_members"]

    def test_remove_member_not_found(self, tmp_path, monkeypatch):
        config_path = tmp_path / "sync-config.json"
        config_path.write_text(json.dumps(_base_config(tmp_path)))
        monkeypatch.setenv("KARMA_SYNC_CONFIG_PATH", str(config_path))

        from main import app
        client = TestClient(app)
        resp = client.delete("/sync/teams/my-team/members/ghost")
        assert resp.status_code == 404
```

**Step 2: Run tests — expect FAIL**

Run: `cd api && pytest tests/test_sync_members.py -v`

**Step 3: Implement member endpoints**

Add to `api/routers/sync_status.py`:

```python
class AddMemberRequest(BaseModel):
    name: str
    device_id: str


@router.post("/teams/{team_name}/members")
async def sync_add_member(team_name: str, req: AddMemberRequest) -> Any:
    """Add a member to a sync group.

    This does the full pipeline:
    1. Add to sync-config.json
    2. Pair device in Syncthing
    3. Auto-create shared folders for all team projects
    4. Auto-accept pending folder offers
    """
    if not ALLOWED_PROJECT_NAME.match(team_name):
        raise HTTPException(400, "Invalid team name")
    if not ALLOWED_PROJECT_NAME.match(req.name) or len(req.name) > 64:
        raise HTTPException(400, "Invalid member name")
    validate_device_id(req.device_id)

    config, _, _ = await run_sync(_load_sync_config)
    if config is None:
        raise HTTPException(400, "Not initialized")

    data = config.model_dump()
    if team_name not in data.get("teams", {}):
        raise HTTPException(404, f"Team '{team_name}' not found")

    from karma.config import TeamMemberSyncthing, TeamConfig

    team_cfg = config.teams[team_name]

    # 1. Add member to config
    syncthing_members = dict(team_cfg.syncthing_members)
    syncthing_members[req.name] = TeamMemberSyncthing(
        syncthing_device_id=req.device_id
    )
    teams = dict(config.teams)
    teams[team_name] = team_cfg.model_copy(
        update={"syncthing_members": syncthing_members}
    )
    updated = config.model_copy(update={"teams": teams})
    await run_sync(updated.save)

    # 2. Pair device in Syncthing
    paired = False
    try:
        proxy = get_proxy()
        await run_sync(proxy.add_device, req.device_id, req.name)
        paired = True
    except (SyncthingNotRunning, ValueError):
        pass

    # 3. Auto-share folders for existing projects
    shared_folders = 0
    try:
        if paired and team_cfg.projects:
            from karma.syncthing import SyncthingClient, read_local_api_key
            api_key = config.syncthing.api_key or await run_sync(read_local_api_key)
            st = SyncthingClient(api_key=api_key)
            if st.is_running():
                from karma.main import _auto_share_folders
                await run_sync(
                    _auto_share_folders,
                    st, config, team_cfg, teams, team_name, req.device_id
                )
                shared_folders = len(team_cfg.projects)
    except Exception:
        pass

    # 4. Auto-accept pending folder offers
    accepted = 0
    try:
        from karma.syncthing import SyncthingClient, read_local_api_key
        api_key = config.syncthing.api_key or await run_sync(read_local_api_key)
        st = SyncthingClient(api_key=api_key)
        if st.is_running():
            from karma.main import _accept_pending_folders
            accepted = await run_sync(_accept_pending_folders, st, updated)
    except Exception:
        pass

    return {
        "ok": True,
        "name": req.name,
        "device_id": req.device_id,
        "paired": paired,
        "shared_folders": shared_folders,
        "accepted_folders": accepted,
    }


@router.delete("/teams/{team_name}/members/{member_name}")
async def sync_remove_member(team_name: str, member_name: str) -> Any:
    """Remove a member from a sync group."""
    if not ALLOWED_PROJECT_NAME.match(team_name):
        raise HTTPException(400, "Invalid team name")
    if not ALLOWED_PROJECT_NAME.match(member_name):
        raise HTTPException(400, "Invalid member name")

    config, _, _ = await run_sync(_load_sync_config)
    if config is None:
        raise HTTPException(400, "Not initialized")

    data = config.model_dump()
    if team_name not in data.get("teams", {}):
        raise HTTPException(404, f"Team '{team_name}' not found")

    team_cfg = config.teams[team_name]
    if member_name not in team_cfg.syncthing_members:
        raise HTTPException(404, f"Member '{member_name}' not found")

    device_id = team_cfg.syncthing_members[member_name].syncthing_device_id

    # Remove from config
    members = dict(team_cfg.syncthing_members)
    del members[member_name]
    teams = dict(config.teams)
    teams[team_name] = team_cfg.model_copy(update={"syncthing_members": members})
    updated = config.model_copy(update={"teams": teams})
    await run_sync(updated.save)

    # Remove device from Syncthing
    try:
        proxy = get_proxy()
        await run_sync(proxy.remove_device, device_id)
    except (SyncthingNotRunning, Exception):
        pass

    return {"ok": True, "name": member_name}
```

**Step 4: Run tests — expect PASS**

Run: `cd api && pytest tests/test_sync_members.py -v`

**Step 5: Commit**

```bash
git add api/routers/sync_status.py api/tests/test_sync_members.py
git commit -m "feat(api): add team member endpoints — POST/DELETE /sync/teams/{name}/members"
```

---

### Task 3: Team project management endpoints

**Files:**
- Modify: `api/routers/sync_status.py`
- Test: `api/tests/test_sync_team_projects.py` (create)

**Step 1: Write failing tests**

```python
# api/tests/test_sync_team_projects.py
"""Tests for adding/removing projects to sync groups."""
from __future__ import annotations
import json
from unittest.mock import patch, MagicMock
import pytest
from fastapi.testclient import TestClient


def _base_config():
    return {
        "user_id": "jayant",
        "machine_id": "mac",
        "teams": {
            "my-team": {
                "backend": "syncthing",
                "projects": {},
                "syncthing_members": {
                    "alice": {"syncthing_device_id": "ALICE-ID"}
                },
                "ipfs_members": {},
            }
        },
        "syncthing": {
            "api_url": "http://127.0.0.1:8384",
            "api_key": "test-key",
            "device_id": "MY-DEVICE-ID",
        },
    }


class TestAddProjectToTeam:
    def test_add_project_success(self, tmp_path, monkeypatch):
        config_path = tmp_path / "sync-config.json"
        config_path.write_text(json.dumps(_base_config()))
        monkeypatch.setenv("KARMA_SYNC_CONFIG_PATH", str(config_path))

        from main import app
        client = TestClient(app)

        with patch("services.syncthing_proxy.SyncthingClient"):
            resp = client.post("/sync/teams/my-team/projects", json={
                "name": "claude-karma",
                "path": "/Users/jayant/Documents/GitHub/claude-karma"
            })

        assert resp.status_code == 200
        data = resp.json()
        assert data["ok"] is True
        assert data["encoded_name"].startswith("-")

        saved = json.loads(config_path.read_text())
        assert "claude-karma" in saved["teams"]["my-team"]["projects"]

    def test_add_project_team_not_found(self, tmp_path, monkeypatch):
        config_path = tmp_path / "sync-config.json"
        config_path.write_text(json.dumps(_base_config()))
        monkeypatch.setenv("KARMA_SYNC_CONFIG_PATH", str(config_path))

        from main import app
        client = TestClient(app)
        resp = client.post("/sync/teams/nope/projects", json={
            "name": "x", "path": "/tmp/x"
        })
        assert resp.status_code == 404


class TestRemoveProjectFromTeam:
    def test_remove_project_success(self, tmp_path, monkeypatch):
        cfg = _base_config()
        cfg["teams"]["my-team"]["projects"]["claude-karma"] = {
            "path": "/Users/jayant/GitHub/claude-karma",
            "encoded_name": "-Users-jayant-GitHub-claude-karma",
        }
        config_path = tmp_path / "sync-config.json"
        config_path.write_text(json.dumps(cfg))
        monkeypatch.setenv("KARMA_SYNC_CONFIG_PATH", str(config_path))

        from main import app
        client = TestClient(app)
        resp = client.delete("/sync/teams/my-team/projects/claude-karma")
        assert resp.status_code == 200

        saved = json.loads(config_path.read_text())
        assert "claude-karma" not in saved["teams"]["my-team"]["projects"]

    def test_remove_project_not_found(self, tmp_path, monkeypatch):
        config_path = tmp_path / "sync-config.json"
        config_path.write_text(json.dumps(_base_config()))
        monkeypatch.setenv("KARMA_SYNC_CONFIG_PATH", str(config_path))

        from main import app
        client = TestClient(app)
        resp = client.delete("/sync/teams/my-team/projects/nope")
        assert resp.status_code == 404
```

**Step 2: Run tests — expect FAIL**

Run: `cd api && pytest tests/test_sync_team_projects.py -v`

**Step 3: Implement**

Add to `api/routers/sync_status.py`:

```python
class AddTeamProjectRequest(BaseModel):
    name: str
    path: str


@router.post("/teams/{team_name}/projects")
async def sync_add_team_project(team_name: str, req: AddTeamProjectRequest) -> Any:
    """Add a project to a sync group.

    Creates outbox (sendonly) + inbox per member (receiveonly) in Syncthing.
    """
    validate_project_name(req.name)
    if not ALLOWED_PROJECT_NAME.match(team_name):
        raise HTTPException(400, "Invalid team name")

    config, _, _ = await run_sync(_load_sync_config)
    if config is None:
        raise HTTPException(400, "Not initialized")
    if team_name not in config.teams:
        raise HTTPException(404, f"Team '{team_name}' not found")

    from karma.sync import encode_project_path
    from karma.config import ProjectConfig, KARMA_BASE

    encoded = encode_project_path(req.path)
    project_config = ProjectConfig(path=req.path, encoded_name=encoded)

    team_cfg = config.teams[team_name]
    projects = dict(team_cfg.projects)
    projects[req.name] = project_config
    teams = dict(config.teams)
    teams[team_name] = team_cfg.model_copy(update={"projects": projects})
    updated = config.model_copy(update={"teams": teams})
    await run_sync(updated.save)

    # Auto-create Syncthing folders
    shared = 0
    try:
        if team_cfg.backend == "syncthing" and team_cfg.syncthing_members:
            from karma.syncthing import SyncthingClient, read_local_api_key
            api_key = config.syncthing.api_key or await run_sync(read_local_api_key)
            st = SyncthingClient(api_key=api_key)
            if st.is_running():
                from pathlib import Path
                # Outbox
                outbox_path = str(KARMA_BASE / "remote-sessions" / config.user_id / encoded)
                outbox_id = f"karma-out-{config.user_id}-{req.name}"
                device_ids = []
                if config.syncthing.device_id:
                    device_ids.append(config.syncthing.device_id)
                for m in team_cfg.syncthing_members.values():
                    device_ids.append(m.syncthing_device_id)
                Path(outbox_path).mkdir(parents=True, exist_ok=True)
                st.add_folder(outbox_id, outbox_path, device_ids, folder_type="sendonly")
                shared += 1

                # Inbox per member
                for mname, mcfg in team_cfg.syncthing_members.items():
                    inbox_path = str(KARMA_BASE / "remote-sessions" / mname / encoded)
                    inbox_id = f"karma-out-{mname}-{req.name}"
                    inbox_devices = [mcfg.syncthing_device_id]
                    if config.syncthing.device_id:
                        inbox_devices.append(config.syncthing.device_id)
                    Path(inbox_path).mkdir(parents=True, exist_ok=True)
                    st.add_folder(inbox_id, inbox_path, inbox_devices, folder_type="receiveonly")
                    shared += 1
    except Exception:
        pass

    return {
        "ok": True,
        "name": req.name,
        "encoded_name": encoded,
        "shared_folders_created": shared,
    }


@router.delete("/teams/{team_name}/projects/{project_name}")
async def sync_remove_team_project(team_name: str, project_name: str) -> Any:
    """Remove a project from a sync group."""
    validate_project_name(project_name)
    if not ALLOWED_PROJECT_NAME.match(team_name):
        raise HTTPException(400, "Invalid team name")

    config, _, _ = await run_sync(_load_sync_config)
    if config is None:
        raise HTTPException(400, "Not initialized")
    if team_name not in config.teams:
        raise HTTPException(404, f"Team '{team_name}' not found")

    team_cfg = config.teams[team_name]
    if project_name not in team_cfg.projects:
        raise HTTPException(404, f"Project '{project_name}' not found in team")

    projects = dict(team_cfg.projects)
    del projects[project_name]
    teams = dict(config.teams)
    teams[team_name] = team_cfg.model_copy(update={"projects": projects})
    updated = config.model_copy(update={"teams": teams})
    await run_sync(updated.save)

    return {"ok": True, "name": project_name}
```

**Step 4: Run tests — expect PASS**

Run: `cd api && pytest tests/test_sync_team_projects.py -v`

**Step 5: Commit**

```bash
git add api/routers/sync_status.py api/tests/test_sync_team_projects.py
git commit -m "feat(api): add team project endpoints — POST/DELETE /sync/teams/{name}/projects"
```

---

### Task 4: Watcher manager service + endpoints

**Files:**
- Create: `api/services/watcher_manager.py`
- Modify: `api/routers/sync_status.py` (add watch endpoints)
- Test: `api/tests/test_watcher_manager.py` (create)

**Step 1: Write failing tests**

```python
# api/tests/test_watcher_manager.py
"""Tests for the in-process watcher manager."""
from __future__ import annotations
import json
from unittest.mock import patch, MagicMock
import pytest


class TestWatcherManager:
    def test_start_creates_watchers(self, tmp_path, monkeypatch):
        from services.watcher_manager import WatcherManager

        # Create fake project dirs
        projects_dir = tmp_path / ".claude" / "projects"
        main_dir = projects_dir / "-Users-jay-karma"
        main_dir.mkdir(parents=True)

        config_data = {
            "user_id": "jay",
            "machine_id": "mac",
            "teams": {
                "my-team": {
                    "backend": "syncthing",
                    "projects": {
                        "karma": {
                            "path": "/Users/jay/karma",
                            "encoded_name": "-Users-jay-karma",
                        }
                    },
                    "syncthing_members": {},
                    "ipfs_members": {},
                }
            },
            "syncthing": {},
        }

        with patch("services.watcher_manager.Path.home", return_value=tmp_path):
            mgr = WatcherManager()
            result = mgr.start("my-team", config_data)

        assert result["running"] is True
        assert result["team"] == "my-team"
        assert mgr.is_running

    def test_stop_cleans_up(self, tmp_path):
        from services.watcher_manager import WatcherManager

        mgr = WatcherManager()
        mgr._running = True
        mgr._team = "test"
        mgr._watchers = [MagicMock(), MagicMock()]

        result = mgr.stop()
        assert result["running"] is False
        assert not mgr.is_running
        for w in mgr._watchers:
            w.stop.assert_called_once()

    def test_status_when_not_running(self):
        from services.watcher_manager import WatcherManager
        mgr = WatcherManager()
        status = mgr.status()
        assert status["running"] is False
        assert status["team"] is None

    def test_cannot_start_twice(self, tmp_path):
        from services.watcher_manager import WatcherManager
        mgr = WatcherManager()
        mgr._running = True
        mgr._team = "existing"

        with pytest.raises(ValueError, match="already running"):
            mgr.start("another", {})
```

**Step 2: Run tests — expect FAIL**

Run: `cd api && pytest tests/test_watcher_manager.py -v`

**Step 3: Implement WatcherManager**

```python
# api/services/watcher_manager.py
"""In-process session watcher manager.

Runs the same SessionWatcher + SessionPackager logic as `karma watch`,
but as a background service managed by the API process.
"""
from __future__ import annotations

import logging
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)

# Add CLI to path
_CLI_PATH = Path(__file__).parent.parent.parent / "cli"
if str(_CLI_PATH) not in sys.path:
    sys.path.insert(0, str(_CLI_PATH))


class WatcherManager:
    """Manages SessionWatcher instances for a single team."""

    def __init__(self) -> None:
        self._running = False
        self._team: Optional[str] = None
        self._watchers: list = []
        self._started_at: Optional[str] = None
        self._last_packaged_at: Optional[str] = None
        self._projects_watched: list[str] = []

    @property
    def is_running(self) -> bool:
        return self._running

    def status(self) -> dict[str, Any]:
        return {
            "running": self._running,
            "team": self._team,
            "started_at": self._started_at,
            "last_packaged_at": self._last_packaged_at,
            "projects_watched": self._projects_watched,
        }

    def start(self, team_name: str, config_data: dict) -> dict[str, Any]:
        """Start watchers for all projects in the given team."""
        if self._running:
            raise ValueError(f"Watcher already running for team '{self._team}'")

        from karma.watcher import SessionWatcher
        from karma.packager import SessionPackager
        from karma.worktree_discovery import find_worktree_dirs
        from karma.config import KARMA_BASE

        team_cfg = config_data.get("teams", {}).get(team_name, {})
        projects = team_cfg.get("projects", {})
        user_id = config_data.get("user_id", "unknown")
        machine_id = config_data.get("machine_id", "unknown")

        projects_dir = Path.home() / ".claude" / "projects"
        watchers = []
        watched = []

        for proj_name, proj in projects.items():
            encoded = proj.get("encoded_name", proj_name)
            claude_dir = projects_dir / encoded
            if not claude_dir.is_dir():
                logger.warning("Skipping %s: dir not found %s", proj_name, claude_dir)
                continue

            outbox = KARMA_BASE / "remote-sessions" / user_id / encoded

            def make_package_fn(
                cd=claude_dir, ob=outbox, en=encoded, pp=proj.get("path", "")
            ):
                def package():
                    wt_dirs = find_worktree_dirs(en, projects_dir)
                    packager = SessionPackager(
                        project_dir=cd,
                        user_id=user_id,
                        machine_id=machine_id,
                        project_path=pp,
                        extra_dirs=wt_dirs,
                    )
                    ob.mkdir(parents=True, exist_ok=True)
                    packager.package(staging_dir=ob)
                    self._last_packaged_at = (
                        datetime.now(timezone.utc).isoformat()
                    )
                return package

            watcher = SessionWatcher(
                watch_dir=claude_dir,
                package_fn=make_package_fn(),
            )
            watcher.start()
            watchers.append(watcher)
            watched.append(proj_name)

            # Also watch worktree dirs
            wt_dirs = find_worktree_dirs(encoded, projects_dir)
            for wt_dir in wt_dirs:
                wt_watcher = SessionWatcher(
                    watch_dir=wt_dir,
                    package_fn=make_package_fn(),
                )
                wt_watcher.start()
                watchers.append(wt_watcher)

        self._watchers = watchers
        self._running = True
        self._team = team_name
        self._started_at = datetime.now(timezone.utc).isoformat()
        self._projects_watched = watched

        logger.info(
            "Watcher started: team=%s, projects=%d, watchers=%d",
            team_name, len(watched), len(watchers),
        )
        return self.status()

    def stop(self) -> dict[str, Any]:
        """Stop all watchers."""
        for w in self._watchers:
            try:
                w.stop()
            except Exception as e:
                logger.warning("Error stopping watcher: %s", e)

        self._watchers = []
        self._running = False
        team = self._team
        self._team = None
        self._started_at = None
        self._projects_watched = []

        logger.info("Watcher stopped (was team=%s)", team)
        return self.status()
```

Add watch endpoints to `api/routers/sync_status.py`:

```python
from services.watcher_manager import WatcherManager

_watcher: WatcherManager | None = None

def get_watcher() -> WatcherManager:
    global _watcher
    if _watcher is None:
        _watcher = WatcherManager()
    return _watcher


@router.get("/watch/status")
async def sync_watch_status() -> Any:
    """Get watcher status."""
    return get_watcher().status()


@router.post("/watch/start")
async def sync_watch_start(team_name: str | None = None) -> Any:
    """Start the session watcher for a team."""
    config, _, _ = await run_sync(_load_sync_config)
    if config is None:
        raise HTTPException(400, "Not initialized")

    data = config.model_dump()
    teams = data.get("teams", {})

    # Auto-detect team if not specified
    if team_name is None:
        syncthing_teams = [n for n, t in teams.items() if t.get("backend") == "syncthing"]
        if len(syncthing_teams) == 1:
            team_name = syncthing_teams[0]
        elif len(syncthing_teams) == 0:
            raise HTTPException(400, "No syncthing teams configured")
        else:
            raise HTTPException(400, f"Multiple teams found. Specify team_name: {syncthing_teams}")

    if team_name not in teams:
        raise HTTPException(404, f"Team '{team_name}' not found")

    watcher = get_watcher()
    if watcher.is_running:
        raise HTTPException(409, "Watcher already running. Stop it first.")

    try:
        result = await run_sync(watcher.start, team_name, data)
        return result
    except Exception as e:
        raise HTTPException(500, f"Failed to start watcher: {e}")


@router.post("/watch/stop")
async def sync_watch_stop() -> Any:
    """Stop the session watcher."""
    watcher = get_watcher()
    if not watcher.is_running:
        return watcher.status()
    return await run_sync(watcher.stop)
```

**Step 4: Run tests — expect PASS**

Run: `cd api && pytest tests/test_watcher_manager.py -v`

**Step 5: Commit**

```bash
git add api/services/watcher_manager.py api/routers/sync_status.py api/tests/test_watcher_manager.py
git commit -m "feat(api): add watcher manager + /sync/watch endpoints"
```

---

### Task 5: Pending folders endpoint

**Files:**
- Modify: `api/routers/sync_status.py`
- Modify: `api/services/syncthing_proxy.py`
- Test: `api/tests/test_sync_pending.py` (create)

**Step 1: Write failing tests**

```python
# api/tests/test_sync_pending.py
"""Tests for pending folder endpoints."""
from __future__ import annotations
from unittest.mock import MagicMock, patch
import pytest
from services.syncthing_proxy import SyncthingNotRunning, SyncthingProxy


class TestGetPendingFolders:
    def test_returns_pending_from_known_members(self):
        mock_client = MagicMock()
        mock_client.get_pending_folders.return_value = {
            "karma-out-alice-myapp": {
                "offeredBy": {"ALICE-DEVICE-ID": {"time": "2026-03-06T00:00:00Z"}}
            }
        }

        proxy = SyncthingProxy.__new__(SyncthingProxy)
        proxy._client = mock_client

        result = proxy.get_pending_folders_for_ui(
            known_devices={"ALICE-DEVICE-ID": ("alice", "my-team")}
        )

        assert len(result) == 1
        assert result[0]["folder_id"] == "karma-out-alice-myapp"
        assert result[0]["from_member"] == "alice"

    def test_filters_unknown_devices(self):
        mock_client = MagicMock()
        mock_client.get_pending_folders.return_value = {
            "karma-evil": {
                "offeredBy": {"UNKNOWN-DEVICE": {"time": "2026-03-06T00:00:00Z"}}
            }
        }

        proxy = SyncthingProxy.__new__(SyncthingProxy)
        proxy._client = mock_client

        result = proxy.get_pending_folders_for_ui(known_devices={})
        assert len(result) == 0

    def test_filters_non_karma_prefix(self):
        mock_client = MagicMock()
        mock_client.get_pending_folders.return_value = {
            "photos-backup": {
                "offeredBy": {"ALICE-ID": {"time": "2026-03-06T00:00:00Z"}}
            }
        }

        proxy = SyncthingProxy.__new__(SyncthingProxy)
        proxy._client = mock_client

        result = proxy.get_pending_folders_for_ui(
            known_devices={"ALICE-ID": ("alice", "team")}
        )
        assert len(result) == 0
```

**Step 2: Run tests — expect FAIL**

Run: `cd api && pytest tests/test_sync_pending.py -v`

**Step 3: Implement**

Add to `api/services/syncthing_proxy.py`:

```python
def get_pending_folders_for_ui(
    self, known_devices: dict[str, tuple[str, str]]
) -> list[dict]:
    """Get pending folder offers filtered for known team members.

    Args:
        known_devices: {device_id: (member_name, team_name)}

    Returns:
        List of pending offers from known members with karma- prefix only.
    """
    client = self._require_client()
    pending = client.get_pending_folders()
    result = []

    for folder_id, info in pending.items():
        if not folder_id.startswith("karma-"):
            continue
        for device_id, offer in info.get("offeredBy", {}).items():
            if device_id not in known_devices:
                continue
            member_name, team_name = known_devices[device_id]
            result.append({
                "folder_id": folder_id,
                "from_device": device_id,
                "from_member": member_name,
                "from_team": team_name,
                "offered_at": offer.get("time"),
            })
    return result
```

Add to `api/routers/sync_status.py`:

```python
@router.get("/pending")
async def sync_pending() -> Any:
    """List pending folder offers from known team members."""
    config, _, _ = await run_sync(_load_sync_config)
    if config is None:
        return {"pending": []}

    # Build known devices lookup
    known: dict[str, tuple[str, str]] = {}
    for team_name, team_cfg in config.teams.items():
        for member_name, member_cfg in team_cfg.syncthing_members.items():
            known[member_cfg.syncthing_device_id] = (member_name, team_name)

    if not known:
        return {"pending": []}

    proxy = get_proxy()
    try:
        pending = await run_sync(proxy.get_pending_folders_for_ui, known)
        return {"pending": pending}
    except SyncthingNotRunning:
        return {"pending": []}


@router.post("/pending/accept")
async def sync_accept_pending() -> Any:
    """Accept all pending folder offers from known team members."""
    config, _, _ = await run_sync(_load_sync_config)
    if config is None:
        raise HTTPException(400, "Not initialized")

    try:
        from karma.syncthing import SyncthingClient, read_local_api_key
        api_key = config.syncthing.api_key or await run_sync(read_local_api_key)
        st = SyncthingClient(api_key=api_key)
        if not st.is_running():
            raise HTTPException(503, "Syncthing is not running")

        from karma.main import _accept_pending_folders
        accepted = await run_sync(_accept_pending_folders, st, config)
        return {"ok": True, "accepted": accepted}
    except SyncthingNotRunning:
        raise HTTPException(503, "Syncthing is not running")
```

**Step 4: Run tests — expect PASS**

Run: `cd api && pytest tests/test_sync_pending.py -v`

**Step 5: Commit**

```bash
git add api/services/syncthing_proxy.py api/routers/sync_status.py api/tests/test_sync_pending.py
git commit -m "feat(api): add pending folder endpoints — GET /sync/pending, POST /sync/pending/accept"
```

---

### Task 6: Project status endpoint (local/packaged/received counts)

**Files:**
- Modify: `api/routers/sync_status.py`
- Test: `api/tests/test_sync_project_status.py` (create)

**Step 1: Write failing tests**

```python
# api/tests/test_sync_project_status.py
"""Tests for per-project sync status endpoint."""
from __future__ import annotations
import json
from unittest.mock import patch
import pytest


class TestProjectStatus:
    def test_returns_counts(self, tmp_path, monkeypatch):
        """GET /sync/teams/{team}/project-status returns local/packaged/received counts."""
        config_path = tmp_path / "sync-config.json"
        config_path.write_text(json.dumps({
            "user_id": "jay",
            "machine_id": "mac",
            "teams": {
                "t1": {
                    "backend": "syncthing",
                    "projects": {
                        "karma": {
                            "path": "/Users/jay/karma",
                            "encoded_name": "-Users-jay-karma",
                        }
                    },
                    "syncthing_members": {
                        "alice": {"syncthing_device_id": "ALICE"}
                    },
                    "ipfs_members": {},
                }
            },
            "syncthing": {},
        }))
        monkeypatch.setenv("KARMA_SYNC_CONFIG_PATH", str(config_path))

        # Create fake dirs
        projects_dir = tmp_path / ".claude" / "projects"
        main_dir = projects_dir / "-Users-jay-karma"
        main_dir.mkdir(parents=True)
        (main_dir / "s1.jsonl").write_text('{"type":"user"}\n')
        (main_dir / "s2.jsonl").write_text('{"type":"user"}\n')

        outbox = tmp_path / "remote-sessions" / "jay" / "-Users-jay-karma" / "sessions"
        outbox.mkdir(parents=True)
        (outbox / "s1.jsonl").write_text('data')

        inbox = tmp_path / "remote-sessions" / "alice" / "-Users-jay-karma" / "sessions"
        inbox.mkdir(parents=True)
        (inbox / "a1.jsonl").write_text('data')
        (inbox / "a2.jsonl").write_text('data')

        from main import app
        from fastapi.testclient import TestClient
        client = TestClient(app)

        with patch("karma.main.Path.home", return_value=tmp_path), \
             patch("karma.config.KARMA_BASE", tmp_path):
            resp = client.get("/sync/teams/t1/project-status")

        assert resp.status_code == 200
        data = resp.json()
        assert len(data["projects"]) == 1
        p = data["projects"][0]
        assert p["name"] == "karma"
        assert p["local_count"] == 2
        assert p["packaged_count"] == 1
        assert p["received_counts"]["alice"] == 2
```

**Step 2: Run tests — FAIL. Step 3: Implement. Step 4: PASS.**

Add to `api/routers/sync_status.py`:

```python
@router.get("/teams/{team_name}/project-status")
async def sync_team_project_status(team_name: str) -> Any:
    """Get per-project sync status with local/packaged/received counts."""
    if not ALLOWED_PROJECT_NAME.match(team_name):
        raise HTTPException(400, "Invalid team name")

    config, _, _ = await run_sync(_load_sync_config)
    if config is None:
        raise HTTPException(400, "Not initialized")
    if team_name not in config.teams:
        raise HTTPException(404, f"Team '{team_name}' not found")

    from pathlib import Path as P
    from karma.config import KARMA_BASE
    from karma.worktree_discovery import find_worktree_dirs

    team_cfg = config.teams[team_name]
    projects_dir = P.home() / ".claude" / "projects"
    result = []

    for proj_name, proj in team_cfg.projects.items():
        encoded = proj.encoded_name
        claude_dir = projects_dir / encoded

        # Local sessions
        local_count = 0
        if claude_dir.is_dir():
            local_count = sum(
                1 for f in claude_dir.glob("*.jsonl")
                if not f.name.startswith("agent-") and f.stat().st_size > 0
            )
        # Worktree sessions
        wt_dirs = find_worktree_dirs(encoded, projects_dir)
        for wd in wt_dirs:
            local_count += sum(
                1 for f in wd.glob("*.jsonl")
                if not f.name.startswith("agent-") and f.stat().st_size > 0
            )

        # Packaged sessions (outbox)
        outbox = KARMA_BASE / "remote-sessions" / config.user_id / encoded / "sessions"
        packaged_count = 0
        if outbox.is_dir():
            packaged_count = sum(
                1 for f in outbox.glob("*.jsonl")
                if not f.name.startswith("agent-")
            )

        # Received per member
        received_counts = {}
        for mname in team_cfg.syncthing_members:
            inbox = KARMA_BASE / "remote-sessions" / mname / encoded / "sessions"
            if inbox.is_dir():
                received_counts[mname] = sum(
                    1 for f in inbox.glob("*.jsonl")
                    if not f.name.startswith("agent-")
                )
            else:
                received_counts[mname] = 0

        result.append({
            "name": proj_name,
            "encoded_name": encoded,
            "path": proj.path,
            "local_count": local_count,
            "packaged_count": packaged_count,
            "received_counts": received_counts,
            "gap": max(0, local_count - packaged_count),
        })

    return {"projects": result}
```

**Step 5: Commit**

```bash
git add api/routers/sync_status.py api/tests/test_sync_project_status.py
git commit -m "feat(api): add project status endpoint — GET /sync/teams/{name}/project-status"
```

---

## Phase 2: Frontend — Types & Server Load

### Task 7: Update TypeScript types

**Files:**
- Modify: `frontend/src/lib/api-types.ts`

**Step 1: Add new types**

Append to the Sync Types section of `frontend/src/lib/api-types.ts`:

```typescript
// --- New sync types for redesign ---

export interface SyncTeam {
    name: string;
    backend: 'syncthing' | 'ipfs';
    projects: SyncTeamProject[];
    members: SyncTeamMember[];
}

export interface SyncTeamProject {
    name: string;
    encoded_name: string;
    path: string;
    local_count: number;
    packaged_count: number;
    received_counts: Record<string, number>;
    gap: number;
}

export interface SyncTeamMember {
    name: string;
    device_id: string;
    connected: boolean;
    in_bytes_total: number;
    out_bytes_total: number;
}

export interface SyncWatchStatus {
    running: boolean;
    team: string | null;
    started_at: string | null;
    last_packaged_at: string | null;
    projects_watched: string[];
}

export interface SyncPendingFolder {
    folder_id: string;
    from_device: string;
    from_member: string;
    from_team: string;
    offered_at: string | null;
}
```

**Step 2: Commit**

```bash
git add frontend/src/lib/api-types.ts
git commit -m "feat(frontend): add TypeScript types for sync redesign"
```

---

## Phase 3: Frontend — Onboarding Wizard

### Task 8: Create SetupWizard component

**Files:**
- Create: `frontend/src/lib/components/sync/SetupWizard.svelte`
- Modify: `frontend/src/routes/sync/+page.svelte` (use wizard when not configured)

This is a 3-step wizard that replaces the current SetupTab for unconfigured users:

1. **Install Syncthing** — detect + install instructions (reuse existing SetupTab state 1)
2. **Name This Machine** — user_id + show device ID (reuse SetupTab state 2)
3. **Create/Join Group** — team creation with project selection

**Step 1: Create SetupWizard.svelte**

The wizard manages its own step state and calls the API at each transition:
- Step 1→2: Auto-advances when `detect.running` becomes true
- Step 2→3: `POST /sync/init` on "Continue"
- Step 3→done: `POST /sync/teams` + `POST /sync/teams/{name}/projects` (for each selected project) + `POST /sync/watch/start`

The wizard component accepts `detect`, `status`, and an `ondone` callback. It renders the 3 steps with a progress bar. Each step is self-contained with its own form state.

Key implementation details:
- Step 3 "Create Group" fetches `GET /projects` to show project list with checkboxes
- Step 3 "Join Existing" just shows the device ID for sharing — no API calls
- Step 3 "Solo Sync" is identical to "Create Group" but with different copy
- On completion, `ondone()` triggers the parent to refresh and switch to dashboard

**Step 2: Modify +page.svelte to conditionally render wizard vs dashboard**

Replace the current unconditional tab layout with:

```svelte
{#if !syncStatus?.configured}
    <SetupWizard bind:detect={syncDetect} bind:status={syncStatus} ondone={refreshData} />
{:else}
    <!-- Existing tab layout, modified for new tabs -->
{/if}
```

**Step 3: Commit**

```bash
git add frontend/src/lib/components/sync/SetupWizard.svelte frontend/src/routes/sync/+page.svelte
git commit -m "feat(frontend): add setup wizard for first-time sync configuration"
```

---

### Task 9: Create OverviewTab component

**Files:**
- Create: `frontend/src/lib/components/sync/OverviewTab.svelte`
- Modify: `frontend/src/routes/sync/+page.svelte` (add Overview tab)

**Key elements:**
1. **Sync Engine banner** — `GET /sync/watch/status` → show running/stopped with start/stop button
2. **Stats row** — members, projects, bandwidth (reuse pattern from current SetupTab state 3)
3. **Machine details** — user_id, device_id (copyable), version
4. **Pending actions** — `GET /sync/pending` → list with Accept/Ignore buttons

The banner is the most important element. It calls `POST /sync/watch/start` or `POST /sync/watch/stop`.

Pending actions call `POST /sync/pending/accept` on "Accept All".

**Step 1: Implement, Step 2: Commit**

```bash
git add frontend/src/lib/components/sync/OverviewTab.svelte frontend/src/routes/sync/+page.svelte
git commit -m "feat(frontend): add Overview tab with sync engine control + pending actions"
```

---

### Task 10: Create MembersTab component

**Files:**
- Create: `frontend/src/lib/components/sync/MembersTab.svelte`
- Modify: `frontend/src/routes/sync/+page.svelte` (replace Devices tab)

**Key elements:**
1. **Member list** — `GET /sync/teams` to get members, enriched with `GET /sync/devices` for connection status
2. **Add member form** — shows "Your Sync ID" + input for teammate's ID + name → `POST /sync/teams/{team}/members`
3. **Remove member** — confirm dialog → `DELETE /sync/teams/{team}/members/{name}`

Reuse `DeviceCard.svelte` for display (it already has expand/collapse, status, transfer stats). The key change is that "Add Member" now calls the team member endpoint instead of raw Syncthing device pairing.

**Step 1: Implement, Step 2: Commit**

```bash
git add frontend/src/lib/components/sync/MembersTab.svelte frontend/src/routes/sync/+page.svelte
git commit -m "feat(frontend): add Members tab with team member management"
```

---

### Task 11: Rewrite ProjectsTab for team-scoped projects

**Files:**
- Modify: `frontend/src/lib/components/sync/ProjectsTab.svelte`
- Modify: `frontend/src/lib/components/sync/ProjectRow.svelte`

**Key changes:**
1. "Enable Sync" → `POST /sync/teams/{team}/projects` (not flat `config.projects`)
2. "Disable" → `DELETE /sync/teams/{team}/projects/{name}`
3. Expanded row shows local/packaged/received counts from `GET /sync/teams/{team}/project-status`
4. Gap indicator: "3 behind — watcher needs to run" if packaged < local

**Step 1: Implement, Step 2: Commit**

```bash
git add frontend/src/lib/components/sync/ProjectsTab.svelte frontend/src/lib/components/sync/ProjectRow.svelte
git commit -m "feat(frontend): rewrite ProjectsTab for team-scoped project management"
```

---

### Task 12: Update +page.svelte tab layout

**Files:**
- Modify: `frontend/src/routes/sync/+page.svelte`
- Modify: `frontend/src/routes/sync/+page.server.ts`

**Key changes:**
1. Replace tabs: Setup → Overview, Devices → Members (keep Projects, Activity)
2. Default tab: `overview` when configured, wizard when not
3. Server load: add `GET /sync/watch/status` and `GET /sync/pending` to initial data
4. Remove old `SetupTab` import (replaced by wizard + overview)

**Step 1: Implement, Step 2: Commit**

```bash
git add frontend/src/routes/sync/+page.svelte frontend/src/routes/sync/+page.server.ts
git commit -m "feat(frontend): update sync page layout — wizard + overview/members/projects/activity"
```

---

## Phase 4: Cleanup & Polish

### Task 13: Remove dead code + update existing SetupTab

**Files:**
- Delete or repurpose: `frontend/src/lib/components/sync/SetupTab.svelte`
- Modify: `frontend/src/lib/components/sync/DevicesTab.svelte` (keep as sub-component or remove)

The old SetupTab and DevicesTab are replaced by SetupWizard, OverviewTab, and MembersTab. Either delete them or keep DevicesTab as a low-level component imported by MembersTab.

**Step 1: Remove unused imports, Step 2: Commit**

```bash
git add -A frontend/src/lib/components/sync/
git commit -m "refactor(frontend): remove old SetupTab, merge DevicesTab into MembersTab"
```

---

### Task 14: Run full test suite + type check

**Step 1: API tests**

```bash
cd api && pytest -v
```

Expected: All pass, including new test files.

**Step 2: Frontend type check**

```bash
cd frontend && npm run check
```

Expected: No errors.

**Step 3: Frontend lint**

```bash
cd frontend && npm run lint
```

Expected: Clean.

**Step 4: Final commit**

```bash
git add -A
git commit -m "chore: fix any remaining type/lint issues from sync redesign"
```

---

## Dependency Graph

```
Task 1 (Team CRUD) ─────────────┐
Task 2 (Members) ───────────────┤
Task 3 (Team Projects) ─────────┤──→ Task 7 (TS Types) ──→ Task 8 (Wizard)
Task 4 (Watcher Manager) ───────┤                          Task 9 (Overview)
Task 5 (Pending Folders) ───────┤                          Task 10 (Members UI)
Task 6 (Project Status) ────────┘                          Task 11 (Projects UI)
                                                           Task 12 (Page Layout)
                                                           Task 13 (Cleanup)
                                                           Task 14 (Full Tests)
```

Tasks 1-6 are independent of each other (all API-side). Task 7 depends on 1-6 being done. Tasks 8-12 depend on 7. Tasks 13-14 are final cleanup.

**Parallelizable:** Tasks 1-6 can all run in parallel. Tasks 8-11 can run in parallel after Task 7.

---

## Files Changed Summary

| File | Action | Task |
|---|---|---|
| `api/routers/sync_status.py` | Modify (add ~200 lines) | 1,2,3,4,5,6 |
| `api/services/watcher_manager.py` | Create (~120 lines) | 4 |
| `api/services/syncthing_proxy.py` | Modify (add ~30 lines) | 5 |
| `api/tests/test_sync_team_crud.py` | Create | 1 |
| `api/tests/test_sync_members.py` | Create | 2 |
| `api/tests/test_sync_team_projects.py` | Create | 3 |
| `api/tests/test_watcher_manager.py` | Create | 4 |
| `api/tests/test_sync_pending.py` | Create | 5 |
| `api/tests/test_sync_project_status.py` | Create | 6 |
| `frontend/src/lib/api-types.ts` | Modify (add types) | 7 |
| `frontend/src/lib/components/sync/SetupWizard.svelte` | Create | 8 |
| `frontend/src/lib/components/sync/OverviewTab.svelte` | Create | 9 |
| `frontend/src/lib/components/sync/MembersTab.svelte` | Create | 10 |
| `frontend/src/lib/components/sync/ProjectsTab.svelte` | Modify (rewrite) | 11 |
| `frontend/src/lib/components/sync/ProjectRow.svelte` | Modify | 11 |
| `frontend/src/routes/sync/+page.svelte` | Modify | 8,9,10,12 |
| `frontend/src/routes/sync/+page.server.ts` | Modify | 12 |
| `frontend/src/lib/components/sync/SetupTab.svelte` | Delete/repurpose | 13 |
| `frontend/src/lib/components/sync/DevicesTab.svelte` | Delete/repurpose | 13 |
