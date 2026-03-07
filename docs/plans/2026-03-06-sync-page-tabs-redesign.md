# Sync Page Tabs Redesign

Date: 2026-03-06
Status: Approved

## Problem

The current sync page has 4 tabs (Overview, Members, Projects, Activity) with several UX issues:

1. **Overview is overloaded** — contains sync engine control, team management, stats, getting started guide, machine details, AND pending actions (6 concerns).
2. **Information duplication** — "Your Sync ID" appears in both Overview and Members. Member/project counts in TeamSelector AND Overview stats.
3. **Team management is scattered** — create team via TeamSelector, delete in Overview, add members in Members tab.
4. **Activity shows raw Syncthing events** — `FolderCompletion`, `StateChanged` etc. are meaningless to users who care about session sync.

## Design

### Tab Structure

```
Overview  |  Team  |  Projects  |  Activity
```

Four tabs with clear, non-overlapping responsibilities.

### Tab 1: Overview — "What's happening right now?"

At-a-glance health check. Is sync working? Any problems?

**Sections (top to bottom):**

1. **Sync Engine Banner** — full-width, prominent. Running/Stopped status with start/stop button. The #1 operational control.

2. **Stats Row** (4 cards):
   - Members Online: `2/3 connected`
   - Projects Syncing: `4 projects`
   - Sessions Shared: total packaged count (outbox)
   - Sessions Received: total received from teammates (inboxes)

3. **Pending Actions** — only renders when count > 0. Folder offers from teammates needing acceptance. When zero, section doesn't appear at all.

4. **Machine Details** — your name, machine ID, Sync ID with copy button, Syncthing version. Reference info at the bottom.

### Tab 2: Team — "Who am I syncing with?"

Replaces "Members" tab. Absorbs team-level config that was scattered across Overview and Members.

**Sections:**

1. **Team Header Card** — team name, backend type. "Delete Team" as a danger-zone action (behind `...` menu or at bottom).

2. **Your Sync ID** (copyable) — "Share this with teammates to connect." Natural home: you're looking at team membership.

3. **Members List** — each member as a card:
   - Name, connection status dot (green/gray)
   - Data transferred (in/out bytes)
   - Last seen / address
   - Remove button (hover-reveal)

4. **Add Member Form** — inline at bottom: Sync ID input + Name input + Add button.

### Tab 3: Projects — "What am I syncing?"

Toggle which projects sync. See per-project health.

**Sections:**

1. **Header row** — "X of Y syncing" + "Enable All" button + search filter

2. **Project List** — each row:
   - Project name + path
   - Toggle switch (synced/not synced)
   - Sync health when enabled:
     - Local sessions count
     - Packaged count (outbox)
     - Gap indicator ("3 behind" warning, or "up to date" green)
     - Per-member received counts (e.g., "alice: 12, bob: 8")
   - "Sync Now" button

### Tab 4: Activity — "What happened recently?"

Session-level sync feed. Human-readable, not raw Syncthing events.

**Sections:**

1. **Header** — "Activity" + "Sync Now" button (rescan all)

2. **Live Status Bar** (compact) — upload/download rate, single line. No full bandwidth chart.

3. **Session Activity Feed** — translated events:
   - "alice synced 3 sessions for claude-karma — 5 min ago"
   - "bob's machine connected — 12 min ago"
   - "Received 2 new sessions from alice — 1 hr ago"

4. **Folder Status** (collapsible, advanced) — raw Syncthing folder stats. Collapsed by default with "Show folder details" toggle.

## Information Placement Rules (no duplication)

| Information | Lives in | NOT in |
|---|---|---|
| Sync engine start/stop | Overview | — |
| Members online count | Overview (stats) | Team tab |
| Member list + connection details | Team tab | Overview |
| Your Sync ID | Team tab | Overview |
| Machine details (name, hostname, version) | Overview | Team tab |
| Project list + toggle | Projects tab | Overview |
| Project sync health (local/packaged/gap) | Projects tab | Activity |
| Pending folder offers | Overview | Team tab |
| Session activity feed | Activity tab | Overview |
| Bandwidth rates | Activity tab (compact) | Overview |
| Delete team | Team tab | Overview |

## Non-goals

- No admin/member privilege system (fully peer-to-peer, trust-based)
- No multi-team dashboard view (team-scoped via TeamSelector)
- No raw bandwidth chart (users can open Syncthing UI at localhost:8384)

## CLI Feature Parity

All CLI sync features accessible via web UI:

| CLI Command | Web UI Location |
|---|---|
| `karma init --backend syncthing` | SetupWizard (pre-tabs) |
| `karma team create` | TeamSelector "+ New Team" |
| `karma team add` | Team tab → Add Member form |
| `karma team remove` | Team tab → member hover → Remove |
| `karma team list` | Team tab → Members List |
| `karma project add --team` | Projects tab → toggle on |
| `karma project remove --team` | Projects tab → toggle off |
| `karma project list` | Projects tab |
| `karma watch --team` | Overview → Sync Engine start |
| `karma accept` | Overview → Pending Actions → Accept All |
| `karma status` | Overview (stats) + Projects tab (per-project health) |
| `karma ls` | Projects tab (received counts per member) |
