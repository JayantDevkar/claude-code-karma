# Sync v4 Phase 2: Infrastructure — Syncthing Abstraction + Pairing

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.
>
> **TDD SKILL:** Use `oh-my-claudecode:tdd` or `superpowers:test-driven-development` for every task.

**Goal:** Build the Syncthing HTTP abstraction (client, device manager, folder manager) and the pairing code service.

**Architecture:** SyncthingClient is a pure HTTP wrapper (no business logic). DeviceManager and FolderManager use SyncthingClient for device/folder operations. PairingService encodes/decodes member identity into shareable codes.

**Tech Stack:** Python 3.9+, httpx (async HTTP), pytest, base32 encoding

**Spec:** `docs/superpowers/specs/2026-03-17-sync-v4-domain-models-design.md` (sections: Syncthing Abstraction, Pairing Codes)

**Parent Plan:** `docs/superpowers/plans/2026-03-17-sync-v4-master.md`

**CAN RUN IN PARALLEL WITH PHASE 1** — no shared dependencies.

---

## Task Dependency Graph

```
Task 1 (SyncthingClient) ──→ Task 2 (DeviceManager)  ──→ Task 5 (Integration)
                          ──→ Task 3 (FolderManager)  ──↗
Task 4 (PairingService) ─── INDEPENDENT ────────────────↗
```

---

### Task 1: SyncthingClient — Pure HTTP Wrapper

**Files:**
- Create: `api/services/syncthing/__init__.py`
- Create: `api/services/syncthing/client.py`
- Test: `api/tests/test_syncthing_client.py`

**Reference:** Existing `api/services/syncthing_proxy.py` for Syncthing REST API patterns. The new client extracts ONLY the HTTP calls — no business logic.

- [ ] **Step 1: Write failing tests**

```python
# api/tests/test_syncthing_client.py
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from services.syncthing.client import SyncthingClient


@pytest.fixture
def client():
    return SyncthingClient(api_url="http://localhost:8384", api_key="test-key")


class TestSyncthingClientConfig:
    def test_init(self, client):
        assert client.api_url == "http://localhost:8384"
        assert client.api_key == "test-key"

    def test_headers_include_api_key(self, client):
        headers = client._headers()
        assert headers["X-API-Key"] == "test-key"


class TestSyncthingClientSystemEndpoints:
    @pytest.mark.asyncio
    async def test_get_system_status(self, client):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"myID": "DEVICE-ID-123"}

        with patch.object(client, "_get", new_callable=AsyncMock, return_value=mock_response.json.return_value):
            result = await client.get_system_status()
            assert result["myID"] == "DEVICE-ID-123"

    @pytest.mark.asyncio
    async def test_get_connections(self, client):
        with patch.object(client, "_get", new_callable=AsyncMock, return_value={"connections": {}}):
            result = await client.get_connections()
            assert "connections" in result


class TestSyncthingClientConfigEndpoints:
    @pytest.mark.asyncio
    async def test_get_config(self, client):
        mock_config = {"devices": [], "folders": []}
        with patch.object(client, "_get", new_callable=AsyncMock, return_value=mock_config):
            result = await client.get_config()
            assert "devices" in result
            assert "folders" in result

    @pytest.mark.asyncio
    async def test_post_config(self, client):
        with patch.object(client, "_put", new_callable=AsyncMock) as mock_put:
            await client.post_config({"devices": [], "folders": []})
            mock_put.assert_called_once()


class TestSyncthingClientPendingEndpoints:
    @pytest.mark.asyncio
    async def test_get_pending_devices(self, client):
        with patch.object(client, "_get", new_callable=AsyncMock, return_value={}):
            result = await client.get_pending_devices()
            assert isinstance(result, dict)

    @pytest.mark.asyncio
    async def test_get_pending_folders(self, client):
        with patch.object(client, "_get", new_callable=AsyncMock, return_value={}):
            result = await client.get_pending_folders()
            assert isinstance(result, dict)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd api && pytest tests/test_syncthing_client.py -v`
Expected: FAIL — `No module named 'services.syncthing'`

- [ ] **Step 3: Implement SyncthingClient**

