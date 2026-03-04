# Syncing Sessions

How Claude Code Karma shares sessions across machines and teams using IPFS or Syncthing.

---

## Why Sync Sessions?

Claude Karma is local-first — it reads from `~/.claude/` on a single machine. But if you hire freelancers who each use Claude Code on their own machines, or you work across multiple devices, there's no way to see all session activity in one dashboard.

Session sync solves this. Freelancers selectively share project sessions with a project owner, who sees everything in their Karma dashboard. Two sync backends are available, each suited to different team structures.

---

## Choosing a Backend

Each team picks one backend. A single user can belong to multiple teams using different backends.

| | IPFS | Syncthing |
|---|---|---|
| **Sync model** | On-demand (push/pull) | Automatic (real-time) |
| **Team size** | Any size, loosely connected | Small trusted teams (2-10) |
| **Setup complexity** | Higher (Kubo daemon + swarm key) | Lower (Syncthing + device IDs) |
| **Audit trail** | Built-in (CID chain via `previous_cid`) | None built-in |
| **Tamper evidence** | Yes (content-addressed, CID changes if modified) | No (trust the TLS channel) |
| **Encryption** | Swarm key (symmetric, shared secret) | TLS 1.3 (per-connection, device certificate) |
| **Authentication** | Swarm membership | Device ID (Ed25519 key pair) |
| **Discovery** | DHT within private swarm | Local announcements or relay |
| **Dependency** | Kubo daemon on every machine (~50MB) | Syncthing daemon on every machine |
| **Best for** | Distributed teams, compliance, audit needs | Co-located teams, real-time visibility |

---

## 1. IPFS Backend

### How It Works

IPFS (InterPlanetary File System) uses content-addressed storage. Each sync snapshot is an immutable DAG identified by a CID (Content Identifier). IPNS (InterPlanetary Name System) provides a mutable pointer so team members can discover the latest snapshot.

```
Freelancer runs `karma sync`
    │
    ▼
SessionPackager discovers JSONL sessions
    │
    ▼
Packages into staging directory + manifest.json
    │
    ▼
ipfs add -r (recursive) → returns CID
    │
    ▼
ipfs pin add (prevents garbage collection)
    │
    ▼
ipfs name publish (updates IPNS pointer to latest CID)
    │
    ▼
Owner runs `karma pull`
    │
    ▼
ipfs name resolve (IPNS key → latest CID)
    │
    ▼
ipfs get (downloads content to ~/.claude_karma/remote-sessions/)
    │
    ▼
Dashboard API reads remote-sessions/ → shows in /team page
```

### Setup

