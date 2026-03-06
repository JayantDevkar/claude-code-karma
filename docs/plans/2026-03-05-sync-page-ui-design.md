# Sync Page UI/UX Design

**Date:** 2026-03-05
**Status:** Approved
**Author:** Jayant Devkar + Claude
**Depends on:** [Syncthing Session Sync Design](./2026-03-03-syncthing-session-sync-design.md), [IPFS Sync UI/UX Design](./2026-03-03-ipfs-sync-ui-ux-design.md)

## Problem

Users who download Claude Karma and open the `/team` page have zero guidance on what P2P sync means, why they'd want it, how to install prerequisites, or how to monitor it once running. The existing Syncthing and IPFS designs are CLI-first — the dashboard should be the single pane of glass so users never touch Syncthing's web UI or terminal.

## MVP Persona

A solo user with 2+ machines running Claude Code. They want to unify their sessions across machines without learning P2P internals.

**Not in MVP scope:** Team/freelancer management, IPFS backend (UI-ready but greyed out).

## Design Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Primary persona | Solo user, multiple machines | Simplest valuable scenario |
| Dashboard role | Single pane of glass | Users never touch Syncthing UI or terminal |
| CLI execution | Backend proxies CLI commands | UI buttons trigger `karma` CLI via API |
| Project selection | Toggle per-project with "select all" | Granular control, easy bulk action |
| Navigation | New `/sync` page, keep `/team` separate | Clear separation: infrastructure vs people |
| Page structure | Tabbed single page | Organized by concern, familiar pattern |
| Detail level | Full Syncthing dashboard replacement | Users never need localhost:8384 |
| Visual hierarchy | Scan > Spot > Drill (progressive disclosure) | Don't overwhelm, surface problems first |
| Data refresh | Poll 10s + SSE for activity stream | Balance between freshness and load |

## Route & Navigation

### Route: `/sync`

**Nav position:** Between "Archived" and "Team" in the header — grouping infrastructure/collaboration items at the end.

**Page header:** "Sync" with `RefreshCw` (lucide) icon, purple accent. Breadcrumb: Dashboard > Sync.

### Tab Bar

Horizontal tabs below the header:

1. **Setup** — green checkmark badge once configured
2. **Devices** — count badge (e.g., "2")
3. **Projects** — count badge of syncing projects
4. **Activity** — orange dot when transfers are active

**Default tab logic:**
- Not configured: Setup tab auto-selected
- Configured: Devices tab auto-selected
- Active transfer in progress: Activity tab gets attention dot

**URL state:** Tab persisted in URL params (`/sync?tab=devices`) for shareable links.

**Polling:** `/sync/status` every 10 seconds. "Last updated: 5s ago" timestamp in header. Manual refresh button.

## Tab 1: Setup

Three progressive states: Not Installed > Not Initialized > Configured.

### State 1: Syncthing Not Detected

```
+-------------------------------------------------------------+
|                                                             |
|  +--- CHOOSE SYNC BACKEND --------------------------------+|
|  |                                                         ||
|  |  +---------------------+  +---------------------+      ||
|  |  |  * Syncthing        |  |  o IPFS             |      ||
|  |  |                     |  |                     |      ||
|  |  |  Real-time auto     |  |  On-demand sync,    |      ||
|  |  |  sync between your  |  |  content-addressed, |      ||
|  |  |  machines. Simple   |  |  tamper-evident.     |      ||
|  |  |  setup, encrypted.  |  |                     |      ||
|  |  |                     |  |  Best for: larger   |      ||
|  |  |  Best for: syncing  |  |  teams, audit trails|      ||
|  |  |  your own machines  |  |  [Coming soon]      |      ||
|  |  +---------------------+  +---------------------+      ||
|  +---------------------------------------------------------+|
|                                                             |
|  +--- INSTALL SYNCTHING ----------------------------------+|
|  |                                                         ||
|  |  * Not detected on this machine                         ||
|  |                                                         ||
|  |  macOS:     brew install syncthing                      ||
|  |  Linux:     sudo apt install syncthing                  ||
|  |  Windows:   scoop install syncthing                     ||
|  |                                                         ||
|  |  Then start it:  syncthing serve --no-browser           ||
|  |                                                         ||
|  |           [ Check Again ]                               ||
|  +---------------------------------------------------------+|
+-------------------------------------------------------------+
```

