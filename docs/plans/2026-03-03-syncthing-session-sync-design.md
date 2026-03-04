# Syncthing Session Sync Design

**Date:** 2026-03-03
**Status:** Approved
**Author:** Jayant Devkar + Claude

## Problem

Claude Karma is 100% local-machine only. If you hire 4-10 freelancers who each use Claude Code on their own machines (Mac, Windows, Linux), there's no way to see their session activity in your dashboard. Same user on multiple machines also can't unify their sessions.

An IPFS-based sync design exists (`2026-03-03-ipfs-session-sync-design.md`) but requires running a Kubo daemon and is on-demand only. Syncthing provides an alternative that offers real-time, automatic sync with simpler setup for trusted teams.

## Goal

Enable cross-system session sharing using Syncthing as a pluggable sync backend alongside IPFS. Both backends produce the same data format so the dashboard API reads them identically.

## Requirements

- Freelancers own their `~/.claude/` — they selectively share specific project sessions
- One user may have multiple machines — sessions should be unified per user identity
- Fully automatic sync after initial setup (no CLI commands needed)
- Bidirectional: owner can push feedback/annotations back to freelancers
- Backend is per-team (a user can use IPFS for one team, Syncthing for another)
- Same data format as IPFS design (manifest.json + sessions/)
- Direct connections by default (no public relays)

## Architecture

```
                SYNCTHING MESH
          (device ID pairing, TLS encrypted)

  ┌──────────────┐  ┌──────────────┐  ┌──────────────────────┐
  │ Freelancer A │  │ Freelancer B │  │  Project Owner (You) │
  │  Syncthing   │  │  Syncthing   │  │    Syncthing         │
  │  Mac Mini    │  │  Windows     │  │    Mac Mini           │
  └──────┬───────┘  └──────┬───────┘  └──────────┬───────────┘
         │                 │                      │
    sync-outbox/      sync-outbox/          sync-inbox/
    (auto-packaged)   (auto-packaged)       (auto-received)
         │                 │                      │
         └────────────┬────┘                      │
                      │                           │
              Syncthing auto-syncs                │
              (bidirectional, TLS)                 │
                      │                           │
              ┌───────▼─────────┐         ┌───────▼─────────┐
              │  karma watch    │         │  Karma Dashboard │
              │  (packages      │         │  API reads from  │
              │   sessions)     │         │  remote-sessions/│
              └─────────────────┘         └─────────────────┘
```

### Components

1. **`karma` CLI** — extended with `--backend syncthing` support, new `karma watch` command
2. **Syncthing** — each participant runs it. Handles transport + encryption
3. **Device ID pairing** — Syncthing's native trust model (Ed25519 key pairs)
4. **Karma API** — same `/remote/*` endpoints, reads from `~/.claude_karma/remote-sessions/` regardless of backend

### Key Difference from IPFS

No IPNS, no CIDs, no Kubo daemon. Syncthing handles discovery, transport, and encryption natively. The `karma` CLI only handles packaging sessions into the shared folder format.

## Data Model

### What Gets Synced

The packaging format is identical to the IPFS design so the API reads both the same way.

### Syncthing Shared Folders

```
~/.claude_karma/
├── sync-outbox/                    # Freelancer → Owner (Syncthing watches this)
│   └── {team}/
│       └── {user-id}/
│           └── {project-encoded-name}/
│               ├── manifest.json
│               ├── sessions/
│               │   ├── {uuid1}.jsonl
│               │   ├── {uuid2}.jsonl
│               │   ├── {uuid1}/
│               │   │   ├── subagents/
│               │   │   │   └── agent-*.jsonl
│               │   │   └── tool-results/
│               │   │       └── toolu_*.txt
│               │   └── {uuid2}/
│               │       └── ...
│               └── todos/
│                   └── {uuid1}-*.json
│
├── sync-inbox/                     # Owner → Freelancer (bidirectional)
│   └── {team}/
│       └── {owner-id}/
│           └── {project-encoded-name}/
│               └── feedback/
│                   ├── {session-uuid}.json    # Per-session annotations
│                   └── project-notes.json     # General project notes
│
├── remote-sessions/                # API reads from here (both backends land here)
│   └── {user-id}/
│       └── {project-encoded-name}/
│           ├── manifest.json
│           └── sessions/
│               └── ...
│
└── sync-config.json
```

### Syncthing Folder Type Mapping

| Syncthing Folder | Path | Freelancer Side | Owner Side |
|---|---|---|---|
| `karma-out-{user-id}` | `sync-outbox/{team}/{user-id}/` | `sendonly` | `receiveonly` |
| `karma-in-{owner-id}` | `sync-inbox/{team}/{owner-id}/` | `receiveonly` | `sendonly` |

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
  "sync_backend": "syncthing",
  "sessions": [
    {
      "uuid": "abc123...",
      "mtime": "2026-03-03T12:00:00Z",
      "size_bytes": 45000
    }
  ]
}
```

Only addition vs IPFS: `"sync_backend": "syncthing"` field.

## CLI Design

### Backend Selection During Init

```bash
$ karma init

