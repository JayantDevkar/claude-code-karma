# Member Page Improvements Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix session visibility for remote members, switch to member_tag URLs, add sync health to member pages, and link team members tab to member detail pages.

**Architecture:** Normalize `remote_user_id` in the indexer to always store `member_tag` (schema v20 migration for existing data). Switch API member lookup from `device_id` to `member_tag` with strict regex fallback for device_id. Add `project_sync` data to profile response to eliminate N+1 API calls. Frontend route rename + session query fix + sync health UI.

**Tech Stack:** Python/FastAPI (backend), Svelte 5 (frontend), SQLite

**Spec:** `docs/superpowers/specs/2026-03-19-member-page-improvements-design.md`

---

### Task 1: Add `get_all_by_member_tag` to MemberRepository

**Files:**
- Modify: `api/repositories/member_repo.py`
- Test: `api/tests/test_repo_member.py`

- [ ] **Step 1: Write the failing test**

Add to `api/tests/test_repo_member.py`:

```python
class TestMemberRepoGetAllByMemberTag:
    def test_returns_members_across_teams(self, conn, repo):
        # Setup: two teams, same member_tag in both
        from repositories.team_repo import TeamRepository
        TeamRepository().save(conn, Team(name="t1", leader_device_id="D1", leader_member_tag="jay.mac"))
        TeamRepository().save(conn, Team(name="t2", leader_device_id="D1", leader_member_tag="jay.mac"))
        m1 = Member(team_name="t1", member_tag="jay.mac", device_id="D1", user_id="jay", machine_tag="mac")
        m2 = Member(team_name="t2", member_tag="jay.mac", device_id="D1", user_id="jay", machine_tag="mac")
        repo.save(conn, m1)
        repo.save(conn, m2)
        results = repo.get_all_by_member_tag(conn, "jay.mac")
        assert len(results) == 2
        assert {r.team_name for r in results} == {"t1", "t2"}

    def test_returns_empty_for_unknown_tag(self, conn, repo):
        assert repo.get_all_by_member_tag(conn, "nobody.nope") == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd api && python -m pytest tests/test_repo_member.py::TestMemberRepoGetAllByMemberTag -v`
Expected: FAIL — `AttributeError: 'MemberRepository' object has no attribute 'get_all_by_member_tag'`

- [ ] **Step 3: Implement the method**

Add to `api/repositories/member_repo.py` after `get_by_device`:

```python
    def get_all_by_member_tag(
        self, conn: sqlite3.Connection, member_tag: str
    ) -> list[Member]:
        rows = conn.execute(
            "SELECT * FROM sync_members WHERE member_tag = ?", (member_tag,)
        ).fetchall()
        return [self._row_to_member(r) for r in rows]

    def get_by_user_id(
        self, conn: sqlite3.Connection, user_id: str
    ) -> list[Member]:
        rows = conn.execute(
            "SELECT * FROM sync_members WHERE user_id = ?", (user_id,)
        ).fetchall()
        return [self._row_to_member(r) for r in rows]
```

- [ ] **Step 4: Run tests**

Run: `cd api && python -m pytest tests/test_repo_member.py -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
cd /Users/jayantdevkar/Documents/GitHub/claude-karma/.claude/worktrees/syncthing-sync-design
git add api/repositories/member_repo.py api/tests/test_repo_member.py
git commit -m "feat(sync): add get_all_by_member_tag and get_by_user_id to MemberRepository

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>"
```

---

### Task 2: Normalize `remote_user_id` in indexer + schema v20 migration

**Files:**
- Modify: `api/services/remote_sessions.py:298-387`
- Modify: `api/db/schema.py` (SCHEMA_VERSION + migration)
- Test: `api/tests/test_remote_user_id_normalization.py`

- [ ] **Step 1: Write the failing test**

Create `api/tests/test_remote_user_id_normalization.py`:

```python
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import json
import sqlite3
import pytest
from db.schema import ensure_schema
from domain.team import Team
from domain.member import Member, MemberStatus
from repositories.team_repo import TeamRepository
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
    TeamRepository().save(conn, Team(name="t1", leader_device_id="D1", leader_member_tag="jay.mac"))
    MemberRepository().save(conn, Member(
        team_name="t1", member_tag="jay.mac", device_id="D1",
        user_id="jay", machine_tag="mac", status=MemberStatus.ACTIVE,
    ))
    return conn


class TestResolveUserIdNormalization:
    def test_priority2_resolves_to_member_tag(self, seeded_conn, tmp_path):
        """When manifest has user_id but no device_id match, resolve to member_tag via DB."""
        from services.remote_sessions import _resolve_user_id
        # Clear cache
        from services.remote_sessions import _resolved_user_cache
        _resolved_user_cache.clear()

        user_dir = tmp_path / "jay"
        user_dir.mkdir()
        proj_dir = user_dir / "project1"
        proj_dir.mkdir()
        manifest = {"user_id": "jay"}  # No device_id
        (proj_dir / "manifest.json").write_text(json.dumps(manifest))

        result = _resolve_user_id(user_dir, conn=seeded_conn)
        assert result == "jay.mac"  # Should resolve to member_tag, not bare "jay"

    def test_priority3_resolves_dir_name_to_member_tag(self, seeded_conn, tmp_path):
        """When no manifest exists and dir_name is a bare user_id, resolve via DB."""
        from services.remote_sessions import _resolve_user_id
        from services.remote_sessions import _resolved_user_cache
        _resolved_user_cache.clear()

        user_dir = tmp_path / "jay"
        user_dir.mkdir()
        # No manifest — falls through to dir_name resolution

        result = _resolve_user_id(user_dir, conn=seeded_conn)
        assert result == "jay.mac"

    def test_unknown_user_id_stays_as_is(self, seeded_conn, tmp_path):
        """When user_id has no DB match, keep as-is."""
        from services.remote_sessions import _resolve_user_id
        from services.remote_sessions import _resolved_user_cache
        _resolved_user_cache.clear()

        user_dir = tmp_path / "unknown"
        user_dir.mkdir()
        proj_dir = user_dir / "project1"
        proj_dir.mkdir()
        manifest = {"user_id": "unknown"}
        (proj_dir / "manifest.json").write_text(json.dumps(manifest))

        result = _resolve_user_id(user_dir, conn=seeded_conn)
        assert result == "unknown"  # No DB match, stays as bare user_id


class TestV20Migration:
    def test_stale_remote_user_id_fixed(self, seeded_conn):
        """v20 migration SQL normalizes bare user_id to member_tag."""
        # Insert a session with stale remote_user_id = "jay" (bare user_id)
        seeded_conn.execute(
            "INSERT INTO sessions (uuid, project_encoded_name, jsonl_mtime, source, remote_user_id) "
            "VALUES ('s1', '-Users-me-repo', 1.0, 'remote', 'jay')"
        )
        seeded_conn.commit()

        # Run the v20 migration SQL directly (ensure_schema already ran,
        # so we test the migration logic independently)
        seeded_conn.execute("""
            UPDATE sessions SET remote_user_id = (
                SELECT m.member_tag FROM sync_members m
                WHERE m.user_id = sessions.remote_user_id
                LIMIT 1
            ) WHERE source = 'remote'
              AND remote_user_id IS NOT NULL
              AND remote_user_id NOT LIKE '%.%'
              AND EXISTS (
                  SELECT 1 FROM sync_members m
                  WHERE m.user_id = sessions.remote_user_id
              )
        """)
        seeded_conn.commit()

        row = seeded_conn.execute(
            "SELECT remote_user_id FROM sessions WHERE uuid = 's1'"
        ).fetchone()
        assert row[0] == "jay.mac"

    def test_already_normalized_not_touched(self, seeded_conn):
        """Sessions with member_tag format remote_user_id are left unchanged."""
        seeded_conn.execute(
            "INSERT INTO sessions (uuid, project_encoded_name, jsonl_mtime, source, remote_user_id) "
            "VALUES ('s2', '-Users-me-repo', 1.0, 'remote', 'jay.mac')"
        )
        seeded_conn.commit()

        seeded_conn.execute("""
            UPDATE sessions SET remote_user_id = (
                SELECT m.member_tag FROM sync_members m
                WHERE m.user_id = sessions.remote_user_id
                LIMIT 1
            ) WHERE source = 'remote'
              AND remote_user_id IS NOT NULL
              AND remote_user_id NOT LIKE '%.%'
              AND EXISTS (
                  SELECT 1 FROM sync_members m
                  WHERE m.user_id = sessions.remote_user_id
              )
        """)

        row = seeded_conn.execute(
            "SELECT remote_user_id FROM sessions WHERE uuid = 's2'"
        ).fetchone()
        assert row[0] == "jay.mac"  # unchanged
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd api && python -m pytest tests/test_remote_user_id_normalization.py -v`
Expected: FAIL — test_priority2 returns "jay" not "jay.mac"

