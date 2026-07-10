# Member Page Improvements — Design Spec

**Date**: 2026-03-19
**Status**: Approved

## Problem

The member detail page has several issues:
1. **Sessions don't show up for remote members** — `MemberSessionsTab` queries with `profile.user_id` (e.g., `jay`) but the DB stores `remote_user_id` as the full `member_tag` (e.g., `jay.mac`)
2. **URL uses `device_id`** — opaque Syncthing hash, not human-readable. Complex fallback logic in the API when device_id is empty
3. **Team members tab doesn't link to member pages** — clicking a member card does nothing
4. **No sync health info** — the overview tab lacks unsynced counts, sync direction, last packaged time
5. **Member color not consistently applied** — should use `getTeamMemberHexColor` across all surfaces

## Decisions

| Decision | Choice |
|----------|--------|
| URL identifier | `member_tag` primary, `device_id` fallback (strict regex detection) |
| Session query fix | Use `member_tag` instead of `user_id` for remote session lookup |
| Team members nav | Click name/avatar → `/members/{member_tag}`, actions stay separate |
| Header metadata | Identity (member_tag, machine, teams) + sync health (unsynced, direction, last synced) |
| Stats additions | Add "Unsynced" card + Sync Health section to Overview tab (self only) |
| Member color | Consistent `--member-color` via `getTeamMemberHexColor(user_id)` on all member surfaces |
| Collision guard | Reject member join if member_tag already exists for a different device_id |

## Design

### 1. API — Member identifier resolution

**Endpoint**: `GET /sync/members/{identifier}` (replaces `GET /sync/members/{device_id}`)

**Lookup logic**:
1. Detect Syncthing device_id using strict regex: `^[A-Z2-7]{7}(-[A-Z2-7]{7}){7}$` (base32, exactly 8 groups of 7 chars). If match → query `sync_members` by `device_id`
2. Otherwise → treat as `member_tag`, query via new `MemberRepository.get_all_by_member_tag(member_tag)` method (`SELECT * FROM sync_members WHERE member_tag = ?` — returns list across all teams)
3. Self-detection: compare resolved `member_tag` against `config.member_tag`

**URL safety**: `member_tag` format is `{user_id}.{machine_tag}` where both parts are `[a-z0-9-]+`. Dots are safe in URL path segments per RFC 3986. No `encodeURIComponent` needed for path, but SvelteKit will URL-decode automatically so this is transparent.

**Backward compatibility**: Old bookmarked URLs like `/members/MFZWI3D-BONSGYC-...` still work because the strict regex detects device_id format and does the lookup accordingly. This is by design.

**New profile response fields**:
```json
{
  "member_tag": "jay.mac",
  "user_id": "jay",
  "machine_tag": "mac",
  "device_id": "DEVICE-7X...",
  "connected": true,
  "is_you": true,
  "unsynced_count": 3,
  "last_packaged_at": "2026-03-19T10:00:00Z",
  "sync_direction": "both",
  "teams": [...],
  "stats": {...},
  "session_stats": [...],
  "activity": [...]
}
```

**`unsynced_count`** (self only, `null` for remote members):
- Reuses `_get_active_counts()` and `_count_packaged()` helpers from `routers/sync_teams.py`
- Import these helpers directly — they're pure functions (filesystem reads + DB queries)
- Sum gap across all projects in all teams for this member
- Performance: disk scan of live-sessions dir (~10 files) + outbox dir glob per project. Acceptable for a profile page that loads once.

**`project_sync`** (self only, `null` for remote members — eliminates N+1 API calls):
- Array of per-project sync status included directly in the profile response
- Each entry: `{"team_name", "git_identity", "encoded_name", "name", "local_count", "packaged_count", "active_count", "gap"}`
- Computed server-side using the same helpers as `project-status` endpoint
- The frontend Sync Health card reads this data directly — no separate `GET /sync/teams/{team}/project-status` calls needed
- `unsynced_count` is derived as `sum(p.gap for p in project_sync)`

**`last_packaged_at`** (self only, `null` for remote members):
- `session_packaged` events are logged by the local user who did the packaging, not the remote member
- Query: `SELECT MAX(created_at) FROM sync_events WHERE event_type='session_packaged'` (no member filter needed — all packaged events are from self)

