# Sync v2 Phase 2: Team Metadata Folder (State Convergence)

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a `karma-meta--{team}` Syncthing folder that all members share, enabling membership state convergence, removal notifications, and subscription visibility — without a central server.

**Architecture:** Each member writes their own JSON state file. Removal signals are written by the team creator. Reconciliation reads all files and updates local DB. Syncthing `sendreceive` type means any member can write (no conflicts since each writes only their own file).

**Tech Stack:** Python, FastAPI, SQLite, Syncthing REST API, pytest

**Prerequisite:** Phase 1 complete.

---

## Chunk 1: Metadata File Format & Helpers (T2.1–T2.2)

### Task 2.1: Metadata File Format and Helper Module

**Files:**
- Create: `api/services/sync_metadata.py`
- Test: `api/tests/test_sync_metadata.py` (create)

- [ ] **Step 1: Write the failing test**

```python
# api/tests/test_sync_metadata.py
"""Tests for team metadata folder helpers."""

import json
from pathlib import Path
import pytest


def test_write_member_state(tmp_path):
    """Writing member state creates the correct JSON file."""
    from services.sync_metadata import write_member_state

    meta_dir = tmp_path / "karma-meta--acme"
    meta_dir.mkdir()

    write_member_state(
        meta_dir,
        member_tag="jayant.mac-mini",
        user_id="jayant",
        machine_id="Jayants-Mac-Mini",
        device_id="LEADER-DID",
        subscriptions={"jayantdevkar-claude-karma": True},
        sync_direction="both",
        session_limit="all",
    )

    state_file = meta_dir / "members" / "jayant.mac-mini.json"
    assert state_file.exists()

    data = json.loads(state_file.read_text())
    assert data["member_tag"] == "jayant.mac-mini"
    assert data["user_id"] == "jayant"
    assert data["device_id"] == "LEADER-DID"
    assert data["subscriptions"]["jayantdevkar-claude-karma"] is True
    assert "updated_at" in data


def test_write_removal_signal(tmp_path):
    """Writing a removal signal creates the correct JSON file."""
    from services.sync_metadata import write_removal_signal

    meta_dir = tmp_path / "karma-meta--acme"
    meta_dir.mkdir()

    write_removal_signal(
        meta_dir,
        removed_member_tag="ayush.ayush-mac",
        removed_device_id="AYUSH-DID",
        removed_by="jayant.mac-mini",
    )

    removal_file = meta_dir / "removals" / "ayush.ayush-mac.json"
    assert removal_file.exists()

    data = json.loads(removal_file.read_text())
    assert data["member_tag"] == "ayush.ayush-mac"
    assert data["removed_by"] == "jayant.mac-mini"
    assert "removed_at" in data


def test_write_team_info(tmp_path):
    """Writing team info creates team.json."""
    from services.sync_metadata import write_team_info

    meta_dir = tmp_path / "karma-meta--acme"
    meta_dir.mkdir()

    write_team_info(meta_dir, team_name="acme", created_by="jayant.mac-mini")

    team_file = meta_dir / "team.json"
    assert team_file.exists()

    data = json.loads(team_file.read_text())
    assert data["name"] == "acme"
    assert data["created_by"] == "jayant.mac-mini"


def test_read_all_member_states(tmp_path):
    """Reading member states discovers all member files."""
    from services.sync_metadata import write_member_state, read_all_member_states

    meta_dir = tmp_path / "karma-meta--acme"
    meta_dir.mkdir()

    write_member_state(meta_dir, member_tag="jayant.mac-mini", user_id="jayant",
                       machine_id="Mini", device_id="DID1")
    write_member_state(meta_dir, member_tag="ayush.ayush-mac", user_id="ayush",
                       machine_id="Mac", device_id="DID2")

    states = read_all_member_states(meta_dir)
    assert len(states) == 2
    tags = {s["member_tag"] for s in states}
    assert tags == {"jayant.mac-mini", "ayush.ayush-mac"}


def test_read_removal_signals(tmp_path):
    """Reading removal signals discovers all removal files."""
    from services.sync_metadata import write_removal_signal, read_removal_signals

    meta_dir = tmp_path / "karma-meta--acme"
    meta_dir.mkdir()

    write_removal_signal(meta_dir, removed_member_tag="ayush.ayush-mac",
                         removed_device_id="DID2", removed_by="jayant.mac-mini")

    removals = read_removal_signals(meta_dir)
    assert len(removals) == 1
    assert removals[0]["member_tag"] == "ayush.ayush-mac"


def test_read_team_info(tmp_path):
    """Reading team info returns creator."""
    from services.sync_metadata import write_team_info, read_team_info

    meta_dir = tmp_path / "karma-meta--acme"
    meta_dir.mkdir()
    write_team_info(meta_dir, team_name="acme", created_by="jayant.mac-mini")

    info = read_team_info(meta_dir)
    assert info["created_by"] == "jayant.mac-mini"


def test_is_removed(tmp_path):
    """Check if a specific member_tag has a removal signal."""
    from services.sync_metadata import write_removal_signal, is_removed

    meta_dir = tmp_path / "karma-meta--acme"
    meta_dir.mkdir()

    assert is_removed(meta_dir, "ayush.ayush-mac") is False

    write_removal_signal(meta_dir, removed_member_tag="ayush.ayush-mac",
                         removed_device_id="DID", removed_by="jayant.mac-mini")

    assert is_removed(meta_dir, "ayush.ayush-mac") is True


def test_validate_removal_authority(tmp_path):
    """Only the team creator can remove members."""
    from services.sync_metadata import write_team_info, validate_removal_authority

    meta_dir = tmp_path / "karma-meta--acme"
    meta_dir.mkdir()
    write_team_info(meta_dir, team_name="acme", created_by="jayant.mac-mini")

    assert validate_removal_authority(meta_dir, "jayant.mac-mini") is True
    assert validate_removal_authority(meta_dir, "ayush.ayush-mac") is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd api && python -m pytest tests/test_sync_metadata.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'services.sync_metadata'`

