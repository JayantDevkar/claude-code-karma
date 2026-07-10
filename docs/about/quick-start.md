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

Share sessions with your team — no cloud, no accounts, fully peer-to-peer.

```bash
# 1. Install Syncthing on each machine
#    macOS: brew install syncthing && brew services start syncthing
#    Linux: sudo apt install syncthing && systemctl --user enable --now syncthing

# 2. Open the Karma dashboard and go to /sync
#    The setup wizard walks you through picking your user ID
#    and detecting Syncthing automatically.

# 3. Create a team on the /team page
#    Click "Create Team" and give it a name like "alpha"

# 4. Add teammates via join codes
#    Your teammate generates a join code from their /sync page.
#    You paste it on the Team page to add them.

# 5. Share projects
#    Pick which projects to share with the team.
#    Each member gets a subscription they can accept, pause, or decline.
```

Sessions are packaged and synced automatically. Teammates' sessions appear in your dashboard within seconds on LAN, or a few minutes over the internet.

See [Syncing Sessions](syncing-sessions.md) for the full walkthrough.

## Next Steps

- [Features](features.md) — See what you can do
- [Architecture](architecture.md) — Understand how it works
- [Hooks Guide](hooks-guide.md) — Set up real-time tracking
- [Syncing Sessions](syncing-sessions.md) — Share with your team
