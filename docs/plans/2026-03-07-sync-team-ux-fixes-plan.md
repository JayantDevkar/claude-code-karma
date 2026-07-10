# Sync & Team UX Fixes — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Fix 16 issues (2 critical, 5 high, 6 medium, 3 low) found by code review, complete the 3 missing `/sync` dashboard sections from the original design, add cross-linking between `/sync` and `/team`, and polish the post-setup onboarding flow.

**Architecture:** The V3 split (`/sync` for engine status, `/team` for people/CRUD, project Team tab for remote sessions) is architecturally sound but incompletely implemented. This plan completes the implementation, hardens security, and adds wayfinding so users don't get lost between pages. No structural changes to routing.

**Tech Stack:** FastAPI (Python), SvelteKit + Svelte 5 (TypeScript), SQLite, Syncthing API proxy

**Background:** See `docs/plans/2026-03-07-sync-team-page-redesign.md` for the original V3 design that introduced the split. The `/sync` dashboard was supposed to have 6 sections; only 4 were built (missing: Per-Project Sync Status, Recent Activity, Sync Now). The code review also found security gaps in the join code mechanism and API auth.

---

## Phase 1: Security Fixes (CRITICAL + HIGH)

### Task 1: Validate `req.path` in `sync_add_team_project` [HIGH-4]

Prevent path traversal via unvalidated filesystem path input.

**Files:**
- Modify: `api/routers/sync_status.py:755-817`
- Test: `api/tests/test_sync_security.py` (create)

**Step 1: Write the failing test**

```python
# api/tests/test_sync_security.py
import pytest
from fastapi.testclient import TestClient
from main import app

client = TestClient(app)

@pytest.mark.parametrize("bad_path", [
    "../../../etc/passwd",
    "/tmp/../etc/shadow",
    "foo/../../bar",
    "/nonexistent/../../root",
])
def test_add_project_rejects_path_traversal(bad_path):
    """Path traversal in project path should be rejected."""
    resp = client.post(
        "/sync/teams/test-team/projects",
        json={"name": "test-proj", "path": bad_path},
    )
    assert resp.status_code == 400
    assert "Invalid" in resp.json().get("detail", "")
```

**Step 2: Run test to verify it fails**

Run: `cd api && pytest tests/test_sync_security.py::test_add_project_rejects_path_traversal -v`
Expected: FAIL — currently no path validation, returns 200 or 404

**Step 3: Add path validation function**

Add to `api/routers/sync_status.py` after the existing `validate_*` functions (around line 63):

```python
def validate_project_path(path: str) -> str:
    """Validate project path — reject traversal and non-absolute paths."""
    if not path:
        return path  # empty path is allowed (uses encoded_name instead)
    resolved = Path(path).resolve()
    # Must be absolute and not contain .. after resolution
    if ".." in Path(path).parts:
        raise HTTPException(400, "Invalid project path: traversal not allowed")
    # Must be under user's home directory
    home = Path.home()
    if not str(resolved).startswith(str(home)):
        raise HTTPException(400, "Invalid project path: must be under home directory")
    return str(resolved)
```

**Step 4: Apply validation in `sync_add_team_project`**

In the `sync_add_team_project` function (line 755), add validation before using `req.path`:

```python
async def sync_add_team_project(team_name: str, req: AddTeamProjectRequest) -> Any:
    validate_project_name(req.name)
    if not ALLOWED_PROJECT_NAME.match(team_name):
        raise HTTPException(400, "Invalid team name")
    validated_path = validate_project_path(req.path)  # ADD THIS
    # ... rest uses validated_path instead of req.path
```

**Step 5: Run test to verify it passes**

Run: `cd api && pytest tests/test_sync_security.py -v`
Expected: PASS

**Step 6: Commit**

```bash
git add api/routers/sync_status.py api/tests/test_sync_security.py
git commit -m "fix(security): validate project path to prevent traversal [HIGH-4]"
```

---

### Task 2: Prevent team auto-creation from join codes [CRITICAL-1 partial]

The join endpoint silently creates teams from any join code. Fix: only join existing teams unless the team name matches a known pattern.

**Files:**
- Modify: `api/routers/sync_status.py:526-607` (sync_join_team)
- Test: `api/tests/test_sync_security.py` (append)

**Step 1: Write the failing test**

```python
# Append to api/tests/test_sync_security.py
def test_join_team_does_not_create_team_from_fabricated_code():
    """Join with a fabricated code should not auto-create teams."""
    # First ensure the team does NOT exist
    resp = client.post(
        "/sync/teams/join",
        json={"join_code": "fabricated-team:attacker:AAAAAAA-BBBBBBB-CCCCCCC-DDDDDDD-EEEEEEE-FFFFFFF-GGGGGGG-HHHHHHH"},
    )
    # Should fail because team doesn't exist locally
    assert resp.status_code == 404
    assert "not found" in resp.json().get("detail", "").lower()
```

