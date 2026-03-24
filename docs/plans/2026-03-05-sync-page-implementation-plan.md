# Sync Page Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build a `/sync` page in the dashboard that replaces Syncthing's localhost UI — users can install, initialize, pair devices, toggle project sync, and monitor transfers without ever leaving the Karma dashboard.

**Architecture:** Backend extends the existing `/sync` router (`api/routers/sync_status.py`) with new endpoints that proxy Syncthing's REST API via the existing `SyncthingClient` class (`cli/karma/syncthing.py`). Frontend adds a tabbed `/sync` route with four tabs (Setup, Devices, Projects, Activity) using the existing `bits-ui` Tabs components and Chart.js for bandwidth visualization.

**Tech Stack:** Python 3.9+ / FastAPI / Pydantic 2.x (backend), SvelteKit 2 / Svelte 5 / Tailwind CSS 4 / Chart.js / bits-ui (frontend)

**Design doc:** `docs/plans/2026-03-05-sync-page-ui-design.md`

---

## Architecture Review Amendments

> **Date:** 2026-03-05 | **Status:** Verified against codebase
>
> The following corrections were identified by cross-referencing the plan against the actual codebase. Apply these changes when implementing each task.

### Amendment A: SyncthingClient API Corrections (Tasks 1, 2)

The plan references methods and attributes that don't exist on `SyncthingClient` (`cli/karma/syncthing.py`):

| Plan references (wrong) | Actual API |
|---|---|
| `client.get_system_status()` | Does NOT exist. Use raw HTTP: `requests.get(f"{client.api_url}/rest/system/status", headers=client.headers)` |
| `client._headers` | `client.headers` (no underscore prefix) |
| `client._session` | Does NOT exist. Client uses `requests.get()`/`requests.put()` directly (no session object) |
| `client.get_connections()` returns per-device dict with `connected` key | Returns raw Syncthing format — `connected` is a field but nested under `connections` key from the API |

**Fix for `detect()` in SyncthingProxy:** Either add `get_system_status()` to SyncthingClient:
```python
# Add to cli/karma/syncthing.py SyncthingClient class:
def get_system_status(self) -> dict:
    resp = requests.get(f"{self.api_url}/rest/system/status", headers=self.headers, timeout=5)
    resp.raise_for_status()
    return resp.json()
```
Or use raw requests in the proxy (matching how `get_events()` should work):
```python
resp = requests.get(f"{self._client.api_url}/rest/system/status", headers=self._client.headers, timeout=5)
```

### Amendment B: Async Wrapping Required (Tasks 1, 2, 9, 10)

`SyncthingClient` uses synchronous `requests` library. All FastAPI endpoints calling it MUST use `asyncio.run_in_executor` to avoid blocking the event loop:

```python
import asyncio
from functools import partial

async def _run_sync(func, *args, **kwargs):
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, partial(func, *args, **kwargs))

# Example usage in router:
@router.get("/detect")
async def sync_detect():
    proxy = get_proxy()
    return await _run_sync(proxy.detect)
```

Apply to ALL endpoints: `/detect`, `/devices`, `/devices POST`, `/devices DELETE`, `/projects`, `/activity`, `/init`.

### Amendment C: CLI Command Corrections (Tasks 9, 10)

The `karma` CLI uses `click` (not argparse). Actual command signatures differ from the plan:

| Plan assumes | Actual CLI command |
|---|---|
| `karma init --backend syncthing --machine-name <name>` | `karma init --user-id <id> --backend syncthing` (no `--machine-name`; machine ID auto-generated from hostname) |
| `karma sync <project>` | **IPFS-only.** For Syncthing, use `SessionPackager` directly to re-package the outbox. |
| `karma project add <name>` | `karma project add <name> --path <abs-path> --team <team>` (requires `--path` and `--team`) |
| `karma project remove <name>` | `karma project remove <name> --team <team>` |
| `karma watch` | `karma watch --team <team>` (requires `--team`) |

**Fix for `POST /sync/init`:** Update `InitRequest` model:
```python
class InitRequest(BaseModel):
    user_id: str  # NOT machine_name
    backend: str = "syncthing"
```
And the subprocess call:
```python
run_karma_command(["init", "--user-id", req.user_id, "--backend", req.backend])
```

**Fix for "Sync Now":** Instead of calling `karma sync`, invoke the packager:
```python
@router.post("/projects/{name}/sync-now")
async def sync_project_now(name: str):
    name = validate_project_name(name)
    # Import and run packager directly instead of karma sync (which is IPFS-only)
    result = run_karma_command(["watch", "--team", _get_default_team_name()])
    # Or better: package directly via Python import
    return {"success": True}
```

### Amendment D: Backend Must Join Folder↔Project Data (Task 7)

The frontend should NOT guess Syncthing folder naming conventions. The plan's `ProjectsTab.svelte` does:
```typescript
synced: syncedFolders.has(`karma-out-${p.encoded_name}`)  // WRONG
```

**Fix:** The `GET /sync/projects` endpoint must return already-joined data by reading `sync-config.json` teams→projects and matching against `SyncthingClient.get_folders()` via `find_folder_by_path()`. See the existing `services/remote_sessions.py` for the config reading pattern.

### Amendment E: Design Token Usage (Tasks 5, 6, 7, 8)

Replace ALL hardcoded Tailwind colors with CSS custom properties. Complete mapping:

| Wrong (in plan) | Correct |
|---|---|
| `bg-green-500` | `bg-[var(--success)]` |
| `bg-orange-500` | `bg-[var(--warning)]` |
| `bg-gray-400` | `bg-[var(--text-muted)]` |
| `bg-red-500` | `bg-[var(--error)]` |
| `bg-blue-500` | `bg-[var(--info)]` |
| `text-red-500` | `text-[var(--error)]` |
| `text-purple-500` | `text-[var(--accent)]` |
| `text-blue-500` | `text-[var(--info)]` |
| `bg-orange-500/5`, `bg-green-500/5` | `var(--status-stale-bg)`, `var(--status-active-bg)` |
| `border-orange-500/30`, `border-green-500/30` | `border-[var(--warning)]/30`, `border-[var(--success)]/30` |
| `'#7c3aed'` (chart hex) | `getThemeColors().accent` from `chartConfig.ts` |
| `'#3b82f6'` (chart hex) | Resolve `--info` via `getComputedStyle` |
| `bg-red-50 dark:bg-red-900/20` (error) | `bg-[var(--error-subtle)]` |

### Amendment F: Test Pattern Corrections (Tasks 1, 2, 9, 10)

Tests use module-level `TestClient(app)` with `monkeypatch`, NOT `with patch()` context managers:

```python
# WRONG (plan's pattern):
with patch("routers.sync_status.get_proxy") as mock_get:
    ...

# CORRECT (codebase pattern):
from fastapi.testclient import TestClient
from main import app
client = TestClient(app)

class TestSyncDetect:
    def test_detect_no_syncthing(self, monkeypatch):
        mock_proxy = MagicMock()
        mock_proxy.detect.return_value = {...}
        monkeypatch.setattr("routers.sync_status.get_proxy", lambda: mock_proxy)
        resp = client.get("/sync/detect")
        assert resp.status_code == 200
```

### Amendment G: Input Validation (Tasks 2, 9, 10)

Add regex validation following `api/routers/commands.py` pattern:

```python
import re
from fastapi import HTTPException

ALLOWED_PROJECT_NAME = re.compile(r"^[a-zA-Z0-9_\-]+$")
ALLOWED_DEVICE_ID = re.compile(r"^[A-Z0-9\-]+$")

def validate_project_name(name: str) -> str:
    if not ALLOWED_PROJECT_NAME.match(name) or len(name) > 128:
        raise HTTPException(400, "Invalid project name")
    return name

def validate_device_id(device_id: str) -> str:
    if not ALLOWED_DEVICE_ID.match(device_id) or len(device_id) > 72:
        raise HTTPException(400, "Invalid device ID")
    return device_id
```

Apply to: `DELETE /sync/devices/{device_id}`, `POST /sync/projects/{name}/enable`, `/disable`, `/sync-now`.

### Amendment H: Frontend Pattern Corrections (Tasks 3, 4, 5, 6, 7, 8)

1. **Tabs API:** `TabsTrigger` has an `icon` prop — use `<TabsTrigger value="setup" icon={Settings2}>Setup</TabsTrigger>` instead of wrapping icons in `<span>` children.

2. **Nav insertion point:** "Sync" goes after Archived (line 161) before Team (line 169) in `Header.svelte`. Same for mobile nav after line 321.

3. **Skeleton route:** Use `if (path.startsWith('/sync')) return 'settings';` (with `startsWith`, not `===`).

4. **Centralize polling:** Single 10s interval at page level in `+page.svelte`, pass data to tabs via props. Remove independent `setInterval` calls from `DevicesTab` and `ActivityTab`.

5. **Error recovery:** Follow settings page pattern — inline `bg-[var(--error-subtle)]` banner with retry button. Add troubleshooting context to error messages.

6. **Network config:** Mark radio buttons as disabled with "(coming soon)" label.

7. **Tab badges:** Add count badges to Devices and Projects triggers, activity dot to Activity trigger.

8. **Accessibility:** Add `aria-label` to all toggle dots, remove buttons, and copy buttons.

9. **Event data formatting:** Replace `JSON.stringify(event.data).slice(0, 100)` with structured formatters per event type.

---

## Task 1: Backend — Syncthing proxy service

Create a service layer that wraps `SyncthingClient` for use by the API. The CLI's `SyncthingClient` talks directly to Syncthing's REST API — this service adds error handling, response shaping, and caching suitable for the FastAPI layer.

**Files:**
- Create: `api/services/syncthing_proxy.py`
- Test: `api/tests/test_syncthing_proxy.py`

**Step 1: Write the failing test**

Create `api/tests/test_syncthing_proxy.py`:

