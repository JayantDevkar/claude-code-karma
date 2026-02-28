# Quick Start

Get Claude Code Karma running in under 5 minutes.

## Prerequisites

| Requirement | Minimum Version |
|-------------|----------------|
| Python | 3.9+ |
| Node.js | 18+ |
| npm | 7+ |
| Git | 2.x |

You must also have Claude Code installed and have existing sessions in `~/.claude/projects/`.

## 1. Clone the Repository

```bash
git clone https://github.com/JayantDevkar/claude-karma.git
cd claude-karma
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

## Next Steps

- [Features](features.md) — Explore the full feature set
- [Architecture](architecture.md) — Understand how Claude Code Karma works
- [API Reference](api-reference.md) — Browse all API endpoints
