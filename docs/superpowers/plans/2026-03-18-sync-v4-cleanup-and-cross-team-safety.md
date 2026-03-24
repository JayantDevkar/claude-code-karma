# Sync v4 Cleanup & Cross-Team Safety Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix cross-team folder cleanup destructiveness, remove dead CLI sync code, and add folder existence guarantees to reconciliation — making v4 safe for multi-team, multi-member, multi-project setups.

**Architecture:** Three workstreams: (1) Add cross-team reference counting to FolderManager cleanup methods so leaving/dissolving a team doesn't destroy folders needed by other teams, (2) Delete all dead CLI sync code that imports from the deleted `db/sync_queries.py`, (3) Add folder existence checks to Phase 3 reconciliation so it can recover from accidentally deleted folders.

**Tech Stack:** Python 3.9+, FastAPI, Pydantic 2.x, SQLite, pytest, async/await

---

## Background

### The Problem

v4's `cleanup_team_folders()` and `cleanup_project_folders()` delete Syncthing folders by matching `(member_tag × folder_suffix)`. Since folder IDs have no team scope (`karma-out--{member_tag}--{suffix}`), leaving Team A destroys folders that Team B also needs if they share the same member+project combination. This is the same root cause as v3's BP-3/BP-4 (documented in `docs/design/sync-v3-audit-findings.md`).

Additionally, the entire CLI sync module (`cli/karma/main.py`, `cli/karma/pending.py`, etc.) imports from `db/sync_queries.py` which was deleted in v4. Since the user is fully on API endpoints, this is dead code that should be removed.

### Files Involved

**Modify:**
- `api/services/syncthing/folder_manager.py` — add cross-team safety to cleanup methods
- `api/services/sync/reconciliation_service.py` — add folder existence check in Phase 3
- `api/services/sync/team_service.py` — pass `conn` to cleanup methods for DB queries

**Delete (dead CLI sync code):**
- `cli/karma/pending.py` — imports from deleted `db.sync_queries`
- `cli/karma/watcher.py` — `_maybe_check_peers()` imports from deleted modules
- Sync commands in `cli/karma/main.py` — `team`, `share`, `unshare`, `watch`, `status`, `nuke`, `join`, `leave`, `pair`

**Create (tests):**
- `api/tests/test_cross_team_cleanup.py` — multi-team overlap safety tests
- `api/tests/test_phase3_folder_recovery.py` — folder existence + recovery tests

**Reference (read-only, for context):**
- `docs/design/sync-v3-audit-findings.md` — BP-3, BP-4 (cross-team cleanup bugs)
- `docs/superpowers/specs/2026-03-17-sync-v4-domain-models-design.md` — v4 design spec
- `api/db/schema.py` — v19 schema (sync_projects, sync_subscriptions)

---

## Task 1: Add Cross-Team Folder Reference Counting to FolderManager

The core fix. Before deleting a folder, check if any other team's active subscriptions reference the same `(member_tag, folder_suffix)` pair.

**Files:**
- Modify: `api/services/syncthing/folder_manager.py`
- Modify: `api/services/sync/team_service.py` (pass `conn` through)
- Modify: `api/services/sync/reconciliation_service.py` (pass `conn` through)
- Test: `api/tests/test_cross_team_cleanup.py`

### Approach

`cleanup_team_folders()` and `cleanup_project_folders()` currently take `folder_suffixes` and `member_tags` as lists and delete the Cartesian product. The fix adds a `conn` parameter and a pre-deletion query:

```sql
-- For each candidate folder_id = karma-out--{member_tag}--{suffix}:
-- Check if any OTHER team has an active subscription for this suffix
SELECT COUNT(*) FROM sync_subscriptions s
JOIN sync_projects p ON s.team_name = p.team_name AND s.project_git_identity = p.git_identity
WHERE p.folder_suffix = ?
  AND s.member_tag = ?
  AND s.status IN ('offered', 'accepted', 'paused')
  AND s.team_name != ?
```

If count > 0, skip deletion (another team needs this folder). If count == 0, safe to delete.