```python
# api/services/syncthing/__init__.py
"""Syncthing abstraction layer — HTTP client, device manager, folder manager."""

# api/services/syncthing/client.py
"""Pure HTTP wrapper for Syncthing REST API. No business logic."""
from __future__ import annotations

import httpx


class SyncthingClient:
    """Maps 1:1 to Syncthing REST API endpoints."""

    def __init__(self, api_url: str, api_key: str, timeout: float = 30.0):
        self.api_url = api_url.rstrip("/")
        self.api_key = api_key
        self.timeout = timeout

    def _headers(self) -> dict[str, str]:
        return {"X-API-Key": self.api_key}

    async def _get(self, path: str) -> dict:
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            resp = await client.get(
                f"{self.api_url}{path}", headers=self._headers()
            )
            resp.raise_for_status()
            return resp.json()

    async def _put(self, path: str, data: dict) -> None:
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            resp = await client.put(
                f"{self.api_url}{path}", headers=self._headers(), json=data
            )
            resp.raise_for_status()

    async def _post(self, path: str, data: dict = None) -> dict | None:
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            resp = await client.post(
                f"{self.api_url}{path}", headers=self._headers(), json=data
            )
            resp.raise_for_status()
            if resp.content:
                return resp.json()
            return None

    async def _delete(self, path: str, params: dict = None) -> None:
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            resp = await client.delete(
                f"{self.api_url}{path}", headers=self._headers(), params=params
            )
            resp.raise_for_status()

    # --- System endpoints ---
    async def get_system_status(self) -> dict:
        return await self._get("/rest/system/status")

    async def get_connections(self) -> dict:
        return await self._get("/rest/system/connections")

    # --- Config endpoints ---
    async def get_config(self) -> dict:
        return await self._get("/rest/config")

    async def post_config(self, config: dict) -> None:
        await self._put("/rest/config", config)

    async def get_config_devices(self) -> list[dict]:
        return await self._get("/rest/config/devices")

    async def put_config_device(self, device: dict) -> None:
        await self._put(f"/rest/config/devices/{device['deviceID']}", device)

    async def delete_config_device(self, device_id: str) -> None:
        await self._delete(f"/rest/config/devices/{device_id}")

    async def get_config_folders(self) -> list[dict]:
        return await self._get("/rest/config/folders")

    async def put_config_folder(self, folder: dict) -> None:
        await self._put(f"/rest/config/folders/{folder['id']}", folder)

    async def delete_config_folder(self, folder_id: str) -> None:
        await self._delete(f"/rest/config/folders/{folder_id}")

    # --- Pending endpoints ---
    async def get_pending_devices(self) -> dict:
        return await self._get("/rest/cluster/pending/devices")

    async def get_pending_folders(self) -> dict:
        return await self._get("/rest/cluster/pending/folders")

    # --- Folder status ---
    async def get_folder_status(self, folder_id: str) -> dict:
        return await self._get(f"/rest/db/status?folder={folder_id}")

    async def post_folder_rescan(self, folder_id: str) -> None:
        await self._post(f"/rest/db/scan?folder={folder_id}")

    # --- Bandwidth ---
    async def get_system_connections(self) -> dict:
        return await self._get("/rest/system/connections")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd api && pytest tests/test_syncthing_client.py -v`
Expected: ALL PASS

- [ ] **Step 5: Commit**

```bash
git add api/services/syncthing/__init__.py api/services/syncthing/client.py api/tests/test_syncthing_client.py
git commit -m "feat(sync-v4): add SyncthingClient — pure HTTP wrapper"
```

---

### Task 2: DeviceManager

**Files:**
- Create: `api/services/syncthing/device_manager.py`
- Test: `api/tests/test_device_manager.py`

**CAN PARALLEL with Task 3. Depends on Task 1.**

- [ ] **Step 1: Write failing tests**

