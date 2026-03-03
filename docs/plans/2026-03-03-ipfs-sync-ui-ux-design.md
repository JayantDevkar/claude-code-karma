# IPFS Sync UI/UX Design

**Date:** 2026-03-03
**Status:** Approved
**Author:** Jayant Devkar + Claude
**Depends on:** [IPFS Session Sync Design](./2026-03-03-ipfs-session-sync-design.md)

## Problem

The IPFS session sync feature has CLI + API + basic frontend, but users can't visualize:
- Whether their IPFS node is running
- When they last synced each project
- Whether local sessions are up-to-date or have unpushed data
- Multi-machine identity (Bob on MacBook vs Mac Mini)

## Design Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Primary persona | Both freelancer + owner | Every user sees "me vs others" |
| Multi-machine | One IPNS key per machine | Bob on 2 machines = 2 entries, grouped by user_id |
| Session detail depth | Full parity with local | Remote sessions are browsable like local ones |
| Core UI focus | Sync health/status visibility | IPFS running? Last sync? Unpushed sessions? |
| UI placement | Dedicated `/sync` page | Infrastructure-level info deserves its own route |
| Diff engine | API reads, CLI acts | API does read-only comparison, CLI does IPFS operations |
| Storage | SQLite sync_history table | Audit trail, sync-over-time charts, staleness detection |

## User Flow

### Freelancer Side (Client A, B, B2)

```
1. karma init              → pick user_id, auto-detects machine hostname, generates per-machine IPNS key
2. karma project add acme  → registers local project for syncing
3. karma sync acme         → packages sessions → IPFS add → IPNS publish → records push event in SQLite
4. Open dashboard /sync    → sees IPFS status, per-project sync freshness, team activity
```

### Owner Side

```
1. karma team add bob-windows  k51bobwin    → registers each machine separately
   karma team add bob-macmini  k51bobmm
2. karma pull                               → resolves IPNS keys → downloads sessions → records pull events
3. Open dashboard /sync                     → sees IPFS status, team members with last pull times
4. Browse /team                             → drill into remote sessions with full parity
```

### Multi-Machine Sync Flow

```
              PRIVATE IPFS CLUSTER (shared swarm key)

  Alice (MacBook)           Bob (Windows)            Bob (Mac Mini)
  ┌──────────────┐         ┌──────────────┐         ┌──────────────┐
  │ user: alice  │         │ user: bob    │         │ user: bob    │
  │ machine:     │         │ machine:     │         │ machine:     │
  │  macbook-pro │         │  bob-windows │         │  bob-macmini │
  │ IPNS key:    │         │ IPNS key:    │         │ IPNS key:    │
  │  k51alice-mb │         │  k51bob-win  │         │  k51bob-mm   │
  └──────┬───────┘         └──────┬───────┘         └──────┬───────┘
         │                        │                        │
    karma sync acme          karma sync acme          karma sync acme
         │                        │                        │
         ▼                        ▼                        ▼
   ipfs add → Qm111         ipfs add → Qm222        ipfs add → Qm333
   ipns publish              ipns publish             ipns publish
   k51alice-mb→Qm111        k51bob-win→Qm222        k51bob-mm→Qm333
         │                        │                        │
         └────────────────────────┼────────────────────────┘
                                  │
                    IPFS pins replicate across cluster
                                  │
                         ┌────────▼────────┐
                         │  Owner (You)    │
                         │  karma pull     │
                         │                 │
                         │  Resolves:      │
                         │  k51alice-mb → remote-sessions/alice-macbook-pro/
                         │  k51bob-win → remote-sessions/bob-windows/
                         │  k51bob-mm  → remote-sessions/bob-macmini/
                         │                 │
                         │  Records each pull in sync_history SQLite
                         └─────────────────┘
```

Key: IPNS keys are per-machine, not per-user. `karma init` generates a unique key.
The owner adds each machine separately. The UI groups them by `user_id` from the manifest.

## /sync Page Layout

```
┌─────────────────────────────────────────────────────────┐
│                    /sync                                 │
│                                                         │
│  ┌─── MY STATUS ────────────────────────────────────┐   │
│  │  IPFS Daemon:  ● Running                         │   │
│  │  Peers: 3 connected                              │   │
│  │  Identity: alice @ alice-macbook-pro              │   │
│  │  IPNS Key: k51qzi5...                            │   │
│  │  Initialized: ✓ (sync-config.json found)         │   │
│  └──────────────────────────────────────────────────┘   │
│                                                         │
│  ┌─── MY PROJECTS ──────────────────────────────────┐   │
│  │                                                   │   │
│  │  acme-app          ● Up to date                   │   │
│  │  Last sync: 2h ago   Sessions: 12/12 pushed       │   │
│  │  CID: QmXyz...abc                                │   │
│  │                                                   │   │
│  │  side-project      ⚠ 3 unpushed sessions          │   │
│  │  Last sync: 2d ago   Sessions: 5/8 pushed         │   │
│  │  [Sync instructions shown]                        │   │
│  │                                                   │   │
│  └──────────────────────────────────────────────────┘   │
│                                                         │
│  ┌─── TEAM ─────────────────────────────────────────┐   │
│  │                                                   │   │
│  │  bob ─────────────────────────────────────────    │   │
│  │  ├─ bob-windows     Last pull: 1h ago             │   │
│  │  │    acme-app: 8 sessions                        │   │
│  │  └─ bob-macmini     Last pull: 1h ago             │   │
│  │       acme-app: 4 sessions                        │   │
│  │                                                   │   │
│  │  carol ───────────────────────────────────────    │   │
│  │  └─ carol-laptop    Last pull: 1h ago             │   │
│  │       acme-app: 6 sessions                        │   │
│  │                                                   │   │
│  └──────────────────────────────────────────────────┘   │
│                                                         │
│  ┌─── SYNC HISTORY ─────────────────────────────────┐   │
│  │  [Table of recent push/pull events from SQLite]   │   │
│  │  Time     | Type | User  | Machine | Project | #  │   │
│  │  2h ago   | push | alice | macbook | acme    | 12 │   │
│  │  1h ago   | pull | bob   | windows | acme    |  8 │   │
│  │  1h ago   | pull | bob   | macmini | acme    |  4 │   │
│  │  1h ago   | pull | carol | laptop  | acme    |  6 │   │
│  └──────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────┘
```

