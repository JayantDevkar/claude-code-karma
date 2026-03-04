# Syncthing Session Sync Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add Syncthing as a pluggable sync backend alongside IPFS, enabling real-time automatic session sharing for trusted teams with bidirectional feedback support.

**Architecture:** Refactor the `karma` CLI config to support per-team backend selection. Add a `SyncthingClient` (REST API wrapper), a `SessionWatcher` (watchdog-based filesystem monitor), and extend the CLI with `karma watch`, `karma team create`, and backend-aware `karma init`. The existing `SessionPackager` and `SyncManifest` are reused with minor extensions. The API gets two new endpoints for sync status.

**Tech Stack:** Python 3.9+, click (CLI), requests (Syncthing REST API), watchdog (filesystem events), Pydantic 2.x (models), pytest (testing)

**Design doc:** `docs/plans/2026-03-03-syncthing-session-sync-design.md`

**Existing code:** The IPFS CLI exists at `cli/` with `config.py`, `ipfs.py`, `sync.py`, `packager.py`, `manifest.py`, and `main.py`. This plan extends that codebase. All file paths are relative to the `cli/` directory unless noted otherwise.

---

## Task 1: Extend SyncManifest with `sync_backend` Field

**Files:**
- Modify: `cli/karma/manifest.py:18-35`
- Modify: `cli/tests/test_packager.py` (add test)

**Step 1: Write the failing test**

Add to `cli/tests/test_packager.py`:

```python
class TestSyncManifest:
    def test_manifest_default_sync_backend_is_none(self):
        from karma.manifest import SyncManifest
        m = SyncManifest(
            user_id="alice",
            machine_id="mac",
            project_path="/foo",
            project_encoded="-foo",
            session_count=0,
            sessions=[],
        )
        assert m.sync_backend is None

    def test_manifest_sync_backend_set(self):
        from karma.manifest import SyncManifest
        m = SyncManifest(
            user_id="alice",
            machine_id="mac",
            project_path="/foo",
            project_encoded="-foo",
            session_count=0,
            sessions=[],
            sync_backend="syncthing",
        )
        assert m.sync_backend == "syncthing"

    def test_manifest_sync_backend_in_dump(self):
        from karma.manifest import SyncManifest
        m = SyncManifest(
            user_id="alice",
            machine_id="mac",
            project_path="/foo",
            project_encoded="-foo",
            session_count=0,
            sessions=[],
            sync_backend="ipfs",
        )
        data = m.model_dump()
        assert data["sync_backend"] == "ipfs"
```

**Step 2: Run test to verify it fails**

Run: `cd cli && pytest tests/test_packager.py::TestSyncManifest -v`
Expected: FAIL — `sync_backend` field doesn't exist yet.

**Step 3: Write minimal implementation**

In `cli/karma/manifest.py`, add to the `SyncManifest` class after `previous_cid`:

```python
    sync_backend: Optional[str] = Field(
        default=None, description="Sync backend used: 'ipfs', 'syncthing', or None"
    )
```

**Step 4: Run test to verify it passes**

Run: `cd cli && pytest tests/test_packager.py::TestSyncManifest -v`
Expected: PASS

**Step 5: Commit**

```bash
git add cli/karma/manifest.py cli/tests/test_packager.py
git commit -m "feat: add sync_backend field to SyncManifest"
```

---

## Task 2: Refactor Config to Support Per-Team Backend Selection

**Files:**
- Modify: `cli/karma/config.py`
- Create: `cli/tests/test_config_teams.py`

This is the biggest structural change. The current config has flat `projects` and `team` dicts. We need a `teams` dict where each team has its own backend, projects, and members.

**Step 1: Write the failing tests**

Create `cli/tests/test_config_teams.py`:

```python
"""Tests for per-team config model."""

import pytest
from karma.config import (
    SyncConfig,
    TeamConfig,
    ProjectConfig,
    SyncthingSettings,
)


class TestTeamConfig:
    def test_create_syncthing_team(self):
        team = TeamConfig(
            backend="syncthing",
            owner_device_id="XXXXXXX-XXXXXXX",
            projects={
                "acme": ProjectConfig(path="/Users/alice/acme", encoded_name="-Users-alice-acme")
            },
        )
        assert team.backend == "syncthing"
        assert "acme" in team.projects

    def test_create_ipfs_team(self):
        team = TeamConfig(
            backend="ipfs",
            owner_ipns_key="k51abc",
            projects={},
        )
        assert team.backend == "ipfs"
        assert team.owner_ipns_key == "k51abc"

    def test_invalid_backend_rejected(self):
        with pytest.raises(Exception):
            TeamConfig(backend="dropbox", projects={})


class TestSyncthingSettings:
    def test_defaults(self):
        s = SyncthingSettings()
        assert s.api_url == "http://127.0.0.1:8384"
        assert s.api_key is None
        assert s.device_id is None

    def test_custom_values(self):
        s = SyncthingSettings(api_url="http://localhost:9999", api_key="abc123")
        assert s.api_url == "http://localhost:9999"
        assert s.api_key == "abc123"


class TestSyncConfigWithTeams:
    def test_config_has_teams(self):
        config = SyncConfig(user_id="alice")
        assert config.teams == {}

    def test_config_has_syncthing_settings(self):
        config = SyncConfig(
            user_id="alice",
            syncthing=SyncthingSettings(api_key="test"),
        )
        assert config.syncthing.api_key == "test"

    def test_backward_compat_projects_still_work(self):
        """Old flat projects dict is still accessible for IPFS-only setups."""
        config = SyncConfig(
            user_id="alice",
            projects={
                "acme": ProjectConfig(path="/foo", encoded_name="-foo")
            },
        )
        assert "acme" in config.projects

    def test_save_and_load_with_teams(self, tmp_path, monkeypatch):
        config_path = tmp_path / "sync-config.json"
        monkeypatch.setattr("karma.config.SYNC_CONFIG_PATH", config_path)
        monkeypatch.setattr("karma.config.KARMA_BASE", tmp_path)

        config = SyncConfig(
            user_id="alice",
            machine_id="test-mac",
            teams={
                "beta": TeamConfig(
                    backend="syncthing",
                    owner_device_id="YYYY",
                    projects={
                        "startup": ProjectConfig(path="/startup", encoded_name="-startup")
                    },
                )
            },
            syncthing=SyncthingSettings(api_url="http://127.0.0.1:8384", api_key="key123"),
        )
        config.save()

        loaded = SyncConfig.load()
        assert loaded is not None
        assert "beta" in loaded.teams
        assert loaded.teams["beta"].backend == "syncthing"
        assert loaded.syncthing.api_key == "key123"
```

**Step 2: Run tests to verify they fail**

Run: `cd cli && pytest tests/test_config_teams.py -v`
Expected: FAIL — `TeamConfig`, `SyncthingSettings` don't exist yet.

**Step 3: Write minimal implementation**

In `cli/karma/config.py`, add new models and extend `SyncConfig`:

```python
from typing import Literal, Optional
# (keep existing imports)


class SyncthingSettings(BaseModel):
    """Syncthing connection settings."""

    model_config = ConfigDict(frozen=True)

    api_url: str = Field(default="http://127.0.0.1:8384", description="Syncthing REST API URL")
    api_key: Optional[str] = Field(default=None, description="Syncthing API key")
    device_id: Optional[str] = Field(default=None, description="This device's Syncthing ID")


class TeamMemberSyncthing(BaseModel):
    """A team member identified by Syncthing device ID."""

    model_config = ConfigDict(frozen=True)

    syncthing_device_id: str = Field(..., description="Syncthing device ID")

    @field_validator("syncthing_device_id")
    @classmethod
    def validate_device_id(cls, v: str) -> str:
        if not v or len(v) > 128:
            raise ValueError("Device ID must be non-empty and under 128 chars")
        return v


class TeamConfig(BaseModel):
    """Configuration for a team with its own sync backend."""

    model_config = ConfigDict(frozen=True)

    backend: Literal["ipfs", "syncthing"] = Field(..., description="Sync backend for this team")
    projects: dict[str, ProjectConfig] = Field(default_factory=dict)
    members: dict[str, TeamMember | TeamMemberSyncthing] = Field(default_factory=dict)
    owner_device_id: Optional[str] = Field(default=None, description="Owner's Syncthing device ID")
    owner_ipns_key: Optional[str] = Field(default=None, description="Owner's IPNS key")
```

Then extend `SyncConfig` to add:

```python
    teams: dict[str, TeamConfig] = Field(default_factory=dict)
    syncthing: SyncthingSettings = Field(default_factory=SyncthingSettings)
```

**Step 4: Run tests to verify they pass**

Run: `cd cli && pytest tests/test_config_teams.py -v`
Expected: PASS

**Step 5: Run existing tests to verify backward compatibility**

Run: `cd cli && pytest tests/test_config.py -v`
Expected: PASS — existing flat config still works.

**Step 6: Commit**

```bash
git add cli/karma/config.py cli/tests/test_config_teams.py
git commit -m "feat: add per-team backend config with Syncthing settings"
```

---

## Task 3: Create SyncthingClient (REST API Wrapper)

**Files:**
- Create: `cli/karma/syncthing.py`
- Create: `cli/tests/test_syncthing.py`

**Step 1: Write the failing tests**

Create `cli/tests/test_syncthing.py`:

```python
"""Tests for Syncthing REST API wrapper."""

from unittest.mock import patch, MagicMock
import pytest

from karma.syncthing import SyncthingClient


class TestSyncthingClient:
    def test_init_defaults(self):
        client = SyncthingClient()
        assert client.api_url == "http://127.0.0.1:8384"

    def test_init_custom(self):
        client = SyncthingClient(api_url="http://localhost:9999", api_key="abc")
        assert client.api_url == "http://localhost:9999"
        assert client.headers["X-API-Key"] == "abc"

    @patch("karma.syncthing.requests.get")
    def test_is_running_true(self, mock_get):
        mock_get.return_value = MagicMock(status_code=200, json=lambda: {"myID": "XXXX"})
        client = SyncthingClient()
        assert client.is_running() is True

    @patch("karma.syncthing.requests.get")
    def test_is_running_false_connection_error(self, mock_get):
        import requests
        mock_get.side_effect = requests.ConnectionError()
        client = SyncthingClient()
        assert client.is_running() is False

    @patch("karma.syncthing.requests.get")
    def test_get_device_id(self, mock_get):
        mock_get.return_value = MagicMock(
            status_code=200,
            json=lambda: {"myID": "AAAAAAA-BBBBBBB-CCCCCCC-DDDDDDD"}
        )
        client = SyncthingClient(api_key="test")
        device_id = client.get_device_id()
        assert device_id == "AAAAAAA-BBBBBBB-CCCCCCC-DDDDDDD"

    @patch("karma.syncthing.requests.get")
    def test_get_connections(self, mock_get):
        mock_get.return_value = MagicMock(
            status_code=200,
            json=lambda: {
                "connections": {
                    "DEVICE1": {"connected": True},
                    "DEVICE2": {"connected": False},
                }
            }
        )
        client = SyncthingClient(api_key="test")
        conns = client.get_connections()
        assert "DEVICE1" in conns
        assert conns["DEVICE1"]["connected"] is True

    @patch("karma.syncthing.requests.get")
    @patch("karma.syncthing.requests.put")
    def test_add_device(self, mock_put, mock_get):
        mock_get.return_value = MagicMock(
            status_code=200,
            json=lambda: {"devices": [], "folders": []}
        )
        mock_put.return_value = MagicMock(status_code=200)

        client = SyncthingClient(api_key="test")
        client.add_device("NEWDEVICE-ID", "alice")

        mock_put.assert_called_once()
        put_data = mock_put.call_args[1]["json"]
        assert any(d["deviceID"] == "NEWDEVICE-ID" for d in put_data["devices"])

    @patch("karma.syncthing.requests.get")
    @patch("karma.syncthing.requests.put")
    def test_add_folder(self, mock_put, mock_get):
        mock_get.return_value = MagicMock(
            status_code=200,
            json=lambda: {"devices": [], "folders": []}
        )
        mock_put.return_value = MagicMock(status_code=200)

        client = SyncthingClient(api_key="test")
        client.add_folder("karma-out-alice", "/tmp/sync", ["DEVICE1"], folder_type="sendonly")

        mock_put.assert_called_once()
        put_data = mock_put.call_args[1]["json"]
        folder = put_data["folders"][0]
        assert folder["id"] == "karma-out-alice"
        assert folder["type"] == "sendonly"
```

**Step 2: Run tests to verify they fail**

Run: `cd cli && pytest tests/test_syncthing.py -v`
Expected: FAIL — `karma.syncthing` module doesn't exist.

**Step 3: Write minimal implementation**

Create `cli/karma/syncthing.py`:

```python
"""Syncthing REST API wrapper."""

import requests


class SyncthingClient:
    """Wraps the Syncthing REST API for device/folder management."""

    def __init__(self, api_url: str = "http://127.0.0.1:8384", api_key: str | None = None):
        self.api_url = api_url.rstrip("/")
        self.headers = {}
        if api_key:
            self.headers["X-API-Key"] = api_key

    def is_running(self) -> bool:
        """Check if Syncthing is running and accessible."""
        try:
            resp = requests.get(
                f"{self.api_url}/rest/system/status",
                headers=self.headers,
                timeout=5,
            )
            return resp.status_code == 200
        except requests.ConnectionError:
            return False

    def get_device_id(self) -> str:
        """Get this device's Syncthing Device ID."""
        resp = requests.get(
            f"{self.api_url}/rest/system/status",
            headers=self.headers,
            timeout=10,
        )
        resp.raise_for_status()
        return resp.json()["myID"]

    def get_connections(self) -> dict:
        """Check which devices are connected."""
        resp = requests.get(
            f"{self.api_url}/rest/system/connections",
            headers=self.headers,
            timeout=10,
        )
        resp.raise_for_status()
        return resp.json()["connections"]

    def add_device(self, device_id: str, name: str) -> None:
        """Pair with a remote device."""
        config = self._get_config()
        config["devices"].append({
            "deviceID": device_id,
            "name": name,
            "autoAcceptFolders": False,
        })
        self._set_config(config)

    def add_folder(
        self,
        folder_id: str,
        path: str,
        devices: list[str],
        folder_type: str = "sendonly",
    ) -> None:
        """Create a shared folder with specified devices."""
        config = self._get_config()
        config["folders"].append({
            "id": folder_id,
            "path": path,
            "devices": [{"deviceID": d} for d in devices],
            "type": folder_type,
        })
        self._set_config(config)

    def remove_device(self, device_id: str) -> None:
        """Remove a paired device."""
        config = self._get_config()
        config["devices"] = [d for d in config["devices"] if d["deviceID"] != device_id]
        self._set_config(config)

    def remove_folder(self, folder_id: str) -> None:
        """Remove a shared folder."""
        config = self._get_config()
        config["folders"] = [f for f in config["folders"] if f["id"] != folder_id]
        self._set_config(config)

    def _get_config(self) -> dict:
        resp = requests.get(f"{self.api_url}/rest/config", headers=self.headers, timeout=10)
        resp.raise_for_status()
        return resp.json()

    def _set_config(self, config: dict) -> None:
        resp = requests.put(
            f"{self.api_url}/rest/config",
            json=config,
            headers=self.headers,
            timeout=10,
        )
        resp.raise_for_status()
```