```python
# api/tests/test_device_manager.py
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
from unittest.mock import AsyncMock, MagicMock
from services.syncthing.device_manager import DeviceManager


@pytest.fixture
def mock_client():
    client = MagicMock()
    client.get_config = AsyncMock(return_value={
        "devices": [
            {"deviceID": "DEV-1", "name": "jayant-macbook"},
            {"deviceID": "DEV-2", "name": "ayush-laptop"},
        ],
        "folders": [],
    })
    client.put_config_device = AsyncMock()
    client.delete_config_device = AsyncMock()
    client.get_connections = AsyncMock(return_value={
        "connections": {
            "DEV-1": {"connected": True},
            "DEV-2": {"connected": False},
        }
    })
    return client


@pytest.fixture
def manager(mock_client):
    return DeviceManager(mock_client)


class TestDevicePairing:
    @pytest.mark.asyncio
    async def test_pair_adds_device(self, manager, mock_client):
        mock_client.get_config = AsyncMock(return_value={"devices": [], "folders": []})
        await manager.pair("DEV-NEW")
        mock_client.put_config_device.assert_called_once()
        call_data = mock_client.put_config_device.call_args[0][0]
        assert call_data["deviceID"] == "DEV-NEW"

    @pytest.mark.asyncio
    async def test_ensure_paired_skips_existing(self, manager, mock_client):
        await manager.ensure_paired("DEV-1")  # already in config
        mock_client.put_config_device.assert_not_called()

    @pytest.mark.asyncio
    async def test_ensure_paired_adds_missing(self, manager, mock_client):
        await manager.ensure_paired("DEV-NEW")
        mock_client.put_config_device.assert_called_once()


class TestDeviceUnpairing:
    @pytest.mark.asyncio
    async def test_unpair_removes_device(self, manager, mock_client):
        await manager.unpair("DEV-1")
        mock_client.delete_config_device.assert_called_once_with("DEV-1")


class TestDeviceConnection:
    @pytest.mark.asyncio
    async def test_is_connected_true(self, manager):
        assert await manager.is_connected("DEV-1") is True

    @pytest.mark.asyncio
    async def test_is_connected_false(self, manager):
        assert await manager.is_connected("DEV-2") is False

    @pytest.mark.asyncio
    async def test_is_connected_unknown(self, manager):
        assert await manager.is_connected("DEV-UNKNOWN") is False

    @pytest.mark.asyncio
    async def test_list_connected(self, manager):
        connected = await manager.list_connected()
        assert connected == ["DEV-1"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd api && pytest tests/test_device_manager.py -v`
Expected: FAIL

- [ ] **Step 3: Implement DeviceManager**

```python
# api/services/syncthing/device_manager.py
"""Device pairing operations using SyncthingClient."""
from __future__ import annotations

from services.syncthing.client import SyncthingClient


class DeviceManager:
    def __init__(self, client: SyncthingClient):
        self.client = client

    async def _get_device_ids(self) -> set[str]:
        config = await self.client.get_config()
        return {d["deviceID"] for d in config.get("devices", [])}

    async def pair(self, device_id: str, name: str = "") -> None:
        """Add a device to Syncthing config."""
        await self.client.put_config_device({
            "deviceID": device_id,
            "name": name,
            "addresses": ["dynamic"],
            "autoAcceptFolders": False,
        })

    async def unpair(self, device_id: str) -> None:
        """Remove a device from Syncthing config."""
        await self.client.delete_config_device(device_id)

    async def ensure_paired(self, device_id: str, name: str = "") -> None:
        """Pair if not already paired. Idempotent."""
        known = await self._get_device_ids()
        if device_id not in known:
            await self.pair(device_id, name)

    async def is_connected(self, device_id: str) -> bool:
        """Check if a device is currently connected."""
        conns = await self.client.get_connections()
        device_info = conns.get("connections", {}).get(device_id, {})
        return device_info.get("connected", False)

    async def list_connected(self) -> list[str]:
        """List all currently connected device IDs."""
        conns = await self.client.get_connections()
        return [
            did for did, info in conns.get("connections", {}).items()
            if info.get("connected", False)
        ]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd api && pytest tests/test_device_manager.py -v`
Expected: ALL PASS

- [ ] **Step 5: Commit**

```bash
git add api/services/syncthing/device_manager.py api/tests/test_device_manager.py
git commit -m "feat(sync-v4): add DeviceManager — pair/unpair/connection status"
```

---

### Task 3: FolderManager

**Files:**
- Create: `api/services/syncthing/folder_manager.py`
- Test: `api/tests/test_folder_manager.py`

