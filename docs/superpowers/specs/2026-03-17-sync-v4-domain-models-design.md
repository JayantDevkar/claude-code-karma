# Sync v4: Domain Models & Clean Slate Architecture

**Date:** 2026-03-17
**Status:** Approved
**Scope:** Full rewrite of sync feature — domain models, repositories, services, routers, schema

## Problem Statement

The sync feature has evolved through v1→v3, each version fixing symptoms (folder ID collisions, cross-team leaks, missing cleanup) rather than root causes. The result: ~5,000 LOC spread across 7 routers, 9 services, and 7 DB tables with no formal domain model. Business rules are scattered — "only leader can remove a member" is enforced in router code, not in a central authority.

v4 introduces proper domain modeling with Pydantic classes and state machines, a repository pattern for persistence, and a simplified architecture that eliminates handshake folders, join codes, and the policy/settings system in favor of explicit subscriptions.

## Design Decisions

| Decision | Choice | Rationale |
|---|---|---|
| Modeling approach | Pydantic models + state machines | Centralize invariants, make transitions explicit and testable |
| Persistence | Repository pattern | Pure models (no DB coupling) → testable without SQLite |
| P2P conflict resolution | Optimistic + leader authority | Leader's state wins. Members converge via metadata folder |
| Membership flow | Leader adds member | Eliminates join codes, handshake folders, bidirectional negotiation |
| Device ID exchange | Permanent pairing code | Member generates once, shares out-of-band. Leader is the gatekeeper |
| Leader failure | Catastrophic (alpha) | Team freezes if leader's machine dies. Succession planned for future |
| Project constraint | Git-only | `git_identity` (owner/repo) is the universal cross-machine key |
| Project sharing | Opt-in with direction | Leader shares → member accepts with receive/send/both |
| Branch info | Set from JSONL | `gitBranch` field on messages already collected as `Set[str]` per session |
| Migration | Clean slate | Drop all sync_* tables, recreate as v19. Alpha — breaking is acceptable |
| Reconciliation | 3 phases (from 6) | No handshakes (phase 2), no auto-accept peers (phase 3), subscription-driven folders (phase 5) |
| Network discovery | Future (v4.1) | Pairing code is primary. LAN discovery layers on top later |

## Domain Models

Four entities with explicit states and transitions. All models are frozen (immutable) — methods return new instances.

### Team

The authority boundary. Only the leader can mutate team membership and project sharing.

```python
class TeamStatus(str, Enum):
    ACTIVE = "active"
    DISSOLVED = "dissolved"

class Team(BaseModel):
    model_config = ConfigDict(frozen=True)

    name: str
    leader_device_id: str
    leader_member_tag: str
    status: TeamStatus = TeamStatus.ACTIVE
    created_at: datetime
```

**State machine:**
```
ACTIVE ──dissolve(by_device=leader)──→ DISSOLVED
```

**Methods:**
- `is_leader(device_id) -> bool`
- `dissolve(*, by_device) -> Team` — only leader, returns DISSOLVED
- `add_member(member, *, by_device) -> Member` — only leader, validates no duplicate member_tag
- `remove_member(member, *, by_device) -> Member` — only leader, returns member with REMOVED status

**Key invariant:** Authorization checks live on Team, not on Member/Project. Team is the single authority checkpoint.

### Member

A person + machine. Identity is `member_tag = "{user_id}.{machine_tag}"`.

```python
class MemberStatus(str, Enum):
    ADDED = "added"       # leader added, device hasn't acknowledged
    ACTIVE = "active"     # device acknowledged via metadata sync
    REMOVED = "removed"   # leader removed

class Member(BaseModel):
    model_config = ConfigDict(frozen=True)

    member_tag: str        # "user_id.machine_tag"
    team_name: str
    device_id: str
    user_id: str           # parsed from member_tag
    machine_tag: str       # parsed from member_tag
    status: MemberStatus = MemberStatus.ADDED
```

**State machine:**
```
ADDED ──activate()──→ ACTIVE ──remove()──→ REMOVED
  │                                           ▲
  └────────────remove()───────────────────────┘
```

**Methods:**
- `activate() -> Member` — ADDED → ACTIVE (device acknowledged)
- `remove() -> Member` — ADDED|ACTIVE → REMOVED (authorization checked by Team, not here). Allows removal before device acknowledges.
- `is_active -> bool` — property

### SharedProject

A project shared with a team. Git-only — `git_identity` is required.

```python
class SharedProjectStatus(str, Enum):
    SHARED = "shared"
    REMOVED = "removed"

class SharedProject(BaseModel):
    model_config = ConfigDict(frozen=True)

    team_name: str
    git_identity: str       # REQUIRED — "owner/repo", the universal key (PK component)
    encoded_name: str | None = None  # local path encoding — set if member has repo cloned, machine-specific
    folder_suffix: str      # derived from git_identity (owner-repo)
    status: SharedProjectStatus = SharedProjectStatus.SHARED
```

**State machine:**
```
SHARED ──remove()──→ REMOVED
```

### Subscription

The member-project relationship. Controls what a member receives and sends for a specific project.