- [ ] **Step 3: Implement sync_metadata.py**

```python
# api/services/sync_metadata.py
"""Team metadata folder helpers.

Each team has a `karma-meta--{team}` Syncthing folder (sendreceive) containing:
  members/{member_tag}.json  — each device writes its own state
  removals/{member_tag}.json — removal signals (creator-only authority)
  team.json                  — team-level info (name, creator)
"""

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

METADATA_PREFIX = "karma-meta--"


def build_metadata_folder_id(team_name: str) -> str:
    """Build ``karma-meta--{team_name}``."""
    if "--" in team_name:
        raise ValueError(f"team_name must not contain '--': {team_name!r}")
    return f"{METADATA_PREFIX}{team_name}"


def parse_metadata_folder_id(folder_id: str) -> Optional[str]:
    """Parse ``karma-meta--{team_name}`` into team_name. Returns None if not metadata."""
    if not folder_id.startswith(METADATA_PREFIX):
        return None
    return folder_id[len(METADATA_PREFIX):]


def is_metadata_folder(folder_id: str) -> bool:
    return folder_id.startswith(METADATA_PREFIX)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def write_member_state(
    meta_dir: Path,
    *,
    member_tag: str,
    user_id: str,
    machine_id: str = "",
    device_id: str = "",
    subscriptions: dict[str, bool] | None = None,
    sync_direction: str = "both",
    session_limit: str = "all",
) -> Path:
    """Write this device's state file to the metadata folder."""
    members_dir = meta_dir / "members"
    members_dir.mkdir(parents=True, exist_ok=True)

    state = {
        "member_tag": member_tag,
        "user_id": user_id,
        "machine_id": machine_id,
        "device_id": device_id,
        "subscriptions": subscriptions or {},
        "sync_direction": sync_direction,
        "session_limit": session_limit,
        "updated_at": _now_iso(),
    }

    path = members_dir / f"{member_tag}.json"
    path.write_text(json.dumps(state, indent=2))
    return path


def write_removal_signal(
    meta_dir: Path,
    *,
    removed_member_tag: str,
    removed_device_id: str,
    removed_by: str,
) -> Path:
    """Write a removal signal for a member."""
    removals_dir = meta_dir / "removals"
    removals_dir.mkdir(parents=True, exist_ok=True)

    signal = {
        "member_tag": removed_member_tag,
        "device_id": removed_device_id,
        "removed_by": removed_by,
        "removed_at": _now_iso(),
    }

    path = removals_dir / f"{removed_member_tag}.json"
    path.write_text(json.dumps(signal, indent=2))
    return path


def write_team_info(meta_dir: Path, *, team_name: str, created_by: str) -> Path:
    """Write team-level info (created once, rarely updated)."""
    info = {
        "name": team_name,
        "created_by": created_by,
        "created_at": _now_iso(),
    }

    path = meta_dir / "team.json"
    path.write_text(json.dumps(info, indent=2))
    return path


def read_all_member_states(meta_dir: Path) -> list[dict]:
    """Read all member state files from the metadata folder."""
    members_dir = meta_dir / "members"
    if not members_dir.exists():
        return []

    states = []
    for path in members_dir.glob("*.json"):
        try:
            states.append(json.loads(path.read_text()))
        except (json.JSONDecodeError, OSError) as e:
            logger.warning("Failed to read member state %s: %s", path, e)
    return states


def read_removal_signals(meta_dir: Path) -> list[dict]:
    """Read all removal signal files."""
    removals_dir = meta_dir / "removals"
    if not removals_dir.exists():
        return []

    signals = []
    for path in removals_dir.glob("*.json"):
        try:
            signals.append(json.loads(path.read_text()))
        except (json.JSONDecodeError, OSError) as e:
            logger.warning("Failed to read removal signal %s: %s", path, e)
    return signals


def read_team_info(meta_dir: Path) -> Optional[dict]:
    """Read team.json. Returns None if not found."""
    path = meta_dir / "team.json"
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text())
    except (json.JSONDecodeError, OSError):
        return None


def is_removed(meta_dir: Path, member_tag: str) -> bool:
    """Check if a member_tag has a removal signal."""
    path = meta_dir / "removals" / f"{member_tag}.json"
    return path.exists()


def validate_removal_authority(meta_dir: Path, remover_member_tag: str) -> bool:
    """Check if the remover is the team creator (creator-only removal)."""
    info = read_team_info(meta_dir)
    if info is None:
        return False
    return info.get("created_by") == remover_member_tag
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd api && python -m pytest tests/test_sync_metadata.py -v`
Expected: All pass

