# Claude Karma Setup

> Step-by-step guide for installing and configuring Claude Karma — a dashboard for monitoring and analyzing Claude Code sessions. Designed for both humans and AI agents (Claude Code, etc.).

---

## What You'll Get

Claude Karma installs in **3 progressive tiers**. Start with the core dashboard, then add live monitoring and smart titles as needed.

| Tier | Components | Dashboard Features | Installation Time |
|------|-----------|-------------------|-------------------|
| **1: Core Dashboard** | API + Frontend | Browse projects, view sessions, analytics | ~5 min |
| **2: Live Monitoring** | + Live Tracker Hook | Real-time session indicators, recently ended | +2 min |
| **3: Smart Titles** | + Title Generator Hook | Human-readable session names | +2 min |

**You can stop after Tier 1.** Tiers 2 and 3 are optional enhancements installed independently.

---

## Prerequisites

Verify you have the required tools:

```bash
# Required
python3 --version    # 3.10+
node --version       # 18+
npm --version        # 7+
git --version        # any version

# Required (must have Claude Code sessions)
ls ~/.claude/projects/    # Should show encoded project directories

# Optional (for smart titles via Claude Haiku)
claude --version     # Claude CLI (any version)
```

| Tool | Minimum | Required? | Why |
|------|---------|-----------|-----|
| Python | 3.10+ | Yes | API backend runs on Python |
| Node.js | 18+ | Yes | Frontend build system |
| npm | 7+ | Yes | Frontend package manager |
| Git | Any | Yes | Clone repository |
| Claude Code | 2.1.19+ | For Tier 2 subagent tracking | Track subagent spawning |
| Claude CLI | Any | For Tier 3 smart titles | Generate titles via Haiku |

---

## Tier 1: Core Dashboard (Required)

### Step 1: Clone the Repository

**What:** Download the Claude Karma repository.
**Why:** Gets all components — API, frontend, and hook scripts — in one go.

```bash
git clone https://github.com/JayantDevkar/claude-karma.git
cd claude-karma
```

**Verify:**
```bash
ls api/main.py frontend/package.json hooks/live_session_tracker.py
```
All three files must exist.

> **Agent notes:** Confirm all three files exist. If `api/` or `frontend/` are empty, the clone may have failed — re-clone.

---

### Step 2: Start the API

**What:** Launch the FastAPI backend on port 8000.
**Why:** Parses Claude Code sessions and serves the REST API that the frontend consumes.

**Working directory:** `cd api`

**Install dependencies:**
```bash
# Option A: System Python (fastest)
pip install -r requirements.txt

# Option B: Virtual environment (recommended for isolation)
python3 -m venv venv
source venv/bin/activate  # or: venv\Scripts\activate on Windows
pip install -r requirements.txt
```

**Start the server:**
```bash
uvicorn main:app --reload --port 8000
```

**On first startup, the API will:**
1. Create `~/.claude_karma/` directory
2. Create `~/.claude_karma/metadata.db` (SQLite metadata index)
3. Start background thread to index all sessions from `~/.claude/projects/`
4. Become available at `http://localhost:8000`

**Verify:**
```bash
curl http://localhost:8000/health
```

Expected response:
```json
{"status": "healthy", "sqlite": {"ready": true, "session_count": <number>}}
```

The `session_count` should match the number of Claude Code sessions you have. If it's 0, ensure you have sessions in `~/.claude/projects/`.

**To disable SQLite** (slower but functional):
```bash
CLAUDE_KARMA_USE_SQLITE=false uvicorn main:app --reload --port 8000
```

> **Agent notes:** Check health endpoint returns `session_count > 0`. If 0, user may not have any Claude Code sessions yet. Ask them to create a test session first.

---

### Step 3: Start the Frontend

**What:** Launch the SvelteKit frontend on port 5173.
**Why:** Provides the web dashboard UI that connects to the API.

**In a second terminal**, run:

```bash
cd frontend

# Install dependencies
npm install

# Start the dev server
npm run dev
```

