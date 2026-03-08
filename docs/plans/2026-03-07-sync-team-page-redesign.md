# Sync & Team Page Redesign

**Date:** 2026-03-07
**Status:** Draft
**Branch:** worktree-syncthing-sync-design

## Problem

The current `/sync` page does too much: Syncthing setup, team CRUD, member management, project assignment, sync status, and activity -- all crammed into a 4-tab layout. The existing `/team` page is a passive read-only browser of remote sessions. Users need clear separation between:

1. **Team management** -- creating teams, adding members, managing who syncs with whom
2. **Sync engine** -- Syncthing setup, watcher status, sync health, activity

## Design Goals

- `/team` becomes the primary team management hub (CRUD teams, members)
- `/sync` becomes focused on Syncthing setup + sync engine status
- Remote sessions move into `/projects/[slug]` as a "Team" tab (context-aware)
- Multi-team support is first-class
- "Join Team" flow uses a join code for maximum convenience

---

## Architecture Overview

### Page Responsibilities (After Redesign)

| Page | Responsibility | Removed From |
|------|---------------|-------------|
| `/sync` | Syncthing install/init wizard + sync engine status | Team CRUD, member mgmt, project assignment |
| `/team` | Team list, create team, join team | Read-only remote session browser |
| `/team/[name]` | Team detail: members, projects, join code, pending devices | N/A (new) |
| `/projects/[slug]` (Team tab) | Remote sessions for this project from teammates | `/team/[user_id]` page |

### What Gets Removed

| Current | Action |
|---------|--------|
| `/sync` TeamTab | Move to `/team/[name]` |
| `/sync` ProjectsTab | Project assignment moves to `/team/[name]`, per-project sync status stays on `/sync` |
| `/sync` Wizard Step 3 (create/join/solo) | Moves to `/team` page (create/join CTAs) |
| `/team` (remote user browser) | Replace with team list |
| `/team/[user_id]` (remote user detail) | Replace with `/team/[name]` (team detail) |
| Remote sessions on `/team/[user_id]` | Move to `/projects/[slug]` Team tab |

---

## Join Code Mechanism

### Problem

Syncthing device IDs carry no team metadata. Users must exchange 56-character device IDs AND coordinate team names separately. This is tedious and error-prone.

### Solution: Join Code

A compact string that encodes team name, user identity, and device ID:

```
Format:  {team_name}:{user_id}:{device_id}
Example: acme:alice:MFZWI3D-BONSGYC-YLTMRWG-C43ENR5-QXGZDMM-FZWI3DP-BONSGYC-ZZZ

Parsing: split on first two ":" chars
  - team_name and user_id are alphanumeric/dash/underscore (no colons)
  - device_id is uppercase alphanumeric with dashes
```

**Why 3 parts?** The `user_id` is critical because:
- It becomes the member name on the joiner's machine
- The member name determines the filesystem inbox path (`remote-sessions/{member_name}/`)
- It must match the remote user's actual `user_id` for folder paths to align correctly

### Generation

When a user creates a team, the join code is auto-generated from:
- `team_name` from the team
- `user_id` from `sync-config.json`
- `device_id` from `sync-config.json` (Syncthing device ID)

Shown prominently on `/team/[name]` with a copy button.

### The Complete Pairing Flow

```
User A (Team Creator)                     User B (Joining)
─────────────────────                     ──────────────────

1. /sync: Install Syncthing               1. /sync: Install Syncthing
2. /sync: Init (name: "alice")            2. /sync: Init (name: "bob")
   -> gets device ID AAA                     -> gets device ID BBB
   -> redirect to /team                      -> redirect to /team

3. /team: "Create Team"
   -> enters name "acme"
   -> team created in SQLite

4. /team/acme: Sees join code              3. /team: "Join Team"
   "acme:alice:AAA..."                        Pastes join code
   -> copies & sends to B via Slack           -> system parses:
                                                 team = "acme"
                                                 leader_name = "alice"
                                                 leader_device = "AAA..."
                                              -> creates team "acme" locally
                                              -> adds member "alice" (device: AAA)
                                              -> pairs AAA in Syncthing
                                              -> auto-accepts pending folders
                                              -> shows: "Share YOUR code back!"
                                                 "acme:bob:BBB..."  [Copy]

                                           4. B sends their code back to A

5. /team/acme: TWO ways to add B:
   Option A: "Add Member" -> paste
     B's code "acme:bob:BBB..."
     -> auto-fills name="bob", device="BBB"
     -> pairs in Syncthing
     -> auto-shares folders

   Option B: Auto-detect pending device
     -> Syncthing shows BBB as pending
     -> team page shows:
        "New device detected: BBB...
         [Accept as team member]"
     -> prompts for name -> "bob"
     -> pairs + shares folders

6. Both have watchers running             5. Watcher auto-started on join
   -> Sessions flow both ways
```