```python
class SubscriptionStatus(str, Enum):
    OFFERED = "offered"     # project shared, member hasn't responded
    ACCEPTED = "accepted"   # member accepted
    PAUSED = "paused"       # member temporarily stopped syncing
    DECLINED = "declined"   # member declined

class SyncDirection(str, Enum):
    RECEIVE = "receive"     # see teammates' sessions
    SEND = "send"           # share own sessions
    BOTH = "both"           # bidirectional

class Subscription(BaseModel):
    model_config = ConfigDict(frozen=True)

    member_tag: str
    team_name: str
    project_git_identity: str   # references SharedProject.git_identity (universal key)
    status: SubscriptionStatus = SubscriptionStatus.OFFERED
    direction: SyncDirection = SyncDirection.BOTH
```

**State machine:**
```
OFFERED ──accept(direction)──→ ACCEPTED ──pause()──→ PAUSED
   │                              │                     │
   │                              │    resume()─────────┘
   │                              │
   └──decline()──→ DECLINED ←──decline()
```

**Methods:**
- `accept(direction) -> Subscription` — OFFERED → ACCEPTED
- `pause() -> Subscription` — ACCEPTED → PAUSED
- `resume() -> Subscription` — PAUSED → ACCEPTED
- `decline() -> Subscription` — any → DECLINED
- `change_direction(direction) -> Subscription` — while ACCEPTED

**Replaces three v3 concepts:** `sync_settings` (scope-based policies), `sync_rejected_folders` (persistent rejection), and the implicit "everyone gets everything" default.

## Packaged Session Metadata

When sessions are packaged for sync, they include:

```python
class PackagedSessionMeta:
    session_uuid: str
    git_identity: str        # "owner/repo" — universal project key
    branches: set[str]       # from session.get_git_branches() — already extracted from JSONL
    member_tag: str          # who created the session
    created_at: datetime
```

**Branch handling:** Each message in a Claude Code JSONL has an optional `gitBranch` field. The parser already collects these into a `Set[str]` per session via `session.get_git_branches()`. A session that spans `main` and `feature-x` shows up when filtering for either branch.

**Project mapping on receiver:** Git identity is the join key. If the receiver has the repo cloned, sessions map to their local project path. If not, sessions are shown under the git identity and auto-map when the repo is eventually cloned.

## Pairing Codes

Members generate a permanent pairing code that encodes their identity:

```python
class PairingInfo:
    member_tag: str      # "user_id.machine_tag"
    device_id: str       # Syncthing device ID

class PairingService:
    def generate_code(self, member_tag: str, device_id: str) -> str:
        """Encode to short shareable code, e.g., 'KXRM-4HPQ-ANVY'."""

    def validate_code(self, code: str) -> PairingInfo:
        """Decode pairing code back to identity."""
```

**Properties:**
- Permanent — generate once, share with any team leader
- Encodes `member_tag + device_id` (set during Syncthing setup)
- Leader is the gatekeeper — possessing a code doesn't grant access, the leader must explicitly add the member
- Displayed in member's UI with copy button for out-of-band sharing (Slack, text, etc.)

## Sync Events

Typed event classes for the audit trail. Each event captures a state transition with structured detail.

```python
class SyncEventType(str, Enum):
    TEAM_CREATED = "team_created"
    TEAM_DISSOLVED = "team_dissolved"
    MEMBER_ADDED = "member_added"
    MEMBER_ACTIVATED = "member_activated"      # device acknowledged
    MEMBER_REMOVED = "member_removed"
    MEMBER_AUTO_LEFT = "member_auto_left"       # removed via metadata signal
    PROJECT_SHARED = "project_shared"
    PROJECT_REMOVED = "project_removed"
    SUBSCRIPTION_OFFERED = "subscription_offered"
    SUBSCRIPTION_ACCEPTED = "subscription_accepted"
    SUBSCRIPTION_PAUSED = "subscription_paused"
    SUBSCRIPTION_RESUMED = "subscription_resumed"
    SUBSCRIPTION_DECLINED = "subscription_declined"
    DIRECTION_CHANGED = "direction_changed"
    SESSION_PACKAGED = "session_packaged"
    SESSION_RECEIVED = "session_received"
    DEVICE_PAIRED = "device_paired"
    DEVICE_UNPAIRED = "device_unpaired"

class SyncEvent(BaseModel):
    model_config = ConfigDict(frozen=True)

    event_type: SyncEventType
    team_name: str | None = None
    member_tag: str | None = None
    project_git_identity: str | None = None
    session_uuid: str | None = None
    detail: dict | None = None          # structured per event type
    created_at: datetime
```

**Detail structure per event type:**

| Event Type | Detail Fields |
|---|---|
| `member_added` | `{device_id, added_by}` |
| `member_removed` | `{device_id, removed_by}` |
| `subscription_accepted` | `{direction}` |
| `direction_changed` | `{old_direction, new_direction}` |
| `session_packaged` | `{branches, session_created_at}` |
| `session_received` | `{from_member_tag, branches}` |
| `device_paired` | `{device_id}` |

Events are deduplicated by `(event_type, session_uuid)` for `session_packaged`/`session_received` to prevent duplicate logging on re-scans.

## Metadata Folder Structure

Each team has a metadata folder (`karma-meta--{team}`, type `sendreceive`) shared with all members. Members write their own files — no conflicts.

```
karma-meta--karma-team/
├── team.json                          # team definition (written by leader)
├── members/
│   ├── jayant.macbook.json            # leader's state
│   ├── ayush.laptop.json              # member's state
│   └── ...
└── removed/
    └── bob.desktop.json               # removal signal (written by leader)
```