```python
"""Tests for Syncthing proxy service."""

import pytest
from unittest.mock import MagicMock, patch

from services.syncthing_proxy import SyncthingProxy, SyncthingNotRunning


class TestSyncthingProxy:
    def test_detect_not_installed(self):
        """detect() returns not installed when Syncthing unreachable."""
        proxy = SyncthingProxy()
        with patch.object(proxy, "_client", None):
            result = proxy.detect()
        assert result["installed"] is False
        assert result["running"] is False

    def test_detect_running(self):
        """detect() returns version when Syncthing is running."""
        mock_client = MagicMock()
        mock_client.is_running.return_value = True
        mock_client.get_system_status.return_value = {
            "myID": "DEVICE-ID-123",
            "version": "v1.27.0",
            "uptime": 3600,
        }

        proxy = SyncthingProxy()
        proxy._client = mock_client

        result = proxy.detect()
        assert result["installed"] is True
        assert result["running"] is True
        assert result["version"] == "v1.27.0"
        assert result["device_id"] == "DEVICE-ID-123"

    def test_get_devices_not_running(self):
        """get_devices() raises when Syncthing not running."""
        proxy = SyncthingProxy()
        proxy._client = None

        with pytest.raises(SyncthingNotRunning):
            proxy.get_devices()

    def test_get_devices_returns_formatted(self):
        """get_devices() formats connection + stats data."""
        mock_client = MagicMock()
        mock_client.is_running.return_value = True
        mock_client.get_connections.return_value = {
            "REMOTE-ID": {
                "connected": True,
                "address": "tcp://192.168.1.42:22000",
                "type": "TCP (LAN)",
                "crypto": "TLS1.3",
                "inBytesTotal": 1000000,
                "outBytesTotal": 2000000,
            }
        }
        mock_client._get_config.return_value = {
            "devices": [
                {"deviceID": "REMOTE-ID", "name": "my-mac-mini"},
            ],
            "folders": [],
        }

        proxy = SyncthingProxy()
        proxy._client = mock_client

        devices = proxy.get_devices()
        assert len(devices) == 1
        assert devices[0]["device_id"] == "REMOTE-ID"
        assert devices[0]["name"] == "my-mac-mini"
        assert devices[0]["connected"] is True
        assert devices[0]["address"] == "tcp://192.168.1.42:22000"

    def test_get_projects_sync_state(self):
        """get_projects() returns per-project sync status."""
        mock_client = MagicMock()
        mock_client.is_running.return_value = True
        mock_client.get_folders.return_value = [
            {
                "id": "karma-out-alice",
                "path": "/home/alice/.claude_karma/remote-sessions/alice",
                "devices": [{"deviceID": "REMOTE-ID"}],
                "type": "sendonly",
            }
        ]

        proxy = SyncthingProxy()
        proxy._client = mock_client

        projects = proxy.get_folder_status()
        assert len(projects) == 1
        assert projects[0]["folder_id"] == "karma-out-alice"
```

**Step 2: Run tests to verify they fail**

Run: `cd api && python -m pytest tests/test_syncthing_proxy.py -v`
Expected: FAIL — `services.syncthing_proxy` does not exist

**Step 3: Implement the proxy service**

Create `api/services/syncthing_proxy.py`:

```python
"""Syncthing proxy service for the Karma API."""

from __future__ import annotations

import logging
import sys
from pathlib import Path
from typing import Any, Optional

# Add CLI to path so we can import SyncthingClient
CLI_PATH = Path(__file__).parent.parent.parent / "cli"
if str(CLI_PATH) not in sys.path:
    sys.path.insert(0, str(CLI_PATH))

try:
    from karma.syncthing import SyncthingClient, read_local_api_key
except ImportError:
    SyncthingClient = None  # type: ignore[misc,assignment]
    read_local_api_key = None  # type: ignore[assignment]

logger = logging.getLogger(__name__)


class SyncthingNotRunning(Exception):
    """Raised when Syncthing daemon is not reachable."""


class SyncthingProxy:
    """Wraps SyncthingClient for API use with error handling."""

    def __init__(self) -> None:
        self._client: Optional[Any] = None
        self._try_connect()

    def _try_connect(self) -> None:
        """Attempt to create a SyncthingClient connection."""
        if SyncthingClient is None:
            return
        try:
            api_key = read_local_api_key() if read_local_api_key else None
            client = SyncthingClient(
                api_url="http://127.0.0.1:8384",
                api_key=api_key,
            )
            if client.is_running():
                self._client = client
        except Exception:
            logger.debug("Syncthing not available", exc_info=True)

    def _require_client(self) -> Any:
        """Return client or raise if not available."""
        if self._client is None:
            self._try_connect()
        if self._client is None:
            raise SyncthingNotRunning("Syncthing daemon is not running")
        return self._client

    def detect(self) -> dict[str, Any]:
        """Check if Syncthing is installed and running."""
        if self._client is None:
            self._try_connect()

        if self._client is None:
            return {
                "installed": SyncthingClient is not None,
                "running": False,
                "version": None,
                "device_id": None,
            }

        try:
            status = self._client.get_system_status()
            return {
                "installed": True,
                "running": True,
                "version": status.get("version"),
                "device_id": status.get("myID"),
                "uptime": status.get("uptime"),
            }
        except Exception:
            return {
                "installed": True,
                "running": False,
                "version": None,
                "device_id": None,
            }

    def get_devices(self) -> list[dict[str, Any]]:
        """Get all paired devices with connection status."""
        client = self._require_client()
        connections = client.get_connections()
        config = client._get_config()
        config_devices = {d["deviceID"]: d for d in config.get("devices", [])}

        devices = []
        for device_id, dev_config in config_devices.items():
            conn = connections.get(device_id, {})
            devices.append({
                "device_id": device_id,
                "name": dev_config.get("name", ""),
                "connected": conn.get("connected", False),
                "address": conn.get("address", ""),
                "type": conn.get("type", ""),
                "crypto": conn.get("crypto", ""),
                "in_bytes_total": conn.get("inBytesTotal", 0),
                "out_bytes_total": conn.get("outBytesTotal", 0),
            })

        return devices

    def add_device(self, device_id: str, name: str) -> dict[str, Any]:
        """Pair with a new device."""
        client = self._require_client()
        client.add_device(device_id, name)
        return {"device_id": device_id, "name": name, "paired": True}

    def remove_device(self, device_id: str) -> dict[str, Any]:
        """Remove a paired device."""
        client = self._require_client()
        client.remove_device(device_id)
        return {"device_id": device_id, "removed": True}

    def get_folder_status(self) -> list[dict[str, Any]]:
        """Get all Syncthing folders with sync state."""
        client = self._require_client()
        folders = client.get_folders()
        return [
            {
                "folder_id": f["id"],
                "path": f.get("path", ""),
                "type": f.get("type", ""),
                "devices": [d["deviceID"] for d in f.get("devices", [])],
            }
            for f in folders
        ]

    def get_events(self, since: int = 0, limit: int = 50) -> list[dict[str, Any]]:
        """Get recent Syncthing events."""
        client = self._require_client()
        try:
            resp = client._session.get(
                f"{client.api_url}/rest/events",
                headers=client._headers,
                params={"since": since, "limit": limit},
                timeout=5,
            )
            resp.raise_for_status()
            return resp.json()
        except Exception:
            return []
```

**Step 4: Run tests to verify they pass**

Run: `cd api && python -m pytest tests/test_syncthing_proxy.py -v`
Expected: All PASS

**Step 5: Commit**

```bash
git add api/services/syncthing_proxy.py api/tests/test_syncthing_proxy.py
git commit -m "feat(api): add Syncthing proxy service layer

Wraps CLI's SyncthingClient for API use with error handling,
response shaping, and graceful fallback when Syncthing isn't running."
```

---

## Task 2: Backend — Expand /sync router with new endpoints

Extend `api/routers/sync_status.py` with the endpoints needed by the frontend tabs.

**Files:**
- Modify: `api/routers/sync_status.py`
- Test: `api/tests/api/test_sync_status.py` (extend existing)

**Step 1: Write failing tests**

Add to `api/tests/api/test_sync_status.py`:

```python
from unittest.mock import MagicMock, patch


class TestSyncDetect:
    def test_detect_no_syncthing(self):
        """GET /sync/detect returns not running when Syncthing unavailable."""
        with patch("routers.sync_status.get_proxy") as mock_get:
            mock_proxy = MagicMock()
            mock_proxy.detect.return_value = {
                "installed": False,
                "running": False,
                "version": None,
                "device_id": None,
            }
            mock_get.return_value = mock_proxy

            resp = client.get("/sync/detect")
            assert resp.status_code == 200
            data = resp.json()
            assert data["installed"] is False
            assert data["running"] is False

    def test_detect_syncthing_running(self):
        """GET /sync/detect returns version when Syncthing running."""
        with patch("routers.sync_status.get_proxy") as mock_get:
            mock_proxy = MagicMock()
            mock_proxy.detect.return_value = {
                "installed": True,
                "running": True,
                "version": "v1.27.0",
                "device_id": "DEVICE-123",
            }
            mock_get.return_value = mock_proxy

            resp = client.get("/sync/detect")
            assert resp.status_code == 200
            data = resp.json()
            assert data["running"] is True
            assert data["version"] == "v1.27.0"


class TestSyncDevices:
    def test_list_devices(self):
        """GET /sync/devices returns paired devices."""
        with patch("routers.sync_status.get_proxy") as mock_get:
            mock_proxy = MagicMock()
            mock_proxy.get_devices.return_value = [
                {
                    "device_id": "REMOTE-1",
                    "name": "mac-mini",
                    "connected": True,
                    "address": "tcp://192.168.1.42:22000",
                    "type": "TCP (LAN)",
                    "crypto": "TLS1.3",
                    "in_bytes_total": 1000,
                    "out_bytes_total": 2000,
                }
            ]
            mock_get.return_value = mock_proxy

            resp = client.get("/sync/devices")
            assert resp.status_code == 200
            data = resp.json()
            assert len(data["devices"]) == 1
            assert data["devices"][0]["name"] == "mac-mini"

    def test_add_device(self):
        """POST /sync/devices pairs a new device."""
        with patch("routers.sync_status.get_proxy") as mock_get:
            mock_proxy = MagicMock()
            mock_proxy.add_device.return_value = {
                "device_id": "NEW-DEV",
                "name": "work-pc",
                "paired": True,
            }
            mock_get.return_value = mock_proxy

            resp = client.post(
                "/sync/devices",
                json={"device_id": "NEW-DEV", "name": "work-pc"},
            )
            assert resp.status_code == 200
            data = resp.json()
            assert data["paired"] is True

    def test_remove_device(self):
        """DELETE /sync/devices/{id} removes a device."""
        with patch("routers.sync_status.get_proxy") as mock_get:
            mock_proxy = MagicMock()
            mock_proxy.remove_device.return_value = {
                "device_id": "OLD-DEV",
                "removed": True,
            }
            mock_get.return_value = mock_proxy

            resp = client.delete("/sync/devices/OLD-DEV")
            assert resp.status_code == 200
            data = resp.json()
            assert data["removed"] is True


class TestSyncProjects:
    def test_list_projects_sync_state(self):
        """GET /sync/projects returns folder sync state."""
        with patch("routers.sync_status.get_proxy") as mock_get:
            mock_proxy = MagicMock()
            mock_proxy.get_folder_status.return_value = [
                {
                    "folder_id": "karma-out-alice",
                    "path": "/home/alice/.claude_karma/remote-sessions/alice",
                    "type": "sendonly",
                    "devices": ["REMOTE-1"],
                }
            ]
            mock_get.return_value = mock_proxy

            resp = client.get("/sync/projects")
            assert resp.status_code == 200
            data = resp.json()
            assert len(data["folders"]) == 1


class TestSyncActivity:
    def test_get_events(self):
        """GET /sync/activity returns recent events."""
        with patch("routers.sync_status.get_proxy") as mock_get:
            mock_proxy = MagicMock()
            mock_proxy.get_events.return_value = [
                {
                    "id": 1,
                    "type": "DeviceConnected",
                    "time": "2026-03-05T10:00:00Z",
                    "data": {"id": "REMOTE-1"},
                }
            ]
            mock_get.return_value = mock_proxy

            resp = client.get("/sync/activity")
            assert resp.status_code == 200
            data = resp.json()
            assert len(data["events"]) == 1
            assert data["events"][0]["type"] == "DeviceConnected"
```

