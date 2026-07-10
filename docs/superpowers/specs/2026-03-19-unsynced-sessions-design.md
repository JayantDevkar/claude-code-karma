# Unsynced Sessions — Design Spec

**Date**: 2026-03-19
**Status**: Approved

## Problem

Users cannot see which sessions are ready to sync, nor trigger sync on demand. The current gap calculation (`local_count - packaged_count`) misleadingly includes running sessions that cannot be synced yet. The "Sync Now" button on `/sync` only triggers reconciliation (device/folder setup), not actual session packaging.

## Decisions

| Decision | Choice |
|----------|--------|
| Gap calculation | Exclude active sessions — gap shows only actionable (ended, unpackaged) sessions |
| Sync trigger | New `POST /sync/package` endpoint with scope params |
| Sync granularity | Global (all teams), per-team, per-project — single endpoint with query params |
| UI placement | Per-project badges + sync buttons on TeamProjectsTab; team-level "Sync All" at tab header |
| Action feedback | Inline spinner + count refresh (no toasts) |

## Design

### 1. API — Extract shared packaging service

**Problem**: The full packaging pipeline in `watcher_manager.py` (lines 339-414) is non-trivial — it resolves outbox paths, discovers worktree directories, checks subscription/direction policy gates, constructs `SessionPackager`, and logs sync events. Both the watcher and the new endpoint need this logic.

**Solution**: Extract a `PackagingService` (or a standalone function `package_project()`) into `api/services/sync/packaging_service.py` that encapsulates the full pipeline:

1. Resolve project dir (`~/.claude/projects/{encoded_name}`)
2. Discover worktree dirs via `find_worktree_dirs()`
3. Build outbox path from `build_outbox_folder_id(member_tag, folder_suffix)`
4. Construct `SessionPackager` with all required params (user_id, machine_id, device_id, member_tag, team_name, proj_suffix)
5. Call `packager.package()`
6. Log `sync_events`

Both `watcher_manager.py`'s `make_package_fn` and the new endpoint call this shared service. This avoids code duplication and drift.

**Concurrency**: Add a per-project `threading.Lock` in the service to serialize packaging. The watcher's background packaging and the endpoint's on-demand packaging must not run simultaneously for the same project (risk: corrupt manifest from interleaved writes).

### 2. API — `POST /sync/package`

**Router**: `api/routers/sync_system.py`

```
POST /sync/package?team_name=X&git_identity=Y
```

**Scope rules**:
- No params → package all projects across all teams
- `team_name` only → package all projects in that team
- `team_name` + `git_identity` → single project

**Logic**:
1. Load `SyncConfig` via `require_config`
2. Determine scope by querying `sync_projects` + `sync_subscriptions` (only projects where user has accepted subscription with send/both direction)
3. For each project in scope: call the shared `PackagingService.package_project()` (from Section 1)
4. Best-effort per project: failures are logged and the response includes `sessions_packaged: 0` with an `error` field for failed projects, rather than failing the entire request
5. Return response:

```json
{
  "ok": true,
  "packaged": [
    {"team_name": "team-1", "git_identity": "owner/repo", "sessions_packaged": 3},
    {"team_name": "team-1", "git_identity": "owner/other", "sessions_packaged": 0, "error": "outbox not found"}
  ]
}
```

### 3. API — Fix gap calculation in `project-status`

**File**: `api/routers/sync_teams.py` (the `get_project_status` endpoint)

**Current**: `gap = local_count - packaged_count` (includes running sessions).

**Fix**: Create a shared helper `get_active_sessions_by_project() -> dict[str, int]` that:
- Reads `~/.claude_karma/live-sessions/*.json`
- Uses `resolved_project_encoded_name` (handles worktree-to-parent resolution) to match sessions to projects
- Counts sessions where `state != "ENDED"` and idle < stale threshold
- Reuses `STALE_LIVE_SESSION_SECONDS` constant from `cli/karma/packager.py` (currently 30 * 60) — import the constant, don't re-derive it
- Returns `{encoded_name: active_count}` dict

In `get_project_status`, match each project's resolved `encoded_name` against this dict.

**New formula**: `gap = max(0, local_count - packaged_count - active_count)`

**Response shape** (additive — new field `active_count`):
```json
{
  "git_identity": "...",
  "local_count": 10,
  "packaged_count": 7,
  "active_count": 2,
  "gap": 1
}
```

The gap now represents only sessions that CAN be synced but haven't been.

### 4. Frontend — TeamProjectsTab sync badges and actions

**File**: `frontend/src/lib/components/team/TeamProjectsTab.svelte`

**New data**: Fetch `GET /sync/teams/{name}/project-status` when tab loads (same pattern as OverviewTab).

**Per-project row changes**:
```
[FolderIcon] ProjectName     [subscription badge] [sync badge] [sync btn] [direction] [pause/remove]
             project path
```

- **Sync badge**: Green "In Sync" pill when gap=0, yellow "N ready to sync" pill when gap>0
- **Sync button**: Small RefreshCw icon button, only visible when gap>0. Calls `POST /sync/package?team_name={name}&git_identity={identity}`. Shows spinner while running, then refreshes status.
- **Visibility**: Sync badge and button only shown for projects with accepted subscription + send/both direction.

**Team-level action**: "Sync All" button in the Active Projects section header. Only visible when total team gap > 0. Calls `POST /sync/package?team_name={name}`.

### 5. Frontend — OverviewTab "Sync Now" fix

**File**: `frontend/src/lib/components/sync/OverviewTab.svelte`

**Current**: `syncAllNow()` calls `POST /sync/reconcile` only.

**Fix**: Call both in parallel via `Promise.all`:
1. `POST /sync/package` (package sessions)
2. `POST /sync/reconcile` (device/folder reconciliation)

Then refresh project status after both complete. These are independent concerns (file copying vs. Syncthing device/folder setup) and can safely run concurrently.

No visual changes — same button, spinner, count refresh. Fixes what happens behind the click.

### 6. Frontend — TypeScript type update

**File**: `frontend/src/lib/api-types.ts`

`SyncProjectStatus` is currently an alias for `SyncTeamProject`. Break the alias and make `SyncProjectStatus` a separate interface extending `SyncTeamProject` with `{ active_count: number }`. This keeps the types clean since `active_count` is only meaningful in the project-status context.

## Files to Create/Modify

| File | Action | Description |
|------|--------|-------------|
| `api/services/sync/packaging_service.py` | Create | Shared packaging pipeline extracted from watcher_manager, with per-project locking |
| `api/services/watcher_manager.py` | Modify | Delegate to `PackagingService` instead of inline `make_package_fn` |
| `api/routers/sync_system.py` | Modify | Add `POST /sync/package` endpoint |
| `api/routers/sync_teams.py` | Modify | Fix gap calculation — subtract active sessions, add `active_count` field |
| `frontend/src/lib/components/team/TeamProjectsTab.svelte` | Modify | Add project-status fetch, sync badges, per-project and team-level sync buttons |
| `frontend/src/lib/components/sync/OverviewTab.svelte` | Modify | Fix `syncAllNow()` to call package + reconcile in parallel |
| `frontend/src/lib/api-types.ts` | Modify | Break `SyncProjectStatus` alias, add `active_count` field |
| `api/tests/test_sync_package.py` | Create | Tests for the new package endpoint |
| `api/tests/test_project_status_gap.py` | Create | Tests for updated gap calculation with active session exclusion |

## Out of Scope

- WebSocket/SSE for real-time sync progress
- Per-member unsynced breakdowns
- Sync history/audit log UI
- Auto-retry on packaging failure