**Step 4: Run tests to verify they pass**

Run: `cd cli && pytest tests/test_syncthing.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add cli/karma/syncthing.py cli/tests/test_syncthing.py
git commit -m "feat: add SyncthingClient REST API wrapper"
```

---

## Task 4: Create SessionWatcher (Filesystem Monitor)

**Files:**
- Create: `cli/karma/watcher.py`
- Create: `cli/tests/test_watcher.py`

**Step 1: Add `watchdog` to dependencies**

In `cli/pyproject.toml`, add `"watchdog>=3.0"` to the `dependencies` list.

**Step 2: Write the failing tests**

Create `cli/tests/test_watcher.py`:

```python
"""Tests for filesystem session watcher."""

import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from karma.watcher import SessionWatcher


class TestSessionWatcher:
    def test_init(self):
        packager_fn = MagicMock()
        watcher = SessionWatcher(
            watch_dir=Path("/tmp/test"),
            package_fn=packager_fn,
            debounce_seconds=2,
        )
        assert watcher.debounce_seconds == 2
        assert watcher.watch_dir == Path("/tmp/test")

    def test_should_process_jsonl(self):
        watcher = SessionWatcher(
            watch_dir=Path("/tmp"),
            package_fn=MagicMock(),
        )
        assert watcher._should_process("/tmp/abc123.jsonl") is True
        assert watcher._should_process("/tmp/agent-xyz.jsonl") is False
        assert watcher._should_process("/tmp/readme.txt") is False
        assert watcher._should_process("/tmp/subdir/file.jsonl") is True

    def test_debounce_calls_package_fn_once(self):
        packager_fn = MagicMock()
        watcher = SessionWatcher(
            watch_dir=Path("/tmp"),
            package_fn=packager_fn,
            debounce_seconds=0.1,
        )
        # Simulate rapid file changes
        watcher._schedule_package()
        watcher._schedule_package()
        watcher._schedule_package()
        time.sleep(0.3)
        # Should only call once despite 3 triggers
        assert packager_fn.call_count == 1

    def test_is_running_property(self):
        watcher = SessionWatcher(
            watch_dir=Path("/tmp"),
            package_fn=MagicMock(),
        )
        assert watcher.is_running is False
```

**Step 3: Run tests to verify they fail**

Run: `cd cli && pytest tests/test_watcher.py -v`
Expected: FAIL — `karma.watcher` module doesn't exist.

**Step 4: Write minimal implementation**

Create `cli/karma/watcher.py`:

```python
"""Filesystem watcher for automatic session packaging."""

import threading
from pathlib import Path
from typing import Callable

from watchdog.events import FileSystemEventHandler, FileModifiedEvent, FileCreatedEvent
from watchdog.observers import Observer


class SessionWatcher(FileSystemEventHandler):
    """Watches Claude project dirs for JSONL changes and triggers packaging."""

    def __init__(
        self,
        watch_dir: Path,
        package_fn: Callable[[], None],
        debounce_seconds: float = 5.0,
    ):
        self.watch_dir = Path(watch_dir)
        self.package_fn = package_fn
        self.debounce_seconds = debounce_seconds
        self._timer: threading.Timer | None = None
        self._observer: Observer | None = None
        self._lock = threading.Lock()

    @property
    def is_running(self) -> bool:
        return self._observer is not None and self._observer.is_alive()

    def _should_process(self, path: str) -> bool:
        """Only process session JSONL files (not agent files)."""
        p = Path(path)
        return p.suffix == ".jsonl" and not p.name.startswith("agent-")

    def on_modified(self, event):
        if not isinstance(event, (FileModifiedEvent, FileCreatedEvent)):
            return
        if self._should_process(event.src_path):
            self._schedule_package()

    def on_created(self, event):
        if self._should_process(event.src_path):
            self._schedule_package()

    def _schedule_package(self):
        """Debounced packaging — waits for quiet period before running."""
        with self._lock:
            if self._timer is not None:
                self._timer.cancel()
            self._timer = threading.Timer(self.debounce_seconds, self._do_package)
            self._timer.daemon = True
            self._timer.start()

    def _do_package(self):
        """Execute the packaging function."""
        try:
            self.package_fn()
        except Exception:
            pass  # Watcher should not crash on packaging errors

    def start(self):
        """Start watching the directory."""
        self._observer = Observer()
        self._observer.schedule(self, str(self.watch_dir), recursive=True)
        self._observer.daemon = True
        self._observer.start()

    def stop(self):
        """Stop watching."""
        with self._lock:
            if self._timer is not None:
                self._timer.cancel()
                self._timer = None
        if self._observer is not None:
            self._observer.stop()
            self._observer.join(timeout=5)
            self._observer = None
```

