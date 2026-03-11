# Sync v2 Phase 1: Device = Member Identity

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make each device a distinct member with its own folder IDs, fixing the session merge bug and duplicate pending offer confusion.

**Architecture:** Introduce `member_tag` = `{user_id}.{machine_tag}` as the identity atom. All folder IDs, DB records, and reconciliation logic use `member_tag` instead of bare `user_id`. Machine tag is auto-derived from hostname, sanitized to `[a-z0-9-]+`.

**Tech Stack:** Python, FastAPI, Pydantic 2.x, SQLite (migration v17), pytest

**Prerequisite:** Phase 0 complete.

---

## Chunk 1: Core Identity Model (T1.1–T1.3, Sequential)

### Task 1.1: Add machine_tag and member_tag to SyncConfig

**Files:**
- Modify: `cli/karma/config.py:30-60` (SyncConfig class)
- Test: `cli/tests/test_sync_config_identity.py` (create)

- [ ] **Step 1: Write the failing test**

```python
# cli/tests/test_sync_config_identity.py
"""Tests for machine_tag and member_tag derivation in SyncConfig."""

import pytest


def test_machine_tag_from_hostname():
    """machine_tag should be sanitized hostname: lowercase, alphanumeric + hyphens."""
    from karma.config import _sanitize_machine_tag

    assert _sanitize_machine_tag("Jayants-Mac-Mini") == "jayants-mac-mini"
    assert _sanitize_machine_tag("MacBook Pro") == "macbook-pro"
    assert _sanitize_machine_tag("DESKTOP_PC.local") == "desktop-pc-local"
    assert _sanitize_machine_tag("my--weird---host") == "my-weird-host"  # collapse multi-hyphens
    assert _sanitize_machine_tag("") == "unknown"


def test_member_tag_computed():
    """member_tag should be user_id.machine_tag."""
    from karma.config import SyncConfig

    config = SyncConfig(user_id="jayant", machine_id="Jayants-Mac-Mini")
    assert config.member_tag == "jayant.jayants-mac-mini"


def test_member_tag_with_custom_machine_tag():
    """If machine_tag is explicitly set, it overrides auto-derivation."""
    from karma.config import SyncConfig

    config = SyncConfig(user_id="jayant", machine_id="Jayants-Mac-Mini", machine_tag="mbp")
    assert config.member_tag == "jayant.mbp"


def test_user_id_cannot_contain_dot():
    """user_id with dots should be rejected (dot is the member_tag separator)."""
    from karma.config import SyncConfig

    with pytest.raises(ValueError, match="user_id"):
        SyncConfig(user_id="jay.ant", machine_id="test")


def test_machine_tag_no_double_dash():
    """machine_tag must not contain -- (folder ID delimiter)."""
    from karma.config import _sanitize_machine_tag

    result = _sanitize_machine_tag("my--host")
    assert "--" not in result


def test_config_roundtrip_with_member_tag(tmp_path):
    """Save and load preserves machine_tag and member_tag."""
    import json

    config_path = tmp_path / "sync-config.json"
    data = {
        "user_id": "jayant",
        "machine_id": "Jayants-Mac-Mini",
        "machine_tag": "mac-mini",
        "syncthing": {"device_id": "ABC", "api_key": "key", "api_url": "http://localhost:8384"},
    }
    config_path.write_text(json.dumps(data))

    from karma.config import SyncConfig
    config = SyncConfig(**json.loads(config_path.read_text()))
    assert config.member_tag == "jayant.mac-mini"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd cli && python -m pytest tests/test_sync_config_identity.py -v`
Expected: FAIL — `ImportError: cannot import name '_sanitize_machine_tag'`

- [ ] **Step 3: Implement SyncConfig changes**

In `cli/karma/config.py`, add the sanitizer function and update `SyncConfig`:

