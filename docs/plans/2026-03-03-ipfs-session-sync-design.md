# IPFS Session Sync Design

**Date:** 2026-03-03
**Status:** Approved
**Author:** Jayant Devkar + Claude

## Problem

Claude Karma is 100% local-machine only. If you hire 4-10 freelancers who each use Claude Code on their own machines (Mac, Windows, Linux), there's no way to see their session activity in your dashboard. Same user on multiple machines (Mac Mini + MacBook Pro) also can't unify their sessions.

## Goal

Enable cross-system session sharing using IPFS (InterPlanetary File System) so a project owner can monitor freelancers' Claude Code usage from a central Karma dashboard.

## Requirements

- Freelancers own their `~/.claude/` — they selectively share specific project sessions
- One user may have multiple machines — sessions should be unified per user identity
- Private IPFS cluster (no public access to session data)
- MVP: CLI command `karma sync <project>` to push sessions on demand
- Different projects can sync to different teams
- Both real-time monitoring (later) and historical review (MVP)

## Architecture

```
                    PRIVATE IPFS CLUSTER
                   (shared swarm key)

  ┌──────────────┐  ┌──────────────┐  ┌──────────────────────┐
  │ Freelancer A │  │ Freelancer B │  │  Project Owner (You) │
  │  Kubo node   │  │  Kubo node   │  │    Kubo node         │
  │  Mac Mini    │  │  Windows     │  │    Mac Mini           │
  └──────┬───────┘  └──────┬───────┘  └──────────┬───────────┘
         │                 │                      │
         └────────────┬────┘                      │
                      │                           │
              pins replicate across cluster        │
                      │                           │
              ┌───────▼─────────┐         ┌───────▼─────────┐
              │  karma sync     │         │  Karma Dashboard │
              │  (CLI)          │         │  API reads from  │
              │                 │         │  local IPFS node │
              └─────────────────┘         └─────────────────┘
```

### Components

1. **`karma` CLI** — new Python CLI tool in `cli/` directory (uses `click`)
2. **Kubo IPFS node** — each participant runs one (background daemon, ~50MB)
3. **Swarm key** — shared secret that makes the IPFS cluster private
4. **Karma API extension** — new router to read sessions from IPFS alongside local `~/.claude/`

## Data Model

### What Gets Synced

When a freelancer runs `karma sync <project>`, sessions for that project are packaged as an IPFS DAG:

```
karma-sync/{user-id}/{project-encoded-name}/
├── manifest.json
├── sessions/
│   ├── {uuid1}.jsonl
│   ├── {uuid2}.jsonl
│   ├── {uuid1}/
│   │   ├── subagents/
│   │   │   └── agent-*.jsonl
│   │   └── tool-results/
│   │       └── toolu_*.txt
│   └── {uuid2}/
│       └── ...
└── todos/
    └── {uuid1}-*.json
```

### manifest.json

```json
{
  "version": 1,
  "user_id": "freelancer-alice",
  "machine_id": "alice-macbook-pro",
  "project_path": "/Users/alice/work/acme-app",
  "project_encoded": "-Users-alice-work-acme-app",
  "synced_at": "2026-03-03T14:30:00Z",
  "session_count": 12,
  "sessions": [
    {
      "uuid": "abc123...",
      "mtime": "2026-03-03T12:00:00Z",
      "size_bytes": 45000
    }
  ],
  "previous_cid": "Qm..."
}
```

**Key fields:**
- `user_id` — freelancer picks during `karma init`
- `machine_id` — auto-generated from hostname, distinguishes same user across machines
- `previous_cid` — chain of syncs for history
- Only project-specific files synced, never global `.claude/` config

### Incremental Sync

Compare local session UUIDs + mtimes against last synced manifest. Only add new/changed files to avoid re-uploading everything.

## CLI Design

New `cli/` directory in monorepo. Python package using `click`.

### Commands

```bash
# First-time setup
karma init
# Prompts: user_id, checks Kubo is running, imports swarm key

# Configure a project for syncing
karma project add acme-app --path /Users/alice/work/acme-app
# Stores config in ~/.claude_karma/sync-config.json

# Sync a project's sessions to IPFS
karma sync acme-app
# Packages sessions, ipfs add -r, pins, prints CID
# Output: "Synced 12 sessions (3 new) → QmXyz..."

# Sync all configured projects
karma sync --all

# List available remote data (on dashboard machine)
karma ls
# Shows all users, projects, latest CIDs

# Pull remote sessions into local dashboard
karma pull
# Fetches all pinned session data from IPFS into ~/.claude_karma/remote-sessions/

# Team management (on owner's machine)
karma team add alice <ipns-key>
karma team list
karma team remove alice
```

### Config File

`~/.claude_karma/sync-config.json`:

```json
{
  "user_id": "alice",
  "machine_id": "alice-macbook-pro",
  "projects": {
    "acme-app": {
      "path": "/Users/alice/work/acme-app",
      "encoded_name": "-Users-alice-work-acme-app",
      "last_sync_cid": "Qm...",
      "last_sync_at": "2026-03-03T14:30:00Z"
    }
  },
  "ipfs_api": "http://127.0.0.1:5001",
  "team": {
    "alice": { "ipns_key": "k51..." },
    "bob": { "ipns_key": "k51..." }
  }
}
```

## IPFS Discovery via IPNS

Each freelancer publishes their latest sync to an IPNS name (mutable pointer to latest CID):

1. `karma sync` does: `ipfs name publish /ipfs/QmLatestCID`
2. Freelancer's IPNS key = persistent identity on the cluster
3. Dashboard resolves each IPNS name → gets latest CID → fetches data

### Onboarding Flow

```
Freelancer:  karma init → generates IPNS key → shares key with project owner
Owner:       karma team add alice <ipns-key>
             karma pull → resolves all team IPNS keys → fetches sessions
```

## Dashboard Integration

### Local Storage

```
~/.claude_karma/
├── remote-sessions/
│   ├── alice/
│   │   └── -Users-alice-work-acme-app/
│   │       ├── manifest.json
│   │       └── sessions/
│   │           ├── {uuid}.jsonl
│   │           └── ...
│   └── bob/
│       └── -Users-bob-projects-acme-app/
│           └── ...
├── sync-config.json
└── live-sessions/
```

### API Changes

New router: `api/routers/remote_sessions.py`

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/remote/users` | List all synced freelancers |
| GET | `/remote/users/{user_id}/projects` | User's synced projects |
| GET | `/remote/users/{user_id}/projects/{project}/sessions` | Sessions list |
| GET | `/remote/sessions/{user_id}/{project}/{uuid}` | View a remote session |
| GET | `/remote/sessions/{user_id}/{project}/{uuid}/timeline` | Session timeline |
| GET | `/remote/analytics/{project}` | Aggregate analytics across all contributors |

Extend existing endpoints:
- `/projects` — optionally include remote session counts
- `/analytics/projects/{name}` — merge remote contributor data

### Frontend Changes

- New "Team" section in sidebar
- Per-user view: sessions, activity timeline, tool usage
- Aggregate project view: progress across all contributors
- User identity badges on sessions (who did what)

## IPFS Implementation Details

### Python ↔ IPFS Communication

The `ipfshttpclient` Python library is poorly maintained. Use **subprocess wrapper** around `ipfs` CLI:

```python
import subprocess
import json

def ipfs_add(path: str, recursive: bool = True) -> str:
    """Add file/directory to IPFS, return CID."""
    cmd = ["ipfs", "add", "-Q"]  # -Q = quiet, only output CID
    if recursive:
        cmd.append("-r")
    cmd.append(path)
    result = subprocess.run(cmd, capture_output=True, text=True, check=True)
    return result.stdout.strip()

def ipfs_name_publish(cid: str) -> str:
    """Publish CID to IPNS."""
    cmd = ["ipfs", "name", "publish", f"/ipfs/{cid}"]
    result = subprocess.run(cmd, capture_output=True, text=True, check=True)
    return result.stdout.strip()

def ipfs_get(cid: str, output_path: str):
    """Fetch content by CID."""
    cmd = ["ipfs", "get", cid, "-o", output_path]
    subprocess.run(cmd, check=True)
```

### Private Cluster Setup

1. Generate swarm key: `ipfs-swarm-key-gen > ~/.ipfs/swarm.key`
2. Distribute `swarm.key` to all participants
3. Set bootstrap nodes: `ipfs bootstrap rm --all && ipfs bootstrap add <owner-multiaddr>`
4. Configure: `LIBP2P_FORCE_PNET=1` environment variable

## Security & Privacy

- **Swarm key** ensures only cluster members can access data
- **IPNS keys** are per-user — freelancer controls what they publish
- **No global `.claude/` access** — only explicitly configured project dirs synced
- **Session data may contain sensitive code** — private cluster keeps it off public IPFS
- Freelancers can `karma project remove <name>` to stop syncing at any time
- Content-addressed = tamper-evident (CID changes if data modified)

## Future Enhancements (Post-MVP)

- **Real-time monitoring**: IPFS PubSub or coordination webhook for live session state
- **Automatic sync via hooks**: `SessionEnd` hook triggers `karma sync` automatically
- **Web UI for onboarding**: Generate invite links with embedded swarm key
- **Session comments/annotations**: Owner can annotate freelancer sessions
- **Cost tracking**: Aggregate token usage across freelancers for billing

## References

- [IPFS Private Cluster Setup](https://geekdecoder.com/setting-up-a-private-ipfs-network-with-ipfs-and-ipfs-cluster/)
- [IPFS Cluster Docs](https://docs.ipfs.tech/install/server-infrastructure/)
- [Kubo Installation](https://docs.ipfs.tech/install/command-line/)
- [IPFS-Toolkit Python](https://github.com/emendir/IPFS-Toolkit-Python)
- [Building Private IPFS Networks](https://eleks.com/research/ipfs-network-data-replication/)