- [ ] **Step 5: Commit**

```bash
cd api
git add services/sync_metadata.py tests/test_sync_metadata.py
git commit -m "feat(sync): add sync_metadata.py for team metadata folder helpers

Provides read/write helpers for the karma-meta--{team} folder:
member state files, removal signals, team info. Creator-only
removal authority enforced via team.json.created_by check."
```

---

### Task 2.2: Create Metadata Folder on Team Create/Join

**Files:**
- Modify: `api/services/sync_folders.py` (add `ensure_metadata_folder`)
- Modify: `api/routers/sync_teams.py` (call in create + join)
- Modify: `api/services/folder_id.py` (add metadata folder predicates — already done in T2.1)
- Test: `api/tests/test_sync_metadata_creation.py` (create)

- [ ] **Step 1: Write the failing test**

```python
# api/tests/test_sync_metadata_creation.py
"""Tests for metadata folder creation during team create/join."""

from unittest.mock import AsyncMock, MagicMock
import pytest


@pytest.fixture
def mock_config():
    config = MagicMock()
    config.user_id = "jayant"
    config.machine_id = "Mac-Mini"
    config.machine_tag = "mac-mini"
    config.member_tag = "jayant.mac-mini"
    config.syncthing.device_id = "LEADER-DID"
    return config


@pytest.mark.asyncio
async def test_ensure_metadata_folder_creates_sendreceive(mock_config):
    """Metadata folder should be created as sendreceive type."""
    mock_proxy = AsyncMock()
    mock_proxy.update_folder_devices = MagicMock(side_effect=ValueError("not found"))
    mock_proxy.add_folder = AsyncMock()

    from services.sync_folders import ensure_metadata_folder

    await ensure_metadata_folder(
        mock_proxy, mock_config, "acme", ["LEADER-DID", "AYUSH-DID"]
    )

    # Verify add_folder was called with sendreceive type
    mock_proxy.add_folder.assert_called_once()
    call_args = mock_proxy.add_folder.call_args
    assert call_args[0][0] == "karma-meta--acme"  # folder_id
    assert call_args[0][3] == "sendreceive"  # folder_type
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd api && python -m pytest tests/test_sync_metadata_creation.py -v`
Expected: FAIL — `ImportError: cannot import name 'ensure_metadata_folder'`