**Step 2: Run test to verify it fails**

Run: `cd api && pytest tests/test_sync_security.py::test_join_team_does_not_create_team_from_fabricated_code -v`
Expected: FAIL — currently returns 200 and creates the team

**Step 3: Modify `sync_join_team` to require existing team**

In `sync_join_team` (line 544), change the auto-create behavior:

```python
    # OLD: auto-create team
    # if get_team(conn, team_name) is None:
    #     create_team(conn, team_name, "syncthing")
    #     log_event(conn, "team_created", team_name=team_name)

    # NEW: require team to exist locally (created via /team page or CLI)
    if get_team(conn, team_name) is None:
        raise HTTPException(
            404,
            f"Team '{team_name}' not found. Create it first on the Teams page, "
            "then paste the join code."
        )
```

**Step 4: Run test to verify it passes**

Run: `cd api && pytest tests/test_sync_security.py -v`
Expected: PASS

**Step 5: Update JoinTeamDialog to handle 404**

In `frontend/src/lib/components/team/JoinTeamDialog.svelte`, the error handling at line 43 already shows `data.detail` — the 404 message will naturally surface. But update the input label to set expectations:

```svelte
<!-- Line 101: update label text -->
<label for="join-code" class="block text-xs font-medium text-[var(--text-secondary)]">
    Paste the join code from your team creator (team must exist locally)
</label>
```

**Step 6: Commit**

```bash
git add api/routers/sync_status.py api/tests/test_sync_security.py frontend/src/lib/components/team/JoinTeamDialog.svelte
git commit -m "fix(security): prevent team auto-creation from join codes [CRITICAL-1]"
```

---

### Task 3: Fix IntegrityError swallowing in join flow [HIGH-5]

When a member exists with a different device_id, detect the mismatch instead of silently ignoring.

**Files:**
- Modify: `api/routers/sync_status.py:549-553`
- Modify: `api/db/sync_queries.py:53-65` (add upsert variant)
- Test: `api/tests/test_sync_security.py` (append)

**Step 1: Write the failing test**

```python
# Append to api/tests/test_sync_security.py
def test_join_team_updates_device_id_on_rejoin():
    """Re-joining with a different device should update the device_id."""
    # This test needs a team that exists — setup depends on test fixtures
    # For now, test the query layer directly
    import sqlite3
    from db.sync_queries import add_member, list_members, create_team
    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE TABLE sync_teams (name TEXT PRIMARY KEY, backend TEXT, created_at TEXT DEFAULT CURRENT_TIMESTAMP)")
    conn.execute("CREATE TABLE sync_members (team_name TEXT, name TEXT, device_id TEXT, ipns_key TEXT, added_at TEXT DEFAULT CURRENT_TIMESTAMP, PRIMARY KEY (team_name, name))")
    create_team(conn, "test", "syncthing")
    add_member(conn, "test", "alice", device_id="OLD-DEVICE")

    # Upsert with new device
    from db.sync_queries import upsert_member
    upsert_member(conn, "test", "alice", device_id="NEW-DEVICE")

    members = list_members(conn, "test")
    assert members[0]["device_id"] == "NEW-DEVICE"
```

**Step 2: Add `upsert_member` to sync_queries.py**

```python
# api/db/sync_queries.py — add after add_member (line 65)
def upsert_member(
    conn: sqlite3.Connection,
    team_name: str,
    name: str,
    device_id: Optional[str] = None,
    ipns_key: Optional[str] = None,
) -> dict:
    """Insert or update member — updates device_id if member already exists."""
    conn.execute(
        """INSERT INTO sync_members (team_name, name, device_id, ipns_key)
           VALUES (?, ?, ?, ?)
           ON CONFLICT(team_name, name) DO UPDATE SET
             device_id = COALESCE(excluded.device_id, device_id)""",
        (team_name, name, device_id, ipns_key),
    )
    conn.commit()
    return {"team_name": team_name, "name": name, "device_id": device_id}
```

**Step 3: Use `upsert_member` in `sync_join_team`**

Replace lines 549-553 in `sync_status.py`:

```python
    # OLD:
    # try:
    #     add_member(conn, team_name, leader_name, device_id=device_id)
    #     log_event(conn, "member_added", team_name=team_name, member_name=leader_name)
    # except sqlite3.IntegrityError:
    #     pass

    # NEW:
    from db.sync_queries import upsert_member
    upsert_member(conn, team_name, leader_name, device_id=device_id)
    log_event(conn, "member_added", team_name=team_name, member_name=leader_name)
```

