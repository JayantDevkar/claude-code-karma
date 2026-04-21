#!/usr/bin/env bash
# Start the API and frontend dev servers together.
# Ctrl-C stops both cleanly.

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
API_DIR="$ROOT/api"
WEB_DIR="$ROOT/frontend"
API_PORT="${API_PORT:-8000}"
WEB_PORT="${WEB_PORT:-5173}"

prefix() {
  local tag="$1"
  while IFS= read -r line; do
    printf '[%s] %s\n' "$tag" "$line"
  done
}

if [[ ! -d "$API_DIR/venv" ]]; then
  echo "[setup] Creating Python venv in $API_DIR/venv"
  python3 -m venv "$API_DIR/venv"
  "$API_DIR/venv/bin/pip" install --upgrade pip >/dev/null
  "$API_DIR/venv/bin/pip" install -e "$API_DIR[dev]"
  "$API_DIR/venv/bin/pip" install -r "$API_DIR/requirements.txt"
fi

if [[ ! -d "$WEB_DIR/node_modules" ]]; then
  echo "[setup] Installing frontend deps"
  (cd "$WEB_DIR" && npm install --engine-strict=false)
fi

pids=()
cleanup() {
  echo ""
  echo "[dev] stopping..."
  for pid in "${pids[@]}"; do
    kill "$pid" 2>/dev/null || true
  done
  wait 2>/dev/null || true
  exit 0
}
trap cleanup INT TERM

echo "[dev] api  → http://localhost:$API_PORT"
echo "[dev] web  → http://localhost:$WEB_PORT"
echo "[dev] Ctrl-C to stop both"
echo ""

(
  cd "$API_DIR"
  exec "$API_DIR/venv/bin/uvicorn" main:app --reload --port "$API_PORT" --host 127.0.0.1
) 2>&1 | prefix api &
pids+=($!)

(
  cd "$WEB_DIR"
  exec npm run dev -- --port "$WEB_PORT"
) 2>&1 | prefix web &
pids+=($!)

wait