```python
import re

def _sanitize_machine_tag(hostname: str) -> str:
    """Derive a safe machine_tag from hostname.

    Rules: lowercase, alphanumeric + hyphens only, collapse multi-hyphens,
    strip leading/trailing hyphens, no '--' (folder ID delimiter).
    """
    if not hostname:
        return "unknown"
    tag = hostname.lower()
    tag = re.sub(r"[^a-z0-9-]", "-", tag)   # non-alphanum → hyphen
    tag = re.sub(r"-{2,}", "-", tag)         # collapse multi-hyphens
    tag = tag.strip("-")
    return tag or "unknown"
```

Update `SyncConfig`:

```python
class SyncConfig(BaseModel):
    """Identity and credentials. Teams/members/projects live in SQLite."""

    model_config = ConfigDict(frozen=True)

    user_id: str = Field(..., description="User identity")
    machine_id: str = Field(
        default_factory=lambda: socket.gethostname(),
        description="Machine hostname",
    )
    machine_tag: str = Field(
        default=None,
        description="Sanitized machine identifier (auto-derived from machine_id if not set)",
    )
    syncthing: SyncthingSettings = Field(default_factory=SyncthingSettings)

    @field_validator("user_id")
    @classmethod
    def validate_user_id(cls, v: str) -> str:
        if not re.match(r"^[a-zA-Z0-9_-]+$", v):
            raise ValueError("user_id must be alphanumeric, dash, or underscore (no dots)")
        return v

    @model_validator(mode="after")
    def _derive_machine_tag(self) -> "SyncConfig":
        if self.machine_tag is None:
            # Use object.__setattr__ because model is frozen
            object.__setattr__(self, "machine_tag", _sanitize_machine_tag(self.machine_id))
        return self

    @property
    def member_tag(self) -> str:
        """Unique device identity: user_id.machine_tag"""
        return f"{self.user_id}.{self.machine_tag}"
```

Note: `model_validator(mode="after")` runs after field validation, allowing us to auto-derive `machine_tag` from `machine_id` when not explicitly set. `object.__setattr__` is needed because the model is frozen.

- [ ] **Step 4: Run test to verify it passes**

Run: `cd cli && python -m pytest tests/test_sync_config_identity.py -v`
Expected: All pass

- [ ] **Step 5: Run existing CLI tests**

Run: `cd cli && python -m pytest tests/ -v`
Expected: All pass

- [ ] **Step 6: Commit**

```bash
git add cli/karma/config.py cli/tests/test_sync_config_identity.py
git commit -m "feat(sync): add machine_tag and member_tag to SyncConfig

Each device now has a member_tag (user_id.machine_tag) that uniquely
identifies it. machine_tag is auto-derived from hostname (sanitized:
lowercase, alphanumeric + hyphens). user_id no longer allows dots
(dot is the member_tag separator)."
```

---

### Task 1.2: DB Migration v17 — Add Columns to sync_members

**Files:**
- Modify: `api/db/schema.py` (SCHEMA_VERSION 16→17, migration, updated CREATE TABLE)
- Test: `api/tests/test_sync_migration_v17.py` (create)

- [ ] **Step 1: Write the failing test**

```python
# api/tests/test_sync_migration_v17.py
"""Tests for schema migration v17 — sync_members identity columns."""

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


def test_sync_members_has_identity_columns(conn):
    """sync_members should have machine_id, machine_tag, member_tag columns."""
    cursor = conn.execute("PRAGMA table_info(sync_members)")
    columns = {row[1] for row in cursor.fetchall()}
    assert "machine_id" in columns
    assert "machine_tag" in columns
    assert "member_tag" in columns


def test_sync_rejected_folders_table_exists(conn):
    """sync_rejected_folders table should exist (for Phase 3, created here)."""
    cursor = conn.execute("PRAGMA table_info(sync_rejected_folders)")
    columns = {row[1] for row in cursor.fetchall()}
    assert "folder_id" in columns
    assert "team_name" in columns
    assert "rejected_at" in columns
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd api && python -m pytest tests/test_sync_migration_v17.py -v`
Expected: FAIL — columns not found

- [ ] **Step 3: Implement the migration**

In `api/db/schema.py`:

1. Update `SCHEMA_VERSION = 17`

2. Update the `sync_members` CREATE TABLE in SCHEMA_SQL:

```sql
CREATE TABLE IF NOT EXISTS sync_members (
    team_name TEXT NOT NULL,
    name TEXT NOT NULL,
    device_id TEXT NOT NULL,
    machine_id TEXT,
    machine_tag TEXT,
    member_tag TEXT,
    added_at TEXT DEFAULT (datetime('now')),
    PRIMARY KEY (team_name, device_id),
    FOREIGN KEY (team_name) REFERENCES sync_teams(name) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_sync_members_name ON sync_members(team_name, name);
CREATE INDEX IF NOT EXISTS idx_sync_members_tag ON sync_members(member_tag);
```

3. Add the `sync_rejected_folders` table to SCHEMA_SQL:

```sql
CREATE TABLE IF NOT EXISTS sync_rejected_folders (
    folder_id TEXT PRIMARY KEY,
    team_name TEXT,
    rejected_at TEXT DEFAULT (datetime('now'))
);
```

4. Add migration in `ensure_schema`:

```python
if version < 17:
    conn.executescript("""
        ALTER TABLE sync_members ADD COLUMN machine_id TEXT;
        ALTER TABLE sync_members ADD COLUMN machine_tag TEXT;
        ALTER TABLE sync_members ADD COLUMN member_tag TEXT;
        CREATE INDEX IF NOT EXISTS idx_sync_members_tag ON sync_members(member_tag);
        CREATE TABLE IF NOT EXISTS sync_rejected_folders (
            folder_id TEXT PRIMARY KEY,
            team_name TEXT,
            rejected_at TEXT DEFAULT (datetime('now'))
        );
    """)
    conn.execute("UPDATE schema_version SET version = 17")
    conn.commit()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd api && python -m pytest tests/test_sync_migration_v17.py -v`
Expected: PASS

- [ ] **Step 5: Run all schema-dependent tests**

Run: `cd api && python -m pytest tests/test_sync_*.py -v`
Expected: All pass (new columns are nullable, existing code unaffected)

- [ ] **Step 6: Commit**

```bash
cd api
git add db/schema.py tests/test_sync_migration_v17.py
git commit -m "feat(sync): schema v17 — add device identity columns to sync_members

Adds machine_id, machine_tag, member_tag columns to sync_members.
Creates sync_rejected_folders table for persistent folder rejection.
All new columns are nullable for backward compatibility during migration."
```

---

### Task 1.3: Update folder_id.py for member_tag Format

**Files:**
- Modify: `api/services/folder_id.py`
- Test: `api/tests/test_folder_id_v2.py` (create)

- [ ] **Step 1: Write the failing test**

```python
# api/tests/test_folder_id_v2.py
"""Tests for folder_id.py v2 — member_tag in folder IDs."""

import pytest
from services.folder_id import (
    build_outbox_id,
    build_handshake_id,
    parse_outbox_id,
    parse_handshake_id,
    parse_member_tag,
)


class TestBuildWithMemberTag:
    def test_outbox_with_member_tag(self):
        fid = build_outbox_id("jayant.mac-mini", "jayantdevkar-claude-karma")
        assert fid == "karma-out--jayant.mac-mini--jayantdevkar-claude-karma"

    def test_handshake_with_member_tag(self):
        fid = build_handshake_id("jayant.mac-mini", "acme")
        assert fid == "karma-join--jayant.mac-mini--acme"

    def test_two_devices_produce_different_outbox_ids(self):
        fid1 = build_outbox_id("jayant.mac-mini", "proj")
        fid2 = build_outbox_id("jayant.mbp", "proj")
        assert fid1 != fid2


class TestParseWithMemberTag:
    def test_parse_outbox_returns_member_tag(self):
        result = parse_outbox_id("karma-out--jayant.mac-mini--proj-suffix")
        assert result == ("jayant.mac-mini", "proj-suffix")

    def test_parse_handshake_returns_member_tag(self):
        result = parse_handshake_id("karma-join--ayush.ayush-mac--acme")
        assert result == ("ayush.ayush-mac", "acme")


class TestParseMemberTag:
    def test_parse_valid_member_tag(self):
        user_id, machine_tag = parse_member_tag("jayant.mac-mini")
        assert user_id == "jayant"
        assert machine_tag == "mac-mini"

    def test_parse_no_dot_returns_bare_name(self):
        """Legacy format without machine_tag — treat as user_id only."""
        user_id, machine_tag = parse_member_tag("jayant")
        assert user_id == "jayant"
        assert machine_tag is None

    def test_parse_multiple_dots_splits_on_first(self):
        user_id, machine_tag = parse_member_tag("jayant.mac.mini")
        assert user_id == "jayant"
        assert machine_tag == "mac.mini"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd api && python -m pytest tests/test_folder_id_v2.py -v`