**CAN PARALLEL with Task 2. Depends on Task 1.**

- [ ] **Step 1: Write failing tests**

```python
# api/tests/test_folder_manager.py
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
from unittest.mock import AsyncMock, MagicMock
from services.syncthing.folder_manager import FolderManager


@pytest.fixture
def mock_client():
    client = MagicMock()
    client.get_config = AsyncMock(return_value={
        "devices": [],
        "folders": [
            {"id": "karma-out--jayant.macbook--owner-repo", "devices": [{"deviceID": "DEV-1"}]},
        ],
    })
    client.put_config_folder = AsyncMock()
    client.delete_config_folder = AsyncMock()
    client.get_config_folders = AsyncMock(return_value=[
        {"id": "karma-out--jayant.macbook--owner-repo", "devices": [{"deviceID": "DEV-1"}]},
    ])
    return client


@pytest.fixture
def manager(mock_client):
    return FolderManager(mock_client, karma_base=Path("/tmp/test-karma"))


class TestEnsureOutboxFolder:
    @pytest.mark.asyncio
    async def test_creates_outbox_folder(self, manager, mock_client):
        mock_client.get_config_folders = AsyncMock(return_value=[])
        await manager.ensure_outbox_folder(
            member_tag="jayant.macbook",
            folder_suffix="owner-repo",
        )
        mock_client.put_config_folder.assert_called_once()
        folder = mock_client.put_config_folder.call_args[0][0]
        assert folder["id"] == "karma-out--jayant.macbook--owner-repo"
        assert folder["type"] == "sendonly"

    @pytest.mark.asyncio
    async def test_skips_existing_outbox(self, manager, mock_client):
        await manager.ensure_outbox_folder(
            member_tag="jayant.macbook",
            folder_suffix="owner-repo",
        )
        mock_client.put_config_folder.assert_not_called()


class TestEnsureInboxFolder:
    @pytest.mark.asyncio
    async def test_creates_inbox_folder(self, manager, mock_client):
        mock_client.get_config_folders = AsyncMock(return_value=[])
        await manager.ensure_inbox_folder(
            remote_member_tag="ayush.laptop",
            folder_suffix="owner-repo",
            remote_device_id="DEV-A",
        )
        mock_client.put_config_folder.assert_called_once()
        folder = mock_client.put_config_folder.call_args[0][0]
        assert folder["id"] == "karma-out--ayush.laptop--owner-repo"
        assert folder["type"] == "receiveonly"


class TestSetFolderDevices:
    @pytest.mark.asyncio
    async def test_set_folder_devices_replaces_list(self, manager, mock_client):
        await manager.set_folder_devices(
            "karma-out--jayant.macbook--owner-repo",
            {"DEV-1", "DEV-2", "DEV-3"},
        )
        mock_client.put_config_folder.assert_called_once()
        folder = mock_client.put_config_folder.call_args[0][0]
        device_ids = {d["deviceID"] for d in folder["devices"]}
        assert device_ids == {"DEV-1", "DEV-2", "DEV-3"}


class TestRemoveOutboxFolder:
    @pytest.mark.asyncio
    async def test_removes_folder(self, manager, mock_client):
        await manager.remove_outbox_folder(
            member_tag="jayant.macbook",
            folder_suffix="owner-repo",
        )
        mock_client.delete_config_folder.assert_called_once_with(
            "karma-out--jayant.macbook--owner-repo"
        )


class TestCleanupTeamFolders:
    @pytest.mark.asyncio
    async def test_cleanup_removes_matching_folders(self, manager, mock_client):
        mock_client.get_config_folders = AsyncMock(return_value=[
            {"id": "karma-out--jayant.macbook--owner-repo"},
            {"id": "karma-meta--karma-team"},
            {"id": "unrelated-folder"},
        ])
        await manager.cleanup_team_folders(
            folder_suffixes=["owner-repo"],
            member_tags=["jayant.macbook"],
            team_name="karma-team",
        )
        # Should delete karma-out and karma-meta folders, not unrelated
        assert mock_client.delete_config_folder.call_count >= 2
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd api && pytest tests/test_folder_manager.py -v`
Expected: FAIL

- [ ] **Step 3: Implement FolderManager**