**`team.json`** (written by leader only):
```json
{
    "name": "karma-team",
    "created_by": "jayant.macbook",
    "leader_device_id": "XXXXXXX-...",
    "created_at": "2026-03-17T10:00:00Z"
}
```

**`members/{member_tag}.json`** (each member writes their own):
```json
{
    "member_tag": "ayush.laptop",
    "device_id": "YYYYYYY-...",
    "user_id": "ayush",
    "machine_tag": "laptop",
    "status": "active",
    "projects": [
        {
            "git_identity": "jayantdevkar/claude-karma",
            "folder_suffix": "jayantdevkar-claude-karma"
        }
    ],
    "subscriptions": {
        "jayantdevkar/claude-karma": {
            "status": "accepted",
            "direction": "both"
        }
    },
    "updated_at": "2026-03-17T10:05:00Z"
}
```

**`removed/{member_tag}.json`** (written by leader on removal):
```json
{
    "member_tag": "bob.desktop",
    "removed_by": "jayant.macbook",
    "removed_at": "2026-03-17T12:00:00Z"
}
```

**How the reconciler uses metadata:**
- Phase 1 reads `members/*.json` to discover new peers and their device IDs
- Phase 1 reads `removed/*.json` to detect own removal → triggers auto-leave
- Phase 1 reads `members/*.json` `projects` list to discover projects shared by other members → creates OFFERED subscriptions locally
- Phase 3 reads `members/*.json` `subscriptions` to compute which devices should be in each folder's device list (only members with `accepted` + `send`|`both` for a project contribute their device to that project's folder)

## Session Packaging Integration

The watcher/packager integrates with the subscription model:

**Packaging gate:** Only package sessions for projects where the local member has an ACCEPTED subscription with direction `send` or `both`.

```python
# In watcher_manager.py (rewritten)
class WatcherManager:
    def package_new_sessions(self, conn) -> None:
        """Package sessions into outbox folders, gated by subscriptions."""
        my_tag = self.config.member_tag
        accepted_subs = self.subs.list_for_member(conn, my_tag)
        for sub in accepted_subs:
            if sub.status != SubscriptionStatus.ACCEPTED:
                continue
            if sub.direction not in (SyncDirection.SEND, SyncDirection.BOTH):
                continue
            project = self.projects.get(conn, sub.team_name, sub.project_git_identity)
            if not project or not project.encoded_name:
                continue  # don't have repo cloned locally
            sessions = self.find_new_sessions(project.encoded_name)
            for session in sessions:
                meta = PackagedSessionMeta(
                    session_uuid=session.uuid,
                    git_identity=project.git_identity,
                    branches=session.get_git_branches(),
                    member_tag=my_tag,
                    created_at=session.created_at,
                )
                self.write_to_outbox(project.folder_suffix, session, meta)
                self.events.log(conn, SyncEvent(
                    event_type=SyncEventType.SESSION_PACKAGED,
                    team_name=sub.team_name,
                    member_tag=my_tag,
                    project_git_identity=project.git_identity,
                    session_uuid=session.uuid,
                    detail={"branches": list(meta.branches)},
                ))
```

**Receiving sessions:** `remote_sessions.py` remains largely unchanged but uses `git_identity` to map received sessions to local projects. When a session arrives in an inbox folder, the receiver:
1. Reads `PackagedSessionMeta` from the packaged session
2. Looks up local project by `git_identity` — if found, maps to `encoded_name`; if not, stores under `git_identity` until repo is cloned
3. Logs `SESSION_RECEIVED` event with `from_member_tag` and `branches`

## Cleanup Logic

### Member Removal Cleanup

When a member is removed (by leader) or auto-leaves (via metadata signal), received session data must be cleaned up:

```python
# In TeamService.remove_member() — leader's machine
def remove_member(self, conn, *, team_name, by_device, member_tag):
    # ... (authorization, state transition, removal signal) ...
    # Cleanup received sessions from this member
    self._cleanup_received_data(conn, team_name, member_tag)

def _cleanup_received_data(self, conn, team_name: str, member_tag: str) -> dict:
    """Remove received session files + DB rows for a removed member."""
    stats = {"files_removed": 0, "rows_removed": 0}
    # Find inbox folders for this member's outboxes
    inbox_pattern = f"karma-out--{member_tag}--*"
    for folder_path in self.folders.find_folders(inbox_pattern):
        shutil.rmtree(folder_path, ignore_errors=True)
        stats["files_removed"] += 1
    # Remove session DB rows from this member
    rows = conn.execute(
        "DELETE FROM sessions WHERE source='remote' AND remote_user_id=? RETURNING uuid",
        (member_tag.split(".")[0],)
    ).fetchall()
    stats["rows_removed"] = len(rows)
    return stats
```

### Project Removal Cleanup

When a project is removed from a team:

```python
# In ProjectService.remove_project()
def remove_project(self, conn, *, team_name, by_device, git_identity):
    # ... (authorization, state transition) ...
    project = self.projects.get(conn, team_name, git_identity)
    # Remove all subscriptions for this project
    subs = self.subs.list_for_project(conn, team_name, git_identity)
    for sub in subs:
        declined = sub.decline()
        self.subs.save(conn, declined)
    # Cleanup Syncthing folders for this project
    self.folders.cleanup_project_folders(conn, team_name, project.folder_suffix)
    # Cleanup received session files for this project
    self._cleanup_project_data(conn, project)
```

