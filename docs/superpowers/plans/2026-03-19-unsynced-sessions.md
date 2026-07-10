# Unsynced Sessions Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let users see which sessions are ready to sync and trigger on-demand packaging at global, team, and per-project granularity.

**Architecture:** Extract packaging pipeline from watcher_manager into a shared PackagingService. Add a `POST /sync/package` endpoint with scope params. Fix the gap calculation to exclude active sessions. Surface sync badges and "Sync Now" buttons in TeamProjectsTab and fix OverviewTab's sync action.

**Tech Stack:** Python/FastAPI (backend), Svelte 5 (frontend), SQLite, SessionPackager (cli/karma/packager.py)

**Spec:** `docs/superpowers/specs/2026-03-19-unsynced-sessions-design.md`

---

### Task 1: Extract PackagingService from watcher_manager

**Files:**
- Create: `api/services/sync/packaging_service.py`
- Modify: `api/services/watcher_manager.py:339-414`
- Test: `api/tests/test_packaging_service.py`

- [ ] **Step 1: Write the failing test**

Create `api/tests/test_packaging_service.py`:

```python
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import sqlite3
import threading
from unittest.mock import MagicMock, patch

import pytest
from db.schema import ensure_schema
from domain.team import Team
from domain.project import SharedProject
from domain.subscription import Subscription, SubscriptionStatus, SyncDirection
from domain.member import Member, MemberStatus
from repositories.team_repo import TeamRepository
from repositories.project_repo import ProjectRepository
from repositories.subscription_repo import SubscriptionRepository
from repositories.member_repo import MemberRepository


@pytest.fixture
def conn():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA foreign_keys=ON")
    ensure_schema(c)
    return c


@pytest.fixture
def seeded_conn(conn):
    """Seed a team with one project and an accepted send subscription."""
    TeamRepository().save(conn, Team(name="t1", leader_device_id="D1", leader_member_tag="jay.mac"))
    ProjectRepository().save(conn, SharedProject(
        team_name="t1", git_identity="owner/repo",
        encoded_name="-Users-me-repo", folder_suffix="owner-repo",
    ))
    MemberRepository().save(conn, Member(
        team_name="t1", member_tag="jay.mac", device_id="D1",
        user_id="jay", machine_tag="mac", status=MemberStatus.ACTIVE,
    ))
    sub = Subscription(
        member_tag="jay.mac", team_name="t1",
        project_git_identity="owner/repo",
    ).accept(SyncDirection.BOTH)
    SubscriptionRepository().save(conn, sub)
    return conn


class TestPackagingServiceResolve:
    def test_resolve_projects_returns_accepted_send_projects(self, seeded_conn):
        from services.sync.packaging_service import PackagingService
        svc = PackagingService(member_tag="jay.mac")
        projects = svc.resolve_packagable_projects(seeded_conn)
        assert len(projects) == 1
        assert projects[0]["git_identity"] == "owner/repo"
        assert projects[0]["team_name"] == "t1"

    def test_resolve_skips_receive_only_subscription(self, seeded_conn):
        # Change subscription to receive-only
        sub = SubscriptionRepository().get(seeded_conn, "jay.mac", "t1", "owner/repo")
        updated = sub.change_direction(SyncDirection.RECEIVE)
        SubscriptionRepository().save(seeded_conn, updated)

        from services.sync.packaging_service import PackagingService
        svc = PackagingService(member_tag="jay.mac")
        projects = svc.resolve_packagable_projects(seeded_conn)
        assert len(projects) == 0

    def test_resolve_no_scope_returns_all_teams(self, seeded_conn):
        from services.sync.packaging_service import PackagingService
        svc = PackagingService(member_tag="jay.mac")
        projects = svc.resolve_packagable_projects(seeded_conn)
        assert len(projects) == 1

    def test_resolve_with_team_filter(self, seeded_conn):
        from services.sync.packaging_service import PackagingService
        svc = PackagingService(member_tag="jay.mac")
        projects = svc.resolve_packagable_projects(seeded_conn, team_name="t1")
        assert len(projects) == 1
        projects = svc.resolve_packagable_projects(seeded_conn, team_name="nonexistent")
        assert len(projects) == 0

    def test_resolve_with_project_filter(self, seeded_conn):
        from services.sync.packaging_service import PackagingService
        svc = PackagingService(member_tag="jay.mac")
        projects = svc.resolve_packagable_projects(
            seeded_conn, team_name="t1", git_identity="owner/repo",
        )
        assert len(projects) == 1
        projects = svc.resolve_packagable_projects(
            seeded_conn, team_name="t1", git_identity="nope",
        )
        assert len(projects) == 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd api && python -m pytest tests/test_packaging_service.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'services.sync.packaging_service'`