**Step 2: Run tests to verify they fail**

Run: `cd api && python -m pytest tests/api/test_sync_status.py -v`
Expected: FAIL — new endpoints don't exist yet

**Step 3: Expand the router**

Modify `api/routers/sync_status.py` — add new endpoints after existing ones:

```python
"""Sync status API endpoints."""

import json
from pathlib import Path
from typing import Any, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from services.syncthing_proxy import SyncthingProxy, SyncthingNotRunning

SYNC_CONFIG_PATH = Path.home() / ".claude_karma" / "sync-config.json"

router = APIRouter(prefix="/sync", tags=["sync"])

# Singleton proxy instance
_proxy: Optional[SyncthingProxy] = None


def get_proxy() -> SyncthingProxy:
    """Get or create the Syncthing proxy singleton."""
    global _proxy
    if _proxy is None:
        _proxy = SyncthingProxy()
    return _proxy


def _load_config() -> Optional[dict]:
    if not SYNC_CONFIG_PATH.exists():
        return None
    try:
        return json.loads(SYNC_CONFIG_PATH.read_text())
    except (json.JSONDecodeError, OSError):
        return None


# --- Existing endpoints (unchanged) ---


@router.get("/status")
async def sync_status():
    """Get sync configuration and status."""
    config = _load_config()
    if config is None:
        return {"configured": False}

    teams = {}
    for name, team in config.get("teams", {}).items():
        teams[name] = {
            "backend": team["backend"],
            "project_count": len(team.get("projects", {})),
            "member_count": len(team.get("ipfs_members", {}))
            + len(team.get("syncthing_members", {})),
        }

    return {
        "configured": True,
        "user_id": config.get("user_id"),
        "machine_id": config.get("machine_id"),
        "teams": teams,
    }


@router.get("/teams")
async def sync_teams():
    """List all teams with their backend and members."""
    config = _load_config()
    if config is None:
        return {"teams": []}

    teams = []
    for name, team in config.get("teams", {}).items():
        teams.append(
            {
                "name": name,
                "backend": team["backend"],
                "projects": list(team.get("projects", {}).keys()),
                "members": list(team.get("ipfs_members", {}).keys())
                + list(team.get("syncthing_members", {}).keys()),
            }
        )

    return {"teams": teams}


# --- New endpoints ---


@router.get("/detect")
async def sync_detect():
    """Check if Syncthing is installed and running."""
    proxy = get_proxy()
    return proxy.detect()


class AddDeviceRequest(BaseModel):
    device_id: str
    name: str


@router.get("/devices")
async def list_devices():
    """List all paired devices with connection status."""
    proxy = get_proxy()
    try:
        devices = proxy.get_devices()
        return {"devices": devices}
    except SyncthingNotRunning:
        raise HTTPException(status_code=503, detail="Syncthing is not running")


@router.post("/devices")
async def add_device(req: AddDeviceRequest):
    """Pair with a new device."""
    proxy = get_proxy()
    try:
        return proxy.add_device(req.device_id, req.name)
    except SyncthingNotRunning:
        raise HTTPException(status_code=503, detail="Syncthing is not running")


@router.delete("/devices/{device_id}")
async def remove_device(device_id: str):
    """Remove a paired device."""
    proxy = get_proxy()
    try:
        return proxy.remove_device(device_id)
    except SyncthingNotRunning:
        raise HTTPException(status_code=503, detail="Syncthing is not running")


@router.get("/projects")
async def sync_projects():
    """Get all Syncthing folders with sync state."""
    proxy = get_proxy()
    try:
        folders = proxy.get_folder_status()
        return {"folders": folders}
    except SyncthingNotRunning:
        raise HTTPException(status_code=503, detail="Syncthing is not running")


@router.get("/activity")
async def sync_activity(since: int = 0, limit: int = 50):
    """Get recent Syncthing events."""
    proxy = get_proxy()
    try:
        events = proxy.get_events(since=since, limit=limit)
        return {"events": events}
    except SyncthingNotRunning:
        raise HTTPException(status_code=503, detail="Syncthing is not running")
```

**Step 4: Run tests to verify they pass**

Run: `cd api && python -m pytest tests/api/test_sync_status.py -v`
Expected: All PASS

**Step 5: Lint**

Run: `cd api && ruff check routers/sync_status.py services/syncthing_proxy.py && ruff format routers/sync_status.py services/syncthing_proxy.py`

**Step 6: Commit**

```bash
git add api/routers/sync_status.py api/tests/api/test_sync_status.py
git commit -m "feat(api): add /sync/detect, devices, projects, activity endpoints

Expands the sync router with endpoints for the dashboard sync page:
detect, device CRUD, project folder status, and activity event log.
All proxy through SyncthingClient via the new proxy service."
```

---

## Task 3: Frontend — /sync route shell with tabs

Create the main sync page with tab structure. Initially all tabs render placeholder content.

**Files:**
- Create: `frontend/src/routes/sync/+page.svelte`
- Create: `frontend/src/routes/sync/+page.server.ts`

**Step 1: Create the server load function**

Create `frontend/src/routes/sync/+page.server.ts`:

```typescript
import type { PageServerLoad } from './$types';
import { API_BASE } from '$lib/config';
import { safeFetch } from '$lib/utils/api-fetch';

interface SyncDetect {
	installed: boolean;
	running: boolean;
	version: string | null;
	device_id: string | null;
	uptime: number | null;
}

interface SyncStatusResponse {
	configured: boolean;
	user_id?: string;
	machine_id?: string;
	teams?: Record<string, unknown>;
}

export const load: PageServerLoad = async ({ fetch, url }) => {
	const [detectResult, statusResult] = await Promise.all([
		safeFetch<SyncDetect>(fetch, `${API_BASE}/sync/detect`),
		safeFetch<SyncStatusResponse>(fetch, `${API_BASE}/sync/status`)
	]);

	const activeTab = url.searchParams.get('tab') || null;

	return {
		detect: detectResult.ok ? detectResult.data : null,
		status: statusResult.ok ? statusResult.data : null,
		activeTab
	};
};
```

**Step 2: Create the page component**

Create `frontend/src/routes/sync/+page.svelte`:

```svelte
<script lang="ts">
	import PageHeader from '$lib/components/layout/PageHeader.svelte';
	import Tabs from '$lib/components/ui/Tabs.svelte';
	import TabsList from '$lib/components/ui/TabsList.svelte';
	import TabsTrigger from '$lib/components/ui/TabsTrigger.svelte';
	import TabsContent from '$lib/components/ui/TabsContent.svelte';
	import { RefreshCw, Settings2, Monitor, FolderGit2, Activity } from 'lucide-svelte';
	import { goto } from '$app/navigation';
	import { page } from '$app/stores';

	let { data } = $props();

	// Determine default tab based on configuration state
	let defaultTab = $derived.by(() => {
		if (data.activeTab) return data.activeTab;
		if (!data.detect?.running || !data.status?.configured) return 'setup';
		return 'devices';
	});

	let activeTab = $state(defaultTab);

	// Sync tab to URL
	$effect(() => {
		const currentTab = $page.url.searchParams.get('tab');
		if (currentTab !== activeTab) {
			const url = new URL($page.url);
			url.searchParams.set('tab', activeTab);
			goto(url.toString(), { replaceState: true, noScroll: true });
		}
	});

	let isRefreshing = $state(false);
	async function refresh() {
		isRefreshing = true;
		// SvelteKit invalidation triggers reload
		const { invalidateAll } = await import('$app/navigation');
		await invalidateAll();
		isRefreshing = false;
	}
</script>

<PageHeader
	title="Sync"
	icon={RefreshCw}
	iconColor="--nav-purple"
	breadcrumbs={[{ label: 'Dashboard', href: '/' }, { label: 'Sync' }]}
/>

<div class="space-y-6">
	<!-- Refresh button -->
	<div class="flex justify-end">
		<button
			onclick={refresh}
			disabled={isRefreshing}
			class="flex items-center gap-1.5 text-xs text-[var(--text-muted)] hover:text-[var(--text-primary)] transition-colors"
		>
			<RefreshCw size={12} class={isRefreshing ? 'animate-spin' : ''} />
			Refresh
		</button>
	</div>

	<Tabs bind:value={activeTab}>
		<TabsList>
			<TabsTrigger value="setup">
				<span class="flex items-center gap-1.5">
					<Settings2 size={14} />
					Setup
					{#if data.status?.configured}
						<span class="w-1.5 h-1.5 rounded-full bg-green-500"></span>
					{/if}
				</span>
			</TabsTrigger>
			<TabsTrigger value="devices">
				<span class="flex items-center gap-1.5">
					<Monitor size={14} />
					Devices
				</span>
			</TabsTrigger>
			<TabsTrigger value="projects">
				<span class="flex items-center gap-1.5">
					<FolderGit2 size={14} />
					Projects
				</span>
			</TabsTrigger>
			<TabsTrigger value="activity">
				<span class="flex items-center gap-1.5">
					<Activity size={14} />
					Activity
				</span>
			</TabsTrigger>
		</TabsList>

		<TabsContent value="setup">
			<div class="py-8 text-center text-[var(--text-muted)]">
				Setup tab — coming in next task
			</div>
		</TabsContent>

		<TabsContent value="devices">
			<div class="py-8 text-center text-[var(--text-muted)]">
				Devices tab — coming in next task
			</div>
		</TabsContent>

		<TabsContent value="projects">
			<div class="py-8 text-center text-[var(--text-muted)]">
				Projects tab — coming in next task
			</div>
		</TabsContent>

		<TabsContent value="activity">
			<div class="py-8 text-center text-[var(--text-muted)]">
				Activity tab — coming in next task
			</div>
		</TabsContent>
	</Tabs>
</div>
```

**Step 3: Verify it builds**

Run: `cd frontend && npm run check`
Expected: No type errors

**Step 4: Commit**

```bash
git add frontend/src/routes/sync/+page.svelte frontend/src/routes/sync/+page.server.ts
git commit -m "feat(frontend): add /sync route shell with tabbed layout

Four tabs (Setup, Devices, Projects, Activity) using bits-ui Tabs.
Default tab is Setup when unconfigured, Devices when configured.
Tab state persisted in URL params."
```

---

## Task 4: Frontend — Add "Sync" to navigation

Add the Sync link to the header navigation (desktop + mobile).

**Files:**
- Modify: `frontend/src/lib/components/Header.svelte`
- Modify: `frontend/src/routes/+layout.svelte` (skeleton)

**Step 1: Add Sync nav link to Header.svelte**

In the desktop nav section (after the "Archived" link, before "Team"), add:

```svelte
<a
	href="/sync"
	class="text-sm font-medium text-[var(--text-muted)] hover:text-[var(--text-primary)] transition-colors"
	class:text-[var(--text-primary)]={$page.url.pathname.startsWith('/sync')}
	aria-current={$page.url.pathname.startsWith('/sync') ? 'page' : undefined}
>
	Sync
</a>
```

Add the same link in the mobile nav section (same position — after Archived, before Team).

**Step 2: Add skeleton route in +layout.svelte**

In the `navigationSkeletonType` derived block, add before `return null`:

