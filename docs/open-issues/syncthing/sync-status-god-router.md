# sync_status.py God Router

**Severity:** HIGH
**File:** `api/routers/sync_status.py` (~1,900 lines)

## Problem

This single file handles:
- Team CRUD (create, join, leave, delete)
- Member management (add, remove, list)
- Project management (add, remove, share)
- Syncthing proxy operations (devices, folders, pending)
- Folder ID parsing and naming conventions
- Auto-accept and auto-share logic
- Watcher management (start, stop, status)
- Pending folder handling
- Activity feeds and event queries
- Team settings (session limit)
- Sync-now packaging trigger
- Full reset flow

This makes it hard to test individual concerns, review changes, and onboard new contributors.

## Proposed Split

| New File | Responsibility |
|----------|---------------|
| `routers/sync_teams.py` | Team/member/project CRUD |
| `routers/sync_devices.py` | Syncthing proxy operations |
| `routers/sync_activity.py` | Events and activity feeds |
| `services/sync_folders.py` | Folder ID parsing, auto-accept, auto-share |

Shared helpers (`validate_project_name`, `validate_project_path`, `_get_sync_conn`) move to `services/sync_helpers.py`.

## Why Deferred

Pure structural refactor with no behavioral changes. Ideal for a separate PR that only moves code, making it easy to review and verify nothing breaks.