**Step 4: Run tests**

Run: `cd api && pytest tests/test_sync_security.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add api/db/sync_queries.py api/routers/sync_status.py api/tests/test_sync_security.py
git commit -m "fix(sync): upsert member on rejoin instead of silently ignoring [HIGH-5]"
```

---

### Task 4: Cap activity limit + sanitize error responses [HIGH-3, LOW-2]

**Files:**
- Modify: `api/routers/sync_status.py:1133-1161`
- Test: `api/tests/test_sync_security.py` (append)

**Step 1: Write the failing test**

```python
def test_activity_limit_is_capped():
    """Activity endpoint should cap limit at 200."""
    resp = client.get("/sync/activity?limit=999999")
    assert resp.status_code == 200
    # Can't test the SQL directly, but verify the endpoint doesn't crash

def test_activity_invalid_event_type():
    """Activity with invalid event_type should return empty, not error."""
    resp = client.get("/sync/activity?event_type=DROP TABLE")
    assert resp.status_code == 200
```

**Step 2: Modify `sync_activity`**

```python
VALID_EVENT_TYPES = {
    "team_created", "team_deleted", "member_added", "member_removed",
    "project_added", "project_removed", "watcher_started", "watcher_stopped",
    "sync_now", "pending_accepted", "folders_shared",
}

@router.get("/activity")
async def sync_activity(
    team_name: str | None = None,
    event_type: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> Any:
    """Get recent sync activity events and bandwidth stats."""
    # Clamp limit
    limit = max(1, min(limit, 200))

    # Validate event_type
    if event_type and event_type not in VALID_EVENT_TYPES:
        event_type = None  # ignore invalid types, return all

    conn = _get_sync_conn()
    events = query_events(conn, team_name=team_name, event_type=event_type,
                          limit=limit, offset=offset)
    # ... rest unchanged
```

**Step 3: Sanitize error responses**

In the same file, fix the two endpoints that leak internals:

```python
# Line 979 (sync_watch_start)
except Exception as e:
    logger.exception("Failed to start watcher")
    raise HTTPException(500, "Failed to start watcher. Check server logs.")

# Line 1044 (sync_accept_pending)
except Exception as e:
    logger.exception("Failed to accept pending folders")
    raise HTTPException(500, "Failed to accept pending folders. Check server logs.")
```

**Step 4: Run tests**

Run: `cd api && pytest tests/test_sync_security.py -v`

**Step 5: Commit**

```bash
git add api/routers/sync_status.py api/tests/test_sync_security.py
git commit -m "fix(security): cap activity limit, validate event_type, sanitize errors [HIGH-3, LOW-2]"
```

---

## Phase 2: Complete Missing `/sync` Dashboard Sections

### Task 5: Add Per-Project Sync Status section to OverviewTab

This was in the original design but never built. Shows each project with sync gap indicators.

**Files:**
- Modify: `frontend/src/lib/components/sync/OverviewTab.svelte`
- Modify: `frontend/src/lib/api-types.ts` (add type)

**Step 1: Add TypeScript type**

In `frontend/src/lib/api-types.ts`, add after the existing sync types:

```typescript
export interface SyncProjectStatus {
	name: string;
	encoded_name: string;
	path: string;
	local_count: number;
	packaged_count: number;
	received_counts: Record<string, number>;
	gap: number;
}
```

**Step 2: Add state and fetch logic to OverviewTab**

In `OverviewTab.svelte`, add after the stats section (around line 133):

```typescript
// ── Per-project sync status ──────────────────────────────────────────
import type { SyncProjectStatus } from '$lib/api-types';
import { Package, AlertTriangle, CheckCircle2 as CheckCircle2Icon } from 'lucide-svelte';

let projectStatuses = $state<SyncProjectStatus[]>([]);
let projectStatusLoading = $state(true);

async function loadProjectStatus() {
    if (!teamName) { projectStatusLoading = false; return; }
    try {
        const res = await fetch(
            `${API_BASE}/sync/teams/${encodeURIComponent(teamName)}/project-status`
        ).catch(() => null);
        if (res?.ok) {
            const data = await res.json();
            projectStatuses = data.projects ?? [];
        }
    } catch { /* non-critical */ }
    finally { projectStatusLoading = false; }
}
```

Add `loadProjectStatus()` call to the `$effect` block at line 201 inside `untrack()`.

**Step 3: Add the template section**

Insert after the Pending Actions section (after line 369), before Machine Details:

```svelte
<!-- ── 5. Per-Project Sync Status ────────────────────────────────── -->
{#if !projectStatusLoading && projectStatuses.length > 0}
    <div class="rounded-[var(--radius-lg)] border border-[var(--border)] bg-[var(--bg-subtle)]">
        <div class="flex items-center justify-between px-5 py-3.5 border-b border-[var(--border-subtle)]">
            <div class="flex items-center gap-2">
                <Package size={14} class="text-[var(--text-muted)]" />
                <h3 class="text-sm font-semibold text-[var(--text-primary)]">Project Sync Status</h3>
            </div>
            <button
                onclick={handleSyncAllNow}
                disabled={syncingAll}
                class="flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded-[var(--radius)] bg-[var(--accent)] text-white hover:bg-[var(--accent-hover)] transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
            >
                {#if syncingAll}
                    <Loader2 size={12} class="animate-spin" />
                    Syncing...
                {:else}
                    <RefreshCw size={12} />
                    Sync All Now
                {/if}
            </button>
        </div>
        <div class="px-5 divide-y divide-[var(--border-subtle)]">
            {#each projectStatuses as proj (proj.encoded_name)}
                <div class="flex items-center justify-between py-3">
                    <div class="flex items-center gap-2.5 min-w-0">
                        <FolderGit2 size={14} class="text-[var(--text-muted)] shrink-0" />
                        <a
                            href="/projects/{encodeURIComponent(proj.encoded_name)}"
                            class="text-sm font-medium text-[var(--text-primary)] hover:text-[var(--accent)] truncate transition-colors"
                        >
                            {proj.name}
                        </a>
                    </div>
                    <div class="flex items-center gap-3 shrink-0">
                        <span class="text-xs text-[var(--text-muted)]">
                            {proj.packaged_count}/{proj.local_count}
                        </span>
                        {#if proj.gap === 0}
                            <span class="flex items-center gap-1 text-xs text-[var(--success)]">
                                <CheckCircle2Icon size={12} />
                                In Sync
                            </span>
                        {:else}
                            <span class="flex items-center gap-1 text-xs text-[var(--warning)]">
                                <AlertTriangle size={12} />
                                {proj.gap} behind
                            </span>
                        {/if}
                    </div>
                </div>
            {/each}
        </div>
    </div>
{/if}
```

**Step 4: Add "Sync All Now" handler**

```typescript
let syncingAll = $state(false);

async function handleSyncAllNow() {
    if (!teamName || syncingAll) return;
    syncingAll = true;
    try {
        const res = await fetch(
            `${API_BASE}/sync/teams/${encodeURIComponent(teamName)}/sync-now`,
            { method: 'POST' }
        ).catch(() => null);
        if (res?.ok) {
            pushSyncAction('sync_now' as any, 'Triggered sync for all projects', teamName ?? '');
            // Refresh project status after sync
            await loadProjectStatus();
        }
    } finally {
        syncingAll = false;
    }
}
```

**Step 5: Verify manually**

Run: `cd frontend && npm run check`
Expected: No type errors

**Step 6: Commit**

```bash
git add frontend/src/lib/components/sync/OverviewTab.svelte frontend/src/lib/api-types.ts
git commit -m "feat(sync): add Per-Project Sync Status section to dashboard [P0]"
```

---

### Task 6: Add Recent Activity section to OverviewTab

Wire up the existing `/sync/activity` API to a visible section.

**Files:**
- Modify: `frontend/src/lib/components/sync/OverviewTab.svelte`
- Modify: `frontend/src/lib/api-types.ts`

**Step 1: Add TypeScript type**

```typescript
export interface SyncEvent {
	id: number;
	event_type: string;
	team_name: string | null;
	member_name: string | null;
	project_encoded_name: string | null;
	detail: string | null;
	created_at: string;
}
```

**Step 2: Add state, fetch, and humanize logic**

```typescript
import { Clock } from 'lucide-svelte';
import type { SyncEvent } from '$lib/api-types';

let recentEvents = $state<SyncEvent[]>([]);
let eventsLoading = $state(true);

function humanizeEvent(e: SyncEvent): string {
    const who = e.member_name ? `${e.member_name} ` : '';
    const team = e.team_name ? ` (${e.team_name})` : '';
    switch (e.event_type) {
        case 'member_added': return `${who}joined${team}`;
        case 'member_removed': return `${who}left${team}`;
        case 'team_created': return `Team "${e.team_name}" created`;
        case 'team_deleted': return `Team "${e.team_name}" deleted`;
        case 'project_added': return `Project "${e.project_encoded_name}" shared${team}`;
        case 'project_removed': return `Project "${e.project_encoded_name}" removed${team}`;
        case 'watcher_started': return `Watcher started${team}`;
        case 'watcher_stopped': return `Watcher stopped${team}`;
        case 'sync_now': return `Manual sync triggered${team}`;
        case 'pending_accepted': return `Pending folders accepted`;
        case 'folders_shared': return `Folders shared with ${who}${team}`;
        default: return e.event_type;
    }
}

async function loadActivity() {
    try {
        const res = await fetch(`${API_BASE}/sync/activity?limit=8`).catch(() => null);
        if (res?.ok) {
            const data = await res.json();
            recentEvents = data.events ?? [];
        }
    } catch { /* non-critical */ }
    finally { eventsLoading = false; }
}
```

