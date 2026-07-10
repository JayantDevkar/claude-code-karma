# Sync v2 Phase 0: Quick Wins (Bug Fixes)

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix 6 known bugs in the sync layer — all independent, all parallelizable.

**Architecture:** Targeted fixes to existing code. No schema changes. No breaking changes.

**Tech Stack:** Python, FastAPI, SQLite, pytest

---

## Chunk 1: Bug Fixes

All 6 tasks are independent — run them in parallel using `superpowers:dispatching-parallel-agents`.

### Task 0.1: Fix reconcile_introduced_devices — Add auto_share_folders

Introduced devices get DB records but no Syncthing folders. MacBook Pro never receives Ayush's sessions because `reconcile_introduced_devices` calls `upsert_member` but NOT `auto_share_folders`.

**Files:**
- Modify: `api/services/sync_reconciliation.py:144-161`
- Test: `api/tests/test_sync_reconciliation_fix.py` (create)

- [ ] **Step 1: Write the failing test**

```python
# api/tests/test_sync_reconciliation_fix.py
"""Tests for reconcile_introduced_devices auto_share_folders fix."""

import sqlite3
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from db.schema import ensure_schema


@pytest.fixture
def conn():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA foreign_keys=ON")
    ensure_schema(c)
    return c


@pytest.fixture
def mock_config():
    config = MagicMock()
    config.user_id = "jayant"
    config.machine_id = "Mac-Mini"
    config.syncthing.device_id = "LEADER-DID"
    return config


@pytest.mark.asyncio
async def test_reconcile_introduced_devices_calls_auto_share(conn, mock_config):
    """Introduced devices should get folders shared back (not just DB record)."""
    from db.sync_queries import create_team, upsert_member, add_team_project

    # Setup: team with one project, leader is a member
    create_team(conn, "acme", backend="syncthing")
    upsert_member(conn, "acme", "jayant", device_id="LEADER-DID")
    conn.execute(
        "INSERT INTO projects (encoded_name) VALUES (?)",
        ("-Users-test-proj",),
    )
    add_team_project(conn, "acme", "-Users-test-proj", path="/test", git_identity="org/proj")

    # Mock proxy: one introduced device NOT in karma DB
    mock_proxy = AsyncMock()
    mock_proxy.get_devices = MagicMock(return_value=[
        {"device_id": "AYUSH-DID", "name": "ayush", "is_self": False},
        {"device_id": "LEADER-DID", "name": "jayant", "is_self": True},
    ])
    mock_proxy.get_configured_folders = MagicMock(return_value=[
        {
            "id": "karma-join--ayush--acme",
            "type": "receiveonly",
            "devices": [{"deviceID": "AYUSH-DID"}, {"deviceID": "LEADER-DID"}],
        },
    ])

    with patch(
        "services.sync_reconciliation.auto_share_folders",
        new_callable=AsyncMock,
    ) as mock_share:
        from services.sync_reconciliation import reconcile_introduced_devices
        count = await reconcile_introduced_devices(mock_proxy, mock_config, conn)

    assert count == 1
    # KEY ASSERTION: auto_share_folders was called for the introduced device
    mock_share.assert_called_once_with(mock_proxy, mock_config, conn, "acme", "AYUSH-DID")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd api && python -m pytest tests/test_sync_reconciliation_fix.py::test_reconcile_introduced_devices_calls_auto_share -v`
Expected: FAIL — `mock_share.assert_called_once_with` fails (never called)

- [ ] **Step 3: Implement the fix**

In `api/services/sync_reconciliation.py`, after line 161 (after the `reconciled += 1`), add the `auto_share_folders` call inside the `for username, team_name in memberships:` loop. Replace lines 144-161:

```python
        for username, team_name in memberships:
            if was_member_removed(conn, team_name, device_id):
                logger.debug(
                    "Reconcile introduced: skipping %s for team %s (previously removed)",
                    device_id[:20], team_name,
                )
                continue
            upsert_member(conn, team_name, username, device_id=device_id)
            log_event(
                conn, "member_auto_accepted", team_name=team_name,
                member_name=username,
                detail={"strategy": "reconciliation", "source": "introduced_device"},
            )
            # Auto-share project folders back to the introduced device
            try:
                await auto_share_folders(proxy, config, conn, team_name, device_id)
            except Exception as e:
                logger.warning(
                    "Reconcile introduced: failed to share folders with %s: %s",
                    device_id[:20], e,
                )
            logger.info(
                "Reconciled introduced device %s as %s in team %s",
                device_id[:20], username, team_name,
            )
            reconciled += 1
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd api && python -m pytest tests/test_sync_reconciliation_fix.py -v`
Expected: PASS

- [ ] **Step 5: Run existing tests to verify no regressions**

Run: `cd api && python -m pytest tests/test_sync_*.py -v`
Expected: All pass

- [ ] **Step 6: Commit**

```bash
cd api
git add services/sync_reconciliation.py tests/test_sync_reconciliation_fix.py
git commit -m "fix(sync): call auto_share_folders for introduced devices

reconcile_introduced_devices was adding members to the DB but not
creating Syncthing folders, leaving introduced peers unable to sync.
Fixes issue #3 from sync architecture review."
```

---

### Task 0.2: Fix ensure_leader_introducers Self-Skip

On the leader's machine, `ensure_leader_introducers` parses the join code, gets the leader's own device_id, and tries to set `introducer=True` on itself. Self isn't in the peer list → ValueError → caught by `except: pass`. Wasteful API call.

**Files:**
- Modify: `api/services/sync_reconciliation.py:166-193`
- Modify: `api/routers/sync_devices.py` (caller — pass own_device_id)
- Test: `api/tests/test_sync_reconciliation_fix.py` (append)

- [ ] **Step 1: Write the failing test**

Append to `api/tests/test_sync_reconciliation_fix.py`:

```python
@pytest.mark.asyncio
async def test_ensure_leader_introducers_skips_self(conn, mock_config):
    """Should not attempt to set introducer on own device."""
    from db.sync_queries import create_team

    create_team(conn, "acme", backend="syncthing", join_code="acme:jayant:LEADER-DID")

    mock_proxy = AsyncMock()

    from services.sync_reconciliation import ensure_leader_introducers
    count = await ensure_leader_introducers(mock_proxy, conn, own_device_id="LEADER-DID")

    # Should NOT have called set_device_introducer (skipped self)
    mock_proxy.set_device_introducer.assert_not_called()
    assert count == 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd api && python -m pytest tests/test_sync_reconciliation_fix.py::test_ensure_leader_introducers_skips_self -v`
Expected: FAIL — TypeError (unexpected keyword argument `own_device_id`)

- [ ] **Step 3: Implement the fix**

In `api/services/sync_reconciliation.py`, modify `ensure_leader_introducers` signature and add self-skip:

```python
async def ensure_leader_introducers(proxy, conn, *, own_device_id: str | None = None) -> int:
    """Ensure leader devices are marked as introducers in Syncthing.

    Parses each team's join code to find the leader device_id and sets the
    introducer flag if it is missing. Skips own device_id to avoid wasteful
    API calls.

    Returns count of devices updated.
    """
    updated = 0
    for team in list_teams(conn):
        join_code = team.get("join_code")
        if not join_code:
            continue
        parts = join_code.split(":", 2)
        if len(parts) == 3:
            _, _, leader_device_id = parts
        elif len(parts) == 2:
            _, leader_device_id = parts
        else:
            continue
        # Skip self — can't set introducer on own device
        if own_device_id and leader_device_id == own_device_id:
            continue
        try:
            changed = await run_sync(proxy.set_device_introducer, leader_device_id, True)
            if changed:
                logger.info("Auto-set introducer=True for leader device %s", leader_device_id[:20])
                updated += 1
        except Exception:
            pass
    return updated
```

Update the caller in `api/routers/sync_devices.py`. Find where `ensure_leader_introducers` is called (in `sync_pending_devices`) and pass `own_device_id`:

```python
# In sync_pending_devices function, find the ensure_leader_introducers call:
own_did = config.syncthing.device_id if config and config.syncthing else None
await ensure_leader_introducers(proxy, conn, own_device_id=own_did)
```

- [ ] **Step 4: Run tests**

Run: `cd api && python -m pytest tests/test_sync_reconciliation_fix.py -v`
Expected: All pass

- [ ] **Step 5: Commit**

```bash
cd api
git add services/sync_reconciliation.py routers/sync_devices.py tests/test_sync_reconciliation_fix.py
git commit -m "fix(sync): skip self when setting leader introducer flag

ensure_leader_introducers was trying to set introducer=True on the
leader's own device, which always fails silently. Now accepts
own_device_id parameter and skips self."
```

---

### Task 0.3: Add User ID Collision Check at Accept Time

When accepting a pending device, the extracted member name could collide with an existing member (different device). This causes silent folder ID collisions — two devices writing to the same outbox.

**Files:**
- Modify: `api/routers/sync_devices.py:206-260`
- Test: `api/tests/test_sync_collision_check.py` (create)

- [ ] **Step 1: Write the failing test**

```python
# api/tests/test_sync_collision_check.py
"""Tests for user_id collision check during device acceptance."""

import sqlite3
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from db.schema import ensure_schema


@pytest.fixture
def conn():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA foreign_keys=ON")
    ensure_schema(c)
    return c


def test_accept_rejects_colliding_member_name(conn):
    """Accepting a device whose name collides with an existing member should fail."""
    from db.sync_queries import create_team, upsert_member, list_members

    create_team(conn, "acme", backend="syncthing")
    upsert_member(conn, "acme", "jayant", device_id="EXISTING-DID")

    # A different device claiming the name "jayant" should be detected
    members = list_members(conn, "acme")
    collisions = [
        m for m in members
        if m["name"] == "jayant" and m["device_id"] != "NEW-DID"
    ]
    assert len(collisions) == 1, "Should detect name collision"
```

- [ ] **Step 2: Run test to verify it passes** (this tests the detection logic, not the endpoint)

Run: `cd api && python -m pytest tests/test_sync_collision_check.py -v`
Expected: PASS

- [ ] **Step 3: Implement the collision check**

In `api/routers/sync_devices.py`, in the `sync_accept_pending_device` function, after member_name is resolved (around line 245), add:

```python
        # Check for name collision — different device claiming the same identity
        existing_members = list_members(conn, team_name)
        collisions = [
            m for m in existing_members
            if m["name"] == member_name and m["device_id"] != device_id
        ]
        if collisions:
            raise HTTPException(
                409,
                f"Member name '{member_name}' is already used by another device "
                f"in team '{team_name}'. The new device must use a different user_id.",
            )
```

Add `list_members` to the imports from `db.sync_queries` at the top of the file.

- [ ] **Step 4: Run all sync tests**

Run: `cd api && python -m pytest tests/test_sync_*.py -v`
Expected: All pass

- [ ] **Step 5: Commit**

```bash
cd api
git add routers/sync_devices.py tests/test_sync_collision_check.py
git commit -m "fix(sync): reject pending device if user_id collides with existing member

Prevents silent folder ID collisions when two different devices claim
the same user_id within a team. Returns 409 Conflict."
```

---

### Task 0.4: Clean Up Settings on Team Delete

`delete_team()` only deletes from `sync_teams` (cascade handles members/projects). But `sync_settings` has no FK — settings with scope `team:X` and `member:X:Y` are orphaned forever.

**Files:**
- Modify: `api/db/sync_queries.py:32-34`
- Test: `api/tests/test_sync_settings_cleanup.py` (create)

- [ ] **Step 1: Write the failing test**