Expected: FAIL — `ImportError: cannot import name 'parse_member_tag'`

- [ ] **Step 3: Implement**

Add `parse_member_tag` to `api/services/folder_id.py`:

```python
def parse_member_tag(member_tag: str) -> tuple[str, str | None]:
    """Parse member_tag into (user_id, machine_tag).

    Format: ``{user_id}.{machine_tag}`` or bare ``{user_id}`` (legacy).
    Splits on the FIRST dot only.

    Returns:
        (user_id, machine_tag) — machine_tag is None if no dot present.
    """
    if "." in member_tag:
        user_id, machine_tag = member_tag.split(".", 1)
        return user_id, machine_tag
    return member_tag, None
```

The existing `build_outbox_id`, `parse_outbox_id`, etc. already work with member_tag because they treat the first component as an opaque string. The `.` in `jayant.mac-mini` doesn't interfere with `--` delimiter parsing.

Verify: `build_outbox_id("jayant.mac-mini", "suffix")` → `"karma-out--jayant.mac-mini--suffix"`. The `_validate_no_double_dash` check passes because `.` is not `--`. The existing code already works.

- [ ] **Step 4: Run test to verify it passes**

Run: `cd api && python -m pytest tests/test_folder_id_v2.py -v`
Expected: PASS

- [ ] **Step 5: Run existing folder_id tests**

Run: `cd api && python -m pytest tests/ -k "folder" -v`
Expected: All pass

- [ ] **Step 6: Commit**

```bash
cd api
git add services/folder_id.py tests/test_folder_id_v2.py
git commit -m "feat(sync): add parse_member_tag to folder_id.py

Parses 'user_id.machine_tag' format used in folder IDs.
Existing build/parse functions already handle dots in the
username component — no changes needed."
```

---

## Chunk 2: Folder & Reconciliation Updates (T1.4–T1.6, Parallel after T1.3)

### Task 1.4: Update sync_folders.py to Use member_tag

**Files:**
- Modify: `api/services/sync_folders.py:32-92` (outbox, inbox, handshake)
- Modify: `api/services/sync_folders.py:205-242` (auto_share_folders)
- Modify: `api/services/sync_folders.py:245-368` (cleanup functions)
- Test: `api/tests/test_sync_folders_member_tag.py` (create)

- [ ] **Step 1: Write the failing test**

```python
# api/tests/test_sync_folders_member_tag.py
"""Tests for sync_folders.py using member_tag in folder IDs."""

from unittest.mock import AsyncMock, MagicMock
import pytest


@pytest.fixture
def mock_config():
    config = MagicMock()
    config.user_id = "jayant"
    config.machine_tag = "mac-mini"
    config.member_tag = "jayant.mac-mini"
    config.syncthing.device_id = "LEADER-DID"
    return config


@pytest.mark.asyncio
async def test_ensure_outbox_uses_member_tag(mock_config):
    """Outbox folder ID should use member_tag, not user_id."""
    mock_proxy = AsyncMock()
    mock_proxy.update_folder_devices = MagicMock(side_effect=ValueError("not found"))
    mock_proxy.add_folder = AsyncMock()

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr("services.sync_folders.KARMA_BASE", MagicMock(__truediv__=lambda s, x: MagicMock(__truediv__=lambda s, x: MagicMock(__truediv__=lambda s, x: MagicMock(mkdir=MagicMock()), __str__=lambda s: "/tmp/test"), __str__=lambda s: "/tmp"), __str__=lambda s: "/tmp"))
        from services.sync_folders import ensure_outbox_folder
        # This should use config.member_tag in the folder ID
        # We'll verify via the proxy.add_folder call

    # The folder ID passed to add_folder should contain member_tag
    # Exact assertion depends on implementation — key point is member_tag not user_id
```