The frontend starts at **http://localhost:5173** and automatically connects to the API at `http://localhost:8000`.

**Custom API URL** (if API runs on a different host/port):
```bash
PUBLIC_API_URL=http://your-api-host:8000 npm run dev
```

Or create `frontend/.env`:
```
PUBLIC_API_URL=http://localhost:8000
```

**Verify:**
Open http://localhost:5173 in your browser. You should see the Claude Karma home page with navigation cards (Projects, Analytics, Agents, etc.).

> **Agent notes:** Confirm browser loads homepage. Check browser console for any errors. If CORS errors appear, verify API is running and accessible.

---

### Step 4: Verify Core Dashboard

**What:** Test that the dashboard works end-to-end.
**Why:** Ensures all core features are accessible before adding optional hooks.

**Working features at this point:**

| Feature | Route | Status |
|---------|-------|--------|
| Home page with navigation | `/` | Works |
| Browse all projects | `/projects` | Works |
| Project detail with sessions | `/projects/[name]` | Works |
| Session detail and conversation | `/projects/[name]/[session]` | Works |
| Session timeline | Session detail → Timeline | Works |
| Tool usage analytics | Session detail → Tools | Works |
| Agent usage analytics | `/agents` | Works |
| Skill usage analytics | `/skills` | Works |
| Analytics dashboard | `/analytics` | Works |
| Plans browser | `/plans` | Works |
| Settings management | `/settings` | Works |
| Archived sessions | Via filters | Works |
| Command palette | Ctrl+K | Works |

**Features that require hooks (next tiers):**

| Feature | Missing Component |
|---------|-------------------|
| Live session indicators | Tier 2 hook |
| Recently ended sessions | Tier 2 hook |
| Human-readable titles | Tier 3 hook |
| Subagent tracking | Tier 2 hook |

**Quick test:**
1. Click "Projects" — you should see your Claude Code projects
2. Click a project — you should see sessions with stats
3. Click a session — you should see the conversation

> **Agent notes:** If any core feature fails, check API health (`curl http://localhost:8000/health`) and browser console for errors. Do NOT proceed to Tier 2 until core works.

**You can stop here.** The full historical dashboard works. Proceed to Tier 2 only if you want real-time monitoring.

---

## Tier 2: Live Monitoring (Recommended)

Adds real-time session tracking — see which Claude Code sessions are active, waiting, idle, or recently ended.

### Step 5: Install the Live Session Tracker Hook

**What:** Add a hook that tracks session state in real-time.
**Why:** Enables live indicators (green pulsing dots) and "Recently Ended" sessions on the dashboard.
**Requires:** Nothing additional running — writes directly to `~/.claude_karma/live-sessions/`.

**Install the script:**

Choose ONE method:

**Symlink (recommended for development):**
```bash
mkdir -p ~/.claude/hooks
ln -sf "$(cd hooks && pwd)/live_session_tracker.py" ~/.claude/hooks/live_session_tracker.py
chmod +x hooks/live_session_tracker.py
```

**Copy (for standalone installation):**
```bash
mkdir -p ~/.claude/hooks
cp hooks/live_session_tracker.py ~/.claude/hooks/
chmod +x ~/.claude/hooks/live_session_tracker.py
```

**Verify the script exists:**
```bash
ls -la ~/.claude/hooks/live_session_tracker.py
```

> **Agent notes:** Confirm symlink or copy succeeded. Script must be executable. Test with: `python3 ~/.claude/hooks/live_session_tracker.py < /dev/null` (should exit cleanly, may print help).

---

### Step 6: Register Hook Events

**What:** Register the tracker to listen for Claude Code events.
**Why:** Tells Claude Code to call the tracker when sessions start, change state, or end.

The tracker must be registered for **8 hook events** in `~/.claude/settings.json`:

| Hook Event | Tracks |
|-----------|--------|
| `SessionStart` | New or resumed session |
| `UserPromptSubmit` | User submitted prompt, actively processing |
| `PostToolUse` | Tool completed |
| `Notification` | Waiting for user input |
| `Stop` | Agent finished |
| `SubagentStart` | Subagent spawned (requires Claude Code 2.1.19+) |
| `SubagentStop` | Subagent finished (requires Claude Code 2.1.19+) |
| `SessionEnd` | Session terminated |

**Add this to `~/.claude/settings.json`:**

```json
{
  "hooks": {
    "SessionStart": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "python3 ~/.claude/hooks/live_session_tracker.py",
            "timeout": 5000
          }
        ]
      }
    ],
    "UserPromptSubmit": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "python3 ~/.claude/hooks/live_session_tracker.py",
            "timeout": 5000
          }
        ]
      }
    ],
    "PostToolUse": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "python3 ~/.claude/hooks/live_session_tracker.py",
            "timeout": 5000
          }
        ]
      }
    ],
    "Notification": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "python3 ~/.claude/hooks/live_session_tracker.py",
            "timeout": 5000
          }
        ]
      }
    ],
    "Stop": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "python3 ~/.claude/hooks/live_session_tracker.py",
            "timeout": 5000
          }
        ]
      }
    ],
    "SubagentStart": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "python3 ~/.claude/hooks/live_session_tracker.py",
            "timeout": 5000
          }
        ]
      }
    ],
    "SubagentStop": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "python3 ~/.claude/hooks/live_session_tracker.py",
            "timeout": 5000
          }
        ]
      }
    ],
    "SessionEnd": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "python3 ~/.claude/hooks/live_session_tracker.py",
            "timeout": 5000
          }
        ]
      }
    ]
  }
}
```

> **Important:** Timeout values are in **milliseconds** for command hooks (5000 = 5 seconds). If you already have a `"hooks"` key in settings.json, merge these entries into it rather than overwriting.

**Verify:**
```bash
# Check settings.json was updated
grep -A2 '"SessionStart"' ~/.claude/settings.json

# Test the hook manually
echo '{"hook_event_name":"SessionStart","session_id":"test-123","cwd":"/tmp","transcript_path":"/tmp/test.jsonl"}' \
  | python3 ~/.claude/hooks/live_session_tracker.py

# Check state file was written
ls ~/.claude_karma/live-sessions/
```

> **Agent notes:** Confirm settings.json has all 8 events. Test manual invocation — should not error. Check live-sessions directory exists after test.

---

### Step 7: Verify Live Tracking

**What:** Confirm the tracker is working in real-time.
**Why:** Live indicators won't show up unless the tracker is being called by Claude Code.

**Test:**
1. Start a new Claude Code session (or resume an existing one)
2. Check for state file: `ls ~/.claude_karma/live-sessions/`
3. Refresh the dashboard at http://localhost:5173
4. You should see a "Live Sessions" section on the home page
5. Active sessions should have a green pulsing indicator

**If live sessions don't appear:**
```bash
# 1. Verify hook is registered
python3 -c "import json; d=json.load(open('$HOME/.claude/settings.json')); print('SessionStart' in d.get('hooks',{}))"

# 2. Check state files are being created
watch -n1 'ls -la ~/.claude_karma/live-sessions/'

# 3. Verify API is reading the state files
curl http://localhost:8000/live-sessions 2>/dev/null | python3 -m json.tool
```

> **Agent notes:** If no live sessions appear, check: 1) hook is in settings.json, 2) Claude Code is actually running, 3) state files in ~/.claude_karma/live-sessions/ are being created/updated.

**Note:** SubagentStart and SubagentStop events require Claude Code 2.1.19+. On older versions, subagent tracking won't work, but everything else will.

---

## Tier 3: Smart Titles (Optional)

Adds human-readable session titles (e.g., "Refactor auth middleware" instead of "serene-meandering-scott").

### Step 8: Install the Session Title Generator Hook

**What:** Add a hook that generates titles when sessions end.
**Why:** Makes session cards easier to scan — titles summarize what was accomplished.
**Requires:** The API must be running (this hook POSTs titles to `/sessions/{uuid}/title`).