- [ ] **Step 1: Write failing test — multi-team folder cleanup safety**

Create `api/tests/test_cross_team_cleanup.py`:

```python
"""Tests for cross-team safe folder cleanup.

Scenario: M1 is in T1 and T2, both sharing project P1.
Leaving T1 must NOT delete M1's P1 outbox folder because T2 still needs it.
"""
import sqlite3
import pytest
from unittest.mock import AsyncMock, MagicMock

from db.schema import ensure_schema
from domain.team import Team
from domain.member import Member, MemberStatus
from domain.project import SharedProject, derive_folder_suffix
from domain.subscription import Subscription, SubscriptionStatus, SyncDirection
from repositories.team_repo import TeamRepository
from repositories.member_repo import MemberRepository
from repositories.project_repo import ProjectRepository
from repositories.subscription_repo import SubscriptionRepository
from services.syncthing.folder_manager import FolderManager, build_outbox_folder_id


@pytest.fixture
def conn():
    db = sqlite3.connect(":memory:")
    db.execute("PRAGMA foreign_keys = ON")
    ensure_schema(db)
    return db


@pytest.fixture
def repos():
    return {
        "teams": TeamRepository(),
        "members": MemberRepository(),
        "projects": ProjectRepository(),
        "subs": SubscriptionRepository(),
    }


@pytest.fixture
def mock_client():
    client = AsyncMock()
    client.get_config_folders = AsyncMock(return_value=[
        {"id": "karma-out--alice.laptop--owner-repo", "devices": []},
        {"id": "karma-meta--team-1", "devices": []},
        {"id": "karma-meta--team-2", "devices": []},
    ])
    client.delete_config_folder = AsyncMock()
    return client


def _setup_two_teams_one_project(conn, repos):
    """Create T1 and T2, both sharing the same project, M1 in both."""
    git_id = "owner/repo"
    suffix = derive_folder_suffix(git_id)

    # Team 1
    t1 = Team(name="team-1", leader_device_id="DEV-LEADER1", leader_member_tag="leader1.mac")
    repos["teams"].save(conn, t1)
    m1_t1 = Member.from_member_tag(
        member_tag="alice.laptop", team_name="team-1",
        device_id="DEV-ALICE", status=MemberStatus.ACTIVE,
    )
    repos["members"].save(conn, m1_t1)
    p1_t1 = SharedProject(team_name="team-1", git_identity=git_id, folder_suffix=suffix)
    repos["projects"].save(conn, p1_t1)
    s1 = Subscription(
        member_tag="alice.laptop", team_name="team-1",
        project_git_identity=git_id, status=SubscriptionStatus.ACCEPTED,
        direction=SyncDirection.BOTH,
    )
    repos["subs"].save(conn, s1)

    # Team 2
    t2 = Team(name="team-2", leader_device_id="DEV-LEADER2", leader_member_tag="leader2.mac")
    repos["teams"].save(conn, t2)
    m1_t2 = Member.from_member_tag(
        member_tag="alice.laptop", team_name="team-2",
        device_id="DEV-ALICE", status=MemberStatus.ACTIVE,
    )
    repos["members"].save(conn, m1_t2)
    p1_t2 = SharedProject(team_name="team-2", git_identity=git_id, folder_suffix=suffix)
    repos["projects"].save(conn, p1_t2)
    s2 = Subscription(
        member_tag="alice.laptop", team_name="team-2",
        project_git_identity=git_id, status=SubscriptionStatus.ACCEPTED,
        direction=SyncDirection.BOTH,
    )
    repos["subs"].save(conn, s2)

    return suffix


class TestCrossTeamCleanup:

    @pytest.mark.asyncio
    async def test_cleanup_skips_folder_needed_by_other_team(self, conn, repos, mock_client):
        """Leaving T1 must NOT delete alice's outbox for owner/repo — T2 still needs it."""
        from pathlib import Path

        suffix = _setup_two_teams_one_project(conn, repos)
        mgr = FolderManager(mock_client, karma_base=Path("/tmp/karma"))

        await mgr.cleanup_team_folders(
            conn=conn,
            folder_suffixes=[suffix],
            member_tags=["alice.laptop", "leader1.mac"],
            team_name="team-1",
        )

        # The outbox folder for alice should NOT have been deleted
        deleted_ids = [call.args[0] for call in mock_client.delete_config_folder.call_args_list]
        assert "karma-out--alice.laptop--owner-repo" not in deleted_ids
        # But the metadata folder for team-1 SHOULD be deleted
        assert "karma-meta--team-1" in deleted_ids

    @pytest.mark.asyncio
    async def test_cleanup_deletes_folder_when_no_other_team(self, conn, repos, mock_client):
        """Leaving T1 when alice is NOT in T2 SHOULD delete alice's outbox."""
        from pathlib import Path

        git_id = "owner/repo"
        suffix = derive_folder_suffix(git_id)

        # Only Team 1 — no Team 2
        t1 = Team(name="team-1", leader_device_id="DEV-LEADER1", leader_member_tag="leader1.mac")
        repos["teams"].save(conn, t1)
        m1 = Member.from_member_tag(
            member_tag="alice.laptop", team_name="team-1",
            device_id="DEV-ALICE", status=MemberStatus.ACTIVE,
        )
        repos["members"].save(conn, m1)
        p1 = SharedProject(team_name="team-1", git_identity=git_id, folder_suffix=suffix)
        repos["projects"].save(conn, p1)
        s1 = Subscription(
            member_tag="alice.laptop", team_name="team-1",
            project_git_identity=git_id, status=SubscriptionStatus.ACCEPTED,
            direction=SyncDirection.BOTH,
        )
        repos["subs"].save(conn, s1)

        mgr = FolderManager(mock_client, karma_base=Path("/tmp/karma"))
        await mgr.cleanup_team_folders(
            conn=conn,
            folder_suffixes=[suffix],
            member_tags=["alice.laptop", "leader1.mac"],
            team_name="team-1",
        )

        deleted_ids = [call.args[0] for call in mock_client.delete_config_folder.call_args_list]
        assert "karma-out--alice.laptop--owner-repo" in deleted_ids

    @pytest.mark.asyncio
    async def test_cleanup_project_skips_cross_team_folder(self, conn, repos, mock_client):
        """Removing P1 from T1 must NOT delete alice's outbox if T2 shares P1."""
        from pathlib import Path

        suffix = _setup_two_teams_one_project(conn, repos)
        mgr = FolderManager(mock_client, karma_base=Path("/tmp/karma"))

        await mgr.cleanup_project_folders(
            conn=conn,
            folder_suffix=suffix,
            member_tags=["alice.laptop", "leader1.mac"],
            team_name="team-1",
        )

        deleted_ids = [call.args[0] for call in mock_client.delete_config_folder.call_args_list]
        assert "karma-out--alice.laptop--owner-repo" not in deleted_ids
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd api && python -m pytest tests/test_cross_team_cleanup.py -v`
Expected: FAIL — `cleanup_team_folders()` doesn't accept `conn` or `team_name` parameters yet.