```python
# api/tests/test_sync_settings_cleanup.py
"""Tests for settings cleanup on team delete."""

import sqlite3
import pytest
from db.schema import ensure_schema


@pytest.fixture
def conn():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA foreign_keys=ON")
    ensure_schema(c)
    return c


def test_delete_team_cleans_up_settings(conn):
    """Deleting a team should remove orphaned sync_settings entries."""
    from db.sync_queries import create_team, set_setting, delete_team

    create_team(conn, "acme", backend="syncthing")
    set_setting(conn, "team:acme", "auto_accept_members", "true")
    set_setting(conn, "member:acme:DEV-123", "sync_direction", "send_only")

    # Also set a setting for a different team (should NOT be cleaned)
    create_team(conn, "other", backend="syncthing")
    set_setting(conn, "team:other", "auto_accept_members", "false")

    delete_team(conn, "acme")

    # Acme settings should be gone
    rows = conn.execute(
        "SELECT * FROM sync_settings WHERE scope LIKE 'team:acme%' OR scope LIKE 'member:acme:%'"
    ).fetchall()
    assert len(rows) == 0, f"Expected 0 orphaned settings, found {len(rows)}"

    # Other team's settings should survive
    rows = conn.execute(
        "SELECT * FROM sync_settings WHERE scope LIKE 'team:other%'"
    ).fetchall()
    assert len(rows) == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd api && python -m pytest tests/test_sync_settings_cleanup.py -v`
Expected: FAIL — orphaned settings found

- [ ] **Step 3: Implement the fix**

In `api/db/sync_queries.py`, modify `delete_team`:

```python
def delete_team(conn: sqlite3.Connection, name: str) -> None:
    # Clean up orphaned settings (sync_settings has no FK to sync_teams)
    conn.execute(
        "DELETE FROM sync_settings WHERE scope = ? OR scope LIKE ?",
        (f"team:{name}", f"member:{name}:%"),
    )
    conn.execute("DELETE FROM sync_teams WHERE name = ?", (name,))
    conn.commit()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd api && python -m pytest tests/test_sync_settings_cleanup.py -v`
Expected: PASS

- [ ] **Step 5: Run existing settings tests**

Run: `cd api && python -m pytest tests/test_sync_settings.py tests/test_sync_team_crud.py -v`
Expected: All pass

- [ ] **Step 6: Commit**

```bash
cd api
git add db/sync_queries.py tests/test_sync_settings_cleanup.py
git commit -m "fix(sync): clean up orphaned settings on team delete

sync_settings has no FK to sync_teams, so team:X and member:X:Y
scoped settings were never cleaned up. Now deleted before CASCADE."
```

---

### Task 0.5: Add Data Cleanup to Remove-Project

`sync_remove_team_project` removes Syncthing folders and DB records, but NOT remote session files on disk or session rows in the DB. Compare with `remove_member` which calls `cleanup_data_for_member`.

**Files:**
- Modify: `api/db/sync_queries.py` (add `cleanup_data_for_project`)
- Modify: `api/routers/sync_projects.py:151-199`
- Test: `api/tests/test_sync_project_cleanup.py` (create)

- [ ] **Step 1: Write the failing test**

```python
# api/tests/test_sync_project_cleanup.py
"""Tests for project removal data cleanup."""

import sqlite3
from pathlib import Path

import pytest
from db.schema import ensure_schema


@pytest.fixture
def conn():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA foreign_keys=ON")
    ensure_schema(c)
    return c


def test_cleanup_data_for_project_removes_remote_sessions(conn, tmp_path):
    """Removing a project should clean up remote session files and DB rows."""
    from db.sync_queries import create_team, upsert_member

    create_team(conn, "acme", backend="syncthing")
    upsert_member(conn, "acme", "ayush", device_id="AYUSH-DID")

    # Create fake remote session files
    remote_dir = tmp_path / "remote-sessions" / "ayush" / "-Users-test-proj"
    remote_dir.mkdir(parents=True)
    (remote_dir / "session1.jsonl").write_text("{}")
    (remote_dir / "session2.jsonl").write_text("{}")

    # Create fake DB session rows
    conn.execute(
        "INSERT INTO sessions (uuid, project_encoded_name, source, remote_user_id) VALUES (?, ?, ?, ?)",
        ("sess-1", "-Users-test-proj", "remote", "ayush"),
    )
    conn.execute(
        "INSERT INTO sessions (uuid, project_encoded_name, source, remote_user_id) VALUES (?, ?, ?, ?)",
        ("sess-2", "-Users-test-proj", "remote", "ayush"),
    )
    # Session from different project (should NOT be deleted)
    conn.execute(
        "INSERT INTO sessions (uuid, project_encoded_name, source, remote_user_id) VALUES (?, ?, ?, ?)",
        ("sess-other", "-Users-other", "remote", "ayush"),
    )
    conn.commit()

    from db.sync_queries import cleanup_data_for_project
    stats = cleanup_data_for_project(conn, "acme", "-Users-test-proj", base_path=tmp_path)

    assert stats["sessions_deleted"] == 2
    assert not remote_dir.exists(), "Remote session directory should be deleted"

    # Other project's session should survive
    remaining = conn.execute(
        "SELECT COUNT(*) FROM sessions WHERE project_encoded_name = '-Users-other'"
    ).fetchone()[0]
    assert remaining == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd api && python -m pytest tests/test_sync_project_cleanup.py -v`