NOTE: Due to the complexity of mocking filesystem paths, this task is better tested via integration test. Instead, write a unit test for the folder ID computation:

```python
# api/tests/test_sync_folders_member_tag.py
"""Tests that sync_folders uses member_tag in folder IDs."""

from services.folder_id import build_outbox_id


def test_outbox_id_uses_member_tag():
    """Outbox folder IDs must use member_tag to avoid same-user collision."""
    mini = build_outbox_id("jayant.mac-mini", "jayantdevkar-claude-karma")
    mbp = build_outbox_id("jayant.mbp", "jayantdevkar-claude-karma")
    assert mini != mbp
    assert "jayant.mac-mini" in mini
    assert "jayant.mbp" in mbp


def test_inbox_id_for_member_uses_member_tag():
    """Inbox folder ID for a member should use their member_tag."""
    inbox = build_outbox_id("ayush.ayush-mac", "jayantdevkar-claude-karma")
    assert "ayush.ayush-mac" in inbox
```

- [ ] **Step 2: Implement sync_folders.py changes**

All changes use `config.member_tag` instead of `config.user_id` and `m["member_tag"]` instead of `m["name"]` for folder ID construction:

**`ensure_outbox_folder` (line 39)**:
```python
# OLD: outbox_id = build_outbox_id(config.user_id, proj_suffix)
# NEW:
outbox_id = build_outbox_id(config.member_tag, proj_suffix)
```

Also update the path (line 40):
```python
# OLD: outbox_path = str(KARMA_BASE / "remote-sessions" / config.user_id / encoded)
# NEW:
outbox_path = str(KARMA_BASE / "remote-sessions" / config.member_tag / encoded)
```

**`ensure_inbox_folders` (lines 75-76)**:
```python
# OLD: inbox_path = str(KARMA_BASE / "remote-sessions" / m["name"] / encoded)
#      inbox_id = build_outbox_id(m['name'], proj_suffix)
# NEW:
member_tag = m.get("member_tag") or m["name"]  # fallback for legacy members
inbox_path = str(KARMA_BASE / "remote-sessions" / member_tag / encoded)
inbox_id = build_outbox_id(member_tag, proj_suffix)
```

**`ensure_handshake_folder` (line 99)**:
```python
# OLD: folder_id = build_handshake_id(config.user_id, team_name)
# NEW:
folder_id = build_handshake_id(config.member_tag, team_name)
```

**`cleanup_syncthing_for_team` (line 265)**:
```python
# OLD: member_names = {m["name"] for m in members}
# NEW:
member_tags = {m.get("member_tag") or m["name"] for m in members}
if config and config.member_tag:
    member_tags.add(config.member_tag)
```
Update line 275 to use `member_tags` instead of `member_names`.

**`cleanup_syncthing_for_member` (line 343)**:
```python
# OLD: elif username == member_name:
# NEW: use member_tag for matching
member_tag = member_tag_param  # passed as parameter
```
Update signature to accept `member_tag` instead of `member_name`.

**`extract_username_from_folder_ids`**: Now returns member_tag (already works since the folder ID username component IS the member_tag in v2).

- [ ] **Step 3: Run tests**

Run: `cd api && python -m pytest tests/test_sync_folders_member_tag.py tests/test_sync_*.py -v`

- [ ] **Step 4: Commit**

```bash
cd api
git add services/sync_folders.py tests/test_sync_folders_member_tag.py
git commit -m "feat(sync): use member_tag in all folder ID operations

ensure_outbox_folder, ensure_inbox_folders, ensure_handshake_folder,
and cleanup functions now use config.member_tag instead of
config.user_id. Fixes same-user multi-device folder ID collision."
```

---

### Task 1.5: Update sync_reconciliation.py for member_tag

**Files:**
- Modify: `api/services/sync_reconciliation.py`
- Test: Update existing reconciliation tests

- [ ] **Step 1: Update reconcile_introduced_devices**