**Step 5: Run tests to verify they pass**

Run: `cd cli && pytest tests/test_watcher.py -v`
Expected: PASS

**Step 6: Commit**

```bash
git add cli/karma/watcher.py cli/tests/test_watcher.py cli/pyproject.toml
git commit -m "feat: add SessionWatcher with debounced filesystem monitoring"
```

---

## Task 5: Extend CLI with Backend-Aware Init and Team Create

**Files:**
- Modify: `cli/karma/main.py`
- Create: `cli/tests/test_cli_syncthing.py`

**Step 1: Write the failing tests**

Create `cli/tests/test_cli_syncthing.py`:

```python
"""Tests for Syncthing CLI commands."""

from unittest.mock import patch, MagicMock
from click.testing import CliRunner

import pytest

from karma.main import cli


@pytest.fixture
def runner():
    return CliRunner()


@pytest.fixture
def mock_config(tmp_path, monkeypatch):
    config_path = tmp_path / "sync-config.json"
    monkeypatch.setattr("karma.config.SYNC_CONFIG_PATH", config_path)
    monkeypatch.setattr("karma.config.KARMA_BASE", tmp_path)
    return config_path


class TestInitWithBackend:
    def test_init_default_no_backend_flag(self, runner, mock_config):
        result = runner.invoke(cli, ["init", "--user-id", "alice"])
        assert result.exit_code == 0
        assert "alice" in result.output

    @patch("karma.main.SyncthingClient")
    def test_init_syncthing_backend(self, mock_st_cls, runner, mock_config):
        mock_st = MagicMock()
        mock_st.is_running.return_value = True
        mock_st.get_device_id.return_value = "AAAA-BBBB-CCCC"
        mock_st_cls.return_value = mock_st

        result = runner.invoke(cli, ["init", "--user-id", "alice", "--backend", "syncthing"])
        assert result.exit_code == 0
        assert "AAAA-BBBB-CCCC" in result.output

    @patch("karma.main.SyncthingClient")
    def test_init_syncthing_not_running(self, mock_st_cls, runner, mock_config):
        mock_st = MagicMock()
        mock_st.is_running.return_value = False
        mock_st_cls.return_value = mock_st

        result = runner.invoke(cli, ["init", "--user-id", "alice", "--backend", "syncthing"])
        assert result.exit_code != 0
        assert "not running" in result.output.lower() or "not running" in str(result.exception).lower()


class TestTeamCreate:
    def test_team_create_syncthing(self, runner, mock_config):
        # First init
        runner.invoke(cli, ["init", "--user-id", "alice"])
        # Then create team
        result = runner.invoke(cli, ["team", "create", "beta", "--backend", "syncthing"])
        assert result.exit_code == 0
        assert "beta" in result.output

    def test_team_create_ipfs(self, runner, mock_config):
        runner.invoke(cli, ["init", "--user-id", "alice"])
        result = runner.invoke(cli, ["team", "create", "alpha", "--backend", "ipfs"])
        assert result.exit_code == 0
        assert "alpha" in result.output

    def test_team_create_requires_init(self, runner, mock_config):
        result = runner.invoke(cli, ["team", "create", "beta", "--backend", "syncthing"])
        assert result.exit_code != 0


class TestTeamAddSyncthing:
    def test_team_add_device_id(self, runner, mock_config):
        runner.invoke(cli, ["init", "--user-id", "alice"])
        runner.invoke(cli, ["team", "create", "beta", "--backend", "syncthing"])
        result = runner.invoke(cli, ["team", "add", "bob", "DEVICEID123", "--team", "beta"])
        assert result.exit_code == 0
        assert "bob" in result.output
```

**Step 2: Run tests to verify they fail**