### Auto-Leave Cleanup (Member's Machine)

When the reconciler detects a removal signal for the local member:

```python
def _auto_leave(self, conn, team: Team) -> None:
    """Clean up everything related to this team on the local machine."""
    # 1. Remove all Syncthing folders for this team
    self.folders.cleanup_team_folders(conn, team.name)
    # 2. Unpair devices that are not in any other team
    members = self.members.list_for_team(conn, team.name)
    for member in members:
        other_teams = self.members.get_by_device(conn, member.device_id)
        if len(other_teams) <= 1:  # only this team
            self.devices.unpair(member.device_id)
    # 3. Delete team from local DB (CASCADE handles members, projects, subs)
    self.teams.delete(conn, team.name)
    # 4. Log event
    self.events.log(conn, SyncEvent(event_type=SyncEventType.MEMBER_AUTO_LEFT, team_name=team.name))
```

## Sync Direction → Syncthing Folder Type Mapping

| Direction | Outbox Folder | Inbox Folders | Syncthing Type |
|---|---|---|---|
| `send` | Created (own sessions packaged here) | Not created | Outbox: `sendonly` |
| `receive` | Not created | Accepted from teammates | Inbox: `receiveonly` |
| `both` | Created | Accepted from teammates | Outbox: `sendonly`, Inbox: `receiveonly` |

- **Outbox:** `karma-out--{my_member_tag}--{folder_suffix}` — type `sendonly` on my machine. Other members receive it as `receiveonly`.
- **Inbox:** `karma-out--{their_member_tag}--{folder_suffix}` — type `receiveonly` on my machine. The folder name uses the sender's member_tag because it's their outbox.
- **Changing direction** from `both` to `receive` removes the outbox folder. From `both` to `send` removes inbox folder acceptance (stops syncing inbound, but does not delete already-received data).

## sync_removed_members Purpose in v4

This table prevents the reconciler from re-adding a removed member via stale metadata. Scenario:

1. Leader removes Bob → writes removal signal to metadata
2. Bob's machine processes removal, auto-leaves
3. But Bob's old `members/bob.desktop.json` state file may still exist in the metadata folder (Syncthing doesn't delete files, only syncs changes)
4. Without `sync_removed_members`, the leader's next reconciliation cycle would see Bob's state file and think "new member discovered"

The table acts as a blocklist: `was_removed(team, device_id)` returns `True`, and the reconciler skips re-adding. The entry is cleared only if the leader explicitly re-adds Bob via a new pairing code.

## Database Schema (v19)

Clean break. All existing sync_* tables dropped and recreated.

```sql
CREATE TABLE sync_teams (
    name             TEXT PRIMARY KEY,
    leader_device_id TEXT NOT NULL,
    leader_member_tag TEXT NOT NULL,
    status           TEXT NOT NULL DEFAULT 'active'
                     CHECK(status IN ('active', 'dissolved')),
    created_at       TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE sync_members (
    team_name        TEXT NOT NULL REFERENCES sync_teams(name) ON DELETE CASCADE,
    member_tag       TEXT NOT NULL,
    device_id        TEXT NOT NULL,
    user_id          TEXT NOT NULL,
    machine_tag      TEXT NOT NULL,
    status           TEXT NOT NULL DEFAULT 'added'
                     CHECK(status IN ('added', 'active', 'removed')),
    added_at         TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at       TEXT NOT NULL DEFAULT (datetime('now')),
    PRIMARY KEY (team_name, member_tag)
);

CREATE TABLE sync_projects (
    team_name        TEXT NOT NULL REFERENCES sync_teams(name) ON DELETE CASCADE,
    git_identity     TEXT NOT NULL,      -- "owner/repo" — universal cross-machine key
    encoded_name     TEXT,               -- local path encoding, nullable (machine-specific)
    folder_suffix    TEXT NOT NULL,       -- derived from git_identity (owner-repo)
    status           TEXT NOT NULL DEFAULT 'shared'
                     CHECK(status IN ('shared', 'removed')),
    shared_at        TEXT NOT NULL DEFAULT (datetime('now')),
    PRIMARY KEY (team_name, git_identity)
);

CREATE TABLE sync_subscriptions (
    member_tag       TEXT NOT NULL,
    team_name        TEXT NOT NULL,
    project_git_identity TEXT NOT NULL,
    status           TEXT NOT NULL DEFAULT 'offered'
                     CHECK(status IN ('offered', 'accepted', 'paused', 'declined')),
    direction        TEXT NOT NULL DEFAULT 'both'
                     CHECK(direction IN ('receive', 'send', 'both')),
    updated_at       TEXT NOT NULL DEFAULT (datetime('now')),
    PRIMARY KEY (member_tag, team_name, project_git_identity),
    FOREIGN KEY (team_name, member_tag)
        REFERENCES sync_members(team_name, member_tag) ON DELETE CASCADE,
    FOREIGN KEY (team_name, project_git_identity)
        REFERENCES sync_projects(team_name, git_identity) ON DELETE CASCADE
);

CREATE TABLE sync_events (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    event_type       TEXT NOT NULL,
    team_name        TEXT,
    member_tag       TEXT,
    project_encoded_name TEXT,
    session_uuid     TEXT,
    detail           TEXT,
    created_at       TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE sync_removed_members (
    team_name        TEXT NOT NULL REFERENCES sync_teams(name) ON DELETE CASCADE,
    device_id        TEXT NOT NULL,
    member_tag       TEXT,
    removed_at       TEXT NOT NULL DEFAULT (datetime('now')),
    PRIMARY KEY (team_name, device_id)
);

-- Indexes
CREATE INDEX idx_members_device ON sync_members(device_id);
CREATE INDEX idx_members_status ON sync_members(team_name, status);
CREATE INDEX idx_projects_suffix ON sync_projects(folder_suffix);
CREATE INDEX idx_projects_git ON sync_projects(git_identity);
CREATE INDEX idx_subs_member ON sync_subscriptions(member_tag);
CREATE INDEX idx_subs_status ON sync_subscriptions(status);
CREATE INDEX idx_subs_project ON sync_subscriptions(project_git_identity);
CREATE INDEX idx_events_type ON sync_events(event_type);
CREATE INDEX idx_events_team ON sync_events(team_name);
CREATE INDEX idx_events_time ON sync_events(created_at);
```