Detecting available backends...
  ✓ Syncthing found (v1.27.0, REST API on :8384)
  ✓ Kubo/IPFS found (v0.24.0, API on :5001)

? Which sync backend do you want to use?
  › Syncthing (recommended for small trusted teams, real-time sync)
    IPFS (recommended for larger teams, on-demand sync, tamper-evident)
```

- If only one backend detected → auto-selects it
- If both detected → asks the user
- If neither detected → prints install instructions and exits
- User can switch later with `karma init --backend syncthing`

### Commands

```bash
# First-time setup with Syncthing backend
karma init --backend syncthing
# Checks Syncthing is running (REST API on port 8384)
# Generates user_id, machine_id
# Prints Device ID for sharing with owner

# Create a team
karma team create alpha --backend syncthing

# Configure a project for syncing
karma project add acme-app --path /Users/alice/work/acme-app --team alpha

# Start the background watcher (packages sessions automatically)
karma watch
# Uses watchdog library to monitor ~/.claude/projects/{encoded-path}/
# On file change → re-packages into sync-outbox/
# Debounces: waits 5 seconds of no changes before packaging

# Stop the watcher
karma watch --stop

# Check sync status
karma status
# Shows: backend, watcher running?, last sync time, pending changes

# Team management (owner side)
karma team add alice <syncthing-device-id>
# Configures Syncthing to share folders with alice's device

karma team list
# Shows all paired devices + their sync state

karma team remove alice
# Removes Syncthing folder sharing for alice
```

### Backend-Agnostic Command Behavior

| Command | IPFS behavior | Syncthing behavior |
|---|---|---|
| `karma init` | Checks Kubo, imports swarm key | Checks Syncthing REST API |
| `karma project add` | Stores config | Stores config + creates Syncthing folder |
| `karma sync` | Packages + ipfs add + IPNS publish | Packages into sync-outbox (Syncthing handles rest) |
| `karma watch` | N/A (IPFS is on-demand) | Starts filesystem watcher |
| `karma team add` | Stores IPNS key | Pairs Syncthing device + shares folders |
| `karma pull` | Resolves IPNS + ipfs get | N/A (Syncthing auto-syncs) |
| `karma status` | Shows last CID, sync time | Shows Syncthing connection state |

### Config File

`~/.claude_karma/sync-config.json`:

```json
{
  "user_id": "alice",
  "machine_id": "alice-macbook-pro",
  "teams": {
    "alpha": {
      "backend": "ipfs",
      "owner_ipns_key": "k51...",
      "projects": {
        "acme-app": {
          "path": "/Users/alice/work/acme-app",
          "last_sync_cid": "Qm..."
        }
      }
    },
    "beta": {
      "backend": "syncthing",
      "owner_device_id": "YYYYYYY-...",
      "projects": {
        "startup-app": {
          "path": "/Users/alice/work/startup-app",
          "last_package_at": "2026-03-03T14:30:00Z"
        }
      }
    }
  },
  "ipfs": {
    "api_url": "http://127.0.0.1:5001"
  },
  "syncthing": {
    "api_url": "http://127.0.0.1:8384",
    "api_key": "abc123...",
    "device_id": "XXXXXXX-XXXXXXX-XXXXXXX-XXXXXXX-XXXXXXX-XXXXXXX-XXXXXXX-XXXXXXX"
  }
}
```

## Syncthing Integration Details

### Python ↔ Syncthing Communication

Syncthing exposes a REST API on `http://127.0.0.1:8384`. Use `requests`:

```python
import requests

class SyncthingClient:
    def __init__(self, api_url: str, api_key: str):
        self.api_url = api_url
        self.headers = {"X-API-Key": api_key}

    def get_device_id(self) -> str:
        """Get this device's ID."""
        resp = requests.get(f"{self.api_url}/rest/system/status", headers=self.headers)
        return resp.json()["myID"]

    def add_device(self, device_id: str, name: str):
        """Pair with a remote device."""
        config = self._get_config()
        config["devices"].append({"deviceID": device_id, "name": name})
        self._set_config(config)

    def add_folder(self, folder_id: str, path: str, devices: list[str], folder_type: str = "sendonly"):
        """Create a shared folder with specified devices."""
        config = self._get_config()
        config["folders"].append({
            "id": folder_id,
            "path": path,
            "devices": [{"deviceID": d} for d in devices],
            "type": folder_type,
        })
        self._set_config(config)

    def get_connections(self) -> dict:
        """Check which devices are connected."""
        resp = requests.get(f"{self.api_url}/rest/system/connections", headers=self.headers)
        return resp.json()["connections"]

    def _get_config(self) -> dict:
        resp = requests.get(f"{self.api_url}/rest/config", headers=self.headers)
        return resp.json()

    def _set_config(self, config: dict):
        requests.put(f"{self.api_url}/rest/config", json=config, headers=self.headers)
```

### Watcher Implementation

