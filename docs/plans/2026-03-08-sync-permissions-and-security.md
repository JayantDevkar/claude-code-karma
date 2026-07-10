# Sync Permissions, Security & Activity — Design Document

**Date:** 2026-03-08
**Status:** Draft
**Branch:** `worktree-syncthing-sync-design`

## Problem Statement

The current sync handshake flow auto-accepts everything once a join code is used.
Users have no control over:
1. Which projects they share when joining a team
2. Whether to accept incoming project shares from teammates
3. What files are received (no validation)

Activity logging exists but is incomplete — some events lack team/member context,
making it impossible to show a useful team-scoped activity feed.

## Design Principles

1. **Explicit sharing, automatic receiving** — You choose what to SEND. You auto-receive from trusted teammates (with validation).
2. **Join code = device trust, not data trust** — The join code pairs devices and creates membership. It does NOT auto-share your sessions.
3. **Team-scoped everything** — All events, approvals, and activity tied to a team.
4. **Validate at the boundary** — Every file from a remote peer is validated before indexing.
5. **Log everything the user cares about** — Every meaningful state change creates an activity event.

## Trust Model

```
Level 0: Anonymous       — Unknown device, rejected
Level 1: Device trust    — Join code exchanged, Syncthing paired (automatic)
Level 2: Team membership — Member added to team DB (automatic via join code)
Level 3: Project sharing — User explicitly shares project with team (REQUIRES USER ACTION)
Level 4: Session sync    — Files flow between paired folders (automatic, with validation)
```

Key insight: Levels 1-2 are automatic (the join code IS the consent).
Level 3 requires explicit user action. Level 4 is automatic but validated.

## Flow Redesign

### Scenario 1: Bob Joins Alice's Team

#### Step 1: Join (automatic — levels 1-2)

Bob pastes `acme:alice:DEVICE-ID` into JoinTeamDialog.

**API: `POST /sync/teams/join`** (CHANGED)

What it does now:
- Parse join code ✓
- Create team locally ✓
- Add self + leader as members ✓
- Pair device in Syncthing ✓
- Create handshake folder ✓

What it NO LONGER does:
- ~~Auto-create outbox/inbox folders~~
- ~~Auto-add matching local projects~~
- ~~Auto-accept pending folders~~

What it NOW returns:

```json
{
  "ok": true,
  "team_name": "acme",
  "team_created": true,
  "leader_name": "alice",
  "paired": true,
  "matching_projects": [
    {
      "encoded_name": "-Users-bob-work-acme-app",
      "path": "/Users/bob/work/acme-app",
      "git_identity": "alice/acme-app",
      "session_count": 42
    }
  ]
}
```

The `matching_projects` list shows local projects whose `git_identity` matches
a project already shared in the team. This is a SUGGESTION, not an auto-share.

#### Step 2: Share Projects (explicit — level 3)

**UX: JoinTeamDialog success state** (CHANGED)

After successful join, the dialog shows:

```
┌─────────────────────────────────────────────┐
│  ✓ Joined team "acme"                       │
│                                             │
│  Connected with alice (pairing active)      │
│                                             │
│  These local projects match the team:       │
│  ┌─────────────────────────────────────┐    │
│  │ ☑ acme-app                          │    │
│  │   /Users/bob/work/acme-app          │    │
│  │   42 sessions                       │    │
│  └─────────────────────────────────────┘    │
│                                             │
│  [ Share Selected ]  [ Skip for Now ]       │
│                                             │
│  You can always share projects later from   │
│  the team page.                             │
└─────────────────────────────────────────────┘
```

"Share Selected" calls existing `POST /sync/teams/{name}/projects` for each
selected project, which creates outbox + inbox folders.

"Skip for Now" navigates to team detail page without sharing anything.

#### Step 3: Receive (automatic — level 4, with validation)

Once Bob has shared at least one project, Syncthing folders are live.
Alice's watcher packages sessions → Syncthing syncs → Bob's inbox receives.

The receive path validates files before indexing (see Security section).

#### Step 4: Alice discovers Bob (automatic)

