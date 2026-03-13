# Sync v3 Architecture Design

> **Date:** 2026-03-13
> **Status:** Design revision 3 (all critic + architect feedback applied)
> **Scope:** Architecture and design only (no code)
> **Input:** `docs/design/sync-v3-audit-findings.md` (BP-1 through BP-18, EC-1 through EC-7, RC-1 through RC-5)

---

## Context

### Original Request

Design the v3 sync architecture for claude-karma's Syncthing P2P sync layer. The v2 layer breaks when members overlap across multiple teams sharing the same projects. Three root causes were identified:

1. Outbox folder IDs lack team scope (BP-1), causing silent device list merging (BP-2) and destructive cleanup (BP-3, BP-4)
2. Syncthing's introducer mechanism leaks across team boundaries (BP-5), creating phantom team memberships (BP-6)
3. No surgical device removal from folders (BP-7), only folder deletion

### Research Findings

The audit document (`docs/design/sync-v3-audit-findings.md`) provides a complete behavioral analysis of v2 with 18 breakpoints, 7 edge cases, 5 race conditions, and 7 verified-correct behaviors. Two candidate architectures were proposed: team-scoped folder IDs (Option A) and project channels (Option B).

### What Works Correctly (Preserved in v3)

- OK-1: Atomic metadata writes (tempfile + rename)
- OK-2: SQLite WAL mode with proper locking
- OK-3: Same-user multi-device differentiation (member_tag)
- OK-4: Handshake and metadata folder IDs include team
- OK-5: Device cross-team check on removal
- OK-6: Event loop handling in daemon thread
- OK-7: Removal authority (creator-only)

---

## ADR-1: Folder ID Strategy — Project Channels

### Decision

**Choose Option B: Project Channels.** Keep the current folder ID format `karma-out--{member_tag}--{suffix}` (one folder per member per project). Teams become an access control layer, not a data boundary. Device lists are computed as the union of all teams sharing that project for that member.

### Status

Accepted.

### Context

Two options were evaluated:

**Option A — Team-Scoped Folder IDs:**
- Format: `karma-out--{member_tag}--{team}--{suffix}`
- Pro: Clean isolation per team. Simple cleanup (just delete team-scoped folders).
- Con: Same session data duplicated N times for N teams sharing the project. Packager must copy to N outbox paths. Folder count multiplied by team count.

**Option B — Project Channels:**
- Format: `karma-out--{member_tag}--{suffix}` (unchanged from v2)
- Pro: No session duplication. One outbox per (member, project). Packager unchanged. Fewer folders.
- Con: Requires cross-team union queries for device lists. Cleanup requires device subtraction (not folder deletion). More complex bookkeeping.

### Rationale

1. **Session data is inherently per-project** (audit section 11.3). A session belongs to `~/.claude/projects/{encoded}/{uuid}.jsonl`. There is no team concept at the session level. Duplicating sessions across team-scoped outboxes adds storage and sync overhead with zero value.

2. **The packager copies sessions to ONE outbox path** (audit section 10.1). With Option A, the packager would need to copy to N paths. With Option B, no packager changes are needed.

3. **Folder count matters** (BP-15, EC-7). At scale (10 teams, 20 projects, 10 members), Option A produces ~2000 folders vs ~125 for Option B. Syncthing performance degrades above ~500 folders.

4. **The complexity is manageable.** The "union device list" computation is a SQL query joining `sync_team_projects` and `sync_members`. The "device subtraction on cleanup" uses `remove_device_from_folder` which already exists (BP-18) but is underused.

### Consequences

- **Folder ID format unchanged.** No migration needed for folder IDs themselves.
- **Device list computation changes.** `ensure_outbox_folder` and `ensure_inbox_folders` must compute the union of all teams' devices for a given (member, project) pair.
- **Cleanup changes.** Leaving a team subtracts that team's devices from shared folders, rather than deleting the folder. Folder deletion only happens when refcount reaches 0 (no team claims the folder).
- **`find_team_for_folder` becomes obsolete** for disambiguation. Folder-to-team mapping is now many-to-many. Replaced by direct SQL queries.
- **`sync_rejected_folders` must become team-scoped** (fixes BP-14).

### Breakpoints Addressed

- BP-1 (no team scope): Addressed by treating team as access control, not folder boundary
- BP-2 (additive-only): Addressed by ADR-3 (declarative device lists)
- BP-3 (destructive cleanup): Addressed by ADR-4 (device subtraction)
- BP-4 (cross-team inbox removal): Addressed by ADR-4 (refcount check)
- BP-8 (ambiguous team lookup): Addressed by eliminating single-team folder assumption
- BP-14 (rejection not team-scoped): Addressed by team-scoped rejection table
- BP-15 (folder count): Addressed by keeping project-scoped folders (lower count)

---

## ADR-2: Explicit Mesh Pairing (Replacing Introducer)

### Decision

**Remove all use of Syncthing's introducer flag.** Replace with explicit device pairing coordinated through the metadata folder. Each device reads the team's metadata folder to discover peer device IDs, then pairs with them directly via the Syncthing REST API.

### Status

Accepted.

### Context

The introducer mechanism (audit section 6.1, BP-5) is:
- Per-device, global, all-or-nothing (not team-scoped)
- Permanent once set (no code path disables it)
- Re-enforced by `ensure_leader_introducers()` on every poll

In multi-team setups, a device marked as introducer for Team A propagates ALL devices/folders (including from Teams B, C, D) to any peer that trusts it. This creates phantom team memberships (BP-6) via reconciliation auto-creating teams from introduced artifacts.

### Rationale

1. **Syncthing's introducer cannot be scoped to a team** (audit section 6.1). This is a fundamental constraint of Syncthing, not a bug in karma's code. No amount of clever coding around it will prevent cross-team leakage when a device participates in multiple teams.

2. **The metadata folder already provides the necessary information.** Each member writes their `device_id` to `members/{member_tag}.json`. Reading the metadata folder gives a complete list of all team members and their device IDs. This is sufficient for explicit pairing.

3. **Explicit pairing is more predictable.** The system pairs exactly the devices it intends to, with no side effects. Debugging "why is device X seeing device Y's data" becomes straightforward: check which teams share a project where both are members.

### New Join Flow (Explicit Mesh)

