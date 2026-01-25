# Claude Karma Setup

Full-stack application for monitoring and analyzing Claude Code sessions.

## Architecture

```
claude-karma/
├── api/                    # FastAPI backend (port 8000)
│   ├── main.py             # Entry point
│   ├── routers/            # API route handlers
│   ├── models/             # Pydantic models for parsing ~/.claude/
│   └── scripts/            # Hook scripts (live tracker, plan approval)
├── frontend/               # SvelteKit frontend (port 5173)
│   └── src/                # Svelte 5 + Tailwind CSS 4
└── captain-hook/           # Claude Code hooks Pydantic library
    └── src/captain_hook/   # Type-safe models for all 10 hook types
```

## Prerequisites

| Tool | Version | Check |
|------|---------|-------|
| Python | 3.10+ | `python3 --version` |
| Node.js | 18+ | `node --version` |
| npm | 9+ | `npm --version` |

## Quick Start

### 1. Clone with Submodules

```bash
git clone --recursive https://github.com/JayantDevkar/claude-karma.git
cd claude-karma
```

If you already cloned without `--recursive`:
```bash
git submodule update --init --recursive
```

### 2. Start API (Terminal 1)

```bash
cd api
pip install -r requirements.txt
uvicorn main:app --reload --port 8000
```

Verify: `curl http://localhost:8000/health` should return `{"status":"healthy"}`

### 3. Start Frontend (Terminal 2)

```bash
cd frontend
npm install
npm run dev
```

### 4. Open Dashboard

Navigate to **http://localhost:5173** to view your Claude Code sessions.

---

## Component Setup Details

### API (FastAPI)

```bash
cd api

# Install dependencies
pip install -r requirements.txt

# Run with hot reload
uvicorn main:app --reload --port 8000

# Run tests
pytest

# Run API tests only
pytest tests/api/ -v

# Lint & format
ruff check . && ruff format .
```

**Key endpoints:**

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/projects` | List all projects |
| GET | `/projects/{encoded_name}` | Project details with sessions |
| GET | `/sessions/{uuid}` | Session details |
| GET | `/sessions/{uuid}/timeline` | Session timeline events |
| GET | `/sessions/{uuid}/tools` | Tool usage breakdown |
| GET | `/plans` | List all plans |
| GET | `/plans/{slug}/status` | Plan approval status |
| GET | `/analytics` | Global analytics |

### Frontend (SvelteKit)

```bash
cd frontend

# Install dependencies
npm install

# Dev server (port 5173)
npm run dev

# Type check
npm run check

# Lint & format
npm run lint && npm run format

# Production build
npm run build
```

**Tech stack:** SvelteKit 2, Svelte 5 (runes), Tailwind CSS 4, Chart.js, bits-ui

### Captain Hook (Hooks Library)

Type-safe Pydantic models for Claude Code's 10 hook types.

```bash
cd captain-hook

# Run tests
pytest tests/test_models.py -v

# Verify import
python3 -c "from captain_hook import parse_hook_event, PreToolUseHook"
```

---

## Claude Code Hooks

Claude Karma includes hook scripts that integrate with Claude Code for real-time tracking and plan approval.

### Hook Scripts

| Script | Purpose | Hook Type |
|--------|---------|-----------|
| `api/scripts/live_session_tracker.py` | Track session state in real-time | Multiple |
| `api/scripts/plan_approval.py` | Verify plan approval before implementation | PermissionRequest |

### Live Session Tracking

Enable real-time session monitoring on the dashboard.

#### 1. Install the Tracker Script

```bash
mkdir -p ~/.local/bin
cp api/scripts/live_session_tracker.py ~/.local/bin/claude-karma-tracker
chmod +x ~/.local/bin/claude-karma-tracker
```

#### 2. Configure Hooks

**Option A: Project-level (recommended)**

Create `.claude/hooks.yaml` in your project:

```yaml
hooks:
  SessionStart:
    - command: "cat | python3 ~/.local/bin/claude-karma-tracker"
      timeout: 2000

  UserPromptSubmit:
    - command: "cat | python3 ~/.local/bin/claude-karma-tracker"
      timeout: 2000

  PostToolUse:
    - command: "cat | python3 ~/.local/bin/claude-karma-tracker"
      timeout: 2000

  Notification:
    - command: "cat | python3 ~/.local/bin/claude-karma-tracker"
      timeout: 2000

  Stop:
    - command: "cat | python3 ~/.local/bin/claude-karma-tracker"
      timeout: 2000

  SessionEnd:
    - command: "cat | python3 ~/.local/bin/claude-karma-tracker"
      timeout: 2000