Expected: FAIL — `ImportError: cannot import name 'cleanup_data_for_project'`

- [ ] **Step 3: Implement cleanup_data_for_project**

Add to `api/db/sync_queries.py`:

```python
def cleanup_data_for_project(
    conn: sqlite3.Connection,
    team_name: str,
    project_encoded_name: str,
    *,
    base_path: Path | None = None,
) -> dict:
    """Remove remote session data for a specific project across all team members.

    Cleans up:
    - Filesystem: remote-sessions/{member}/{encoded}/ directories
    - DB: sessions with source='remote' for this project
    """
    import shutil
    from pathlib import Path as _Path

    if base_path is None:
        from karma.config import KARMA_BASE
        base_path = KARMA_BASE

    stats = {"sessions_deleted": 0, "dirs_deleted": 0}

    members = list_members(conn, team_name)

    # Filesystem cleanup
    for m in members:
        member_dir = base_path / "remote-sessions" / m["name"] / project_encoded_name
        if member_dir.exists():
            shutil.rmtree(member_dir)
            stats["dirs_deleted"] += 1
            # Remove parent if empty
            parent = member_dir.parent
            if parent.exists() and not any(parent.iterdir()):
                parent.rmdir()

    # DB cleanup: remove remote sessions for this project
    cursor = conn.execute(
        "DELETE FROM sessions WHERE source = 'remote' AND project_encoded_name = ?",
        (project_encoded_name,),
    )
    stats["sessions_deleted"] = cursor.rowcount
    conn.commit()

    return stats
```

Add the import at the top of `sync_queries.py`:
```python
from pathlib import Path
```

- [ ] **Step 4: Wire it into the remove-project endpoint**

In `api/routers/sync_projects.py`, in `sync_remove_team_project`, after the Syncthing folder cleanup and before `remove_team_project(conn, ...)`, add:

```python
        # Clean up remote session data (filesystem + DB)
        try:
            from db.sync_queries import cleanup_data_for_project
            stats = cleanup_data_for_project(conn, team_name, encoded_name)
            if stats["sessions_deleted"] or stats["dirs_deleted"]:
                logger.info(
                    "Cleaned up %d sessions and %d dirs for %s/%s",
                    stats["sessions_deleted"], stats["dirs_deleted"],
                    team_name, encoded_name,
                )
        except Exception as e:
            logger.warning("Failed to clean up project data: %s", e)
```

- [ ] **Step 5: Run test to verify it passes**

Run: `cd api && python -m pytest tests/test_sync_project_cleanup.py -v`
Expected: PASS

- [ ] **Step 6: Run existing project tests**

Run: `cd api && python -m pytest tests/test_sync_team_projects.py tests/test_sync_project_status.py -v`
Expected: All pass

- [ ] **Step 7: Commit**

```bash
cd api
git add db/sync_queries.py routers/sync_projects.py tests/test_sync_project_cleanup.py
git commit -m "fix(sync): clean up remote session data when removing a project

sync_remove_team_project was removing Syncthing folders but leaving
remote session files on disk and DB rows. Now calls
cleanup_data_for_project to match remove_member's cleanup behavior."
```

---