**Migration strategy:** v19 migration drops all sync_* tables and recreates from scratch. No data migration. Users re-create teams after update.

**Changes from v18:**
- `sync_settings` → deleted (replaced by `sync_subscriptions.direction`)
- `sync_rejected_folders` → deleted (replaced by `sync_subscriptions.status='declined'`)
- `sync_members` PK changed from `(team_name, device_id)` to `(team_name, member_tag)`, added `updated_at`
- `sync_team_projects` → renamed to `sync_projects`, PK changed from `(team_name, encoded_name)` to `(team_name, git_identity)`, `encoded_name` now nullable, added `status` column
- `sync_teams` simplified — removed `join_code`, `backend`, `sync_session_limit`, `pending_leave`
- `sync_subscriptions` → new table (references `git_identity` not `encoded_name`)
- `sync_events` column `member_name` renamed to `member_tag`

## Repositories

Thin persistence layer. Models never touch the DB.

```python
class TeamRepository:
    def get(self, conn, name: str) -> Team | None
    def get_by_leader(self, conn, device_id: str) -> list[Team]
    def save(self, conn, team: Team) -> None
    def delete(self, conn, name: str) -> None
    def list_all(self, conn) -> list[Team]

class MemberRepository:
    def get(self, conn, team_name: str, member_tag: str) -> Member | None
    def get_by_device(self, conn, device_id: str) -> list[Member]
    def save(self, conn, member: Member) -> None
    def list_for_team(self, conn, team_name: str) -> list[Member]
    def was_removed(self, conn, team_name: str, device_id: str) -> bool
    def record_removal(self, conn, team_name: str, device_id: str) -> None

class ProjectRepository:
    def get(self, conn, team_name: str, git_identity: str) -> SharedProject | None
    def save(self, conn, project: SharedProject) -> None
    def list_for_team(self, conn, team_name: str) -> list[SharedProject]
    def find_by_suffix(self, conn, suffix: str) -> list[SharedProject]
    def find_by_git_identity(self, conn, git_identity: str) -> list[SharedProject]  # cross-team

class SubscriptionRepository:
    def get(self, conn, member_tag: str, team_name: str, git_identity: str) -> Subscription | None
    def save(self, conn, sub: Subscription) -> None
    def list_for_member(self, conn, member_tag: str) -> list[Subscription]
    def list_for_project(self, conn, team_name: str, git_identity: str) -> list[Subscription]
    def list_accepted_for_suffix(self, conn, suffix: str) -> list[Subscription]  # for device list computation

class EventRepository:
    def log(self, conn, event: SyncEvent) -> int
    def query(self, conn, *, team: str = None, event_type: str = None, limit: int = 50) -> list[SyncEvent]
```

## Service Layer

Services orchestrate domain models, repositories, and Syncthing.

### TeamService

```python
class TeamService:
    def __init__(self, teams: TeamRepository, members: MemberRepository,
                 subs: SubscriptionRepository, events: EventRepository,
                 devices: DeviceManager, metadata: MetadataService,
                 projects: ProjectRepository): ...

    def create_team(self, conn, *, name, leader_member_tag, leader_device_id) -> Team
    def add_member(self, conn, *, team_name, by_device, new_member_tag, new_device_id) -> Member
    def remove_member(self, conn, *, team_name, by_device, member_tag) -> Member
    def dissolve_team(self, conn, *, team_name, by_device) -> Team
```

**`dissolve_team` flow:**
1. `team.dissolve(by_device=leader)` — validates leader authorization
2. Write dissolution signal to metadata folder (so remote members auto-leave)
3. Cleanup all Syncthing folders for this team (`FolderManager.cleanup_team_folders()`)
4. Unpair devices not shared with other teams (cross-team safety check)
5. Delete team from DB — `ON DELETE CASCADE` handles members, projects, subscriptions at DB level
6. Log TeamDissolved event

Note: DB cascade is acceptable here because dissolution is a terminal operation. The domain model validates the transition (only leader can dissolve), then the DB handles the bulk cleanup. Remote members' machines clean up independently via the metadata dissolution signal.

**`create_team` flow:**
1. Create Team (ACTIVE) + leader as Member (ACTIVE)
2. Save to repos
3. Write metadata folder (team.json + own member state)
4. Log TeamCreated event