- Backend calls Syncthing REST API (`localhost:8384/rest/system/status`) to detect
- "Check Again" button re-polls
- IPFS card greyed out with "Coming soon"
- OS auto-detected, matching install command highlighted

### State 2: Syncthing Detected, Not Initialized

```
+-------------------------------------------------------------+
|  +--- SYNCTHING DETECTED ---------------------------------+|
|  |  Syncthing v1.27.0 running on port 8384                ||
|  +---------------------------------------------------------+|
|                                                             |
|  +--- INITIALIZE -----------------------------------------+|
|  |                                                         ||
|  |  Machine Name   [ alice-macbook-pro     ]               ||
|  |                 (auto-filled from hostname)              ||
|  |                                                         ||
|  |  Your Device ID (read-only, from Syncthing):            ||
|  |  +--------------------------------------------------+   ||
|  |  | XXXXXXX-XXXXXXX-XXXXXXX-XXXXXXX-XXXXXXX-XXXXXXX |   ||
|  |  +--------------------------------------------------+   ||
|  |                            [ Copy ]                     ||
|  |                                                         ||
|  |  Share this Device ID with your other machine,          ||
|  |  then paste theirs below.                               ||
|  |                                                         ||
|  |            [ Initialize ]                               ||
|  +---------------------------------------------------------+|
+-------------------------------------------------------------+
```

- Backend calls `karma init --backend syncthing` on Initialize
- Machine name editable (defaults to hostname)
- Device ID fetched from Syncthing API, displayed read-only with copy button

### State 3: Initialized — Pair Devices

```
+-------------------------------------------------------------+
|  +--- THIS MACHINE ---------------------------------------+|
|  |  alice-macbook-pro                                      ||
|  |  Device ID: XXXXXXX-...  [Copy]                        ||
|  |  Syncthing: v1.27.0  Running                           ||
|  +---------------------------------------------------------+|
|                                                             |
|  +--- PAIRED DEVICES -------------------------------------+|
|  |                                                         ||
|  |  alice-mac-mini    Connected            [Remove]        ||
|  |  YYYYYYY-...       Last seen: 2m ago                    ||
|  |                                                         ||
|  |  - - - - - - - - - - - - - - - - - - - - - - - - - -   ||
|  |                                                         ||
|  |  + Add Device                                           ||
|  |  Paste Device ID: [                          ]          ||
|  |  Device Name:     [                          ]          ||
|  |                              [ Pair Device ]            ||
|  +---------------------------------------------------------+|
|                                                             |
|  +--- NETWORK CONFIGURATION ------------------------------+|
|  |  * Local network (devices on same WiFi/LAN)             ||
|  |  o Remote (via Syncthing relays, encrypted)             ||
|  |  o VPN (Tailscale/WireGuard, direct connection)         ||
|  |                                                         ||
|  |  [x] Disable global announce (privacy)                  ||
|  |  [x] Disable relays (direct connections only)           ||
|  +---------------------------------------------------------+|
+-------------------------------------------------------------+
```

- "Add Device" triggers backend `karma team add <name> <device-id>`
- Connection status polled from Syncthing `/rest/system/connections`
- Network mode maps to Syncthing's relay/announce options
- Remove button with confirmation dialog

## Tab 2: Devices

Daily monitoring view. All paired machines with full Syncthing detail.

### Layout

Each device is a card. "This Machine" card first, then paired devices.

### Per-Device Card

