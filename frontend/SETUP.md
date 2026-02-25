# Setup Guide

Follow these instructions to get **Claude Karma** running locally.

## Prerequisites

- **Node.js** (v18+)
- **Python** (3.10+)
- **Claude Code** (CLI tool installed and active)

## 1. Backend Setup

The backend is a FastAPI service that parses your local `.claude` logs.

```bash
cd backend

# Initialize submodule if not already done
git submodule update --init --recursive

# Create a virtual environment (optional but recommended)
python -m venv venv
source venv/bin/activate  # or venv\Scripts\activate on Windows

# Install dependencies
pip install -r apps/api/requirements.txt

# Start the API server
cd apps/api
uvicorn main:app --reload --port 8000
```

The API will be available at `http://localhost:8000`.

## 2. Frontend Setup

The frontend is a SvelteKit application.

```bash
cd frontend

# Install dependencies
npm install

# Start the development server
npm run dev
```

Open your browser to `http://localhost:5173`.

## Troubleshooting

- **Missing Data?** Ensure you have run `claude` (the CLI tool) at least once on your machine. The dashboard reads from your local `~/.claude` or project-specific `.claude` directories.
- **API Connection Error?** Verify the backend is running on port `8000` and usually check console logs for CORS issues if accessing from a different port.
