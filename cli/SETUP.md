# Private IPFS Cluster Setup Guide

This guide walks you through setting up a private IPFS cluster for Claude Karma session syncing.

## Prerequisites

- Each participant (freelancer + project owner) needs a machine with ~100MB free disk space
- All participants must be reachable on the same network (or via port forwarding)

## 1. Install Kubo (IPFS)

### macOS
```bash
brew install ipfs
```

### Windows
```bash
choco install ipfs
# or
scoop install kubo
```

### Linux (Debian/Ubuntu)
```bash
wget https://dist.ipfs.tech/kubo/v0.28.0/kubo_v0.28.0_linux-amd64.tar.gz
tar -xvzf kubo_v0.28.0_linux-amd64.tar.gz
cd kubo && sudo bash install.sh
```

### Verify installation
```bash
ipfs --version
# Expected: ipfs version 0.28.0 (or newer)
```

## 2. Initialize IPFS

```bash
ipfs init
```

## 3. Generate Swarm Key (Project Owner Only)

The swarm key makes the IPFS network **private** — only nodes with this key can connect.

```bash
# Install the key generator
go install github.com/Kubuxu/go-ipfs-swarm-key-gen/ipfs-swarm-key-gen@latest

# Generate the key
ipfs-swarm-key-gen > ~/.ipfs/swarm.key
```

If you don't have Go installed, you can generate a key with Python:
```bash
python3 -c "
import secrets
print('/key/swarm/psk/1.0.0/')
print('/base16/')
print(secrets.token_hex(32))
" > ~/.ipfs/swarm.key
```

## 4. Distribute Swarm Key

Send the `~/.ipfs/swarm.key` file to **all team members** via a secure channel (encrypted message, not email).

Each team member places the file at `~/.ipfs/swarm.key`.

## 5. Configure Bootstrap Nodes

Remove the default public bootstrap nodes and add the project owner's node:

```bash
# On EVERY participant's machine:
ipfs bootstrap rm --all

# Get the owner's peer address:
# (run on owner's machine)
ipfs id
# Look for the address like: /ip4/<IP>/tcp/4001/p2p/<PeerID>

# On every other machine, add the owner as bootstrap:
ipfs bootstrap add /ip4/<OWNER_IP>/tcp/4001/p2p/<OWNER_PEER_ID>
```

## 6. Force Private Network

Set the environment variable to enforce private networking:

```bash
# Add to your shell profile (~/.bashrc, ~/.zshrc, etc.)
export LIBP2P_FORCE_PNET=1
```

## 7. Start the IPFS Daemon

```bash
ipfs daemon &
```

Verify the private cluster works:
```bash
# On any participant's machine:
ipfs swarm peers
# Should show the owner's peer (and other team members)
```

## 8. Install and Configure Karma CLI

```bash
# From the claude-karma repository:
cd cli
pip install -e .

# Initialize (each participant):
karma init
# Enter your user ID when prompted

# Add a project to sync:
karma project add my-project --path /path/to/your/project
```

## 9. Onboarding a New Team Member

### Freelancer does:
```bash
karma init --user-id alice
# Note the IPNS key printed (or run: ipfs key list -l)
# Share the IPNS key with the project owner
```

### Project owner does:
```bash
karma team add alice <alice-ipns-key>
```

## 10. Daily Workflow

### Freelancer (after a work session):
```bash
karma sync my-project
# Output: Synced 12 sessions (3 new) -> QmXyz...
```

### Project owner (to review work):
```bash
karma pull
# Fetches latest sessions from all team members
```

Then open the Karma dashboard at http://localhost:5173/team to view remote sessions.

## Troubleshooting

### "IPFS daemon not running"
```bash
ipfs daemon &
# Wait a few seconds, then retry
```

### No peers showing
- Verify swarm key is identical on all machines (`md5 ~/.ipfs/swarm.key`)
- Check firewall allows TCP port 4001
- Ensure `LIBP2P_FORCE_PNET=1` is set

### Sync is slow
- IPNS publishing can take 30-60 seconds. This is normal for the first publish.
- Subsequent syncs with incremental changes are faster.