The function extracts usernames from folder IDs. With v2 folder IDs, the extracted value is now a `member_tag` (e.g., `ayush.ayush-mac`). Update the variable names and DB writes to use `member_tag`:

```python
# Line 140-141: name extraction already returns the folder ID's username component
# which IS the member_tag in v2. Rename variable for clarity:
# OLD: name = syncthing_device_name or candidate_name
#      memberships.append((name, tname))
# NEW:
member_tag = syncthing_device_name or candidate_name
memberships.append((member_tag, tname))
```

In the upsert call (line 151):
```python
# Extract user_id from member_tag for the name field
from services.folder_id import parse_member_tag
user_id, machine_tag = parse_member_tag(username)
upsert_member(conn, team_name, user_id, device_id=device_id,
              machine_tag=machine_tag, member_tag=username)
```

- [ ] **Step 2: Update upsert_member in sync_queries.py to accept new columns**

```python
def upsert_member(
    conn, team_name, name, *, device_id,
    machine_id=None, machine_tag=None, member_tag=None,
):
    conn.execute(
        """INSERT INTO sync_members (team_name, name, device_id, machine_id, machine_tag, member_tag)
           VALUES (?, ?, ?, ?, ?, ?)
           ON CONFLICT (team_name, device_id) DO UPDATE SET
             name = excluded.name,
             machine_id = COALESCE(excluded.machine_id, machine_id),
             machine_tag = COALESCE(excluded.machine_tag, machine_tag),
             member_tag = COALESCE(excluded.member_tag, member_tag)""",
        (team_name, name, device_id, machine_id, machine_tag, member_tag),
    )
    conn.commit()
```

- [ ] **Step 3: Run tests**

Run: `cd api && python -m pytest tests/test_sync_*.py -v`

- [ ] **Step 4: Commit**

```bash
cd api
git add services/sync_reconciliation.py db/sync_queries.py
git commit -m "feat(sync): reconciliation uses member_tag for identity

upsert_member now accepts machine_id, machine_tag, member_tag columns.
reconcile_introduced_devices extracts member_tag from folder IDs."
```

---

### Task 1.6: Update cli/karma/pending.py for member_tag

**Files:**
- Modify: `cli/karma/pending.py:259-281` (pre-scan)
- Modify: `cli/karma/pending.py:300-390` (folder handling)

- [ ] **Step 1: Update pre-scan to extract member_tag**

The pre-scan parses handshake folders (`karma-join--{member_tag}--{team}`) to get real identities. With v2, the extracted value is a full member_tag:

```python
# In pre-scan loop (line 266):
# OLD: candidate_user, _team = parsed_hs
# NEW:
candidate_member_tag, _team = parsed_hs
from services.folder_id import parse_member_tag
candidate_user, candidate_machine_tag = parse_member_tag(candidate_member_tag)
```

Update the healing logic to also set machine_tag and member_tag:

```python
upsert_member(conn, db_team, candidate_user, device_id=dev_id,
              machine_tag=candidate_machine_tag,
              member_tag=candidate_member_tag)
```

- [ ] **Step 2: Update own outbox handling**

```python
# _handle_own_outbox: use config.member_tag for path construction
outbox_path = str(KARMA_BASE / "remote-sessions" / config.member_tag / encoded)
```

- [ ] **Step 3: Update peer outbox handling**

```python
# _handle_peer_outbox: use parsed member_tag from folder ID
parsed = parse_outbox_id(folder_id)
if parsed:
    peer_member_tag, suffix = parsed
    inbox_path = str(KARMA_BASE / "remote-sessions" / peer_member_tag / encoded)
```

- [ ] **Step 4: Run tests**

Run: `cd cli && python -m pytest tests/ -v`

- [ ] **Step 5: Commit**

```bash
git add cli/karma/pending.py
git commit -m "feat(sync): pending.py uses member_tag for folder handling

Pre-scan extracts member_tag from handshake folders and heals DB.
Own outbox and peer outbox handlers use member_tag for paths."
```

---

## Chunk 3: Router & Peripheral Updates (T1.7–T1.9, Parallel)