### Why Two Exchanges?

Syncthing requires **mutual pairing** -- both sides must know about each other. This is a security feature: no one can push data to your machine without your consent. The join code makes each exchange a simple copy-paste:

1. A -> B: A's join code (via Slack/email)
2. B -> A: B's join code back (via Slack/email), OR A auto-detects B's pending device

### Pending Device Auto-Detection (Convenience Feature)

After B joins and pairs with A's Syncthing, B's device appears in A's Syncthing as a "pending device" (connected but not configured). We can detect this via Syncthing's `GET /rest/cluster/pending/devices` API.

On A's `/team/[name]` page, we poll for pending devices and show:
```
+--------------------------------------------------+
| Pending Connections                               |
|                                                   |
| A new device is trying to connect:               |
| BBB-DEF456-GHI...                                |
|                                                   |
| Name: [bob_____________]  [Accept as Member]     |
+--------------------------------------------------+
```

This eliminates the need for B to share their code back -- A just accepts the pending device. The user_id still needs to be entered manually (Syncthing pending devices don't carry app-level metadata), but it's a minor friction point.

**New SyncthingClient method needed:**
```python
def get_pending_devices(self) -> dict:
    """Get devices trying to connect that aren't configured."""
    resp = requests.get(
        f"{self.api_url}/rest/cluster/pending/devices",
        headers=self.headers,
        timeout=10,
    )
    resp.raise_for_status()
    return resp.json()
```

---

## Page Designs

### `/sync` -- Sync Engine

#### State 1: Not Configured (Wizard -- Steps 0-2 Only)

```
+--------------------------------------------------+
| Sync                                    [Refresh] |
+--------------------------------------------------+

Step 0: How It Works
+--------------------------------------------------+
|                                                   |
| Share Claude Code sessions across machines        |
| using Syncthing -- peer-to-peer, no cloud.        |
|                                                   |
| 1. Install Syncthing                              |
| 2. Name your machine                              |
| 3. Create or join a team                          |
|                                                   |
|                   [Get Started]                    |
+--------------------------------------------------+

Step 1: Install Syncthing
+--------------------------------------------------+
|                                                   |
| macOS:  brew install syncthing                    |
|         brew services start syncthing             |
|                                                   |
| Linux:  sudo apt install syncthing               |
|         systemctl --user start syncthing          |
|                                                   |
|                   [Check Again]                    |
+--------------------------------------------------+

Step 2: Name This Machine
+--------------------------------------------------+
|                                                   |
| Your Name: [alice___________]                     |
|                                                   |
| This identifies you when sharing sessions         |
| with teammates.                                   |
|                                                   |
| Your Device ID:                                   |
| MFZWI3D-BONSGYC-YLTMRWG-...           [Copy]    |
|                                                   |
|                   [Initialize]                     |
+--------------------------------------------------+

-> After init, redirect to /team
```

#### State 2: Configured (Sync Status Dashboard)

No tabs. A single scrollable page with sections:

```
+--------------------------------------------------+
| Sync                            Last updated: 5s  |
|                                          [Refresh] |
+--------------------------------------------------+

Sync Engine
+--------------------------------------------------+
|                                                   |
| Syncthing   Running  v1.29.0                     |
| Watcher     Running  watching 4 projects         |
|                                  [Stop Watcher]   |
|                                                   |
| Identity:   alice (alice-mbp)                     |
| Device ID:  MFZWI3D-BONSGYC-...        [Copy]    |
+--------------------------------------------------+

Sync Health
+--------------------------------------------------+
| +----------+----------+----------+----------+    |
| | Projects | Sessions | Sessions | Members  |    |
| | Synced   | Packaged | Received | Online   |    |
| |    4     |   127    |    89    |   2/3    |    |
| +----------+----------+----------+----------+    |
+--------------------------------------------------+

Per-Project Sync Status
+--------------------------------------------------+
|                                                   |
| claude-karma        In Sync      127 / 127       |
| hubdata             2 behind      45 / 47        |
| my-app              In Sync       32 / 32        |
| side-project        Syncing       12 / 15        |
|                                                   |
|                              [Sync All Now]       |
+--------------------------------------------------+

Pending Actions                     (only if exist)
+--------------------------------------------------+
|                                                   |
| alice shared 3 project folders    [Accept All]   |
+--------------------------------------------------+

Recent Activity
+--------------------------------------------------+
|                                                   |
| 2m ago   session_packaged   claude-karma         |
| 5m ago   session_packaged   hubdata              |
| 1h ago   member_added      bob (team: acme)     |
| 2h ago   watcher_started   acme                 |
|                                                   |
|                         [View All Activity]       |
+--------------------------------------------------+

Danger Zone
+--------------------------------------------------+
|                                                   |
|                 [Reset Sync Setup]                 |
|                                                   |
| This will delete your sync config, stop the       |
| watcher, and clear all team data.                 |
+--------------------------------------------------+
```

### `/team` -- Team List

#### State 1: Sync Not Configured

```
+--------------------------------------------------+
| Teams                                             |
+--------------------------------------------------+

+--------------------------------------------------+
|                                                   |
|     Set up sync first                             |
|                                                   |
|     Before creating or joining a team, you need   |
|     to install Syncthing and initialize sync.     |
|                                                   |
|              [Go to Sync Setup]                    |
+--------------------------------------------------+
```

#### State 2: No Teams Yet

```
+--------------------------------------------------+
| Teams                                             |
+--------------------------------------------------+

+--------------------------------------------------+
|                                                   |
|     No teams yet                                  |
|                                                   |
|     Create a team to start sharing sessions       |
|     with teammates, or join an existing team.     |
|                                                   |
|     [Create Team]         [Join Team]              |
+--------------------------------------------------+
```

#### State 3: Has Teams

```
+--------------------------------------------------+
| Teams                     [Create Team] [Join Team]|
+--------------------------------------------------+

+-----------------------------+  +-----------------------------+
| acme                        |  | personal-sync               |
| syncthing                   |  | syncthing                   |
|                             |  |                             |
| 3 members  |  4 projects   |  | 1 member   |  2 projects   |
| 2 online                   |  | 1 online                   |
+-----------------------------+  +-----------------------------+
```

Each card links to `/team/[name]`.

#### Create Team Dialog

```
+--------------------------------------------------+
| Create Team                                       |
|                                                   |
| Team Name: [acme___________]                      |
|                                                   |
| This name will be shared with teammates.          |
| Use lowercase letters, numbers, dashes.           |
|                                                   |
|              [Cancel]    [Create]                   |
+--------------------------------------------------+
```

After creation, redirects to `/team/[name]` where the join code is shown.

#### Join Team Dialog

```
+--------------------------------------------------+
| Join Team                                         |
|                                                   |
| Paste the join code from your team creator:       |
|                                                   |
| [acme:alice:MFZWI3D-BONSGYC-YLTMRWG-C43E...]    |
|                                                   |
| Detected:                                         |
|   Team:   acme                                    |
|   Leader: alice                                   |
|   Device: MFZWI3D-BON...                         |
|                                                   |
|              [Cancel]    [Join Team]               |
+--------------------------------------------------+
```

The "Detected" section appears live as the user pastes, giving instant feedback that the code parsed correctly.

After joining:

```
+--------------------------------------------------+
| Joined "acme"!                                    |
|                                                   |
| You're now connected to alice's team.             |
| Syncthing will start exchanging sessions          |
| once alice accepts your device.                   |
|                                                   |
| Share YOUR code back with alice:                  |
| +----------------------------------------------+ |
| | acme:bob:DEF456-GHI789-JKL012-...           | |
| |                                       [Copy] | |
| +----------------------------------------------+ |
|                                                   |
|              [Go to Team Page]                     |
+--------------------------------------------------+
```

### `/team/[name]` -- Team Detail

```
+--------------------------------------------------+
| Teams > acme                        [Delete Team] |
+--------------------------------------------------+

Join Code
+--------------------------------------------------+
|                                                   |
| Share this with teammates to let them join:       |
| +----------------------------------------------+ |
| | acme:alice:MFZWI3D-BONSGYC-YLTMRWG-C43E...  | |
| |                                       [Copy] | |
| +----------------------------------------------+ |
+--------------------------------------------------+

Pending Connections              (only if detected)
+--------------------------------------------------+
|                                                   |
| A new device is trying to connect:               |
| DEF456-GHI789-JKL...                             |
|                                                   |
| Name: [_______________]    [Accept as Member]    |
+--------------------------------------------------+

Members (3)                          [Add Member]
+--------------------------------------------------+
| You (alice)                                       |
|   MFZWI3D-BON...                     Online      |
+--------------------------------------------------+
| bob                                               |
|   DEF456-GHI...                       Online      |
|   Last seen: 2m ago                    [Remove]   |
+--------------------------------------------------+
| charlie                                           |
|   XYZ789-ABC...                       Offline     |
|   Last seen: 3h ago                   [Remove]    |
+--------------------------------------------------+

Shared Projects (4)                [Add Projects]
+--------------------------------------------------+
| claude-karma       /Users/.../claude-karma        |
|                                        [Remove]   |
| hubdata            /Users/.../hubdata             |
|                                        [Remove]   |
| my-app             /Users/.../my-app              |
|                                        [Remove]   |
+--------------------------------------------------+
```

#### Add Member Dialog

Accepts either a join code OR manual name + device ID:

```
+--------------------------------------------------+
| Add Team Member                                   |
|                                                   |
| Paste their join code:                            |
| [acme:bob:DEF456-GHI789-JKL012-...]              |
|                                                   |
| Detected:                                         |
|   Name:   bob                                     |
|   Device: DEF456-GHI...                           |
|                                                   |
| -- or enter manually --                           |
|                                                   |
| Name:      [_______________]                      |
| Device ID: [_______________]                      |
|                                                   |
|              [Cancel]    [Add Member]              |
+--------------------------------------------------+
```

When a join code is pasted, the name and device ID fields auto-populate from the parsed values. The user can edit if needed.

#### Add Projects Dialog

```
+--------------------------------------------------+
| Share Projects with "acme"                        |
|                                                   |
| Select projects to sync:                          |
|                                                   |
| [ ] claude-karma     /Users/.../claude-karma     |
| [ ] hubdata          /Users/.../hubdata          |
| [x] side-project     /Users/.../side-project     |
| [x] experiments      /Users/.../experiments      |
|                                                   |
| Already shared: claude-karma, hubdata            |
|                                                   |
|              [Cancel]    [Share Selected]          |
+--------------------------------------------------+
```

Projects already in the team are shown separately (not in the checkbox list) to avoid confusion.

### `/projects/[slug]` -- New "Team" Tab

Added alongside existing tabs (Overview, Agents, Skills, Tools, Memory, Analytics, Archived):

```
Tabs: [Overview] [Agents] [Skills] [Tools] [Memory] [Analytics] [Team] [Archived]
```

The "Team" tab only appears if there are remote sessions for this project.

#### Team Tab Content

```
+--------------------------------------------------+
| Team Sessions                                     |
|                                                   |
| Sessions shared by teammates for this project.    |
+--------------------------------------------------+

+--------------------------------------------------+
| bob (12 sessions)                                |
| Last synced: 5m ago | Machine: bob-mbp           |
+--------------------------------------------------+
| 2m ago   a1b2c3d4   1.2 MB   "Fix auth bug"    |
| 1h ago   e5f6g7h8   890 KB   "Add user API"    |
| 3h ago   i9j0k1l2   2.1 MB                     |
| ...                         [Show all 12]       |
+--------------------------------------------------+

+--------------------------------------------------+
| charlie (7 sessions)                             |
| Last synced: 3h ago | Machine: charlie-desktop   |
+--------------------------------------------------+
| 3h ago   m3n4o5p6   1.5 MB   "Refactor DB"     |
| 5h ago   q7r8s9t0   445 KB                     |
+--------------------------------------------------+
```

Each session row links to `/projects/[slug]/[session_uuid]` -- the existing session viewer already handles remote sessions via `find_remote_session()` fallback.

If no remote sessions exist:
```
+--------------------------------------------------+
| No team sessions yet                              |
|                                                   |
| Once teammates share this project via a team,     |
| their sessions will appear here.                  |
|                                                   |
|              [Go to Teams]                         |
+--------------------------------------------------+
```

---

## API Changes

### New Endpoints

| Method | Endpoint | Purpose |
|--------|----------|---------|
| `POST` | `/sync/teams/join` | Join a team via join code |
| `GET` | `/sync/teams/{name}/join-code` | Get join code for a team |
| `GET` | `/sync/pending-devices` | List pending Syncthing devices |
| `GET` | `/projects/{slug}/remote-sessions` | Remote sessions for a specific project, grouped by user |

### Modified Endpoints

| Endpoint | Change |
|----------|--------|
| `GET /sync/status` | Add `device_id` field to response |

### New SyncthingClient Method

```python
# cli/karma/syncthing.py
def get_pending_devices(self) -> dict:
    """Get devices trying to connect that aren't configured.
    Returns dict keyed by device_id with connection details."""
    resp = requests.get(
        f"{self.api_url}/rest/cluster/pending/devices",
        headers=self.headers,
        timeout=10,
    )
    resp.raise_for_status()
    return resp.json()
```

### New: `POST /sync/teams/join`

```python
class JoinTeamRequest(BaseModel):
    join_code: str  # "team_name:user_id:DEVICE-ID-..."

@router.post("/teams/join")
async def sync_join_team(req: JoinTeamRequest):
    # 1. Parse join code (team_name:user_id:device_id)
    parts = req.join_code.split(":", 2)
    if len(parts) != 3:
        raise HTTPException(400, "Invalid join code format. Expected team:user:device_id")
    team_name, leader_name, device_id = parts

    # 2. Validate all parts
    validate_user_id(team_name)
    validate_user_id(leader_name)
    validate_device_id(device_id)

    # 3. Load identity (must be initialized)
    config = await run_sync(_load_identity)
    if config is None:
        raise HTTPException(400, "Not initialized. Run sync setup first.")

    conn = _get_sync_conn()

    # 4. Create team locally (if not exists)
    if get_team(conn, team_name) is None:
        create_team(conn, team_name, "syncthing")
        log_event(conn, "team_created", team_name=team_name)

    # 5. Add leader as member (with their user_id as the name)
    try:
        add_member(conn, team_name, leader_name, device_id=device_id)
        log_event(conn, "member_added", team_name=team_name, member_name=leader_name)
    except Exception:
        pass  # already exists (idempotent)

    # 6. Pair device in Syncthing (best-effort)
    paired = False
    try:
        proxy = get_proxy()
        await run_sync(proxy.add_device, device_id, leader_name)
        paired = True
    except Exception:
        pass

    # 7. Auto-accept pending folders from the leader
    accepted = 0
    try:
        from karma.syncthing import SyncthingClient, read_local_api_key
        api_key = config.syncthing.api_key or await run_sync(read_local_api_key)
        st = SyncthingClient(api_key=api_key)
        if st.is_running():
            from karma.main import _accept_pending_folders
            accepted = await run_sync(_accept_pending_folders, st, config, conn)
            if accepted:
                log_event(conn, "pending_accepted", detail={"count": accepted})
    except Exception:
        pass

    # 8. Generate joiner's own code to share back
    own_device_id = config.syncthing.device_id if config.syncthing else None
    own_join_code = f"{team_name}:{config.user_id}:{own_device_id}" if own_device_id else None

    return {
        "ok": True,
        "team_name": team_name,
        "leader_name": leader_name,
        "paired": paired,
        "accepted_folders": accepted,
        "your_join_code": own_join_code,
    }
```

### New: `GET /sync/teams/{name}/join-code`

```python
@router.get("/teams/{team_name}/join-code")
async def sync_team_join_code(team_name: str):
    if not ALLOWED_PROJECT_NAME.match(team_name):
        raise HTTPException(400, "Invalid team name")

    config = await run_sync(_load_identity)
    if config is None:
        raise HTTPException(400, "Not initialized")

    conn = _get_sync_conn()
    if get_team(conn, team_name) is None:
        raise HTTPException(404, f"Team '{team_name}' not found")

    device_id = config.syncthing.device_id if config.syncthing else None
    if not device_id:
        raise HTTPException(400, "No Syncthing device ID configured")

    join_code = f"{team_name}:{config.user_id}:{device_id}"
    return {"join_code": join_code, "team_name": team_name, "user_id": config.user_id}
```

### New: `GET /sync/pending-devices`

```python
@router.get("/pending-devices")
async def sync_pending_devices():
    """List Syncthing devices trying to connect that aren't configured."""
    conn = _get_sync_conn()
    known = get_known_devices(conn)

    proxy = get_proxy()
    try:
        pending = await run_sync(proxy.get_pending_devices)
    except SyncthingNotRunning:
        return {"devices": []}

    # Filter out devices we already know
    known_device_ids = set(known.keys())
    result = []
    for device_id, info in pending.items():
        if device_id not in known_device_ids:
            result.append({
                "device_id": device_id,
                "name": info.get("name", ""),
                "address": info.get("address", ""),
                "time": info.get("time", ""),
            })

    return {"devices": result}
```

### New: `GET /projects/{slug}/remote-sessions`

```python
# In api/routers/projects.py or a new endpoint in sessions.py

@router.get("/projects/{project_slug}/remote-sessions")
async def project_remote_sessions(project_slug: str):
    """Get remote sessions for a project, grouped by remote user."""
    validate_project_name(project_slug)

    from services.remote_sessions import list_remote_sessions_for_project
    from karma.config import SyncConfig

    config = SyncConfig.load() if SyncConfig else None
    local_user = config.user_id if config else None

    remote_base = Path.home() / ".claude_karma" / "remote-sessions"
    if not remote_base.is_dir():
        return {"users": []}

    users = []
    for user_dir in sorted(remote_base.iterdir()):
        if not user_dir.is_dir():
            continue
        # Skip our own outbox
        if local_user and user_dir.name == local_user:
            continue

        project_dir = user_dir / project_slug
        if not project_dir.is_dir():
            continue

        sessions_dir = project_dir / "sessions"
        manifest_path = project_dir / "manifest.json"

        sessions = []
        if sessions_dir.is_dir():
            for f in sorted(sessions_dir.glob("*.jsonl"), key=lambda p: p.stat().st_mtime, reverse=True):
                if f.name.startswith("agent-"):
                    continue
                sessions.append({
                    "uuid": f.stem,
                    "mtime": f.stat().st_mtime,
                    "size_bytes": f.stat().st_size,
                })

        manifest = {}
        if manifest_path.exists():
            import json
            try:
                manifest = json.loads(manifest_path.read_text())
            except (json.JSONDecodeError, OSError):
                pass

        if sessions:
            users.append({
                "user_id": user_dir.name,
                "machine_id": manifest.get("machine_id"),
                "synced_at": manifest.get("synced_at"),
                "session_count": len(sessions),
                "sessions": sessions,
            })

    return {"users": users}
```

### Modified: `GET /sync/status`

Add `device_id` to the response:

```python
@router.get("/status")
async def sync_status():
    config = await run_sync(_load_identity)
    if config is None:
        return {"configured": False}

    # ... existing team loading code ...

    return {
        "configured": True,
        "user_id": config.user_id,
        "machine_id": config.machine_id,
        "device_id": config.syncthing.device_id if config.syncthing else None,  # NEW
        "teams": teams,
    }
```

---

## Frontend Changes

### Files to Create

| File | Purpose |
|------|---------|
| `frontend/src/routes/team/+page.svelte` | **Rewrite**: team list with create/join CTAs |
| `frontend/src/routes/team/+page.server.ts` | **Rewrite**: fetch from `GET /sync/teams` + `GET /sync/status` |
| `frontend/src/routes/team/[name]/+page.svelte` | New: team detail (members, projects, join code, pending devices) |
| `frontend/src/routes/team/[name]/+page.server.ts` | New: fetch team detail + devices + join code + pending devices |
| `frontend/src/lib/components/team/TeamCard.svelte` | Team list card (name, member count, project count, online count) |
| `frontend/src/lib/components/team/TeamMemberCard.svelte` | Member card with connection status (online/offline/last seen) |
| `frontend/src/lib/components/team/JoinTeamDialog.svelte` | Join code paste dialog with live parsing feedback |
| `frontend/src/lib/components/team/CreateTeamDialog.svelte` | Team name input dialog |
| `frontend/src/lib/components/team/AddMemberDialog.svelte` | Paste join code OR manual name + device ID |
| `frontend/src/lib/components/team/AddProjectDialog.svelte` | Project selection checkbox dialog |
| `frontend/src/lib/components/team/JoinCodeCard.svelte` | Prominent join code display with copy button |
| `frontend/src/lib/components/team/PendingDeviceCard.svelte` | Pending device with name input + accept button |
| `frontend/src/lib/components/team/JoinSuccessCard.svelte` | Post-join confirmation with "share your code back" CTA |
| `frontend/src/lib/components/project/RemoteSessionsTab.svelte` | Team tab in project detail page |

### Files to Modify

| File | Change |
|------|--------|
| `frontend/src/routes/sync/+page.svelte` | Remove TeamTab, ProjectsTab, TeamSelector imports. Remove 4-tab structure. Replace with sync status dashboard (single page, no tabs). Keep wizard but remove step 3. |
| `frontend/src/routes/sync/+page.server.ts` | Simplify: only fetch detect, status, watch status. Remove pending fetch (moves to sync status dashboard inline). |
| `frontend/src/lib/components/sync/SetupWizard.svelte` | Remove step 3 (create/join/solo). After init, redirect to `/team`. |
| `frontend/src/routes/projects/[project_slug]/+page.svelte` | Add "Team" tab with `RemoteSessionsTab` component. Tab only shown if remote sessions exist. |
| `frontend/src/routes/projects/[project_slug]/+page.server.ts` | Fetch `GET /projects/{slug}/remote-sessions` count for tab badge. |
| `frontend/src/lib/components/Header.svelte` | Rename "Team" nav item to "Teams" |

### Files to Delete

| File | Reason |
|------|--------|
| `frontend/src/lib/components/sync/TeamTab.svelte` | Replaced by `/team/[name]` |
| `frontend/src/lib/components/sync/ProjectsTab.svelte` | Project assignment to `/team/[name]`, sync status to `/sync` dashboard |
| `frontend/src/lib/components/sync/TeamSelector.svelte` | No longer needed -- team selection happens on `/team` list page |
| `frontend/src/lib/components/sync/MembersTab.svelte` | Already superseded, now fully replaced |
| `frontend/src/routes/team/[user_id]/+page.svelte` | Replaced by `/team/[name]` |
| `frontend/src/routes/team/[user_id]/+page.server.ts` | Replaced by `/team/[name]` |

### Navigation Sidebar

```
Before:                     After:
  Dashboard                   Dashboard
  Projects                    Projects
  Sessions                    Sessions
  Team          ->            Teams        (links to /team)
  Sync                        Sync         (links to /sync)
  Analytics                   Analytics
  ...                         ...
```

---

## Implementation Phases

### Phase 1: API -- Join Code + Pending Devices + Remote Sessions per Project

1. Add `get_pending_devices()` to `SyncthingClient` and `SyncthingProxy`
2. Add `POST /sync/teams/join` endpoint (parse 3-part code, create team, pair, accept)
3. Add `GET /sync/teams/{name}/join-code` endpoint
4. Add `GET /sync/pending-devices` endpoint
5. Add `GET /projects/{slug}/remote-sessions` endpoint
6. Add `device_id` to `GET /sync/status` response
7. Write tests for join code parsing, validation, and the join flow

### Phase 2: Frontend -- `/team` Page Rewrite

1. Rewrite `/team/+page.svelte` as team list (grid of TeamCards, create/join CTAs)
2. Rewrite `/team/+page.server.ts` to fetch from `GET /sync/teams` + `GET /sync/status`
3. Build `CreateTeamDialog` component
4. Build `JoinTeamDialog` component with live code parsing
5. Build `JoinSuccessCard` with "share your code back" CTA
6. Handle "sync not configured" state (redirect to `/sync`)

### Phase 3: Frontend -- `/team/[name]` Team Detail

1. Create `/team/[name]/+page.svelte` with sections: join code, pending devices, members, projects
2. Create `/team/[name]/+page.server.ts` (fetch team, devices, join code, pending devices)
3. Build `JoinCodeCard` component (prominent display, copy button)
4. Build `PendingDeviceCard` component (name input, accept button)
5. Build `TeamMemberCard` component (connection status, remove button)
6. Build `AddMemberDialog` (paste code OR manual entry, auto-parse)
7. Build `AddProjectDialog` (checkbox list of projects)
8. Add polling for pending devices and member connection status

### Phase 4: Frontend -- `/sync` Page Simplification

1. Remove TeamTab, ProjectsTab, TeamSelector, OverviewTab imports
2. Remove 4-tab structure entirely
3. Remove wizard step 3 (create/join/solo)
4. Add redirect to `/team` after wizard step 2 init
5. Build sync status dashboard sections:
   - Sync Engine card (Syncthing status, watcher, device ID)
   - Sync Health stats row
   - Per-project sync status list (read-only, from `GET /sync/teams/{name}/project-status`)
   - Pending folder actions
   - Recent activity list
   - Danger zone (reset)

### Phase 5: Frontend -- Project Team Tab

1. Create `RemoteSessionsTab.svelte` component
2. Add "Team" tab to project detail page tabs
3. Fetch `GET /projects/{slug}/remote-sessions` on tab activation
4. Render grouped by user with session list and links
5. Conditionally show tab only when remote sessions exist (use count from server load)

### Phase 6: Cleanup

1. Delete deprecated components (TeamTab, ProjectsTab, TeamSelector, MembersTab)
2. Delete `/team/[user_id]` route files
3. Update navigation sidebar (Team -> Teams)
4. Update `CLAUDE.md` route tables and component lists
5. Update `api-types.ts` with any new/changed types

---

## Design Decisions (Resolved)

| Question | Decision | Rationale |
|----------|----------|-----------|
| Member name matching | Join code includes `user_id` -- auto-used as member name | Filesystem inbox path must match remote user's `user_id` for folder alignment |
| Bidirectional pairing | Join success shows "share YOUR code back" + pending device auto-detection | Two mechanisms for convenience -- code exchange OR auto-detect |
| Watcher auto-start | Auto-start on join, manual control on `/sync` | Reduces friction for joiners; power users can stop/start from sync page |
| Project opt-in on join | Accept all pending folders automatically | Joiners get whatever the team shares; they can remove projects later from `/team/[name]` |
| Multi-team | First-class -- `/team` is a list view, each team has its own detail page | Supports real use case of personal sync + work team |
| Where are remote sessions? | `/projects/[slug]` Team tab (context-aware) | More useful than a separate page -- see teammate sessions alongside your own |
| Join code format | `team:user_id:device_id` (3 parts, colon-separated) | Readable, debuggable, carries all needed info, no server required |