```typescript
if (path === '/sync') return 'settings'; // Reuse settings skeleton for now
```

**Step 3: Verify it builds**

Run: `cd frontend && npm run check`
Expected: No type errors

**Step 4: Commit**

```bash
git add frontend/src/lib/components/Header.svelte frontend/src/routes/+layout.svelte
git commit -m "feat(frontend): add Sync to navigation header

Adds Sync link between Archived and Team in both desktop and mobile
nav. Reuses settings skeleton during navigation loading."
```

---

## Task 5: Frontend — Setup tab component

The most complex tab — three states with progressive disclosure.

**Files:**
- Create: `frontend/src/lib/components/sync/SetupTab.svelte`
- Modify: `frontend/src/routes/sync/+page.svelte` (import SetupTab)

**Step 1: Create SetupTab.svelte**

Create `frontend/src/lib/components/sync/SetupTab.svelte`:

```svelte
<script lang="ts">
	import { API_BASE } from '$lib/config';
	import {
		CheckCircle,
		XCircle,
		Copy,
		Plus,
		Trash2,
		Loader2,
		Wifi,
		Globe,
		Shield
	} from 'lucide-svelte';

	interface DetectData {
		installed: boolean;
		running: boolean;
		version: string | null;
		device_id: string | null;
		uptime: number | null;
	}

	interface StatusData {
		configured: boolean;
		user_id?: string;
		machine_id?: string;
	}

	interface Device {
		device_id: string;
		name: string;
		connected: boolean;
		address: string;
	}

	let {
		detect,
		status
	}: {
		detect: DetectData | null;
		status: StatusData | null;
	} = $props();

	// Local state
	let machineName = $state('');
	let isInitializing = $state(false);
	let initError = $state<string | null>(null);

	let newDeviceId = $state('');
	let newDeviceName = $state('');
	let isPairing = $state(false);
	let pairError = $state<string | null>(null);

	let devices = $state<Device[]>([]);
	let isLoadingDevices = $state(false);

	let isChecking = $state(false);
	let copied = $state(false);

	// Derived state
	let setupState = $derived.by(() => {
		if (!detect?.running) return 'not-installed';
		if (!status?.configured) return 'not-initialized';
		return 'configured';
	});

	// Auto-fill machine name from hostname-like value
	$effect(() => {
		if (status?.machine_id && !machineName) {
			machineName = status.machine_id;
		}
	});

	// Load devices when configured
	$effect(() => {
		if (setupState === 'configured') {
			loadDevices();
		}
	});

	// Detect OS for install instructions
	let detectedOS = $derived.by(() => {
		if (typeof navigator === 'undefined') return 'macos';
		const ua = navigator.userAgent.toLowerCase();
		if (ua.includes('mac')) return 'macos';
		if (ua.includes('win')) return 'windows';
		return 'linux';
	});

	async function checkAgain() {
		isChecking = true;
		try {
			const res = await fetch(`${API_BASE}/sync/detect`);
			if (res.ok) {
				const data = await res.json();
				detect = data;
			}
		} finally {
			isChecking = false;
		}
	}

	async function initialize() {
		isInitializing = true;
		initError = null;
		try {
			const res = await fetch(`${API_BASE}/sync/init`, {
				method: 'POST',
				headers: { 'Content-Type': 'application/json' },
				body: JSON.stringify({ machine_name: machineName })
			});
			if (res.ok) {
				// Reload status
				const [detectRes, statusRes] = await Promise.all([
					fetch(`${API_BASE}/sync/detect`),
					fetch(`${API_BASE}/sync/status`)
				]);
				if (detectRes.ok) detect = await detectRes.json();
				if (statusRes.ok) status = await statusRes.json();
			} else {
				const err = await res.json();
				initError = err.detail || 'Initialization failed';
			}
		} catch (e) {
			initError = 'Failed to connect to API';
		} finally {
			isInitializing = false;
		}
	}

	async function copyDeviceId() {
		if (detect?.device_id) {
			await navigator.clipboard.writeText(detect.device_id);
			copied = true;
			setTimeout(() => (copied = false), 2000);
		}
	}

	async function loadDevices() {
		isLoadingDevices = true;
		try {
			const res = await fetch(`${API_BASE}/sync/devices`);
			if (res.ok) {
				const data = await res.json();
				devices = data.devices;
			}
		} finally {
			isLoadingDevices = false;
		}
	}

	async function pairDevice() {
		if (!newDeviceId.trim() || !newDeviceName.trim()) return;
		isPairing = true;
		pairError = null;
		try {
			const res = await fetch(`${API_BASE}/sync/devices`, {
				method: 'POST',
				headers: { 'Content-Type': 'application/json' },
				body: JSON.stringify({ device_id: newDeviceId.trim(), name: newDeviceName.trim() })
			});
			if (res.ok) {
				newDeviceId = '';
				newDeviceName = '';
				await loadDevices();
			} else {
				const err = await res.json();
				pairError = err.detail || 'Pairing failed';
			}
		} catch {
			pairError = 'Failed to connect to API';
		} finally {
			isPairing = false;
		}
	}

	async function removeDevice(deviceId: string) {
		if (!confirm('Remove this device? It will stop syncing.')) return;
		try {
			const res = await fetch(`${API_BASE}/sync/devices/${encodeURIComponent(deviceId)}`, {
				method: 'DELETE'
			});
			if (res.ok) {
				await loadDevices();
			}
		} catch {
			// silent
		}
	}
</script>

<div class="space-y-6 py-4">
	<!-- Backend Selection -->
	<div
		class="border border-[var(--border)] rounded-[var(--radius-lg)] p-5 bg-[var(--bg-base)]"
	>
		<h3 class="text-sm font-medium text-[var(--text-primary)] mb-4">Choose Sync Backend</h3>
		<div class="grid grid-cols-1 sm:grid-cols-2 gap-3">
			<div
				class="border-2 border-[var(--accent)] rounded-[var(--radius)] p-4 bg-[var(--bg-subtle)]"
			>
				<div class="flex items-center gap-2 mb-2">
					<div class="w-3 h-3 rounded-full bg-[var(--accent)]"></div>
					<span class="font-medium text-[var(--text-primary)]">Syncthing</span>
				</div>
				<p class="text-xs text-[var(--text-secondary)] mb-2">
					Real-time auto sync between your machines. Simple setup, encrypted.
				</p>
				<p class="text-xs text-[var(--text-muted)]">
					Best for: syncing your own machines
				</p>
			</div>
			<div
				class="border border-[var(--border)] rounded-[var(--radius)] p-4 opacity-50 cursor-not-allowed"
			>
				<div class="flex items-center gap-2 mb-2">
					<div class="w-3 h-3 rounded-full bg-[var(--border)]"></div>
					<span class="font-medium text-[var(--text-secondary)]">IPFS</span>
				</div>
				<p class="text-xs text-[var(--text-secondary)] mb-2">
					On-demand sync, content-addressed, tamper-evident.
				</p>
				<p class="text-xs text-[var(--text-muted)]">Coming soon</p>
			</div>
		</div>
	</div>

	{#if setupState === 'not-installed'}
		<!-- State 1: Not detected -->
		<div
			class="border border-orange-500/30 rounded-[var(--radius-lg)] p-5 bg-orange-500/5"
		>
			<div class="flex items-center gap-2 mb-4">
				<XCircle size={16} class="text-orange-500" />
				<h3 class="text-sm font-medium text-[var(--text-primary)]">
					Syncthing not detected
				</h3>
			</div>

			<div class="space-y-3 text-sm">
				<div
					class="flex items-center gap-3 px-3 py-2 rounded-[var(--radius)] {detectedOS === 'macos' ? 'bg-[var(--bg-muted)]' : ''}"
				>
					<span class="text-[var(--text-muted)] w-16">macOS</span>
					<code class="font-mono text-xs text-[var(--text-secondary)]"
						>brew install syncthing</code
					>
				</div>
				<div
					class="flex items-center gap-3 px-3 py-2 rounded-[var(--radius)] {detectedOS === 'linux' ? 'bg-[var(--bg-muted)]' : ''}"
				>
					<span class="text-[var(--text-muted)] w-16">Linux</span>
					<code class="font-mono text-xs text-[var(--text-secondary)]"
						>sudo apt install syncthing</code
					>
				</div>
				<div
					class="flex items-center gap-3 px-3 py-2 rounded-[var(--radius)] {detectedOS === 'windows' ? 'bg-[var(--bg-muted)]' : ''}"
				>
					<span class="text-[var(--text-muted)] w-16">Windows</span>
					<code class="font-mono text-xs text-[var(--text-secondary)]"
						>scoop install syncthing</code
					>
				</div>

				<p class="text-xs text-[var(--text-muted)] pt-2">
					Then start it: <code class="font-mono">syncthing serve --no-browser</code>
				</p>
			</div>

			<div class="mt-4">
				<button
					onclick={checkAgain}
					disabled={isChecking}
					class="px-4 py-2 text-sm font-medium rounded-[var(--radius)] bg-[var(--accent)] text-white hover:opacity-90 transition-opacity disabled:opacity-50"
				>
					{#if isChecking}
						<Loader2 size={14} class="inline animate-spin mr-1" />
					{/if}
					Check Again
				</button>
			</div>
		</div>
	{:else if setupState === 'not-initialized'}
		<!-- State 2: Detected, not initialized -->
		<div
			class="border border-green-500/30 rounded-[var(--radius-lg)] p-5 bg-green-500/5"
		>
			<div class="flex items-center gap-2 mb-1">
				<CheckCircle size={16} class="text-green-500" />
				<span class="text-sm font-medium text-[var(--text-primary)]">
					Syncthing {detect?.version} running
				</span>
			</div>
		</div>

		<div
			class="border border-[var(--border)] rounded-[var(--radius-lg)] p-5 bg-[var(--bg-base)]"
		>
			<h3 class="text-sm font-medium text-[var(--text-primary)] mb-4">Initialize</h3>

			<div class="space-y-4">
				<div>
					<label class="block text-xs text-[var(--text-muted)] mb-1">Machine Name</label>
					<input
						type="text"
						bind:value={machineName}
						placeholder="my-macbook-pro"
						class="w-full max-w-xs px-3 py-2 text-sm rounded-[var(--radius)] border border-[var(--border)] bg-[var(--bg-subtle)] text-[var(--text-primary)] placeholder:text-[var(--text-muted)]"
					/>
					<p class="text-xs text-[var(--text-muted)] mt-1">Auto-filled from hostname</p>
				</div>

				{#if detect?.device_id}
					<div>
						<label class="block text-xs text-[var(--text-muted)] mb-1"
							>Your Device ID</label
						>
						<div class="flex items-center gap-2">
							<code
								class="flex-1 px-3 py-2 text-xs font-mono bg-[var(--bg-muted)] rounded-[var(--radius)] text-[var(--text-secondary)] truncate"
							>
								{detect.device_id}
							</code>
							<button
								onclick={copyDeviceId}
								class="px-3 py-2 text-xs rounded-[var(--radius)] border border-[var(--border)] hover:bg-[var(--bg-muted)] transition-colors"
							>
								{#if copied}
									Copied!
								{:else}
									<Copy size={12} class="inline" /> Copy
								{/if}
							</button>
						</div>
						<p class="text-xs text-[var(--text-muted)] mt-1">
							Share this with your other machine
						</p>
					</div>
				{/if}

				{#if initError}
					<p class="text-xs text-red-500">{initError}</p>
				{/if}

				<button
					onclick={initialize}
					disabled={isInitializing}
					class="px-4 py-2 text-sm font-medium rounded-[var(--radius)] bg-[var(--accent)] text-white hover:opacity-90 transition-opacity disabled:opacity-50"
				>
					{#if isInitializing}
						<Loader2 size={14} class="inline animate-spin mr-1" />
					{/if}
					Initialize
				</button>
			</div>
		</div>
	{:else}
		<!-- State 3: Configured — show this machine + paired devices -->
		<div
			class="border border-green-500/30 rounded-[var(--radius-lg)] p-5 bg-green-500/5"
		>
			<div class="flex items-center justify-between">
				<div>
					<div class="flex items-center gap-2 mb-1">
						<CheckCircle size={16} class="text-green-500" />
						<span class="font-medium text-[var(--text-primary)]">
							{status?.machine_id || 'This Machine'}
						</span>
					</div>
					<p class="text-xs text-[var(--text-muted)]">
						Syncthing {detect?.version} running
					</p>
				</div>
				{#if detect?.device_id}
					<button
						onclick={copyDeviceId}
						class="flex items-center gap-1.5 px-3 py-1.5 text-xs rounded-[var(--radius)] border border-[var(--border)] hover:bg-[var(--bg-muted)] transition-colors"
					>
						<Copy size={12} />
						{copied ? 'Copied!' : 'Copy Device ID'}
					</button>
				{/if}
			</div>
		</div>

		<!-- Paired Devices -->
		<div
			class="border border-[var(--border)] rounded-[var(--radius-lg)] p-5 bg-[var(--bg-base)]"
		>
			<h3 class="text-sm font-medium text-[var(--text-primary)] mb-4">Paired Devices</h3>

			{#if isLoadingDevices}
				<p class="text-sm text-[var(--text-muted)]">Loading devices...</p>
			{:else if devices.length === 0}
				<p class="text-sm text-[var(--text-muted)] mb-4">No devices paired yet.</p>
			{:else}
				<div class="space-y-3 mb-4">
					{#each devices as device}
						<div
							class="flex items-center justify-between px-3 py-2.5 rounded-[var(--radius)] bg-[var(--bg-subtle)]"
						>
							<div>
								<div class="flex items-center gap-2">
									<span
										class="w-2 h-2 rounded-full {device.connected ? 'bg-green-500' : 'bg-gray-400'}"
									></span>
									<span class="text-sm font-medium text-[var(--text-primary)]">
										{device.name}
									</span>
								</div>
								<p class="text-xs text-[var(--text-muted)] ml-4 mt-0.5">
									{device.connected ? device.address : 'Disconnected'}
								</p>
							</div>
							<button
								onclick={() => removeDevice(device.device_id)}
								class="p-1.5 text-[var(--text-muted)] hover:text-red-500 transition-colors"
								title="Remove device"
							>
								<Trash2 size={14} />
							</button>
						</div>
					{/each}
				</div>
			{/if}

			<!-- Add Device Form -->
			<div class="border-t border-[var(--border)] pt-4 mt-4">
				<div class="flex items-center gap-2 mb-3">
					<Plus size={14} class="text-[var(--text-muted)]" />
					<span class="text-sm font-medium text-[var(--text-primary)]">Add Device</span>
				</div>
				<div class="space-y-3">
					<input
						type="text"
						bind:value={newDeviceId}
						placeholder="Paste Device ID"
						class="w-full px-3 py-2 text-sm font-mono rounded-[var(--radius)] border border-[var(--border)] bg-[var(--bg-subtle)] text-[var(--text-primary)] placeholder:text-[var(--text-muted)]"
					/>
					<input
						type="text"
						bind:value={newDeviceName}
						placeholder="Device name (e.g., my-mac-mini)"
						class="w-full px-3 py-2 text-sm rounded-[var(--radius)] border border-[var(--border)] bg-[var(--bg-subtle)] text-[var(--text-primary)] placeholder:text-[var(--text-muted)]"
					/>
					{#if pairError}
						<p class="text-xs text-red-500">{pairError}</p>
					{/if}
					<button
						onclick={pairDevice}
						disabled={isPairing || !newDeviceId.trim() || !newDeviceName.trim()}
						class="px-4 py-2 text-sm font-medium rounded-[var(--radius)] bg-[var(--accent)] text-white hover:opacity-90 transition-opacity disabled:opacity-50"
					>
						{#if isPairing}
							<Loader2 size={14} class="inline animate-spin mr-1" />
						{/if}
						Pair Device
					</button>
				</div>
			</div>
		</div>

		<!-- Network Configuration -->
		<div
			class="border border-[var(--border)] rounded-[var(--radius-lg)] p-5 bg-[var(--bg-base)]"
		>
			<h3 class="text-sm font-medium text-[var(--text-primary)] mb-4">Network</h3>
			<div class="space-y-2">
				<label class="flex items-center gap-3 px-3 py-2 rounded-[var(--radius)] hover:bg-[var(--bg-subtle)] cursor-pointer">
					<input type="radio" name="network" value="local" checked class="accent-[var(--accent)]" />
					<div>
						<div class="flex items-center gap-1.5">
							<Wifi size={12} class="text-[var(--text-muted)]" />
							<span class="text-sm text-[var(--text-primary)]">Local network</span>
						</div>
						<p class="text-xs text-[var(--text-muted)]">Devices on same WiFi/LAN</p>
					</div>
				</label>
				<label class="flex items-center gap-3 px-3 py-2 rounded-[var(--radius)] hover:bg-[var(--bg-subtle)] cursor-pointer">
					<input type="radio" name="network" value="relay" class="accent-[var(--accent)]" />
					<div>
						<div class="flex items-center gap-1.5">
							<Globe size={12} class="text-[var(--text-muted)]" />
							<span class="text-sm text-[var(--text-primary)]">Remote (relays)</span>
						</div>
						<p class="text-xs text-[var(--text-muted)]">Via Syncthing relays, encrypted</p>
					</div>
				</label>
				<label class="flex items-center gap-3 px-3 py-2 rounded-[var(--radius)] hover:bg-[var(--bg-subtle)] cursor-pointer">
					<input type="radio" name="network" value="vpn" class="accent-[var(--accent)]" />
					<div>
						<div class="flex items-center gap-1.5">
							<Shield size={12} class="text-[var(--text-muted)]" />
							<span class="text-sm text-[var(--text-primary)]">VPN</span>
						</div>
						<p class="text-xs text-[var(--text-muted)]">Tailscale/WireGuard, direct connection</p>
					</div>
				</label>
			</div>
		</div>
	{/if}
</div>
```