- [ ] **Step 3: Implement PackagingService**

Create `api/services/sync/packaging_service.py`:

```python
"""Shared packaging service — used by both watcher and on-demand endpoint."""
from __future__ import annotations

import logging
import sqlite3
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)

# Per-project locks to prevent concurrent packaging of the same project
_project_locks: dict[str, threading.Lock] = {}
_locks_lock = threading.Lock()


def _get_project_lock(encoded_name: str) -> threading.Lock:
    with _locks_lock:
        if encoded_name not in _project_locks:
            _project_locks[encoded_name] = threading.Lock()
        return _project_locks[encoded_name]


@dataclass
class PackageResult:
    team_name: str
    git_identity: str
    sessions_packaged: int = 0
    error: Optional[str] = None


class PackagingService:
    """Centralised session packaging — resolves subscriptions, builds outbox
    paths, calls SessionPackager, logs events."""

    def __init__(
        self,
        member_tag: str,
        user_id: str = "unknown",
        machine_id: str = "unknown",
        device_id: str = "",
    ):
        self.member_tag = member_tag
        self.user_id = user_id
        self.machine_id = machine_id
        self.device_id = device_id

    def resolve_packagable_projects(
        self,
        conn: sqlite3.Connection,
        *,
        team_name: Optional[str] = None,
        git_identity: Optional[str] = None,
    ) -> list[dict[str, Any]]:
        """Return projects the current member can package (accepted + send/both).

        Each entry: {"team_name", "git_identity", "encoded_name", "folder_suffix"}
        """
        from repositories.subscription_repo import SubscriptionRepository
        from repositories.project_repo import ProjectRepository

        subs = SubscriptionRepository().list_for_member(conn, self.member_tag)
        results: list[dict[str, Any]] = []
        seen: set[tuple[str, str]] = set()  # dedup by (encoded_name, team_name)

        for s in subs:
            if s.status.value != "accepted":
                continue
            if s.direction.value not in ("send", "both"):
                continue
            if team_name and s.team_name != team_name:
                continue

            project = ProjectRepository().get(conn, s.team_name, s.project_git_identity)
            if not project or project.status.value != "shared":
                continue
            if git_identity and project.git_identity != git_identity:
                continue

            enc = project.encoded_name or ""
            key = (enc, s.team_name)
            if key in seen:
                continue
            seen.add(key)

            results.append({
                "team_name": s.team_name,
                "git_identity": project.git_identity,
                "encoded_name": enc,
                "folder_suffix": project.folder_suffix,
            })
        return results

    def package_project(
        self,
        conn: sqlite3.Connection,
        *,
        team_name: str,
        git_identity: str,
        encoded_name: str,
        folder_suffix: str,
    ) -> PackageResult:
        """Package sessions for a single project. Thread-safe via per-project lock."""
        from karma.packager import SessionPackager
        from karma.worktree_discovery import find_worktree_dirs
        from karma.config import KARMA_BASE
        from services.syncthing.folder_manager import build_outbox_folder_id

        lock = _get_project_lock(encoded_name)
        if not lock.acquire(blocking=False):
            return PackageResult(
                team_name=team_name,
                git_identity=git_identity,
                error="Packaging already in progress",
            )

        try:
            projects_dir = Path.home() / ".claude" / "projects"
            claude_dir = projects_dir / encoded_name
            if not claude_dir.is_dir():
                return PackageResult(
                    team_name=team_name,
                    git_identity=git_identity,
                    error=f"Project dir not found: {encoded_name}",
                )

            # Resolve outbox path
            folder_id = build_outbox_folder_id(self.member_tag, folder_suffix)
            outbox = KARMA_BASE / folder_id
            outbox.mkdir(parents=True, exist_ok=True)

            # Discover worktree dirs
            wt_dirs = find_worktree_dirs(encoded_name, projects_dir)

            packager = SessionPackager(
                project_dir=claude_dir,
                user_id=self.user_id,
                machine_id=self.machine_id,
                device_id=self.device_id,
                project_path="",
                extra_dirs=wt_dirs,
                member_tag=self.member_tag,
            )
            manifest = packager.package(staging_dir=outbox)
            count = len(manifest.sessions) if manifest else 0

            # Log sync events
            self._log_events(conn, team_name, git_identity, manifest)

            return PackageResult(
                team_name=team_name,
                git_identity=git_identity,
                sessions_packaged=count,
            )
        except Exception as e:
            logger.warning("Packaging failed for %s: %s", encoded_name, e)
            return PackageResult(
                team_name=team_name,
                git_identity=git_identity,
                error=str(e),
            )
        finally:
            lock.release()

    def _log_events(self, conn, team_name, git_identity, manifest):
        if not manifest or not manifest.sessions:
            return
        try:
            from repositories.event_repo import EventRepository
            from domain.events import SyncEvent, SyncEventType
            repo = EventRepository()
            for session_uuid in manifest.sessions:
                repo.log(conn, SyncEvent(
                    event_type=SyncEventType.session_packaged,
                    team_name=team_name,
                    project_git_identity=git_identity,
                    session_uuid=session_uuid,
                ))
        except Exception:
            logger.debug("Failed to log session_packaged events", exc_info=True)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd api && python -m pytest tests/test_packaging_service.py -v`