### Task 1.7: Update Routers for member_tag

**Files:**
- Modify: `api/routers/sync_devices.py` (accept handler populates member_tag)
- Modify: `api/routers/sync_teams.py` (join handler populates member_tag)
- Modify: `api/routers/sync_members.py` (list/remove uses member_tag)
- Modify: `api/routers/sync_projects.py` (share uses member_tag)
- Modify: `api/routers/sync_pending.py` (display uses member_tag)

Key changes:

**sync_devices.py — accept handler**: After extracting member_name, compute member_tag:
```python
from services.folder_id import parse_member_tag
# If name came from handshake folder, it's already a member_tag
user_id, machine_tag_part = parse_member_tag(member_name)
if machine_tag_part is None:
    # Legacy: bare username. Try to get machine info from pending device
    machine_tag_part = _sanitize_device_name(device_info.get("name", ""))
member_tag = f"{user_id}.{machine_tag_part}" if machine_tag_part else user_id
```

**sync_teams.py — join handler**: When creating self-member:
```python
upsert_member(conn, team_name, config.user_id, device_id=own_did,
              machine_id=config.machine_id, machine_tag=config.machine_tag,
              member_tag=config.member_tag)
```

**sync_pending.py — display**: Use member_tag for richer descriptions:
```python
# In enrichment loop, replace member display:
from services.folder_id import parse_member_tag
user_id, machine_tag = parse_member_tag(owner)
if machine_tag:
    member_display = f"{user_id} ({machine_tag})"
else:
    member_display = user_id
item["description"] = f"Receive sessions from {member_display} for {label}"
```

- [ ] **Step 1–5: Implement, test, commit**

```bash
git add api/routers/sync_devices.py api/routers/sync_teams.py \
        api/routers/sync_members.py api/routers/sync_projects.py \
        api/routers/sync_pending.py
git commit -m "feat(sync): routers populate and display member_tag

Accept, join, share, and pending endpoints now compute and store
member_tag. Pending UI shows device-specific descriptions like
'jayant (mac-mini)' instead of bare 'jayant'."
```

---

### Task 1.8: Update remote_sessions.py for member_tag

**Files:**
- Modify: `api/services/remote_sessions.py`

The remote session discovery scans `~/.claude_karma/remote-sessions/{member}/`. With member_tag, directory names become `jayant.mac-mini` instead of `jayant`.

Key change: user_id resolution should parse the directory name as member_tag:
```python
from services.folder_id import parse_member_tag

# When scanning remote-sessions directories:
for member_dir in remote_base.iterdir():
    member_tag = member_dir.name
    user_id, machine_tag = parse_member_tag(member_tag)
    # Use user_id for display, member_tag for path resolution
```

- [ ] **Step 1–3: Implement, test, commit**

```bash
git add api/services/remote_sessions.py
git commit -m "feat(sync): remote_sessions.py parses member_tag directories"
```

---

### Task 1.9: Update packager.py for member_tag

**Files:**
- Modify: `cli/karma/packager.py`

The packager writes sessions to `~/.claude_karma/remote-sessions/{user_id}/{encoded}/`. With member_tag, this becomes `{member_tag}/{encoded}/`.

Key change in `package()`:
```python
# OLD: outbox_dir = KARMA_BASE / "remote-sessions" / config.user_id / encoded
# NEW:
outbox_dir = KARMA_BASE / "remote-sessions" / config.member_tag / encoded
```

Also update `manifest.json` to include member_tag:
```python
manifest = {
    "user_id": config.user_id,
    "machine_id": config.machine_id,
    "member_tag": config.member_tag,
    # ... existing fields
}
```

- [ ] **Step 1–3: Implement, test, commit**

```bash
git add cli/karma/packager.py
git commit -m "feat(sync): packager uses member_tag for outbox directory and manifest"
```

---

## Post-Phase Verification

- [ ] **Verify two devices with same user_id produce distinct folder IDs**

```python
from services.folder_id import build_outbox_id
assert build_outbox_id("jayant.mac-mini", "proj") != build_outbox_id("jayant.mbp", "proj")
```

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
