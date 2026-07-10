# Sync v2 Phase 3: UX Polish

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Persistent folder rejection (no re-offering), selective project subscriptions (opt-out), any-member invite, and per-device session limits.

**Architecture:** Uses `sync_rejected_folders` table (created in Phase 1 migration), metadata folder subscriptions (Phase 2), and new invite endpoint.

**Tech Stack:** Python, FastAPI, SQLite, pytest

**Prerequisite:** Phase 2 complete.

---

## Chunk 1: Persistent Rejection & Subscriptions (T3.1–T3.4)

### Task 3.1: Persistent Folder Rejection Table + Logic

The `sync_rejected_folders` table was created in Phase 1 (migration v17). Now wire it into the rejection and acceptance flows.

**Files:**
- Modify: `api/db/sync_queries.py` (add reject/check functions)
- Modify: `api/routers/sync_pending.py` (rejection saves to DB)
- Modify: `cli/karma/pending.py` (skip rejected folders)
- Test: `api/tests/test_sync_rejection.py` (create)

- [ ] **Step 1: Write the failing test**

```python
# api/tests/test_sync_rejection.py
"""Tests for persistent folder rejection."""

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


def test_reject_folder_persists(conn):
    """Rejecting a folder should persist in the DB."""
    from db.sync_queries import reject_folder, is_folder_rejected

    reject_folder(conn, "karma-out--ayush.mac--proj", team_name="acme")

    assert is_folder_rejected(conn, "karma-out--ayush.mac--proj") is True
    assert is_folder_rejected(conn, "karma-out--other--proj") is False


def test_unreject_folder(conn):
    """Accepting a previously rejected folder should remove the rejection."""
    from db.sync_queries import reject_folder, unreject_folder, is_folder_rejected

    reject_folder(conn, "karma-out--ayush.mac--proj", team_name="acme")
    assert is_folder_rejected(conn, "karma-out--ayush.mac--proj") is True

    unreject_folder(conn, "karma-out--ayush.mac--proj")
    assert is_folder_rejected(conn, "karma-out--ayush.mac--proj") is False


def test_list_rejected_folders(conn):
    """Should list all rejected folders for a team."""
    from db.sync_queries import reject_folder, list_rejected_folders

    reject_folder(conn, "karma-out--a.mac--p1", team_name="acme")
    reject_folder(conn, "karma-out--b.mac--p2", team_name="acme")
    reject_folder(conn, "karma-out--c.mac--p3", team_name="other")

    acme_rejected = list_rejected_folders(conn, "acme")
    assert len(acme_rejected) == 2
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd api && python -m pytest tests/test_sync_rejection.py -v`
Expected: FAIL — `ImportError: cannot import name 'reject_folder'`

- [ ] **Step 3: Implement DB functions**

Add to `api/db/sync_queries.py`:

```python
def reject_folder(conn: sqlite3.Connection, folder_id: str, *, team_name: str = None) -> None:
    """Persistently reject a folder offer (won't be re-offered)."""
    conn.execute(
        "INSERT OR REPLACE INTO sync_rejected_folders (folder_id, team_name) VALUES (?, ?)",
        (folder_id, team_name),
    )
    conn.commit()


def unreject_folder(conn: sqlite3.Connection, folder_id: str) -> None:
    """Remove a folder rejection (allows re-offering)."""
    conn.execute("DELETE FROM sync_rejected_folders WHERE folder_id = ?", (folder_id,))
    conn.commit()


def is_folder_rejected(conn: sqlite3.Connection, folder_id: str) -> bool:
    """Check if a folder has been persistently rejected."""
    row = conn.execute(
        "SELECT 1 FROM sync_rejected_folders WHERE folder_id = ?", (folder_id,)
    ).fetchone()
    return row is not None


def list_rejected_folders(conn: sqlite3.Connection, team_name: str) -> list[dict]:
    """List all rejected folders for a team."""
    rows = conn.execute(
        "SELECT folder_id, team_name, rejected_at FROM sync_rejected_folders WHERE team_name = ?",
        (team_name,),
    ).fetchall()
    return [dict(r) for r in rows]
```