```python
# api/services/syncthing/folder_manager.py
"""Folder lifecycle management using SyncthingClient."""
from __future__ import annotations

from pathlib import Path

from services.syncthing.client import SyncthingClient


def build_outbox_folder_id(member_tag: str, folder_suffix: str) -> str:
    return f"karma-out--{member_tag}--{folder_suffix}"


def build_metadata_folder_id(team_name: str) -> str:
    return f"karma-meta--{team_name}"


class FolderManager:
    def __init__(self, client: SyncthingClient, karma_base: Path):
        self.client = client
        self.karma_base = karma_base

    async def _get_folder_ids(self) -> set[str]:
        folders = await self.client.get_config_folders()
        return {f["id"] for f in folders}

    async def _get_folder(self, folder_id: str) -> dict | None:
        folders = await self.client.get_config_folders()
        for f in folders:
            if f["id"] == folder_id:
                return f
        return None

    async def ensure_outbox_folder(self, member_tag: str, folder_suffix: str) -> None:
        """Create sendonly outbox folder if not exists."""
        folder_id = build_outbox_folder_id(member_tag, folder_suffix)
        if folder_id in await self._get_folder_ids():
            return
        folder_path = self.karma_base / "outboxes" / folder_id
        await self.client.put_config_folder({
            "id": folder_id,
            "path": str(folder_path),
            "type": "sendonly",
            "devices": [],
            "rescanIntervalS": 60,
        })

    async def ensure_inbox_folder(
        self, remote_member_tag: str, folder_suffix: str, remote_device_id: str
    ) -> None:
        """Create receiveonly inbox folder for a remote member's outbox."""
        folder_id = build_outbox_folder_id(remote_member_tag, folder_suffix)
        if folder_id in await self._get_folder_ids():
            return
        folder_path = self.karma_base / "inboxes" / folder_id
        await self.client.put_config_folder({
            "id": folder_id,
            "path": str(folder_path),
            "type": "receiveonly",
            "devices": [{"deviceID": remote_device_id}],
            "rescanIntervalS": 0,  # receive-only, no scanning needed
        })

    async def remove_outbox_folder(self, member_tag: str, folder_suffix: str) -> None:
        """Remove an outbox folder."""
        folder_id = build_outbox_folder_id(member_tag, folder_suffix)
        await self.client.delete_config_folder(folder_id)

    async def set_folder_devices(self, folder_id: str, device_ids: set[str]) -> None:
        """Declaratively set the device list for a folder. Replaces entire list."""
        folder = await self._get_folder(folder_id)
        if folder is None:
            return
        folder["devices"] = [{"deviceID": did} for did in device_ids]
        await self.client.put_config_folder(folder)

    async def remove_device_from_team_folders(
        self, folder_suffixes: list[str], member_tags: list[str], device_id: str
    ) -> None:
        """Remove a device from all folders matching the given suffixes and member_tags."""
        folders = await self.client.get_config_folders()
        for folder in folders:
            fid = folder["id"]
            # Check if this folder belongs to any of the team's projects
            is_team_folder = any(
                fid == build_outbox_folder_id(mt, fs)
                for mt in member_tags
                for fs in folder_suffixes
            )
            if is_team_folder:
                folder["devices"] = [
                    d for d in folder.get("devices", [])
                    if d["deviceID"] != device_id
                ]
                await self.client.put_config_folder(folder)

    async def cleanup_team_folders(
        self, folder_suffixes: list[str], member_tags: list[str], team_name: str
    ) -> None:
        """Remove all Syncthing folders related to a team."""
        folders = await self.client.get_config_folders()
        meta_id = build_metadata_folder_id(team_name)
        for folder in folders:
            fid = folder["id"]
            is_outbox = any(
                fid == build_outbox_folder_id(mt, fs)
                for mt in member_tags
                for fs in folder_suffixes
            )
            is_meta = fid == meta_id
            if is_outbox or is_meta:
                await self.client.delete_config_folder(fid)

    async def cleanup_project_folders(
        self, folder_suffix: str, member_tags: list[str]
    ) -> None:
        """Remove all folders for a specific project suffix."""
        folders = await self.client.get_config_folders()
        for folder in folders:
            fid = folder["id"]
            if any(fid == build_outbox_folder_id(mt, folder_suffix) for mt in member_tags):
                await self.client.delete_config_folder(fid)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd api && pytest tests/test_folder_manager.py -v`