```
+-------------------------------------------------------------+
|  alice-mac-mini                                    [...]    |
|  Connected  |  Device ID: YYYYYYY-...  |  Last seen: now    |
|                                                             |
|  +--- CONNECTION -----------------------------------------+|
|  |  Address: tcp://192.168.1.42:22000                      ||
|  |  Type: Direct (LAN)                                     ||
|  |  Encryption: TLS 1.3                                    ||
|  |  Connected since: Mar 3, 2:15 PM                        ||
|  +---------------------------------------------------------+|
|                                                             |
|  +--- TRANSFER -------------------------------------------+|
|  |  Up: 0 B/s        Down: 45 KB/s                        ||
|  |  Total sent: 420 MB    Total received: 380 MB           ||
|  |                                                         ||
|  |  In Sync  ========================--  92%               ||
|  |  Files: 847/920 synced                                  ||
|  +---------------------------------------------------------+|
|                                                             |
|  +--- SHARED FOLDERS -------------------------------------+|
|  |  karma-out-alice   remote-sessions/alice/               ||
|  |    Up to date      284 files, 120 MB                    ||
|  |                                                         ||
|  |  karma-in-alice    remote-sessions/alice-mini/          ||
|  |    Syncing...      12 files remaining                   ||
|  |    ============--------  62%  ~30s left                 ||
|  +---------------------------------------------------------+|
+-------------------------------------------------------------+
```

### Status Indicators

| State | Display |
|-------|---------|
| Green "Connected" | Active TLS connection |
| Green "Online" | This machine (always) |
| Blue "Syncing" | Active file transfer |
| Grey "Disconnected" | No connection |
| Orange "Stale" | Disconnected >24h, with help text |

### [...] Menu Per Device

- Pause syncing
- Copy Device ID
- Remove device (with confirmation)

### Data Sources

| Syncthing API | What it provides |
|---------------|-----------------|
| `/rest/system/connections` | Connection details, bandwidth |
| `/rest/db/completion` | Per-folder sync percentage |
| `/rest/stats/device` | Last seen, total transfer |
| `/rest/system/status` | Local device info, uptime |

## Tab 3: Projects

Toggle which projects sync. Progressive disclosure: Scan > Spot > Drill.

### Default View (Collapsed Rows)

```
+--------------------------------------------------------------+
|  PROJECTS                          [ Select All ] [Refresh]  |
|                                                              |
|  +----------------------------------------------------------+|
|  |  *  claude-karma           In sync       42 sessions     ||
|  |     Last sync: 5m ago      2 machines                    ||
|  |----------------------------------------------------------||
|  |  *  side-project           ! 3 pending    8 sessions     ||
|  |     Last sync: 2d ago      1 machine     [Sync Now]      ||
|  |----------------------------------------------------------||
|  |  o  acme-app                Not syncing  12 sessions     ||
|  |                                        [Enable Sync]     ||
|  |----------------------------------------------------------||
|  |  o  personal-site           Not syncing   4 sessions     ||
|  |                                        [Enable Sync]     ||
|  +----------------------------------------------------------+|
|                                                              |
|  ! 1 conflict across projects              [View Conflicts]  |
+--------------------------------------------------------------+
```

**What you see at a glance:**
- Each project is one row: toggle dot, name, status badge, session count
- Secondary line: last sync time, machine count
- Action buttons only on rows that need them
- Conflicts summarized as a single banner at the bottom

### Expanded Project (Click Row) — Level 1

```
|  *  claude-karma           In sync       42 sessions  |
|     Last sync: 5m ago      2 machines                  |
|                                                        |
|     +--- Machines ----+                                |
|     |  alice-macbook-pro (this)    24 sessions         |
|     |  alice-mac-mini              18 sessions         |
|     +-----------------+                                |
|                                                        |
|     > Files (48)          > Sync History               |
```

Machine breakdown as a mini table. "Files" and "Sync History" are chevron links to level 2.

### Files Expanded — Level 2

```
|     v Files (48)                                        |
|     +---------------------------------------------------+
|     |  Syncing now (2)                                   |
|     |  --------------------------------------------------|
|     |  ghi789.jsonl        Syncing  72%  89 KB   ~5s    |
|     |  ghi789/subagents/   Pending        12 KB         |
|     |                                                    |
|     |  Recently synced (showing 5 of 46)                 |
|     |  --------------------------------------------------|
|     |  abc123.jsonl        Synced   45 KB   5m ago      |
|     |  def456.jsonl        Synced   120 KB  5m ago      |
|     |  def456/tool-results Synced   8 KB    5m ago      |
|     |  abc123-task.json    Synced   2 KB    5m ago      |
|     |  ...                                               |
|     |                         [ Show all 46 ]            |
|     +----------------------------------------------------+
```

