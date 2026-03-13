# Sync v2 Audit Findings — Multi-Team Scalability Analysis

> **Date:** 2026-03-13
> **Status:** Observations for v3 design input
> **Scope:** Multi-team, multi-member, multi-project overlap behaviors
> **Audience:** Agents and developers designing sync v3

---

## Table of Contents

1. [Test Setup](#1-test-setup)
2. [Component Behavior Observations](#2-component-behavior-observations)
3. [Timeline Walkthrough: T4 → T3 → T2 → T1](#3-timeline-walkthrough)
4. [Cross-Team Overlap Matrix](#4-cross-team-overlap-matrix)
5. [Observed Breakpoints (BP-1 through BP-8)](#5-observed-breakpoints)
6. [Syncthing Primitive Behaviors](#6-syncthing-primitive-behaviors)
7. [Reconciliation Loop Observations](#7-reconciliation-loop-observations)
8. [Race Conditions & Timing](#8-race-conditions--timing)
9. [Edge Cases (EC-1 through EC-7)](#9-edge-cases)
10. [Filesystem & Data Flow Observations](#10-filesystem--data-flow-observations)
11. [Scalability Observations](#11-scalability-observations)
12. [Additional Breakpoints (BP-9 through BP-18)](#12-additional-breakpoints-investigated)
13. [Observations That Work Correctly (OK-1 through OK-7)](#13-observations-that-work-correctly)
14. [Open Questions for v3](#14-open-questions-for-v3)

---

## 1. Test Setup

### Devices

| Label | User | member_tag | Description |
|-------|------|------------|-------------|
| M1 | Jayant | `jayant.macbook` | Jayant's MacBook |
| M2 | Jayant | `jayant.mac-mini` | Jayant's Mac Mini (same user, different machine) |
| M3 | Alice | `alice.laptop` | Alice's Laptop |
| M4 | Bruce | `bruce.mac-mini` | Bruce's Mac Mini |
| M5 | ? | `?.?` | Additional member |
| M6 | ? | `?.?` | Additional member |

### Teams (creation order: T4 → T3 → T2 → T1)

| Team | Leader | Members | Projects |
|------|--------|---------|----------|
| T4 | M4 | M1, M3, M5, M6 | P1, P2, P3 |
| T3 | M2 | M3, M2, M1 | P3 |
| T2 | M3 | M3, M1 | P2 |
| T1 | M1 | M1, M2 | P1 |

### Assumptions for This Analysis

- All members already have the shared projects locally
- Leaders share the projects after team creation
- Members join one after another via join code
- Default settings (auto_accept=false, sync_direction=both)

---

## 2. Component Behavior Observations

### 2.1 Folder ID Format

**Observed:** Folder IDs use format `karma-out--{member_tag}--{suffix}` where suffix derives from `git_identity` (replace `/` with `-`) or project encoded name.

**Observation:** The folder ID contains NO team identifier. The same (member_tag, project) pair across multiple teams produces the **identical folder ID**.

```
File: api/services/folder_id.py

karma-out--{member_tag}--{suffix}     ← session outbox/inbox
karma-join--{member_tag}--{team_name} ← handshake (HAS team)
karma-meta--{team_name}               ← metadata  (HAS team)
```

Only outbox/inbox folders lack team scoping.

### 2.2 update_folder_devices Is Additive (Union)

**Observed in:** `api/services/syncthing_proxy.py`

`update_folder_devices(folder_id, device_ids)` **adds** devices to the existing folder device list. It never removes devices. It skips duplicates.

**Implication:** Once a device is added to a folder, there is no code path in `ensure_outbox_folder` or `ensure_inbox_folders` that removes it. The device list is monotonically growing during normal operation.

### 2.3 Cleanup Removes Entire Folders

**Observed in:** `api/services/sync_folders.py:355-426`

`cleanup_syncthing_for_team()` matches outbox folders by `(member_tag in team_members AND suffix in team_project_suffixes)` and calls `proxy.remove_folder()` — removing the **entire folder**, not individual devices.

**Observation:** There is NO cross-team check before folder removal. The only cross-team check exists for **devices** (line 415-418):
```python
other_count = conn.execute(
    "SELECT COUNT(*) FROM sync_members WHERE device_id = ? AND team_name != ?",
    (device_id, team_name),
).fetchone()[0]
if other_count == 0:
    # only then remove device
```

No equivalent query exists for folders:
```python
# THIS DOES NOT EXIST:
# "SELECT COUNT(*) FROM sync_team_projects WHERE project_suffix = ? AND team_name != ?"
```

### 2.4 Cleanup for Member Removal

**Observed in:** `api/services/sync_folders.py:429-487`

`cleanup_syncthing_for_member()` behavior:
- If folder is MY outbox → removes member's device from the folder (`remove_device_from_folder`)
- If folder is the MEMBER's outbox → removes the **entire inbox folder** (`remove_folder`)

**Observation:** No cross-team check on inbox removal. If the removed member is in another team sharing the same project, their inbox folder is destroyed for all teams.

### 2.5 Introducer Flag Behavior

**Observed in:** `api/routers/sync_teams.py` (join flow) and `api/services/sync_reconciliation.py`

When a device joins a team:
1. Joiner pairs leader with `introducer=True`
2. `ensure_leader_introducers()` re-enforces this flag on every `GET /sync/pending-devices` poll

**Observation:** The introducer flag is:
- Set per-device globally in Syncthing (not per-team)
- Permanent once set (no code path disables it after handshake)
- Re-enforced by `ensure_leader_introducers()` which iterates ALL teams' join codes

### 2.6 Reconciliation Creates Teams From Introduced Artifacts

**Observed in:** `api/services/sync_reconciliation.py:220-364`

`reconcile_pending_handshakes()` processes pending `karma-join--*` folders from already-configured devices. If the team doesn't exist locally:
```python
if not team_exists:
    create_team(conn, team_name, backend="syncthing")
```

**Observation:** This auto-creates teams from ANY handshake folder that arrives, regardless of whether the device was invited to that team.

### 2.7 Metadata Reconciliation Timer

**Observed in:** `api/services/watcher_manager.py:118-171` and `api/services/sync_metadata_reconciler.py`

- Runs every 60 seconds as a daemon thread
- Reads `metadata-folders/{team}/members/*.json` and `removals/*.json`
- Discovers new members and detects removal signals
- `auto_leave=True` triggers `cleanup_syncthing_for_team()` + `delete_team()` on removal detection

### 2.8 Pending Devices Endpoint Runs All Reconciliation

**Observed in:** `api/routers/sync_devices.py`

`GET /sync/pending-devices` runs 4 phases sequentially:
1. `ensure_leader_introducers()` — re-sets introducer flags
2. `reconcile_introduced_devices()` — discovers introduced peers
3. `reconcile_pending_handshakes()` — processes handshake folders
4. `auto_accept_pending_peers()` — accepts pending devices

**Observation:** This is the primary trigger for reconciliation during active use. The 60s metadata timer is the secondary mechanism.

---

## 3. Timeline Walkthrough

### Phase 1: T4 Created (Leader M4)

**M4 creates T4, shares P1, P2, P3:**
```
M4 Syncthing state:
  karma-meta--T4 (sendreceive)
  karma-out--bruce.mac-mini--P1_suffix (sendonly)
  karma-out--bruce.mac-mini--P2_suffix (sendonly)
  karma-out--bruce.mac-mini--P3_suffix (sendonly)
  Devices: [self]
```

**M1 joins T4 (join code: T4:bruce:DID_M4):**
```
M1 actions:
  Pairs DID_M4 with introducer=True
  Creates karma-join--jayant.macbook--T4 (sendonly, shared with DID_M4)
  Creates karma-meta--T4 (sendreceive, shared with DID_M4)

M4 reconciliation (on next GET /sync/pending-devices):
  auto_accept_pending_peers → sees DID_M1 offering handshake
  Handshake bypass: skips auto_accept policy check
  add_device(DID_M1)
  upsert_member(T4, jayant.macbook, DID_M1)
  auto_share_folders(T4, DID_M1):
    karma-out--bruce.mac-mini--P1 → add DID_M1 to device list
    karma-out--bruce.mac-mini--P2 → add DID_M1
    karma-out--bruce.mac-mini--P3 → add DID_M1
    Create karma-out--jayant.macbook--P1 (receiveonly, inbox for M1)
    Create karma-out--jayant.macbook--P2 (receiveonly)
    Create karma-out--jayant.macbook--P3 (receiveonly)

M1 pending folders appear:
  karma-out--bruce.mac-mini--P1/P2/P3 → "Receive from bruce"
  karma-out--jayant.macbook--P1/P2/P3 → "Send your sessions for..."
  M1 accepts all
```

**M3 joins T4:**

Same flow as M1. M4 accepts, runs auto_share_folders.

**Introducer propagation observed:**
- M3 set DID_M4 as introducer
- M4 has DID_M1 configured
- Syncthing propagates DID_M1 to M3 automatically
- M3's Syncthing auto-adds DID_M1 + any folders M4 shares with M1

**M3's reconcile_introduced_devices:**
- Finds DID_M1 (unknown, introduced by M4)
- Extracts team_name=T4 from folder parsing
- upsert_member(T4, jayant.macbook, DID_M1)
- auto_share_folders(T4, DID_M1)

**Reverse propagation:**
- M1 has DID_M4 as introducer
- M4 now has DID_M3 → propagates to M1
- M1 discovers M3, adds as T4 member

**M5, M6 join:** Same pattern. Full mesh forms via introducer cascades.

**T4 end state per device: ~17 Syncthing folders** (1 meta + 1 handshake + 3 outboxes + 12 inboxes for 4 peers × 3 projects)

**Observation:** Single-team operation works correctly. No issues observed.

---

### Phase 2: T3 Created (Leader M2)

M2 has no prior sync state. Creates T3, shares P3.

**M3 joins T3:**
```
M3 pairs DID_M2 with introducer=True  ← M3 now trusts M2 as introducer
M3 creates karma-join--alice.laptop--T3
M3 creates karma-meta--T3
```

M2 accepts M3. auto_share_folders creates P3 outbox/inbox.

**Introducer observation:** M3 set M2 as introducer. M2 currently only has M3 → no additional devices propagated yet.

**M1 joins T3:**
```
M1 pairs DID_M2 with introducer=True  ← M1 now trusts M2 as introducer
M1 creates karma-join--jayant.macbook--T3
```

M2 accepts M1. auto_share_folders:
```
For P3:
  ensure_outbox: karma-out--jayant.mac-mini--P3_suffix (M2's outbox)
    devices → [DID_M1, DID_M3, DID_M2]
  ensure_inbox: karma-out--jayant.macbook--P3_suffix (M1's outbox, receiveonly)
```

**Observation — same-user member_tag differentiation works:**
- M1's outbox: `karma-out--jayant.macbook--P3_suffix`
- M2's outbox: `karma-out--jayant.mac-mini--P3_suffix`
- Different member_tags → different folder IDs → no collision for this pair.

**Introducer propagation from M2:**
- M3 trusts M2 as introducer. M2 now has DID_M1. M3 already has DID_M1 from T4. No new info.
- M1 trusts M2 as introducer. M2 now has DID_M3. M1 already has DID_M3 from T4. No new info.

**Observation:** No cross-team leakage YET because M2 only has T3 members, which overlap with T4 anyway.

**HOWEVER — Folder ID Collision Detected:**

M1's P3 outbox for T4: `karma-out--jayant.macbook--P3_suffix`
M1's P3 outbox for T3: `karma-out--jayant.macbook--P3_suffix`

**Same folder ID.** When T3 calls `ensure_outbox_folder`, it calls `update_folder_devices` on the EXISTING T4 folder.

```
Before T3: karma-out--jayant.macbook--P3 devices = [DID_M3, DID_M4, DID_M5, DID_M6] (T4)
After T3:  karma-out--jayant.macbook--P3 devices = [DID_M3, DID_M4, DID_M5, DID_M6, DID_M2] (T4 ∪ T3)
```

**Since update_folder_devices is additive, DID_M2 gets ADDED to T4's folder.** M2 can now receive M1's P3 sessions even though M2 is not in T4.

Same collision for M3's P3 outbox: `karma-out--alice.laptop--P3_suffix`
- T4 devices + T3 device (DID_M2 added)
- M2 receives M3's P3 sessions via T4's folder — M2 is only in T3.

**Observation:** The additive behavior means cross-team device leakage is silent and cumulative. Devices from team B appear on team A's folder without any explicit sharing decision.

---

### Phase 3: T2 Created (Leader M3)

M3 creates T2, shares P2.

**M1 joins T2:**
```
M1: add_device(DID_M3) → already exists (from T4)
M1: set_device_introducer(DID_M3, True) ← M1 now trusts M3 as introducer
```

**Observation — Introducer flag accumulation on M1:**
```
M1's introducer trust list:
  DID_M4 = introducer (from T4 join)
  DID_M2 = introducer (from T3 join)
  DID_M3 = introducer (from T2 join)  ← NEW
```

M1 now trusts 3 different devices as introducers. Each will propagate ALL their devices and folders to M1.

**Folder collision — M3's P2 outbox:**
```
T4 outbox: karma-out--alice.laptop--P2_suffix  devices=[DID_M1, DID_M4, DID_M5, DID_M6]
T2 calls ensure_outbox with devices=[DID_M1]
After: devices=[DID_M1, DID_M4, DID_M5, DID_M6]  (additive, M1 already there)
```

No NEW devices added in this case because all T2 members (M1) are already in T4's device list. But the system made no conscious decision about this — it's an accident of the additive behavior.

---

### Phase 4: T1 Created (Leader M1)

M1 creates T1, shares P1.

**M2 joins T1:**
```
M2: pair DID_M1 with introducer=True ← M2 now trusts M1 as introducer
```

**Observation — Introducer Nuclear Cascade:**

M1's Syncthing config contains devices from ALL four teams:
```
DID_M2 (T1, T3), DID_M3 (T4, T2, T3), DID_M4 (T4), DID_M5 (T4), DID_M6 (T4)
```

M1's Syncthing config contains folders from ALL four teams:
```
karma-out--jayant.macbook--P1 (T4+T1), karma-out--jayant.macbook--P2 (T4),
karma-out--jayant.macbook--P3 (T4+T3), karma-out--bruce.mac-mini--P1/P2/P3,
karma-out--alice.laptop--P1/P2/P3, karma-out--jayant.mac-mini--P3,
karma-join--jayant.macbook--T4/T3/T2/T1,
karma-meta--T4/T3/T2/T1, plus all inbox folders...
```

**Via introducer, ALL of this propagates to M2.**

M2 auto-receives:
```
New devices: DID_M3, DID_M4, DID_M5, DID_M6  (none of which M2 shares a team with)
New folders: karma-join--jayant.macbook--T4    (T4 handshake — M2 is not in T4)
             karma-join--jayant.macbook--T2    (T2 handshake — M2 is not in T2)
             karma-out--bruce.mac-mini--*      (T4 inbox folders)
             karma-out--alice.laptop--*        (T4/T2 inbox folders)
             karma-meta--T4, karma-meta--T2    (metadata for non-joined teams)
```

**M2's reconciliation processes these artifacts:**

`reconcile_pending_handshakes` on M2:
- Sees `karma-join--jayant.macbook--T4` from DID_M1 (configured device)
- Team "T4" doesn't exist in M2's DB
- **Creates T4 locally:** `create_team(conn, "T4", backend="syncthing")`
- Adds M1 as member, adds self as member
- Calls auto_share_folders(T4, DID_M1)

`reconcile_introduced_devices` on M2:
- Unknown devices: DID_M4, DID_M5, DID_M6
- Finds karma folders shared with them → extracts team_name=T4
- upsert_member for each into T4

**Result: M2 becomes a phantom member of T4 (and T2) without invitation.**

**Observation:** This is not a theoretical scenario. Given the test setup, this WILL happen whenever T1 is created with M1 as leader and M2 as joiner, because M1 has cross-team state from T4.

---

## 4. Cross-Team Overlap Matrix

### Member-Team Overlap

```
         T4    T3    T2    T1
M1        x     x     x     x  ← in ALL teams (maximum introducer exposure)
M2              x           x
M3        x     x     x
M4        x
M5        x
M6        x
```

### Project-Team Overlap

```
         P1    P2    P3
T4        x     x     x
T3                    x
T2              x
T1        x
```

### Folder ID Collisions (same member + same project + different teams)

| Member | Project | Teams | Folder ID | Collision? |
|--------|---------|-------|-----------|-----------|
| M1 | P1 | T4, T1 | `karma-out--jayant.macbook--P1_suffix` | **YES** |
| M1 | P3 | T4, T3 | `karma-out--jayant.macbook--P3_suffix` | **YES** |
| M3 | P2 | T4, T2 | `karma-out--alice.laptop--P2_suffix` | **YES** |
| M3 | P3 | T4, T3 | `karma-out--alice.laptop--P3_suffix` | **YES** |
| M2 | P3 | T3 | `karma-out--jayant.mac-mini--P3_suffix` | No (single team) |
| M2 | P1 | T1 | `karma-out--jayant.mac-mini--P1_suffix` | No (single team) |

**4 collisions** in this 4-team setup. Each collision causes silent cross-team device accumulation.

### Introducer Leak Paths

```
M2 joins T1 → M1 is introducer for M2
  M1 knows [M3, M4, M5, M6] from T4
  → M2 gets T4 devices + folders (LEAK)

M1 joins T2 → M3 is introducer for M1
  M3 knows [M4, M5, M6] from T4
  → M1 gets T4 devices (already has them, no new leak in this case)

M3 joins T3 → M2 is introducer for M3
  M2 gains T4 artifacts from M1 later (via T1 join)
  → M3 gets T4 artifacts back via M2 (but already has from T4)
```

**Observation:** Any device that overlaps teams becomes a bridge. The most dangerous path is always through the device with the highest team count (M1 in this setup).

---

## 5. Observed Breakpoints

### BP-1: Outbox Folder ID Has No Team Scope

**Location:** `api/services/folder_id.py:build_outbox_id()`

**Behavior:** `karma-out--{member_tag}--{suffix}` — no team in the ID.

**Effect:** Same member sharing same project in N teams = 1 folder serving N teams. Device lists from all N teams merge silently (additive). Cleanup for any one team may destroy the folder for all N teams.

### BP-2: update_folder_devices Is Additive-Only

**Location:** `api/services/syncthing_proxy.py:update_folder_devices()`

**Behavior:** Adds devices, never removes. No "set devices to exactly this list" operation.

**Effect:** Once a device leaks into a folder via cross-team sharing, there is no code path to remove it during normal operation. The device list can only grow.

**Paradox with cleanup:** Normal operation can only ADD devices. Cleanup can only REMOVE THE ENTIRE FOLDER. There is no "remove one team's devices from the folder" operation.

### BP-3: Team Cleanup Has No Cross-Team Folder Guard

**Location:** `api/services/sync_folders.py:355-426`

**Behavior:** `cleanup_syncthing_for_team()` removes folders matching `(member_tag in team_members AND suffix in team_projects)`. No check for whether other teams share the same (member, project) pair.

**Effect:** Leaving T2 (which shares P2) removes `karma-out--alice.laptop--P2_suffix` — the same folder T4 uses for M3's P2 sessions. T4's P2 sync from M3 breaks.

### BP-4: Member Cleanup Removes Cross-Team Inboxes

**Location:** `api/services/sync_folders.py:429-487`

**Behavior:** When removing a member's inbox folder (their outbox), `remove_folder` is called without checking if the member is in another team sharing the same project.

**Effect:** Removing M3 from T2 would remove `karma-out--alice.laptop--P2_suffix` entirely, breaking T4's inbox for M3's P2 sessions.

### BP-5: Introducer Flag Is Global, Permanent, and Re-Enforced

**Location:** Join flow in `sync_teams.py`, `ensure_leader_introducers()` in `sync_reconciliation.py`

**Behavior:** The introducer flag is:
1. Set at Syncthing level (not team-scoped)
2. Never disabled after handshake
3. Re-enforced on every `GET /sync/pending-devices` poll

**Effect:** A device marked as introducer for Team A will propagate ALL devices/folders (including from Teams B, C, D) to any device that trusts it. There's no way to limit the scope.

### BP-6: Reconciliation Auto-Creates Phantom Teams

**Location:** `api/services/sync_reconciliation.py:reconcile_pending_handshakes()`

**Behavior:** When a handshake folder (`karma-join--X--TeamY`) arrives from a configured device for a team that doesn't exist locally, the code creates that team.

**Effect:** Introduced handshake folders from other teams cause phantom team memberships. The device becomes a member of teams it was never invited to.

### BP-7: No Device Removal From Folders (Only Folder Removal)

**Location:** `api/services/sync_folders.py` — `ensure_outbox_folder`, `ensure_inbox_folders`

**Behavior:** These functions only ADD devices. `remove_device_from_folder` exists in proxy but is only called in `cleanup_syncthing_for_member` for the caller's OWN outbox folders.

**Effect:** When a member leaves a team, there is no operation to "remove just that team's claim" on a shared folder. The choices are: leave all leaked devices in place, or delete the entire folder.

### BP-8: find_team_for_folder Returns First Match

**Location:** `api/services/sync_folders.py:find_team_for_folder()`

**Behavior:** Returns the first team that matches a folder by suffix. When the same project suffix exists in multiple teams, the result is ambiguous.

**Effect:** Pending folder UI may attribute a folder to the wrong team. Rejection/acceptance decisions may be scoped to the wrong team.

---

## 6. Syncthing Primitive Behaviors

These are Syncthing (the underlying tool) behaviors that constrain the design:

### 6.1 Introducer Mechanism

When device A marks device B as "introducer":
- A auto-accepts ALL devices from B's cluster config
- A auto-accepts ALL folders that B shares with devices B introduces to A
- This is ALL-or-nothing — cannot scope to specific folders or teams
- The flag is per-device, global (not per-folder)

### 6.2 Folder IDs Are Global

- A folder ID is unique across the entire Syncthing instance
- Two folders cannot share the same ID (even if different paths)
- Folder IDs are the joining key between sender and receiver

### 6.3 Device Pairing Is Global

- Adding a device makes it available for ALL folders
- There is no "add device for folder X only"
- Device trust is binary: paired or not paired

### 6.4 No Folder Namespacing

- Syncthing has no concept of groups, teams, or namespaces
- All folders exist in a flat list
- The `karma-` prefix convention is the only isolation mechanism

### 6.5 Folder Type Semantics

- `sendonly`: Can only push changes, ignores remote changes
- `receiveonly`: Can only accept changes, local changes reverted
- `sendreceive`: Bidirectional sync (used for metadata folders)

---

## 7. Reconciliation Loop Observations

### 7.1 Two Independent Reconciliation Paths

```
Path A: API-driven (GET /sync/pending-devices)
  1. ensure_leader_introducers()     ← re-enforces introducer flags
  2. reconcile_introduced_devices()  ← discovers peers from introducer
  3. reconcile_pending_handshakes()  ← processes team handshakes
  4. auto_accept_pending_peers()     ← accepts pending devices

Path B: Timer-driven (every 60 seconds)
  1. reconcile_all_teams_metadata()  ← reads metadata folder
     - Discovers new members from members/*.json
     - Detects removal from removals/*.json
     - Auto-leaves on removal detection
```

**Observation:** These paths are independent. Path A can add members that Path B then removes (if a removal signal exists). Path B can auto-leave a team that Path A tries to add members to. No mutual exclusion between them.

### 7.2 Reconciliation Ordering Dependency

Path A runs phases sequentially within a single API call. But across multiple devices, the ordering is non-deterministic:

```
Device X:  [join T3] → [create handshake] → [create metadata]
Device Y:  [poll pending] → [see handshake] → [auto-accept] → [share folders]
Device X:  [poll pending] → [see pending folders] → [accept]
```

**Observation:** There is no global coordination. Each device runs reconciliation independently based on its local state + what Syncthing has synced so far.

### 7.3 Removal Detection Latency

```
Creator writes removal signal → Syncthing syncs to removed device (seconds to minutes)
→ Metadata timer fires (up to 60 seconds) → is_removed() check → auto_leave()
```

**Observation:** Worst case: 60s timer + Syncthing sync delay. During this window, the removed device may still create new folders or accept pending offers.

---

## 8. Race Conditions & Timing

### RC-1: Auto-Leave vs Reinvite Race

**Scenario:**
1. Removal signal detected → auto_leave begins
2. Simultaneously, another device sends a new handshake folder
3. reconcile_pending_handshakes recreates the team
4. auto_leave deletes the team
5. Handshake reconciliation fails (team gone)

**No mutual exclusion exists** between the removal path and the invitation path.

### RC-2: Partial Cleanup on Auto-Leave

**Observed in:** `sync_metadata_reconciler.py:_auto_leave_team()`

```python
try:
    cleanup_syncthing_for_team(...)
    syncthing_cleaned = True
except Exception:
    logger.warning(...)  # Continues anyway

delete_team(conn, team_name)  # Runs even if cleanup failed
```

**Observation:** If Syncthing cleanup fails but DB delete succeeds → orphaned Syncthing folders persist. No recovery mechanism.

### RC-3: Metadata Sync Lag on Join

**Scenario:** Device joins team. Metadata folder is created but hasn't synced yet. Other members' reconciliation reads an empty/partial metadata folder.

**Observation:** `reconcile_metadata_folder()` handles this gracefully — it reads what's available and catches up on next cycle. But `validate_removal_authority()` has a DB fallback for when `team.json` hasn't synced yet.

### RC-4: Concurrent ensure_outbox_folder Calls

**Scenario:** Two async handlers call `ensure_outbox_folder` for the same folder ID simultaneously.

**Observation:** Both call `update_folder_devices` (additive) → both may succeed but the second call adds no new devices. Not a correctness issue due to additive semantics, but the "try update, fall back to create" pattern could race: both fail update, both try create, one fails.

### RC-5: Watcher Thread + API Thread SQLite Access

**Observation:** `MetadataReconciliationTimer` runs in a daemon thread, using `get_writer_db()`. API handlers also use writer connections. SQLite's WAL mode allows concurrent reads but only one writer. If both paths try to write simultaneously, one blocks.

The code uses `get_writer_db()` which returns a single connection — potential for connection contention under load.

---

## 9. Edge Cases

### EC-1: member_tag Collision

**Scenario:** Two different users choose the same `user_id` AND have the same hostname.

**Observation:** `member_tag = user_id.machine_tag`. If user_id="jay" and both machines are named "macbook-pro", both get `jay.macbook-pro`. The `user_id` validation (`^[a-zA-Z0-9_-]+$`) enforces format but not uniqueness.

**Impact:** Identical folder IDs, session data mixed between users, removal signals target both.

### EC-2: Device ID Changes (Syncthing Reinstall)

**Scenario:** User reinstalls Syncthing → new device ID, same machine.

**Observation:** The old device ID remains in all teams' member lists and folder device lists. The new device ID is unknown. No migration path exists — user must re-join all teams.

**Stale state:** Old device entries persist in `sync_members`, `sync_removed_members`, metadata folder member files, and Syncthing folder device lists.

### EC-3: git_identity Change

**Scenario:** User changes the git remote URL of a project after folders are created.

**Observation:** The folder suffix is computed from `git_identity` at share time and stored in `sync_team_projects.git_identity`. If the remote changes:
- Existing folders use old suffix → continue working
- New `share project` calls compute new suffix → create NEW folder
- Old and new folders coexist → session duplication

No migration or update path for git_identity changes.

### EC-4: Project Shared With No Sessions

**Scenario:** Leader shares a project that has 0 local sessions.

**Observation:** Works correctly — outbox folder is created but empty. Syncthing handles empty folders fine. Sessions will sync when they appear.

### EC-5: Same Project, Different Local Paths

**Scenario:** M1 has `~/GitHub/repo` and M3 has `~/code/repo`. Same git_identity.

**Observation:** `_compute_proj_suffix()` uses `git_identity` when available → same suffix → same folder ID. Cross-machine path differences are handled by the project mapping system in `remote_sessions.py` using git_identity matching.

### EC-6: Folder Rejection + Re-Share

**Scenario:** M1 rejects `karma-out--alice.laptop--P2` via `POST /sync/pending/reject`. Later, M3 shares P2 in a new team with M1.

**Observation:** `sync_rejected_folders` table persists rejection by folder_id. Since the folder ID is the same (no team scope), the rejection applies across teams. M1 would NOT receive M3's P2 sessions in the new team either.

`unreject_folder()` is called on explicit accept, but automatic re-sharing via `auto_share_folders` does not check/clear rejections.

### EC-7: Folder Count Scalability

**Formula per device:**
```
For each team T that device is in:
  1 metadata folder (karma-meta--T)
  1 handshake folder (karma-join--self--T)
  For each project P in T:
    1 outbox (karma-out--self--P)           ← shared across teams (collision)
    N-1 inboxes (karma-out--peer--P)        ← one per peer, shared across teams

Total unique folders ≈ T_count × (2) + unique_projects × (1 + unique_peers_for_project)
```

For this setup (M1 in 4 teams, 3 projects, 5 peers):
```
M1: 4×2 (meta+handshake) + 3 (outboxes) + 5×3 (inboxes) = 8 + 3 + 15 = 26 folders
```

With 10 teams × 5 projects × 20 members: `10×2 + 5 + 19×5 = 20 + 5 + 95 = 120 folders`

**Observation:** Syncthing has been tested with hundreds of folders, but performance degrades with many small folders due to per-folder file watchers and status tracking.

---

## 10. Filesystem & Data Flow Observations

### 10.1 Session Packaging (Sender Side)

**File:** `cli/karma/packager.py`

```
Local sessions:     ~/.claude/projects/{encoded}/{uuid}.jsonl
Staging:            /tmp/sync-staging/{encoded}/sessions/{uuid}.jsonl
Outbox:             ~/.syncthing/karma-out--{member_tag}--{suffix}/sessions/{uuid}.jsonl
                    Also: manifest.json, titles.json, todos/, debug/, plans/
```

**Observation:** The packager copies sessions to ONE outbox path per project. With team-scoped folder IDs, it would need to copy to N outbox paths (one per team sharing the project).

### 10.2 Session Discovery (Receiver Side)

**File:** `api/services/remote_sessions.py`

```
Inbox:              ~/.claude_karma/remote-sessions/{user_dir}/{encoded}/sessions/{uuid}.jsonl
```

Scans inbox directories, reads manifest.json for identity, resolves local project via git_identity mapping.

**Observation on dedup:** No active deduplication. Relies on unique UUIDs per session. If the same session appeared in two different inbox paths (possible with cross-team folder sharing), both would be discovered. The API layer does not dedup by (uuid, remote_user_id).

### 10.3 Manifest Contains Identity

Each outbox contains `manifest.json` with:
```json
{
  "user_id": "jayant",
  "machine_id": "mac-mini",
  "member_tag": "jayant.mac-mini",
  "device_id": "...",
  "project_path": "...",
  "git_identity": "jayantdevkar/claude-karma",
  "sessions": [{"uuid": "...", "mtime": "...", "size_bytes": ...}]
}
```

**Observation:** `device_id` in manifest enables authoritative identity resolution. If the same physical outbox serves multiple teams, the manifest is the same — no team-specific metadata.

---

## 11. Scalability Observations

### 11.1 The "Additive-Only + Delete-All" Paradox

The system has two modes for device lists:
1. **During operation:** Devices accumulate (additive only, no removal)
2. **During cleanup:** Entire folder removed (all or nothing)

There is no "surgical removal" of specific devices from a folder based on team membership. This creates a fundamental impedance mismatch:
- **Teams are dynamic** (members join/leave frequently)
- **Folder device lists are append-only** (until folder deletion)
- **Folder deletion is cross-team destructive** (affects all teams sharing the folder)

### 11.2 The "Introducer Scope" Problem

Syncthing's introducer is per-device, not per-team. In a multi-team setup:
- Every join adds a new introducer trust
- Introducers propagate ALL their state (not just the team's)
- The more teams a device is in, the more it leaks across boundaries

**Growth pattern:** A device in N teams trusts up to N introducers, each potentially bridging their teams' device lists into the current device.

### 11.3 Session Data Is Inherently Per-Project

Sessions are written to `~/.claude/projects/{encoded}/{uuid}.jsonl`. There is no team concept at the session level. A session belongs to a project, not a team.

**Implication:** The "who gets my sessions" decision should be per-project (union of teams), not per-team (requiring duplication).

### 11.4 Device List Is the Only Access Control

Syncthing has no ACL system. The folder's device list IS the access control. Any device in the list receives the folder's content. The only way to revoke access is to remove the device from the list (or delete the folder).

---

## 12. Additional Breakpoints (Investigated)

### BP-9: member_tag Collision — No Validation

**Location:** `cli/karma/config.py:20-32`, `api/routers/sync_devices.py:64-75`

**Observation:** `_sanitize_machine_tag()` sanitizes hostname to `[a-z0-9-]+` but provides NO collision detection. No runtime check exists at pair/accept time. Two different users on machines with the same hostname choosing the same `user_id` produce identical `member_tag` values.

**Example:** User "alice" on two different physical machines both named "macbook" → both produce `alice.macbook` → identical folder IDs, session data mixed, removal signals target both.

**Missing code:**
```python
# Nothing like this exists in the accept/join flow:
existing = conn.execute(
    "SELECT device_id FROM sync_members WHERE member_tag = ? AND device_id != ?",
    (member_tag, new_device_id)
).fetchone()
if existing:
    raise HTTPException(409, "member_tag collision")
```

### BP-10: Device ID Reuse After Syncthing Reinstall

**Location:** `api/db/sync_queries.py:110-143`

**Observation:** `upsert_member()` has deletion logic for same-name, different-device_id:
```python
conn.execute(
    "DELETE FROM sync_members WHERE team_name = ? AND name = ? AND device_id != ?",
    (team_name, name, device_id),
)
```

This works IF the name stays the same. But old entries with the old device_id persist in:
- Syncthing folder device lists (stale device still listed)
- Metadata folder member files (old device_id in JSON)
- `sync_removed_members` table (old device_id blocks re-join)

No automatic cleanup of orphaned device entries when Syncthing is reinstalled. User must re-join all teams manually.

### BP-11: No Per-Folder Locking for Concurrent Operations

**Location:** `api/services/sync_folders.py:69-87`

**Observation:** `ensure_outbox_folder()` uses try-update, fallback-to-add pattern with no locking:
```python
try:
    await run_sync(proxy.update_folder_devices, folder_id, device_ids)
except ValueError:
    await run_sync(proxy.add_folder, folder_id, path, all_ids, mode)
```

Two concurrent async handlers calling `ensure_outbox_folder` for the same folder_id can both fail the update, both try to create, one fails. Not a data corruption risk (Syncthing rejects duplicate folder creation), but can cause error logs and missed folder setup.

No `asyncio.Lock()` per folder_id exists anywhere in the codebase.

### BP-12: Folder Acceptance Before Metadata Sync

**Location:** `api/services/sync_folders.py:300-312` (`auto_share_folders`)

**Observation:** `auto_share_folders()` reads `member_subscriptions` from metadata folder:
```python
for state in read_all_member_states(meta_dir):
    device = state.get("device_id", "")
    subs = state.get("subscriptions", {})
    if device:
        member_subscriptions[device] = subs
```

If metadata folder hasn't synced yet (common during initial join), `read_all_member_states()` returns empty list → subscriptions dict is empty → all projects are shared regardless of member's opt-out preferences.

**Ordering dependency:** The system assumes metadata folder syncs before project folders are offered. No explicit check or wait exists.

### BP-13: git_identity Change Creates Orphaned Folders

**Location:** `api/services/sync_identity.py:171-175`

**Observation:** Folder suffix is computed from `git_identity` at share time:
```python
def _compute_proj_suffix(git_identity, path, encoded):
    if git_identity:
        return git_identity.replace("/", "-")
```

If `git_identity` changes (repo transfer, remote rename):
1. Old folders use old suffix → continue working but orphaned
2. New share computes new suffix → creates NEW folder with new ID
3. Both old and new folders coexist → session duplication on receiver
4. No migration, detection, or cleanup path exists for this scenario

### BP-14: sync_rejected_folders Not Team-Scoped

**Location:** `api/db/sync_queries.py:reject_folder()`

**Observation:** Rejection is stored by `folder_id` (which lacks team scope). Rejecting `karma-out--alice.laptop--P2_suffix` in T2 context also rejects it for T4, since both teams produce the identical folder_id.

`auto_share_folders()` does not check/clear rejections. Only explicit `POST /sync/pending/accept/{folder_id}` calls `unreject_folder()`.

### BP-15: No Folder Count Safeguard

**Observation:** No validation exists for total folder count per Syncthing instance. Formula:
```
Folders per device ≈ T×2 + P×(M×T - 1)
```

At scale (10 teams, 20 projects, 10 members): ~2000 folders. Syncthing performance degrades above ~500-1000 folders (file watcher overhead, REST API response times, inode limits).

No rate limiting, no warning, no hard cap in the codebase.

### BP-16: Partial Cleanup on Auto-Leave

**Location:** `api/services/sync_metadata_reconciler.py:169-214`

**Observation:** `_auto_leave_team()` continues to `delete_team()` even if Syncthing cleanup fails:
```python
try:
    cleanup_syncthing_for_team(...)
    syncthing_cleaned = True
except Exception:
    logger.warning(...)  # CONTINUES ANYWAY

delete_team(conn, team_name)  # Runs even if cleanup failed
```

Result: Orphaned Syncthing folders persist. No recovery mechanism. Next reconciliation cycle won't find the team (deleted from DB) so won't retry cleanup.

### BP-17: Auto-Leave vs Reinvite Race

**Location:** `api/services/sync_metadata_reconciler.py:151-166`

**Observation:** No mutual exclusion between:
1. Timer-driven `_auto_leave_team()` (detects removal signal)
2. API-driven `reconcile_pending_handshakes()` (processes new join)

If a device is removed and simultaneously re-invited:
- Timer detects removal → starts cleanup
- API processes new handshake → creates team + member
- Timer finishes → deletes team
- Result: Re-invite silently lost

### BP-18: remove_device_from_folder Exists But Underused

**Location:** `api/services/syncthing_proxy.py:231-272`

**Observation:** `remove_device_from_folder(folder_id, device_id)` exists and works correctly — it removes a single device from a folder's device list without deleting the folder. Uses `PUT /rest/config/folders/{id}` with filtered device list.

However, it is ONLY used in `cleanup_syncthing_for_member()` for the caller's OWN outbox folders (line 455-456). It is NEVER used in:
- `cleanup_syncthing_for_team()` — which removes entire folders instead
- `ensure_outbox_folder()` / `ensure_inbox_folders()` — which only add devices
- Any cross-team device removal path

This primitive could enable "surgical" device removal if cleanup logic were redesigned.

---

## 13. Observations That Work Correctly

For completeness — these areas were investigated and found to be sound:

### OK-1: Atomic Metadata Writes
`sync_metadata.py` uses `tempfile.mkstemp()` + `rename()` for all JSON writes. POSIX atomic. No partial file corruption risk. Each device writes its own file (`members/{member_tag}.json`), so no cross-device write conflicts.

### OK-2: SQLite WAL Mode
Writer uses WAL mode with `busy_timeout=5000`. Single writer connection via `_writer_lock`. Read connections are separate. Concurrent reads don't block writes. Solid for the single-machine-per-device model.

### OK-3: Same-User Multi-Device Differentiation
`member_tag = user_id.machine_tag` correctly differentiates M1 (`jayant.macbook`) from M2 (`jayant.mac-mini`). Folder IDs, metadata files, and DB entries are distinct. The v2 fix for this works.

### OK-4: Handshake and Metadata Folder IDs Include Team
`karma-join--{member_tag}--{team_name}` and `karma-meta--{team_name}` both include team. These never collide across teams. Only outbox/inbox (`karma-out--`) lacks team scope.

### OK-5: Device Cross-Team Check on Removal
`cleanup_syncthing_for_team()` and `cleanup_syncthing_for_member()` both check `SELECT COUNT(*) FROM sync_members WHERE device_id = ? AND team_name != ?` before removing a Syncthing device. Devices shared across teams are preserved. (Only folder cleanup lacks this check.)

### OK-6: Event Loop Handling in Daemon Thread
`_auto_leave_team()` correctly detects it's running in a daemon thread (not async context), creates a new event loop, and runs cleanup. No event loop reuse bugs.

### OK-7: Removal Authority
Creator-only removal enforced via `validate_removal_authority()` which checks `team.json["created_by"]` with DB fallback for when metadata hasn't synced yet. Sound design.

---

## 14. Open Questions for v3

### Design Questions

1. **Should the outbox be team-scoped or project-scoped?**
   - Team-scoped: `karma-out--{member}--{team}--{suffix}` — clean isolation, but session duplication
   - Project-scoped: `karma-out--{member}--{suffix}` (current) — no duplication, but requires union device list management

2. **Should the introducer mechanism be used at all?**
   - Alternative: explicit mesh via metadata folder (each device reads member list, pairs explicitly)
   - Tradeoff: More API calls vs. guaranteed team isolation

3. **How should cross-team folder device lists be computed?**
   - If project-scoped: union of all teams' members for that project
   - If team-scoped: simple (just that team's members)

4. **How should cleanup handle shared folders?**
   - Reference counting: "is this folder needed by another team?"
   - Device subtraction: "remove just this team's devices from the folder"
   - Needs `set_folder_devices` (replace) not just `update_folder_devices` (add)

5. **How should removal propagate across overlapping teams?**
   - Removing M3 from T4 should not affect M3's T2 membership
   - But if the outbox folder is shared, removing M3's inbox for T4 removes it for T2 too

6. **Should there be a "channel" concept separate from teams?**
   - Channel = (member, project) — the physical sync unit
   - Team = access control layer — determines which channels a member subscribes to

### Implementation Questions

7. **Does Syncthing support `set_folder_devices` (replace entire list)?**
   - The REST API supports `PUT /rest/config/folders/{id}` with full config
   - The proxy has `update_folder_devices` (additive) and `remove_device_from_folder` (single device)
   - A "set exactly these devices" operation would need to diff and remove/add

8. **What is the maximum practical folder count per Syncthing instance?**
   - Need benchmarking with 50-200 folders
   - File watcher overhead per folder is the main concern

9. **How to migrate v2 folder IDs to v3?**
   - Rename folders? Syncthing may not support rename
   - Create new + delete old? Requires re-sync of all data
   - Side-by-side? Both formats active during migration window

10. **How to handle the introducer-to-explicit-mesh transition?**
    - Existing introducer flags need to be disabled
    - Devices introduced via old mechanism need explicit pairing
    - One-time migration on startup?

---

---

## Appendix A: Key Source Files

| File | Purpose |
|------|---------|
| `api/services/folder_id.py` | Folder ID build/parse. `build_outbox_id`, `parse_member_tag` |
| `api/services/sync_folders.py` | Folder CRUD, cleanup, auto_share_folders |
| `api/services/sync_reconciliation.py` | 4-phase reconciliation (introduced, handshakes, auto-accept, introducer) |
| `api/services/sync_metadata.py` | Metadata folder read/write (member states, removal signals, team info) |
| `api/services/sync_metadata_writer.py` | Convenience wrapper for updating own state in metadata |
| `api/services/sync_metadata_reconciler.py` | Timer-driven metadata reconciliation, auto-leave |
| `api/services/sync_policy.py` | Policy evaluation (auto_accept, sync_direction) |
| `api/services/sync_identity.py` | Identity loading, validation, singletons |
| `api/services/syncthing_proxy.py` | Syncthing REST API wrapper |
| `api/services/remote_sessions.py` | Remote session discovery and indexing |
| `api/services/watcher_manager.py` | Session watcher + metadata reconciliation timer |
| `api/db/sync_queries.py` | All sync DB CRUD operations |
| `api/db/schema.py` | SQLite schema v17 |
| `api/routers/sync_teams.py` | Team lifecycle, join, invite, settings |
| `api/routers/sync_members.py` | Member add/remove, profiles |
| `api/routers/sync_devices.py` | Device pairing, pending device acceptance |
| `api/routers/sync_projects.py` | Project sharing, status |
| `api/routers/sync_pending.py` | Pending folder accept/reject |
| `cli/karma/packager.py` | Session packaging into outbox |
| `cli/karma/config.py` | SyncConfig with member_tag derivation |

## Appendix B: Database Schema (v17)

```
sync_teams(name PK, backend, join_code, sync_session_limit, created_at)
sync_members(team_name+device_id PK, name, machine_id, machine_tag, member_tag, added_at)
  FK: team_name → sync_teams ON DELETE CASCADE
sync_team_projects(team_name+project_encoded_name PK, path, git_identity, added_at)
  FK: team_name → sync_teams ON DELETE CASCADE
  FK: project_encoded_name → projects
sync_events(id PK, event_type, team_name, member_name, project_encoded_name, session_uuid, detail, created_at)
  FK: team_name → sync_teams ON DELETE SET NULL
sync_settings(scope+setting_key PK, value, updated_at)
  NO FK (orphaned on team delete, explicit cleanup exists)
sync_removed_members(team_name+device_id PK, removed_at)
  FK: team_name → sync_teams ON DELETE CASCADE
sync_rejected_folders(folder_id PK, team_name, rejected_at)
  NO FK
```

## Appendix C: Folder ID Formats

```
Outbox/Inbox:  karma-out--{member_tag}--{suffix}
Handshake:     karma-join--{member_tag}--{team_name}
Metadata:      karma-meta--{team_name}
```

- `member_tag` = `{user_id}.{machine_tag}` (split on first dot)
- `suffix` = git_identity with `/` → `-`, or last path component, or encoded name
- Delimiter `--` is unambiguous (member_tag, suffix, team_name cannot contain `--`)
