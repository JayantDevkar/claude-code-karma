# IPFS Sync UI/UX Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add a `/sync` page showing IPFS daemon health, per-project sync freshness, team status, and sync history — backed by a new `sync_history` SQLite table, new API endpoints, and CLI enhancements for per-machine IPNS keys.

**Architecture:** Four layers bottom-up: (1) SQLite schema migration adds `sync_history` table, (2) CLI gains `karma status` command and writes push/pull events to SQLite, (3) new `/sync/*` API router reads filesystem + SQLite to serve sync status, (4) SvelteKit `/sync` page renders the four-zone dashboard.

**Tech Stack:** Python 3.9+ (click, Pydantic, sqlite3), FastAPI, SvelteKit/Svelte 5, Tailwind CSS 4, lucide-svelte icons.

**Design docs:**
- `docs/plans/2026-03-03-ipfs-session-sync-design.md` — IPFS architecture
- `docs/plans/2026-03-03-ipfs-sync-ui-ux-design.md` — UI/UX design

---

## Task 1: SQLite schema — add `sync_history` table

**Files:**
- Modify: `api/db/schema.py` (bump SCHEMA_VERSION 9→10, add migration)
- Test: `api/tests/test_sync_history_schema.py`

**Step 1: Write the failing test**

Create `api/tests/test_sync_history_schema.py`:

```python
"""Tests for sync_history schema migration."""
import sqlite3
import pytest
from db.schema import ensure_schema, SCHEMA_VERSION


def test_schema_version_is_10():
    assert SCHEMA_VERSION == 10


def test_sync_history_table_created():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    ensure_schema(conn)

    # Table exists
    tables = {
        r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
    }
    assert "sync_history" in tables

    # Columns are correct
    cols = {r[1] for r in conn.execute("PRAGMA table_info(sync_history)").fetchall()}
    assert cols == {
        "id", "event_type", "user_id", "machine_id",
        "project", "cid", "ipns_key", "session_count", "created_at",
    }


def test_sync_history_insert_and_query():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    ensure_schema(conn)

    conn.execute(
        "INSERT INTO sync_history (event_type, user_id, machine_id, project, cid, ipns_key, session_count, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        ("push", "alice", "macbook-pro", "acme-app", "QmTest123", "k51abc", 5, "2026-03-03T14:00:00Z"),
    )
    conn.commit()

    rows = conn.execute("SELECT * FROM sync_history WHERE user_id = 'alice'").fetchall()
    assert len(rows) == 1
    assert rows[0]["event_type"] == "push"
    assert rows[0]["session_count"] == 5


def test_sync_history_indexes_exist():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    ensure_schema(conn)

    indexes = {
        r[1] for r in conn.execute(
            "SELECT * FROM sqlite_master WHERE type='index' AND tbl_name='sync_history'"
        ).fetchall()
        if r[1]  # skip auto-index
    }
    assert "idx_sync_history_user" in indexes
    assert "idx_sync_history_project" in indexes
    assert "idx_sync_history_created" in indexes
```

**Step 2: Run test to verify it fails**

Run: `cd api && python -m pytest tests/test_sync_history_schema.py -v`
Expected: FAIL — `SCHEMA_VERSION` is 9, `sync_history` table doesn't exist.

**Step 3: Implement schema migration**

In `api/db/schema.py`:

1. Change `SCHEMA_VERSION = 9` → `SCHEMA_VERSION = 10`

2. Add to `SCHEMA_SQL` (after the `projects` table block):

```sql
-- Sync history (IPFS push/pull audit trail)
CREATE TABLE IF NOT EXISTS sync_history (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    event_type    TEXT NOT NULL,
    user_id       TEXT NOT NULL,
    machine_id    TEXT NOT NULL,
    project       TEXT NOT NULL,
    cid           TEXT,
    ipns_key      TEXT,
    session_count INTEGER DEFAULT 0,
    created_at    TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_sync_history_user ON sync_history(user_id);
CREATE INDEX IF NOT EXISTS idx_sync_history_project ON sync_history(project);
CREATE INDEX IF NOT EXISTS idx_sync_history_created ON sync_history(created_at);
```

3. Add migration block in `ensure_schema()` before the version recording:

```python
        if current_version < 10:
            logger.info("Migrating v9 → v10: adding sync_history table")
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS sync_history (
                    id            INTEGER PRIMARY KEY AUTOINCREMENT,
                    event_type    TEXT NOT NULL,
                    user_id       TEXT NOT NULL,
                    machine_id    TEXT NOT NULL,
                    project       TEXT NOT NULL,
                    cid           TEXT,
                    ipns_key      TEXT,
                    session_count INTEGER DEFAULT 0,
                    created_at    TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_sync_history_user ON sync_history(user_id);
                CREATE INDEX IF NOT EXISTS idx_sync_history_project ON sync_history(project);
                CREATE INDEX IF NOT EXISTS idx_sync_history_created ON sync_history(created_at);
            """)
```