- [ ] **Step 3: Fix `_resolve_user_id` in `api/services/remote_sessions.py`**

The key changes to `_resolve_user_id` (lines 298-387):

1. Add comment at top: `# NOTE: remote_user_id should always be member_tag format (e.g., "jay.mac"), not bare user_id.`

2. After Priority 2 (line 362-364), add DB normalization:

```python
                # Priority 2: manifest user_id (no DB match)
                if manifest_uid:
                    resolved = manifest_uid
                    # Normalize bare user_id to member_tag via DB
                    if conn is not None and "." not in manifest_uid:
                        try:
                            members = MemberRepository().get_by_user_id(conn, manifest_uid)
                            if members:
                                resolved = members[0].member_tag
                        except Exception:
                            pass
                break
```

3. **IMPORTANT**: Add a final normalization block BEFORE the cache write (line 386). Move the cache write after this block:

```python
    # Final normalization: if resolved is a bare user_id (no dot),
    # attempt to resolve to full member_tag via DB lookup.
    # This handles Priority 3 dir_name fallback and any other bare user_id.
    if conn is not None and "." not in resolved:
        try:
            from repositories.member_repo import MemberRepository
            members = MemberRepository().get_by_user_id(conn, resolved)
            if members:
                resolved = members[0].member_tag
        except Exception:
            pass

    # Cache the FINAL resolved value (after all normalization)
    _resolved_user_cache[dir_name] = (now, resolved)
    return resolved
```

This replaces the existing lines 386-387. The cache now stores the normalized value.

- [ ] **Step 4: Add v20 migration to `api/db/schema.py`**

Bump `SCHEMA_VERSION = 20` (line 13).

Add after the v19 migration block:

```python
        if current_version < 20:
            logger.info(
                "Migrating → v20: normalize remote_user_id from bare user_id to member_tag"
            )
            # Update sessions where remote_user_id is a bare user_id (no dot)
            # and a matching sync_members entry exists.
            conn.execute("""
                UPDATE sessions SET remote_user_id = (
                    SELECT m.member_tag FROM sync_members m
                    WHERE m.user_id = sessions.remote_user_id
                    LIMIT 1
                ) WHERE source = 'remote'
                  AND remote_user_id IS NOT NULL
                  AND remote_user_id NOT LIKE '%.%'
                  AND EXISTS (
                      SELECT 1 FROM sync_members m
                      WHERE m.user_id = sessions.remote_user_id
                  )
            """)
```

- [ ] **Step 5: Run tests**

Run: `cd api && python -m pytest tests/test_remote_user_id_normalization.py -v`
Expected: All PASS

- [ ] **Step 6: Run full test suite for regressions**

Run: `cd api && python -m pytest tests/ -v --timeout=30 -x`
Expected: All PASS

- [ ] **Step 7: Commit**

```bash
git add api/services/remote_sessions.py api/db/schema.py api/tests/test_remote_user_id_normalization.py api/repositories/member_repo.py
git commit -m "fix(sync): normalize remote_user_id to always store member_tag

_resolve_user_id() Priority 2/3 now resolves bare user_id to full
member_tag via DB lookup. Schema v20 migration fixes existing stale
values. This ensures MemberSessionsTab can query by member_tag reliably.

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>"
```

---

### Task 3: Switch member API endpoint from `device_id` to `identifier`

**Files:**
- Modify: `api/routers/sync_members.py:122-295`
- Test: `api/tests/test_member_identifier.py`

- [ ] **Step 1: Write the failing test**

Create `api/tests/test_member_identifier.py`:

```python
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import re
import pytest

# Test the identifier detection regex
DEVICE_ID_RE = re.compile(r"^[A-Z2-7]{7}(-[A-Z2-7]{7}){7}$")


class TestDeviceIdDetection:
    def test_real_device_id_matches(self):
        assert DEVICE_ID_RE.match("VRE7WLU-CXIVLS5-ARODGO7-22PNRQ3-7AAQ3ET-5CHXGA4-T5FKVKU-UM5QLQW")

    def test_member_tag_does_not_match(self):
        assert not DEVICE_ID_RE.match("jay.mac")

    def test_short_string_does_not_match(self):
        assert not DEVICE_ID_RE.match("ABCDEFG")

    def test_lowercase_does_not_match(self):
        assert not DEVICE_ID_RE.match("vre7wlu-cxivls5-arodgo7-22pnrq3-7aaq3et-5chxga4-t5fkvku-um5qlqw")
```