```

**Option B: Global hooks**

Add to `~/.claude/settings.json`:

```json
{
  "hooks": {
    "SessionStart": [{ "command": "cat | python3 ~/.local/bin/claude-karma-tracker", "timeout": 2000 }],
    "UserPromptSubmit": [{ "command": "cat | python3 ~/.local/bin/claude-karma-tracker", "timeout": 2000 }],
    "PostToolUse": [{ "command": "cat | python3 ~/.local/bin/claude-karma-tracker", "timeout": 2000 }],
    "Notification": [{ "command": "cat | python3 ~/.local/bin/claude-karma-tracker", "timeout": 2000 }],
    "Stop": [{ "command": "cat | python3 ~/.local/bin/claude-karma-tracker", "timeout": 2000 }],
    "SessionEnd": [{ "command": "cat | python3 ~/.local/bin/claude-karma-tracker", "timeout": 2000 }]
  }
}
```

#### Session States

| State | Meaning | Dashboard |
|-------|---------|-----------|
| `LIVE` | Active tool execution | Green (pulsing) |
| `WAITING` | Needs user input | Blue |
| `STOPPED` | Agent finished | Gray |
| `STALE` | Idle 60+ seconds | Yellow |
| `ENDED` | Session terminated | Dimmed |

### Plan Approval Hook

Require plan approval in Claude Karma before Claude can exit plan mode.

#### 1. Install the Script

```bash
cp api/scripts/plan_approval.py ~/.local/bin/claude-karma-plan-approval
chmod +x ~/.local/bin/claude-karma-plan-approval
```

#### 2. Configure Hook

Add to `.claude/hooks.yaml` or global settings:

```yaml
hooks:
  PermissionRequest:
    - matcher: "ExitPlanMode"
      hooks:
        - type: command
          command: "cat | python3 ~/.local/bin/claude-karma-plan-approval"
          timeout: 30000
```

Or in `~/.claude/settings.json`:

```json
{
  "hooks": {
    "PermissionRequest": [{
      "matcher": "ExitPlanMode",
      "hooks": [{
        "type": "command",
        "command": "cat | python3 ~/.local/bin/claude-karma-plan-approval",
        "timeout": 30000
      }]
    }]
  }
}
```

#### Decision Logic

| Plan Status | Hook Response | Result |
|-------------|---------------|--------|
| `approved` | Allow | Claude proceeds with implementation |
| `changes_requested` | Deny + feedback | Claude sees reviewer feedback |
| `pending` | Deny | User prompted to review in UI |
| Has annotations | Deny + annotations | Claude sees suggested changes |

#### Workflow

1. Claude enters plan mode and writes a plan
2. Claude calls `ExitPlanMode` to start implementation
3. Hook checks plan status via Claude Karma API
4. If approved: Claude proceeds
5. If pending/changes requested: Claude receives feedback and waits

---

## Data Locations

Claude Karma reads from Claude Code's local storage:

| Data | Location |
|------|----------|
| Projects | `~/.claude/projects/` |
| Sessions | `~/.claude/projects/{project}/{uuid}.jsonl` |
| Subagents | `~/.claude/projects/{project}/{uuid}/subagents/` |
| Tool Results | `~/.claude/projects/{project}/{uuid}/tool-results/` |
| Plans | `~/.claude/plans/{slug}.md` |
| Todos | `~/.claude/todos/{uuid}-*.json` |
| Debug Logs | `~/.claude/debug/{uuid}.txt` |
| Live Sessions | `~/.claude_karma/live-sessions/{slug}.json` |

---

## Submodule Management

| Submodule | Branch | Repository |
|-----------|--------|------------|
| `api/` | main | dot-claude-files-parser |
| `frontend/` | main | ClaudeDashboard |
| `captain-hook/` | main | captain-hook |

```bash
# Update all submodules to latest
git submodule update --remote

# Update specific submodule
git submodule update --remote api

# Check submodule status
git submodule status
```

---

## Troubleshooting

### API Issues

**API won't start:**
```bash
# Check Python version
python3 --version  # Should be 3.10+

# Reinstall dependencies
pip install -r api/requirements.txt
```

**Empty projects list:**
```bash
# Check Claude Code has been used
ls ~/.claude/projects/

# Check sessions exist
ls ~/.claude/projects/-Users-*/
```

### Frontend Issues

**Frontend won't start:**
```bash
# Check Node version
node --version  # Should be 18+

# Clear cache and reinstall
cd frontend
rm -rf node_modules
npm install
```

**CORS errors:**
The API allows requests from `localhost:5173`. Update `api/main.py` if using a different port.

### Hook Issues

**Live sessions not tracking:**
```bash
# Check state files are created
ls ~/.claude_karma/live-sessions/

# Watch for changes
watch -n1 'cat ~/.claude_karma/live-sessions/*.json 2>/dev/null | jq -s .'
```

**Plan approval not working:**
```bash
# Test the script manually
echo '{"tool_name": "ExitPlanMode", "tool_input": {}}' | python3 ~/.local/bin/claude-karma-plan-approval

# Check API is running
curl http://localhost:8000/plans
```

### Port Conflicts

```bash
# Kill process on port 8000
lsof -ti:8000 | xargs kill -9

# Kill process on port 5173
lsof -ti:5173 | xargs kill -9
```

---

## Development

### Running Tests

```bash
# API tests
cd api && pytest -v

# Captain Hook tests
cd captain-hook && pytest tests/test_models.py -v

# Frontend type check
cd frontend && npm run check
```

### Linting

```bash
# Python (ruff)
cd api && ruff check . && ruff format .

# TypeScript/Svelte
cd frontend && npm run lint && npm run format
```

### Building for Production

```bash
# Frontend
cd frontend && npm run build

# Preview production build
npm run preview
```