**Step 4: Run test to verify it passes**

Run: `cd api && python -m pytest tests/test_sync_history_schema.py -v`
Expected: All 4 tests PASS.

**Step 5: Commit**

```bash
git add api/db/schema.py api/tests/test_sync_history_schema.py
git commit -m "feat: add sync_history SQLite table (schema v10)"
```

---

## Task 2: CLI — per-machine IPNS key generation in `karma init`

**Files:**
- Modify: `cli/karma/main.py` (update `init` command)
- Modify: `cli/karma/config.py` (add `ipns_key_name` field to SyncConfig)
- Test: `cli/tests/test_cli.py` (add init key tests)

**Step 1: Write the failing test**

Add to `cli/tests/test_cli.py`:

```python
def test_init_sets_ipns_key_name(tmp_path, monkeypatch):
    """karma init should store a per-machine IPNS key name in config."""
    monkeypatch.setattr("karma.config.SYNC_CONFIG_PATH", tmp_path / "sync-config.json")
    monkeypatch.setattr("karma.config.KARMA_BASE", tmp_path)

    from karma.config import SyncConfig
    config = SyncConfig(user_id="alice")
    assert config.ipns_key_name == f"karma-alice-{config.machine_id}"
```

**Step 2: Run test to verify it fails**

Run: `cd cli && python -m pytest tests/test_cli.py::test_init_sets_ipns_key_name -v`
Expected: FAIL — `ipns_key_name` field doesn't exist on SyncConfig.

**Step 3: Implement**

In `cli/karma/config.py`, add computed field to `SyncConfig`:

```python
    ipns_key_name: str = Field(
        default="",
        description="IPNS key name for this machine (karma-{user_id}-{machine_id})",
    )

    def __init__(self, **data):
        super().__init__(**data)
        if not self.ipns_key_name:
            # Set via object.__setattr__ because model is frozen
            object.__setattr__(self, "ipns_key_name", f"karma-{self.user_id}-{self.machine_id}")
```

In `cli/karma/main.py`, update the `init` command to display the key name:

```python
    click.echo(f"Initialized as '{user_id}' on '{config.machine_id}'.")
    click.echo(f"IPNS key name: {config.ipns_key_name}")
    click.echo(f"Config saved to {SYNC_CONFIG_PATH}")
```

**Step 4: Run test to verify it passes**

Run: `cd cli && python -m pytest tests/test_cli.py::test_init_sets_ipns_key_name -v`
Expected: PASS

**Step 5: Commit**

```bash
git add cli/karma/config.py cli/karma/main.py cli/tests/test_cli.py
git commit -m "feat: per-machine IPNS key name in karma init"
```

---

## Task 3: CLI — `karma status` command

**Files:**
- Modify: `cli/karma/main.py` (add `status` command)
- Test: `cli/tests/test_cli.py` (add status tests)

**Step 1: Write the failing test**

Add to `cli/tests/test_cli.py`:

```python
from click.testing import CliRunner
from karma.main import cli

def test_status_not_initialized(tmp_path, monkeypatch):
    """karma status should fail if not initialized."""
    monkeypatch.setattr("karma.config.SYNC_CONFIG_PATH", tmp_path / "nope.json")
    runner = CliRunner()
    result = runner.invoke(cli, ["status"])
    assert result.exit_code != 0
    assert "Not initialized" in result.output


def test_status_shows_projects(tmp_path, monkeypatch):
    """karma status should show project sync state."""
    monkeypatch.setattr("karma.config.SYNC_CONFIG_PATH", tmp_path / "sync-config.json")
    monkeypatch.setattr("karma.config.KARMA_BASE", tmp_path)

    from karma.config import SyncConfig, ProjectConfig
    config = SyncConfig(
        user_id="alice",
        projects={"acme": ProjectConfig(path="/tmp/acme", encoded_name="-tmp-acme")},
    )
    config.save()

    runner = CliRunner()
    result = runner.invoke(cli, ["status"])
    assert result.exit_code == 0
    assert "alice" in result.output
    assert "acme" in result.output
```

**Step 2: Run test to verify it fails**

Run: `cd cli && python -m pytest tests/test_cli.py::test_status_not_initialized tests/test_cli.py::test_status_shows_projects -v`
Expected: FAIL — `status` command doesn't exist.

**Step 3: Implement**

Add to `cli/karma/main.py`:

```python
@cli.command()
def status():
    """Show sync status for this machine."""
    config = require_config()

    # Identity
    click.echo(f"Identity: {config.user_id} @ {config.machine_id}")
    click.echo(f"IPNS Key: {config.ipns_key_name}")

    # IPFS status (best-effort, don't fail if daemon isn't running)
    try:
        from karma.ipfs import IPFSClient
        ipfs = IPFSClient(api_url=config.ipfs_api)
        if ipfs.is_running():
            peers = ipfs.swarm_peers()
            click.echo(f"IPFS: Running ({len(peers)} peers)")
        else:
            click.echo("IPFS: Not running")
    except Exception:
        click.echo("IPFS: Unknown (could not check)")

    # Projects
    if not config.projects:
        click.echo("\nNo projects configured.")
        return

    click.echo(f"\nProjects ({len(config.projects)}):")
    for name, proj in config.projects.items():
        # Count local sessions
        from pathlib import Path
        claude_dir = Path.home() / ".claude" / "projects" / proj.encoded_name
        local_count = len(list(claude_dir.glob("*.jsonl"))) if claude_dir.is_dir() else 0

        if proj.last_sync_at:
            sync_info = f"synced {proj.last_sync_at}"
        else:
            sync_info = "never synced"

        click.echo(f"  {name}: {local_count} sessions ({sync_info})")
```

**Step 4: Run test to verify it passes**

Run: `cd cli && python -m pytest tests/test_cli.py::test_status_not_initialized tests/test_cli.py::test_status_shows_projects -v`
Expected: PASS

**Step 5: Commit**

```bash
git add cli/karma/main.py cli/tests/test_cli.py
git commit -m "feat: add karma status command"
```

---

## Task 4: CLI — record push/pull events to SQLite

**Files:**
- Create: `cli/karma/history.py` (sync_history writer)
- Modify: `cli/karma/main.py` (call history writer after sync/pull)
- Test: `cli/tests/test_history.py`

**Step 1: Write the failing test**

Create `cli/tests/test_history.py`:

```python
"""Tests for sync_history recording."""
import sqlite3
from karma.history import record_sync_event, get_db_path, ensure_sync_schema


def test_record_push_event(tmp_path, monkeypatch):
    monkeypatch.setattr("karma.history.KARMA_BASE", tmp_path)

    record_sync_event(
        event_type="push",
        user_id="alice",
        machine_id="macbook-pro",
        project="acme-app",
        cid="QmTest123",
        ipns_key="k51abc",
        session_count=5,
    )

    db_path = tmp_path / "metadata.db"
    assert db_path.exists()

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    rows = conn.execute("SELECT * FROM sync_history").fetchall()
    assert len(rows) == 1
    assert rows[0]["event_type"] == "push"
    assert rows[0]["user_id"] == "alice"
    assert rows[0]["session_count"] == 5
    conn.close()


def test_record_pull_event(tmp_path, monkeypatch):
    monkeypatch.setattr("karma.history.KARMA_BASE", tmp_path)

    record_sync_event(
        event_type="pull",
        user_id="bob",
        machine_id="bob-windows",
        project="acme-app",
        cid="QmBob456",
        session_count=3,
    )

    db_path = tmp_path / "metadata.db"
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    rows = conn.execute("SELECT * FROM sync_history WHERE event_type='pull'").fetchall()
    assert len(rows) == 1
    assert rows[0]["machine_id"] == "bob-windows"
    conn.close()
```

**Step 2: Run test to verify it fails**

Run: `cd cli && python -m pytest tests/test_history.py -v`
Expected: FAIL — `karma.history` module doesn't exist.

**Step 3: Implement**

Create `cli/karma/history.py`:

```python
"""Record sync events to SQLite for audit trail."""

import sqlite3
from datetime import datetime, timezone
from pathlib import Path

KARMA_BASE = Path.home() / ".claude_karma"

SYNC_HISTORY_SCHEMA = """
CREATE TABLE IF NOT EXISTS sync_history (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    event_type    TEXT NOT NULL,
    user_id       TEXT NOT NULL,
    machine_id    TEXT NOT NULL,
    project       TEXT NOT NULL,
    cid           TEXT,
    ipns_key      TEXT,
    session_count INTEGER DEFAULT 0,
    created_at    TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_sync_history_user ON sync_history(user_id);
CREATE INDEX IF NOT EXISTS idx_sync_history_project ON sync_history(project);
CREATE INDEX IF NOT EXISTS idx_sync_history_created ON sync_history(created_at);
"""


def _get_db_path() -> Path:
    return KARMA_BASE / "metadata.db"


def ensure_sync_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(SYNC_HISTORY_SCHEMA)


def record_sync_event(
    event_type: str,
    user_id: str,
    machine_id: str,
    project: str,
    cid: str = "",
    ipns_key: str = "",
    session_count: int = 0,
) -> None:
    """Write a push or pull event to sync_history."""
    db_path = _get_db_path()
    db_path.parent.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(str(db_path))
    try:
        ensure_sync_schema(conn)
        conn.execute(
            "INSERT INTO sync_history (event_type, user_id, machine_id, project, cid, ipns_key, session_count, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (event_type, user_id, machine_id, project, cid, ipns_key, session_count,
             datetime.now(timezone.utc).isoformat()),
        )
        conn.commit()
    finally:
        conn.close()
```

