# Syncing Sessions with Your Team

How to share Claude Code sessions across machines and teams.

## Why sync sessions?

Claude Code Karma reads from `~/.claude/` on your local machine. If you have freelancers or team members, each person has their own machine with their own `~/.claude/` directory.

Syncing solves this. Freelancers share their sessions with you automatically. You see everything in one unified dashboard. They control what gets shared.

## How Syncthing sync works

Syncthing is a tool that automatically syncs files between machines. Once set up, new sessions are packaged and synced without any manual commands.

**The flow:**
1. Claude Code writes a new session JSONL file
2. `karma watch` detects the new file
3. Sessions are packaged into `~/.claude_karma/remote-sessions/`
4. Syncthing auto-syncs to other team members' machines (encrypted)
5. Their dashboards show the sessions

No manual commands needed. It just happens.

## Setup

### Prerequisites

Everyone needs [Syncthing](https://syncthing.net/downloads/) installed.

### Step 1: Initialize Karma

Everyone runs this once:

```bash
karma init
```

You'll be prompted for your user ID (e.g., your name). Karma checks if Syncthing is running and reads your device ID.

You'll see:
```
Your Syncthing Device ID: AAAA-BBBB-CCCC-DDDD-EEEE-FFFF-GGGG-HHHH
```

Save this. You'll share it with your team.

### Step 2: Create a Team

The project owner creates a team:

```bash
karma team create alpha
```

Then adds the freelancer by device ID:

```bash
karma team add alice XXXX-YYYY-ZZZZ-WWWW-...
```

The freelancer does the same on their machine:

```bash
karma team add owner AAAA-BBBB-CCCC-DDDD-...
```

(Use the owner's device ID from their `karma init` output.)

### Step 3: Register Projects

The freelancer registers the project they're working on:

```bash
karma project add acme-app --path /Users/alice/work/acme-app --team alpha
```

### Step 4: Start the Watcher

The freelancer starts the watcher:

```bash
karma watch --team alpha
```

This runs in the foreground. Sessions sync automatically while it's running. Press Ctrl+C to stop.

## Daily workflow

### For the freelancer

Start the watcher when you begin working:

```bash
karma watch --team alpha
```

Keep it running in a terminal. Sessions sync automatically as you work. Press Ctrl+C when done.

### For the owner

Nothing to do. Sessions appear automatically in your Karma dashboard on the **Team** page.

Check status anytime:

```bash
karma status
```

## Network setup

By default, Syncthing only works on the same local network (LAN).

### Local teams (same network)

Syncthing works out of the box.

### Remote teams (different networks)

**Option A: Open a port**

Open port 22000 on both machines and give Syncthing the public IP. Syncthing connects directly.

**Option B: Use a VPN**

Put everyone on a VPN (Tailscale, WireGuard, etc). Syncthing discovers peers over the VPN.

**Option C: Use Syncthing relays**

Enable Syncthing relays. Data is end-to-end encrypted; relays can't read it. Go to `localhost:8384` (Syncthing's UI) and enable relays in Settings.

## CLI Reference

Install the CLI first:

```bash
pip install -e cli/karma/
```

### Initialization

| Command | What |
|---------|------|
| `karma init` | Initialize on this machine |

### Teams

| Command | What |
|---------|------|
| `karma team create <name>` | Create a team |
| `karma team add <name> <device-id> --team <team>` | Add a member |
| `karma team list` | List teams and members |
| `karma team remove <name> --team <team>` | Remove a member |
| `karma team leave <name>` | Leave and clean up |

### Projects

| Command | What |
|---------|------|
| `karma project add <name> --path <path> --team <team>` | Register a project |
| `karma project list` | List registered projects |
| `karma project remove <name>` | Stop syncing |

### Syncing

| Command | What |
|---------|------|
| `karma watch --team <team>` | Start auto-sync (keep running) |
| `karma accept` | Accept pending folder offers |
| `karma ls` | List remote sessions |
| `karma status` | Check sync status |

## Configuration

All sync config is stored at `~/.claude_karma/sync-config.json`:

```json
{
  "user_id": "alice",
  "machine_id": "alice-macbook",
  "teams": {
    "alpha": {
      "projects": {
        "acme-app": {
          "path": "/Users/alice/work/acme-app"
        }
      },
      "syncthing_members": {
        "owner": {
          "syncthing_device_id": "AAAA-BBBB-..."
        }
      }
    }
  },
  "syncthing": {
    "api_url": "http://127.0.0.1:8384",
    "api_key": "...",
    "device_id": "AAAA-BBBB-..."
  }
}
```

This file is private (mode 0600). It's created during `karma init`.

## Security

### What gets synced

Only projects you explicitly register with `karma project add`. Everything else stays local.

### In transit

Syncthing uses TLS 1.3 with certificate authentication. All data is encrypted.

### At rest

Syncthing doesn't encrypt data at rest. Keep your `remote-sessions/` directory protected. Session files may contain sensitive code.

## Onboarding checklist

### For the owner

- [ ] Install Syncthing
- [ ] Run `karma init`
- [ ] Create a team: `karma team create alpha`
- [ ] Share your device ID with the freelancer
- [ ] Add the freelancer: `karma team add alice <device-id>`
- [ ] Sessions appear in the **Team** page

### For the freelancer

- [ ] Install Syncthing
- [ ] Run `karma init`
- [ ] Add the owner: `karma team add owner <device-id>`
- [ ] Register your project: `karma project add app --path /work/app --team alpha`
- [ ] Start the watcher: `karma watch --team alpha`
- [ ] Keep it running while you work

That's it. No manual commands. Sessions sync automatically.

## Troubleshooting

**"Team not found" error**

Make sure the team exists. Check with `karma team list`. If it doesn't exist, run `karma team create <name>`.

**"Syncthing not running" error**

Start Syncthing. It runs as a background service or tray application depending on your OS.

**Sessions not syncing**

1. Make sure `karma watch` is running: `karma status`
2. Check Syncthing is running: `localhost:8384`
3. Verify folders are paired (both devices should see them in Syncthing UI)
4. Check network connectivity between machines

**"Project not found" error**

Register the project first: `karma project add <name> --path <path> --team <team>`

**Syncthing folders not appearing**

Run `karma accept` to accept pending folder offers from team members.
