# Claude Karma Setup

Full-stack application for monitoring and analyzing Claude Code sessions.

## Architecture

```
claude-karma/
├── api/                    # FastAPI backend (port 8000)
│   ├── main.py             # Entry point
│   ├── routers/            # API route handlers
│   └── models/             # Python Pydantic models
├── web/                    # SvelteKit frontend (port 5173)
│   └── frontend/           # Svelte 5 + Tailwind CSS
└── captain-hook/           # Claude Code hooks library
```

## Prerequisites

- **Python 3.10+** (for API)
- **Node.js 18+** (for frontend)
- **pnpm** (for frontend package management)

```bash
# Install pnpm if not already installed
npm install -g pnpm
```

## Quick Start

### 1. Clone with submodules

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

The API will be available at http://localhost:8000

Verify with:
```bash
curl http://localhost:8000/health
# Should return: {"status": "healthy"}
```

### 3. Start Frontend (Terminal 2)

```bash
cd web/frontend
pnpm install
pnpm dev
```

The frontend will be available at http://localhost:5173

### 4. Open Browser

Navigate to http://localhost:5173 to view the dashboard.

## API Endpoints

| Endpoint | Description |
|----------|-------------|
| `GET /projects` | List all projects |
| `GET /projects/{name}` | Project details with sessions |
| `GET /sessions/{uuid}` | Session details |
| `GET /sessions/{uuid}/timeline` | Session timeline events |
| `GET /analytics` | Global analytics |

## Development

### API Development

```bash
cd api

# Run with hot reload
uvicorn main:app --reload --port 8000

# Run tests
pytest

# Run API tests only
pytest tests/api/
```

### Frontend Development

```bash
cd web/frontend

# Dev server with hot reload
pnpm dev

# Type check
pnpm check

# Lint
pnpm lint

# Build for production
pnpm build
```

## Submodule Branches

The repository uses specific branches for each submodule:

| Submodule | Branch | Repository |
|-----------|--------|------------|
| `api/` | `refactor/delete-react-frontend` | dot-claude-files-parser |
| `web/` | `refactor/move-frontend` | ClaudeDashboard |
| `captain-hook/` | `main` | captain-hook |

To update submodules to latest:
```bash
git submodule update --remote
```

## Troubleshooting

### API won't start
- Ensure Python 3.10+ is installed: `python --version`
- Install requirements: `pip install -r api/requirements.txt`

### Frontend won't start
- Ensure Node.js 18+ is installed: `node --version`
- Ensure pnpm is installed: `pnpm --version`
- Clear node_modules and reinstall: `rm -rf node_modules && pnpm install`

### Empty dashboard
- The API reads from `~/.claude/projects/` - ensure you have Claude Code sessions
- Check API is running: `curl http://localhost:8000/health`