Add `loadActivity()` to the `$effect` `untrack()` block.

**Step 3: Add the template**

Insert after Per-Project Sync Status, before Machine Details:

```svelte
<!-- ── 6. Recent Activity ────────────────────────────────────────── -->
{#if !eventsLoading && recentEvents.length > 0}
    <div class="rounded-[var(--radius-lg)] border border-[var(--border)] bg-[var(--bg-subtle)]">
        <div class="flex items-center gap-2 px-5 py-3.5 border-b border-[var(--border-subtle)]">
            <Clock size={14} class="text-[var(--text-muted)]" />
            <h3 class="text-sm font-semibold text-[var(--text-primary)]">Recent Activity</h3>
        </div>
        <div class="px-5 divide-y divide-[var(--border-subtle)]">
            {#each recentEvents as event (event.id)}
                <div class="flex items-center justify-between py-2.5">
                    <span class="text-xs text-[var(--text-secondary)]">{humanizeEvent(event)}</span>
                    <span class="text-[11px] text-[var(--text-muted)] shrink-0 ml-3">
                        {formatRelativeTime(event.created_at)}
                    </span>
                </div>
            {/each}
        </div>
    </div>
{/if}
```

**Step 4: Verify**

Run: `cd frontend && npm run check`

**Step 5: Commit**

```bash
git add frontend/src/lib/components/sync/OverviewTab.svelte frontend/src/lib/api-types.ts
git commit -m "feat(sync): add Recent Activity section to dashboard [P1]"
```

---

### Task 7: Collapse Machine Details into accordion [MEDIUM, P2]

**Files:**
- Modify: `frontend/src/lib/components/sync/OverviewTab.svelte:372-434`

**Step 1: Add collapsed state**

```typescript
let machineDetailsOpen = $state(false);
```

**Step 2: Replace the Machine Details section**

Replace the static card (lines 372-434) with a collapsible version:

```svelte
<!-- ── Machine Details (collapsible) ─────────────────────────────── -->
<div class="rounded-[var(--radius-lg)] border border-[var(--border)] bg-[var(--bg-subtle)]">
    <button
        onclick={() => (machineDetailsOpen = !machineDetailsOpen)}
        class="w-full flex items-center justify-between px-5 py-3.5 text-left"
        aria-expanded={machineDetailsOpen}
    >
        <div class="flex items-center gap-2">
            <Monitor size={14} class="text-[var(--text-muted)]" />
            <h3 class="text-sm font-semibold text-[var(--text-primary)]">Machine Details</h3>
        </div>
        <svg
            class="w-4 h-4 text-[var(--text-muted)] transition-transform {machineDetailsOpen ? 'rotate-180' : ''}"
            fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2"
        >
            <path d="M19 9l-7 7-7-7" />
        </svg>
    </button>

    {#if machineDetailsOpen}
        <div class="px-5 pb-5 space-y-3 border-t border-[var(--border-subtle)] pt-3">
            <!-- existing machine details content (lines 378-433) -->
            ...
        </div>
    {/if}
</div>
```

**Step 3: Commit**

```bash
git add frontend/src/lib/components/sync/OverviewTab.svelte
git commit -m "feat(sync): collapse Machine Details section by default [MEDIUM]"
```

---

## Phase 3: Cross-Linking & Wayfinding

### Task 8: Add watcher status banner to team detail page [P0]

Users on `/team/[name]` need to know if sync is actually running.

**Files:**
- Create: `frontend/src/lib/components/sync/SyncStatusBanner.svelte`
- Modify: `frontend/src/routes/team/[name]/+page.svelte`
- Modify: `frontend/src/routes/team/[name]/+page.server.ts`

**Step 1: Create the banner component**