On Alice's machine, `/sync/pending-devices` poll triggers `_auto_accept_pending_peers()`:
1. Sees Bob's device as pending
2. Matches via karma-join-bob-acme handshake folder → team=acme, username=bob
3. Auto-accepts device, adds as member ✓
4. Auto-creates inbox for Bob's outbox (to RECEIVE Bob's sessions) ✓
5. Adds Bob's device to Alice's existing outbox folders (so Bob receives Alice's sessions) ✓
6. Logs: `member_auto_accepted`, `folders_shared`

This is fine because Alice already shared her projects with the team.
Adding a new member just extends the share — the team-level consent covers it.

### Scenario 2: Project Present on Both Members

Alice has `acme-app`, Bob has `acme-app` (same git_identity).

1. Bob joins team → sees `acme-app` in `matching_projects`
2. Bob checks the box and clicks "Share Selected"
3. API creates Bob's outbox for `acme-app` (sendonly → Alice)
4. API creates inbox for Alice's outbox (receiveonly ← Alice)
5. Sessions flow both ways

**Key change**: Bob CHOSE to share. Previously this was automatic.

### Scenario 3: Only the Sharer Has the Project

Alice shares `acme-app`. Bob joins but doesn't have this project locally.

1. Bob joins → `matching_projects` is empty (no local git_identity match)
2. Bob clicks "Skip for Now" or shares different projects
3. Alice's auto-accept creates inbox for Bob (empty, ready for when Bob starts working)
4. Meanwhile: Bob receives Alice's sessions via inbox
5. Bob can see Alice's `acme-app` sessions in remote sessions view
6. If Bob later clones the repo: next time they visit team page, a banner shows
   "You have a local project matching acme-app — share it?"

### Scenario 4: New Member Joins, 1+ Projects Already Shared

Team `acme` has Alice + Carol sharing `acme-app` and `acme-api`. Dave joins.

1. Dave pastes join code → paired with Alice (code issuer)
2. `matching_projects` shows which of Dave's local projects match
3. Dave selects and shares
4. Alice's pending-devices poll: auto-accepts Dave, creates inbox for Dave, adds Dave to existing outboxes
5. **Carol's discovery**: Next poll of `/sync/pending-devices` on Carol's machine:
   - Carol's watcher triggers a pending check (NEW — see Watcher Enhancement below)
   - `_auto_accept_pending_peers()` finds Dave's device
   - Matches via handshake folder or join-code trust
   - Creates inbox for Dave, adds Dave to Carol's outboxes
   - Log: `member_auto_accepted(dave)` on Carol's machine

**Watcher Enhancement** (addresses Carol discovery delay):

```python
# watcher.py — add periodic pending check
class SessionWatcher:
    PENDING_CHECK_INTERVAL = 300  # 5 minutes

    async def _check_pending_peers(self):
        """Periodically check for new team members."""
        # Calls _auto_accept_pending_peers() via API
        # This ensures all running watchers discover new members
        # even without the frontend being open
```

### Scenario 5: Member Removal (currently broken)

Alice removes Bob from team `acme`.

**Current**: DB row deleted, Syncthing folders remain, sync continues.

**Fixed flow**:

```python
# sync_status.py — remove_member endpoint (CHANGED)
async def sync_remove_member(team_name, device_id):
    # 1. Remove from DB
    remove_member(conn, team_name, device_id)

    # 2. Remove device from all team's Syncthing folders
    projects = list_team_projects(conn, team_name)
    for proj in projects:
        suffix = _compute_proj_suffix(...)
        # Remove from my outbox device list
        proxy.remove_device_from_folder(f"karma-out-{config.user_id}-{suffix}", device_id)
        # Remove their inbox folder entirely
        proxy.remove_folder(f"karma-out-{member_name}-{suffix}")

    # 3. Remove handshake folder
    proxy.remove_folder(f"karma-join-{member_name}-{team_name}")

    # 4. Optionally remove device from Syncthing entirely
    # (only if device is not in any other team)
    other_teams = [m for m in get_all_memberships(conn, device_id) if m != team_name]
    if not other_teams:
        proxy.remove_device(device_id)

    # 5. Log
    log_event(conn, "member_removed", team_name=team_name, member_name=member_name)
```

### Scenario 6: Re-joining (idempotent)

Bob uses the join code again. Everything is idempotent:
- `upsert_member` → ON CONFLICT DO UPDATE ✓
- Handshake folder → already exists ✓
- `matching_projects` returned again for re-selection ✓
- No duplicate folders created ✓

## Activity Logging Redesign

### Schema Change

```sql
-- No new table needed. Fix the existing sync_events usage:

-- ALL events MUST have team_name (enforce in code, not schema — keep nullable for migration)
-- ALL member-related events MUST have member_name
-- detail JSON gets structured sub-fields
```

### Event Types (Revised)

| Event Type | team_name | member_name | project | detail |
|-----------|-----------|-------------|---------|--------|
| `team_created` | ✓ required | creator | - | `{join_code: "..."}` |
| `team_deleted` | ✓ required | deleter | - | - |
| `member_joined` (NEW) | ✓ | joiner | - | `{via: "join_code"}` |
| `member_auto_accepted` | ✓ | accepted member | - | `{strategy: "handshake"\|"join_code_trust"}` |
| `member_removed` | ✓ | removed member | - | `{removed_by: "self"\|"alice"}` |
| `project_shared` (NEW) | ✓ | sharer | ✓ | `{session_count: N}` |
| `project_removed` | ✓ | remover | ✓ | - |
| `folders_shared` | ✓ | for_member | - | `{outboxes: N, inboxes: N}` |
| `pending_accepted` | ✓ required | from_member | ✓ optional | `{count: N, folders: [...]}` |
| `session_packaged` | ✓ | packager | ✓ | `{uuid: "...", size_bytes: N}` |
| `session_received` | ✓ | from_member | ✓ | `{uuid: "...", size_bytes: N}` |
| `file_rejected` (NEW) | ✓ | from_member | ✓ | `{reason: "...", file: "..."}` |
| `sync_now` | ✓ | triggerer | ✓ optional | - |
| `watcher_started` | ✓ | - | - | - |
| `watcher_stopped` | ✓ | - | - | - |

### Activity API Changes

```python
# GET /sync/activity — UNCHANGED (already supports team_name filter)
# But now ALL events have team_name, so team filter always works

# NEW: GET /sync/teams/{team_name}/activity — convenience alias
@router.get("/teams/{team_name}/activity")
async def sync_team_activity(team_name: str, limit: int = 50, offset: int = 0):
    """Team-scoped activity feed for the team detail page."""
    # Same as /sync/activity?team_name=X but validates team exists
```

### Frontend: Team Activity Section

**Location: `/team/[name]` page** (team detail)

Add an "Activity" section below the existing sections:

```
┌─────────────────────────────────────────────────────┐
│  Activity                              [Filter ▾]   │
│─────────────────────────────────────────────────────│
│  ● bob shared acme-app (42 sessions)    2m ago     │
│  ● bob joined the team via join code    5m ago     │
│  ● alice shared acme-api (18 sessions)  1h ago     │
│  ● carol was auto-accepted as member    1h ago     │
│  ● alice created team acme              2h ago     │
│                                                     │
│  [ Load More ]                                      │
└─────────────────────────────────────────────────────┘
```

Each event type gets:
- An icon (user+ for joins, folder for shares, sync for sessions, shield for rejections)
- Human-readable description
- Relative timestamp
- Color coding (green for positive, yellow for warnings, red for rejections)

**Location: `/sync` overview page** — keep the global activity feed (all teams).

## Disk Space & Session Limits

### Rule

```
FREE DISK >= 10 GiB  →  sync per user's setting (default: all)
FREE DISK <  10 GiB  →  force "recent 100" regardless of setting
```

### User Setting

Stored per team in `sync_teams.sync_session_limit`:

| Value | Behavior |
|-------|----------|
| `all` (default) | Sync every session for shared projects |
| `recent_100` | Only the 100 most recent sessions per project |
| `recent_10` | Only the 10 most recent sessions per project |

### Schema Change

```sql
-- Migration v23
ALTER TABLE sync_teams ADD COLUMN sync_session_limit TEXT DEFAULT 'all';
```

### API

```python
# PATCH /sync/teams/{team_name}/settings
class UpdateTeamSettingsRequest(BaseModel):
    sync_session_limit: Literal["all", "recent_100", "recent_10"]
```

### Packager Logic

```python
import shutil

MIN_FREE_BYTES = 10 * 1024 * 1024 * 1024  # 10 GiB

def _get_session_limit(team_session_limit: str, dest_path: Path) -> int | None:
    """Return max sessions to package, or None for unlimited.

    If disk has < 10 GiB free, force recent 100 regardless of setting.
    """
    free = shutil.disk_usage(dest_path).free
    if free < MIN_FREE_BYTES:
        return 100  # safety cap

    limits = {"all": None, "recent_100": 100, "recent_10": 10}
    return limits.get(team_session_limit, None)
```

Applied in `packager.package()`:
- Sort sessions by mtime descending
- Slice to limit
- Manifest `session_count` reflects total, `sessions` array has only synced ones

### UX: Team Detail Page (`/team/[name]`)

In the Projects section, a segmented control:

```
Sessions to sync: [ All ]  [ Recent 100 ]  [ Recent 10 ]
```

- Calls `PATCH /sync/teams/{name}/settings` on change
- If disk < 10 GiB, show warning banner:
  "Low disk space — limited to recent 100 sessions regardless of setting"

## File Validation & Security

### Validation Pipeline

Every file received via Syncthing passes through validation before indexing:

```
Syncthing receives file
    ↓
ValidateReceivedFile (NEW)
    ├─ Check: file extension in allowlist?
    ├─ Check: file size within limits?
    ├─ Check: path safe (no traversal)?
    ├─ Check: content parseable (JSONL/JSON)?
    ├─ PASS → proceed to indexer
    └─ FAIL → quarantine + log file_rejected event
```

### Allowlist

```python
# api/services/file_validator.py (NEW)

ALLOWED_EXTENSIONS = {".jsonl", ".json", ".txt"}
MAX_JSONL_SIZE = 200 * 1024 * 1024   # 200 MB per session file
MAX_JSON_SIZE = 10 * 1024 * 1024     # 10 MB per manifest/todo
MAX_TXT_SIZE = 50 * 1024 * 1024      # 50 MB per tool result
MAX_FILES_PER_SESSION = 500          # subagents + tool results
MAX_TOTAL_SIZE_PER_PROJECT = 2 * 1024 * 1024 * 1024  # 2 GB
```

### Path Sanitization

```python
def validate_remote_path(base_dir: Path, relative_parts: list[str]) -> Path:
    """Construct and validate a path from remote-derived components.

    Ensures the resolved path is strictly under base_dir.
    Rejects: .., symlinks, non-alphanumeric chars (except - and _).
    """
    # Validate each component
    SAFE_PART = re.compile(r'^[a-zA-Z0-9_\-\.]+$')
    for part in relative_parts:
        if not SAFE_PART.match(part):
            raise ValueError(f"Unsafe path component: {part!r}")
        if part in (".", ".."):
            raise ValueError(f"Path traversal attempt: {part!r}")

    constructed = base_dir.joinpath(*relative_parts).resolve()

    # Verify it's still under base_dir
    if not str(constructed).startswith(str(base_dir.resolve())):
        raise ValueError(f"Path escapes base: {constructed}")

    return constructed
```

### JSONL Content Validation

```python
def validate_jsonl_file(path: Path, max_size: int = MAX_JSONL_SIZE) -> bool:
    """Quick validation of a JSONL file before indexing."""
    # Size check
    if path.stat().st_size > max_size:
        return False

    # Sample first and last lines — must be valid JSON
    with open(path) as f:
        first_line = f.readline()
        if not first_line.strip():
            return False
        try:
            obj = json.loads(first_line)
            # Must have expected top-level keys
            if not isinstance(obj, dict):
                return False
            if "type" not in obj and "role" not in obj:
                return False
        except json.JSONDecodeError:
            return False

    return True
```

### Manifest Schema Validation

```python
from pydantic import BaseModel, field_validator
from typing import Optional

class ManifestSession(BaseModel):
    uuid: str
    mtime: str
    size_bytes: int = 0
    worktree_name: Optional[str] = None
    git_branch: Optional[str] = None

class SyncManifest(BaseModel):
    """Validated manifest for remote session packages."""
    version: int
    user_id: str
    machine_id: str
    project_path: str
    project_encoded: str
    synced_at: str
    session_count: int
    sessions: list[ManifestSession]
    sync_backend: str = "syncthing"
    skill_classifications: dict[str, str] = {}

    @field_validator("user_id", "machine_id")
    @classmethod
    def validate_identifiers(cls, v):
        if not re.match(r'^[a-zA-Z0-9_\-\.]+$', v):
            raise ValueError(f"Unsafe identifier: {v!r}")
        return v

    @field_validator("skill_classifications")
    @classmethod
    def validate_classifications(cls, v):
        VALID_CATEGORIES = {"plugin_skill", "mcp_tool", "slash_command", "hook_command"}
        return {k: cat for k, cat in v.items() if cat in VALID_CATEGORIES}
```

### Quarantine

Files that fail validation are moved to a quarantine directory instead of deleted:

```
~/.claude_karma/quarantine/
├── 2026-03-08T14:30:00Z_alice_malformed-session.jsonl
└── 2026-03-08T14:31:00Z_bob_oversized-tool-result.txt
```

A `file_rejected` event is logged with the reason, so the user sees it in the activity feed:

```
⚠ Rejected file from alice: session.jsonl exceeds 200MB limit    5m ago
```

## Member Removal Cleanup

### API Change: `DELETE /sync/teams/{team_name}/members/{device_id}`

```python
async def sync_remove_member(team_name: str, device_id: str):
    # 1. Get member info before deletion
    member = get_member_by_device_id(conn, device_id)
    member_name = member["name"] if member else "unknown"

    # 2. Remove from DB
    remove_member(conn, team_name, device_id)

    # 3. Cleanup Syncthing folders (best-effort)
    try:
        proxy = get_proxy()
        projects = list_team_projects(conn, team_name)
        for proj in projects:
            suffix = _compute_proj_suffix(...)
            # Remove device from our outbox sharing list
            try:
                await run_sync(proxy.remove_device_from_folder,
                    f"karma-out-{config.user_id}-{suffix}", device_id)
            except Exception:
                pass
            # Remove their inbox folder from our Syncthing
            try:
                await run_sync(proxy.remove_folder,
                    f"karma-out-{member_name}-{suffix}")
            except Exception:
                pass

        # Remove handshake folder
        try:
            await run_sync(proxy.remove_folder,
                f"karma-join-{member_name}-{team_name}")
        except Exception:
            pass

        # Remove device entirely if not in other teams
        all_memberships = conn.execute(
            "SELECT team_name FROM sync_members WHERE device_id = ?",
            (device_id,)
        ).fetchall()
        if not all_memberships:
            await run_sync(proxy.remove_device, device_id)
    except Exception as e:
        logger.warning("Cleanup failed for removed member %s: %s", member_name, e)

    # 4. Log
    log_event(conn, "member_removed", team_name=team_name,
              member_name=member_name,
              detail={"removed_by": config.user_id})

    return {"ok": True, "member_name": member_name, "cleanup": True}
```

## Watcher Enhancement: Periodic Peer Discovery

```python
# cli/karma/watcher.py (CHANGED)

PEER_CHECK_INTERVAL = 300  # 5 minutes

class SessionWatcher:
    def __init__(self, ...):
        self._last_peer_check = 0

    def _maybe_check_peers(self):
        """Check for new team members periodically."""
        now = time.time()
        if now - self._last_peer_check < PEER_CHECK_INTERVAL:
            return

        self._last_peer_check = now
        try:
            # Import and call the pending acceptance logic
            from karma.main import _accept_pending_folders
            accepted = _accept_pending_folders(self.st, self.config, self.conn)
            if accepted:
                logger.info("Watcher discovered %d new folders from peers", accepted)
        except Exception as e:
            logger.debug("Peer check failed: %s", e)
```

This ensures Carol discovers Dave within 5 minutes even without
the frontend open, as long as the watcher is running.

## UX: Permission Steps at the Right Place

### Page-by-Page Breakdown

#### `/sync` (Setup & Overview)
- **Permission**: Initialize sync identity (one-time)
- **Activity**: Global activity feed (all teams, last 8 events)
- **No approval actions here** — this is the overview/status page

#### `/team` (Team List)
- **Permission**: Create team, Join team
- **Pending**: Shows incoming device connections with "Ask for join code" CTA
- **No project-level actions here** — keeps the list page simple

#### `/team/[name]` (Team Detail) — THE MAIN CONTROL CENTER
- **Permissions**:
  - Share projects: "Add Projects" button → AddProjectDialog with multi-select
  - Accept incoming shares: "Incoming Shares" section with Accept/Reject per project
  - Remove members: Per-member remove button with confirmation
  - Leave team: Danger zone
- **Activity**: Team-scoped activity feed (dedicated section)
- **Status**: Per-project sync status (local vs packaged vs received)

#### JoinTeamDialog (Modal overlay)
- **Permission**: Confirm join + select projects to share (in one flow)
- Shows parsed join code details before confirming
- After success: shows matching projects for immediate sharing
- "Skip for Now" always available — no forced sharing

### Flow Diagram

```
User pastes join code
    ↓
JoinTeamDialog parses + shows details
    ↓
[Join Team] button
    ↓
API pairs device + creates membership
    ↓
Dialog shows success + matching projects
    ↓
User selects projects → [Share Selected]
    OR
[Skip for Now] → navigate to /team/[name]
    ↓
/team/[name] page:
    ├── Members section (alice, bob)
    ├── Projects section (shared by you + received)
    ├── Incoming Shares (from other members, accept/reject)
    └── Activity feed (everything that happened)
```

## Implementation Tasks

### Backend (API)

1. **Schema migration v23** — Add `sync_session_limit TEXT DEFAULT 'all'` to `sync_teams`
2. **Modify `sync_join_team()`** — Remove auto-share, return `matching_projects` list
3. **Add `validate_received_file()`** — New service in `api/services/file_validator.py`
4. **Add `SyncManifest` Pydantic model** — Validate manifest.json on receive
5. **Integrate validation into indexer** — Call validator before `Session.from_path()`
6. **Enrich all `log_event()` calls** — Ensure team_name + member_name on every event
7. **Add `GET /sync/teams/{team_name}/activity`** — Team-scoped activity endpoint
8. **Add `PATCH /sync/teams/{team_name}/settings`** — Session limit update endpoint
9. **Fix `sync_remove_member()`** — Add Syncthing folder cleanup
10. **Add quarantine directory** — Move rejected files, log `file_rejected` events

### CLI

11. **Packager session limit** — Add `_get_session_limit()` + disk space check to `package()`
12. **Add file validation to `_accept_pending_folders()`** — Validate before creating inbox
13. **Add peer check to watcher** — Periodic `_accept_pending_folders()` call every 5 min
14. **Add path sanitization** — `validate_remote_path()` for all remote-derived paths

### Frontend

15. **Modify JoinTeamDialog** — Show matching projects after join success
16. **Add Activity section to team detail page** — `TeamActivityFeed.svelte` component
17. **Add session limit selector to team detail** — Segmented control + low-disk warning
18. **Add file rejection warnings** — Show `file_rejected` events prominently in feed

## Migration / Backwards Compatibility

- Existing teams continue to work (no schema change)
- Existing auto-shared folders remain intact (no cleanup of working state)
- The only behavior change: NEW joins won't auto-share projects
- Activity events from before this change will have null team_name — that's fine,
  the UI shows "—" for missing context

## Security Summary

| Attack Vector | Current | After Fix |
|--------------|---------|-----------|
| Malicious JSONL (crash indexer) | No validation | Size + format check |
| Oversized files (disk exhaustion) | No limits | Per-file + per-project caps |
| Path traversal via folder ID | Relies on Path() | Explicit regex + resolve check |
| Git identity spoofing | Auto-resolves wrong project | Manifest validated, project sharing explicit |
| Non-JSONL files injected | Any file accepted | Extension allowlist |
| Removed member keeps syncing | Folders persist | Full Syncthing cleanup |
| 3rd member discovery delay | Frontend poll only | Watcher periodic check (5 min) |
| Disk exhaustion via sync | No limits | 10 GiB floor → force recent 100 |
| Unbounded session count | All sessions synced | User-controlled: all / 100 / 10 |