- [ ] **Step 3: Update FolderManager with cross-team safe cleanup**

Modify `api/services/syncthing/folder_manager.py`:

```python
# Add conn and team_name parameters to cleanup_team_folders
async def cleanup_team_folders(
    self,
    folder_suffixes: List[str],
    member_tags: List[str],
    team_name: str,
    conn: "sqlite3.Connection | None" = None,
) -> None:
    """Delete team folders, skipping outbox folders needed by other teams.

    For each candidate outbox folder (member_tag × suffix), checks if any
    other team has an active subscription for the same (member_tag, suffix).
    If so, skips deletion (another team needs the folder).

    The metadata folder (karma-meta--{team_name}) is always deleted since
    metadata folders ARE team-scoped.
    """
    target_ids = {
        build_outbox_folder_id(mt, suffix)
        for mt in member_tags
        for suffix in folder_suffixes
    }
    meta_id = build_metadata_folder_id(team_name)

    # Determine which outbox folders are safe to delete
    safe_to_delete = set()
    if conn is not None:
        for mt in member_tags:
            for suffix in folder_suffixes:
                folder_id = build_outbox_folder_id(mt, suffix)
                if folder_id not in target_ids:
                    continue
                # Check if any OTHER team has an active subscription
                # for this member_tag + folder_suffix combination
                row = conn.execute(
                    """
                    SELECT COUNT(*) FROM sync_subscriptions s
                    JOIN sync_projects p
                      ON s.team_name = p.team_name
                     AND s.project_git_identity = p.git_identity
                    WHERE p.folder_suffix = ?
                      AND s.member_tag = ?
                      AND s.status IN ('offered', 'accepted', 'paused')
                      AND s.team_name != ?
                    """,
                    (suffix, mt, team_name),
                ).fetchone()
                if row[0] == 0:
                    safe_to_delete.add(folder_id)
    else:
        # No DB connection — fall back to deleting all (legacy behavior)
        safe_to_delete = target_ids

    # Always delete the metadata folder (it IS team-scoped)
    safe_to_delete.add(meta_id)

    all_folders = await self._client.get_config_folders()
    for folder in all_folders:
        if folder["id"] in safe_to_delete:
            await self._client.delete_config_folder(folder["id"])


# Same pattern for cleanup_project_folders
async def cleanup_project_folders(
    self,
    folder_suffix: str,
    member_tags: List[str],
    conn: "sqlite3.Connection | None" = None,
    team_name: str = "",
) -> None:
    """Delete outbox/inbox folders for a project, skipping cross-team shared ones."""
    target_ids = {
        build_outbox_folder_id(mt, folder_suffix) for mt in member_tags
    }

    safe_to_delete = set()
    if conn is not None and team_name:
        for mt in member_tags:
            folder_id = build_outbox_folder_id(mt, folder_suffix)
            row = conn.execute(
                """
                SELECT COUNT(*) FROM sync_subscriptions s
                JOIN sync_projects p
                  ON s.team_name = p.team_name
                 AND s.project_git_identity = p.git_identity
                WHERE p.folder_suffix = ?
                  AND s.member_tag = ?
                  AND s.status IN ('offered', 'accepted', 'paused')
                  AND s.team_name != ?
                """,
                (folder_suffix, mt, team_name),
            ).fetchone()
            if row[0] == 0:
                safe_to_delete.add(folder_id)
    else:
        safe_to_delete = target_ids

    all_folders = await self._client.get_config_folders()
    for folder in all_folders:
        if folder["id"] in safe_to_delete:
            await self._client.delete_config_folder(folder["id"])
```