**Prerequisites:** Install [Kubo](https://docs.ipfs.tech/install/command-line/) on every machine.

**Private cluster setup:**

1. Generate a swarm key on the owner's machine:
   ```bash
   ipfs-swarm-key-gen > ~/.ipfs/swarm.key
   ```

2. Distribute `swarm.key` to all freelancers (secure channel).

3. Configure each node for private mode:
   ```bash
   ipfs bootstrap rm --all
   ipfs bootstrap add <owner-multiaddr>
   export LIBP2P_FORCE_PNET=1
   ipfs daemon &
   ```

**Initialize karma:**

```bash
# Freelancer
karma init
# Enter user ID, detects Kubo running on :5001

# Owner
karma init
karma team create alpha
karma team add alice <alice-ipns-key>
```

### Daily Workflow

**Freelancer side:**

```bash
# Register a project for syncing
karma project add acme-app --path /Users/alice/work/acme-app

# Push sessions when ready
karma sync acme-app
# Output: Synced 12 sessions → QmXyz...

# Push all configured projects
karma sync --all
```

**Owner side:**

```bash
# Pull sessions from all team members
karma pull
# Resolves IPNS keys → fetches latest CIDs → places in remote-sessions/

# List what's available
karma ls
```

### IPNS Identity

Each freelancer has an IPNS key — a stable identity that points to their latest sync CID. The onboarding exchange:

```
Freelancer:  karma init → generates IPNS key → shares key with owner
Owner:       karma team add alice <ipns-key>
             karma pull → resolves IPNS → fetches sessions
```

### Audit Chain

Every sync records the previous CID in the manifest:

```json
{
  "previous_cid": "QmPreviousSnapshot..."
}
```

This creates an append-only chain. You can walk backwards through CIDs to see the full history of syncs — each snapshot is immutable and tamper-evident.

### IPFS Implementation

The `IPFSClient` in `cli/karma/ipfs.py` wraps the Kubo CLI via subprocess (no Python HTTP client — deliberate choice for reliability):

```python
from karma.ipfs import IPFSClient

client = IPFSClient()
client.is_running()                    # Check Kubo daemon
cid = client.add("/path/to/staging")   # Add directory → CID
client.pin_add(cid)                    # Pin to prevent GC
client.name_publish(cid)               # Publish to IPNS
resolved = client.name_resolve(key)    # Resolve IPNS → CID
client.get(cid, "/output/path")        # Fetch by CID
```

---

## 2. Syncthing Backend

### How It Works

Syncthing provides real-time, automatic file synchronization. Once configured, session packaging and transport happen without any manual commands.

```
Claude Code writes JSONL session
    │
    ▼
SessionWatcher (watchdog) detects file change
    │
    ▼
Debounces for 5 seconds (waits for writes to settle)
    │
    ▼
SessionPackager packages into remote-sessions/{user}/{project}/
    │
    ▼
Syncthing auto-detects change in shared folder
    │
    ▼
Syncthing replicates to owner's machine (TLS encrypted)
    │
    ▼
Data arrives in owner's remote-sessions/ (receiveonly folder)
    │
    ▼
Dashboard API reads remote-sessions/ → shows in /team page
```

### Setup

**Prerequisites:** Install [Syncthing](https://docs.syncthing.net/) on every machine.

**Initialize karma:**

```bash
# Freelancer
karma init --backend syncthing
# Checks Syncthing REST API on :8384
# Reads local device ID
# Prints: "Your Device ID: XXXXXXX-XXXXXXX-..."

# Owner
karma init --backend syncthing
```

**Create a team and pair devices:**

```bash
# Owner creates team
karma team create beta --backend syncthing

# Owner adds freelancer by device ID
karma team add alice XXXXXXX-XXXXXXX-... --team beta

# Freelancer adds owner by device ID
karma team add owner YYYYYYY-YYYYYYY-... --team beta
```

**Register projects and start watching:**

```bash
# Freelancer
karma project add acme-app --path /Users/alice/work/acme-app --team beta
karma watch --team beta
# Watching 1 project for team 'beta'... (Ctrl+C to stop)
```

Sessions are now automatically packaged and synced whenever Claude Code writes to the project directory.

### Daily Workflow

**Freelancer side:**

```bash
# Start the watcher (runs in foreground)
karma watch --team beta
# That's it — sessions sync automatically as you work
```

**Owner side:**

```bash
# Nothing to do — sessions appear automatically in the dashboard
# Check status anytime:
karma status
```

### Syncthing Shared Folders

Syncthing uses folder types to control data flow direction:

| Folder | Path | Freelancer | Owner |
|---|---|---|---|
| `karma-out-{user-id}` | `remote-sessions/{user-id}/` | sendonly | receiveonly |
| `karma-in-{owner-id}` | `sync-inbox/{team}/{owner-id}/` | receiveonly | sendonly |

**sendonly** = this machine writes, others only receive.
**receiveonly** = this machine reads, others write.

### Network Configuration

By default, Syncthing is configured for maximum privacy:

```json
{
  "relaysEnabled": false,
  "globalAnnounceEnabled": false,
  "localAnnounceEnabled": true
}
```

**For remote freelancers** (different networks):
- **Option A:** Open port 22000 (Syncthing's default) on both sides
- **Option B:** Use a VPN (Tailscale, WireGuard) — Syncthing discovers peers over the VPN
- **Option C:** Enable Syncthing relays — data is end-to-end encrypted, the relay cannot read it

### Syncthing Implementation

The `SyncthingClient` in `cli/karma/syncthing.py` wraps Syncthing's REST API:

```python
from karma.syncthing import SyncthingClient

client = SyncthingClient(api_url="http://127.0.0.1:8384", api_key="...")
client.is_running()                          # Check daemon
device_id = client.get_device_id()           # Local device ID
client.add_device("XXXX-...", "alice")       # Pair device
client.add_folder("karma-out-alice", path, devices, "sendonly")
connections = client.get_connections()        # Connected devices
```

The `SessionWatcher` in `cli/karma/watcher.py` uses the `watchdog` library:

```python
from karma.watcher import SessionWatcher

watcher = SessionWatcher(
    watch_dir="~/.claude/projects/-Users-alice-acme/",
    package_fn=my_packaging_callback
)
watcher.start()  # Starts watchdog observer as daemon thread
```

- Monitors recursively for `.jsonl` file changes
- Filters out `agent-*.jsonl` (subagent files handled separately)
- Debounces for 5 seconds before triggering packaging

---

## Shared Components

### Session Packager

Both backends use the same `SessionPackager` (`cli/karma/packager.py`). It discovers and stages session files:

1. Globs `*.jsonl` in the Claude project directory (skips `agent-*.jsonl`, empty files)
2. Copies each session's JSONL file to `staging/sessions/`
3. Copies associated directories (subagents, tool-results) if they exist
4. Finds matching todo files from `~/.claude/todos/`
5. Writes `manifest.json` with session metadata

### Manifest Format

Both backends produce identical `manifest.json`:

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
  ],
  "previous_cid": "Qm..."
}
```

| Field | Description |
|-------|-------------|
| `user_id` | Freelancer's chosen identity (set during `karma init`) |
| `machine_id` | Auto-generated from hostname (distinguishes same user across machines) |
| `sync_backend` | `"ipfs"` or `"syncthing"` (optional, for introspection) |
| `previous_cid` | IPFS only — links to the previous sync snapshot |
| `sessions` | List of session UUIDs with modification time and file size |

### Configuration

All sync config lives at `~/.claude_karma/sync-config.json` (permissions: `0600`):

```json
{
  "user_id": "alice",
  "machine_id": "alice-macbook-pro",
  "teams": {
    "alpha": {
      "backend": "ipfs",
      "projects": { "acme-app": { "path": "/Users/alice/work/acme-app" } },
      "ipfs_members": { "bob": { "ipns_key": "k51..." } },
      "syncthing_members": {}
    },
    "beta": {
      "backend": "syncthing",
      "projects": { "startup": { "path": "/Users/alice/work/startup" } },
      "ipfs_members": {},
      "syncthing_members": { "carol": { "syncthing_device_id": "XXXX-..." } }
    }
  },
  "syncthing": {
    "api_url": "http://127.0.0.1:8384",
    "api_key": "...",
    "device_id": "AAAA-..."
  },
  "ipfs_api": "http://127.0.0.1:5001"
}
```

Teams are isolated — `alpha` uses IPFS while `beta` uses Syncthing, on the same machine.

### Remote Sessions Directory

Both backends place data in the same location for the API to read:

```
~/.claude_karma/remote-sessions/
├── alice/
│   └── -Users-alice-work-acme-app/
│       ├── manifest.json
│       └── sessions/
│           ├── {uuid1}.jsonl
│           ├── {uuid1}/
│           │   ├── subagents/
│           │   └── tool-results/
│           └── {uuid2}.jsonl
└── bob/
    └── ...
```

The API's `/remote/*` endpoints read this directory without knowing which backend produced the files.

---

## API Endpoints

### Sync Status

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/sync/status` | Configuration summary: user, teams, backends |
| GET | `/sync/teams` | Team list with backend type and member details |

### Remote Sessions

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/remote/users` | List all synced users |
| GET | `/remote/users/{user_id}/projects` | User's synced projects |
| GET | `/remote/users/{user_id}/projects/{project}/sessions` | Session list from manifest |
| GET | `/remote/users/{user_id}/projects/{project}/manifest` | Full manifest |

These endpoints are backend-agnostic — they read from `~/.claude_karma/remote-sessions/` regardless of transport.

---

## CLI Reference

All commands are available via the `karma` CLI tool (installed from `cli/`).

### Global Commands

| Command | Description |
|---------|-------------|
| `karma init [--backend ipfs\|syncthing]` | Initialize sync on this machine |
| `karma status` | Show sync configuration and connection state |

### Team Management

| Command | Description |
|---------|-------------|
| `karma team create <name> --backend <type>` | Create a team with a sync backend |
| `karma team add <name> <id> --team <team>` | Add member (IPNS key or device ID) |
| `karma team list` | List all teams and members |
| `karma team remove <name> --team <team>` | Remove a member |

### Project Management

| Command | Description |
|---------|-------------|
| `karma project add <name> --path <path> [--team <team>]` | Register a project for syncing |
| `karma project list` | List configured projects |
| `karma project remove <name>` | Stop syncing a project |

### IPFS-Specific

| Command | Description |
|---------|-------------|
| `karma sync <project>` | Package and publish to IPFS |
| `karma sync --all` | Sync all configured projects |
| `karma pull` | Pull sessions from all team members via IPNS |
| `karma ls` | List available remote sessions |

### Syncthing-Specific

| Command | Description |
|---------|-------------|
| `karma watch --team <team>` | Start filesystem watcher (auto-packages sessions) |

---

## Security

### What Gets Synced

Only explicitly configured project directories. Never global `~/.claude/` config, credentials, or unregistered projects. Freelancers control what they share via `karma project add/remove`.

### Data in Transit

| Backend | Protection |
|---------|------------|
| IPFS | Swarm key encrypts all traffic within the private cluster |
| Syncthing | TLS 1.3 per-connection with device certificate authentication |

### Data at Rest

Neither backend encrypts data at rest by default. The config file (`sync-config.json`) is written with `0600` permissions. Session data may contain sensitive code — keep the `remote-sessions/` directory protected.

### Path Traversal Protection

The API validates all paths in remote sessions:
- Rejects `..` components
- Validates filenames with regex
- Checks resolved paths stay inside the output directory
- Skips symlinks

---

## Onboarding Cheat Sheet

### IPFS Team

```
Owner                                Freelancer
─────                                ──────────
1. Set up private IPFS cluster       1. Install Kubo
   (swarm key, bootstrap)               Import swarm key
2. karma init                        2. karma init
3. karma team create alpha           3. Share IPNS key ──────►
4. karma team add alice <key>
                                     4. karma project add app --path /work/app
                                     5. karma sync app
5. karma pull
6. Sessions in dashboard!
```

### Syncthing Team

```
Owner                                Freelancer
─────                                ──────────
1. Install Syncthing                 1. Install Syncthing
2. karma init --backend syncthing    2. karma init --backend syncthing
3. karma team create beta
   --backend syncthing
4. Share device ID ◄────────────────► 3. Share device ID
5. karma team add alice <device-id>  4. karma team add owner <device-id>
   --team beta                          --team beta
                                     5. karma project add app --path /work/app
                                        --team beta
                                     6. karma watch --team beta
6. Sessions appear automatically!
```