```
STEP 1: Joiner joins team
  Joiner → pair with leader device (from join code)
  Joiner → create karma-join--{self}--{team}
  Joiner → create karma-meta--{team} (shared with leader)
  Joiner → write own member state to metadata folder
  NOTE: introducer=False on leader device

STEP 2: Leader accepts joiner
  Leader → auto_accept_pending_peers (as today)
  Leader → add joiner device, NO introducer flag
  Leader → auto_share_folders (as today)
  Leader → update metadata folder device list to include joiner

STEP 3: Metadata propagation
  Metadata folder syncs to all team members (sendreceive)
  Each member reads metadata → discovers new member's device_id

STEP 4: Explicit mesh pairing — existing members (NEW)
  Each existing member → reads metadata folder
  For each new device_id not yet paired:
    proxy.add_device(device_id, member_tag)  # NO introducer
  Then: compute_and_apply_device_lists() for all project folders (ADR-3)

STEP 5: Explicit mesh pairing — joiner (NEW)
  Joiner receives metadata folder from leader (Step 2)
  Joiner → mesh_pair_from_metadata()
    Reads metadata → discovers all existing members' device_ids
    For each peer not yet paired:
      proxy.add_device(device_id, member_tag)  # NO introducer
    compute_and_apply_device_lists() for all project folders
  NOTE: Without this step, the joiner can only sync with the leader
    until the next reconciliation cycle discovers peers.
```

### What This Replaces

| v2 Component | v3 Replacement |
|---|---|
| `ensure_leader_introducers()` | Removed entirely |
| `reconcile_introduced_devices()` | Replaced by `mesh_pair_from_metadata()` |
| `reconcile_pending_handshakes()` | Kept (handshake processing is team-scoped, works correctly) |
| `auto_accept_pending_peers()` | Kept (policy gate + identity verification) |
| Introducer flag on `add_device()` | Always `introducer=False` |

### Explicit Mesh Pairing Function

New function `mesh_pair_from_metadata(proxy, config, conn)`:

```
For each team in list_teams(conn):
  meta_dir = KARMA_BASE / "metadata-folders" / team_name
  member_states = read_all_member_states(meta_dir)
  removal_signals = read_removal_signals(meta_dir)
  removed_tags = {r["member_tag"] for r in removal_signals}

  For each member_state:
    if member_state.member_tag in removed_tags: skip
    if member_state.member_tag == config.member_tag: skip (self)
    if member_state.device_id already configured in Syncthing: skip

    # Pair with new device (no introducer)
    proxy.add_device(device_id, member_tag)
    upsert_member(conn, team_name, ...)

    # Compute and apply device lists for all project folders
    compute_and_apply_device_lists(proxy, config, conn, team_name)
```

### Migration: Disabling Existing Introducers

On first v3 startup:

```
For each configured device in Syncthing:
  if device.introducer == True:
    proxy.set_device_introducer(device_id, False)
    log_event("introducer_disabled", detail={"device_id": device_id})
```

### Breakpoints Addressed

- BP-5 (global introducer): Eliminated entirely
- BP-6 (phantom team creation): Eliminated (no introduced artifacts from foreign teams)
- BP-7 (partial): Device pairing is now explicit, so device lists are deterministic

---

## ADR-3: Declarative Device List Management

### Decision

Replace the additive-only `update_folder_devices` pattern with a **declarative `set_folder_devices`** approach. For each folder, compute the desired device list from the database, then apply it as the complete list (adding missing devices, removing stale devices).

### Status

Accepted.

### Context

v2's `update_folder_devices` (BP-2) only adds devices. Once a device leaks into a folder, there is no normal-operation code path to remove it. The only removal mechanism is deleting the entire folder (BP-3, BP-4, BP-7).

Meanwhile, `remove_device_from_folder` (BP-18) exists and works correctly but is only used in one cleanup path.

### The Union Query

