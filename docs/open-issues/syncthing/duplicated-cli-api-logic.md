# Duplicated Logic Between CLI and API

**Severity:** HIGH
**Files:** `api/routers/sync_status.py`, `cli/karma/main.py`

## Problem

Both files independently implement:
- `_parse_folder_id` — folder ID parsing (API line 211, CLI line 171)
- `_auto_share_folders` — folder sharing logic (API line 442, CLI line 117)
- Project suffix computation from git identity or path

The API version is async (uses `SyncthingProxy`), the CLI version is sync (uses `SyncthingClient`). They have subtly different behavior and could diverge over time.

Additionally, the API's `sync_accept_pending` endpoint imports `_accept_pending_folders` from `karma.main`, creating tight coupling between the API router and CLI module.

## Impact

- Bug fixes applied to one implementation may not reach the other
- Behavioral divergence between API-triggered and CLI-triggered sync operations
- Tight coupling makes testing harder

## Proposed Fix

Extract shared logic into a common module (e.g., `cli/karma/folder_ids.py` or a shared library) with:
- `parse_folder_id(folder_id, known_names)` — pure function, no I/O
- `compute_project_suffix(git_identity, path, encoded_name)` — pure function
- Folder naming conventions as constants

Both async (API) and sync (CLI) callers import the pure functions and handle I/O themselves.

## Why Deferred

Requires creating a shared module, updating imports across both codebases, and retesting all sync flows. The current duplication is manageable with both implementations exercised through their respective entry points.