- [ ] **Step 2: Run test to verify it passes** (regex is standalone)

Run: `cd api && python -m pytest tests/test_member_identifier.py -v`
Expected: All PASS

- [ ] **Step 3: Refactor `get_member_profile` endpoint**

In `api/routers/sync_members.py`, add the regex constant near the top:

```python
import re

DEVICE_ID_RE = re.compile(r"^[A-Z2-7]{7}(-[A-Z2-7]{7}){7}$")
```

Change the endpoint signature and lookup logic (lines 122-150):

```python
@router.get("/members/{identifier}")
async def get_member_profile(
    identifier: str,
    conn: sqlite3.Connection = Depends(get_conn),
    config=Depends(get_optional_config),
):
    """Full member profile. Accepts member_tag or device_id (auto-detected)."""
    if not identifier or not identifier.strip():
        raise HTTPException(400, "identifier must not be empty")
    repos = make_repos()

    # Detect format: Syncthing device_id vs member_tag
    if DEVICE_ID_RE.match(identifier):
        memberships = repos["members"].get_by_device(conn, identifier)
    else:
        memberships = repos["members"].get_all_by_member_tag(conn, identifier)

    # Fallback for self: config device_id → member_tag
    if not memberships and config:
        my_did = (
            config.syncthing.device_id
            if getattr(config, "syncthing", None)
            else None
        )
        if config.member_tag:
            if identifier == my_did or identifier == config.member_tag:
                teams = repos["teams"].list_all(conn)
                for t in teams:
                    m = repos["members"].get(conn, t.name, config.member_tag)
                    if m:
                        memberships.append(m)

    if not memberships:
        raise HTTPException(404, f"Member '{identifier}' not found")
```

- [ ] **Step 4: Add new fields to the profile response**

After the stats computation (around line 280), add the new fields before building the final response dict:

```python
    # New fields: member_tag, machine_tag, unsynced_count, last_packaged_at,
    # sync_direction, project_sync
    from routers.sync_teams import _get_active_counts, _count_packaged

    unsynced_count = None
    last_packaged_at = None
    project_sync = None
    sync_direction_val = None

    if is_you:
        # Compute per-project sync data (eliminates N+1 API calls from frontend)
        active_counts = _get_active_counts()
        project_sync_list = []
        total_gap = 0
        for m in memberships:
            team_projects = repos["projects"].list_for_team(conn, m.team_name)
            for p in team_projects:
                if p.status.value != "shared":
                    continue
                enc, display = _resolve_project(conn, p.git_identity)
                local_count = 0
                if enc:
                    row = conn.execute(
                        "SELECT COUNT(*) FROM sessions WHERE project_encoded_name = ? AND (source IS NULL OR source != 'remote')",
                        (enc,),
                    ).fetchone()
                    local_count = row[0] if row else 0
                packaged_count = _count_packaged(member_tag, p.folder_suffix)
                active_count = active_counts.get(enc, 0) if enc else 0
                gap = max(0, local_count - packaged_count - active_count)
                total_gap += gap
                project_sync_list.append({
                    "team_name": m.team_name,
                    "git_identity": p.git_identity,
                    "encoded_name": enc,
                    "name": display or p.git_identity,
                    "local_count": local_count,
                    "packaged_count": packaged_count,
                    "active_count": active_count,
                    "gap": gap,
                })
        unsynced_count = total_gap
        project_sync = project_sync_list

        # last_packaged_at — all session_packaged events are from self
        lp_row = conn.execute(
            "SELECT MAX(created_at) FROM sync_events WHERE event_type = 'session_packaged'"
        ).fetchone()
        last_packaged_at = lp_row[0] if lp_row and lp_row[0] else None

    # sync_direction: aggregate from accepted subscriptions
    subs = repos["subs"].list_for_member(conn, member_tag)
    accepted_dirs = {s.direction.value for s in subs if s.status.value == "accepted"}
    if len(accepted_dirs) == 0:
        sync_direction_val = None
    elif len(accepted_dirs) == 1:
        sync_direction_val = next(iter(accepted_dirs))
    else:
        sync_direction_val = "mixed"
```

Then add these to the return dict (after existing fields):