**Title generation priority:**
1. Most recent git commit message during the session (free, no LLM)
2. Claude Haiku via `claude -p` CLI (requires Claude CLI installed)
3. Truncated initial user prompt (fallback)

**Install the script:**

**Symlink:**
```bash
ln -sf "$(cd hooks && pwd)/session_title_generator.py" ~/.claude/hooks/session_title_generator.py
chmod +x hooks/session_title_generator.py
```

**Copy:**
```bash
cp hooks/session_title_generator.py ~/.claude/hooks/
chmod +x ~/.claude/hooks/session_title_generator.py
```

**Verify:**
```bash
ls -la ~/.claude/hooks/session_title_generator.py
```

> **Agent notes:** Confirm script exists and is executable. API must be running for this to work.

---

### Step 9: Register Hook Event

**What:** Register the title generator for `SessionEnd` event.
**Why:** Titles are generated only after a session ends, so we listen for that one event.

**Add this to `~/.claude/settings.json`** (under `"SessionEnd"` if it already exists from Tier 2):

```json
{
  "hooks": {
    "SessionEnd": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "python3 ~/.claude/hooks/session_title_generator.py",
            "timeout": 15000
          }
        ]
      }
    ]
  }
}
```

If you have Tier 2 live tracker, your `SessionEnd` should now have TWO entries:
```json
{
  "hooks": {
    "SessionEnd": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "python3 ~/.claude/hooks/live_session_tracker.py",
            "timeout": 5000
          }
        ]
      },
      {
        "hooks": [
          {
            "type": "command",
            "command": "python3 ~/.claude/hooks/session_title_generator.py",
            "timeout": 15000
          }
        ]
      }
    ]
  }
}
```

**Verify:**
```bash
# Check both SessionEnd entries exist
grep -A15 '"SessionEnd"' ~/.claude/settings.json
```

> **Agent notes:** Settings.json should have SessionEnd with BOTH hooks if using Tier 2+3. Timeout is 15000ms (15 seconds) for title gen since it may call Claude Haiku.

---

### Step 10: Verify Title Generation and Backfill

**What:** Test that titles are generated, and optionally create titles for existing sessions.
**Why:** Ensures feature is working and provides titles for sessions before the hook was installed.

**Test (after ending a Claude Code session):**
```bash
# After a session ends, check for title
curl http://localhost:8000/projects | python3 -c "
import sys, json
for p in json.load(sys.stdin)['projects']:
    for s in p.get('recent_sessions', []):
        print(f'{s.get(\"title\", \"NO TITLE\")} — {s[\"slug\"]}')" 2>/dev/null
```

**Backfill existing sessions:**
```bash
cd api
python3 scripts/backfill_titles.py
```

This generates titles for all sessions created before the hook was installed. Requires:
- API running
- Claude CLI available (for Haiku titles)

**Verify backfill:**
```bash
# Check project detail for newly titled sessions
curl http://localhost:8000/projects/YOUR-PROJECT-NAME | python3 -m json.tool | grep -A2 '"title"'
```

> **Agent notes:** If backfill fails, check: 1) API is running, 2) Claude CLI is installed (`which claude`), 3) API has permission to read sessions. Backfill is optional; it's fine if some sessions have no title.

---

## Hook Configuration Reference

### Complete Configuration (All Tiers)

The full `~/.claude/settings.json` for Tier 2 + 3:

```json
{
  "hooks": {
    "SessionStart": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "python3 ~/.claude/hooks/live_session_tracker.py",
            "timeout": 5000
          }
        ]
      }
    ],
    "UserPromptSubmit": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "python3 ~/.claude/hooks/live_session_tracker.py",
            "timeout": 5000
          }
        ]
      }
    ],
    "PostToolUse": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "python3 ~/.claude/hooks/live_session_tracker.py",
            "timeout": 5000
          }
        ]
      }
    ],
    "Notification": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "python3 ~/.claude/hooks/live_session_tracker.py",
            "timeout": 5000
          }
        ]
      }
    ],
    "Stop": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "python3 ~/.claude/hooks/live_session_tracker.py",
            "timeout": 5000
          }
        ]
      }
    ],
    "SubagentStart": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "python3 ~/.claude/hooks/live_session_tracker.py",
            "timeout": 5000
          }
        ]
      }
    ],
    "SubagentStop": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "python3 ~/.claude/hooks/live_session_tracker.py",
            "timeout": 5000
          }
        ]
      }
    ],
    "SessionEnd": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "python3 ~/.claude/hooks/live_session_tracker.py",
            "timeout": 5000
          }
        ]
      },
      {
        "hooks": [
          {
            "type": "command",
            "command": "python3 ~/.claude/hooks/session_title_generator.py",
            "timeout": 15000
          }
        ]
      }
    ]
  }
}
```

### Tier 2 Only (Live Tracking)

