# Quick Start

Get Claude Code Karma running in under 5 minutes.

## Prerequisites

| Requirement | Minimum Version |
|-------------|-----------------|
| Python | 3.9+ |
| Node.js | 18+ |
| npm | 7+ |
| Git | 2.x |

You must also have Claude Code installed and have existing sessions in `~/.claude/projects/`.

## 1. Clone the Repository

```bash
git clone https://github.com/JayantDevkar/claude-code-karma.git
cd claude-code-karma
```

## 2. Start the API

```bash
cd api
pip install -e ".[dev]" && pip install -r requirements.txt
uvicorn main:app --reload --port 8000
```

The API server starts at `http://localhost:8000`. It automatically discovers and parses session files from `~/.claude/projects/`.

Verify the API is running:

```bash
curl http://localhost:8000/health
```

## 3. Start the Frontend

In a separate terminal:

```bash
cd frontend
npm install
npm run dev
```

The dashboard opens at `http://localhost:5173`.

## 4. Verify

Open [http://localhost:5173](http://localhost:5173) in your browser. You should see your Claude Code projects listed with their sessions.

## Optional: Enable Live Session Tracking

Claude Code Karma includes hook scripts that track sessions in real time. To enable live tracking:

1. Copy or symlink the hook scripts from `hooks/` to `~/.claude/hooks/`
2. Register them in your Claude Code `settings.json`

Live tracking provides real-time session state (STARTING, LIVE, WAITING, STOPPED, ENDED) and automatic session title generation.

See the [Hooks Guide](hooks-guide.md) for detailed setup instructions.

## Optional: Enable Session Sync (IPFS or Syncthing)

Claude Code Karma supports sharing sessions across machines and teams. Choose one sync backend:

### For Teams with Syncthing (Recommended for Small Teams)

**Prerequisites:**
- Install [Syncthing](https://syncthing.net/) on each team member's machine

**Setup:**

```bash
# Install the CLI tool
pip install -e cli/karma/

# Initialize on your machine
karma init --backend syncthing

# You'll see your Syncthing Device ID. Share this with your project owner.
# They'll do: karma team add you <your-device-id>

# Create a team
karma team create alpha --backend syncthing

# Add a project to sync
karma project add acme-app --path /Users/you/work/acme-app --team alpha

# Start the automatic watcher
karma watch --team alpha
```

Now sessions are automatically packaged and synced via Syncthing. View remote sessions in the dashboard under the **Teams** page.

### For Larger Teams with IPFS

**Prerequisites:**
- Install [Kubo (IPFS)](https://docs.ipfs.tech/install/command-line/)
- Start the IPFS daemon: `ipfs daemon &`

**Setup:**

```bash
# Install the CLI tool
pip install -e cli/karma/

# Initialize on your machine
karma init --backend ipfs

# Create a team
karma team create alpha --backend ipfs

# Add a project to sync
karma project add acme-app --path /Users/you/work/acme-app --team alpha

# Sync when ready
karma sync acme-app

# Pull sessions from team members
karma team add alice <their-ipns-key>
karma pull
```

View remote sessions in the dashboard under the **Teams** page.

### Check Sync Status

```bash
karma status
karma ls
```

## Next Steps

- [Features](features.md) — Explore the full feature set
- [Architecture](architecture.md) — Understand how Claude Code Karma works
- [API Reference](api-reference.md) — Browse all API endpoints