**`add_member` flow:**
1. `team.add_member()` — validates leader authorization
2. Create Member (ADDED)
3. `DeviceManager.pair(device_id)` — Syncthing pairing
4. Write updated metadata
5. Create OFFERED subscription for each shared project
6. Log MemberAdded event

**`remove_member` flow:**
1. `team.remove_member()` — validates leader authorization (works for ADDED or ACTIVE members)
2. Member → REMOVED, record removal in `sync_removed_members` (prevents re-add from stale metadata)
3. Write removal signal to metadata folder (`removed/{member_tag}.json`)
4. Remove device from all team folder device lists
5. Cleanup received session data from this member (files + DB rows)
6. Unpair device only if not used by any other team (cross-team safety check)
7. Log MemberRemoved event

### ProjectService

```python
class ProjectService:
    def __init__(self, projects: ProjectRepository, subs: SubscriptionRepository,
                 members: MemberRepository, teams: TeamRepository,
                 folders: FolderManager, metadata: MetadataService,
                 events: EventRepository): ...

    def share_project(self, conn, *, team_name, by_device, git_identity, encoded_name=None) -> SharedProject
    def remove_project(self, conn, *, team_name, by_device, git_identity) -> SharedProject
    def accept_subscription(self, conn, *, member_tag, team_name, git_identity, direction) -> Subscription
    def pause_subscription(self, conn, *, member_tag, team_name, git_identity) -> Subscription
    def resume_subscription(self, conn, *, member_tag, team_name, git_identity) -> Subscription
    def decline_subscription(self, conn, *, member_tag, team_name, git_identity) -> Subscription
    def change_direction(self, conn, *, member_tag, team_name, git_identity, direction) -> Subscription
```

**`share_project` flow:**
1. Validate leader authorization
2. Validate git_identity is present (git-only constraint)
3. Create SharedProject (SHARED) with `git_identity` as PK, `encoded_name` optional (set if leader has repo cloned)
4. Create OFFERED subscription for each active member (excluding leader)
5. Create leader's outbox folder in Syncthing (if leader has `encoded_name`)
6. Update metadata with project list
7. Log ProjectShared event

**`accept_subscription` flow:**
1. `sub.accept(direction)` — OFFERED → ACCEPTED
2. Apply sync direction:
   - `receive` or `both` → `FolderManager.ensure_inbox_folders()`
   - `send` or `both` → `FolderManager.ensure_outbox_folder()`
3. Update metadata with subscription state
4. Log SubscriptionAccepted event

### ReconciliationService

Simplified from 6 phases to 3. Runs every 60s.

```python
class ReconciliationService:
    def run_cycle(self, conn) -> None:
        for team in self.teams.list_all(conn):
            self.phase_metadata(conn, team)
            self.phase_mesh_pair(conn, team)
            self.phase_device_lists(conn, team)
```

**Phase 1 — Metadata Reconciliation:**
- Read team metadata folder
- Detect removal signals → auto-leave if own member_tag is removed
- Discover new members → register as ADDED, transition to ACTIVE
- Discover new projects → create OFFERED subscriptions

**Phase 2 — Mesh Pairing:**
- For each active team member, ensure Syncthing device is paired
- Idempotent — skips already-paired devices

**Phase 3 — Device List Sync:**
- For each project suffix, query accepted subscriptions across all teams
- Compute desired device set
- `FolderManager.set_folder_devices()` — declarative, replaces entire device list

**Eliminated phases (from v3):**
- Phase 2 (reconcile pending handshakes) — no handshake folders in v4
- Phase 3 (auto-accept pending peers) — leader adds explicitly
- Phase 5 (auto-accept pending folders) — subscription-driven acceptance

### Syncthing Abstraction

Three focused classes replacing the monolithic `syncthing_proxy.py`:

```python
class SyncthingClient:
    """Pure HTTP wrapper. No business logic. 1:1 with Syncthing REST API."""
    def get_config(self) -> dict
    def post_config(self, config: dict) -> None
    def get_system_status(self) -> dict
    def get_connections(self) -> dict
    def get_pending_devices(self) -> list[dict]
    def get_pending_folders(self) -> list[dict]

class DeviceManager:
    """Device pairing operations."""
    def pair(self, device_id: str) -> None
    def unpair(self, device_id: str) -> None
    def ensure_paired(self, device_id: str) -> None
    def is_connected(self, device_id: str) -> bool
    def list_connected(self) -> list[str]

class FolderManager:
    """Folder lifecycle tied to subscriptions."""
    def ensure_outbox_folder(self, conn, sub: Subscription) -> None
    def ensure_inbox_folders(self, conn, sub: Subscription) -> None
    def set_folder_devices(self, suffix: str, device_ids: set[str]) -> None
    def remove_device_from_team_folders(self, conn, team: str, device_id: str) -> None
    def cleanup_team_folders(self, conn, team: str) -> None
```

### MetadataService

```python
class MetadataService:
    def write_team_state(self, team: Team, members: list[Member]) -> None
    def write_removal_signal(self, team_name: str, member_tag: str) -> None
    def read_team_metadata(self, team_name: str) -> dict[str, dict]
    def write_own_state(self, team_name: str, member_tag: str,
                       subscriptions: list[Subscription]) -> None
```

### PairingService

```python
class PairingService:
    def generate_code(self, member_tag: str, device_id: str) -> str
    def validate_code(self, code: str) -> PairingInfo
```