**Step 2: Wire it into the sync page**

Update `frontend/src/routes/sync/+page.svelte` — replace the setup TabsContent placeholder:

```svelte
<!-- Add import at top -->
import SetupTab from '$lib/components/sync/SetupTab.svelte';

<!-- Replace the setup TabsContent -->
<TabsContent value="setup">
    <SetupTab detect={data.detect} status={data.status} />
</TabsContent>
```

**Step 3: Verify it builds**

Run: `cd frontend && npm run check`
Expected: No type errors

**Step 4: Commit**

```bash
git add frontend/src/lib/components/sync/SetupTab.svelte frontend/src/routes/sync/+page.svelte
git commit -m "feat(frontend): implement Setup tab for /sync page

Three-state progressive flow: detect Syncthing installation,
initialize with machine name, pair devices with Device ID exchange.
Network configuration for LAN/relay/VPN modes."
```

---

## Task 6: Frontend — Devices tab component

**Files:**
- Create: `frontend/src/lib/components/sync/DevicesTab.svelte`
- Create: `frontend/src/lib/components/sync/DeviceCard.svelte`
- Modify: `frontend/src/routes/sync/+page.svelte`

**Step 1: Create DeviceCard.svelte**

Create `frontend/src/lib/components/sync/DeviceCard.svelte`:

```svelte
<script lang="ts">
	import { Monitor, ChevronDown, ChevronRight, ArrowUp, ArrowDown, Lock, Pause, Copy, Trash2 } from 'lucide-svelte';

	interface Device {
		device_id: string;
		name: string;
		connected: boolean;
		address: string;
		type: string;
		crypto: string;
		in_bytes_total: number;
		out_bytes_total: number;
		is_self?: boolean;
	}

	let { device }: { device: Device } = $props();

	let expanded = $state(false);

	function formatBytes(bytes: number): string {
		if (bytes < 1024) return `${bytes} B`;
		if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
		if (bytes < 1024 * 1024 * 1024) return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
		return `${(bytes / (1024 * 1024 * 1024)).toFixed(1)} GB`;
	}

	let statusColor = $derived(
		device.is_self ? 'bg-green-500' : device.connected ? 'bg-green-500' : 'bg-gray-400'
	);
	let statusText = $derived(
		device.is_self ? 'Online' : device.connected ? 'Connected' : 'Disconnected'
	);
</script>

<div class="border border-[var(--border)] rounded-[var(--radius-lg)] bg-[var(--bg-base)] overflow-hidden">
	<!-- Header (always visible) -->
	<button
		onclick={() => (expanded = !expanded)}
		class="w-full flex items-center justify-between p-4 text-left hover:bg-[var(--bg-subtle)] transition-colors"
	>
		<div class="flex items-center gap-3">
			<Monitor size={16} class="text-[var(--text-muted)]" />
			<div>
				<div class="flex items-center gap-2">
					<span class="text-sm font-medium text-[var(--text-primary)]">
						{device.name}
					</span>
					{#if device.is_self}
						<span class="text-xs text-[var(--text-muted)]">(This Machine)</span>
					{/if}
				</div>
				<div class="flex items-center gap-3 mt-0.5">
					<span class="flex items-center gap-1 text-xs">
						<span class="w-1.5 h-1.5 rounded-full {statusColor}"></span>
						{statusText}
					</span>
					{#if device.connected && !device.is_self}
						<span class="text-xs text-[var(--text-muted)]">
							<ArrowUp size={10} class="inline" />
							{formatBytes(device.out_bytes_total)}
							<ArrowDown size={10} class="inline ml-1" />
							{formatBytes(device.in_bytes_total)}
						</span>
					{/if}
				</div>
			</div>
		</div>
		<div class="text-[var(--text-muted)]">
			{#if expanded}
				<ChevronDown size={16} />
			{:else}
				<ChevronRight size={16} />
			{/if}
		</div>
	</button>

	<!-- Expanded detail -->
	{#if expanded}
		<div class="border-t border-[var(--border)] p-4 space-y-4">
			<!-- Connection -->
			<div>
				<h4 class="text-xs font-medium text-[var(--text-muted)] uppercase tracking-wider mb-2">
					Connection
				</h4>
				<div class="grid grid-cols-2 gap-2 text-sm">
					<div>
						<span class="text-xs text-[var(--text-muted)]">Address</span>
						<p class="font-mono text-xs text-[var(--text-secondary)]">
							{device.address || 'N/A'}
						</p>
					</div>
					<div>
						<span class="text-xs text-[var(--text-muted)]">Type</span>
						<p class="text-xs text-[var(--text-secondary)]">{device.type || 'N/A'}</p>
					</div>
					<div>
						<span class="text-xs text-[var(--text-muted)]">Encryption</span>
						<p class="flex items-center gap-1 text-xs text-[var(--text-secondary)]">
							<Lock size={10} />
							{device.crypto || 'N/A'}
						</p>
					</div>
					<div>
						<span class="text-xs text-[var(--text-muted)]">Device ID</span>
						<p class="font-mono text-xs text-[var(--text-secondary)] truncate">
							{device.device_id.slice(0, 20)}...
						</p>
					</div>
				</div>
			</div>

			<!-- Transfer -->
			<div>
				<h4 class="text-xs font-medium text-[var(--text-muted)] uppercase tracking-wider mb-2">
					Transfer
				</h4>
				<div class="grid grid-cols-2 gap-2 text-sm">
					<div>
						<span class="text-xs text-[var(--text-muted)]">Total Sent</span>
						<p class="text-xs text-[var(--text-secondary)]">
							{formatBytes(device.out_bytes_total)}
						</p>
					</div>
					<div>
						<span class="text-xs text-[var(--text-muted)]">Total Received</span>
						<p class="text-xs text-[var(--text-secondary)]">
							{formatBytes(device.in_bytes_total)}
						</p>
					</div>
				</div>
			</div>
		</div>
	{/if}
</div>
```