- [ ] **Step 3: Implement ensure_metadata_folder**

Add to `api/services/sync_folders.py`:

```python
from services.sync_metadata import build_metadata_folder_id, write_team_info, write_member_state

async def ensure_metadata_folder(
    proxy, config, team_name: str, device_ids: list[str],
    *, is_creator: bool = False,
) -> None:
    """Create or update the team metadata folder (sendreceive, shared by all members).

    Also writes the local member's state file and team.json (if creator).
    """
    from karma.config import KARMA_BASE

    folder_id = build_metadata_folder_id(team_name)
    meta_path = KARMA_BASE / "metadata-folders" / team_name
    meta_path.mkdir(parents=True, exist_ok=True)

    try:
        await run_sync(proxy.update_folder_devices, folder_id, device_ids)
    except ValueError:
        all_ids = list(device_ids)
        if config.syncthing.device_id and config.syncthing.device_id not in all_ids:
            all_ids.append(config.syncthing.device_id)
        await run_sync(proxy.add_folder, folder_id, str(meta_path), all_ids, "sendreceive")

    # Write team.json if we're the creator
    if is_creator:
        write_team_info(meta_path, team_name=team_name, created_by=config.member_tag)

    # Write own member state
    write_member_state(
        meta_path,
        member_tag=config.member_tag,
        user_id=config.user_id,
        machine_id=config.machine_id,
        device_id=config.syncthing.device_id or "",
    )
```

- [ ] **Step 4: Wire into team create and join endpoints**

In `api/routers/sync_teams.py`, in `sync_create_team` (after creating team + adding self):
```python
# Create metadata folder (sendreceive, shared with future members)
await ensure_metadata_folder(proxy, config, team_name, [own_did], is_creator=True)
```

In `sync_join_team` (after creating team + adding members):
```python
# Create/join metadata folder
leader_did = parts[-1]  # from join code parsing
await ensure_metadata_folder(proxy, config, team_name, [own_did, leader_did])
```

In `auto_share_folders` in `sync_folders.py`, also add the new device to the metadata folder:
```python
# Add new device to metadata folder
try:
    meta_folder_id = build_metadata_folder_id(team_name)
    await run_sync(proxy.update_folder_devices, meta_folder_id, all_device_ids)
except Exception as e:
    logger.debug("Failed to update metadata folder devices: %s", e)
```

- [ ] **Step 5: Run tests**

Run: `cd api && python -m pytest tests/test_sync_metadata_creation.py tests/test_sync_team_crud.py -v`

- [ ] **Step 6: Commit**

```bash
cd api
git add services/sync_folders.py routers/sync_teams.py tests/test_sync_metadata_creation.py
git commit -m "feat(sync): create karma-meta--{team} folder on team create/join

Metadata folder is sendreceive type shared by all members. Team
creator writes team.json with created_by. Each member writes their
own state file on join."
```