- Active transfers float to top with progress bars
- Completed files grouped and capped at 5, expandable
- File sizes right-aligned, muted color

### Hierarchy Summary

| Level | What's shown | Visible by default |
|-------|-------------|-------------------|
| L0 | Project row: name, status badge, counts, action button | Always |
| L1 | Machine breakdown (mini table) | On row click |
| L2 | Files list (active first, then recent) | On chevron click |
| L2 | Sync history for this project | On chevron click |
| Global | Conflicts banner + detail | Only when conflicts exist |

### Visual Status Cues

- Green text = everything fine, no action needed
- Orange text + action button = needs attention, here's what to do
- Grey = inactive, opt-in available
- Blue = something is actively happening

### Action Buttons

- **Enable Sync**: backend calls `karma project add <name>`
- **Sync Now**: backend calls `karma sync <project>`
- **Restart Watcher**: backend calls `karma watch`

### Conflicts Section

Pulled out to own section below project list. Only visible when conflicts exist.

```
+--- CONFLICTS (1) -----------------------------------------------+
|                                                                   |
|  side-project / sessions / xyz.jsonl                              |
|  Modified on both machines  |  Mar 3, 2:15 PM                    |
|  Kept: alice-macbook-pro version                                  |
|                                                                   |
|  [ Keep Mine ]  [ Keep Other ]  [ View Diff ]                     |
+-------------------------------------------------------------------+
```

## Tab 4: Activity

Real-time feed of everything happening. The "terminal output" for non-terminal users.

### Layout: Bandwidth Chart + Filterable Event Log

```
+--------------------------------------------------------------+
|  ACTIVITY                                                    |
|                                                              |
|  +--- BANDWIDTH -------- Up: 1.2 MB/s  Down: 450 KB/s ----+|
|  |                                                           ||
|  |  (sparkline chart, ~120px tall, upload/download lines)    ||
|  |                                                           ||
|  |  -1h            -30m             now                      ||
|  |  [ 1h ] [ 6h ] [ 24h ] [ 7d ]                            ||
|  +-----------------------------------------------------------+|
|                                                              |
|  +--- EVENT LOG --------------------------------------------|
|  |                                                           ||
|  |  Filter: [ All types ] [ All devices ] [ All projects ]   ||
|  |                                                           ||
|  |  * 2:34 PM   Transfer complete                            ||
|  |              claude-karma/sessions/abc123.jsonl            ||
|  |              <- alice-mac-mini  45 KB                     ||
|  |                                                           ||
|  |  * 2:34 PM   Transfer started                             ||
|  |              claude-karma/sessions/ghi789.jsonl            ||
|  |              <- alice-mac-mini  89 KB                     ||
|  |                                                           ||
|  |  * 2:30 PM   Device connected                             ||
|  |              alice-mac-mini                                ||
|  |              tcp://192.168.1.42:22000 (LAN)               ||
|  |                                                           ||
|  |  o 2:15 PM   Device disconnected                          ||
|  |              alice-work-pc                                 ||
|  |              Last seen: 2 days ago                         ||
|  |                                                           ||
|  |  ! 1:50 PM   Conflict detected                            ||
|  |              side-project/sessions/xyz.jsonl               ||
|  |              Both machines modified this file              ||
|  |                                           [Resolve ->]    ||
|  |                                                           ||
|  |  * 1:45 PM   Watcher packaged                             ||
|  |              side-project: 3 sessions -> remote-sessions/  ||
|  |                                                           ||
|  |  * 12:00 PM  Scan completed                               ||
|  |              All folders up to date                        ||
|  |                                                           ||
|  |                    [ Load older ]                          ||
|  +-----------------------------------------------------------+|
+--------------------------------------------------------------+
```

### Bandwidth Chart

- Always visible at top, small footprint (~120px tall)
- Two lines: upload (out) and download (in)
- Time range buttons: 1h, 6h, 24h, 7d
- Current rates displayed inline in the section header

### Event Log