For a given folder `karma-out--{member_tag}--{suffix}`, the query must be scoped to teams where the folder OWNER is a member. Without this constraint, a folder would incorrectly include devices from teams the owner does not belong to (e.g., M4's outbox for P2 would include T2 devices even though M4 is NOT in T2).

```sql
-- All devices that should have access to this folder,
-- scoped to teams where the folder owner is a member.
-- Input: :suffix, :owner_member_tag
SELECT DISTINCT sm.device_id
FROM sync_team_projects stp
JOIN sync_members sm ON sm.team_name = stp.team_name
WHERE stp.folder_suffix = :suffix
  AND sm.device_id IS NOT NULL
  AND sm.device_id != ''
  AND stp.team_name IN (
    SELECT team_name FROM sync_members
    WHERE member_tag = :owner_member_tag
  )
```

This computes the union of all team members across all teams that (a) share the project identified by `suffix` AND (b) include the folder owner as a member. The `owner_member_tag` parameter is extracted from the folder ID: `karma-out--{owner_member_tag}--{suffix}`.

### New Function: `compute_and_apply_device_lists`

```
def compute_and_apply_device_lists(proxy, config, conn, team_name=None):
    """Compute desired device lists for all project folders and apply them.

    If team_name is provided, only recomputes folders for that team's projects.
    Otherwise recomputes all folders.

    IMPORTANT: The union query is scoped to teams where the folder OWNER
    is a member (see ADR-3 union query). The owner_member_tag is extracted
    from the folder ID: karma-out--{owner_member_tag}--{suffix}.

    LOCKING: Must acquire client._config_lock for the full GET-compute-PUT
    cycle of each folder (see RC-4 mitigation).

    FOLDER COUNT WARNING: Logs a warning at 200 folders, logs an error
    at 500 folders (see BP-15 safeguard).
    """
    # 0. Count total folders; warn at 200, error at 500
    # 1. Get all project suffixes (optionally filtered by team)
    # 2. For each suffix, for each folder matching the suffix:
    #    a. Extract owner_member_tag from folder ID
    #    b. Compute the union device list from DB (scoped to owner's teams)
    #    c. Get current device list from Syncthing
    #    d. Compute diff: devices_to_add, devices_to_remove
    #    e. Acquire client._config_lock, apply: add missing, remove stale
    # 3. For folders where device list becomes empty (only self):
    #    Delete the folder (refcount = 0)
```

### Implementation: `set_folder_devices`

New proxy method that replaces the device list atomically:

```
def set_folder_devices(self, folder_id, device_ids):
    """Set the folder's device list to exactly these device_ids.

    Uses PUT /rest/config/folders/{id} with the full folder config.
    Adds self device_id automatically (Syncthing requires it).

    MUST be called while holding client._config_lock (RLock) for the
    full GET-compute-PUT cycle. This prevents interleaving with other
    config mutations. Two threads computing DIFFERENT desired states
    would NOT produce the same result — the lock prevents corruption.
    See existing lock pattern at syncthing_proxy.py:231 and :293.
    """
    # Caller must hold client._config_lock
    # Get current folder config
    # Replace devices list with new list
    # PUT the updated config
```

This is a combination of the existing `update_folder_devices` (add) and `remove_device_from_folder` (remove) into a single atomic operation.

### When Device Lists Are Recomputed

| Event | Scope |
|---|---|
| Member joins team | All folders for that team's projects |
| Member leaves team | All folders for that team's projects |
| Project shared with team | All folders for that project |
| Project removed from team | All folders for that project |
| Device change detected (EC-2) | All folders for all teams the device is in |
| Metadata reconciliation discovers new member | All folders for that team's projects |
| v3 migration startup | All folders |

### Breakpoints Addressed

- BP-2 (additive-only): Replaced with declarative set
- BP-7 (no device removal): `set_folder_devices` removes stale devices
- BP-18 (underused remove): `remove_device_from_folder` logic incorporated into `set_folder_devices`

---

## ADR-4: Cross-Team Safe Cleanup

### Decision

Cleanup operations use **device subtraction** (remove a team's devices from shared folders) rather than **folder deletion**. A folder is only deleted when its computed device list becomes empty (only self remaining), meaning no team claims it anymore.

### Status

Accepted.

### Context

v2 cleanup (BP-3, BP-4) removes entire folders without checking cross-team usage. Leaving Team A deletes `karma-out--alice.laptop--P2_suffix` even if Team B also uses that folder.

### Cleanup Logic: Leave Team

```
async def cleanup_for_team_leave(proxy, config, conn, team_name):
    """Clean up when leaving a team. Subtracts team's devices from shared folders."""

    team_members = list_members(conn, team_name)
    team_projects = list_team_projects(conn, team_name)
    team_device_ids = {m["device_id"] for m in team_members}

    for proj in team_projects:
        suffix = _compute_proj_suffix(proj)

        # For each folder related to this project:
        #   Recompute the desired device list WITHOUT this team
        #   (union of all OTHER teams sharing this project)
        desired_devices = compute_union_devices_excluding_team(
            conn, suffix, team_name
        )

        # Apply the new device list
        # If desired_devices is empty (no other team claims this folder):
        #   Delete the folder
        # Else:
        #   set_folder_devices(folder_id, desired_devices)

    # Remove team-specific folders (handshake, metadata)
    # These are team-scoped, so always safe to delete
    remove_folder(karma-join--{self}--{team_name})
    remove_folder(karma-meta--{team_name})

    # Remove devices not used by any remaining team
    for device_id in team_device_ids:
        if not device_in_any_other_team(conn, device_id, team_name):
            proxy.remove_device(device_id)
```

### Cleanup Logic: Remove Member

```
async def cleanup_for_member_removal(proxy, config, conn, team_name, member_device_id):
    """Clean up when removing a member from a team."""

    # Recompute device lists for all project folders in this team
    # The removed member's device will no longer appear in the union
    # (because they're removed from sync_members for this team)
    compute_and_apply_device_lists(proxy, config, conn, team_name)

    # Remove the member's inbox folder ONLY if no other team claims it
    member_tag = get_member_tag(conn, member_device_id)
    for proj in list_team_projects(conn, team_name):
        suffix = _compute_proj_suffix(proj)
        inbox_id = build_outbox_id(member_tag, suffix)
        desired_devices = compute_union_devices_for_folder(conn, inbox_id)
        if not desired_devices or desired_devices == {config.syncthing.device_id}:
            proxy.remove_folder(inbox_id)
        else:
            set_folder_devices(inbox_id, desired_devices)

    # Remove member's handshake folder (team-scoped, always safe)
    remove_folder(karma-join--{member_tag}--{team_name})

    # Remove device if not in any other team
    if not device_in_any_other_team(conn, member_device_id, team_name):
        proxy.remove_device(member_device_id)
```

### Cleanup Logic: Remove Project From Team

```
async def cleanup_for_project_removal(proxy, config, conn, team_name, project):
    """Clean up when removing a project from a team."""

    suffix = _compute_proj_suffix(project)

    # Recompute device lists for all folders with this suffix
    # Without this team, some devices may no longer need access
    desired_devices = compute_union_devices_excluding_team(conn, suffix, team_name)

    # For my outbox
    outbox_id = build_outbox_id(config.member_tag, suffix)
    if not desired_devices:
        proxy.remove_folder(outbox_id)
    else:
        set_folder_devices(outbox_id, desired_devices)

    # For each peer's inbox
    # Same logic: recompute, subtract, delete if empty

    # Filesystem cleanup: remove received session data for this project
    cleanup_data_for_project(conn, team_name, project_encoded_name)
```

### Breakpoints Addressed

- BP-3 (destructive team cleanup): Replaced with device subtraction
- BP-4 (cross-team inbox removal): Replaced with refcount check
- RC-2 (partial cleanup): Addressed by making cleanup idempotent (recompute desired state, apply diff)

---

## ADR-5: Edge Case Handling

### Decision

Address each edge case with specific mechanisms.

### BP-9: member_tag Collision Prevention

**Problem:** Two different users with the same `user_id` and same hostname produce identical `member_tag` values. No validation exists at join/accept time.

**Solution:** Add collision detection at three points:

1. **At join time (joiner side):** Before creating the handshake folder, query the metadata folder for existing member states. If any member_state has the same `member_tag` but a different `device_id`, abort the join and prompt the user to choose a different `user_id`.

2. **At accept time (leader side):** Before `upsert_member`, check:
   ```sql
   SELECT device_id FROM sync_members
   WHERE member_tag = ? AND device_id != ?
   ```
   If collision detected, reject the device (dismiss pending, log warning).

3. **Metadata folder validation:** `reconcile_metadata_folder` checks for multiple member states with the same `member_tag` but different `device_id` values. If found, log a critical warning.

### BP-12: Folder Acceptance Before Metadata Sync

**Problem:** `auto_share_folders` reads subscriptions from metadata, but metadata may not have synced yet. All projects are shared regardless of opt-out preferences.

**Solution:** Two-phase folder sharing with stateless detection:

1. **Phase 1 (immediate):** Share only the metadata folder with the new member. Do NOT share project folders yet.

2. **Phase 2 (deferred, stateless detection):** On each reconciliation cycle (60s timer), detect members who need project folders via a stateless check: "member exists in `sync_members` for this team, but their device is not in any of this team's project folders' device lists." When detected, run `compute_and_apply_device_lists` to share project folders with subscription awareness.

**Detection mechanism:** The reconciliation timer (60s) performs this stateless check on every cycle. No durable timer or timestamp is needed. If metadata has not synced yet (member has no subscription preferences), the default opt-in behavior shares all projects. Once metadata arrives with opt-out preferences, the next reconciliation cycle self-corrects by removing the member from opted-out folders.

**No fallback timer needed:** The stateless detection runs every 60s and always converges to the correct state. Late-arriving subscription preferences self-correct on the next cycle.

### BP-13: git_identity Change Creates Orphaned Folders

**Problem:** Changing a project's git remote URL creates a new folder suffix. Old folders persist.

**Solution:**

1. **Store the folder suffix in `sync_team_projects`** as a new column `folder_suffix`. Computed once at share time, immutable afterward. This decouples the folder ID from the current `git_identity`.

2. **On `git_identity` change detection:** Log a warning event but do NOT change the folder suffix. The old suffix continues working.

3. **Manual migration:** Provide a CLI command `karma sync migrate-project --team T --project P` that:
   - Creates new folders with new suffix
   - Waits for sync completion
   - Removes old folders
   - Updates `sync_team_projects.folder_suffix`

### BP-14: sync_rejected_folders Not Team-Scoped

**Problem:** Rejection is stored by `folder_id`. Since folder IDs lack team scope, rejecting a folder in one team rejects it for all teams.

**Solution:** Change the rejection key to `(folder_id, team_name)`:

```sql
CREATE TABLE IF NOT EXISTS sync_rejected_folders (
    folder_id TEXT NOT NULL,
    team_name TEXT NOT NULL,
    rejected_at TEXT DEFAULT (datetime('now')),
    PRIMARY KEY (folder_id, team_name)
);
```

`is_folder_rejected` checks `WHERE folder_id = ? AND team_name = ?`. A folder can be rejected in Team A but accepted in Team B.

### EC-1: member_tag Collision (Addressed by BP-9)

See BP-9 above. Additionally, consider adding a random 4-character suffix to `machine_tag` if the hostname is very common (e.g., "macbook-pro", "localhost"). This reduces collision probability from `P(same user_id AND same hostname)` to `P(same user_id AND same hostname AND same random suffix)`.

**Decision:** Do NOT add random suffix. The BP-9 collision detection is sufficient. Random suffixes would break the human-readable property of member_tags.

### EC-2: Device ID Changes (Syncthing Reinstall)

**Problem:** Old device ID persists in all teams' member lists and folder device lists. No migration path. After Syncthing reinstall, the device has a new device ID, no pairings, and no access to metadata folders.

**Solution:**

1. **Detection:** On startup, if `config.syncthing.device_id` differs from the stored device_id in any team's member record where `member_tag == config.member_tag`, flag a device ID change.

2. **User notification:** Log a warning and surface via the API: "Your Syncthing device ID has changed. You must re-join all teams to restore sync." The device cannot self-heal because it has no pairings and no metadata folder access after a Syncthing reinstall.

3. **Re-join required:** The user must re-join each team using a new invite code. The old member state in peers' metadata folders will show the stale device_id. Peers will clean up the stale entry via `compute_and_apply_device_lists` (the old device_id won't appear in any union query because the old member record will be replaced by the new one after re-joining).

4. **Local cleanup:** On device ID change detection, clear local `sync_members` records that reference the old device_id for this member_tag. Do NOT attempt to write to metadata folders (they are inaccessible without pairings).

**NOTE:** Self-heal via metadata folder is NOT possible in this scenario. The device has no pairings after Syncthing reinstall, so it cannot access any metadata folders to update its member state.

### EC-6: Folder Rejection + Re-Share

**Problem:** With team-scoped rejections (BP-14 fix), this is partially addressed. But `auto_share_folders` still doesn't check rejections.

**Solution:** `compute_and_apply_device_lists` checks `sync_rejected_folders` before including a device in a folder's device list. If the local device has rejected folder X for team T, the local device is excluded from the device list for folder X when computing on behalf of team T.

In practice: the local device writes a rejection to the metadata folder. Other members read this and exclude the rejecting device from the folder's device list.

### Breakpoints Addressed

- BP-9: Collision detection at join/accept
- BP-12: Two-phase folder sharing
- BP-13: Immutable folder suffix
- BP-14: Team-scoped rejection
- EC-1: Covered by BP-9
- EC-2: Device ID change detection + re-join required
- EC-6: Team-scoped rejection + metadata awareness

---

## ADR-6: Migration Strategy (v2 to v3)

### Decision

**Rolling migration with backward compatibility window.** v3 code handles both v2 and v3 folder patterns. Migration runs once per device on first v3 startup.

### Status

Accepted.

### Migration Steps (Per Device, On First v3 Startup)

```
STEP 1: Disable all introducer flags
  For each configured device:
    if device.introducer: set_device_introducer(device_id, False)

STEP 2: Schema migration (v17 -> v18)
  ALTER TABLE sync_team_projects ADD COLUMN folder_suffix TEXT;
  ALTER TABLE sync_rejected_folders ADD COLUMN team_name TEXT;
  (see Schema Changes section below)

STEP 3: Backfill folder_suffix
  For each row in sync_team_projects:
    folder_suffix = _compute_proj_suffix(git_identity, path, encoded_name)
    UPDATE sync_team_projects SET folder_suffix = ? WHERE ...

STEP 4: Migrate rejected folders
  For each row in sync_rejected_folders:
    If team_name is NULL:
      # Try to determine team from folder_id
      team = find_team_for_folder(conn, [folder_id])
      UPDATE sync_rejected_folders SET team_name = ? WHERE folder_id = ?

STEP 5: Recompute all device lists
  For each team:
    compute_and_apply_device_lists(proxy, config, conn, team_name)
  This removes any leaked devices from cross-team contamination.

STEP 6: Clean up phantom teams
  For each team in list_teams(conn):
    meta_dir = KARMA_BASE / "metadata-folders" / team_name
    If meta_dir does not exist AND team has no local join_code:
      # Phantom team created by introducer leak (BP-6)
      delete_team(conn, team_name)

STEP 7: Record migration
  INSERT INTO schema_version (version) VALUES (18)
```

### Backward Compatibility

- **Folder IDs unchanged.** v2 and v3 devices share the same folder IDs. No folder recreation needed.
- **Metadata folder format unchanged.** v3 adds optional fields to member state JSON (e.g., `rejections`) but reads v2 format without error.
- **v2 devices continue to work** during migration window (their additive device list updates are harmless; v3 devices will correct the lists on next recompute cycle).
- **Handshake folders unchanged.** Join flow is backward compatible.

### Known Limitation: v2/v3 Coexistence Oscillation

During the migration window, v2 and v3 devices may oscillate device lists. v3 removes a leaked device from a folder, then a v2 device adds it back (via its additive-only `update_folder_devices`), then v3 removes it again on the next recompute cycle.

**Impact:** Harmless. No data corruption or sync failure. Device lists fluctuate but converge once all devices upgrade. Syncthing handles transient device list changes gracefully (folders are not deleted, just temporarily inaccessible to the removed device).

**Recommendation:** Complete the v3 migration across all devices within 24 hours to minimize oscillation. The reconciliation cycle (60s) will converge device lists within one cycle after the last v2 device upgrades.

### Risk Mitigation

- **Step 5 is idempotent.** Can be re-run safely.
- **Step 1 is non-destructive.** Devices remain paired; only the auto-propagation behavior changes.
- **Step 6 requires confirmation.** Phantom team detection checks for missing metadata folder AND missing join code. Teams the user legitimately joined (which have join codes stored) are preserved.

---

## Data Flow Diagrams

### Join Team Flow (v3)

```
Joiner                           Leader                          Peer (existing member)
  |                                |                                |
  |-- pair leader (no introducer)--|                                |
  |-- create handshake folder ---->|                                |
  |-- create metadata folder ----->|                                |
  |-- write member state --------->|                                |
  |                                |                                |
  |                         auto_accept_pending_peers()             |
  |                                |-- add_device(joiner, False) -->|
  |                                |-- upsert_member() ----------->|
  |                                |-- share metadata folder ------>|
  |                                |   (DO NOT share project        |
  |                                |    folders yet — Phase 1)      |
  |                                |                                |
  |                         [metadata syncs to all members]         |
  |                                |                                |
  |                                |                     mesh_pair_from_metadata()
  |                                |                                |-- reads metadata
  |                                |                                |-- discovers joiner
  |                                |                                |-- add_device(joiner)
  |                                |                                |-- compute_and_apply_device_lists()
  |                                |                                |
  |                         [metadata synced, joiner's state visible]
  |                                |                                |
  |  mesh_pair_from_metadata()     |                                |
  |  (joiner discovers peers)     |                                |
  |-- add_device(peer, False) --->|                                |
  |-- compute_and_apply_device_lists()                              |
  |                                |                                |
  |                         compute_and_apply_device_lists()        |
  |                                |   (Phase 2 — project folders   |
  |                                |    shared with subscription    |
  |                                |    awareness)                  |
  |                                |                                |
  |<-- pending project folders ----|                                |
  |-- accept project folders ----->|                                |
```

### Leave Team Flow (v3)

```
Leaver                           Remaining Members
  |                                |
  |-- cleanup_for_team_leave() --->|
  |   For each project folder:     |
  |     compute union WITHOUT team |
  |     If union empty:            |
  |       remove_folder()          |
  |     Else:                      |
  |       set_folder_devices()     |
  |                                |
  |   remove handshake folder      |
  |   remove metadata folder       |
  |                                |
  |   For each team device:        |
  |     If not in other teams:     |
  |       remove_device()          |
  |                                |
  |   delete_team(conn)            |
  |                                |
  |                         [metadata folder reflects removal]
  |                                |
  |                         mesh_pair_from_metadata()
  |                                |-- leaver no longer in metadata
  |                                |-- compute_and_apply_device_lists()
  |                                |   (leaver's device removed from
  |                                |    folders for this team only)
```

### Share Project Flow (v3)

```
Sharer                           All Team Members
  |                                |
  |-- add_team_project(conn) ----->|
  |   (stores folder_suffix)       |
  |                                |
  |-- ensure_outbox_folder() ----->|
  |   (uses compute union:         |
  |    all devices from all teams  |
  |    sharing this project)       |
  |                                |
  |-- ensure_inbox_folders() ----->|
  |   For each member:             |
  |     compute union devices      |
  |     set_folder_devices()       |
  |                                |
  |                         [peers receive pending folder offers]
  |                                |
  |                         accept_pending_folders()
  |                                |-- compute_and_apply_device_lists()
```

### Remove Project From Team Flow (v3)

```
Remover                          Remaining Members
  |                                |
  |-- remove_team_project(conn) -->|
  |                                |
  |-- cleanup_for_project_removal()|
  |   compute union WITHOUT team   |
  |   For each folder with suffix: |
  |     If union empty:            |
  |       remove_folder()          |
  |       cleanup filesystem       |
  |     Else:                      |
  |       set_folder_devices()     |
  |                                |
  |                         [metadata/reconciliation cycle]
  |                                |
  |                         compute_and_apply_device_lists()
  |                                |   (removed team's devices
  |                                |    subtracted from folders)
```

### Remove Member Flow (v3)

```
Remover (creator)                Removed Member          Other Members
  |                                |                        |
  |-- remove_member(conn) -------->|                        |
  |-- write_removal_signal() ----->|                        |
  |                                |                        |
  |-- cleanup_for_member_removal() |                        |
  |   compute_and_apply_device_lists()                      |
  |   (removed device excluded     |                        |
  |    from union for this team)   |                        |
  |                                |                        |
  |   For member's inbox folders:  |                        |
  |     compute union              |                        |
  |     If empty: remove_folder()  |                        |
  |     Else: set_folder_devices() |                        |
  |                                |                        |
  |   Remove handshake folder      |                        |
  |   Remove device if no teams    |                        |
  |                                |                        |
  |                         [metadata syncs removal signal] |
  |                                |                        |
  |                         is_removed() → True             |
  |                         _auto_leave_team()              |
  |                                |                        |
  |                                |              mesh_pair_from_metadata()
  |                                |                        |-- reads removal
  |                                |                        |-- compute_and_apply()
  |                                |                        |   (removed device
  |                                |                        |    excluded from lists)
```

---

## Schema Changes (v17 -> v18) — Atomic Migration

All schema changes are applied in a single atomic v18 migration in Phase 1. Phases 2-4 use the already-migrated schema. This prevents ambiguity about which phase owns the migration.

### New Columns

```sql
-- Store computed folder suffix (immutable after creation)
ALTER TABLE sync_team_projects ADD COLUMN folder_suffix TEXT;

-- Durable leave-in-progress marker (survives restarts)
-- NULL = normal, datetime = cleanup started at this time
ALTER TABLE sync_teams ADD COLUMN pending_leave TEXT;
```

### Modified Tables

```sql
-- sync_rejected_folders: change PK to (folder_id, team_name)
-- SQLite cannot ALTER TABLE to change PK, so drop and recreate
-- NOTE: Unattributable rejections are dropped during migration (see below)
CREATE TABLE sync_rejected_folders (
    folder_id TEXT NOT NULL,
    team_name TEXT NOT NULL,
    rejected_at TEXT DEFAULT (datetime('now')),
    PRIMARY KEY (folder_id, team_name)
);
```

### New Index

```sql
CREATE INDEX IF NOT EXISTS idx_sync_team_projects_suffix
  ON sync_team_projects(folder_suffix);
```

### Migration SQL + Python

The migration has both SQL and Python steps, run together in Phase 1:

```sql
-- v18 migration (SQL portion)

-- 1. Add folder_suffix column
ALTER TABLE sync_team_projects ADD COLUMN folder_suffix TEXT;

-- 2. Add pending_leave column for durable cleanup tracking (RC-1, RC-2)
ALTER TABLE sync_teams ADD COLUMN pending_leave TEXT;

-- 3. Create new sync_rejected_folders table (empty — Python step populates it)
CREATE TABLE sync_rejected_folders_v18 (
    folder_id TEXT NOT NULL,
    team_name TEXT NOT NULL,
    rejected_at TEXT DEFAULT (datetime('now')),
    PRIMARY KEY (folder_id, team_name)
);

-- 4. New index
CREATE INDEX IF NOT EXISTS idx_sync_team_projects_suffix
  ON sync_team_projects(folder_suffix);
```

```python
# v18 migration (Python portion, runs between SQL steps 3 and table swap)

# Step A: Backfill folder_suffix (Python logic for fallback)
for row in cursor.execute("SELECT * FROM sync_team_projects"):
    suffix = _compute_proj_suffix(row["git_identity"], row["path"], row["encoded_name"])
    cursor.execute("UPDATE sync_team_projects SET folder_suffix = ? WHERE ...", (suffix,))

# Step B: Migrate rejected folders — attribute to teams, drop orphans
for row in cursor.execute("SELECT folder_id, rejected_at FROM sync_rejected_folders"):
    team = find_team_for_folder(conn, [row["folder_id"]])
    if team:
        # Attributable rejection — migrate to new table
        cursor.execute(
            "INSERT INTO sync_rejected_folders_v18 (folder_id, team_name, rejected_at) VALUES (?, ?, ?)",
            (row["folder_id"], team, row["rejected_at"])
        )
    else:
        # Unattributable rejection — folder's project removed from all teams.
        # Drop it. If the folder is re-shared later, user can re-reject.
        log.info("Dropping orphaned rejection for folder %s (no team claims it)", row["folder_id"])

# Step C: Swap tables
cursor.execute("DROP TABLE sync_rejected_folders")
cursor.execute("ALTER TABLE sync_rejected_folders_v18 RENAME TO sync_rejected_folders")

# Step D: Retry any interrupted cleanups from before migration
for row in cursor.execute("SELECT name FROM sync_teams WHERE pending_leave IS NOT NULL"):
    log.warning("Team %s has interrupted cleanup — will retry on next timer cycle", row["name"])
```

```sql
-- Final: Record version
INSERT OR REPLACE INTO schema_version (version) VALUES (18);
```

### Summary of v18 Schema Changes

| Change | Purpose |
|--------|---------|
| `sync_team_projects.folder_suffix` | Decouple folder ID from git_identity changes (BP-13) |
| `sync_teams.pending_leave` | Durable cleanup tracking, survives restarts (RC-1, RC-2) |
| `sync_rejected_folders` recreated | Team-scoped PK `(folder_id, team_name)` (BP-14) |
| Orphaned rejections dropped | Stale rows for folders no team claims (C5) |

---

## Reconciliation Architecture (v3)

### Reconciliation Phases (Revised)

The v2 4-phase reconciliation (run on `GET /sync/pending-devices`) is restructured:

```
v3 Reconciliation (triggered by GET /sync/pending-devices and 60s timer):

  Phase 1: mesh_pair_from_metadata()
    Read all teams' metadata folders
    Pair with any undiscovered devices (no introducer)
    Upsert member records

  Phase 2: reconcile_pending_handshakes()
    Process pending karma-join-* folders from configured devices
    Create teams, add members (same as v2, works correctly)

  Phase 3: auto_accept_pending_peers()
    Accept pending devices offering karma-* folders
    Policy gate (same as v2, works correctly)

  Phase 4: compute_and_apply_device_lists()
    For all teams (or changed teams):
      Compute union device lists
      Apply to all project folders
      Remove stale devices, delete empty folders
```

**Removed:** `ensure_leader_introducers()` (no longer needed)
**Removed:** `reconcile_introduced_devices()` (replaced by Phase 1)
**Added:** Phase 4 as a dedicated step (was implicit in v2's auto_share_folders)

### Timer-Driven Reconciliation (60s)

Same as v2 but adds Phase 4:

```
reconcile_all_teams_metadata(config, conn, auto_leave=True)
  For each team:
    reconcile_metadata_folder()  # discover members, detect removals
    compute_and_apply_device_lists()  # ensure folder device lists are correct
```

### Race Condition Mitigation

**RC-1 (auto-leave vs reinvite):**
- Use the durable `pending_leave` column (see RC-2) to prevent re-creation during cleanup
- `reconcile_pending_handshakes` checks `pending_leave IS NULL` before creating/recreating teams
- Use `sync_removed_members` as the authoritative source: if device_id appears in removed_members for a team, handshake reconciliation skips it (already works in v2)

**RC-2 (partial cleanup):**
- Make cleanup idempotent: `compute_and_apply_device_lists` can always re-derive the correct state
- Do NOT delete team from DB until Syncthing cleanup succeeds
- Use the `pending_leave` column (added in v18 schema) for durability:
  - On cleanup start: `UPDATE sync_teams SET pending_leave = datetime('now') WHERE name = ?`
  - On cleanup success: `DELETE FROM sync_teams WHERE name = ?`
  - On startup: `SELECT name FROM sync_teams WHERE pending_leave IS NOT NULL` to retry interrupted cleanups
- Retry on every 60s timer cycle. After 5 failed attempts (5 minutes), log an error and surface via the API (`GET /sync/teams` should show teams with `pending_leave` status). No automatic escalation — user must manually resolve.

**RC-3 (no change needed):**
- Handled gracefully by v2, confirmed in audit.

**RC-4 (concurrent ensure_outbox_folder):**
- `set_folder_devices` is idempotent (sets to desired state), but two concurrent calls may compute DIFFERENT desired states if the DB changes between reads
- Safety is ensured by `client._config_lock` (RLock in `cli/karma/syncthing.py:59`) which serializes all config mutations
- `set_folder_devices` MUST acquire `client._config_lock` for the full GET-compute-PUT cycle (see existing lock pattern at `syncthing_proxy.py:231` and `:293`)
- This prevents interleaving of concurrent config mutations that would produce inconsistent results

**RC-5 (SQLite contention):**
- No change needed. WAL mode + single writer connection is sufficient for the single-machine model.

---

## Implementation Phases

### Phase 1: Declarative Device Lists (Foundation)

**Depends on:** Nothing (can be deployed independently)

**Scope:**
- New function `compute_union_devices(conn, suffix)` in `sync_folders.py`
- New function `compute_and_apply_device_lists(proxy, config, conn, team_name)` in `sync_folders.py`
- New proxy method `set_folder_devices(folder_id, device_ids)` in `syncthing_proxy.py`
- Modify `ensure_outbox_folder` and `ensure_inbox_folders` to use `compute_union_devices`
- **Complete v18 schema migration** (atomic, all changes in this phase):
  - Add `folder_suffix` column to `sync_team_projects`
  - Add `pending_leave` column to `sync_teams`
  - Recreate `sync_rejected_folders` with team-scoped PK `(folder_id, team_name)`
  - Drop unattributable rejections during migration
  - Add index on `sync_team_projects(folder_suffix)`
- Backfill `folder_suffix` values

**Files modified:**
- `api/services/sync_folders.py` — new functions, modify ensure_* functions
- `api/services/syncthing_proxy.py` — new `set_folder_devices` method
- `api/db/sync_queries.py` — new query `compute_union_devices`
- `api/db/schema.py` — complete v18 migration (all schema changes: folder_suffix, pending_leave, sync_rejected_folders recreation)
- `api/services/sync_identity.py` — modify `_compute_proj_suffix` to store result

**Breakpoints fixed:** BP-2, BP-7, BP-13 (schema), BP-14 (schema), BP-18

**Acceptance criteria:**
- `compute_union_devices` returns correct set for single-team and multi-team cases
- `set_folder_devices` correctly adds and removes devices
- `set_folder_devices` acquires `client._config_lock` for the full GET-compute-PUT cycle
- `ensure_outbox_folder` uses union query with `owner_member_tag` constraint
- `folder_suffix` populated for all existing team projects
- `pending_leave` column exists in `sync_teams`
- `sync_rejected_folders` has `(folder_id, team_name)` PK after migration
- Unattributable rejections are dropped during migration (logged)
- Folder count warning logged at 200 folders, error at 500
- Existing tests pass

---

### Phase 2: Explicit Mesh Pairing (Replace Introducer)

**Depends on:** Phase 1 (needs `compute_and_apply_device_lists`)

**Scope:**
- New function `mesh_pair_from_metadata(proxy, config, conn)` in `sync_reconciliation.py`
- Remove `ensure_leader_introducers()` function
- Remove `reconcile_introduced_devices()` function
- Modify join flow: `introducer=False` on `add_device`
- Migration: disable existing introducer flags on startup

**Files modified:**
- `api/services/sync_reconciliation.py` — replace reconcile_introduced_devices, remove ensure_leader_introducers
- `api/routers/sync_teams.py` — join flow, remove introducer flag
- `api/routers/sync_devices.py` — update reconciliation phase order

**Breakpoints fixed:** BP-5, BP-6

**Acceptance criteria:**
- No device has `introducer=True` after migration
- Joining a team does NOT propagate foreign teams' devices
- Peers discover each other via metadata folder reading
- `mesh_pair_from_metadata` correctly pairs undiscovered devices

---

### Phase 3: Cross-Team Safe Cleanup

**Depends on:** Phase 1 (needs `compute_and_apply_device_lists` and `set_folder_devices`)

**Scope:**
- Rewrite `cleanup_syncthing_for_team` to use device subtraction
- Rewrite `cleanup_syncthing_for_member` to use device subtraction
- New function `cleanup_for_project_removal`
- Make `_auto_leave_team` idempotent (don't delete team if cleanup fails)

**Files modified:**
- `api/services/sync_folders.py` — rewrite cleanup functions
- `api/services/sync_metadata_reconciler.py` — idempotent auto-leave
- `api/db/sync_queries.py` — helper queries for cross-team checks

**Breakpoints fixed:** BP-3, BP-4, RC-2

**Acceptance criteria:**
- Leaving Team A does NOT remove folders used by Team B
- Removing member from Team A does NOT remove their inbox if shared with Team B
- `_auto_leave_team` retries cleanup on next cycle if it fails
- Cleanup is idempotent (running twice produces same result)

---

### Phase 4: Edge Cases and Hardening

**Depends on:** Phases 1-3

**Scope:**
- BP-9: member_tag collision detection at join/accept
- BP-12: Two-phase folder sharing (metadata first, then projects)
- BP-13: Immutable folder_suffix (store in DB, don't recompute)
- BP-14: Team-scoped rejected folders (query changes; schema already migrated in Phase 1)
- EC-2: Device ID change detection and re-join notification
- EC-6: Team-scoped rejection in `compute_and_apply_device_lists`
- RC-1: `pending_leave` guard in reconciliation (uses durable column from v18 schema)

**Files modified:**
- `api/services/sync_reconciliation.py` — collision detection, `pending_leave` guard
- `api/services/sync_folders.py` — two-phase sharing, rejection checks
- `api/db/sync_queries.py` — team-scoped rejection queries (using v18 schema from Phase 1)
- `api/services/sync_metadata_reconciler.py` — device ID change detection
- `cli/karma/config.py` — device ID change detection on startup

**Breakpoints fixed:** BP-9, BP-12, BP-13, BP-14, EC-1, EC-2, EC-6, RC-1

**Acceptance criteria:**
- Duplicate member_tag at join time produces clear error
- New member receives metadata folder before project folders
- Changing git remote does NOT create orphaned folders
- Rejecting a folder in Team A does NOT affect Team B
- Reinstalling Syncthing is detected on startup; user is warned to re-join teams
- Auto-leave and reinvite do not race (`pending_leave` column prevents team re-creation during cleanup)

---

## Commit Strategy

| Phase | Commits | Description |
|---|---|---|
| Phase 1 | 3-4 | Complete v18 schema migration, compute_union_devices, set_folder_devices, integrate into ensure_* |
| Phase 2 | 2-3 | mesh_pair_from_metadata, remove introducer code, migration step |
| Phase 3 | 2-3 | Rewrite cleanup functions, idempotent auto-leave |
| Phase 4 | 4-5 | One commit per edge case fix (BP-9, BP-12, BP-13/14 queries, EC-2, RC-1) |

Total: ~12-15 commits across 4 phases.

---

## Success Criteria

### Functional

1. A device in 4 teams sharing overlapping projects has correct folder device lists (union of all relevant teams, no leaks)
2. Leaving Team A does not break sync for Team B (even if they share projects)
3. Removing member M from Team A does not affect M's membership in Team B
4. No phantom team creation (no introduced artifacts from foreign teams)
5. Folder rejections are team-scoped (rejecting in Team A does not affect Team B)
6. Device ID change (Syncthing reinstall) is detected on startup and user is warned to re-join teams; stale device entries are cleaned up by peers via `compute_and_apply_device_lists`

### Performance

7. Total folder count per device stays under 200 for the target scale (10 teams, 20 projects, 10 members)
8. Device list recomputation completes in under 2 seconds for target scale
9. No increase in Syncthing REST API calls during normal operation (recomputation is event-driven, not polling)

### Migration

10. v2 to v3 migration is automatic (runs on first startup)
11. v2 and v3 devices can coexist during migration window
12. No data loss during migration (session data, team memberships, settings preserved)

---

## Integration Test Strategy: Multi-Team Overlap

The audit document's 4-team test setup (section 9) provides the basis for integration tests. The test setup uses 4 machines (M1-M4) across 3 users, with 4 teams sharing overlapping projects:

| Team | Members | Projects |
|------|---------|----------|
| T1 | M1, M2, M3 | P1, P2 |
| T2 | M1, M2 | P2, P3 |
| T3 | M2, M3, M4 | P1, P3 |
| T4 | M1, M4 | P2 |

Key test scenarios derived from this setup:

1. **Union device list correctness:** M1's outbox for P2 should include devices from T1, T2, T4 (all teams where M1 is a member AND P2 is shared). Must NOT include M4's T3 device for P2 (M4 is in T3, but P2 is not in T3).
2. **Leave team — device subtraction:** M1 leaves T2. M1's P2 outbox should still include T1 and T4 devices. M1's P3 outbox should become empty (only T2 claimed P3 for M1) and be deleted.
3. **Remove member — cross-team preservation:** Remove M2 from T1. M2's P1 outbox should still include T3 devices. M2's P2 outbox should still include T2 devices.
4. **Folder rejection — team-scoped:** M3 rejects P1 in T1. M3 should still receive P1 from T3.
5. **Device ID change:** M4 reinstalls Syncthing. M4's stale device_id is cleaned up from T3 and T4 folders by peers on next recompute cycle.

Tests should use mocked Syncthing API responses and in-memory SQLite to validate the SQL queries and reconciliation logic without requiring actual Syncthing instances.

---

## Must Have

- Declarative device list management (compute desired state, apply diff)
- Explicit mesh pairing (no introducer flags)
- Cross-team safe cleanup (device subtraction, not folder deletion)
- Team-scoped folder rejections
- member_tag collision detection
- Backward-compatible migration from v2

## Must NOT Have

- Team-scoped folder IDs (rejected — causes session duplication)
- Central coordination server (violates P2P constraint)
- Breaking changes to metadata folder format (must be backward compatible)
- Manual migration steps (must be automatic on startup)
- New folder types (outbox/inbox/handshake/metadata is sufficient)

---

## Appendix: Key Query — Union Device List

The core query that enables the project channel model. All variants include the `owner_member_tag` constraint to scope results to teams where the folder owner is a member (see C1 fix in ADR-3).

### Variant 1: Base union (for `compute_and_apply_device_lists`)

```sql
-- Given a folder suffix and owner, compute all devices that should have access
-- across all teams that share a project with that suffix AND include the owner.
--
-- Input: :suffix (e.g., "jayantdevkar-claude-karma"), :owner_member_tag
-- Output: set of device_ids

SELECT DISTINCT sm.device_id
FROM sync_team_projects stp
JOIN sync_members sm ON sm.team_name = stp.team_name
WHERE stp.folder_suffix = :suffix
  AND sm.device_id IS NOT NULL
  AND sm.device_id != ''
  AND stp.team_name IN (
    SELECT team_name FROM sync_members
    WHERE member_tag = :owner_member_tag
  )
```

### Variant 2: For a specific member's outbox (includes owner's own devices)

```sql
-- Union of team devices for the owner's outbox folder.
-- The owner_member_tag is extracted from the folder ID.
-- Owner's own devices are included automatically because the owner
-- is a member of the teams returned by the subquery.
--
-- Input: :suffix, :owner_member_tag
SELECT DISTINCT sm.device_id
FROM sync_team_projects stp
JOIN sync_members sm ON sm.team_name = stp.team_name
WHERE stp.folder_suffix = :suffix
  AND sm.device_id IS NOT NULL
  AND sm.device_id != ''
  AND stp.team_name IN (
    SELECT team_name FROM sync_members
    WHERE member_tag = :owner_member_tag
  )
```

### Variant 3: For cleanup (excluding a specific team)

```sql
-- Union WITHOUT a specific team, still scoped to owner's teams
-- Used by cleanup_for_team_leave and cleanup_for_project_removal
--
-- Input: :suffix, :excluded_team, :owner_member_tag
SELECT DISTINCT sm.device_id
FROM sync_team_projects stp
JOIN sync_members sm ON sm.team_name = stp.team_name
WHERE stp.folder_suffix = :suffix
  AND stp.team_name != :excluded_team
  AND sm.device_id IS NOT NULL
  AND sm.device_id != ''
  AND stp.team_name IN (
    SELECT team_name FROM sync_members
    WHERE member_tag = :owner_member_tag
  )
```
