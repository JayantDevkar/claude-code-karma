# Sync SQLite Migration Design

**Date:** 2026-03-07
**Status:** Approved
**Author:** Jayant Devkar + Claude

## Problem

Sync configuration (teams, members, projects) lives in `sync-config.json` — a flat Pydantic model that's fully deserialized and rewritten on every operation. There's no activity history, no query capability, no search/indexing, and concurrent access from the CLI + API + watcher risks file corruption. Users sharing session data deserve full transparency into sync activity.

## Goal

Move teams, members, and project associations into SQLite (`metadata.db`). Add a comprehensive sync event log. Keep JSON for identity/credentials only.

## Decisions

| Decision | Choice | Rationale |
|---|---|---|
| Event retention | Keep forever | ~100 bytes/event, 10K events/year = 1MB. Negligible. |
| CLI DB access | Direct SQLite reads via shared `db/` module | Single source of truth, no drift. DB-agnostic abstraction for future Postgres migration. |
| JSON scope | Identity only (`user_id`, `machine_id`, Syncthing credentials) | Bootstrap data needed before DB exists. Everything relational goes to SQLite. |
| Event types | Comprehensive (12+) | Users sharing data deserve full visibility |
| Migration | None needed | Feature not in prod yet, greenfield |
| DB location | Same `metadata.db` (schema v18) | Real FKs, existing connection infrastructure, one DB file |

## Schema

Four new tables added via schema v18 migration:

```sql
CREATE TABLE IF NOT EXISTS sync_teams (
    name TEXT PRIMARY KEY,
    backend TEXT NOT NULL DEFAULT 'syncthing',
    created_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS sync_members (
    team_name TEXT NOT NULL,
    name TEXT NOT NULL,
    device_id TEXT,
    ipns_key TEXT,
    added_at TEXT DEFAULT (datetime('now')),
    PRIMARY KEY (team_name, name),
    FOREIGN KEY (team_name) REFERENCES sync_teams(name) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_sync_members_device ON sync_members(device_id);

CREATE TABLE IF NOT EXISTS sync_team_projects (
    team_name TEXT NOT NULL,
    project_encoded_name TEXT NOT NULL,
    path TEXT,
    added_at TEXT DEFAULT (datetime('now')),
    PRIMARY KEY (team_name, project_encoded_name),
    FOREIGN KEY (team_name) REFERENCES sync_teams(name) ON DELETE CASCADE,
    FOREIGN KEY (project_encoded_name) REFERENCES projects(encoded_name)
);

CREATE TABLE IF NOT EXISTS sync_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_type TEXT NOT NULL,
    team_name TEXT,
    member_name TEXT,
    project_encoded_name TEXT,
    session_uuid TEXT,
    detail TEXT,
    created_at TEXT DEFAULT (datetime('now')),
    FOREIGN KEY (team_name) REFERENCES sync_teams(name) ON DELETE SET NULL
);

CREATE INDEX IF NOT EXISTS idx_sync_events_type ON sync_events(event_type);
CREATE INDEX IF NOT EXISTS idx_sync_events_team ON sync_events(team_name, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_sync_events_time ON sync_events(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_sync_events_member ON sync_events(member_name, created_at DESC);
```

## Event Types

| Event Type | When | Key fields |
|---|---|---|
| `session_packaged` | Watcher packages a session | `session_uuid`, `project_encoded_name` |
| `session_received` | Indexer finds new remote session | `session_uuid`, `member_name`, `project_encoded_name` |
| `member_connected` | Syncthing device online | `member_name` |
| `member_disconnected` | Syncthing device offline | `member_name` |
| `team_created` | Team created | `team_name` |
| `team_deleted` | Team deleted | `team_name` |
| `member_added` | Member added | `team_name`, `member_name` |
| `member_removed` | Member removed | `team_name`, `member_name` |
| `project_added` | Project added to team | `team_name`, `project_encoded_name` |
| `project_removed` | Project removed from team | `team_name`, `project_encoded_name` |
| `watcher_started` | Watcher started | `team_name` |
| `watcher_stopped` | Watcher stopped | `team_name` |
| `pending_accepted` | Pending folder accepted | `team_name` |
| `sync_error` | Any sync failure | detail has error message |

## JSON Config (Trimmed)

`~/.claude_karma/sync-config.json` keeps only:

```json
{
  "user_id": "alice",
  "machine_id": "alice-macbook-pro",
  "syncthing": {
    "api_url": "http://127.0.0.1:8384",
    "api_key": "abc123...",
    "device_id": "XXXXXXX-..."
  }
}
```

## Module Structure

```
api/db/
├── connection.py           # Existing — unchanged
├── schema.py               # Add v18 migration with 4 new tables
├── indexer.py              # Add log_event() call in index_remote_sessions()
├── queries.py              # Existing session queries — unchanged
└── sync_queries.py         # NEW: team/member/project/event CRUD functions

cli/karma/
├── config.py               # Trim to identity-only SyncConfig
├── db.py                   # NEW: thin connection helper for CLI
└── syncthing.py            # Unchanged
```

`sync_queries.py` functions all take a raw `sqlite3.Connection` — no framework dependency. The API wraps with `run_in_executor` for async. The CLI calls directly.

## API Router Changes

Every mutating sync endpoint switches from JSON read/write to SQLite queries + `log_event()`. Syncthing proxy endpoints (detect, devices, folders, rescan) stay unchanged. Activity endpoint queries `sync_events` table instead of raw Syncthing events.

## References

- Existing schema: `api/db/schema.py` (v17)
- Connection layer: `api/db/connection.py` (reader/writer separation, WAL mode)
- Current sync router: `api/routers/sync_status.py` (17 endpoints)
- Current config: `cli/karma/config.py` (SyncConfig Pydantic model)
- Syncthing client: `cli/karma/syncthing.py`
- Syncthing proxy: `api/services/syncthing_proxy.py`