Then modify `cli/karma/main.py` — in the `sync` command, after successful sync:

```python
                # Record push event
                from karma.history import record_sync_event
                record_sync_event(
                    event_type="push",
                    user_id=config.user_id,
                    machine_id=config.machine_id,
                    project=project_name,
                    cid=cid,
                    ipns_key=config.ipns_key_name,
                    session_count=count,
                )
```

In the `pull` command, after each successful member pull:

```python
    for r in results:
        if r["status"] == "ok":
            from karma.history import record_sync_event
            record_sync_event(
                event_type="pull",
                user_id=r["member"],
                machine_id=r["member"],  # team member name encodes machine
                project="all",  # pull fetches all projects
                cid=r["cid"],
            )
```

**Step 4: Run tests**

Run: `cd cli && python -m pytest tests/test_history.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add cli/karma/history.py cli/karma/main.py cli/tests/test_history.py
git commit -m "feat: record push/pull events to sync_history SQLite"
```

---

## Task 5: API — `/sync/status` endpoint

**Files:**
- Create: `api/routers/sync.py`
- Modify: `api/main.py` (register router)
- Test: `api/tests/api/test_sync_router.py`

**Step 1: Write the failing test**

Create `api/tests/api/test_sync_router.py`:

```python
"""Tests for /sync API endpoints."""
import json
import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client():
    from main import app
    return TestClient(app)


def test_sync_status_not_initialized(client, tmp_path, monkeypatch):
    """Returns initialized=false when no sync-config.json exists."""
    monkeypatch.setattr("routers.sync.SYNC_CONFIG_PATH", tmp_path / "nope.json")
    resp = client.get("/sync/status")
    assert resp.status_code == 200
    data = resp.json()
    assert data["initialized"] is False


def test_sync_status_initialized(client, tmp_path, monkeypatch):
    """Returns identity info when sync-config.json exists."""
    config_path = tmp_path / "sync-config.json"
    config_path.write_text(json.dumps({
        "user_id": "alice",
        "machine_id": "macbook-pro",
        "ipns_key_name": "karma-alice-macbook-pro",
        "projects": {},
        "team": {},
        "ipfs_api": "http://127.0.0.1:5001",
    }))
    monkeypatch.setattr("routers.sync.SYNC_CONFIG_PATH", config_path)

    resp = client.get("/sync/status")
    assert resp.status_code == 200
    data = resp.json()
    assert data["initialized"] is True
    assert data["user_id"] == "alice"
    assert data["machine_id"] == "macbook-pro"
```

**Step 2: Run test to verify it fails**

Run: `cd api && python -m pytest tests/api/test_sync_router.py -v`
Expected: FAIL — `routers.sync` doesn't exist.

**Step 3: Implement**

Create `api/routers/sync.py`:

```python
"""Sync status API — IPFS daemon health, project sync state, team info, history."""

import json
import logging
import sqlite3
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Query
from pydantic import BaseModel

logger = logging.getLogger(__name__)

router = APIRouter()

KARMA_BASE = Path.home() / ".claude_karma"
SYNC_CONFIG_PATH = KARMA_BASE / "sync-config.json"
REMOTE_SESSIONS_DIR = KARMA_BASE / "remote-sessions"


class SyncStatus(BaseModel):
    initialized: bool
    user_id: Optional[str] = None
    machine_id: Optional[str] = None
    ipns_key_name: Optional[str] = None
    ipfs_running: Optional[bool] = None
    ipfs_peer_count: Optional[int] = None


class ProjectSyncState(BaseModel):
    name: str
    path: str
    encoded_name: str
    local_session_count: int
    synced_session_count: int
    unpushed_count: int
    last_sync_at: Optional[str] = None
    last_sync_cid: Optional[str] = None
    status: str  # "up_to_date", "unpushed", "never_synced"


class TeamMachine(BaseModel):
    machine_id: str
    ipns_key: str
    last_pull_at: Optional[str] = None
    projects: list[dict]


class TeamMember(BaseModel):
    user_id: str
    machines: list[TeamMachine]


class SyncHistoryEntry(BaseModel):
    id: int
    event_type: str
    user_id: str
    machine_id: str
    project: str
    cid: Optional[str] = None
    session_count: int
    created_at: str


def _load_sync_config() -> Optional[dict]:
    if not SYNC_CONFIG_PATH.exists():
        return None
    try:
        return json.loads(SYNC_CONFIG_PATH.read_text())
    except (json.JSONDecodeError, OSError):
        return None


@router.get("/status", response_model=SyncStatus)
def get_sync_status() -> SyncStatus:
    """Get IPFS daemon health, identity, and initialization state."""
    config = _load_sync_config()
    if config is None:
        return SyncStatus(initialized=False)

    return SyncStatus(
        initialized=True,
        user_id=config.get("user_id"),
        machine_id=config.get("machine_id"),
        ipns_key_name=config.get("ipns_key_name"),
        # IPFS status checked client-side or via a separate health probe
        ipfs_running=None,
        ipfs_peer_count=None,
    )


@router.get("/projects", response_model=list[ProjectSyncState])
def get_sync_projects() -> list[ProjectSyncState]:
    """Get per-project sync state: local vs synced session counts."""
    config = _load_sync_config()
    if config is None:
        return []

    results = []
    claude_projects_dir = Path.home() / ".claude" / "projects"

    for name, proj in config.get("projects", {}).items():
        encoded = proj.get("encoded_name", "")
        local_dir = claude_projects_dir / encoded

        # Count local session JSONL files
        local_count = 0
        if local_dir.is_dir():
            local_count = len([
                f for f in local_dir.glob("*.jsonl")
                if not f.name.startswith("agent-")
            ])

        # Get synced count from last manifest
        synced_count = 0
        last_sync_cid = proj.get("last_sync_cid")
        last_sync_at = proj.get("last_sync_at")

        if last_sync_cid:
            # Try to get session count from the manifest we know about
            # For now, use the config's recorded state
            synced_count = local_count  # Approximation until we track per-sync counts

        unpushed = local_count - synced_count
        if not last_sync_cid:
            status = "never_synced"
            unpushed = local_count
        elif unpushed > 0:
            status = "unpushed"
        else:
            status = "up_to_date"

        results.append(ProjectSyncState(
            name=name,
            path=proj.get("path", ""),
            encoded_name=encoded,
            local_session_count=local_count,
            synced_session_count=synced_count,
            unpushed_count=max(0, unpushed),
            last_sync_at=last_sync_at,
            last_sync_cid=last_sync_cid,
            status=status,
        ))

    return results


@router.get("/team", response_model=list[TeamMember])
def get_sync_team() -> list[TeamMember]:
    """Get team members grouped by user_id with their machines."""
    config = _load_sync_config()
    if config is None:
        return []

    # Group team members by user_id (extracted from manifests)
    user_machines: dict[str, list[TeamMachine]] = {}

    for member_name, member_data in config.get("team", {}).items():
        ipns_key = member_data.get("ipns_key", "")

        # Check if we have pulled data for this member
        member_dir = REMOTE_SESSIONS_DIR / member_name
        projects = []
        user_id = member_name  # default
        last_pull_at = None

        if member_dir.is_dir():
            for proj_dir in sorted(member_dir.iterdir()):
                if not proj_dir.is_dir():
                    continue
                manifest_path = proj_dir / "manifest.json"
                if manifest_path.exists():
                    try:
                        manifest = json.loads(manifest_path.read_text())
                        user_id = manifest.get("user_id", member_name)
                        synced_at = manifest.get("synced_at")
                        if synced_at and (last_pull_at is None or synced_at > last_pull_at):
                            last_pull_at = synced_at
                        projects.append({
                            "encoded_name": proj_dir.name,
                            "session_count": manifest.get("session_count", 0),
                        })
                    except (json.JSONDecodeError, OSError):
                        pass

        machine = TeamMachine(
            machine_id=member_name,
            ipns_key=ipns_key,
            last_pull_at=last_pull_at,
            projects=projects,
        )

        if user_id not in user_machines:
            user_machines[user_id] = []
        user_machines[user_id].append(machine)

    return [
        TeamMember(user_id=uid, machines=machines)
        for uid, machines in sorted(user_machines.items())
    ]


@router.get("/history", response_model=list[SyncHistoryEntry])
def get_sync_history(
    limit: int = Query(default=50, le=200),
    offset: int = Query(default=0, ge=0),
) -> list[SyncHistoryEntry]:
    """Get paginated sync history from SQLite."""
    db_path = KARMA_BASE / "metadata.db"
    if not db_path.exists():
        return []

    try:
        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row

        # Check if sync_history table exists
        tables = {
            r[0] for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
        if "sync_history" not in tables:
            conn.close()
            return []

        rows = conn.execute(
            "SELECT id, event_type, user_id, machine_id, project, cid, session_count, created_at "
            "FROM sync_history ORDER BY created_at DESC LIMIT ? OFFSET ?",
            (limit, offset),
        ).fetchall()
        conn.close()

        return [SyncHistoryEntry(**dict(r)) for r in rows]
    except (sqlite3.OperationalError, sqlite3.DatabaseError):
        return []
```