**Step 2: Create DevicesTab.svelte**

Create `frontend/src/lib/components/sync/DevicesTab.svelte`:

```svelte
<script lang="ts">
	import { onMount, onDestroy } from 'svelte';
	import { API_BASE } from '$lib/config';
	import DeviceCard from './DeviceCard.svelte';
	import { Monitor } from 'lucide-svelte';

	interface DetectData {
		installed: boolean;
		running: boolean;
		version: string | null;
		device_id: string | null;
		uptime: number | null;
	}

	interface StatusData {
		configured: boolean;
		user_id?: string;
		machine_id?: string;
	}

	interface Device {
		device_id: string;
		name: string;
		connected: boolean;
		address: string;
		type: string;
		crypto: string;
		in_bytes_total: number;
		out_bytes_total: number;
		is_self?: boolean;
	}

	let { detect, status }: { detect: DetectData | null; status: StatusData | null } = $props();

	let devices = $state<Device[]>([]);
	let isLoading = $state(true);
	let error = $state<string | null>(null);
	let pollInterval: ReturnType<typeof setInterval>;

	async function loadDevices() {
		try {
			const res = await fetch(`${API_BASE}/sync/devices`);
			if (res.ok) {
				const data = await res.json();
				devices = data.devices;
				error = null;
			} else if (res.status === 503) {
				error = 'Syncthing is not running';
			}
		} catch {
			error = 'Failed to connect to API';
		} finally {
			isLoading = false;
		}
	}

	// Build "this machine" card from detect data
	let selfDevice = $derived.by((): Device | null => {
		if (!detect?.device_id) return null;
		return {
			device_id: detect.device_id,
			name: status?.machine_id || 'This Machine',
			connected: true,
			address: 'tcp://0.0.0.0:22000',
			type: 'Local',
			crypto: '',
			in_bytes_total: 0,
			out_bytes_total: 0,
			is_self: true,
		};
	});

	let allDevices = $derived.by(() => {
		const list: Device[] = [];
		if (selfDevice) list.push(selfDevice);
		list.push(...devices);
		return list;
	});

	onMount(() => {
		loadDevices();
		pollInterval = setInterval(loadDevices, 10000);
	});

	onDestroy(() => {
		clearInterval(pollInterval);
	});
</script>

<div class="space-y-4 py-4">
	{#if !detect?.running}
		<div class="text-center py-8 text-[var(--text-muted)]">
			<Monitor size={32} class="mx-auto mb-3 opacity-40" />
			<p>Syncthing is not running. Go to the Setup tab to get started.</p>
		</div>
	{:else if isLoading}
		<div class="space-y-3">
			{#each [1, 2] as _}
				<div class="h-20 bg-[var(--bg-muted)] rounded-[var(--radius-lg)] animate-pulse"></div>
			{/each}
		</div>
	{:else if error}
		<div class="text-center py-8 text-red-500">
			<p>{error}</p>
		</div>
	{:else}
		{#each allDevices as device}
			<DeviceCard {device} />
		{/each}
	{/if}
</div>
```

**Step 3: Wire into sync page**

Update `frontend/src/routes/sync/+page.svelte` — import and use DevicesTab:

```svelte
import DevicesTab from '$lib/components/sync/DevicesTab.svelte';

<TabsContent value="devices">
    <DevicesTab detect={data.detect} status={data.status} />
</TabsContent>
```

**Step 4: Verify it builds**

Run: `cd frontend && npm run check`

**Step 5: Commit**

```bash
git add frontend/src/lib/components/sync/DeviceCard.svelte frontend/src/lib/components/sync/DevicesTab.svelte frontend/src/routes/sync/+page.svelte
git commit -m "feat(frontend): implement Devices tab with expandable cards

Shows all paired devices with connection status, transfer stats,
address, encryption, and device ID. Polls every 10s for live updates.
Self-device shown first with 'This Machine' badge."
```

---

## Task 7: Frontend — Projects tab component

**Files:**
- Create: `frontend/src/lib/components/sync/ProjectsTab.svelte`
- Create: `frontend/src/lib/components/sync/ProjectRow.svelte`
- Modify: `frontend/src/routes/sync/+page.svelte`

**Step 1: Create ProjectRow.svelte**

Create `frontend/src/lib/components/sync/ProjectRow.svelte`:

```svelte
<script lang="ts">
	import { ChevronDown, ChevronRight, RefreshCw } from 'lucide-svelte';
	import { API_BASE } from '$lib/config';

	interface ProjectSync {
		name: string;
		encoded_name: string;
		local_session_count: number;
		synced: boolean;
		status: 'synced' | 'pending' | 'disabled';
		last_sync_at: string | null;
		machine_count: number;
		pending_count: number;
	}

	let { project }: { project: ProjectSync } = $props();

	let expanded = $state(false);
	let isSyncing = $state(false);
	let isToggling = $state(false);

	let statusColor = $derived.by(() => {
		if (!project.synced) return 'bg-gray-400';
		if (project.pending_count > 0) return 'bg-orange-500';
		return 'bg-green-500';
	});

	let statusText = $derived.by(() => {
		if (!project.synced) return 'Not syncing';
		if (project.pending_count > 0) return `${project.pending_count} pending`;
		return 'In sync';
	});

	function formatTimeAgo(iso: string | null): string {
		if (!iso) return 'Never';
		const diff = Date.now() - new Date(iso).getTime();
		const mins = Math.floor(diff / 60000);
		if (mins < 1) return 'just now';
		if (mins < 60) return `${mins}m ago`;
		const hours = Math.floor(mins / 60);
		if (hours < 24) return `${hours}h ago`;
		const days = Math.floor(hours / 24);
		return `${days}d ago`;
	}

	async function toggleSync() {
		isToggling = true;
		try {
			const action = project.synced ? 'disable' : 'enable';
			await fetch(`${API_BASE}/sync/projects/${encodeURIComponent(project.name)}/${action}`, {
				method: 'POST',
			});
			project.synced = !project.synced;
		} finally {
			isToggling = false;
		}
	}

	async function syncNow() {
		isSyncing = true;
		try {
			await fetch(
				`${API_BASE}/sync/projects/${encodeURIComponent(project.name)}/sync-now`,
				{ method: 'POST' }
			);
		} finally {
			isSyncing = false;
		}
	}
</script>

<div class="border-b border-[var(--border)] last:border-b-0">
	<!-- Row header -->
	<button
		onclick={() => project.synced && (expanded = !expanded)}
		class="w-full flex items-center gap-3 px-4 py-3 text-left hover:bg-[var(--bg-subtle)] transition-colors"
		disabled={!project.synced}
	>
		<!-- Toggle dot -->
		<button
			onclick|stopPropagation={toggleSync}
			disabled={isToggling}
			class="w-3 h-3 rounded-full border-2 {project.synced ? 'bg-[var(--accent)] border-[var(--accent)]' : 'border-[var(--border)]'} transition-colors flex-shrink-0"
			title={project.synced ? 'Disable sync' : 'Enable sync'}
		></button>

		<!-- Name + status -->
		<div class="flex-1 min-w-0">
			<div class="flex items-center gap-2">
				<span class="text-sm font-medium text-[var(--text-primary)] truncate">
					{project.name}
				</span>
				<span class="flex items-center gap-1 text-xs">
					<span class="w-1.5 h-1.5 rounded-full {statusColor}"></span>
					{statusText}
				</span>
			</div>
			{#if project.synced}
				<p class="text-xs text-[var(--text-muted)] mt-0.5">
					Last sync: {formatTimeAgo(project.last_sync_at)} &middot; {project.machine_count} machine{project.machine_count !== 1 ? 's' : ''}
				</p>
			{/if}
		</div>

		<!-- Session count -->
		<span class="text-xs text-[var(--text-muted)] flex-shrink-0">
			{project.local_session_count} sessions
		</span>

		<!-- Action button (only for synced projects with issues) -->
		{#if project.synced && project.pending_count > 0}
			<button
				onclick|stopPropagation={syncNow}
				disabled={isSyncing}
				class="flex items-center gap-1 px-2 py-1 text-xs font-medium rounded-[var(--radius)] bg-orange-500/10 text-orange-600 hover:bg-orange-500/20 transition-colors flex-shrink-0"
			>
				<RefreshCw size={10} class={isSyncing ? 'animate-spin' : ''} />
				Sync Now
			</button>
		{:else if !project.synced}
			<button
				onclick|stopPropagation={toggleSync}
				disabled={isToggling}
				class="px-2 py-1 text-xs font-medium rounded-[var(--radius)] bg-[var(--accent)]/10 text-[var(--accent)] hover:bg-[var(--accent)]/20 transition-colors flex-shrink-0"
			>
				Enable Sync
			</button>
		{/if}

		<!-- Expand chevron (only for synced projects) -->
		{#if project.synced}
			<span class="text-[var(--text-muted)] flex-shrink-0">
				{#if expanded}
					<ChevronDown size={14} />
				{:else}
					<ChevronRight size={14} />
				{/if}
			</span>
		{/if}
	</button>

	<!-- Expanded detail (Level 1) -->
	{#if expanded && project.synced}
		<div class="px-4 pb-4 pl-10">
			<p class="text-xs text-[var(--text-muted)] italic">
				Machine breakdown and file details will load here.
			</p>
		</div>
	{/if}
</div>
```

**Step 2: Create ProjectsTab.svelte**

Create `frontend/src/lib/components/sync/ProjectsTab.svelte`:

```svelte
<script lang="ts">
	import { onMount } from 'svelte';
	import { API_BASE } from '$lib/config';
	import ProjectRow from './ProjectRow.svelte';
	import { FolderGit2 } from 'lucide-svelte';

	interface ProjectSync {
		name: string;
		encoded_name: string;
		local_session_count: number;
		synced: boolean;
		status: 'synced' | 'pending' | 'disabled';
		last_sync_at: string | null;
		machine_count: number;
		pending_count: number;
	}

	let projects = $state<ProjectSync[]>([]);
	let isLoading = $state(true);
	let error = $state<string | null>(null);

	async function loadProjects() {
		try {
			const [projectsRes, syncRes] = await Promise.all([
				fetch(`${API_BASE}/projects`),
				fetch(`${API_BASE}/sync/projects`)
			]);

			if (projectsRes.ok) {
				const projectData = await projectsRes.json();
				const syncData = syncRes.ok ? await syncRes.json() : { folders: [] };
				const syncedFolders = new Set(
					syncData.folders.map((f: { folder_id: string }) => f.folder_id)
				);

				projects = projectData.map((p: { encoded_name: string; session_count: number; display_name?: string }) => ({
					name: p.display_name || p.encoded_name,
					encoded_name: p.encoded_name,
					local_session_count: p.session_count || 0,
					synced: syncedFolders.has(`karma-out-${p.encoded_name}`),
					status: 'synced' as const,
					last_sync_at: null,
					machine_count: 1,
					pending_count: 0,
				}));
			}
		} catch {
			error = 'Failed to load projects';
		} finally {
			isLoading = false;
		}
	}

	async function selectAll() {
		for (const project of projects) {
			if (!project.synced) {
				await fetch(
					`${API_BASE}/sync/projects/${encodeURIComponent(project.name)}/enable`,
					{ method: 'POST' }
				);
				project.synced = true;
			}
		}
	}

	onMount(loadProjects);
</script>

<div class="py-4">
	{#if isLoading}
		<div class="space-y-2">
			{#each [1, 2, 3] as _}
				<div class="h-14 bg-[var(--bg-muted)] rounded-[var(--radius)] animate-pulse"></div>
			{/each}
		</div>
	{:else if error}
		<div class="text-center py-8 text-red-500">
			<p>{error}</p>
		</div>
	{:else if projects.length === 0}
		<div class="text-center py-8 text-[var(--text-muted)]">
			<FolderGit2 size={32} class="mx-auto mb-3 opacity-40" />
			<p>No projects found. Start a Claude Code session first.</p>
		</div>
	{:else}
		<div class="flex justify-end mb-3">
			<button
				onclick={selectAll}
				class="text-xs font-medium text-[var(--accent)] hover:underline"
			>
				Select All
			</button>
		</div>

		<div
			class="border border-[var(--border)] rounded-[var(--radius-lg)] overflow-hidden bg-[var(--bg-base)]"
		>
			{#each projects as project}
				<ProjectRow {project} />
			{/each}
		</div>
	{/if}
</div>
```

**Step 3: Wire into sync page**

Update `frontend/src/routes/sync/+page.svelte`:

```svelte
import ProjectsTab from '$lib/components/sync/ProjectsTab.svelte';

<TabsContent value="projects">
    <ProjectsTab />
</TabsContent>
```

**Step 4: Verify it builds**

Run: `cd frontend && npm run check`

**Step 5: Commit**

```bash
git add frontend/src/lib/components/sync/ProjectRow.svelte frontend/src/lib/components/sync/ProjectsTab.svelte frontend/src/routes/sync/+page.svelte
git commit -m "feat(frontend): implement Projects tab with toggle + disclosure

Per-project rows with sync toggle, status badges, action buttons.
Expandable rows for machine breakdown. Select All for bulk enable."
```

---

## Task 8: Frontend — Activity tab with bandwidth chart and event log

**Files:**
- Create: `frontend/src/lib/components/sync/ActivityTab.svelte`
- Create: `frontend/src/lib/components/sync/BandwidthChart.svelte`
- Modify: `frontend/src/routes/sync/+page.svelte`

**Step 1: Create BandwidthChart.svelte**

Create `frontend/src/lib/components/sync/BandwidthChart.svelte`:

```svelte
<script lang="ts">
	import { onMount, onDestroy } from 'svelte';
	import { Chart, LineController, LineElement, PointElement, LinearScale, CategoryScale, Filler, Tooltip } from 'chart.js';
	import { registerChartDefaults, getThemeColors, createResponsiveConfig } from '$lib/components/charts/chartConfig';

	Chart.register(LineController, LineElement, PointElement, LinearScale, CategoryScale, Filler, Tooltip);

	let { uploadData = [], downloadData = [], labels = [] }: {
		uploadData: number[];
		downloadData: number[];
		labels: string[];
	} = $props();

	let canvas: HTMLCanvasElement;
	let chart: Chart | null = null;

	onMount(() => {
		registerChartDefaults();
		const colors = getThemeColors();

		chart = new Chart(canvas, {
			type: 'line',
			data: {
				labels,
				datasets: [
					{
						label: 'Upload',
						data: uploadData,
						borderColor: '#7c3aed',
						backgroundColor: 'rgba(124, 58, 237, 0.1)',
						fill: true,
						tension: 0.3,
						pointRadius: 0,
						borderWidth: 1.5,
					},
					{
						label: 'Download',
						data: downloadData,
						borderColor: '#3b82f6',
						backgroundColor: 'rgba(59, 130, 246, 0.1)',
						fill: true,
						tension: 0.3,
						pointRadius: 0,
						borderWidth: 1.5,
					},
				],
			},
			options: {
				...createResponsiveConfig(false),
				scales: {
					x: { display: false },
					y: {
						display: true,
						grid: { color: colors.border },
						ticks: {
							callback: (value) => {
								const num = Number(value);
								if (num >= 1048576) return `${(num / 1048576).toFixed(0)} MB/s`;
								if (num >= 1024) return `${(num / 1024).toFixed(0)} KB/s`;
								return `${num} B/s`;
							},
							maxTicksLimit: 4,
						},
					},
				},
				plugins: {
					legend: { display: false },
				},
			},
		});
	});

	$effect(() => {
		if (chart) {
			chart.data.labels = labels;
			chart.data.datasets[0].data = uploadData;
			chart.data.datasets[1].data = downloadData;
			chart.update('none');
		}
	});

	onDestroy(() => {
		chart?.destroy();
	});
</script>

<div class="h-[120px]">
	<canvas bind:this={canvas}></canvas>
</div>
```

**Step 2: Create ActivityTab.svelte**

Create `frontend/src/lib/components/sync/ActivityTab.svelte`:

```svelte
<script lang="ts">
	import { onMount, onDestroy } from 'svelte';
	import { API_BASE } from '$lib/config';
	import BandwidthChart from './BandwidthChart.svelte';
	import { ArrowUp, ArrowDown, Activity } from 'lucide-svelte';

	interface SyncEvent {
		id: number;
		type: string;
		time: string;
		data: Record<string, unknown>;
	}

	let events = $state<SyncEvent[]>([]);
	let isLoading = $state(true);
	let error = $state<string | null>(null);
	let lastEventId = $state(0);
	let pollInterval: ReturnType<typeof setInterval>;

	// Bandwidth chart data (placeholder — real data from events)
	let uploadData = $state<number[]>(Array(60).fill(0));
	let downloadData = $state<number[]>(Array(60).fill(0));
	let chartLabels = $state<string[]>(Array(60).fill(''));

	let filterType = $state('all');
	let filterDevice = $state('all');

	async function loadEvents() {
		try {
			const res = await fetch(`${API_BASE}/sync/activity?since=${lastEventId}&limit=50`);
			if (res.ok) {
				const data = await res.json();
				if (data.events.length > 0) {
					events = [...data.events, ...events].slice(0, 200);
					lastEventId = data.events[0]?.id ?? lastEventId;
				}
				error = null;
			} else if (res.status === 503) {
				error = 'Syncthing is not running';
			}
		} catch {
			error = 'Failed to connect to API';
		} finally {
			isLoading = false;
		}
	}

	let filteredEvents = $derived.by(() => {
		return events.filter((e) => {
			if (filterType !== 'all') {
				const typeMap: Record<string, string[]> = {
					transfers: ['ItemFinished', 'DownloadProgress'],
					connections: ['DeviceConnected', 'DeviceDisconnected'],
					conflicts: ['LocalChangeDetected'],
					errors: ['FolderErrors'],
				};
				if (typeMap[filterType] && !typeMap[filterType].includes(e.type)) return false;
			}
			return true;
		});
	});

	function getEventDot(type: string): string {
		const map: Record<string, string> = {
			ItemFinished: 'bg-green-500',
			DownloadProgress: 'bg-blue-500',
			DeviceConnected: 'bg-green-500',
			DeviceDisconnected: 'bg-gray-400',
			LocalChangeDetected: 'bg-orange-500',
			FolderErrors: 'bg-red-500',
			StateChanged: 'bg-gray-400',
		};
		return map[type] || 'bg-gray-400';
	}

	function getEventLabel(type: string): string {
		const map: Record<string, string> = {
			ItemFinished: 'Transfer complete',
			DownloadProgress: 'Transfer in progress',
			DeviceConnected: 'Device connected',
			DeviceDisconnected: 'Device disconnected',
			LocalChangeDetected: 'Local change detected',
			FolderErrors: 'Folder error',
			StateChanged: 'State changed',
			FolderCompletion: 'Folder sync progress',
			FolderSummary: 'Scan completed',
		};
		return map[type] || type;
	}

	function formatTime(iso: string): string {
		return new Date(iso).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
	}

	onMount(() => {
		loadEvents();
		pollInterval = setInterval(loadEvents, 5000);
	});

	onDestroy(() => {
		clearInterval(pollInterval);
	});
</script>

<div class="space-y-6 py-4">
	<!-- Bandwidth Chart -->
	<div class="border border-[var(--border)] rounded-[var(--radius-lg)] p-4 bg-[var(--bg-base)]">
		<div class="flex items-center justify-between mb-3">
			<h3 class="text-xs font-medium text-[var(--text-muted)] uppercase tracking-wider">
				Bandwidth
			</h3>
			<div class="flex items-center gap-4 text-xs text-[var(--text-muted)]">
				<span class="flex items-center gap-1">
					<ArrowUp size={10} class="text-purple-500" />
					<span class="text-purple-500">Upload</span>
				</span>
				<span class="flex items-center gap-1">
					<ArrowDown size={10} class="text-blue-500" />
					<span class="text-blue-500">Download</span>
				</span>
			</div>
		</div>
		<BandwidthChart {uploadData} {downloadData} labels={chartLabels} />
	</div>

	<!-- Event Log -->
	<div class="border border-[var(--border)] rounded-[var(--radius-lg)] bg-[var(--bg-base)]">
		<div class="flex items-center justify-between p-4 border-b border-[var(--border)]">
			<h3 class="text-xs font-medium text-[var(--text-muted)] uppercase tracking-wider">
				Event Log
			</h3>
			<div class="flex gap-2">
				<select
					bind:value={filterType}
					class="text-xs px-2 py-1 rounded-[var(--radius)] border border-[var(--border)] bg-[var(--bg-subtle)] text-[var(--text-secondary)]"
				>
					<option value="all">All types</option>
					<option value="transfers">Transfers</option>
					<option value="connections">Connections</option>
					<option value="conflicts">Conflicts</option>
					<option value="errors">Errors</option>
				</select>
			</div>
		</div>

		<div class="divide-y divide-[var(--border)]">
			{#if isLoading}
				<div class="p-4 text-center text-[var(--text-muted)] text-sm">Loading events...</div>
			{:else if error}
				<div class="p-4 text-center text-red-500 text-sm">{error}</div>
			{:else if filteredEvents.length === 0}
				<div class="p-8 text-center text-[var(--text-muted)]">
					<Activity size={24} class="mx-auto mb-2 opacity-40" />
					<p class="text-sm">No events yet</p>
				</div>
			{:else}
				{#each filteredEvents as event}
					<div class="flex gap-3 px-4 py-3">
						<span
							class="w-2 h-2 rounded-full mt-1.5 flex-shrink-0 {getEventDot(event.type)}"
						></span>
						<div class="min-w-0 flex-1">
							<div class="flex items-center gap-2">
								<span class="text-xs text-[var(--text-muted)]">
									{formatTime(event.time)}
								</span>
								<span class="text-sm font-medium text-[var(--text-primary)]">
									{getEventLabel(event.type)}
								</span>
							</div>
							{#if event.data}
								<p class="text-xs text-[var(--text-muted)] mt-0.5 truncate">
									{JSON.stringify(event.data).slice(0, 100)}
								</p>
							{/if}
						</div>
					</div>
				{/each}
			{/if}
		</div>
	</div>
</div>
```