Run: `cd cli && pytest tests/test_cli_syncthing.py -v`
Expected: FAIL — `--backend` option and `team create` command don't exist.

**Step 3: Write minimal implementation**

Modify `cli/karma/main.py`:

1. Add `--backend` option to `init` command:

```python
@cli.command()
@click.option("--user-id", prompt="Your user ID (e.g., your name)", help="Identity for syncing")
@click.option("--backend", type=click.Choice(["ipfs", "syncthing"]), default=None, help="Sync backend")
def init(user_id: str, backend: str | None):
    """Initialize Karma sync on this machine."""
    # ... existing validation ...

    if backend == "syncthing":
        from karma.syncthing import SyncthingClient
        st = SyncthingClient()
        if not st.is_running():
            raise click.ClickException("Syncthing is not running. Start Syncthing first.")
        device_id = st.get_device_id()
        config = SyncConfig(user_id=user_id)
        config.save()
        click.echo(f"Initialized as '{user_id}' on '{config.machine_id}'.")
        click.echo(f"Your Syncthing Device ID: {device_id}")
        click.echo("Share this Device ID with your project owner.")
    else:
        config = SyncConfig(user_id=user_id)
        config.save()
        click.echo(f"Initialized as '{user_id}' on '{config.machine_id}'.")
        click.echo("Next: install Kubo, start IPFS daemon, add a project.")
```

2. Add `team create` command:

```python
@team.command("create")
@click.argument("name")
@click.option("--backend", type=click.Choice(["ipfs", "syncthing"]), required=True, help="Sync backend")
def team_create(name: str, backend: str):
    """Create a new team with a specific sync backend."""
    if not _SAFE_NAME.match(name):
        raise click.ClickException("Team name must be alphanumeric, dash, or underscore only.")

    config = require_config()

    from karma.config import TeamConfig
    team_config = TeamConfig(backend=backend, projects={})

    teams = dict(config.teams)
    teams[name] = team_config
    updated = config.model_copy(update={"teams": teams})
    updated.save()

    click.echo(f"Created team '{name}' (backend: {backend})")
```

3. Modify `team add` to accept `--team` option and support both IPNS keys and device IDs:

```python
@team.command("add")
@click.argument("name")
@click.argument("identifier")
@click.option("--team", "team_name", default=None, help="Team to add member to (for per-team config)")
def team_add(name: str, identifier: str, team_name: str | None):
    """Add a team member by their IPNS key or Syncthing device ID."""
    # ... validation ...
    config = require_config()

    if team_name and team_name in config.teams:
        # Per-team member add
        team_cfg = config.teams[team_name]
        if team_cfg.backend == "syncthing":
            from karma.config import TeamMemberSyncthing
            member = TeamMemberSyncthing(syncthing_device_id=identifier)
        else:
            member = TeamMember(ipns_key=identifier)
        members = dict(team_cfg.members)
        members[name] = member
        teams = dict(config.teams)
        teams[team_name] = team_cfg.model_copy(update={"members": members})
        updated = config.model_copy(update={"teams": teams})
        updated.save()
        click.echo(f"Added '{name}' to team '{team_name}'")
    else:
        # Legacy flat team dict (IPFS-only backward compat)
        # ... existing logic ...
```

**Step 4: Run tests to verify they pass**

Run: `cd cli && pytest tests/test_cli_syncthing.py -v`
Expected: PASS

**Step 5: Run all existing tests**

Run: `cd cli && pytest -v`
Expected: All PASS (existing behavior preserved).

**Step 6: Commit**

```bash
git add cli/karma/main.py cli/tests/test_cli_syncthing.py
git commit -m "feat: add --backend flag to init, team create command, Syncthing-aware team add"
```

---

## Task 6: Add `karma watch` Command

**Files:**
- Modify: `cli/karma/main.py`
- Add tests to: `cli/tests/test_cli_syncthing.py`

**Step 1: Write the failing tests**

Add to `cli/tests/test_cli_syncthing.py`:

```python
class TestWatchCommand:
    def test_watch_requires_init(self, runner, mock_config):
        result = runner.invoke(cli, ["watch"])
        assert result.exit_code != 0

    def test_watch_requires_syncthing_team(self, runner, mock_config):
        runner.invoke(cli, ["init", "--user-id", "alice"])
        result = runner.invoke(cli, ["watch", "--team", "nonexistent"])
        assert result.exit_code != 0

    @patch("karma.main.SessionWatcher")
    def test_watch_starts_and_stops_on_interrupt(self, mock_watcher_cls, runner, mock_config):
        runner.invoke(cli, ["init", "--user-id", "alice"])
        runner.invoke(cli, ["team", "create", "beta", "--backend", "syncthing"])
        runner.invoke(cli, [
            "project", "add", "app", "--path", "/tmp/test-project", "--team", "beta"
        ])

        mock_watcher = MagicMock()
        mock_watcher_cls.return_value = mock_watcher
        # Simulate KeyboardInterrupt after start
        mock_watcher.start.side_effect = KeyboardInterrupt()

        result = runner.invoke(cli, ["watch", "--team", "beta"])
        # Should handle gracefully
        mock_watcher.stop.assert_called()
```