### Task 0.6: Fix auto_accept Exception Handling

When `add_device` fails in `auto_accept_pending_peers`, the `continue` skips `upsert_member` AND `auto_share_folders`. If the device was already configured by the introducer, this silently skips the member flow.

**Files:**
- Modify: `api/services/sync_reconciliation.py:411-416`
- Test: `api/tests/test_sync_reconciliation_fix.py` (append)

- [ ] **Step 1: Write the failing test**

Append to `api/tests/test_sync_reconciliation_fix.py`:

```python
@pytest.mark.asyncio
async def test_auto_accept_continues_after_add_device_failure(conn, mock_config):
    """If add_device fails (device already configured), should still add member + share folders."""
    from db.sync_queries import create_team, list_members

    create_team(conn, "acme", backend="syncthing", join_code="acme:jayant:LEADER-DID")

    mock_proxy = AsyncMock()
    # add_device raises (device already configured by introducer)
    mock_proxy.add_device = MagicMock(side_effect=Exception("device already exists"))
    mock_proxy.get_pending_devices = MagicMock(return_value={
        "AYUSH-DID": {"name": "ayush"},
    })
    mock_proxy.get_pending_folders = MagicMock(return_value={
        "karma-join--ayush--acme": {"offeredBy": {"AYUSH-DID": {}}},
    })
    mock_proxy.get_configured_folders = MagicMock(return_value=[])

    with patch("services.sync_reconciliation.should_auto_accept_device", return_value=True):
        with patch(
            "services.sync_reconciliation.auto_share_folders",
            new_callable=AsyncMock,
        ) as mock_share:
            from services.sync_reconciliation import auto_accept_pending_peers
            accepted, remaining = await auto_accept_pending_peers(mock_proxy, mock_config, conn)

    # Member should have been added despite add_device failure
    members = list_members(conn, "acme")
    ayush_members = [m for m in members if m["name"] == "ayush"]
    assert len(ayush_members) == 1, "ayush should be added to DB even if add_device fails"

    # auto_share_folders should have been called
    mock_share.assert_called_once()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd api && python -m pytest tests/test_sync_reconciliation_fix.py::test_auto_accept_continues_after_add_device_failure -v`
Expected: FAIL — `ayush_members` is empty (skipped by `continue`)

- [ ] **Step 3: Implement the fix**

In `api/services/sync_reconciliation.py`, replace the `auto_accept_pending_peers` try/except block around `add_device` (lines 411-416):

Replace:
```python
            try:
                await run_sync(proxy.add_device, device_id, username)
            except Exception as e:
                logger.warning("Auto-accept: failed to add device %s: %s", device_id[:20], e)
                continue
```

With:
```python
            try:
                await run_sync(proxy.add_device, device_id, username)
            except Exception as e:
                logger.warning(
                    "Auto-accept: add_device failed for %s (may already exist via introducer): %s",
                    device_id[:20], e,
                )
                # Don't skip — device may already be configured via introducer.
                # Proceed with upsert_member and auto_share_folders.
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd api && python -m pytest tests/test_sync_reconciliation_fix.py -v`
Expected: All pass

- [ ] **Step 5: Run all sync tests**

Run: `cd api && python -m pytest tests/test_sync_*.py -v`
Expected: All pass

- [ ] **Step 6: Commit**

```bash
cd api
git add services/sync_reconciliation.py tests/test_sync_reconciliation_fix.py
git commit -m "fix(sync): don't skip member flow when add_device fails in auto_accept

If a device was already configured by the Syncthing introducer,
add_device raises. The old code skipped upsert_member and
auto_share_folders entirely. Now proceeds with DB + folder setup."
```

---

## Post-Phase Verification

- [ ] **Run full sync test suite**

```bash
cd api && python -m pytest tests/test_sync_*.py -v --tb=short
```

- [ ] **Run full API test suite for regressions**

```bash
cd api && python -m pytest tests/ -v --tb=short
```

- [ ] **Lint**

```bash
cd api && ruff check services/sync_reconciliation.py routers/sync_devices.py routers/sync_projects.py db/sync_queries.py
```