## API Endpoints

4 routers (down from 7):

### sync_teams.py — Team + Member Management

| Method | Endpoint | Description |
|---|---|---|
| POST | `/sync/teams` | Create team |
| GET | `/sync/teams` | List all teams |
| GET | `/sync/teams/{name}` | Team detail (members, projects, subscriptions) |
| DELETE | `/sync/teams/{name}` | Dissolve team |
| POST | `/sync/teams/{name}/members` | Add member (leader pastes pairing code) |
| DELETE | `/sync/teams/{name}/members/{tag}` | Remove member |
| GET | `/sync/teams/{name}/members` | List members with connection status |

### sync_projects.py — Project Sharing + Subscriptions

| Method | Endpoint | Description |
|---|---|---|
| POST | `/sync/teams/{name}/projects` | Share project (git-only) |
| DELETE | `/sync/teams/{name}/projects/{git_identity}` | Remove project |
| GET | `/sync/teams/{name}/projects` | List team projects |
| POST | `/sync/subscriptions/{team}/{project}/accept` | Accept with direction |
| POST | `/sync/subscriptions/{team}/{project}/pause` | Pause subscription |
| POST | `/sync/subscriptions/{team}/{project}/resume` | Resume subscription |
| POST | `/sync/subscriptions/{team}/{project}/decline` | Decline subscription |
| PATCH | `/sync/subscriptions/{team}/{project}/direction` | Change sync direction |
| GET | `/sync/subscriptions` | List all my subscriptions |

### sync_pairing.py — Pairing + Devices

| Method | Endpoint | Description |
|---|---|---|
| GET | `/sync/pairing/code` | Generate my pairing code |
| POST | `/sync/pairing/validate` | Validate a pairing code (preview) |
| GET | `/sync/devices` | Connected devices with status |

### sync_system.py — System Status

| Method | Endpoint | Description |
|---|---|---|
| GET | `/sync/status` | Syncthing running, version, device_id |
| POST | `/sync/initialize` | First-time setup |
| POST | `/sync/reconcile` | Trigger manual reconciliation |

## File Layout

```
api/
├── domain/                              # Pure domain models
│   ├── __init__.py
│   ├── team.py                          # Team + TeamStatus
│   ├── member.py                        # Member + MemberStatus
│   ├── project.py                       # SharedProject + SharedProjectStatus
│   ├── subscription.py                  # Subscription + SubscriptionStatus + SyncDirection
│   └── events.py                        # Typed event classes
│
├── repositories/                        # SQLite persistence
│   ├── __init__.py
│   ├── team_repo.py
│   ├── member_repo.py
│   ├── project_repo.py
│   ├── subscription_repo.py
│   └── event_repo.py
│
├── services/
│   ├── sync/                            # Business operations
│   │   ├── __init__.py
│   │   ├── team_service.py
│   │   ├── project_service.py
│   │   ├── reconciliation_service.py
│   │   ├── metadata_service.py
│   │   └── pairing_service.py
│   │
│   ├── syncthing/                       # Syncthing abstraction
│   │   ├── __init__.py
│   │   ├── client.py
│   │   ├── device_manager.py
│   │   └── folder_manager.py
│   │
│   ├── watcher_manager.py              # Rewritten — uses ReconciliationService
│   └── remote_sessions.py             # Unchanged — session discovery
│
├── routers/
│   ├── sync_teams.py                   # Rewritten
│   ├── sync_projects.py                # Rewritten
│   ├── sync_pairing.py                 # New
│   └── sync_system.py                  # Simplified
│
└── db/
    └── schema.py                        # v19 migration added
```

### Deleted Files

```
DELETED (v3 → v4):
api/routers/sync_members.py             → merged into sync_teams.py
api/routers/sync_pending.py             → eliminated
api/routers/sync_devices.py             → merged into sync_pairing.py
api/routers/sync_operations.py          → absorbed

api/services/sync_queries.py            → replaced by repositories/
api/services/sync_reconciliation.py     → replaced by sync/reconciliation_service.py
api/services/sync_folders.py            → replaced by syncthing/folder_manager.py
api/services/sync_metadata_reconciler.py → replaced by sync/metadata_service.py
api/services/sync_metadata_writer.py    → replaced by sync/metadata_service.py
api/services/sync_identity.py           → replaced by domain models + pairing_service
api/services/sync_policy.py             → eliminated (subscription model replaces policies)
api/services/syncthing_proxy.py         → replaced by syncthing/ package
api/db/sync_queries.py                  → replaced by repositories/

DELETED DB TABLES:
sync_settings                            → replaced by sync_subscriptions.direction
sync_rejected_folders                    → replaced by sync_subscriptions.status='declined'
```

## End-to-End Flows

### Flow 1: Leader Creates Team + Shares Project

```
Leader → POST /sync/teams { name: "karma-team" }
  → TeamService.create_team()
    → Team(ACTIVE) + leader Member(ACTIVE)
    → MetadataService.write_team_state()
      → creates karma-meta--karma-team/ folder
      → writes team.json + leader's member state file

Leader → POST /sync/teams/karma-team/projects
    { git_identity: "jayantdevkar/claude-karma", encoded_name: "-Users-jayant-..." }
  → ProjectService.share_project()
    → SharedProject(SHARED, git_identity=PK, folder_suffix="jayantdevkar-claude-karma")
    → FolderManager.ensure_outbox_folder()
      → creates karma-out--jayant.macbook--jayantdevkar-claude-karma (sendonly)
    → MetadataService.write_own_state() (includes project list)
```

