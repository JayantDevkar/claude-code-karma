#!/usr/bin/env bash
# karma-side trigger for the agent-coord rooms indexer.
#
# Called synchronously by claude-communicate's UserPromptSubmit hook to
# ingest any new room messages on disk before the agent's next turn.
#
# Fail-open contract (proposal.md §5 Layer 4): always exit 0. Never block
# the agent's prompt on indexer failure. The 300s polling timer in
# api/main.py is the safety net if this fails.
#
# claude-communicate's hook owns its own delivery preamble + cursor +
# fail-open wrapping; this script only triggers ingest. Stdout / stderr
# go to claude-communicate's hook log, not back to the agent.

set +e  # don't propagate errors

KARMA_API_DIR="${KARMA_API_DIR:-$HOME/Documents/GitHub/claude-karma/api}"
PYTHON_BIN="${KARMA_PYTHON:-python3}"

if [[ ! -d "$KARMA_API_DIR" ]]; then
    echo "[room-sync] karma api dir not found: $KARMA_API_DIR" >&2
    exit 0
fi

cd "$KARMA_API_DIR" || exit 0

# Run the indexer module. PYTHONPATH lets `db.sync_rooms` resolve `db`,
# `config`, etc. without an installed package.
PYTHONPATH="$KARMA_API_DIR" "$PYTHON_BIN" -m db.sync_rooms 2>&1 || true

exit 0
