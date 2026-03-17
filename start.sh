#!/bin/bash
# Claude Code Karma - Start Backend (port 8000) and Frontend (port 5199)

BACKEND_PORT=8000
FRONTEND_PORT=5199

echo "Starting Claude Code Karma..."
echo

# Get script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Function to kill process on port
kill_port() {
    local PORT=$1
    local NAME=$2
    local PIDS=$(lsof -ti:$PORT 2>/dev/null || netstat -ano | findstr ":$PORT" | findstr "LISTENING" | awk '{print $5}' | sort -u)

    if [ -n "$PIDS" ]; then
        for PID in $PIDS; do
            echo "  - Killing $NAME process on port $PORT (PID: $PID)"
            kill -9 $PID 2>/dev/null
        done
    fi
}

# Kill existing processes on ports
kill_port $BACKEND_PORT "Backend"
kill_port $FRONTEND_PORT "Frontend"

# Start Backend on port 8000
echo "[1/2] Starting Backend on port $BACKEND_PORT..."
cd "$SCRIPT_DIR/api"
uvicorn main:app --reload --port $BACKEND_PORT &
BACKEND_PID=$!

# Wait for backend to start
sleep 3

# Start Frontend on port 5199
echo "[2/2] Starting Frontend on port $FRONTEND_PORT..."
cd "$SCRIPT_DIR/frontend"
npm run dev -- --port $FRONTEND_PORT &
FRONTEND_PID=$!

echo
echo "========================================"
echo "  Backend: http://localhost:$BACKEND_PORT (PID: $BACKEND_PID)"
echo "  Frontend: http://localhost:$FRONTEND_PORT (PID: $FRONTEND_PID)"
echo "========================================"
echo
echo "Press Ctrl+C to stop both servers"
echo

# Handle Ctrl+C to kill both processes
trap "kill $BACKEND_PID $FRONTEND_PID 2>/dev/null; exit" INT TERM

# Wait for any process to exit
wait