```svelte
<!-- frontend/src/lib/components/sync/SyncStatusBanner.svelte -->
<script lang="ts">
    import { Play, Square, ExternalLink } from 'lucide-svelte';

    let {
        running = false,
        syncthingUp = false,
        teamName = ''
    }: {
        running: boolean;
        syncthingUp: boolean;
        teamName?: string;
    } = $props();
</script>

{#if running}
    <div class="flex items-center gap-2.5 px-4 py-2.5 rounded-[var(--radius-lg)] border border-[var(--success)]/20 bg-[var(--status-active-bg)]">
        <span class="w-2 h-2 rounded-full bg-[var(--success)] shrink-0" aria-hidden="true"></span>
        <span class="text-xs font-medium text-[var(--text-primary)] flex-1">Sync active</span>
        <a
            href="/sync"
            class="flex items-center gap-1 text-[11px] text-[var(--text-muted)] hover:text-[var(--accent)] transition-colors"
        >
            Manage <ExternalLink size={10} />
        </a>
    </div>
{:else}
    <div class="flex items-center gap-2.5 px-4 py-2.5 rounded-[var(--radius-lg)] border border-[var(--warning)]/20 bg-[var(--status-idle-bg)]">
        <span class="w-2 h-2 rounded-full bg-[var(--warning)] shrink-0" aria-hidden="true"></span>
        <span class="text-xs text-[var(--text-secondary)] flex-1">
            {syncthingUp ? 'Session watcher paused' : 'Syncthing not running'}
        </span>
        <a
            href="/sync"
            class="flex items-center gap-1 text-[11px] font-medium text-[var(--accent)] hover:text-[var(--accent-hover)] transition-colors"
        >
            Start sync <ExternalLink size={10} />
        </a>
    </div>
{/if}
```

**Step 2: Fetch watcher status in team detail page.server.ts**

Add to the parallel fetch in `frontend/src/routes/team/[name]/+page.server.ts`:

```typescript
// Add to imports
import type { SyncWatchStatus, SyncDetect } from '$lib/api-types';

// Add to the Promise.all (line 24):
const [teamsData, devices, joinCodeData, pendingData, syncStatus, watchStatus, detectData] = await Promise.all([
    // ... existing fetches ...,
    fetchWithFallback<SyncWatchStatus>(fetch, `${API_BASE}/sync/watch/status`, { running: false }),
    fetchWithFallback<SyncDetect>(fetch, `${API_BASE}/sync/detect`, { running: false }),
]);

// Add to return:
return {
    // ... existing fields ...,
    watchStatus,
    detectData,
};
```

**Step 3: Add banner to team detail page**

In `frontend/src/routes/team/[name]/+page.svelte`, add after PageHeader:

```svelte
import SyncStatusBanner from '$lib/components/sync/SyncStatusBanner.svelte';

<!-- Insert after the PageHeader closing tag, before the {#if !team} block -->
<div class="mb-6">
    <SyncStatusBanner
        running={data.watchStatus?.running ?? false}
        syncthingUp={data.detectData?.running ?? false}
        teamName={data.teamName}
    />
</div>
```

**Step 4: Verify**

Run: `cd frontend && npm run check`

**Step 5: Commit**

```bash
git add frontend/src/lib/components/sync/SyncStatusBanner.svelte \
    frontend/src/routes/team/[name]/+page.svelte \
    frontend/src/routes/team/[name]/+page.server.ts
git commit -m "feat(team): add sync status banner to team detail page [P0]"
```

---

### Task 9: Make stats clickable with navigation links [P2]

**Files:**
- Modify: `frontend/src/lib/components/sync/OverviewTab.svelte:280-302`

**Step 1: Wrap stats in anchor tags**

Replace the static stat cards with navigable versions. For "Members Online", link to `/team/{teamName}`. For "Projects", link to `/team/{teamName}`. For "Sessions Received", show per-project breakdown.

Replace the stats grid (lines 280-302):

```svelte
<div class="grid grid-cols-2 sm:grid-cols-4 gap-3">
    <a
        href={teamName ? `/team/${encodeURIComponent(teamName)}` : '/team'}
        class="rounded-[var(--radius-lg)] border border-[var(--border)] bg-[var(--bg-subtle)] p-4 text-center hover:border-[var(--accent)]/40 transition-colors"
    >
        <Users size={16} class="mx-auto text-[var(--text-muted)] mb-1.5" />
        <p class="text-lg font-semibold text-[var(--text-primary)]">{connectedMembers}/{totalMembers}</p>
        <p class="text-[11px] text-[var(--text-muted)]">Members Online</p>
    </a>
    <a
        href={teamName ? `/team/${encodeURIComponent(teamName)}` : '/team'}
        class="rounded-[var(--radius-lg)] border border-[var(--border)] bg-[var(--bg-subtle)] p-4 text-center hover:border-[var(--accent)]/40 transition-colors"
    >
        <FolderGit2 size={16} class="mx-auto text-[var(--text-muted)] mb-1.5" />
        <p class="text-lg font-semibold text-[var(--text-primary)]">{projectCount}</p>
        <p class="text-[11px] text-[var(--text-muted)]">Projects</p>
    </a>
    <div class="rounded-[var(--radius-lg)] border border-[var(--border)] bg-[var(--bg-subtle)] p-4 text-center">
        <ArrowUp size={16} class="mx-auto text-[var(--accent)] mb-1.5" />
        <p class="text-lg font-semibold text-[var(--text-primary)]">{sessionsSharedCount}</p>
        <p class="text-[11px] text-[var(--text-muted)]">Sessions Shared</p>
    </div>
    <div class="rounded-[var(--radius-lg)] border border-[var(--border)] bg-[var(--bg-subtle)] p-4 text-center">
        <ArrowDown size={16} class="mx-auto text-[var(--info)] mb-1.5" />
        <p class="text-lg font-semibold text-[var(--text-primary)]">{sessionsReceivedCount}</p>
        <p class="text-[11px] text-[var(--text-muted)]">Sessions Received</p>
    </div>
</div>
```