---

## Chunk 2: State Writes & Reads (T2.3–T2.5)

### Task 2.3: Write Own Member State on Key Events

**Files:**
- Create: `api/services/sync_metadata_writer.py` (thin wrapper that finds meta_dir and writes)
- Modify: `api/routers/sync_teams.py` (join writes state)
- Modify: `api/routers/sync_projects.py` (share/unshare updates subscriptions)
- Modify: `api/routers/sync_members.py` (settings change updates state)

- [ ] **Step 1: Implement sync_metadata_writer.py**

```python
# api/services/sync_metadata_writer.py
"""Convenience wrapper to write own state to the metadata folder."""

import logging
from pathlib import Path

from services.sync_metadata import (
    build_metadata_folder_id,
    write_member_state,
)

logger = logging.getLogger(__name__)


def update_own_metadata(config, conn, team_name: str) -> None:
    """Write/update this device's state in the team metadata folder.

    Reads current subscriptions and settings from DB, writes to the
    metadata folder so other members can see our state.
    """
    from karma.config import KARMA_BASE
    from db.sync_queries import list_team_projects, get_effective_setting

    meta_dir = KARMA_BASE / "metadata-folders" / team_name
    if not meta_dir.exists():
        logger.debug("Metadata dir not found for team %s", team_name)
        return

    # Build subscriptions from team projects (all subscribed by default)
    projects = list_team_projects(conn, team_name)
    subscriptions = {}
    for proj in projects:
        # Check sync_rejected_folders for opt-out
        encoded = proj["project_encoded_name"]
        subscriptions[encoded] = True  # default opt-in

    # Check rejected folders
    try:
        rows = conn.execute(
            "SELECT folder_id FROM sync_rejected_folders WHERE team_name = ?",
            (team_name,),
        ).fetchall()
        rejected_suffixes = set()
        for row in rows:
            from services.folder_id import parse_outbox_id
            parsed = parse_outbox_id(row[0] if isinstance(row, tuple) else row["folder_id"])
            if parsed:
                rejected_suffixes.add(parsed[1])

        from services.sync_identity import _compute_proj_suffix
        for proj in projects:
            suffix = _compute_proj_suffix(
                proj.get("git_identity"), proj.get("path"), proj["project_encoded_name"]
            )
            if suffix in rejected_suffixes:
                subscriptions[proj["project_encoded_name"]] = False
    except Exception as e:
        logger.debug("Failed to check rejected folders: %s", e)

    sync_direction = get_effective_setting(conn, "sync_direction", team_name=team_name)
    session_limit = get_effective_setting(conn, "sync_session_limit", team_name=team_name) or "all"

    write_member_state(
        meta_dir,
        member_tag=config.member_tag,
        user_id=config.user_id,
        machine_id=config.machine_id,
        device_id=config.syncthing.device_id or "",
        subscriptions=subscriptions,
        sync_direction=sync_direction,
        session_limit=session_limit,
    )
```

- [ ] **Step 2: Call from key endpoints**

Add `update_own_metadata(config, conn, team_name)` calls after:
- `sync_join_team` (after joining)
- `sync_add_team_project` (after sharing a project)
- `sync_remove_team_project` (after removing a project)
- `sync_update_team_settings` (after changing settings)
- `sync_update_member_settings` (after changing member settings)

- [ ] **Step 3: Test and commit**

```bash
cd api
git add services/sync_metadata_writer.py routers/sync_teams.py \
        routers/sync_projects.py routers/sync_members.py
git commit -m "feat(sync): write own member state to metadata folder on key events

Subscriptions, sync_direction, and session_limit are published to
the metadata folder so other members can see our state."
```

---

### Task 2.4: Write Removal Signal (Creator Only)

**Files:**
- Modify: `api/routers/sync_members.py` (remove-member writes removal signal)
- Test: existing removal tests + new metadata test

- [ ] **Step 1: Implement removal signal in remove-member endpoint**