```python
    return {
        "member_tag": member_tag,
        "user_id": user_id,
        "machine_tag": memberships[0].machine_tag,
        "device_id": device_id or "",
        # ... existing fields ...
        "unsynced_count": unsynced_count,
        "last_packaged_at": last_packaged_at,
        "sync_direction": sync_direction_val,
        "project_sync": project_sync,
    }
```

- [ ] **Step 5: Update `list_members` to include `member_tag` and `machine_tag`**

In the listing endpoint response builder (lines 104-112), add `member_tag` and `machine_tag`:

```python
        result.append({
            "name": entry["name"],
            "member_tag": tag,
            "machine_tag": entry.get("_machine_tag", ""),
            "device_id": did or "",
            # ... rest unchanged
        })
```

Also store `_machine_tag` when building `members_by_tag` (line 87-93):

```python
            else:
                members_by_tag[tag] = {
                    "name": m.user_id,
                    "device_id": m.device_id or (my_device_id if tag == my_member_tag else m.device_id),
                    "teams": [t.name],
                    "_added_at": m.added_at,
                    "_member_tag": tag,
                    "_machine_tag": m.machine_tag,
                }
```

- [ ] **Step 6: Add member creation collision guard**

In the add-member / join endpoint (find the function that creates new members — likely in `team_service.py` or `sync_members.py`), add a check before saving:

```python
# Collision guard: reject if member_tag already registered to a different device
existing = repos["members"].get_all_by_member_tag(conn, new_member_tag)
for e in existing:
    if e.device_id and e.device_id != new_device_id:
        raise HTTPException(409, f"member_tag '{new_member_tag}' already registered to a different device")
```

- [ ] **Step 7: Update activity and settings endpoint signatures**

In `sync_members.py`, find the activity endpoint (`GET /sync/members/{device_id}/activity`) and settings endpoints. Apply the same identifier resolution pattern:

```python
@router.get("/members/{identifier}/activity")
async def get_member_activity(
    identifier: str,
    # ... existing params ...
):
    # Resolve identifier to member_tag
    if DEVICE_ID_RE.match(identifier):
        memberships = repos["members"].get_by_device(conn, identifier)
    else:
        memberships = repos["members"].get_all_by_member_tag(conn, identifier)
    if not memberships:
        raise HTTPException(404, f"Member '{identifier}' not found")
    member_tag = memberships[0].member_tag
    # ... rest of function uses member_tag ...
```

Apply the same change to `GET /sync/teams/{team}/members/{identifier}/settings` and `PATCH /sync/teams/{team}/members/{identifier}/settings`.

- [ ] **Step 7: Run tests**

Run: `cd api && python -m pytest tests/test_member_identifier.py tests/test_packaging_service.py tests/test_project_status_gap.py -v`
Expected: All PASS

- [ ] **Step 8: Commit**

```bash
git add api/routers/sync_members.py api/tests/test_member_identifier.py
git commit -m "feat(sync): switch member API from device_id to member_tag identifier

Auto-detects Syncthing device_id via strict base32 regex, falls back to
member_tag lookup. Adds member_tag, machine_tag, unsynced_count,
last_packaged_at, sync_direction, project_sync to profile response.
List endpoint now includes member_tag and machine_tag.

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>"
```

---

### Task 4: Update frontend TypeScript types

**Files:**
- Modify: `frontend/src/lib/api-types.ts`

- [ ] **Step 1: Update MemberProfile interface**

Find the `MemberProfile` interface in `api-types.ts` and add the new fields:

```typescript
export interface MemberProfile {
    // ... existing fields ...
    member_tag: string;
    machine_tag: string;
    unsynced_count: number | null;
    last_packaged_at: string | null;
    sync_direction: 'both' | 'send' | 'receive' | 'mixed' | null;
    project_sync: MemberProjectSync[] | null;
}

export interface MemberProjectSync {
    team_name: string;
    git_identity: string;
    encoded_name: string | null;
    name: string;
    local_count: number;
    packaged_count: number;
    active_count: number;
    gap: number;
}
```

Also update the member listing item type to include `member_tag` and `machine_tag`.

- [ ] **Step 2: Run type check**

Run: `cd frontend && npm run check`
Expected: May have errors in components that reference old fields — note them for next tasks.

- [ ] **Step 3: Commit**

```bash
cd /Users/jayantdevkar/Documents/GitHub/claude-karma/.claude/worktrees/syncthing-sync-design
git add frontend/src/lib/api-types.ts
git commit -m "feat(sync): add member_tag, project_sync, sync health fields to MemberProfile type

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>"
```