- [ ] **Step 4: Update callers to pass `conn` and `team_name`**

In `api/services/sync/team_service.py`, update `leave_team()` and `dissolve_team()`:

```python
# leave_team — line ~234
await self.folders.cleanup_team_folders(suffixes, tags, team_name, conn=conn)

# dissolve_team — line ~274
await self.folders.cleanup_team_folders(suffixes, tags, team_name, conn=conn)
```

In `api/services/sync/reconciliation_service.py`, update `_auto_leave()`:

```python
# _auto_leave — line ~344
await self.folders.cleanup_team_folders(suffixes, tags, team.name, conn=conn)
```

In `api/services/sync/project_service.py`, update `remove_project()`:

```python
# remove_project — line ~141
await self.folders.cleanup_project_folders(
    removed.folder_suffix, tags, conn=conn, team_name=name,
)
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd api && python -m pytest tests/test_cross_team_cleanup.py -v`
Expected: PASS — all 3 tests green.

- [ ] **Step 6: Run existing tests to verify no regressions**

Run: `cd api && python -m pytest tests/test_folder_manager.py tests/test_team_service.py tests/test_reconciliation_service.py tests/test_project_service.py tests/test_sync_v4_e2e.py -v`
Expected: Existing tests may need minor updates for the new `conn` parameter (use `conn=None` for backward compat).

- [ ] **Step 7: Commit**

```bash
git add api/services/syncthing/folder_manager.py api/services/sync/team_service.py \
  api/services/sync/reconciliation_service.py api/services/sync/project_service.py \
  api/tests/test_cross_team_cleanup.py
git commit -m "fix(sync-v4): add cross-team safety to folder cleanup — skip folders needed by other teams"
```