Expected: ALL PASS

- [ ] **Step 5: Commit**

```bash
git add api/services/syncthing/folder_manager.py api/tests/test_folder_manager.py
git commit -m "feat(sync-v4): add FolderManager — outbox/inbox/device list management"
```

---

### Task 4: PairingService

**Files:**
- Create: `api/services/sync/pairing_service.py`
- Create: `api/services/sync/__init__.py`
- Test: `api/tests/test_pairing_service.py`

**INDEPENDENT — can run parallel with Tasks 1-3**

- [ ] **Step 1: Write failing tests**

```python
# api/tests/test_pairing_service.py
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
from services.sync.pairing_service import PairingService, PairingInfo


@pytest.fixture
def service():
    return PairingService()


class TestGenerateCode:
    def test_generates_non_empty_code(self, service):
        code = service.generate_code("jayant.macbook", "ABCDEFG-1234567-HIJKLMN-OPQRSTU-VWXYZ12-3456789-0ABCDEF")
        assert len(code) > 0

    def test_code_is_uppercase_with_dashes(self, service):
        code = service.generate_code("jayant.macbook", "DEV-ID-123")
        # Format: groups of 4 chars separated by dashes
        parts = code.split("-")
        assert all(len(p) == 4 for p in parts)
        assert all(c.isalnum() or c == "-" for c in code)

    def test_same_input_same_code(self, service):
        code1 = service.generate_code("jayant.macbook", "DEV-ID")
        code2 = service.generate_code("jayant.macbook", "DEV-ID")
        assert code1 == code2  # permanent, deterministic

    def test_different_input_different_code(self, service):
        code1 = service.generate_code("jayant.macbook", "DEV-1")
        code2 = service.generate_code("ayush.laptop", "DEV-2")
        assert code1 != code2


class TestValidateCode:
    def test_roundtrip(self, service):
        code = service.generate_code("jayant.macbook", "DEVICE-ABC-123")
        info = service.validate_code(code)
        assert info.member_tag == "jayant.macbook"
        assert info.device_id == "DEVICE-ABC-123"

    def test_invalid_code_raises(self, service):
        with pytest.raises(ValueError, match="Invalid pairing code"):
            service.validate_code("XXXX-INVALID")


class TestPairingInfo:
    def test_pairing_info_fields(self):
        info = PairingInfo(member_tag="jayant.macbook", device_id="DEV-1")
        assert info.member_tag == "jayant.macbook"
        assert info.device_id == "DEV-1"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd api && pytest tests/test_pairing_service.py -v`
Expected: FAIL

- [ ] **Step 3: Implement PairingService**

```python
# api/services/sync/__init__.py
"""Sync v4 business services."""

# api/services/sync/pairing_service.py
"""Pairing code generation and validation.

Encodes member_tag + device_id into a short shareable code.
Format: base32-encoded "{member_tag}:{device_id}", grouped into 4-char blocks with dashes.
Permanent — same input always produces same code.
"""
from __future__ import annotations

import base64

from pydantic import BaseModel


class PairingInfo(BaseModel):
    member_tag: str
    device_id: str


class PairingService:
    SEPARATOR = ":"

    def generate_code(self, member_tag: str, device_id: str) -> str:
        """Encode member_tag + device_id into a shareable pairing code."""
        payload = f"{member_tag}{self.SEPARATOR}{device_id}"
        encoded = base64.b32encode(payload.encode("utf-8")).decode("ascii")
        # Remove padding
        encoded = encoded.rstrip("=")
        # Group into 4-char blocks with dashes
        groups = [encoded[i:i+4] for i in range(0, len(encoded), 4)]
        return "-".join(groups)

    def validate_code(self, code: str) -> PairingInfo:
        """Decode a pairing code back to PairingInfo."""
        try:
            # Remove dashes and re-add padding
            raw = code.replace("-", "")
            padding = (8 - len(raw) % 8) % 8
            raw += "=" * padding
            decoded = base64.b32decode(raw.upper()).decode("utf-8")
            if self.SEPARATOR not in decoded:
                raise ValueError("Missing separator")
            member_tag, device_id = decoded.split(self.SEPARATOR, 1)
            return PairingInfo(member_tag=member_tag, device_id=device_id)
        except Exception as e:
            raise ValueError(f"Invalid pairing code: {e}") from e
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd api && pytest tests/test_pairing_service.py -v`
Expected: ALL PASS