- [ ] **Step 4: Wire into rejection endpoint**

In `api/routers/sync_pending.py`, in `sync_reject_single_folder`:

```python
    # After dismissing with Syncthing, persist the rejection
    from db.sync_queries import reject_folder
    conn = _sid._get_sync_conn()

    # Find team for this folder
    from services.sync_folders import find_team_for_folder
    team = find_team_for_folder(conn, [folder_id])
    reject_folder(conn, folder_id, team_name=team)
```

- [ ] **Step 5: Wire into pending folder filtering**

In `api/routers/sync_pending.py`, in `sync_pending`, filter out rejected folders:

```python
    # After getting pending folders, filter out rejected ones
    from db.sync_queries import is_folder_rejected
    pending = [item for item in pending if not is_folder_rejected(conn, item["folder_id"])]
```

In `cli/karma/pending.py`, in `accept_pending_folders`, skip rejected:

```python
    # In the folder processing loop:
    from db.sync_queries import is_folder_rejected
    if is_folder_rejected(conn, folder_id):
        continue
```

- [ ] **Step 6: Wire into acceptance (unreject on accept)**

In `api/routers/sync_pending.py`, in `sync_accept_single_folder`:

```python
    # If user explicitly accepts a previously rejected folder, remove the rejection
    from db.sync_queries import unreject_folder
    conn = _sid._get_sync_conn()
    unreject_folder(conn, folder_id)
```

- [ ] **Step 7: Run tests**

Run: `cd api && python -m pytest tests/test_sync_rejection.py tests/test_sync_pending.py -v`
Expected: All pass

- [ ] **Step 8: Commit**

```bash
cd api
git add db/sync_queries.py routers/sync_pending.py
git commit -m "feat(sync): persistent folder rejection — rejected folders never re-offered

Adds reject_folder/unreject_folder/is_folder_rejected to sync_queries.
Rejection endpoint saves to DB. Pending listing filters rejected.
Explicit accept removes prior rejection."
```

---

### Task 3.2: Update Metadata on Rejection (Subscription Signal)

When a user rejects a folder, update their metadata file's subscriptions to `false` for that project. Other members can read this and skip creating inbox folders for us.

**Files:**
- Modify: `api/routers/sync_pending.py` (rejection updates metadata)
- Uses: `api/services/sync_metadata_writer.py` (from Phase 2)

- [ ] **Step 1: After rejection, update metadata**

In `sync_reject_single_folder`, after persisting rejection:

```python
    # Update own metadata to reflect unsubscription
    try:
        from services.sync_metadata_writer import update_own_metadata
        config = await run_sync(_sid._load_identity)
        if config:
            update_own_metadata(config, conn, team)
    except Exception as e:
        logger.debug("Failed to update metadata after rejection: %s", e)
```

- [ ] **Step 2: Commit**

```bash
cd api
git add routers/sync_pending.py
git commit -m "feat(sync): rejection updates metadata folder subscriptions

When a folder is rejected, the member's metadata file is updated
with subscription=false for that project. Other members can read
this and avoid re-sharing."
```

---

### Task 3.3: auto_share_folders Checks Subscriptions

Before creating an inbox for a member, check their metadata file's subscriptions. If the project is explicitly `false`, skip inbox creation.

**Files:**
- Modify: `api/services/sync_folders.py:205-242` (auto_share_folders)
- Test: `api/tests/test_sync_subscription_check.py` (create)

- [ ] **Step 1: Write the failing test**

```python
# api/tests/test_sync_subscription_check.py
"""Tests for subscription checking in auto_share_folders."""

import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch
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


def test_should_check_member_subscription(tmp_path):
    """auto_share_folders should check metadata subscriptions before creating inbox."""
    from services.sync_metadata import read_all_member_states

    meta_dir = tmp_path / "metadata-folders" / "acme"
    members_dir = meta_dir / "members"
    members_dir.mkdir(parents=True)

    # Ayush has unsubscribed from the project
    (members_dir / "ayush.ayush-mac.json").write_text(json.dumps({
        "member_tag": "ayush.ayush-mac",
        "user_id": "ayush",
        "device_id": "AYUSH-DID",
        "subscriptions": {"jayantdevkar-claude-karma": False},
    }))

    states = read_all_member_states(meta_dir)
    ayush_state = states[0]
    assert ayush_state["subscriptions"]["jayantdevkar-claude-karma"] is False
```