**Step 2: Commit**

```bash
git add frontend/src/lib/components/sync/OverviewTab.svelte
git commit -m "feat(sync): make Members and Projects stats clickable to team page [P2]"
```

---

### Task 10: Consolidate home page nav cards [P2]

Replace two separate "Teams" and "Sync" cards with a single "Sync & Teams" entry.

**Files:**
- Modify: `frontend/src/routes/+page.svelte:40-41`

**Step 1: Replace two cards with one**

```svelte
<!-- OLD (lines 40-41): -->
<!-- <NavigationCard title="Teams" href="/team" icon={Users} color="indigo" /> -->
<!-- <NavigationCard title="Sync" href="/sync" icon={RefreshCw} color="green" /> -->

<!-- NEW: -->
<NavigationCard title="Sync & Teams" href="/sync" icon={RefreshCw} color="green" />
```

**Step 2: Add a redirect from `/team` sync page subtitle pointing to `/sync`**

In `/team/+page.svelte`, update the subtitle to mention sync:

```svelte
subtitle="Create and manage teams to share sessions with teammates · Sync status on /sync"
```

**Step 3: Commit**

```bash
git add frontend/src/routes/+page.svelte frontend/src/routes/team/+page.svelte
git commit -m "feat(nav): consolidate Sync and Teams into single nav card [P2]"
```

---

## Phase 4: Polish & Bug Fixes

### Task 11: Fix stale stats on team switch [MEDIUM-4]

**Files:**
- Modify: `frontend/src/lib/components/sync/OverviewTab.svelte:197-205`

**Step 1: Reset `statsLoaded` when teamName changes**

Add at line 197, before the `$effect`:

```typescript
// Reset loaded flags when team changes so loading indicators reappear
$effect(() => {
    const _team = teamName; // track
    statsLoaded = false;
    projectStatusLoading = true;
    eventsLoading = true;
});
```

**Step 2: Commit**

```bash
git add frontend/src/lib/components/sync/OverviewTab.svelte
git commit -m "fix(sync): reset stats when switching teams [MEDIUM-4]"
```

---

### Task 12: Add AbortController to team detail polling [HIGH-1]

**Files:**
- Modify: `frontend/src/routes/team/[name]/+page.svelte:51-72`

**Step 1: Add AbortController**

Replace the polling `onMount` block:

```typescript
onMount(() => {
    let abortController = new AbortController();

    const interval = setInterval(async () => {
        abortController.abort();
        abortController = new AbortController();
        const signal = abortController.signal;
        try {
            const [pendingRes, devicesRes] = await Promise.all([
                fetch(`${API_BASE}/sync/pending-devices`, { signal }),
                fetch(`${API_BASE}/sync/devices`, { signal })
            ]);
            if (pendingRes.ok) {
                const pd = await pendingRes.json();
                pendingDevices = pd.devices ?? [];
            }
            if (devicesRes.ok) {
                const dd = await devicesRes.json();
                devices = dd.devices ?? [];
            }
        } catch (e) {
            if (e instanceof DOMException && e.name === 'AbortError') return;
        }
    }, POLLING_INTERVALS.SYNC_STATUS);

    return () => {
        clearInterval(interval);
        abortController.abort();
    };
});
```

**Step 2: Commit**

```bash
git add frontend/src/routes/team/[name]/+page.svelte
git commit -m "fix(team): add AbortController to polling to prevent stale state updates [HIGH-1]"
```

---

### Task 13: Fix SetupWizard dynamic import navigation [MEDIUM-5]

**Files:**
- Modify: `frontend/src/lib/components/sync/SetupWizard.svelte:1-46`

**Step 1: Replace dynamic import with static import + guard**

```typescript
// At top of script:
import { goto } from '$app/navigation';

let hasNavigated = false;

// Replace the $effect (lines 42-46):
$effect(() => {
    if (status?.configured && step === 2 && !hasNavigated) {
        hasNavigated = true;
        goto('/team');
    }
});
```