---

## Task 2: Add Folder Existence Recovery to Phase 3

Phase 3 (`phase_device_lists`) calls `set_folder_devices()` which is a no-op if the folder doesn't exist. If a folder was accidentally deleted, Phase 3 can never recover it. Fix: ensure outbox folders exist before setting device lists.

**Files:**
- Modify: `api/services/sync/reconciliation_service.py`
- Test: `api/tests/test_phase3_folder_recovery.py`

- [ ] **Step 1: Write failing test — Phase 3 creates missing outbox folder**

Create `api/tests/test_phase3_folder_recovery.py`:

```python
"""Tests for Phase 3 folder existence recovery."""
import sqlite3
import pytest
from unittest.mock import AsyncMock

from db.schema import ensure_schema
from domain.team import Team
from domain.member import Member, MemberStatus
from domain.project import SharedProject, derive_folder_suffix
from domain.subscription import Subscription, SubscriptionStatus, SyncDirection
from repositories.team_repo import TeamRepository
from repositories.member_repo import MemberRepository
from repositories.project_repo import ProjectRepository
from repositories.subscription_repo import SubscriptionRepository
from repositories.event_repo import EventRepository
from services.sync.reconciliation_service import ReconciliationService


@pytest.fixture
def conn():
    db = sqlite3.connect(":memory:")
    db.execute("PRAGMA foreign_keys = ON")
    ensure_schema(db)
    return db


@pytest.fixture
def mock_folders():
    m = AsyncMock()
    m.get_configured_folders = AsyncMock(return_value=[])  # No folders exist!
    m.set_folder_devices = AsyncMock()
    m.ensure_outbox_folder = AsyncMock()
    return m


class TestPhase3FolderRecovery:

    @pytest.mark.asyncio
    async def test_phase3_ensures_outbox_exists_for_accepted_send_sub(self, conn, mock_folders):
        """Phase 3 should create missing outbox folders for members with send|both subs."""
        repos = {
            "teams": TeamRepository(),
            "members": MemberRepository(),
            "projects": ProjectRepository(),
            "subs": SubscriptionRepository(),
            "events": EventRepository(),
        }

        git_id = "owner/repo"
        suffix = derive_folder_suffix(git_id)

        team = Team(name="team-1", leader_device_id="DEV-L", leader_member_tag="leader.mac")
        repos["teams"].save(conn, team)

        m1 = Member.from_member_tag(
            member_tag="alice.laptop", team_name="team-1",
            device_id="DEV-ALICE", status=MemberStatus.ACTIVE,
        )
        repos["members"].save(conn, m1)

        p1 = SharedProject(team_name="team-1", git_identity=git_id, folder_suffix=suffix)
        repos["projects"].save(conn, p1)

        sub = Subscription(
            member_tag="alice.laptop", team_name="team-1",
            project_git_identity=git_id, status=SubscriptionStatus.ACCEPTED,
            direction=SyncDirection.BOTH,
        )
        repos["subs"].save(conn, sub)

        svc = ReconciliationService(
            **repos,
            devices=AsyncMock(),
            folders=mock_folders,
            metadata=AsyncMock(),
            my_member_tag="alice.laptop",
            my_device_id="DEV-ALICE",
        )

        await svc.phase_device_lists(conn, team)

        # Should have called ensure_outbox_folder for alice
        mock_folders.ensure_outbox_folder.assert_called_once_with(
            "alice.laptop", suffix,
        )
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd api && python -m pytest tests/test_phase3_folder_recovery.py -v`
Expected: FAIL — `ensure_outbox_folder` never called.

- [ ] **Step 3: Add folder existence check to phase_device_lists**

In `api/services/sync/reconciliation_service.py`, update `phase_device_lists()`:

```python
async def phase_device_lists(self, conn: sqlite3.Connection, team) -> None:
    """Phase 3: Declarative device list sync + folder existence recovery."""
    from services.syncthing.folder_manager import build_outbox_folder_id

    projects = self.projects.list_for_team(conn, team.name)
    team_members = self.members.list_for_team(conn, team.name)

    for project in projects:
        if project.status.value != "shared":
            continue

        accepted = self.subs.list_accepted_for_suffix(conn, project.folder_suffix)

        # Compute desired device set: members with send|both direction
        desired: set[str] = set()
        for sub in accepted:
            if sub.direction in (SyncDirection.SEND, SyncDirection.BOTH):
                member = self.members.get(conn, sub.team_name, sub.member_tag)
                if member and member.is_active:
                    desired.add(member.device_id)

        # Ensure outbox folders exist for members with send|both subs
        # in THIS team (recovery from accidental deletion)
        for sub in accepted:
            if sub.team_name != team.name:
                continue
            if sub.direction in (SyncDirection.SEND, SyncDirection.BOTH):
                member = self.members.get(conn, sub.team_name, sub.member_tag)
                if member and member.is_active:
                    await self.folders.ensure_outbox_folder(
                        sub.member_tag, project.folder_suffix,
                    )

        # Apply declaratively to all outbox folders with this suffix
        for m in team_members:
            folder_id = build_outbox_folder_id(m.member_tag, project.folder_suffix)
            await self.folders.set_folder_devices(folder_id, desired)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd api && python -m pytest tests/test_phase3_folder_recovery.py tests/test_reconciliation_service.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add api/services/sync/reconciliation_service.py api/tests/test_phase3_folder_recovery.py
git commit -m "fix(sync-v4): Phase 3 ensures outbox folders exist before setting device lists"
```

---

## Task 3: Delete Dead CLI Sync Code

The CLI sync commands all import from `db.sync_queries` which doesn't exist in v4. Since the user is fully on API endpoints, delete all dead sync code from the CLI.

**Files:**
- Delete: `cli/karma/pending.py` (entire file — all imports from deleted module)
- Modify: `cli/karma/watcher.py` (remove `_maybe_check_peers` and its imports)
- Modify: `cli/karma/main.py` (remove sync CLI commands, keep non-sync commands)
- Modify: `cli/karma/project_resolution.py` (remove sync_queries imports, keep non-sync functions)

- [ ] **Step 1: Identify which CLI commands are sync-specific**

Run: `cd cli && grep -n "def.*cmd\|@click.command\|@click.group" karma/main.py`
Identify sync commands: `team`, `share`, `unshare`, `watch`, `status`, `nuke`, `join`, `leave`, `pair`, `pending`, `overview`

- [ ] **Step 2: Delete `cli/karma/pending.py`**

This entire file imports from `db.sync_queries`. All its functionality is now in `api/routers/sync_pending.py`.

```bash
git rm cli/karma/pending.py
```

- [ ] **Step 3: Clean `cli/karma/watcher.py`**

Remove `_maybe_check_peers()` method and its peer check timer. Keep the basic `SessionWatcher` class (filesystem watching) since it's used by the API's `WatcherManager`.

Remove lines 66-104 (`_maybe_check_peers`, `_schedule_peer_check`, `_run_peer_check`) and the peer timer from `start()` and `stop()`.

- [ ] **Step 4: Clean `cli/karma/main.py`**

Remove all sync CLI commands that import from `db.sync_queries`. Keep non-sync utilities (e.g., `init`, basic config commands if any exist without sync_queries deps).

