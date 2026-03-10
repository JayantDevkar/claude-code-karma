# Quick Start

Get Claude Code Karma running in 5 minutes.

## Prerequisites

- Python 3.9+
- Node.js 18+
- npm 7+
- Git 2.x
- Claude Code installed with existing sessions in `~/.claude/projects/`

## 1. Clone

```bash
git clone https://github.com/JayantDevkar/claude-code-karma.git
cd claude-code-karma
```

## 2. Start the API

In terminal 1:

```bash
cd api
pip install -e ".[dev]" && pip install -r requirements.txt
uvicorn main:app --reload --port 8000
```

The API server starts at `http://localhost:8000`. It automatically discovers sessions from `~/.claude/projects/`.

Verify it's running:

```bash
curl http://localhost:8000/health
```

## 3. Start the Frontend

In terminal 2:

```bash
cd frontend
npm install
npm run dev
```

The dashboard opens at `http://localhost:5173`. You should see your Claude Code projects listed with their sessions.

That's it. You're done.

## Optional: Enable Real-Time Session Tracking

To watch active sessions as they happen, you need to install hooks.

```bash
# Copy or symlink the hook scripts
ln -s /path/to/claude-karma/hooks/live_session_tracker.py ~/.claude/hooks/
ln -s /path/to/claude-karma/hooks/session_title_generator.py ~/.claude/hooks/

# Register them in ~/.claude/settings.json
# See Hooks Guide for the full settings.json structure
```

This enables:
- Real-time session state (STARTING, LIVE, WAITING, STOPPED, ENDED)
- Automatic session titles based on git commits or AI generation

See [Hooks Guide](hooks-guide.md) for detailed setup.

## Optional: Enable Session Sync with Syncthing

To share sessions with your team via Syncthing:

```bash
# Install Syncthing on each machine
# https://syncthing.net/downloads/

# Install the CLI tool
pip install -e cli/karma/

# Initialize on your machine
karma init

# You'll see your Syncthing Device ID. Share it with your team lead.

# Create a team
karma team create alpha

# Add a team member
karma team add alice <their-device-id>

# Register a project
karma project add acme-app --path /Users/you/work/acme-app --team alpha

# Start the watcher (keeps running, syncs automatically)
karma watch --team alpha
```

Sessions are packaged and synced automatically. Check the Teams page in the dashboard to see remote sessions.

See [Syncing Sessions](syncing-sessions.md) for full details.

## Next Steps

- [Features](features.md) — See what you can do
- [Architecture](architecture.md) — Understand how it works
- [Hooks Guide](hooks-guide.md) — Set up real-time tracking
- [Syncing Sessions](syncing-sessions.md) — Share with your team