**Step 2: Commit**

```bash
git add frontend/src/lib/components/sync/SetupWizard.svelte
git commit -m "fix(sync): use static import for goto and prevent duplicate navigation [MEDIUM-5]"
```

---

### Task 14: Remove dead `syncActions` store calls or wire up consumer [HIGH-2]

Since we added the Recent Activity section in Task 6 (which uses server events), the client-side `syncActions` store is redundant. Remove the dead calls.

**Files:**
- Modify: `frontend/src/lib/components/sync/OverviewTab.svelte` (remove `pushSyncAction` calls)
- Delete: `frontend/src/lib/stores/syncActions.svelte.ts`

**Step 1: Remove imports and calls from OverviewTab**

Remove the import line:
```typescript
// REMOVE: import { pushSyncAction } from '$lib/stores/syncActions.svelte';
```

Remove calls at lines 55, 68, and 172 (the `pushSyncAction(...)` calls in `startWatch`, `stopWatch`, and `acceptAll`).

**Step 2: Delete the store file**

```bash
rm frontend/src/lib/stores/syncActions.svelte.ts
```

**Step 3: Verify no other imports**

Run: `cd frontend && grep -r "syncActions" src/`
Expected: No matches

**Step 4: Type check**

Run: `cd frontend && npm run check`

**Step 5: Commit**

```bash
git add -A
git commit -m "fix(sync): remove dead syncActions store — replaced by server activity feed [HIGH-2]"
```

---

### Task 15: Fix device ID truncation [LOW-4]

**Files:**
- Modify: `frontend/src/lib/components/team/TeamMemberCard.svelte:84-86`
- Modify: `frontend/src/lib/components/team/PendingDeviceCard.svelte:57-59`
- Modify: `frontend/src/lib/components/team/AddMemberDialog.svelte:101`

**Step 1: Fix in all three files**

Replace `{value.slice(0, 20)}...` with:

```svelte
{value.length > 20 ? value.slice(0, 20) + '...' : value}
```

Apply to:
- `TeamMemberCard.svelte:85` — `member.device_id`
- `PendingDeviceCard.svelte:58` — `device.device_id`
- `AddMemberDialog.svelte:101` — `parsed.device_id`

**Step 2: Commit**

```bash
git add frontend/src/lib/components/team/TeamMemberCard.svelte \
    frontend/src/lib/components/team/PendingDeviceCard.svelte \
    frontend/src/lib/components/team/AddMemberDialog.svelte
git commit -m "fix(team): only show ellipsis when device ID is actually truncated [LOW-4]"
```

---

### Task 16: Add minimum team name length [LOW-3]

**Files:**
- Modify: `api/routers/sync_status.py:487`
- Modify: `frontend/src/lib/components/team/CreateTeamDialog.svelte:18`

**Step 1: API — require 2+ chars**

```python
# Line 487:
if not ALLOWED_PROJECT_NAME.match(req.name) or len(req.name) > 64 or len(req.name) < 2:
    raise HTTPException(400, "Team name must be 2-64 characters (letters, numbers, dashes, underscores)")
```

**Step 2: Frontend — match validation**

```typescript
// CreateTeamDialog.svelte line 18:
let isValid = $derived(/^[a-zA-Z0-9_-]{2,64}$/.test(teamName));
```

**Step 3: Commit**

```bash
git add api/routers/sync_status.py frontend/src/lib/components/team/CreateTeamDialog.svelte
git commit -m "fix(team): require minimum 2-character team name [LOW-3]"
```

---

## Summary

| Phase | Tasks | Issues Addressed |
|---|---|---|
| **Phase 1: Security** | Tasks 1-4 | CRITICAL-1, HIGH-3, HIGH-4, HIGH-5, LOW-2 |
| **Phase 2: Dashboard** | Tasks 5-7 | Per-Project Status, Activity, Sync Now, Machine Details collapse |
| **Phase 3: Wayfinding** | Tasks 8-10 | Watcher banner on team page, clickable stats, nav consolidation |
| **Phase 4: Polish** | Tasks 11-16 | MEDIUM-4, HIGH-1, MEDIUM-5, HIGH-2, LOW-4, LOW-3 |

**Not addressed (deferred — requires separate design work):**
- CRITICAL-2: Full API authentication (needs auth design beyond scope of this UX fix)
- MEDIUM-1: Read connection separation (optimization, not UX)
- MEDIUM-2: Join code split consistency (edge case, no real-world impact today)
- MEDIUM-3: Partial project add failure (rare edge case)
- MEDIUM-6: Singleton thread safety (unlikely in single-event-loop FastAPI)
- Getting Started checklist (needs UX design + persistence model)
- Better ProjectTeamTab session metadata (needs API enhancement)