```python
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
import threading

class SessionWatcher(FileSystemEventHandler):
    def __init__(self, packager, debounce_seconds=5):
        self.packager = packager
        self.debounce = debounce_seconds
        self._timer = None

    def on_modified(self, event):
        if event.src_path.endswith(".jsonl"):
            self._debounced_package(event.src_path)

    def _debounced_package(self, path):
        if self._timer:
            self._timer.cancel()
        self._timer = threading.Timer(
            self.debounce, self.packager.package_project, args=[path]
        )
        self._timer.start()
```

The watcher monitors `~/.claude/projects/` for JSONL changes, debounces for 5 seconds, then packages into `sync-outbox/`. Syncthing picks up the changes automatically.

### Onboarding Flow

```
Freelancer:                              Owner:

1. Install Syncthing                     1. Install Syncthing
2. karma init --backend syncthing        2. karma init --backend syncthing
3. Share Device ID with owner    ──────► 3. karma team add alice <device-id>
                                         4. Share own Device ID back  ◄──────
5. karma team add owner <device-id>
6. karma project add acme-app --team beta
7. karma watch
                                         Sessions appear in dashboard!
```

## Security & Privacy

### Transport Security Comparison

| Layer | IPFS | Syncthing |
|---|---|---|
| Encryption | Swarm key (symmetric) | TLS 1.3 (per-connection) |
| Authentication | Swarm membership | Device ID (Ed25519 key pair) |
| Discovery | DHT within swarm | Local announcements (default) |
| Data at rest | Not encrypted by default | Not encrypted by default |

### Syncthing Network Configuration

By default, we configure Syncthing for maximum privacy:

```json
{
    "options": {
        "relaysEnabled": false,
        "globalAnnounceEnabled": false,
        "localAnnounceEnabled": true
    }
}
```

For remote freelancers (different networks):
- **Option A:** Open port 22000 (Syncthing's default)
- **Option B:** Use a VPN (Tailscale, WireGuard) — Syncthing discovers over the VPN
- **Option C:** Enable Syncthing relays (data is encrypted, relay can't read it)

The `karma init` setup asks which network mode to use.

### Data Privacy

- **No global `~/.claude/` access** — only explicitly configured project dirs synced
- **Send-only folders** — freelancer controls what they share
- **Session data may contain sensitive code** — direct connections + TLS keeps it private
- Freelancers can `karma project remove <name>` to stop syncing
- `karma watch --stop` halts all automatic syncing immediately

### Syncthing vs IPFS Security Trade-offs

| Concern | IPFS | Syncthing |
|---|---|---|
| Tamper evidence | CID changes if data modified | No built-in (trust the TLS channel) |
| Audit trail | CID chain via `previous_cid` | Syncthing versioning (optional) |
| Data sovereignty | Freelancer publishes on-demand | Freelancer can pause/stop watch |
| Network exposure | Private swarm only | Direct connection + optional relay |

## Dashboard Integration

### API Changes

Since both backends produce the same folder structure in `~/.claude_karma/remote-sessions/`, the existing `/remote/*` endpoints work unchanged.

New endpoints:

| Method | Endpoint | Description |
|---|---|---|
| GET | `/sync/status` | Backend type, connection state, last sync time per team |
| GET | `/sync/teams` | List all teams with their backend + members |

### Frontend Additions

- **Sync status indicator** — green (connected), yellow (syncing), grey (disconnected)
- **Backend badge** — "IPFS" or "Syncthing" label on each team card
- **Feedback panel** (Syncthing only) — owner can write per-session annotations that sync back

## Design Decisions Summary

| Decision | Choice | Rationale |
|---|---|---|
| Approach | Syncthing as pluggable sync backend | Supports both IPFS and Syncthing |
| Sync trigger | Fully automatic (watcher + Syncthing) | Leverages Syncthing's core strength |
| Onboarding | Device ID exchange | Simple, secure, native Syncthing |
| Data format | Same as IPFS (manifest.json + sessions/) | API reads both identically |
| Direction | Bidirectional (send-only/receive-only folders) | Owner can push feedback |
| Multi-team | Backend is per-team | User can use IPFS for one team, Syncthing for another |
| Security | Direct connections, no relays by default | Maximum privacy for trusted teams |

## Future Enhancements (Post-MVP)

- **Live session streaming** — Syncthing's event API notifies dashboard when new files arrive
- **Automatic `karma watch` via launchd/systemd** — starts on boot
- **Conflict resolution UI** — if both backends deliver data for same user/project
- **Encrypted folders** — Syncthing's "untrusted" mode for cloud relay setups
- **SessionEnd hook integration** — immediate packaging on session end (no debounce)
- **Cost tracking** — aggregate token usage across freelancers for billing

## References

- [Syncthing Documentation](https://docs.syncthing.net/)
- [Syncthing REST API](https://docs.syncthing.net/dev/rest.html)
- [Syncthing Security](https://docs.syncthing.net/users/security.html)
- [watchdog (Python filesystem events)](https://github.com/gorakhargosh/watchdog)
- [IPFS Session Sync Design](./2026-03-03-ipfs-session-sync-design.md)
