# Syncing Sessions

Share Claude Code sessions across your machines and with your team — no cloud, no accounts, no servers.

## The problem

Claude Code Karma reads from `~/.claude/` on your local machine. That's great for solo use, but the moment you have two machines or a teammate, each person's sessions are invisible to everyone else.

You lose context. You duplicate work. You can't learn from how your teammates use Claude.

## The solution: peer-to-peer sync

We use **Syncthing** — an open-source, encrypted, peer-to-peer file sync tool. There's no central server. Sessions travel directly from one machine to another. Your data stays entirely under your control.

Think of it like AirDrop for Claude sessions, but it works across the internet too.

## Three concepts you need to know

Everything in Karma sync is built on three ideas: **you**, **teams**, and **projects**.

### 1. You (the Member)

Every person + machine combination is a unique **member**. Your identity looks like this:

```
jayant.macbook
  ↑        ↑
  you    your machine
```

Why per-machine? Because your sessions are machine-specific. If you're "jayant" on a MacBook and also "jayant" on a desktop, those are two separate members with separate session outboxes. Same person, different machines, different sessions.

You choose your `user_id` once (your name, no dots). The `machine_tag` is auto-detected from your hostname.

### 2. Teams (who can see your stuff)

A **team** is a group of members who can see each other's sessions. That's all it is — an access control list.

```
Team "backend-crew"
├── jayant.macbook    (creator)
├── ayush.laptop
└── priya.desktop
```

Teams don't own data. They don't store anything. They just answer the question: "who should get a copy of my sessions?"

You can be in multiple teams. A freelancer might be in a team with Client A and a separate team with Client B. Sessions shared with Team A are invisible to Team B.

**Creator privilege:** only the person who created the team can remove members. This prevents accidental or unauthorized removals.

### 3. Projects (what gets shared)

You choose which **projects** to share with each team. A project is just a directory you've used Claude Code in — Karma identifies it by its git remote (like `org/repo`).

```
Team "backend-crew" shares:
├── claude-karma     (jayantdevkar/claude-karma)
└── api-gateway      (acme/api-gateway)
```

Sharing is per-project, per-team. You might share `claude-karma` with your team but keep `personal-notes` private. You're always in control of what gets shared.

## How sessions flow

Here's what happens when you use Claude Code with sync enabled:

```
  YOUR MACHINE                                    TEAMMATE'S MACHINE
 ┌─────────────────────┐                          ┌─────────────────────┐
 │                     │                          │                     │
 │  You use Claude     │                          │                     │
 │  Code on a project  │                          │                     │
 │        │            │                          │                     │
 │        ▼            │                          │                     │
 │  Session saved to   │                          │                     │
 │  ~/.claude/         │                          │                     │
 │        │            │                          │                     │
 │        ▼            │                          │                     │
 │  Watcher detects    │                          │                     │
 │  the new session    │                          │                     │
 │        │            │                          │                     │
 │        ▼            │      Syncthing P2P       │                     │
 │  Packaged into      │      (encrypted,         │  Session appears    │
 │  YOUR OUTBOX     ───┼──── automatic) ──────────┼──► in THEIR INBOX   │
 │                     │                          │        │            │
 │                     │                          │        ▼            │
 │                     │                          │  Shows up in their  │
 │                     │                          │  Karma dashboard    │
 │                     │                          │                     │
 │  Their session      │      Syncthing P2P       │  They use Claude    │
 │  appears in     ◄───┼──── (encrypted,  ◄───────┼── Code too, session │
 │  YOUR INBOX         │      automatic)          │  goes to THEIR      │
 │        │            │                          │  OUTBOX             │
 │        ▼            │                          │                     │
 │  Shows up in your   │                          │                     │
 │  Karma dashboard    │                          │                     │
 │                     │                          │                     │
 └─────────────────────┘                          └─────────────────────┘
```

**Key insight:** your outbox and their inbox are the *same folder*. You create it as "send-only"; they add it as "receive-only". Syncthing handles the rest. No copying, no uploading — files just appear.

## The folder model

Karma creates three types of Syncthing folders automatically. You never have to manage these — they're invisible plumbing.

| Type | What it does | Example |
|------|-------------|---------|
| **Outbox** | Your sessions → teammates (send-only) | `karma-out--jayant.macbook--org-repo` |
| **Inbox** | Teammate's sessions → you (receive-only) | `karma-out--ayush.laptop--org-repo` |
| **Metadata** | Team member list & signals (shared) | `karma-meta--backend-crew` |

Notice that "outbox" and "inbox" have the same naming pattern (`karma-out--{member}--{project}`). That's because they're the same folder seen from different sides. Jayant's outbox IS ayush's inbox for that project.