Register in `api/main.py` — add import and include:

```python
from routers import sync as sync_router  # add to imports

app.include_router(sync_router.router, prefix="/sync", tags=["sync"])  # add after remote_sessions
```

**Step 4: Run tests**

Run: `cd api && python -m pytest tests/api/test_sync_router.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add api/routers/sync.py api/main.py api/tests/api/test_sync_router.py
git commit -m "feat: add /sync API router (status, projects, team, history)"
```

---

## Task 6: Frontend — `/sync` page (My Status zone)

**Files:**
- Create: `frontend/src/routes/sync/+page.server.ts`
- Create: `frontend/src/routes/sync/+page.svelte`
- Modify: `frontend/src/lib/components/Header.svelte` (add Sync nav link)

**Step 1: Create server load function**

Create `frontend/src/routes/sync/+page.server.ts`:

```typescript
import type { PageServerLoad } from './$types';
import { API_BASE } from '$lib/config';
import { safeFetch } from '$lib/utils/api-fetch';

interface SyncStatus {
	initialized: boolean;
	user_id: string | null;
	machine_id: string | null;
	ipns_key_name: string | null;
	ipfs_running: boolean | null;
	ipfs_peer_count: number | null;
}

interface ProjectSyncState {
	name: string;
	path: string;
	encoded_name: string;
	local_session_count: number;
	synced_session_count: number;
	unpushed_count: number;
	last_sync_at: string | null;
	last_sync_cid: string | null;
	status: 'up_to_date' | 'unpushed' | 'never_synced';
}

interface TeamMachine {
	machine_id: string;
	ipns_key: string;
	last_pull_at: string | null;
	projects: Array<{ encoded_name: string; session_count: number }>;
}

interface TeamMember {
	user_id: string;
	machines: TeamMachine[];
}

interface SyncHistoryEntry {
	id: number;
	event_type: string;
	user_id: string;
	machine_id: string;
	project: string;
	cid: string | null;
	session_count: number;
	created_at: string;
}

export const load: PageServerLoad = async ({ fetch }) => {
	const [statusResult, projectsResult, teamResult, historyResult] = await Promise.all([
		safeFetch<SyncStatus>(fetch, `${API_BASE}/sync/status`),
		safeFetch<ProjectSyncState[]>(fetch, `${API_BASE}/sync/projects`),
		safeFetch<TeamMember[]>(fetch, `${API_BASE}/sync/team`),
		safeFetch<SyncHistoryEntry[]>(fetch, `${API_BASE}/sync/history?limit=20`)
	]);

	return {
		status: statusResult.ok ? statusResult.data : null,
		projects: projectsResult.ok ? projectsResult.data : [],
		team: teamResult.ok ? teamResult.data : [],
		history: historyResult.ok ? historyResult.data : [],
		error: statusResult.ok ? null : statusResult.message
	};
};
```

**Step 2: Create the Svelte page**

Create `frontend/src/routes/sync/+page.svelte`:

```svelte
<script lang="ts">
	import PageHeader from '$lib/components/layout/PageHeader.svelte';
	import {
		RefreshCw,
		Wifi,
		WifiOff,
		CheckCircle,
		AlertTriangle,
		XCircle,
		Monitor,
		Clock,
		Users,
		FolderGit2,
		ArrowUpCircle,
		ArrowDownCircle
	} from 'lucide-svelte';

	let { data } = $props();

	function timeAgo(iso: string | null): string {
		if (!iso) return 'never';
		const diff = Date.now() - new Date(iso).getTime();
		const mins = Math.floor(diff / 60000);
		if (mins < 1) return 'just now';
		if (mins < 60) return `${mins}m ago`;
		const hours = Math.floor(mins / 60);
		if (hours < 24) return `${hours}h ago`;
		const days = Math.floor(hours / 24);
		return `${days}d ago`;
	}
</script>

<PageHeader
	title="Sync"
	icon={RefreshCw}
	iconColor="--nav-purple"
	breadcrumbs={[{ label: 'Dashboard', href: '/' }, { label: 'Sync' }]}
/>

<div class="space-y-6">
	<!-- Zone 1: My Status -->
	<section class="border border-[var(--border)] rounded-[var(--radius-lg)] p-5 bg-[var(--bg-base)]">
		<h2 class="text-sm font-semibold text-[var(--text-secondary)] uppercase tracking-wider mb-4">
			My Status
		</h2>

		{#if !data.status || !data.status.initialized}
			<div class="flex items-center gap-3 text-[var(--text-muted)]">
				<XCircle size={18} class="text-red-400" />
				<div>
					<p class="font-medium text-[var(--text-primary)]">Not initialized</p>
					<p class="text-sm">
						Run <code class="px-1.5 py-0.5 bg-[var(--bg-muted)] rounded text-xs font-mono"
							>karma init</code
						> to set up IPFS sync.
					</p>
				</div>
			</div>
		{:else}
			<div class="grid grid-cols-1 sm:grid-cols-3 gap-4">
				<div class="flex items-center gap-2">
					<Monitor size={16} class="text-[var(--text-muted)]" />
					<div>
						<p class="text-xs text-[var(--text-muted)]">Identity</p>
						<p class="font-medium text-sm">
							{data.status.user_id}
							<span class="text-[var(--text-muted)]">@ {data.status.machine_id}</span>
						</p>
					</div>
				</div>
				<div class="flex items-center gap-2">
					{#if data.status.ipfs_running === true}
						<Wifi size={16} class="text-emerald-400" />
						<div>
							<p class="text-xs text-[var(--text-muted)]">IPFS Daemon</p>
							<p class="font-medium text-sm text-emerald-400">
								Running ({data.status.ipfs_peer_count ?? '?'} peers)
							</p>
						</div>
					{:else if data.status.ipfs_running === false}
						<WifiOff size={16} class="text-red-400" />
						<div>
							<p class="text-xs text-[var(--text-muted)]">IPFS Daemon</p>
							<p class="font-medium text-sm text-red-400">Not running</p>
						</div>
					{:else}
						<Wifi size={16} class="text-[var(--text-muted)]" />
						<div>
							<p class="text-xs text-[var(--text-muted)]">IPFS Daemon</p>
							<p class="font-medium text-sm text-[var(--text-muted)]">Unknown</p>
						</div>
					{/if}
				</div>
				<div class="flex items-center gap-2">
					<RefreshCw size={16} class="text-[var(--text-muted)]" />
					<div>
						<p class="text-xs text-[var(--text-muted)]">IPNS Key</p>
						<p class="font-mono text-xs text-[var(--text-secondary)] truncate max-w-[200px]">
							{data.status.ipns_key_name ?? 'none'}
						</p>
					</div>
				</div>
			</div>
		{/if}
	</section>

	<!-- Zone 2: My Projects -->
	{#if data.projects.length > 0}
		<section
			class="border border-[var(--border)] rounded-[var(--radius-lg)] p-5 bg-[var(--bg-base)]"
		>
			<h2
				class="text-sm font-semibold text-[var(--text-secondary)] uppercase tracking-wider mb-4"
			>
				My Projects
			</h2>
			<div class="space-y-3">
				{#each data.projects as project}
					<div
						class="flex items-center justify-between py-3 px-4 rounded-[var(--radius-md)] bg-[var(--bg-subtle)]"
					>
						<div class="flex items-center gap-3">
							<FolderGit2 size={16} class="text-[var(--text-muted)]" />
							<div>
								<span class="font-medium text-sm text-[var(--text-primary)]">{project.name}</span>
								<p class="text-xs text-[var(--text-muted)]">
									{project.local_session_count} sessions
									{#if project.last_sync_at}
										&middot; synced {timeAgo(project.last_sync_at)}
									{/if}
								</p>
							</div>
						</div>
						<div class="flex items-center gap-2">
							{#if project.status === 'up_to_date'}
								<span class="flex items-center gap-1.5 text-xs text-emerald-400">
									<CheckCircle size={14} />
									Up to date
								</span>
							{:else if project.status === 'unpushed'}
								<span class="flex items-center gap-1.5 text-xs text-amber-400">
									<AlertTriangle size={14} />
									{project.unpushed_count} unpushed
								</span>
							{:else}
								<span class="flex items-center gap-1.5 text-xs text-[var(--text-muted)]">
									<XCircle size={14} />
									Never synced
								</span>
							{/if}
						</div>
					</div>
				{/each}
			</div>
		</section>
	{/if}

	<!-- Zone 3: Team -->
	{#if data.team.length > 0}
		<section
			class="border border-[var(--border)] rounded-[var(--radius-lg)] p-5 bg-[var(--bg-base)]"
		>
			<h2
				class="text-sm font-semibold text-[var(--text-secondary)] uppercase tracking-wider mb-4"
			>
				Team
			</h2>
			<div class="space-y-4">
				{#each data.team as member}
					<div>
						<h3 class="font-medium text-sm text-[var(--text-primary)] mb-2 flex items-center gap-2">
							<Users size={14} class="text-[var(--text-muted)]" />
							{member.user_id}
						</h3>
						<div class="ml-5 space-y-2">
							{#each member.machines as machine}
								<div
									class="flex items-center justify-between py-2 px-3 rounded-[var(--radius-md)] bg-[var(--bg-subtle)]"
								>
									<div class="flex items-center gap-2">
										<Monitor size={14} class="text-[var(--text-muted)]" />
										<span class="text-sm text-[var(--text-secondary)]">{machine.machine_id}</span>
									</div>
									<div class="flex items-center gap-3 text-xs text-[var(--text-muted)]">
										{#each machine.projects as proj}
											<span>{proj.session_count} sessions</span>
										{/each}
										{#if machine.last_pull_at}
											<span class="flex items-center gap-1">
												<Clock size={12} />
												{timeAgo(machine.last_pull_at)}
											</span>
										{/if}
									</div>
								</div>
							{/each}
						</div>
					</div>
				{/each}
			</div>
		</section>
	{/if}

	<!-- Zone 4: Sync History -->
	{#if data.history.length > 0}
		<section
			class="border border-[var(--border)] rounded-[var(--radius-lg)] p-5 bg-[var(--bg-base)]"
		>
			<h2
				class="text-sm font-semibold text-[var(--text-secondary)] uppercase tracking-wider mb-4"
			>
				Sync History
			</h2>
			<div class="overflow-x-auto">
				<table class="w-full text-sm">
					<thead>
						<tr class="text-left text-xs text-[var(--text-muted)] border-b border-[var(--border)]">
							<th class="pb-2 pr-4">Time</th>
							<th class="pb-2 pr-4">Type</th>
							<th class="pb-2 pr-4">User</th>
							<th class="pb-2 pr-4">Machine</th>
							<th class="pb-2 pr-4">Project</th>
							<th class="pb-2 text-right">Sessions</th>
						</tr>
					</thead>
					<tbody>
						{#each data.history as entry}
							<tr class="border-b border-[var(--border)]/50">
								<td class="py-2 pr-4 text-[var(--text-muted)]">{timeAgo(entry.created_at)}</td>
								<td class="py-2 pr-4">
									{#if entry.event_type === 'push'}
										<span class="flex items-center gap-1 text-blue-400">
											<ArrowUpCircle size={14} />
											push
										</span>
									{:else}
										<span class="flex items-center gap-1 text-emerald-400">
											<ArrowDownCircle size={14} />
											pull
										</span>
									{/if}
								</td>
								<td class="py-2 pr-4 text-[var(--text-primary)]">{entry.user_id}</td>
								<td class="py-2 pr-4 text-[var(--text-secondary)]">{entry.machine_id}</td>
								<td class="py-2 pr-4 text-[var(--text-secondary)]">{entry.project}</td>
								<td class="py-2 text-right text-[var(--text-primary)]">{entry.session_count}</td>
							</tr>
						{/each}
					</tbody>
				</table>
			</div>
		</section>
	{/if}
</div>
```