Expected: All 5 tests PASS

- [ ] **Step 5: Refactor watcher_manager to use PackagingService**

In `api/services/watcher_manager.py`, replace the `make_package_fn` closure (lines 339-414) to delegate to `PackagingService.package_project()`:

```python
# Replace make_package_fn with:
def make_package_fn(
    en=encoded, pt=proj_teams, ps=proj.get("folder_suffix", en),
    gi=proj.get("git_identity", en),
):
    def package():
        from db.connection import get_writer_db
        from services.sync.packaging_service import PackagingService
        db = get_writer_db()
        svc = PackagingService(
            member_tag=member_tag or user_id,
            user_id=user_id,
            machine_id=machine_id,
            device_id=device_id,
        )
        # Try each team this project belongs to
        for tn in pt:
            svc.package_project(
                db,
                team_name=tn,
                git_identity=gi,
                encoded_name=en,
                folder_suffix=ps,
            )
        # Preserve _last_packaged_at for status reporting
        self._last_packaged_at = (
            datetime.now(timezone.utc).isoformat()
        )
    return package
```

- [ ] **Step 6: Run existing tests to verify no regressions**

Run: `cd api && python -m pytest tests/ -v --timeout=30 -x`
Expected: All existing tests PASS

- [ ] **Step 7: Commit**

```bash
git add api/services/sync/packaging_service.py api/tests/test_packaging_service.py api/services/watcher_manager.py
git commit -m "refactor(sync): extract PackagingService from watcher_manager"
```

---

### Task 2: Add `POST /sync/package` endpoint

**Files:**
- Modify: `api/routers/sync_system.py`
- Test: `api/tests/test_sync_package_endpoint.py`

- [ ] **Step 1: Write the failing test**

Create `api/tests/test_sync_package_endpoint.py`:

```python
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from unittest.mock import AsyncMock, MagicMock, patch
import pytest
from httpx import AsyncClient, ASGITransport
from main import app


@pytest.fixture
def mock_config():
    config = MagicMock()
    config.member_tag = "jay.mac"
    config.user_id = "jay"
    config.machine_id = "mac"
    config.device_id = "D1"
    config.syncthing = MagicMock()
    config.syncthing.device_id = "D1"
    return config


@pytest.mark.asyncio
async def test_package_endpoint_exists(mock_config):
    """POST /sync/package returns 200, not 404/405."""
    with patch("routers.sync_system.require_config", return_value=mock_config):
        with patch("services.sync.packaging_service.PackagingService") as MockSvc:
            instance = MockSvc.return_value
            instance.resolve_packagable_projects.return_value = []
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                res = await client.post("/sync/package")
                assert res.status_code != 404
                assert res.status_code != 405
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd api && python -m pytest tests/test_sync_package_endpoint.py -v`
Expected: FAIL — 404 or 405 (route doesn't exist yet)

- [ ] **Step 3: Implement the endpoint**

Add to `api/routers/sync_system.py`:

```python
@router.post("/package")
async def trigger_package(
    team_name: Optional[str] = None,
    git_identity: Optional[str] = None,
    conn: sqlite3.Connection = Depends(get_conn),
    config=Depends(require_config),
):
    """Trigger on-demand session packaging.

    Scope:
    - No params: all projects across all teams
    - team_name: all projects in that team
    - team_name + git_identity: single project
    """
    from services.sync.packaging_service import PackagingService

    svc = PackagingService(
        member_tag=config.member_tag,
        user_id=config.user_id,
        machine_id=config.machine_id,
        device_id=config.syncthing.device_id if config.syncthing else "",
    )

    projects = svc.resolve_packagable_projects(
        conn, team_name=team_name, git_identity=git_identity,
    )

    results = []
    for proj in projects:
        result = svc.package_project(
            conn,
            team_name=proj["team_name"],
            git_identity=proj["git_identity"],
            encoded_name=proj["encoded_name"],
            folder_suffix=proj["folder_suffix"],
        )
        entry = {
            "team_name": result.team_name,
            "git_identity": result.git_identity,
            "sessions_packaged": result.sessions_packaged,
        }
        if result.error:
            entry["error"] = result.error
        results.append(entry)

    return {"ok": True, "packaged": results}
```

Also add `Optional` import if not already present at top of file.

- [ ] **Step 4: Run test to verify it passes**

Run: `cd api && python -m pytest tests/test_sync_package_endpoint.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add api/routers/sync_system.py api/tests/test_sync_package_endpoint.py
git commit -m "feat(sync): add POST /sync/package endpoint for on-demand packaging"
```

---

### Task 3: Fix gap calculation — exclude active sessions

**Files:**
- Modify: `api/routers/sync_teams.py:291-366`
- Test: `api/tests/test_project_status_gap.py`

- [ ] **Step 1: Write the failing test**

Create `api/tests/test_project_status_gap.py`:

```python
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import json
import tempfile
from datetime import datetime, timezone, timedelta
from unittest.mock import patch

import pytest
from routers.sync_teams import _get_active_counts


@pytest.fixture
def live_sessions_dir(tmp_path):
    """Create a temp live-sessions dir with test data."""
    live_dir = tmp_path / "live-sessions"
    live_dir.mkdir()
    return live_dir


def _write_live_session(live_dir, slug, session_id, encoded_name, state="RUNNING", idle_minutes=0):
    now = datetime.now(timezone.utc)
    updated = now - timedelta(minutes=idle_minutes)
    data = {
        "session_id": session_id,
        "state": state,
        "transcript_path": f"/Users/me/.claude/projects/{encoded_name}/{session_id}.jsonl",
        "updated_at": updated.isoformat(),
    }
    (live_dir / f"{slug}.json").write_text(json.dumps(data))


class TestGetActiveCounts:
    def test_empty_dir_returns_empty(self, live_sessions_dir):
        result = _get_active_counts(live_sessions_dir)
        assert result == {}

    def test_running_session_counted(self, live_sessions_dir):
        _write_live_session(live_sessions_dir, "s1", "uuid-1", "-Users-me-repo", state="RUNNING")
        result = _get_active_counts(live_sessions_dir)
        assert result.get("-Users-me-repo", 0) == 1

    def test_ended_session_not_counted(self, live_sessions_dir):
        _write_live_session(live_sessions_dir, "s1", "uuid-1", "-Users-me-repo", state="ENDED")
        result = _get_active_counts(live_sessions_dir)
        assert result.get("-Users-me-repo", 0) == 0

    def test_stale_session_not_counted(self, live_sessions_dir):
        _write_live_session(live_sessions_dir, "s1", "uuid-1", "-Users-me-repo", state="RUNNING", idle_minutes=35)
        result = _get_active_counts(live_sessions_dir)
        assert result.get("-Users-me-repo", 0) == 0

    def test_multiple_projects(self, live_sessions_dir):
        _write_live_session(live_sessions_dir, "s1", "uuid-1", "-Users-me-repo-a", state="RUNNING")
        _write_live_session(live_sessions_dir, "s2", "uuid-2", "-Users-me-repo-a", state="RUNNING")
        _write_live_session(live_sessions_dir, "s3", "uuid-3", "-Users-me-repo-b", state="RUNNING")
        result = _get_active_counts(live_sessions_dir)
        assert result["-Users-me-repo-a"] == 2
        assert result["-Users-me-repo-b"] == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd api && python -m pytest tests/test_project_status_gap.py -v`
Expected: FAIL — `ImportError: cannot import name '_get_active_counts'`

- [ ] **Step 3: Implement `_get_active_counts` helper**

Add to `api/routers/sync_teams.py`, near the other helpers:

```python
def _get_active_counts(live_sessions_dir: Path | None = None) -> dict[str, int]:
    """Count active (non-ended, non-stale) sessions per project encoded_name.

    Reads ~/.claude_karma/live-sessions/*.json. Returns {encoded_name: count}.
    Uses worktree-to-parent resolution so worktree sessions roll up to
    the real project (same logic as LiveSession.resolved_project_encoded_name).
    """
    from karma.packager import STALE_LIVE_SESSION_SECONDS

    if live_sessions_dir is None:
        from config import settings as app_settings
        live_sessions_dir = app_settings.karma_base / "live-sessions"

    if not live_sessions_dir.is_dir():
        return {}

    import json as _json
    now = datetime.now(timezone.utc)
    counts: dict[str, int] = {}

    for json_file in live_sessions_dir.glob("*.json"):
        try:
            data = _json.loads(json_file.read_text(encoding="utf-8"))
            if data.get("state") == "ENDED":
                continue

            # Check staleness
            updated_str = data.get("updated_at")
            if updated_str:
                updated = datetime.fromisoformat(updated_str.replace("Z", "+00:00"))
                if updated.tzinfo is None:
                    updated = updated.replace(tzinfo=timezone.utc)
                if (now - updated).total_seconds() > STALE_LIVE_SESSION_SECONDS:
                    continue

            # Extract encoded_name from transcript_path
            tp = data.get("transcript_path", "")
            if "/projects/" not in tp:
                continue
            parts = tp.split("/projects/", 1)[1].split("/")
            if not parts:
                continue
            enc = parts[0]

            # Worktree resolution: if the encoded name looks like a worktree
            # path (contains ".claude-worktrees" or "claude/worktrees"),
            # resolve to the real project via git_root if available.
            git_root = data.get("git_root")
            if git_root and (".claude-worktrees" in enc or "-worktrees-" in enc):
                enc = "-" + git_root.lstrip("/").replace("/", "-")

            counts[enc] = counts.get(enc, 0) + 1
        except (ValueError, OSError):
            continue
    return counts
```

Also add required imports at top of file if not present: `from datetime import datetime, timezone` and `from pathlib import Path`.

- [ ] **Step 4: Run test to verify it passes**

Run: `cd api && python -m pytest tests/test_project_status_gap.py -v`
Expected: All 5 tests PASS

- [ ] **Step 5: Wire into `get_project_status` endpoint**

In `api/routers/sync_teams.py`, modify `get_project_status` (around line 338-365):

```python
    # After computing local_counts and received_by_encoded...
    # Get active session counts to exclude from gap
    active_counts = _get_active_counts()

    result = []
    for p in projects:
        # ... existing sub_counts, encoded, display logic ...
        local_count = local_counts.get(encoded, 0) if encoded else 0
        received = received_by_encoded.get(encoded, {}) if encoded else {}
        packaged_count = (
            _count_packaged(member_tag, p.folder_suffix) if member_tag else 0
        )
        active_count = active_counts.get(encoded, 0) if encoded else 0

        result.append({
            # ... existing fields ...
            "active_count": active_count,
            "gap": max(0, local_count - packaged_count - active_count) if member_tag else None,
        })
```

- [ ] **Step 6: Run all sync tests to verify no regressions**

Run: `cd api && python -m pytest tests/test_project_status_gap.py tests/test_packaging_service.py -v`
Expected: All PASS

- [ ] **Step 7: Commit**

```bash
git add api/routers/sync_teams.py api/tests/test_project_status_gap.py
git commit -m "fix(sync): exclude active sessions from gap calculation, add active_count field"
```

---

### Task 4: Update frontend TypeScript types

**Files:**
- Modify: `frontend/src/lib/api-types.ts`

- [ ] **Step 1: Update SyncProjectStatus type**

In `frontend/src/lib/api-types.ts`, replace the type alias (line 1824-1825):

```typescript
/** Per-project sync status with active session tracking */
export interface SyncProjectStatus extends SyncTeamProject {
	active_count?: number;
	subscription_counts?: {
		offered: number;
		accepted: number;
		paused: number;
		declined: number;
	};
}
```

- [ ] **Step 2: Run type check**

Run: `cd frontend && npm run check`
Expected: No new type errors

- [ ] **Step 3: Commit**

```bash
git add frontend/src/lib/api-types.ts
git commit -m "feat(sync): break SyncProjectStatus into own interface with active_count"
```

---

### Task 5: Add sync badges and actions to TeamProjectsTab

**Files:**
- Modify: `frontend/src/lib/components/team/TeamProjectsTab.svelte`

- [ ] **Step 1: Add project-status data fetching**

Add to the `<script>` section of `TeamProjectsTab.svelte`:

```typescript
import { RefreshCw, Loader2, CheckCircle2 } from 'lucide-svelte';
import type { SyncProjectStatus } from '$lib/api-types';

// Add new state variables
let projectStatuses = $state<SyncProjectStatus[]>([]);
let projectStatusLoading = $state(true);
let syncingProject = $state<string | null>(null); // git_identity of project being synced
let syncingAll = $state(false);

// Add fetch function
async function loadProjectStatus() {
    try {
        const res = await fetch(
            `${API_BASE}/sync/teams/${encodeURIComponent(teamName)}/project-status`
        ).catch(() => null);
        if (res?.ok) {
            const data = await res.json();
            projectStatuses = data.projects ?? [];
        }
    } catch {
        // non-critical
    } finally {
        projectStatusLoading = false;
    }
}

// Derive status lookup by git_identity
let statusByGit = $derived.by(() => {
    const map = new Map<string, SyncProjectStatus>();
    for (const ps of projectStatuses) {
        map.set(ps.git_identity, ps);
    }
    return map;
});

// Total team gap
let totalTeamGap = $derived(
    projectStatuses.reduce((sum, p) => sum + (p.gap ?? 0), 0)
);

// Sync a single project
async function syncProject(gitIdentity: string) {
    syncingProject = gitIdentity;
    try {
        await fetch(
            `${API_BASE}/sync/package?team_name=${encodeURIComponent(teamName)}&git_identity=${encodeURIComponent(gitIdentity)}`,
            { method: 'POST' }
        );
        await loadProjectStatus();
    } finally {
        syncingProject = null;
    }
}

// Sync all projects in this team
async function syncAllTeam() {
    syncingAll = true;
    try {
        await fetch(
            `${API_BASE}/sync/package?team_name=${encodeURIComponent(teamName)}`,
            { method: 'POST' }
        );
        await loadProjectStatus();
    } finally {
        syncingAll = false;
    }
}
```

Add a new `$effect` to trigger the fetch on mount (this component currently has no `$effect` — it receives data via props):

```typescript
$effect(() => {
    // Fetch project status on mount
    loadProjectStatus();
});
```

- [ ] **Step 2: Add "Sync All" button to Active Projects header**

The Active Projects section currently has no dedicated header element. Create one above the project list (before the `{#each activeProjects ...}` block):

```svelte
<!-- Active Projects header -->
<div class="flex items-center justify-between px-5 py-3.5 border-b border-[var(--border-subtle)]">
    <div class="flex items-center gap-2">
        <h3 class="text-sm font-semibold text-[var(--text-primary)]">Active Projects</h3>
        <span class="px-1.5 py-0.5 text-[10px] font-medium rounded bg-[var(--accent)]/10 text-[var(--accent)]">
            {activeProjects.length}
        </span>
    </div>
    {#if totalTeamGap > 0}
        <button
            onclick={syncAllTeam}
            disabled={syncingAll}
            class="flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded-[var(--radius)] bg-[var(--accent)] text-white hover:bg-[var(--accent-hover)] transition-colors disabled:opacity-50"
        >
            {#if syncingAll}
                <Loader2 size={12} class="animate-spin" />
                Syncing...
            {:else}
                <RefreshCw size={12} />
                Sync All ({totalTeamGap})
            {/if}
        </button>
    {/if}
</div>
```

- [ ] **Step 3: Add per-project sync badge and button**

In each project row, after the subscription badge, add sync status:

```svelte
<!-- After subscription badge, before direction controls -->
{@const ps = statusByGit.get(project.git_identity)}
{@const hasSendSub = mySub?.status === 'accepted' && (mySub?.direction === 'send' || mySub?.direction === 'both')}
{#if ps && hasSendSub}
    {#if (ps.gap ?? 0) === 0}
        <span class="shrink-0 flex items-center gap-1 px-2 py-1 text-[11px] font-medium rounded-full bg-[var(--success)]/10 text-[var(--success)] border border-[var(--success)]/20">
            <CheckCircle2 size={11} />
            In Sync
        </span>
    {:else}
        <span class="shrink-0 flex items-center gap-1 px-2 py-1 text-[11px] font-medium rounded-full bg-[var(--warning)]/10 text-[var(--warning)] border border-[var(--warning)]/20">
            {ps.gap} ready to sync
        </span>
        <button
            onclick={() => syncProject(project.git_identity)}
            disabled={syncingProject === project.git_identity}
            class="shrink-0 p-1.5 rounded-[var(--radius)] text-[var(--text-muted)] hover:text-[var(--accent)] hover:bg-[var(--accent)]/10 transition-colors disabled:opacity-50"
            aria-label="Sync {project.git_identity}"
        >
            {#if syncingProject === project.git_identity}
                <Loader2 size={14} class="animate-spin" />
            {:else}
                <RefreshCw size={14} />
            {/if}
        </button>
    {/if}
{/if}
```

- [ ] **Step 4: Test manually**

1. Start API: `cd api && uvicorn main:app --reload --port 8000`
2. Start frontend: `cd frontend && npm run dev`
3. Navigate to `/team/{team-name}` → Projects tab
4. Verify: sync badges show per project, "Sync All" button appears if gap > 0
5. Click "Sync" on a project → spinner → badge updates
6. Click "Sync All" → spinner → all badges update

- [ ] **Step 5: Commit**

```bash
git add frontend/src/lib/components/team/TeamProjectsTab.svelte
git commit -m "feat(sync): add sync badges and per-project/team sync buttons to TeamProjectsTab"
```

---

### Task 6: Fix OverviewTab "Sync Now" to call package + reconcile

**Files:**
- Modify: `frontend/src/lib/components/sync/OverviewTab.svelte`

- [ ] **Step 1: Update syncAllNow to call both endpoints**

In `OverviewTab.svelte`, replace the `syncAllNow` function (lines 107-116):

```typescript
async function syncAllNow() {
    syncAllActing = true;
    try {
        // Package sessions + reconcile devices in parallel
        await Promise.all([
            fetch(`${API_BASE}/sync/package`, { method: 'POST' }).catch(() => null),
            fetch(`${API_BASE}/sync/reconcile`, { method: 'POST' }).catch(() => null),
        ]);
        await loadProjectStatus();
    } finally {
        syncAllActing = false;
    }
}
```

- [ ] **Step 2: Test manually**

1. Navigate to `/sync`
2. Click "Sync Now"
3. Verify spinner shows, then counts refresh
4. Check API logs for both `/sync/package` and `/sync/reconcile` requests

- [ ] **Step 3: Run frontend type check**

Run: `cd frontend && npm run check`
Expected: No type errors

- [ ] **Step 4: Commit**

```bash
git add frontend/src/lib/components/sync/OverviewTab.svelte
git commit -m "fix(sync): Sync Now button now packages sessions + reconciles devices"
```

---

### Task 7: Final verification and cleanup

- [ ] **Step 1: Run all backend tests**

Run: `cd api && python -m pytest tests/ -v --timeout=30`
Expected: All tests PASS

- [ ] **Step 2: Run frontend type check**

Run: `cd frontend && npm run check`
Expected: No errors

- [ ] **Step 3: Manual E2E test**

1. Start API + frontend
2. `/sync` page: Verify gap excludes active sessions, "Sync Now" packages + reconciles
3. `/team/{name}` Projects tab: Verify per-project badges, per-project sync button, "Sync All" button
4. Start a Claude Code session → verify it appears as active (not in gap count)
5. End the session → verify gap increments, "Sync" button packages it

- [ ] **Step 4: Commit any fixups**

```bash
git add -A
git commit -m "chore(sync): unsynced sessions feature — final cleanup"
```