In `api/routers/sync_members.py`, in `sync_remove_member`, after the existing cleanup:

```python
    # Write removal signal to metadata folder (creator-only enforcement)
    try:
        from karma.config import KARMA_BASE
        from services.sync_metadata import (
            write_removal_signal, validate_removal_authority,
        )

        meta_dir = KARMA_BASE / "metadata-folders" / team_name
        if meta_dir.exists():
            if not validate_removal_authority(meta_dir, config.member_tag):
                raise HTTPException(
                    403,
                    f"Only the team creator can remove members. "
                    f"You can control your own sync direction instead.",
                )
            write_removal_signal(
                meta_dir,
                removed_member_tag=member_tag,
                removed_device_id=member_device_id,
                removed_by=config.member_tag,
            )
    except HTTPException:
        raise
    except Exception as e:
        logger.warning("Failed to write removal signal: %s", e)
```

- [ ] **Step 2: Test and commit**

```bash
cd api
git add routers/sync_members.py
git commit -m "feat(sync): write removal signal to metadata folder

Only the team creator can remove members (enforced via team.json).
Removal signal propagates to all members via Syncthing."
```

---

### Task 2.5: Reconciliation Reads Metadata Folder

**Files:**
- Create: `api/services/sync_metadata_reconciler.py`
- Test: `api/tests/test_sync_metadata_reconciler.py` (create)

- [ ] **Step 1: Implement the reconciler**

```python
# api/services/sync_metadata_reconciler.py
"""Reconcile local DB state with team metadata folder contents."""

import logging
from pathlib import Path

from db.sync_queries import (
    list_members, list_teams, upsert_member, remove_member, log_event,
)
from services.sync_metadata import (
    read_all_member_states, read_removal_signals, is_removed,
)

logger = logging.getLogger(__name__)


def reconcile_metadata_folder(config, conn, team_name: str) -> dict:
    """Read the team metadata folder and reconcile with local DB.

    1. Read all member state files → add missing members to DB
    2. Read removal signals → if WE are removed, flag for auto-leave
    3. Read other members' subscriptions → cache locally for auto_share_folders

    Returns dict with counts: members_added, members_updated, self_removed.
    """
    from karma.config import KARMA_BASE

    meta_dir = KARMA_BASE / "metadata-folders" / team_name
    if not meta_dir.exists():
        return {"members_added": 0, "members_updated": 0, "self_removed": False}

    stats = {"members_added": 0, "members_updated": 0, "self_removed": False}

    # Check if WE are removed
    if is_removed(meta_dir, config.member_tag):
        logger.warning("This device has been removed from team %s", team_name)
        stats["self_removed"] = True
        return stats

    # Read all member states and reconcile with DB
    member_states = read_all_member_states(meta_dir)
    existing_members = list_members(conn, team_name)
    existing_tags = {m.get("member_tag") for m in existing_members if m.get("member_tag")}
    existing_devices = {m["device_id"] for m in existing_members}

    # Check removal signals (skip removed members)
    removal_signals = read_removal_signals(meta_dir)
    removed_tags = {r["member_tag"] for r in removal_signals}

    for state in member_states:
        mtag = state.get("member_tag", "")
        device_id = state.get("device_id", "")
        user_id = state.get("user_id", "")

        if not mtag or not device_id:
            continue

        # Skip removed members
        if mtag in removed_tags:
            continue

        # Skip self
        if mtag == config.member_tag:
            continue

        if mtag not in existing_tags and device_id not in existing_devices:
            # New member discovered via metadata
            from services.folder_id import parse_member_tag
            _, machine_tag = parse_member_tag(mtag)
            upsert_member(
                conn, team_name, user_id, device_id=device_id,
                machine_id=state.get("machine_id"),
                machine_tag=machine_tag,
                member_tag=mtag,
            )
            log_event(
                conn, "member_added", team_name=team_name,
                member_name=user_id,
                detail={"source": "metadata_folder", "member_tag": mtag},
            )
            stats["members_added"] += 1
        elif device_id in existing_devices:
            # Existing member — update identity columns if missing
            upsert_member(
                conn, team_name, user_id, device_id=device_id,
                machine_id=state.get("machine_id"),
                machine_tag=state.get("member_tag", "").split(".", 1)[1] if "." in state.get("member_tag", "") else None,
                member_tag=mtag,
            )
            stats["members_updated"] += 1

    return stats


def reconcile_all_teams_metadata(config, conn) -> dict:
    """Run metadata reconciliation for all teams."""
    total = {"teams": 0, "members_added": 0, "self_removed_teams": []}
    for team in list_teams(conn):
        result = reconcile_metadata_folder(config, conn, team["name"])
        total["teams"] += 1
        total["members_added"] += result["members_added"]
        if result["self_removed"]:
            total["self_removed_teams"].append(team["name"])
    return total
```