If you only want live tracking without title generation, use the same configuration as [Step 6](#step-6-register-hook-events) — omit the `session_title_generator.py` entry from `SessionEnd`.

### Removing a Hook

To remove a hook after installation:

| Hook | Action |
|------|--------|
| Live tracker | Delete all `live_session_tracker.py` entries from `"hooks"` in settings.json |
| Title generator | Delete the `session_title_generator.py` entry from `"SessionEnd"` |

Then optionally clean up the script:
```bash
rm ~/.claude/hooks/live_session_tracker.py    # or
rm ~/.claude/hooks/session_title_generator.py
```

---

## Environment Variables Reference

### API (Python/FastAPI)

All variables use the `CLAUDE_KARMA_` prefix. Set via shell, `.env` file in `api/`, or export:

```bash
# Start with custom settings
CLAUDE_KARMA_LOG_LEVEL=DEBUG uvicorn main:app --reload --port 8000
```

**Core:**

| Variable | Default | Description |
|----------|---------|-------------|
| `CLAUDE_KARMA_CLAUDE_BASE` | `~/.claude` | Base directory for Claude Code data |
| `CLAUDE_KARMA_USE_SQLITE` | `true` | Enable SQLite index (`false` = JSONL-only mode) |
| `CLAUDE_KARMA_LOG_LEVEL` | `INFO` | Logging level (DEBUG, INFO, WARNING, ERROR) |

**Cache Durations (seconds):**

| Variable | Default | Description |
|----------|---------|-------------|
| `CLAUDE_KARMA_CACHE_PROJECTS_LIST` | `30` | Projects list |
| `CLAUDE_KARMA_CACHE_PROJECT_DETAIL` | `60` | Project details |
| `CLAUDE_KARMA_CACHE_SESSION_DETAIL` | `60` | Session details |
| `CLAUDE_KARMA_CACHE_LIVE_SESSIONS` | `5` | Live sessions (short for real-time) |
| `CLAUDE_KARMA_CACHE_ANALYTICS` | `120` | Analytics data |
| `CLAUDE_KARMA_CACHE_AGENT_USAGE` | `300` | Agent usage |
| `CLAUDE_KARMA_CACHE_FILE_ACTIVITY` | `300` | File activity |

**File Size Limits:**

| Variable | Default | Description |
|----------|---------|-------------|
| `CLAUDE_KARMA_MAX_AGENT_SIZE` | `100000` | Max agent markdown size (bytes) |
| `CLAUDE_KARMA_MAX_SKILL_SIZE` | `1000000` | Max skill file size (bytes) |

**In-Memory Cache:**

| Variable | Default | Description |
|----------|---------|-------------|
| `CLAUDE_KARMA_CACHE_MAX_SIZE` | `1000` | Max entries in bounded caches |
| `CLAUDE_KARMA_CACHE_TTL` | `3600` | TTL for cached entries (seconds) |

**CORS & Production:**

| Variable | Default | Description |
|----------|---------|-------------|
| `CLAUDE_KARMA_CORS_ORIGINS` | `["http://localhost:5173"]` | CORS allowed origins (JSON array) |

### Frontend (SvelteKit)

| Variable | Default | Description |
|----------|---------|-------------|
| `PUBLIC_API_URL` | `http://localhost:8000` | FastAPI backend URL |

Set via shell or `frontend/.env`:
```bash
PUBLIC_API_URL=http://your-api-host:8000 npm run dev
```

### Hook Scripts

| Variable | Default | Used By | Description |
|----------|---------|---------|-------------|
| `CLAUDE_KARMA_API` | `http://localhost:8000` | Title generator | API base URL for POSTing titles |

---

## Directory Structure

### Claude Karma Creates

```
~/.claude_karma/
  metadata.db              # SQLite metadata index (auto-created)
  metadata.db-wal          # SQLite WAL journal (auto-managed)
  metadata.db-shm          # SQLite shared memory (auto-managed)
  live-sessions/           # Live session state (created by Tier 2 hook)
    {slug}.json            # One per active session
```

### Claude Code Data (Read by Claude Karma)

```
~/.claude/
  projects/                # Encoded project directories
    {encoded-path}/        # One per project (e.g., -Users-me-repo)
      {uuid}.jsonl         # Session transcripts
      {uuid}/
        subagents/         # Subagent sessions
          agent-{id}.jsonl
        tool-results/      # Tool output
          toolu_{id}.txt
  hooks/                   # Hook scripts (installed in Tiers 2-3)
    live_session_tracker.py
    session_title_generator.py
  settings.json            # Claude Code config (hooks registered here)
```

### Repository Structure

```
claude-karma/
  api/                     # FastAPI backend (Python)
  frontend/                # SvelteKit frontend (Svelte 5)
  captain-hook/            # Hook type definitions (Python)
  hooks/                   # Hook script source
    live_session_tracker.py
    session_title_generator.py
  SETUP.md                 # This file
  CLAUDE.md                # Agent guidance
  FEATURES.md              # Feature documentation
```

---

## Verification Checklist

Run through this after setup to confirm everything works.

### Tier 1: Core Dashboard

- [ ] API health: `curl http://localhost:8000/health` returns `{"status": "healthy", ...}`
- [ ] API has sessions: health response shows `session_count > 0`
- [ ] API projects endpoint: `curl http://localhost:8000/projects` returns JSON list
- [ ] Frontend loads: Browser at http://localhost:5173 shows home page
- [ ] Projects visible: Clicking "Projects" shows your Claude Code projects
- [ ] Project detail works: Clicking a project shows sessions with stats
- [ ] Session detail works: Clicking a session shows conversation
- [ ] Session timeline works: Session detail tab shows timeline
- [ ] Analytics available: `/analytics` page loads

### Tier 2: Live Monitoring

- [ ] Hook script exists: `ls ~/.claude/hooks/live_session_tracker.py`
- [ ] Hook registered: `grep "SessionStart" ~/.claude/settings.json`
- [ ] State directory exists: `ls ~/.claude_karma/live-sessions/`
- [ ] Live sessions appear: Start a new Claude Code session, then check dashboard home page
- [ ] Status badge works: Live sessions show status color (green = LIVE, blue = WAITING)
- [ ] Recently ended section: Sessions you just ended appear in "Recently Ended"

### Tier 3: Smart Titles

- [ ] Hook script exists: `ls ~/.claude/hooks/session_title_generator.py`
- [ ] Hook registered: `grep "session_title_generator" ~/.claude/settings.json`
- [ ] New sessions titled: End a new Claude Code session, check dashboard for descriptive title
- [ ] Backfill complete: `cd api && python3 scripts/backfill_titles.py` ran without errors
- [ ] Existing sessions titled: Old sessions now have titles instead of just slugs

---

## Troubleshooting

### API Won't Start

**Symptom:** `uvicorn main:app` fails or hangs

```bash
# Check Python version (must be 3.10+)
python3 --version

# Verify requirements installed
cd api && pip install -r requirements.txt

# Check port 8000 is free
lsof -ti:8000
# If in use, kill with: lsof -ti:8000 | xargs kill -9

# Check for syntax errors
python3 -c "import main" 2>&1 | head -20
```

### Frontend Won't Start

**Symptom:** `npm run dev` fails or port 5173 in use

```bash
# Check Node version (must be 18+)
node --version

# Clear node_modules and reinstall
cd frontend && rm -rf node_modules package-lock.json && npm install

# Check port 5173 is free
lsof -ti:5173
```

### Empty Projects List

**Symptom:** Dashboard shows no projects or 0 sessions

```bash
# Verify Claude Code has been used
ls ~/.claude/projects/

# Check sessions exist in a project
ls ~/.claude/projects/-Users-*/
```

If `~/.claude/projects/` is empty, use Claude Code to create a test session first.

### CORS Errors in Browser

**Symptom:** Console shows "Access to XMLHttpRequest blocked by CORS"

The API allows `http://localhost:5173` by default. If frontend runs elsewhere:

```bash
CLAUDE_KARMA_CORS_ORIGINS='["http://localhost:5173","http://localhost:3000"]' \
  uvicorn main:app --reload --port 8000
```

### Live Sessions Not Appearing

**Symptom:** Tier 2 hook installed but no live indicators on dashboard

```bash
# 1. Check hook is registered
grep -c "SessionStart" ~/.claude/settings.json

# 2. Start a Claude Code session and check state files
watch -n1 'ls -la ~/.claude_karma/live-sessions/'

# 3. Check API sees live sessions
curl http://localhost:8000/live-sessions 2>/dev/null | python3 -m json.tool

# 4. Test hook manually
echo '{"hook_event_name":"SessionStart","session_id":"test","cwd":"/tmp"}' \
  | python3 ~/.claude/hooks/live_session_tracker.py
```

### Session Titles Not Generating

**Symptom:** Tier 3 hook installed but sessions have no titles

```bash
# 1. Check hook script exists
ls ~/.claude/hooks/session_title_generator.py

# 2. Verify API is running (required for this hook)
curl http://localhost:8000/health

# 3. Check Claude CLI available (optional, for Haiku titles)
which claude

# 4. Run backfill for existing sessions
cd api && python3 scripts/backfill_titles.py

# 5. Check API logs for errors
tail -50 ~/.claude_karma/api.log 2>/dev/null || echo "No log file"
```

### SQLite Database Issues

**Symptom:** API shows `"sqlite": {"ready": false}` in health endpoint

```bash
# 1. Check database exists
ls -la ~/.claude_karma/metadata.db

# 2. Verify API can write to directory
touch ~/.claude_karma/test.txt && rm ~/.claude_karma/test.txt

# 3. Force reindex (API must be running)
curl -X POST http://localhost:8000/admin/reindex

# 4. Nuclear option: delete and rebuild
rm ~/.claude_karma/metadata.db*
# Then restart API (auto-recreates database)
```

### Subagent Tracking Not Working

**Symptom:** SubagentStart/SubagentStop events registered but not tracking

```bash
# Requires Claude Code 2.1.19+
claude --version

# Verify both events registered
grep -c "SubagentStart" ~/.claude/settings.json
grep -c "SubagentStop" ~/.claude/settings.json
```

On older Claude Code versions, subagent tracking is unavailable but everything else works.

---

## Updating

```bash
git pull origin main
```

### After Updating

```bash
# Reinstall dependencies if they changed
cd api && pip install -r requirements.txt
cd frontend && npm install

# Reindex SQLite if schema changed
curl -X POST http://localhost:8000/admin/reindex
```

---

## Getting Help

- **API errors:** Check `uvicorn` terminal output
- **Frontend errors:** Check browser console (F12)
- **Hook issues:** Enable debug logging: `CLAUDE_KARMA_LOG_LEVEL=DEBUG`
- **File paths:** Verify `~/.claude/` and `~/.claude_karma/` exist and are readable