For each function that has `from db.sync_queries import ...`, either:
- Delete the entire command if it's sync-only
- Or rewrite to use API endpoints if still needed (unlikely per user's answer)

- [ ] **Step 5: Clean `cli/karma/project_resolution.py`**

Remove functions that import from `db.sync_queries`. Keep `resolve_local_project()` if it's used by non-CLI code (check imports first).

- [ ] **Step 6: Verify no remaining imports from deleted module**

Run: `grep -r "from db.sync_queries" cli/ --include="*.py"`
Expected: No matches.

- [ ] **Step 7: Run API tests to verify no regressions**

Run: `cd api && python -m pytest -x -q`
Expected: All tests pass (CLI code is not imported by API).

- [ ] **Step 8: Commit**

```bash
git add -A cli/
git commit -m "refactor(sync-v4): remove dead CLI sync code — all sync operations via API now"
```

---

## Task 4: Multi-Team E2E Integration Test

Add a comprehensive test that exercises the exact scenario from the v3 audit: M1 in T1 and T2, both sharing project P1, verify leaving T1 doesn't break T2's sync.

**Files:**
- Create: `api/tests/test_sync_v4_multi_team_e2e.py`

- [ ] **Step 1: Write the multi-team E2E test**

```python
"""Multi-team overlap E2E test.

Scenario from v3 audit (docs/design/sync-v3-audit-findings.md):
- T1: Leader L1, Member Alice — shares P1
- T2: Leader L2, Member Alice — shares P1
- Alice accepts P1 in both teams
- Alice leaves T1
- Verify: Alice's P1 outbox still works for T2
- Verify: T2's reconciliation Phase 3 still manages device lists correctly
"""
import sqlite3
import pytest
from unittest.mock import AsyncMock, patch
from pathlib import Path

from db.schema import ensure_schema
from repositories.team_repo import TeamRepository
from repositories.member_repo import MemberRepository
from repositories.project_repo import ProjectRepository
from repositories.subscription_repo import SubscriptionRepository
from repositories.event_repo import EventRepository
from services.sync.team_service import TeamService
from services.sync.project_service import ProjectService
from services.sync.reconciliation_service import ReconciliationService
from services.syncthing.folder_manager import build_outbox_folder_id


@pytest.fixture
def conn():
    db = sqlite3.connect(":memory:")
    db.execute("PRAGMA foreign_keys = ON")
    ensure_schema(db)
    return db


@pytest.fixture
def mock_infra():
    """Mock Syncthing infrastructure."""
    devices = AsyncMock()
    folders = AsyncMock()
    folders.ensure_metadata_folder = AsyncMock()
    folders.ensure_outbox_folder = AsyncMock()
    folders.ensure_inbox_folder = AsyncMock()
    folders.set_folder_devices = AsyncMock()
    folders.cleanup_team_folders = AsyncMock()
    folders.cleanup_project_folders = AsyncMock()
    folders.remove_device_from_team_folders = AsyncMock()
    folders.remove_outbox_folder = AsyncMock()
    folders.get_configured_folders = AsyncMock(return_value=[])
    metadata = AsyncMock()
    metadata.write_team_state = AsyncMock()
    metadata.write_member_state = AsyncMock()
    metadata.write_removal_signal = AsyncMock()
    return devices, folders, metadata


class TestMultiTeamOverlapE2E:

    @pytest.mark.asyncio
    async def test_leave_team1_preserves_team2_subscriptions(self, conn, mock_infra):
        """Full lifecycle: create 2 teams, share same project, leave one, verify other intact."""
        devices, folders, metadata = mock_infra
        repos = dict(
            teams=TeamRepository(), members=MemberRepository(),
            projects=ProjectRepository(), subs=SubscriptionRepository(),
            events=EventRepository(),
        )

        team_svc = TeamService(**repos, devices=devices, metadata=metadata, folders=folders)
        proj_svc = ProjectService(**repos, folders=folders, metadata=metadata)

        # 1. Create Team 1 (leader: L1)
        t1 = await team_svc.create_team(
            conn, name="team-1",
            leader_member_tag="leader1.mac", leader_device_id="DEV-L1",
        )

        # 2. Create Team 2 (leader: L2)
        t2 = await team_svc.create_team(
            conn, name="team-2",
            leader_member_tag="leader2.mac", leader_device_id="DEV-L2",
        )

        # 3. Both leaders share the same project
        p1_t1 = await proj_svc.share_project(
            conn, team_name="team-1", by_device="DEV-L1",
            git_identity="owner/repo", encoded_name="-Users-me-repo",
        )
        p1_t2 = await proj_svc.share_project(
            conn, team_name="team-2", by_device="DEV-L2",
            git_identity="owner/repo", encoded_name="-Users-me-repo",
        )

        # 4. Add Alice to both teams
        m1_t1 = await team_svc.add_member(
            conn, team_name="team-1", by_device="DEV-L1",
            new_member_tag="alice.laptop", new_device_id="DEV-ALICE",
        )
        m1_t2 = await team_svc.add_member(
            conn, team_name="team-2", by_device="DEV-L2",
            new_member_tag="alice.laptop", new_device_id="DEV-ALICE",
        )

        # 5. Alice accepts P1 in both teams
        from domain.subscription import SyncDirection
        sub_t1 = await proj_svc.accept_subscription(
            conn, member_tag="alice.laptop", team_name="team-1",
            git_identity="owner/repo", direction=SyncDirection.BOTH,
        )
        sub_t2 = await proj_svc.accept_subscription(
            conn, member_tag="alice.laptop", team_name="team-2",
            git_identity="owner/repo", direction=SyncDirection.BOTH,
        )

        # Verify: Alice has ACCEPTED subs in both teams
        all_subs = repos["subs"].list_for_member(conn, "alice.laptop")
        accepted = [s for s in all_subs if s.status.value == "accepted"]
        assert len(accepted) == 2

        # 6. Alice leaves Team 1
        await team_svc.leave_team(
            conn, team_name="team-1", member_tag="alice.laptop",
        )

        # 7. Verify: Alice's T2 subscription is still ACCEPTED
        t2_subs = repos["subs"].list_for_member(conn, "alice.laptop")
        t2_accepted = [s for s in t2_subs if s.team_name == "team-2" and s.status.value == "accepted"]
        assert len(t2_accepted) == 1
        assert t2_accepted[0].direction.value == "both"

        # 8. Verify: T1 data is cleaned up
        t1_check = repos["teams"].get(conn, "team-1")
        assert t1_check is None  # Deleted by leave_team

        # 9. Run Phase 3 for T2 — should still work
        recon = ReconciliationService(
            **repos, devices=devices, folders=folders,
            metadata=metadata, my_member_tag="alice.laptop",
            my_device_id="DEV-ALICE",
        )
        t2_reloaded = repos["teams"].get(conn, "team-2")
        await recon.phase_device_lists(conn, t2_reloaded)

        # Phase 3 should have called set_folder_devices for alice's outbox
        assert folders.set_folder_devices.called
```

- [ ] **Step 2: Run the test**

Run: `cd api && python -m pytest tests/test_sync_v4_multi_team_e2e.py -v`
Expected: PASS (after Tasks 1-2 are implemented).

- [ ] **Step 3: Commit**

```bash
git add api/tests/test_sync_v4_multi_team_e2e.py
git commit -m "test(sync-v4): add multi-team overlap E2E test — verifies cross-team safety"
```

---

## Task 5: Run Full Test Suite & Final Cleanup

- [ ] **Step 1: Run all sync v4 tests**

Run: `cd api && python -m pytest tests/test_sync_v4*.py tests/test_cross_team*.py tests/test_phase3*.py tests/test_team_service.py tests/test_folder_manager.py tests/test_reconciliation_service.py tests/test_project_service.py -v`
Expected: All green.

- [ ] **Step 2: Run full API test suite**

Run: `cd api && python -m pytest -x -q`
Expected: All green.

- [ ] **Step 3: Verify no remaining dead imports**

Run: `grep -r "sync_queries\|sync_rejected_folders\|sync_settings\|sync_team_projects" api/ cli/ --include="*.py" -l`
Expected: Only docs/plans files, no source code.

- [ ] **Step 4: Final commit**

```bash
git commit -m "chore(sync-v4): verify all tests pass after cross-team safety + dead code cleanup"
```

---

## Execution Order

| Task | Depends On | Description |
|------|-----------|-------------|
| 1 | — | Cross-team safe cleanup in FolderManager |
| 2 | — | Phase 3 folder existence recovery |
| 3 | — | Delete dead CLI sync code |
| 4 | 1, 2 | Multi-team E2E integration test |
| 5 | 1, 2, 3, 4 | Full test suite verification |

Tasks 1, 2, and 3 are independent and can be done in parallel.