### Flow 2: Leader Adds Member via Pairing Code

```
Member's UI → GET /sync/pairing/code → "KXRM-4HPQ-ANVY"
Member shares code out-of-band (Slack, text)

Leader → POST /sync/teams/karma-team/members { pairing_code: "KXRM-4HPQ-ANVY" }
  → PairingService.validate_code() → PairingInfo(member_tag, device_id)
  → TeamService.add_member()
    → team.add_member() validates leader authorization
    → Member(ADDED)
    → DeviceManager.pair(device_id)
    → MetadataService.write_team_state() (includes new member)
    → For each shared project: Subscription(OFFERED)

═══ Syncthing syncs metadata folder ═══

Member's ReconciliationService.phase_metadata()
  → Reads metadata, finds own member_tag
  → Member ADDED → ACTIVE
  → DeviceManager.ensure_paired(leader)
  → MetadataService.write_own_state()
  → UI shows: "Added to karma-team" + offered projects
```

### Flow 3: Member Accepts Project

```
Member → POST /sync/subscriptions/karma-team/jayantdevkar%2Fclaude-karma/accept
    { direction: "both" }
  → ProjectService.accept_subscription()
    → sub.accept(BOTH) → OFFERED → ACCEPTED
    → FolderManager.ensure_outbox_folder(sub)
      → creates karma-out--ayush.laptop--jayantdevkar-claude-karma (sendonly)
    → FolderManager.ensure_inbox_folders(sub)
      → accepts karma-out--jayant.macbook--jayantdevkar-claude-karma (receiveonly)
    → MetadataService.write_own_state() (subscriptions: {claude-karma: accepted/both})

Next reconciliation cycle (60s):
  → phase_device_lists() queries accepted subs for suffix "jayantdevkar-claude-karma"
  → desired_devices = {jayant.macbook_device, ayush.laptop_device}
  → FolderManager.set_folder_devices() applies declaratively

═══ SYNCING ═══
```

### Flow 4: Leader Removes Member

```
Leader → DELETE /sync/teams/karma-team/members/ayush.laptop
  → TeamService.remove_member()
    → team.remove_member() validates leader authorization
    → Member → REMOVED
    → record_removal() prevents re-add from stale data
    → MetadataService.write_removal_signal()
    → FolderManager.remove_device_from_team_folders()

═══ Syncthing syncs metadata folder ═══

Member's ReconciliationService.phase_metadata()
  → Reads removal signal for own member_tag
  → auto_leave(): cleanup folders, delete local team data, unpair devices
  → UI shows: "Removed from karma-team"
```

### Flow 5: Member Changes Sync Direction

```
Member → PATCH /sync/subscriptions/karma-team/project/direction { direction: "receive" }
  → ProjectService.change_direction()
    → sub.change_direction(RECEIVE)
    → FolderManager.remove_outbox_folder() (stops sending)
    → Inbox folders remain (still receiving)
    → MetadataService.write_own_state()
```

### Flow 6: Leader Removes Project

```
Leader → DELETE /sync/teams/karma-team/projects/jayantdevkar%2Fclaude-karma
  → ProjectService.remove_project()
    → Validates leader authorization
    → SharedProject → REMOVED
    → Decline all subscriptions for this project (all members)
    → FolderManager.cleanup_project_folders()
      → removes outbox + inbox folders for this project's suffix
    → Cleanup received session files for this project
    → MetadataService.write_own_state() (project removed from list)
    → EventRepository.log(ProjectRemoved)

═══ Syncthing syncs metadata folder ═══

Members' ReconciliationService.phase_metadata()
  → Reads leader's updated state, project no longer listed
  → Local subscriptions already DECLINED via metadata reconciliation
  → Folder cleanup on next phase_device_lists() (device removed from folders)
```

## Conflict Resolution

| Conflict | Resolution |
|---|---|
| Leader removes member, member hasn't seen it yet | Member keeps syncing until metadata arrives, then auto-leaves. Leader wins. |
| Member declines project, leader re-shares | New subscription created as OFFERED. Member can decline again. |
| Two teams share same project | Separate subscriptions per team. Device lists are union across teams. |
| Leader dissolves team while member is offline | Reconciler reads dissolution from metadata, auto-leaves. |
| Member's machine dies and comes back | Reconciler re-reads metadata, re-establishes state. |

## Metrics

| Metric | v3 | v4 |
|---|---|---|
| Router files | 7 | 4 |
| Service files | 9 | 8 (in packages) |
| DB tables | 7 | 6 |
| Reconciliation phases | 6 | 3 |
| Domain model files | 0 | 5 |
| Repository files | 0 | 5 |
| Estimated sync LOC | ~5,000 | ~3,000 |

## Future Work (Not in v4)

- **Leadership transfer** — `team.transfer_leadership(new_device_id)` method + metadata write
- **Automatic succession** — promote longest-active member after leader offline for X days
- **Network discovery (v4.1)** — LAN-based Karma user discovery via UDP broadcast or Syncthing's local discovery, layered on top of pairing codes
- **Session limit per subscription** — replace removed `sync_session_limit` at subscription level