**Step 3: Wire into sync page**

Update `frontend/src/routes/sync/+page.svelte`:

```svelte
import ActivityTab from '$lib/components/sync/ActivityTab.svelte';

<TabsContent value="activity">
    <ActivityTab />
</TabsContent>
```

**Step 4: Verify it builds**

Run: `cd frontend && npm run check`

**Step 5: Commit**

```bash
git add frontend/src/lib/components/sync/BandwidthChart.svelte frontend/src/lib/components/sync/ActivityTab.svelte frontend/src/routes/sync/+page.svelte
git commit -m "feat(frontend): implement Activity tab with bandwidth chart + event log

Chart.js sparkline for upload/download bandwidth. Filterable event log
with color-coded dots per event type. Polls every 5s for new events."
```

---

## Task 9: Backend — POST /sync/init endpoint

The Setup tab needs `POST /sync/init` to run `karma init`. This executes the CLI command via subprocess.

**Files:**
- Modify: `api/routers/sync_status.py`
- Test: `api/tests/api/test_sync_status.py`

**Step 1: Write failing test**

Add to `api/tests/api/test_sync_status.py`:

```python
class TestSyncInit:
    def test_init_success(self):
        """POST /sync/init runs karma init."""
        with patch("routers.sync_status.run_karma_command") as mock_run:
            mock_run.return_value = {"success": True, "output": "Initialized"}
            with patch("routers.sync_status.get_proxy") as mock_get:
                mock_proxy = MagicMock()
                mock_proxy.detect.return_value = {
                    "installed": True,
                    "running": True,
                    "version": "v1.27.0",
                    "device_id": "DEVICE-123",
                }
                mock_get.return_value = mock_proxy

                resp = client.post(
                    "/sync/init",
                    json={"machine_name": "my-macbook"},
                )
                assert resp.status_code == 200
                data = resp.json()
                assert data["success"] is True
```

**Step 2: Run test to verify it fails**

Run: `cd api && python -m pytest tests/api/test_sync_status.py::TestSyncInit -v`

**Step 3: Add the endpoint and helper**

Add to `api/routers/sync_status.py`:

```python
import subprocess
import shutil


class InitRequest(BaseModel):
    machine_name: str


def run_karma_command(args: list[str]) -> dict[str, Any]:
    """Execute a karma CLI command and return result."""
    karma_path = shutil.which("karma")
    if not karma_path:
        # Try the local CLI directory
        cli_path = Path(__file__).parent.parent.parent / "cli"
        karma_path = str(cli_path / "karma" / "main.py")

    try:
        result = subprocess.run(
            ["python", "-m", "karma"] + args if not shutil.which("karma") else ["karma"] + args,
            capture_output=True,
            text=True,
            timeout=30,
            cwd=str(Path.home()),
        )
        return {
            "success": result.returncode == 0,
            "output": result.stdout.strip(),
            "error": result.stderr.strip() if result.returncode != 0 else None,
        }
    except subprocess.TimeoutExpired:
        return {"success": False, "output": "", "error": "Command timed out"}
    except FileNotFoundError:
        return {"success": False, "output": "", "error": "karma CLI not found"}


@router.post("/init")
async def sync_init(req: InitRequest):
    """Initialize sync with karma CLI."""
    result = run_karma_command(["init", "--backend", "syncthing", "--machine-name", req.machine_name])
    if result["success"]:
        # Refresh proxy to pick up new config
        global _proxy
        _proxy = None

        proxy = get_proxy()
        detect = proxy.detect()
        return {
            "success": True,
            "device_id": detect.get("device_id"),
            "machine_name": req.machine_name,
        }
    return {"success": False, "error": result.get("error", "Initialization failed")}
```

**Step 4: Run tests**

Run: `cd api && python -m pytest tests/api/test_sync_status.py -v`

**Step 5: Commit**

```bash
git add api/routers/sync_status.py api/tests/api/test_sync_status.py
git commit -m "feat(api): add POST /sync/init endpoint for CLI initialization

Executes karma init via subprocess, returns device ID on success.
Resets proxy singleton to pick up new configuration."
```

---

## Task 10: Backend — Project enable/disable + sync-now endpoints

**Files:**
- Modify: `api/routers/sync_status.py`
- Test: `api/tests/api/test_sync_status.py`

**Step 1: Write failing tests**

```python
class TestSyncProjectActions:
    def test_enable_project_sync(self):
        """POST /sync/projects/{name}/enable starts syncing."""
        with patch("routers.sync_status.run_karma_command") as mock_run:
            mock_run.return_value = {"success": True, "output": "Enabled"}
            resp = client.post("/sync/projects/my-project/enable")
            assert resp.status_code == 200
            assert resp.json()["success"] is True

    def test_disable_project_sync(self):
        """POST /sync/projects/{name}/disable stops syncing."""
        with patch("routers.sync_status.run_karma_command") as mock_run:
            mock_run.return_value = {"success": True, "output": "Disabled"}
            resp = client.post("/sync/projects/my-project/disable")
            assert resp.status_code == 200
            assert resp.json()["success"] is True

    def test_sync_now(self):
        """POST /sync/projects/{name}/sync-now triggers manual sync."""
        with patch("routers.sync_status.run_karma_command") as mock_run:
            mock_run.return_value = {"success": True, "output": "Synced 5 sessions"}
            resp = client.post("/sync/projects/my-project/sync-now")
            assert resp.status_code == 200
            assert resp.json()["success"] is True
```

**Step 2: Add endpoints**

```python
@router.post("/projects/{name}/enable")
async def enable_project_sync(name: str):
    """Enable sync for a project."""
    result = run_karma_command(["project", "add", name])
    return {"success": result["success"], "error": result.get("error")}


@router.post("/projects/{name}/disable")
async def disable_project_sync(name: str):
    """Disable sync for a project."""
    result = run_karma_command(["project", "remove", name])
    return {"success": result["success"], "error": result.get("error")}


@router.post("/projects/{name}/sync-now")
async def sync_project_now(name: str):
    """Trigger manual sync for a project."""
    result = run_karma_command(["sync", name])
    return {"success": result["success"], "output": result.get("output"), "error": result.get("error")}


@router.post("/watcher/restart")
async def restart_watcher():
    """Restart the file watcher."""
    result = run_karma_command(["watch"])
    return {"success": result["success"], "error": result.get("error")}
```

**Step 3: Run tests**

Run: `cd api && python -m pytest tests/api/test_sync_status.py -v`

**Step 4: Lint**

Run: `cd api && ruff check routers/sync_status.py && ruff format routers/sync_status.py`

**Step 5: Commit**

```bash
git add api/routers/sync_status.py api/tests/api/test_sync_status.py
git commit -m "feat(api): add project enable/disable/sync-now and watcher endpoints

POST endpoints that execute karma CLI commands for per-project sync
control and manual sync triggers."
```

---

## Task 11: Full verification

**Step 1: Run all API tests**

Run: `cd api && python -m pytest tests/ -v --timeout=30`
Expected: All PASS

**Step 2: Run frontend type check**

Run: `cd frontend && npm run check`
Expected: No errors

**Step 3: Run frontend lint**

Run: `cd frontend && npm run lint`
Expected: No errors

**Step 4: Manual smoke test**

1. Start API: `cd api && uvicorn main:app --reload --port 8000`
2. Start frontend: `cd frontend && npm run dev`
3. Navigate to `http://localhost:5173/sync`
4. Verify:
   - Tab bar renders with 4 tabs
   - Setup tab shows backend selection + install/detect state
   - Devices tab shows loading or "not running" state
   - Projects tab lists local projects
   - Activity tab shows empty event log with bandwidth chart
   - Tab state persists in URL
   - "Sync" appears in header nav

---

## Summary

| Task | What | Files | Priority |
|------|------|-------|----------|
| 1 | Syncthing proxy service | `services/syncthing_proxy.py` | High |
| 2 | Expand /sync router | `routers/sync_status.py` | High |
| 3 | /sync route shell + tabs | `routes/sync/+page.*` | High |
| 4 | Navigation update | `Header.svelte`, `+layout.svelte` | High |
| 5 | Setup tab | `sync/SetupTab.svelte` | High |
| 6 | Devices tab | `sync/DevicesTab.svelte`, `DeviceCard.svelte` | High |
| 7 | Projects tab | `sync/ProjectsTab.svelte`, `ProjectRow.svelte` | High |
| 8 | Activity tab | `sync/ActivityTab.svelte`, `BandwidthChart.svelte` | High |
| 9 | POST /sync/init | `routers/sync_status.py` | High |
| 10 | Project enable/disable/sync-now | `routers/sync_status.py` | High |
| 11 | Full verification | — | Required |

**Not in scope (future tasks):**
- SSE streaming for real-time events (polling is MVP)
- Conflict resolution UI (detect only in MVP)
- Network mode persistence via `PUT /sync/config` (radio buttons disabled with "coming soon" in MVP)
- Per-file sync status in Projects tab L2 (placeholder in MVP)
- IPFS backend (greyed out)
- QR code for device ID sharing (MVP uses copy/paste)
- `karma sync` for Syncthing (IPFS-only; Syncthing uses packager + auto-sync)

**Required reading before implementation:**
- Architecture Review Amendments (above) — apply all corrections as you implement each task
- Design Token Mapping in `docs/plans/2026-03-05-sync-page-ui-design.md`
- `cli/karma/main.py` — actual CLI command signatures
- `cli/karma/syncthing.py` — actual SyncthingClient API (no `get_system_status()`, no `_session`, `headers` not `_headers`)