- [ ] **Step 2: Write tests**

```python
# api/tests/test_sync_metadata_reconciler.py
"""Tests for metadata folder reconciliation."""

import sqlite3
import json
from pathlib import Path
from unittest.mock import MagicMock, patch
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
    config.machine_tag = "mac-mini"
    config.member_tag = "jayant.mac-mini"
    config.syncthing.device_id = "LEADER-DID"
    return config


def test_reconcile_discovers_new_member(conn, mock_config, tmp_path):
    """New member in metadata folder should be added to DB."""
    from db.sync_queries import create_team, upsert_member, list_members

    create_team(conn, "acme", backend="syncthing")
    upsert_member(conn, "acme", "jayant", device_id="LEADER-DID",
                  member_tag="jayant.mac-mini")

    # Write ayush's state to metadata folder
    meta_dir = tmp_path / "metadata-folders" / "acme"
    members_dir = meta_dir / "members"
    members_dir.mkdir(parents=True)
    (members_dir / "ayush.ayush-mac.json").write_text(json.dumps({
        "member_tag": "ayush.ayush-mac",
        "user_id": "ayush",
        "machine_id": "Ayush-Mac",
        "device_id": "AYUSH-DID",
    }))

    with patch("services.sync_metadata_reconciler.KARMA_BASE", tmp_path):
        from services.sync_metadata_reconciler import reconcile_metadata_folder
        result = reconcile_metadata_folder(mock_config, conn, "acme")

    assert result["members_added"] == 1
    members = list_members(conn, "acme")
    ayush = [m for m in members if m["name"] == "ayush"]
    assert len(ayush) == 1
    assert ayush[0]["member_tag"] == "ayush.ayush-mac"


def test_reconcile_detects_self_removal(conn, mock_config, tmp_path):
    """If our member_tag has a removal signal, self_removed should be True."""
    from db.sync_queries import create_team

    create_team(conn, "acme", backend="syncthing")

    meta_dir = tmp_path / "metadata-folders" / "acme"
    removals_dir = meta_dir / "removals"
    removals_dir.mkdir(parents=True)
    (removals_dir / "jayant.mac-mini.json").write_text(json.dumps({
        "member_tag": "jayant.mac-mini",
        "device_id": "LEADER-DID",
        "removed_by": "admin.admin-pc",
        "removed_at": "2026-03-11T12:00:00Z",
    }))

    with patch("services.sync_metadata_reconciler.KARMA_BASE", tmp_path):
        from services.sync_metadata_reconciler import reconcile_metadata_folder
        result = reconcile_metadata_folder(mock_config, conn, "acme")

    assert result["self_removed"] is True
    assert result["members_added"] == 0
```

- [ ] **Step 3: Run tests**

Run: `cd api && python -m pytest tests/test_sync_metadata_reconciler.py -v`
Expected: PASS

- [ ] **Step 4: Commit**

```bash
cd api
git add services/sync_metadata_reconciler.py tests/test_sync_metadata_reconciler.py
git commit -m "feat(sync): metadata folder reconciliation

Reads member states and removal signals from karma-meta--{team}.
Discovers new members, updates identity columns, detects self-removal."
```