- [ ] **Step 2: Implement subscription check**

In `api/services/sync_folders.py`, in `auto_share_folders`, before calling `ensure_inbox_folders`:

```python
    # Check member subscriptions from metadata folder
    member_subscriptions = {}
    try:
        from karma.config import KARMA_BASE
        from services.sync_metadata import read_all_member_states
        meta_dir = KARMA_BASE / "metadata-folders" / team_name
        if meta_dir.exists():
            for state in read_all_member_states(meta_dir):
                device = state.get("device_id", "")
                subs = state.get("subscriptions", {})
                member_subscriptions[device] = subs
    except Exception as e:
        logger.debug("Failed to read member subscriptions: %s", e)
```

Then in `ensure_inbox_folders`, add a subscription check parameter:

```python
async def ensure_inbox_folders(
    proxy, config, members, encoded, proj_suffix,
    *, only_device_id=None, member_subscriptions=None,
):
    for m in members:
        # ... existing checks ...

        # Check subscription opt-out
        if member_subscriptions:
            device_subs = member_subscriptions.get(m["device_id"], {})
            # Check by encoded_name or by suffix
            if any(v is False for k, v in device_subs.items() if k == encoded or k.endswith(proj_suffix)):
                logger.info("Skipping inbox for %s — unsubscribed from %s", m.get("member_tag", m["name"]), proj_suffix)
                continue
```

- [ ] **Step 3: Run tests and commit**

```bash
cd api
git add services/sync_folders.py tests/test_sync_subscription_check.py
git commit -m "feat(sync): auto_share_folders respects member subscriptions

Before creating an inbox folder for a member, checks their metadata
file's subscriptions. If explicitly false, skips inbox creation."
```

---

### Task 3.4: Any-Member Invite Endpoint

Any team member (not just the creator) can generate an invite code pointing to their own device as the entry point.

**Files:**
- Modify: `api/routers/sync_teams.py` (add invite endpoint)
- Test: `api/tests/test_sync_invite.py` (create)

- [ ] **Step 1: Write the failing test**

```python
# api/tests/test_sync_invite.py
"""Tests for any-member invite generation."""


def test_invite_code_uses_inviter_device():
    """Invite code should use the inviter's device_id, not the team creator's."""
    # The invite code format is team:user_id.machine_tag:device_id
    invite = "acme:ayush.ayush-mac:AYUSH-DID"
    parts = invite.split(":", 2)
    assert parts[0] == "acme"
    assert parts[1] == "ayush.ayush-mac"
    assert parts[2] == "AYUSH-DID"
```

- [ ] **Step 2: Implement invite endpoint**

Add to `api/routers/sync_teams.py`:

```python
@router.post("/teams/{team_name}/invite")
async def sync_generate_invite(team_name: str) -> Any:
    """Generate an invite code for this team using the current device as entry point.

    Any team member can generate an invite — the joiner connects to the inviter
    first, then the Syncthing mesh propagates all other devices.
    """
    conn = _sid._get_sync_conn()
    team = get_team(conn, team_name)
    if team is None:
        raise HTTPException(404, "Team not found")

    config = await run_sync(_sid._load_identity)
    if config is None:
        raise HTTPException(400, "Not initialized")

    # Verify caller is a member of this team
    members = list_members(conn, team_name)
    is_member = any(
        m["device_id"] == config.syncthing.device_id for m in members
    )
    if not is_member:
        raise HTTPException(403, "You are not a member of this team")

    invite_code = f"{team_name}:{config.member_tag}:{config.syncthing.device_id}"

    return {
        "invite_code": invite_code,
        "team_name": team_name,
        "inviter": config.member_tag,
        "note": "Any member can generate invite codes. The joiner connects to you first.",
    }
```