### Status Indicators

| State | Icon | Meaning |
|-------|------|---------|
| ● green | Running | IPFS daemon healthy, peers connected |
| ● orange | Degraded | IPFS running but 0 peers, or sync stale >24h |
| ● red | Down | IPFS daemon not reachable |
| ✓ green | Up to date | All local sessions synced |
| ⚠ orange | Unpushed | Local sessions exist that haven't been synced |
| ✗ red | Not initialized | No sync-config.json found |

## Database Schema

### sync_history table (in ~/.claude_karma/metadata.db)

```sql
CREATE TABLE sync_history (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    event_type    TEXT NOT NULL,        -- 'push' or 'pull'
    user_id       TEXT NOT NULL,        -- who synced
    machine_id    TEXT NOT NULL,        -- which machine
    project       TEXT NOT NULL,        -- project name
    cid           TEXT,                 -- IPFS CID
    ipns_key      TEXT,                 -- IPNS key used
    session_count INTEGER DEFAULT 0,    -- sessions in this sync
    created_at    TEXT NOT NULL         -- ISO timestamp
);

CREATE INDEX idx_sync_history_user ON sync_history(user_id);
CREATE INDEX idx_sync_history_project ON sync_history(project);
CREATE INDEX idx_sync_history_created ON sync_history(created_at);
```

**Push events** — recorded by CLI after `karma sync` succeeds.
**Pull events** — recorded by CLI after `karma pull` fetches from each member.

Enables: last-synced display, sync frequency charts, staleness detection, audit trail.

## API Endpoints

### New /sync router

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/sync/status` | IPFS daemon health, peer count, identity, init state |
| GET | `/sync/projects` | Per-project sync state: local count vs synced count, freshness |
| GET | `/sync/team` | Pulled team members grouped by user_id, with last pull time |
| GET | `/sync/history` | Paginated sync_history from SQLite |

### /sync/status response

```json
{
  "initialized": true,
  "user_id": "alice",
  "machine_id": "alice-macbook-pro",
  "ipfs_running": true,
  "ipfs_peer_count": 3,
  "ipns_key": "k51qzi5..."
}
```

### /sync/projects response

```json
[
  {
    "name": "acme-app",
    "path": "/Users/alice/work/acme-app",
    "local_session_count": 12,
    "synced_session_count": 12,
    "unpushed_count": 0,
    "last_sync_at": "2026-03-03T12:00:00Z",
    "last_sync_cid": "QmXyz...",
    "status": "up_to_date"
  },
  {
    "name": "side-project",
    "local_session_count": 8,
    "synced_session_count": 5,
    "unpushed_count": 3,
    "last_sync_at": "2026-03-01T10:00:00Z",
    "last_sync_cid": "QmAbc...",
    "status": "unpushed"
  }
]
```

### /sync/team response

```json
{
  "members": [
    {
      "user_id": "bob",
      "machines": [
        {
          "machine_id": "bob-windows",
          "ipns_key": "k51bobwin",
          "last_pull_at": "2026-03-03T13:00:00Z",
          "projects": [
            { "name": "acme-app", "session_count": 8 }
          ]
        },
        {
          "machine_id": "bob-macmini",
          "ipns_key": "k51bobmm",
          "last_pull_at": "2026-03-03T13:00:00Z",
          "projects": [
            { "name": "acme-app", "session_count": 4 }
          ]
        }
      ]
    }
  ]
}
```

## CLI Changes

### karma init (modified)

Generates a per-machine IPNS key named `karma-{user_id}-{machine_id}`:
```bash
$ karma init
Your user ID: alice
Generating IPNS key: karma-alice-macbook-pro
Key ID: k51qzi5...

Share this key with your project owner:
  k51qzi5...
```

### karma status (new command)

Quick CLI check matching the /sync page info:
```bash
$ karma status
IPFS: ● Running (3 peers)
Identity: alice @ alice-macbook-pro
IPNS Key: k51qzi5...

Projects:
  acme-app:      ✓ Up to date (12 sessions, synced 2h ago)
  side-project:  ⚠ 3 unpushed (5/8 synced, last sync 2d ago)
```

### karma sync (modified)

After successful sync, writes a push event to sync_history SQLite table.

### karma pull (modified)

After each member fetch, writes a pull event to sync_history SQLite table.

## Frontend Routes

| Route | Description |
|-------|-------------|
| `/sync` | Sync health dashboard (IPFS status, project sync state, team, history) |
| `/team` | Browse remote sessions (existing, enhanced with user grouping) |
| `/team/[user_id]` | User's synced projects (existing) |

## Future Enhancements

- Real-time IPFS status polling (WebSocket or SSE)
- "Sync Now" button in UI that triggers CLI via local API
- Sync frequency charts from sync_history data
- Staleness alerts ("Bob hasn't synced in 3 days")
- Auto-sync via SessionEnd hook integration