**`sync_direction`** aggregation precedence:
1. Collect all accepted subscriptions for this member
2. Get unique direction values: `{sub.direction for sub in subs}`
3. If only one unique value → return that value ("both", "send", or "receive")
4. If multiple distinct values → return "mixed"
5. If no accepted subscriptions → return `null`

**Activity and settings endpoints**: Same identifier resolution — detect device_id regex first, fall back to member_tag.

**Member creation guard**: In the join/add-member flow, before creating a member, check: `SELECT device_id FROM sync_members WHERE member_tag = ? AND device_id != ? LIMIT 1`. If found → return 409 "member_tag already registered to a different device".

### 2. API — List members endpoint update

**Endpoint**: `GET /sync/members` (listing)

**Current issue**: Response does not include `member_tag`. It only returns `name`, `device_id`, `connected`, `is_you`, `team_count`, `teams`, `added_at`.

**Fix**: Add `member_tag` and `machine_tag` to the listing response. Change deduplication from `device_id` to `member_tag` (matching the frontend's new needs).

### 3. API + Indexer — Normalize `remote_user_id` to `member_tag`

**Root cause**: The `_resolve_user_id()` function in `api/services/remote_sessions.py` has 3 resolution paths that store **different formats** in the `remote_user_id` column:

| Priority | Condition | Stores | Example |
|----------|-----------|--------|---------|
| 1 | DB + device_id match | `member_tag` | `jay.mac` |
| 2 | Manifest only (no DB match) | `user_id` | `jay` |
| 3 | Dir name fallback | `user_id` | `jay` |

This means the same remote member can have sessions stored under both `jay` and `jay.mac` depending on timing. A frontend-only fix (sending `member_tag`) would fix Priority 1 sessions but break Priority 2/3. Sending `user_id` (current behavior) fixes 2/3 but breaks 1.

**Fix (3 parts)**:

1. **Normalize `_resolve_user_id()`** (`api/services/remote_sessions.py`): In Priority 2 and 3 paths, when `resolved` is a bare `user_id` without a dot, attempt a DB lookup via `SELECT member_tag FROM sync_members WHERE user_id = ? LIMIT 1`. If found, use the full `member_tag`. This ensures all new sessions get indexed with `member_tag`.

2. **Schema v20 migration** (`api/db/schema.py`): Add a one-time fixup that normalizes existing stale values:
   ```sql
   UPDATE sessions SET remote_user_id = (
       SELECT m.member_tag FROM sync_members m
       WHERE m.user_id = sessions.remote_user_id
       LIMIT 1
   ) WHERE source = 'remote'
     AND remote_user_id NOT LIKE '%.%'
     AND EXISTS (SELECT 1 FROM sync_members m WHERE m.user_id = sessions.remote_user_id);
   ```
   This updates bare `user_id` values to full `member_tag` where a match exists. Runs once on startup (seconds).

3. **Frontend fix** (`MemberSessionsTab.svelte`): Send `profile.member_tag` as the `user` param. Now that `remote_user_id` is always `member_tag`, this matches correctly.

**Comment in indexer.py**: Add a note explaining that `remote_user_id` should always be `member_tag` format to prevent future regressions.

### 4. Frontend — Route rename

**Route**: `frontend/src/routes/members/[device_id]/` → `frontend/src/routes/members/[member_tag]/`

- `+page.server.ts`: `params.member_tag` → `GET /sync/members/{member_tag}`
- `+page.svelte`: breadcrumb shows member_tag, `{#each}` key on `member.member_tag`

**Members listing** (`/members/+page.svelte`):
- Card links: `/members/{member.member_tag}` (was `/members/{member.device_id}`)
- Deduplication key: `member_tag` (was `device_id`)

### 5. Frontend — Team Members Tab navigation

**Component**: `TeamMembersTab.svelte`

- Member name becomes an `<a>` tag: `href="/members/{member.member_tag}"`
- Avatar becomes clickable with same link
- Hover: name underline + avatar ring glow using `getTeamMemberHexColor(member.user_id)`
- Action buttons (remove member) stay separate, not part of the link

### 6. Frontend — Member Detail Page header

**Header metadata** (two conceptual rows):
- **Row 1**: Display name + badges (You, Online/Offline)
- **Row 2**: `member_tag` · Machine: `machine_tag` · N teams (link to Teams tab) · N unsynced (yellow, self only) · Direction: `sync_direction` · Last synced: relative time (self only)

**Avatar**: Uses `getTeamMemberHexColor(user_id)` for background gradient. Scopes `--member-color` CSS custom properties to the page root.

### 7. Frontend — Overview tab additions

**Stats row** (4 cards):
- Total Sessions | Sent | Received | **Unsynced** (self) or **Projects** (remote)
- Unsynced card uses yellow/warning accent when > 0, grey when 0

**Sync Health card** (new, self only):
- Header: "Sync Health" + "Sync Now" button
- Per-project rows: project name, `packaged/local` count, gap badge
- Data: reads directly from `profile.project_sync` array (included in profile response — no extra API calls)
- "Sync Now" calls `POST /sync/package`, then re-fetches the profile to refresh counts

**Remote member view** (not self):
- Instead of Sync Health card, show "Sessions from {name}" — received counts per project
- Data from `profile.teams[].projects[].session_count`

### 8. Navigation and breadcrumbs

**Breadcrumb patterns**:

| Page | Breadcrumbs |
|------|-------------|
| `/members` | Dashboard / Members |
| `/members/{member_tag}` | Dashboard / Members / `{user_id}` (`member_tag` as tooltip) |
| `/team/{name}` | Dashboard / Teams / `{name}` |

**Cross-navigation links**:
1. Team Members Tab → click name/avatar → `/members/{member_tag}`
2. Member Page Teams tab → click team card → `/team/{name}`
3. Member Page header "N teams" → switches to Teams tab
4. Members listing → click card → `/members/{member_tag}`

## Files to Create/Modify

| File | Action | Description |
|------|--------|-------------|
| `api/services/remote_sessions.py` | Modify | Normalize `_resolve_user_id()` to always return `member_tag` when member exists in DB |
| `api/db/schema.py` | Modify | Add v20 migration to fix stale `remote_user_id` values (bare user_id → member_tag) |
| `api/repositories/member_repo.py` | Modify | Add `get_all_by_member_tag(member_tag)` and `get_by_user_id(user_id)` methods |
| `api/routers/sync_members.py` | Modify | Identifier resolution (regex detect + member_tag lookup), new profile fields (member_tag, machine_tag, unsynced_count, last_packaged_at, sync_direction, project_sync), list endpoint adds member_tag/machine_tag, collision guard |
| `frontend/src/routes/members/[member_tag]/+page.svelte` | Rename+Modify | Route rename, updated breadcrumbs, header metadata |
| `frontend/src/routes/members/[member_tag]/+page.server.ts` | Rename+Modify | Param change to member_tag |
| `frontend/src/routes/members/+page.svelte` | Modify | Card links and dedup use member_tag |
| `frontend/src/lib/api-types.ts` | Modify | Add member_tag, machine_tag, unsynced_count, last_packaged_at, sync_direction, project_sync to MemberProfile |
| `frontend/src/lib/components/team/TeamMembersTab.svelte` | Modify | Name/avatar become links to /members/{member_tag} with member color |
| `frontend/src/lib/components/team/MemberSessionsTab.svelte` | Modify | Fix: use member_tag instead of user_id for remote session query |
| `frontend/src/lib/components/team/MemberOverviewTab.svelte` | Modify | Add Unsynced stat card, Sync Health card (self using profile.project_sync), received summary (remote) |
| `api/tests/test_member_identifier.py` | Create | Tests for identifier resolution, collision guard, list endpoint |
| `api/tests/test_remote_user_id_normalization.py` | Create | Tests for `_resolve_user_id` normalization and v20 migration |

## Out of Scope

- Member-to-member messaging or direct session sharing
- Historical sync timeline (when each session was packaged/received)
- Member permission roles beyond leader/member
- Offline session queuing UI