**Step 2: Run tests to verify they fail**

Run: `cd cli && pytest tests/test_cli_syncthing.py::TestWatchCommand -v`
Expected: FAIL — `watch` command doesn't exist yet.

**Step 3: Write minimal implementation**

Add to `cli/karma/main.py`:

```python
@cli.command()
@click.option("--team", "team_name", required=True, help="Team to watch for")
def watch(team_name: str):
    """Watch project sessions and auto-package for Syncthing sync."""
    from karma.watcher import SessionWatcher
    from karma.packager import SessionPackager

    config = require_config()

    if team_name not in config.teams:
        raise click.ClickException(f"Team '{team_name}' not found. Run: karma team create {team_name}")

    team_cfg = config.teams[team_name]
    if team_cfg.backend != "syncthing":
        raise click.ClickException(f"Team '{team_name}' uses {team_cfg.backend}, not syncthing. Watch is only for Syncthing.")

    if not team_cfg.projects:
        raise click.ClickException(f"No projects in team '{team_name}'. Run: karma project add <name> --team {team_name}")

    click.echo(f"Watching {len(team_cfg.projects)} project(s) for team '{team_name}'...")
    click.echo("Press Ctrl+C to stop.\n")

    watchers = []
    for proj_name, proj in team_cfg.projects.items():
        claude_dir = Path.home() / ".claude" / "projects" / proj.encoded_name
        if not claude_dir.is_dir():
            click.echo(f"  Skipping '{proj_name}': Claude dir not found ({claude_dir})")
            continue

        outbox = KARMA_BASE / "sync-outbox" / team_name / config.user_id / proj.encoded_name

        def make_package_fn(cd=claude_dir, ob=outbox, pn=proj_name):
            def package():
                packager = SessionPackager(
                    project_dir=cd,
                    user_id=config.user_id,
                    machine_id=config.machine_id,
                    project_path=proj.path,
                )
                ob.mkdir(parents=True, exist_ok=True)
                packager.package(staging_dir=ob)
                click.echo(f"  Packaged '{pn}' -> {ob}")
            return package

        watcher = SessionWatcher(
            watch_dir=claude_dir,
            package_fn=make_package_fn(),
        )
        watcher.start()
        watchers.append(watcher)
        click.echo(f"  Watching: {proj_name} ({claude_dir})")

    try:
        import time
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        click.echo("\nStopping watchers...")
    finally:
        for w in watchers:
            w.stop()
        click.echo("Done.")
```

Also need to update `project add` to accept `--team` option:

```python
@project.command("add")
@click.argument("name")
@click.option("--path", required=True, help="Absolute path to the project directory")
@click.option("--team", "team_name", default=None, help="Team to add project to")
def project_add(name: str, path: str, team_name: str | None):
    """Add a project for syncing."""
    # ... existing validation ...
    config = require_config()
    encoded = encode_project_path(path)
    project_config = ProjectConfig(path=path, encoded_name=encoded)

    if team_name:
        if team_name not in config.teams:
            raise click.ClickException(f"Team '{team_name}' not found.")
        team_cfg = config.teams[team_name]
        projects = dict(team_cfg.projects)
        projects[name] = project_config
        teams = dict(config.teams)
        teams[team_name] = team_cfg.model_copy(update={"projects": projects})
        updated = config.model_copy(update={"teams": teams})
    else:
        # Legacy flat projects
        projects = dict(config.projects)
        projects[name] = project_config
        updated = config.model_copy(update={"projects": projects})

    updated.save()
    click.echo(f"Added project '{name}' ({path})")
```

**Step 4: Run tests to verify they pass**

Run: `cd cli && pytest tests/test_cli_syncthing.py -v`
Expected: PASS

**Step 5: Run all tests**

Run: `cd cli && pytest -v`
Expected: All PASS

**Step 6: Commit**

```bash
git add cli/karma/main.py cli/tests/test_cli_syncthing.py
git commit -m "feat: add karma watch command and --team flag for project add"
```

---

## Task 7: Add `karma status` Command

**Files:**
- Modify: `cli/karma/main.py`
- Add tests to: `cli/tests/test_cli_syncthing.py`

**Step 1: Write the failing tests**

Add to `cli/tests/test_cli_syncthing.py`:

```python
class TestStatusCommand:
    def test_status_no_teams(self, runner, mock_config):
        runner.invoke(cli, ["init", "--user-id", "alice"])
        result = runner.invoke(cli, ["status"])
        assert result.exit_code == 0
        assert "No teams" in result.output

    def test_status_shows_teams(self, runner, mock_config):
        runner.invoke(cli, ["init", "--user-id", "alice"])
        runner.invoke(cli, ["team", "create", "beta", "--backend", "syncthing"])
        result = runner.invoke(cli, ["status"])
        assert result.exit_code == 0
        assert "beta" in result.output
        assert "syncthing" in result.output.lower()
```

**Step 2: Run tests to verify they fail**

Run: `cd cli && pytest tests/test_cli_syncthing.py::TestStatusCommand -v`
Expected: FAIL — `status` command doesn't exist.

**Step 3: Write minimal implementation**

Add to `cli/karma/main.py`:

```python
@cli.command()
def status():
    """Show sync status for all teams."""
    config = require_config()

    click.echo(f"User: {config.user_id} ({config.machine_id})")

    if not config.teams and not config.projects:
        click.echo("No teams or projects configured.")
        return

    # Legacy flat projects
    if config.projects:
        click.echo(f"\nLegacy projects (IPFS):")
        for name, proj in config.projects.items():
            sync_info = f"last sync: {proj.last_sync_at}" if proj.last_sync_at else "never synced"
            click.echo(f"  {name}: {proj.path} ({sync_info})")

    # Per-team
    for team_name, team_cfg in config.teams.items():
        click.echo(f"\n{team_name} ({team_cfg.backend}):")
        if not team_cfg.projects:
            click.echo("  No projects")
        for proj_name, proj in team_cfg.projects.items():
            last = proj.last_sync_at or "never"
            click.echo(f"  {proj_name}: {proj.path} (last: {last})")
        if team_cfg.members:
            click.echo(f"  Members: {', '.join(team_cfg.members.keys())}")
```

**Step 4: Run tests to verify they pass**

Run: `cd cli && pytest tests/test_cli_syncthing.py::TestStatusCommand -v`
Expected: PASS

**Step 5: Commit**

```bash
git add cli/karma/main.py cli/tests/test_cli_syncthing.py
git commit -m "feat: add karma status command showing teams and sync state"
```

---

## Task 8: Add API Sync Status Endpoints

**Files:**
- Create: `api/routers/sync_status.py`
- Create: `api/tests/api/test_sync_status.py`
- Modify: `api/main.py` (register router)

**Step 1: Write the failing tests**

Create `api/tests/api/test_sync_status.py`:

```python
"""Tests for sync status API endpoints."""

import json
from pathlib import Path
from unittest.mock import patch

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
```

**Step 2: Run tests to verify they fail**

Run: `cd api && pytest tests/api/test_sync_status.py -v`
Expected: FAIL — router doesn't exist.

**Step 3: Write minimal implementation**

Create `api/routers/sync_status.py`:

```python
"""Sync status API endpoints."""

import json
from pathlib import Path

from fastapi import APIRouter

SYNC_CONFIG_PATH = Path.home() / ".claude_karma" / "sync-config.json"

router = APIRouter(prefix="/sync", tags=["sync"])


def _load_config() -> dict | None:
    if not SYNC_CONFIG_PATH.exists():
        return None
    return json.loads(SYNC_CONFIG_PATH.read_text())


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
            "member_count": len(team.get("members", {})),
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
        teams.append({
            "name": name,
            "backend": team["backend"],
            "projects": list(team.get("projects", {}).keys()),
            "members": list(team.get("members", {}).keys()),
        })

    return {"teams": teams}
```

In `api/main.py`, add:

```python
from routers.sync_status import router as sync_status_router
app.include_router(sync_status_router)
```

**Step 4: Run tests to verify they pass**

Run: `cd api && pytest tests/api/test_sync_status.py -v`
Expected: PASS

**Step 5: Run all API tests**

Run: `cd api && pytest -v`
Expected: All PASS

**Step 6: Commit**

```bash
git add api/routers/sync_status.py api/tests/api/test_sync_status.py api/main.py
git commit -m "feat: add /sync/status and /sync/teams API endpoints"
```

---

## Summary

| Task | Component | Key Files | Tests |
|------|-----------|-----------|-------|
| 1 | Manifest extension | `manifest.py` | `test_packager.py` |
| 2 | Per-team config | `config.py` | `test_config_teams.py` |
| 3 | Syncthing client | `syncthing.py` | `test_syncthing.py` |
| 4 | Filesystem watcher | `watcher.py` | `test_watcher.py` |
| 5 | CLI init + team create | `main.py` | `test_cli_syncthing.py` |
| 6 | CLI watch command | `main.py` | `test_cli_syncthing.py` |
| 7 | CLI status command | `main.py` | `test_cli_syncthing.py` |
| 8 | API sync endpoints | `sync_status.py` | `test_sync_status.py` |

**Dependencies:** Task 1 → Task 2 → Tasks 3, 4 (parallel) → Tasks 5, 6, 7 (sequential) → Task 8