---

## Chunk 3: Auto-Leave & Watcher (T2.6–T2.7, Parallel)

### Task 2.6: Auto-Leave on Self-Removal Detection

**Files:**
- Modify: `api/routers/sync_teams.py` or new endpoint
- Uses: `reconcile_metadata_folder` result's `self_removed` flag

When `self_removed=True`, trigger the existing `sync_delete_team` flow (clean up Syncthing folders, delete team from DB). This can be wired into the reconciliation that runs periodically.

- [ ] **Step 1: Implement auto-leave in reconciliation**

In `api/services/sync_metadata_reconciler.py`, extend `reconcile_all_teams_metadata`:

```python
def reconcile_all_teams_metadata(config, conn) -> dict:
    total = {"teams": 0, "members_added": 0, "self_removed_teams": []}
    for team in list_teams(conn):
        result = reconcile_metadata_folder(config, conn, team["name"])
        total["teams"] += 1
        total["members_added"] += result["members_added"]
        if result["self_removed"]:
            total["self_removed_teams"].append(team["name"])
            # Auto-leave: clean up Syncthing state and delete team locally
            try:
                from services.sync_folders import cleanup_syncthing_for_team
                from services.sync_identity import get_proxy
                proxy = get_proxy()
                import asyncio
                asyncio.get_event_loop().run_until_complete(
                    cleanup_syncthing_for_team(proxy, config, conn, team["name"])
                )
                from db.sync_queries import delete_team
                log_event(conn, "team_left", team_name=team["name"],
                          detail={"reason": "removed_via_metadata"})
                delete_team(conn, team["name"])
                logger.info("Auto-left team %s (removed via metadata)", team["name"])
            except Exception as e:
                logger.warning("Failed to auto-leave team %s: %s", team["name"], e)
    return total
```

- [ ] **Step 2: Test and commit**

```bash
cd api
git add services/sync_metadata_reconciler.py
git commit -m "feat(sync): auto-leave team when removal signal detected

When metadata reconciliation finds our member_tag in the removals
folder, automatically clean up Syncthing state and delete the team
locally. No stale state remains."
```

---

### Task 2.7: Watcher-Driven Reconciliation Loop

**Files:**
- Modify: wherever the watcher loop is defined (check `api/services/` or `api/routers/sync_operations.py`)
- Add metadata reconciliation to the periodic loop

- [ ] **Step 1: Find the watcher implementation**

The watcher is referenced in `api/routers/sync_operations.py` (watch_start/watch_stop). Find the actual loop and add:

```python
# Every 60 seconds (or on Syncthing event):
from services.sync_metadata_reconciler import reconcile_all_teams_metadata
result = reconcile_all_teams_metadata(config, conn)
if result["self_removed_teams"]:
    logger.info("Auto-left teams: %s", result["self_removed_teams"])
```

Also add the existing reconciliation phases:
```python
from services.sync_reconciliation import (
    reconcile_introduced_devices,
    reconcile_pending_handshakes,
)
await reconcile_introduced_devices(proxy, config, conn)
await reconcile_pending_handshakes(proxy, config, conn)
```

- [ ] **Step 2: Test and commit**

```bash
git add api/services/ api/routers/sync_operations.py
git commit -m "feat(sync): watcher runs metadata + device reconciliation every 60s

System is now self-healing without UI interaction. Watcher periodically
reconciles metadata folder state, introduced devices, and pending
handshakes."
```

---

## Post-Phase Verification

- [ ] **Scenario test: Create team, join, remove member, verify auto-leave**

1. Machine A creates team, shares project
2. Machine B joins team
3. Machine A removes Machine B
4. Verify: removal signal written to metadata folder
5. Verify: Machine B's next reconciliation detects removal and auto-leaves

- [ ] **Run full test suite**

```bash
cd api && python -m pytest tests/ -v --tb=short
```