- [ ] **Step 5: Commit**

```bash
git add api/services/sync/__init__.py api/services/sync/pairing_service.py api/tests/test_pairing_service.py
git commit -m "feat(sync-v4): add PairingService — permanent pairing code encode/decode"
```

---

### Task 5: Phase 2 Integration Test

**Files:**
- Test: `api/tests/test_sync_v4_infrastructure.py`

**SEQUENTIAL — after Tasks 1-4**

- [ ] **Step 1: Write integration test**

```python
# api/tests/test_sync_v4_infrastructure.py
"""Integration test: Syncthing abstraction layer works together."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
from unittest.mock import AsyncMock, MagicMock
from services.syncthing.client import SyncthingClient
from services.syncthing.device_manager import DeviceManager
from services.syncthing.folder_manager import FolderManager, build_outbox_folder_id
from services.sync.pairing_service import PairingService


class TestInfrastructureStack:
    """Simulates: pair device → create outbox → set device list."""

    @pytest.mark.asyncio
    async def test_pair_and_share(self):
        client = MagicMock(spec=SyncthingClient)
        client.get_config = AsyncMock(return_value={"devices": [], "folders": []})
        client.put_config_device = AsyncMock()
        client.get_config_folders = AsyncMock(return_value=[])
        client.put_config_folder = AsyncMock()

        devices = DeviceManager(client)
        folders = FolderManager(client, karma_base=Path("/tmp/test"))

        # 1. Pair with new device
        await devices.pair("DEV-AYUSH")
        client.put_config_device.assert_called_once()

        # 2. Create outbox folder
        await folders.ensure_outbox_folder("jayant.macbook", "owner-repo")
        client.put_config_folder.assert_called_once()
        folder = client.put_config_folder.call_args[0][0]
        assert folder["type"] == "sendonly"

        # 3. Set device list on folder
        client.put_config_folder.reset_mock()
        folder_id = build_outbox_folder_id("jayant.macbook", "owner-repo")
        client.get_config_folders = AsyncMock(return_value=[
            {"id": folder_id, "devices": [], "type": "sendonly"},
        ])
        await folders.set_folder_devices(folder_id, {"DEV-AYUSH", "DEV-JAYANT"})
        updated = client.put_config_folder.call_args[0][0]
        device_ids = {d["deviceID"] for d in updated["devices"]}
        assert device_ids == {"DEV-AYUSH", "DEV-JAYANT"}

    def test_pairing_code_roundtrip(self):
        svc = PairingService()
        code = svc.generate_code("ayush.laptop", "DEV-AYUSH-FULL-ID")
        info = svc.validate_code(code)
        assert info.member_tag == "ayush.laptop"
        assert info.device_id == "DEV-AYUSH-FULL-ID"
```

- [ ] **Step 2: Run integration test**

Run: `cd api && pytest tests/test_sync_v4_infrastructure.py -v`
Expected: ALL PASS

- [ ] **Step 3: Run full Phase 2 suite**

Run: `cd api && pytest tests/test_syncthing_client.py tests/test_device_manager.py tests/test_folder_manager.py tests/test_pairing_service.py tests/test_sync_v4_infrastructure.py -v`
Expected: ALL PASS

- [ ] **Step 4: Commit**

```bash
git add api/tests/test_sync_v4_infrastructure.py
git commit -m "test(sync-v4): add Phase 2 integration test — infrastructure stack"
```

---

## Phase 2 Completion Checklist

- [ ] SyncthingClient wraps all needed REST endpoints
- [ ] DeviceManager handles pair/unpair/connection status
- [ ] FolderManager handles outbox/inbox/device list/cleanup
- [ ] PairingService encodes/decodes permanent pairing codes
- [ ] Integration test passes
- [ ] All Phase 2 code committed