- [ ] **Step 3: Update join handler to accept any invite code**

The existing join handler already parses `team:user:device_id` format. With member_tag, the user part is now `user_id.machine_tag`. The join handler just needs to extract the device_id (last part) — it doesn't care about the inviter's identity beyond pairing.

Verify that `sync_join_team` in `sync_teams.py` handles the new format:

```python
# Existing parsing: parts = join_code.split(":", 2)
# parts[0] = team_name, parts[1] = inviter member_tag, parts[2] = device_id
# The device_id extraction already works. The member_tag in parts[1]
# is used for the member name — now it's a full member_tag, which is better.
```

- [ ] **Step 4: Run tests and commit**

```bash
cd api
git add routers/sync_teams.py tests/test_sync_invite.py
git commit -m "feat(sync): any team member can generate invite codes

POST /sync/teams/{team}/invite generates an invite code using the
caller's device as entry point. Reduces leader dependency — new
members can join via any online member."
```

---

### Task 3.5: Session Limit Per-Device in Metadata

Session limit is already per-team (`sync_teams.sync_session_limit`). Allow per-device override via the metadata file.

**Files:**
- Modify: `cli/karma/packager.py` (read session_limit from own metadata)
- Already written to metadata in Phase 2's `update_own_metadata`

- [ ] **Step 1: Update packager to check metadata**

In `cli/karma/packager.py`, in the `get_session_limit` method:

```python
def get_session_limit(self, team_name: str) -> str:
    """Get session limit, checking metadata file first (per-device override)."""
    # Check own metadata file for per-device override
    try:
        from karma.config import KARMA_BASE
        import json
        meta_file = KARMA_BASE / "metadata-folders" / team_name / "members" / f"{self.config.member_tag}.json"
        if meta_file.exists():
            state = json.loads(meta_file.read_text())
            limit = state.get("session_limit")
            if limit and limit != "all":
                return limit
    except Exception:
        pass

    # Fall back to team-level setting
    return self._get_team_session_limit(team_name)
```

- [ ] **Step 2: Commit**

```bash
git add cli/karma/packager.py
git commit -m "feat(sync): per-device session limit via metadata file

Packager checks own metadata file for session_limit override before
falling back to team-level setting. Allows each device to control
how many sessions it shares."
```

---

## Chunk 2: Frontend Hints (Not Implemented — For Reference)

The frontend changes needed to support the new UX:

### Pending Folders Page
- Show `member_tag` in descriptions: "jayant (mac-mini)" not "jayant"
- Accept / Decline buttons per folder
- "Accept All" batch button
- Declined folders don't reappear

### Team Members Page
- Show device info: "jayant (Mac Mini)" with machine icon
- Group by user_id, expand to see devices
- Per-device sync direction toggle
- Per-device session limit selector

### Project Sharing Page
- Subscribe / Unsubscribe toggle per project per device
- Show who's subscribed (from metadata folder)

### Settings Page
- "Manual approval" / "Auto-accept from team members" toggle
- Per-team and per-device overrides

---

## Post-Phase Verification

- [ ] **Rejected folder doesn't reappear**

1. Reject a pending folder
2. Trigger rescan
3. Verify folder doesn't appear in pending list

- [ ] **Unsubscribed project doesn't create inbox**

1. Member A unsubscribes from project X
2. Member B shares project X with team
3. Verify Member A doesn't get inbox folder for project X

- [ ] **Any-member invite works**

1. Member B generates invite code
2. Member C joins using B's invite
3. Verify C connects to B, mesh propagates A

- [ ] **Per-device session limit**

1. Set session_limit="recent_10" in member metadata
2. Run packager
3. Verify only 10 most recent sessions packaged

- [ ] **Run full test suite**

```bash
cd api && python -m pytest tests/ -v --tb=short
cd cli && python -m pytest tests/ -v --tb=short
```

- [ ] **Lint**

```bash
cd api && ruff check services/ routers/ db/
cd cli && ruff check karma/
```