---

### Task 5: Rename frontend route from `[device_id]` to `[member_tag]`

**Files:**
- Rename: `frontend/src/routes/members/[device_id]/` → `frontend/src/routes/members/[member_tag]/`
- Modify: `frontend/src/routes/members/[member_tag]/+page.server.ts`
- Modify: `frontend/src/routes/members/[member_tag]/+page.svelte`
- Modify: `frontend/src/routes/members/+page.svelte`

- [ ] **Step 1: Rename the route directory**

```bash
cd /Users/jayantdevkar/Documents/GitHub/claude-karma/.claude/worktrees/syncthing-sync-design
git mv frontend/src/routes/members/\[device_id\] frontend/src/routes/members/\[member_tag\]
```

- [ ] **Step 2: Update `+page.server.ts`**

Change `params.device_id` to `params.member_tag` and update the API call:

```typescript
export const load: PageServerLoad = async ({ fetch, params }) => {
    const memberTag = params.member_tag;

    const profileResult = await safeFetch<MemberProfile>(
        fetch,
        `${API_BASE}/sync/members/${encodeURIComponent(memberTag)}`
    );

    return {
        memberTag,
        profile: profileResult.ok ? profileResult.data : null,
        error: profileResult.ok ? null : profileResult.message
    };
};
```

- [ ] **Step 3: Update `+page.svelte`**

Update all references from `data.deviceId` to `data.memberTag`. Update breadcrumbs to show member_tag.

- [ ] **Step 4: Update MemberListItem interface in `+page.server.ts`**

In `frontend/src/routes/members/+page.server.ts`, the `MemberListItem` interface needs `member_tag` and `machine_tag` fields added to match the updated API response:

```typescript
interface MemberListItem {
    name: string;
    member_tag: string;
    machine_tag: string;
    device_id: string;
    connected: boolean;
    is_you: boolean;
    team_count: number;
    teams: string[];
    added_at: string;
}
```

- [ ] **Step 5: Update members listing page**

In `frontend/src/routes/members/+page.svelte`, change card links from `/members/{member.device_id}` to `/members/{member.member_tag}`. Change `{#each}` key from `member.device_id` to `member.member_tag`.

- [ ] **Step 5: Run type check**

Run: `cd frontend && npm run check`
Expected: 0 errors

- [ ] **Step 6: Commit**

```bash
git add -A frontend/src/routes/members/
git commit -m "feat(sync): rename member route from [device_id] to [member_tag]

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>"
```

---

### Task 6: Fix MemberSessionsTab — use member_tag for remote query

**Files:**
- Modify: `frontend/src/lib/components/team/MemberSessionsTab.svelte:117`

- [ ] **Step 1: Fix the session query**

In `MemberSessionsTab.svelte`, line 117, change:

```typescript
// Before:
params.set('user', profile.user_id);

// After:
params.set('user', profile.member_tag);
```

This is the one-line fix that makes remote sessions visible. It works because Task 2 normalized `remote_user_id` to always store `member_tag`.

- [ ] **Step 2: Run type check**

Run: `cd frontend && npm run check`
Expected: 0 errors

- [ ] **Step 3: Commit**

```bash
cd /Users/jayantdevkar/Documents/GitHub/claude-karma/.claude/worktrees/syncthing-sync-design
git add frontend/src/lib/components/team/MemberSessionsTab.svelte
git commit -m "fix(sync): use member_tag instead of user_id for remote session query

Fixes sessions not showing up for remote members. The remote_user_id
column stores member_tag (e.g., 'jay.mac'), not bare user_id ('jay').

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>"
```

---

### Task 7: Add clickable navigation from TeamMembersTab to member pages

**Files:**
- Modify: `frontend/src/lib/components/team/TeamMembersTab.svelte`

- [ ] **Step 1: Read the current component**

Read `TeamMembersTab.svelte` to understand the current card template structure and variable names.

- [ ] **Step 2: Make member name a link**

Find the member name display element and wrap it in an `<a>` tag:

```svelte
<a
    href="/members/{member.member_tag}"
    class="text-sm font-semibold text-[var(--text-primary)] hover:text-[var(--member-color,var(--accent))] transition-colors"
    style="--member-color: {getTeamMemberHexColor(member.user_id)}"
>
    {member.user_id}
</a>
```

- [ ] **Step 3: Make avatar clickable**

Wrap the avatar div in an `<a>` tag with the same href. Add hover ring effect:

```svelte
<a href="/members/{member.member_tag}" class="shrink-0">
    <!-- existing avatar div, add hover ring -->
</a>
```

- [ ] **Step 4: Import getTeamMemberHexColor if not already imported**

```typescript
import { getTeamMemberHexColor } from '$lib/utils';
```

- [ ] **Step 5: Run type check**

Run: `cd frontend && npm run check`
Expected: 0 errors

- [ ] **Step 6: Commit**

```bash
cd /Users/jayantdevkar/Documents/GitHub/claude-karma/.claude/worktrees/syncthing-sync-design
git add frontend/src/lib/components/team/TeamMembersTab.svelte
git commit -m "feat(sync): add clickable navigation from team members tab to member pages

Name and avatar link to /members/{member_tag} with member-colored hover.

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>"
```

---

### Task 8: Update member detail page header with sync health metadata

**Files:**
- Modify: `frontend/src/routes/members/[member_tag]/+page.svelte`

- [ ] **Step 1: Read the current header section**

Understand the current PageHeader usage and metadata items.

- [ ] **Step 2: Update header metadata**

Replace the current metadata items (device ID, throughput, last active) with:

```svelte
{@const metadataItems = [
    { icon: Tag, text: profile.member_tag },
    { icon: Monitor, text: `Machine: ${profile.machine_tag}` },
    { icon: Users, text: `${profile.teams.length} team${profile.teams.length !== 1 ? 's' : ''}` },
]}
```

For self (`is_you`), add sync health items:

```svelte
{#if profile.is_you && profile.unsynced_count != null}
    <!-- Unsynced count -->
    <span class="text-xs {profile.unsynced_count > 0 ? 'text-[var(--warning)]' : 'text-[var(--success)]'}">
        {profile.unsynced_count > 0 ? `${profile.unsynced_count} unsynced` : 'All synced'}
    </span>
{/if}
{#if profile.sync_direction}
    <span class="text-xs text-[var(--text-muted)]">Direction: {profile.sync_direction}</span>
{/if}
{#if profile.last_packaged_at}
    <span class="text-xs text-[var(--text-muted)]">Last synced: {formatRelativeTime(profile.last_packaged_at)}</span>
{/if}
```

- [ ] **Step 3: Run type check**

Run: `cd frontend && npm run check`
Expected: 0 errors

- [ ] **Step 4: Commit**

```bash
cd /Users/jayantdevkar/Documents/GitHub/claude-karma/.claude/worktrees/syncthing-sync-design
git add frontend/src/routes/members/\[member_tag\]/+page.svelte
git commit -m "feat(sync): update member page header with sync health metadata

Shows member_tag, machine, team count, unsynced count, sync direction,
and last synced time. Unsynced highlighted in warning color when > 0.

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>"
```

---

### Task 9: Add Sync Health card and Unsynced stat to MemberOverviewTab

**Files:**
- Modify: `frontend/src/lib/components/team/MemberOverviewTab.svelte`

- [ ] **Step 1: Read the current overview tab**

Understand the stats row and existing cards.

- [ ] **Step 2: Add Unsynced stat card**

In the stats row (4th card), add:

```svelte
{#if profile.is_you}
    <div class="rounded-[var(--radius-lg)] border border-[var(--border)] bg-[var(--bg-subtle)] p-4 text-center">
        <span class="text-lg font-semibold {(profile.unsynced_count ?? 0) > 0 ? 'text-[var(--warning)]' : 'text-[var(--text-primary)]'}">
            {profile.unsynced_count ?? 0}
        </span>
        <p class="text-[11px] text-[var(--text-muted)] mt-1">Unsynced</p>
    </div>
{:else}
    <div class="rounded-[var(--radius-lg)] border border-[var(--border)] bg-[var(--bg-subtle)] p-4 text-center">
        <span class="text-lg font-semibold text-[var(--text-primary)]">{profile.stats.total_projects}</span>
        <p class="text-[11px] text-[var(--text-muted)] mt-1">Projects</p>
    </div>
{/if}
```

- [ ] **Step 3: Add Sync Health card (self only)**

After the stats row, before the activity chart:

```svelte
{#if profile.is_you && profile.project_sync}
    <div class="rounded-[var(--radius-lg)] border border-[var(--border)] bg-[var(--bg-subtle)]">
        <div class="flex items-center justify-between px-5 py-3.5 border-b border-[var(--border-subtle)]">
            <h3 class="text-sm font-semibold text-[var(--text-primary)]">Sync Health</h3>
            <button
                onclick={syncNow}
                disabled={syncing}
                class="flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded-[var(--radius)] bg-[var(--accent)] text-white hover:bg-[var(--accent-hover)] transition-colors disabled:opacity-50"
            >
                {#if syncing}
                    <Loader2 size={12} class="animate-spin" />
                    Syncing...
                {:else}
                    <RefreshCw size={12} />
                    Sync Now
                {/if}
            </button>
        </div>
        <div class="px-5 divide-y divide-[var(--border-subtle)]">
            {#each profile.project_sync as ps (ps.git_identity)}
                <div class="flex items-center gap-3 py-3">
                    <span class="text-sm text-[var(--text-primary)] flex-1 truncate">{ps.name}</span>
                    <span class="text-xs text-[var(--text-muted)]">{ps.packaged_count}/{ps.local_count} packaged</span>
                    {#if ps.gap === 0}
                        <span class="px-2 py-0.5 text-[10px] rounded-full bg-[var(--success)]/10 text-[var(--success)] border border-[var(--success)]/20">In Sync</span>
                    {:else}
                        <span class="px-2 py-0.5 text-[10px] rounded-full bg-[var(--warning)]/10 text-[var(--warning)] border border-[var(--warning)]/20">{ps.gap} ready</span>
                    {/if}
                </div>
            {/each}
        </div>
    </div>
{/if}
```

Add the sync function and state:

```typescript
import { RefreshCw, Loader2 } from 'lucide-svelte';
import { API_BASE } from '$lib/config';
import { invalidateAll } from '$app/navigation';

let syncing = $state(false);

async function syncNow() {
    syncing = true;
    try {
        await fetch(`${API_BASE}/sync/package`, { method: 'POST' }).catch(() => null);
        // Re-fetch page data (profile) via SvelteKit's invalidation
        await invalidateAll();
    } finally {
        syncing = false;
    }
}
```

- [ ] **Step 4: Add "Sessions from {name}" card for remote members**

```svelte
{#if !profile.is_you}
    <div class="rounded-[var(--radius-lg)] border border-[var(--border)] bg-[var(--bg-subtle)]">
        <div class="px-5 py-3.5 border-b border-[var(--border-subtle)]">
            <h3 class="text-sm font-semibold text-[var(--text-primary)]">Sessions from {profile.user_id}</h3>
        </div>
        <div class="px-5 divide-y divide-[var(--border-subtle)]">
            {#each profile.teams as team (team.name)}
                {#each team.projects as proj (proj.encoded_name)}
                    <div class="flex items-center justify-between py-3">
                        <span class="text-sm text-[var(--text-primary)]">{proj.name}</span>
                        <span class="text-xs text-[var(--text-muted)]">{proj.session_count} sessions</span>
                    </div>
                {/each}
            {/each}
        </div>
    </div>
{/if}
```

- [ ] **Step 5: Run type check**

Run: `cd frontend && npm run check`
Expected: 0 errors

- [ ] **Step 6: Commit**

```bash
cd /Users/jayantdevkar/Documents/GitHub/claude-karma/.claude/worktrees/syncthing-sync-design
git add frontend/src/lib/components/team/MemberOverviewTab.svelte
git commit -m "feat(sync): add Sync Health card and unsynced stat to member overview

Self view: Unsynced stat card + per-project Sync Health with Sync Now button.
Remote view: Sessions from {name} summary with per-project counts.

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>"
```

---

### Task 10: Final verification

- [ ] **Step 1: Run all backend tests**

Run: `cd api && python -m pytest tests/ -v --timeout=30`
Expected: All tests PASS

- [ ] **Step 2: Run frontend type check**

Run: `cd frontend && npm run check`
Expected: 0 errors

- [ ] **Step 3: Manual E2E test**

1. Start API + frontend
2. Navigate to `/members` → verify cards link to `/members/{member_tag}`
3. Click a member → verify breadcrumbs, header metadata, sessions tab works
4. Check self view: Unsynced stat, Sync Health card, Sync Now button
5. Check remote member: Sessions from {name} card
6. Navigate to `/team/{name}` → Members tab → click name → verify navigation
7. Verify member colors are consistent across all views

- [ ] **Step 4: Commit any fixups**

```bash
git add -A
git commit -m "chore(sync): member page improvements — final cleanup

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>"
```