The **metadata folder** is how members discover each other. Each device writes a small JSON file with its identity. When a new member joins, everyone else picks up their info from the metadata folder automatically — no central coordinator needed.

## Multiple teams, one outbox

Here's where it gets clever. If you're in two teams that both share the same project, Karma doesn't create two outboxes. It creates ONE outbox and expands the device list:

```
Team A shares "claude-karma":  members = {jayant, ayush, priya}
Team B shares "claude-karma":  members = {jayant, bob, charlie}
                                          ↓
Jayant's outbox device list = {ayush, priya, bob, charlie}
```

This is the **"project channels" model**. Sessions belong to projects, not teams. Teams just decide who has access. This avoids duplicating session data and keeps things efficient.

When jayant leaves Team B, only Team B's devices (bob, charlie) are removed from the outbox. Team A's devices stay. No data is lost.

## What gets synced (and what doesn't)

**Synced:**
- Session conversations and messages
- Tool usage and token statistics
- Session metadata and timelines
- Subagent activity

**Never synced:**
- Your source code
- Secrets, credentials, or `.env` files
- Files outside `~/.claude/projects/`
- Anything from projects you haven't explicitly shared

## The lifecycle

### Getting started (one-time)

```
1. Install Syncthing        →  brew install syncthing (macOS)
2. Open Karma → /sync       →  The setup wizard walks you through it
3. Pick your user_id        →  Your name, like "jayant"
4. Machine tag auto-detects →  From your hostname, like "macbook"
```

### Creating a team

```
1. Create team              →  Give it a name like "backend-crew"
2. Get a join code          →  A short code like "backend-crew:jayant:DEVICE-ID"
3. Share the code           →  Send it to your teammate via Slack, email, anything
```

### Joining a team

```
1. Enter the join code      →  Paste what your teammate sent you
2. Devices pair             →  Automatic, encrypted handshake
3. Pick projects to share   →  Select which local projects to sync
4. Sessions start flowing   →  Within seconds on LAN, minutes over internet
```

### Day to day

Nothing. It just works. Karma's watcher runs in the background, packaging new sessions and syncing them automatically. Sessions from teammates appear in your dashboard.

## Settings you can tweak

| Setting | What it does | Default |
|---------|-------------|---------|
| **Sync direction** | Send only, receive only, both, or none | Both |
| **Session limit** | Sync all sessions, recent 100, or recent 10 | All |
| **Auto-accept members** | Automatically accept new team members | Off |
| **Project subscription** | Opt out of receiving specific projects | Everything |

Settings cascade: you can set them per-member, per-team, or per-device. The most specific setting wins.

## Security model

### In transit
All transfers use **TLS 1.3** with mutual certificate authentication. Only devices you've explicitly paired can connect. Even Syncthing's relay servers (used when devices can't connect directly) see only encrypted blobs.

### At rest
Session files are stored unencrypted on disk. Protect your `~/.claude_karma/` directory with standard filesystem permissions (mode 0700 by default).

### Access control
- Only the team **creator** can remove members
- Removed members are notified via a removal signal in the metadata folder
- Removed members auto-leave and their data is cleaned up
- You can reject (unsubscribe from) specific projects per team

### What Karma manages for you
- Device pairing and folder creation
- Member discovery via metadata folders
- Automatic cleanup when leaving teams
- Folder device lists (who can sync what)

You never touch Syncthing directly — Karma handles all of it through Syncthing's REST API.

## Network setup

### Same network (LAN)
Works out of the box. Syncthing discovers peers automatically. Sync is near-instant.

### Different networks (internet)
Three options:

1. **Syncthing relays** (easiest) — Enabled by default. Data is end-to-end encrypted; relays can't read it. Slightly slower.
2. **VPN** (Tailscale, WireGuard) — Put everyone on a VPN. Syncthing discovers peers over the VPN as if they were on the same LAN.
3. **Port forwarding** — Open port 22000. Syncthing connects directly. Fastest, but requires router config.

## Troubleshooting

**Sessions not appearing?**
- Check that the watcher is running (`/sync` page shows status)
- Verify both devices are online in Syncthing (`localhost:8384`)
- Make sure the project is shared with the team

**"Syncthing not detected"?**
- Install Syncthing and start it as a background service
- macOS: `brew install syncthing && brew services start syncthing`
- Linux: `sudo apt install syncthing && systemctl --user enable --now syncthing`

**Teammate's sessions not syncing?**
- Both machines need the project shared with the same team
- Check pending folders on the `/sync` page — you may need to accept new folders
- Verify network connectivity between machines

**Want to stop sharing a project?**
- Remove the project from the team on the `/sync` page
- Sessions already synced remain on teammates' machines (they're copies)