**Step 3: Add Sync link to Header**

In `frontend/src/lib/components/Header.svelte`, add a "Sync" nav link between "Team" and the settings icon. In both the desktop nav and mobile nav sections, add:

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

**Step 4: Verify**

Run: `cd frontend && npm run check`
Expected: No type errors.

**Step 5: Commit**

```bash
git add frontend/src/routes/sync/ frontend/src/lib/components/Header.svelte
git commit -m "feat: add /sync page with four-zone dashboard"
```

---

## Task 7: Run all tests and verify

**Step 1: Run API tests**

```bash
cd api && python -m pytest tests/ -v
```

Expected: All tests pass, including new sync tests.

**Step 2: Run CLI tests**

```bash
cd cli && python -m pytest tests/ -v
```

Expected: All tests pass.

**Step 3: Run frontend type check**

```bash
cd frontend && npm run check
```

Expected: No errors.

**Step 4: Final commit**

If any fixes were needed, commit them:

```bash
git add -A && git commit -m "fix: test and type check fixes for sync feature"
```

---

## Summary of Changes

| Layer | Files | What Changes |
|-------|-------|-------------|
| **SQLite** | `api/db/schema.py` | Schema v10: `sync_history` table + indexes |
| **CLI** | `cli/karma/config.py` | `ipns_key_name` field on SyncConfig |
| **CLI** | `cli/karma/main.py` | `karma status` command, push/pull event recording |
| **CLI** | `cli/karma/history.py` | New module: write sync events to SQLite |
| **API** | `api/routers/sync.py` | New router: `/sync/status`, `/sync/projects`, `/sync/team`, `/sync/history` |
| **API** | `api/main.py` | Register sync router |
| **Frontend** | `frontend/src/routes/sync/` | New `/sync` page with 4-zone layout |
| **Frontend** | `frontend/src/lib/components/Header.svelte` | Add "Sync" nav link |
| **Tests** | 3 new test files | Schema, CLI, API endpoint tests |