Reverse chronological. Each entry:
- **Colored dot**: green (success), orange (warning), grey (info/disconnect), blue (in-progress)
- **Timestamp**: left-aligned, muted
- **Event type**: bold, one line
- **Detail line**: file path, device name, size — muted, smaller text
- **Action link**: only on actionable events (conflicts: "Resolve ->")

### Event Types

| Event | Dot Color | Source |
|-------|-----------|--------|
| Transfer complete | Green | Syncthing events API |
| Transfer started | Blue | Syncthing events API |
| Device connected | Green | Syncthing events API |
| Device disconnected | Grey | Syncthing events API |
| Conflict detected | Orange | Syncthing events API |
| Watcher packaged | Green | `karma watch` log |
| Scan completed | Grey | Syncthing events API |
| Error | Red | Any source |

### Filters

Three dropdowns, all update URL params for bookmarkability:
- Event type: All, Transfers, Connections, Conflicts, Errors
- Device: All devices, or pick one
- Project: All projects, or pick one

### Data Source

Syncthing `/rest/events` SSE endpoint proxied through backend. Live-updating without polling. Bandwidth computed from transfer events. `karma watch` packaging events from sync_history SQLite table.

## API Endpoints (New)

All endpoints proxy to Syncthing REST API and/or execute `karma` CLI commands.

### Setup & Configuration

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/sync/detect` | Check if Syncthing/IPFS installed, return version |
| POST | `/sync/init` | Run `karma init`, return device ID |
| PUT | `/sync/config` | Update network mode settings |

### Device Management

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/sync/devices` | All devices with connection + transfer stats |
| GET | `/sync/devices/{id}` | Single device detail |
| POST | `/sync/devices` | Pair a new device |
| DELETE | `/sync/devices/{id}` | Remove a device |

### Project Sync

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/sync/projects` | All projects with sync state |
| GET | `/sync/projects/{name}/files` | Per-file sync status |
| POST | `/sync/projects/{name}/enable` | Enable sync for a project |
| POST | `/sync/projects/{name}/disable` | Disable sync for a project |
| POST | `/sync/projects/{name}/sync-now` | Trigger manual sync |

### Activity & Monitoring

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/sync/activity` | Event log (paginated) |
| GET | `/sync/activity/stream` | SSE event stream |
| GET | `/sync/bandwidth` | Bandwidth time series |
| POST | `/sync/watcher/restart` | Restart the file watcher |
| POST | `/sync/conflicts/{id}/resolve` | Resolve a conflict |

## Frontend Implementation

### New Files

```
frontend/src/routes/sync/
  +page.svelte          # Main sync page with tabs
  +page.server.ts       # Load sync status + detect state

frontend/src/lib/components/sync/
  SetupTab.svelte       # Backend selection, install, init, pair
  DevicesTab.svelte     # Device monitoring cards
  ProjectsTab.svelte    # Project sync toggles + detail
  ActivityTab.svelte    # Bandwidth chart + event log
  DeviceCard.svelte     # Per-device expandable card
  ProjectRow.svelte     # Per-project collapsible row
  SyncProgress.svelte   # Reusable progress bar
  ConflictPanel.svelte  # Conflict resolution UI
  BandwidthChart.svelte # Chart.js sparkline
```

### Navigation Changes

- Add "Sync" link in Header.svelte (desktop + mobile nav)
- Add skeleton for `/sync` in +layout.svelte

### Component Patterns

- Tabs: use existing tab pattern or `bits-ui` Tabs primitive
- Progress bars: Tailwind width utility with CSS transitions
- Status dots: inline SVG circles with color classes
- Expandable rows: Svelte 5 `$state` for open/closed, CSS transitions
- SSE stream: `EventSource` in `$effect` with cleanup
- Polling: `setInterval` in `$effect` with 10s interval, cleanup on unmount

## Future Enhancements (Post-MVP)

- IPFS backend support (un-grey the IPFS card)
- "Invite via link" — generate a pairing URL with device ID embedded
- Sync scheduling — only sync during certain hours
- Bandwidth limits — throttle Syncthing transfers
- Desktop notifications — alert when sync completes or conflicts detected
- Session-level sync status badges in project views
