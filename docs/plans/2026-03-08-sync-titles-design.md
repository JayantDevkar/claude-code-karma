# Sync Session Titles Across Devices

## Problem

When sessions are synced via Syncthing, the receiver sees remote sessions without titles. The hook-generated titles (from git commits or Haiku) are stored only in the sender's local SQLite and disk cache — they never reach the outbox.

Claude Code's native `SessionTitleMessage` entries (type: "summary") are inside the JSONL and do get synced, but the receiver's `_build_remote_metadata()` only reads first/last lines for performance — it never extracts them.

**Result**: Owner sees a list of UUIDs/slugs for freelancer sessions, making team activity opaque.

## Design: `titles.json` Sidecar File

A separate `titles.json` file in each outbox directory, written independently of the packager, synced by Syncthing like any other file.

### Why not add titles to manifest.json?

Timing gap. The watcher fires on JSONL changes; the title hook fires on SessionEnd. The title is generated AFTER packaging. And the title POST doesn't modify any JSONL, so no re-trigger occurs. A separate file avoids this chicken-and-egg problem.

### File location

```
~/.claude_karma/remote-sessions/{user_id}/{encoded_name}/
  ├── manifest.json     (structural: uuids, mtimes, worktrees)
  ├── titles.json       (display: uuid → title)  ← NEW
  └── sessions/
      └── *.jsonl
```

### File format

```json
{
  "version": 1,
  "updated_at": "2026-03-08T14:30:00Z",
  "titles": {
    "abc-123-uuid": {
      "title": "Fix auth bug in login flow",
      "source": "git",
      "generated_at": "2026-03-08T12:00:00Z"
    },
    "def-456-uuid": {
      "title": "Add pagination to users API",
      "source": "haiku",
      "generated_at": "2026-03-08T13:00:00Z"
    }
  }
}
```

Fields per entry:
- `title` — the display title string
- `source` — how it was generated: `"git"`, `"haiku"`, or `"fallback"`
- `generated_at` — ISO timestamp of generation

## Data Flow

```
SENDER                                    RECEIVER
══════                                    ════════

SessionEnd
  ├─ Watcher → packages JSONL + manifest
  │    └─ packager also dumps known titles from cache → titles.json
  │
  └─ Title hook → POST /sessions/{id}/title
       ├─ SQLite ✅ (existing)
       ├─ Disk cache ✅ (existing)
       └─ Outbox titles.json ✅ (NEW)
              │
              Syncthing syncs titles.json
                     │
                     ▼
              Receiver reads titles.json
              alongside manifest
                     │
                     ▼
              Dashboard shows title ✅
```

Both write paths (packager + title POST handler) merge into the same `titles.json`. The packager catches older sessions' titles from the cache; the title handler catches the latest session's title even if the packager already ran.

## Changes

### Sender side

**1. `api/routers/sessions.py` — POST /sessions/{uuid}/title handler**

After storing in SQLite + disk cache (existing), also write to the outbox `titles.json`:
- Read sync-config.json to get `user_id`
- Find the session's `encoded_name`
- Write/merge into `~/.claude_karma/remote-sessions/{user_id}/{encoded_name}/titles.json`
- Use atomic write (write to `.tmp`, rename) to avoid partial reads

**2. `cli/karma/packager.py` — `package()` method**

After writing `manifest.json`, also write `titles.json`:
- Read from the local title cache (`SessionTitleCache`) for all discovered sessions
- Merge with any existing `titles.json` in the staging dir (preserve titles for sessions we didn't re-discover)
- Write atomically

**3. New utility: `cli/karma/titles_io.py`**

Shared read/write logic for `titles.json`:
- `read_titles(path) -> dict[str, TitleInfo]`
- `write_title(path, uuid, title, source)` — merge-and-write
- `write_titles_bulk(path, entries)` — bulk write from packager
- Atomic file writes with `.tmp` + rename

### Receiver side

**4. `api/services/remote_sessions.py` — metadata builder**

- New `_load_remote_titles(user_id, encoded_name) -> dict[str, str]` (cached with TTL, same pattern as `_load_manifest_worktree_map`)
- `_build_remote_metadata()` populates title from this cache
- `list_remote_sessions_for_project()` and `iter_all_remote_session_metadata()` pass titles through

**5. `api/services/session_filter.py` — SessionMetadata**

- Add `remote_title: Optional[str] = None` field
- Search/filter logic can match against remote titles

### No changes needed

- `cli/karma/manifest.py` — manifest model stays structural
- `hooks/session_title_generator.py` — it POSTs to API, which handles the rest
- `api/db/sync_queries.py` — no DB schema changes
- `api/services/syncthing_proxy.py` — Syncthing handles file sync automatically

## Edge Cases

| Case | Handling |
|------|----------|
| Title generated before first package | Packager reads from cache, includes in titles.json |
| Title generated after package | POST handler writes to outbox titles.json directly |
| Multiple titles for same session | Use latest (by generated_at); sender already deduplicates |
| Session deleted but title remains | Harmless — orphan entries in titles.json are ignored |
| titles.json doesn't exist yet | Create it; receiver treats missing file as "no titles" |
| Concurrent writes (packager + hook) | Atomic writes prevent corruption; last writer wins but both merge |
| Receiver has own title for remote session | Remote title takes priority (it was generated on the source machine with full context) |

## Testing

- Unit: `titles_io.py` read/write/merge logic
- Integration: POST /title → verify titles.json written in outbox
- Integration: packager → verify titles.json includes cached titles
- Integration: remote_sessions → verify titles loaded from inbox titles.json
- E2E: generate title on sender → verify it appears in receiver's session list
