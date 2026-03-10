# Duplicated Logic Between CLI and API

**Severity:** HIGH
**Files:** `api/routers/sync_status.py`, `cli/karma/main.py`

## Status: PARTIALLY RESOLVED

Folder ID parsing has been consolidated into `api/services/folder_id.py`:
- `parse_karma_folder_id(folder_id, known_names=None)` — replaces 4 prior implementations
- `parse_karma_handshake_id(folder_id, known_teams=None)` — replaces `_parse_handshake_folder`
- `known_names_from_db(conn)` / `known_teams_from_db(conn)` — DB convenience helpers

Both the API (`api/routers/sync_status.py`) and CLI (`cli/karma/pending.py`) now import from this shared module.

## Remaining Duplication

- `_auto_share_folders` — folder sharing logic (API async vs CLI sync)
- Project suffix computation from git identity or path
