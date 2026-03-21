# Team Member Customization & Member Pages — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add per-member nickname and color overrides stored in the backend, plus an independent `/members/{user_id}` page showing stats, sessions, and customization UI.

**Architecture:** New `member_preferences` table in `karma.db` keyed by `user_id`. New `/members` API router. Frontend member page at `/members/[user_id]` with inline edit dialog. Expanded 14-color palette. All sync logic (`device_id`, `remote_user_id`) remains untouched.

**Tech Stack:** Python/FastAPI/SQLite (backend), SvelteKit/Svelte 5/Tailwind (frontend)

**Design Doc:** `docs/plans/2026-03-08-team-member-customization-design.md`

---

## Task 1: Database — `member_preferences` table + migration

**Files:**
- Modify: `api/db/schema.py` (line 13: SCHEMA_VERSION, line 274: SCHEMA_SQL, after line 638: new migration)

**Step 1: Add table to SCHEMA_SQL**

In `api/db/schema.py`, inside the `SCHEMA_SQL` string (before the closing `"""`), after the sync_events indexes (line 273), add:

```sql
-- Member display preferences (cosmetic overrides, keyed by user_id not team)
CREATE TABLE IF NOT EXISTS member_preferences (
    user_id     TEXT PRIMARY KEY,
    nickname    TEXT,
    color       TEXT,
    updated_at  TEXT DEFAULT (datetime('now'))
);
```

**Step 2: Add to ensure_schema sync table safety net**

In the `if current_version >= SCHEMA_VERSION:` block (around line 294), add the new CREATE TABLE IF NOT EXISTS alongside the existing sync tables:

```sql
CREATE TABLE IF NOT EXISTS member_preferences (
    user_id TEXT PRIMARY KEY,
    nickname TEXT,
    color TEXT,
    updated_at TEXT DEFAULT (datetime('now'))
);
```

**Step 3: Add migration v23**

After the v22 migration block (after line 638), add:

```python
        if current_version < 23:
            logger.info("Migrating -> v23: adding member_preferences table")
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS member_preferences (
                    user_id     TEXT PRIMARY KEY,
                    nickname    TEXT,
                    color       TEXT,
                    updated_at  TEXT DEFAULT (datetime('now'))
                );
            """)
```

**Step 4: Bump SCHEMA_VERSION**

Change line 13 from `SCHEMA_VERSION = 22` to `SCHEMA_VERSION = 23`.

**Step 5: Verify**

Run: `cd api && python -c "from db.schema import ensure_schema; import sqlite3; conn = sqlite3.connect(':memory:'); conn.row_factory = sqlite3.Row; ensure_schema(conn); print([r['name'] for r in conn.execute(\"SELECT name FROM sqlite_master WHERE type='table'\").fetchall()])"`

Expected: Output includes `member_preferences` in the list.

**Step 6: Commit**

```bash
git add api/db/schema.py
git commit -m "feat(db): add member_preferences table (v23 migration)"
```

---

## Task 2: Backend — CRUD functions for member_preferences

**Files:**
- Create: `api/db/member_queries.py`

**Step 1: Write the CRUD module**

Create `api/db/member_queries.py`:

```python
"""CRUD functions for member_preferences table.

Cosmetic-only overrides (nickname, color) keyed by user_id.
Does NOT modify sync_members, device_id, or any sync logic.
"""

import sqlite3
from typing import Optional


def get_preferences(conn: sqlite3.Connection, user_id: str) -> Optional[dict]:
    """Get display preferences for a member, or None if no overrides."""
    row = conn.execute(
        "SELECT user_id, nickname, color, updated_at FROM member_preferences WHERE user_id = ?",
        (user_id,),
    ).fetchone()
    return dict(row) if row else None


def get_all_preferences(conn: sqlite3.Connection) -> dict[str, dict]:
    """Return all preferences keyed by user_id. For frontend bulk fetch."""
    rows = conn.execute(
        "SELECT user_id, nickname, color, updated_at FROM member_preferences"
    ).fetchall()
    return {r["user_id"]: dict(r) for r in rows}


def upsert_preferences(
    conn: sqlite3.Connection,
    user_id: str,
    nickname: Optional[str] = None,
    color: Optional[str] = None,
) -> dict:
    """Set or update display preferences for a member."""
    conn.execute(
        """INSERT INTO member_preferences (user_id, nickname, color, updated_at)
           VALUES (?, ?, ?, datetime('now'))
           ON CONFLICT(user_id)
           DO UPDATE SET
               nickname = COALESCE(excluded.nickname, member_preferences.nickname),
               color = COALESCE(excluded.color, member_preferences.color),
               updated_at = datetime('now')""",
        (user_id, nickname, color),
    )
    conn.commit()
    return get_preferences(conn, user_id)


def delete_preferences(conn: sqlite3.Connection, user_id: str) -> None:
    """Reset a member's preferences to defaults."""
    conn.execute("DELETE FROM member_preferences WHERE user_id = ?", (user_id,))
    conn.commit()
```

**Step 2: Run a quick test**

Run: `cd api && python -c "
from db.schema import ensure_schema
from db.member_queries import get_preferences, upsert_preferences, get_all_preferences, delete_preferences
import sqlite3
conn = sqlite3.connect(':memory:')
conn.row_factory = sqlite3.Row
ensure_schema(conn)
assert get_preferences(conn, 'alice') is None
result = upsert_preferences(conn, 'alice', nickname='Alice M.', color='emerald')
assert result['nickname'] == 'Alice M.'
assert result['color'] == 'emerald'
all_prefs = get_all_preferences(conn)
assert 'alice' in all_prefs
delete_preferences(conn, 'alice')
assert get_preferences(conn, 'alice') is None
print('All member_queries tests pass')
"`

Expected: `All member_queries tests pass`

**Step 3: Commit**

```bash
git add api/db/member_queries.py
git commit -m "feat(db): add member_preferences CRUD functions"
```

---

## Task 3: Backend — `/members` API router

**Files:**
- Create: `api/routers/members.py`
- Modify: `api/main.py` (line 178: add router registration)

**Step 1: Create the router**

Create `api/routers/members.py`:

```python
"""Members API — display preferences and aggregated member profiles.

Cosmetic-only: never modifies device_id, remote_user_id, or sync logic.
Reads sync_members for team membership, sessions table for stats.
"""

import logging
import sqlite3
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from db.connection import get_writer_db, create_read_connection
from db.member_queries import (
    get_preferences,
    get_all_preferences,
    upsert_preferences,
    delete_preferences,
)

logger = logging.getLogger(__name__)

router = APIRouter()

# ── Valid color names (must match CSS variables --team-{color}) ──

VALID_COLORS = frozenset([
    "coral", "rose", "amber", "cyan", "pink", "lime", "indigo", "teal",
    "emerald", "violet", "orange", "sky", "fuchsia", "slate",
])


# ── Request/Response Models ──


class PreferencesUpdate(BaseModel):
    nickname: Optional[str] = None
    color: Optional[str] = None


class PreferencesResponse(BaseModel):
    user_id: str
    nickname: Optional[str] = None
    color: Optional[str] = None
    updated_at: Optional[str] = None


class MemberStats(BaseModel):
    session_count: int = 0
    project_count: int = 0
    total_messages: int = 0
    last_active: Optional[str] = None


class MemberProfile(BaseModel):
    user_id: str
    device_id: Optional[str] = None
    nickname: Optional[str] = None
    color: Optional[str] = None
    teams: list[str] = []
    stats: MemberStats = MemberStats()
    connected: bool = False


class MemberListItem(BaseModel):
    user_id: str
    device_id: Optional[str] = None
    nickname: Optional[str] = None
    color: Optional[str] = None
    teams: list[str] = []
    session_count: int = 0
    connected: bool = False


# ── Helpers ──


def _get_read_conn() -> sqlite3.Connection:
    return create_read_connection()


def _get_write_conn() -> sqlite3.Connection:
    return get_writer_db()


def _get_member_teams(conn: sqlite3.Connection, user_id: str) -> list[str]:
    """Find all teams a user_id belongs to via sync_members."""
    rows = conn.execute(
        "SELECT DISTINCT team_name FROM sync_members WHERE name = ?",
        (user_id,),
    ).fetchall()
    return [r["team_name"] for r in rows]


def _get_member_device_id(conn: sqlite3.Connection, user_id: str) -> Optional[str]:
    """Get the device_id for a user from sync_members."""
    row = conn.execute(
        "SELECT device_id FROM sync_members WHERE name = ? LIMIT 1",
        (user_id,),
    ).fetchone()
    return row["device_id"] if row else None


def _get_member_stats(conn: sqlite3.Connection, user_id: str) -> dict:
    """Compute stats from sessions table for a remote user."""
    row = conn.execute(
        """SELECT
               COUNT(*) as session_count,
               COUNT(DISTINCT project_encoded_name) as project_count,
               SUM(COALESCE(message_count, 0)) as total_messages,
               MAX(COALESCE(end_time, start_time)) as last_active
           FROM sessions
           WHERE remote_user_id = ?""",
        (user_id,),
    ).fetchone()
    if not row or row["session_count"] == 0:
        return {"session_count": 0, "project_count": 0, "total_messages": 0, "last_active": None}
    return dict(row)


def _get_all_known_members(conn: sqlite3.Connection) -> list[dict]:
    """Get all unique members from sync_members with their teams."""
    rows = conn.execute(
        """SELECT name, device_id, GROUP_CONCAT(team_name) as teams
           FROM sync_members
           GROUP BY name
           ORDER BY name"""
    ).fetchall()
    result = []
    for r in rows:
        teams = r["teams"].split(",") if r["teams"] else []
        result.append({
            "user_id": r["name"],
            "device_id": r["device_id"],
            "teams": teams,
        })
    return result


# ── Endpoints ──


@router.get("", response_model=list[MemberListItem])
async def list_members():
    """List all known team members with preferences and session counts."""
    import asyncio
    loop = asyncio.get_event_loop()

    def _query():
        conn = _get_read_conn()
        try:
            members = _get_all_known_members(conn)
            prefs = get_all_preferences(conn)

            result = []
            for m in members:
                uid = m["user_id"]
                p = prefs.get(uid, {})
                # Get session count
                row = conn.execute(
                    "SELECT COUNT(*) as cnt FROM sessions WHERE remote_user_id = ?",
                    (uid,),
                ).fetchone()
                session_count = row["cnt"] if row else 0

                result.append({
                    "user_id": uid,
                    "device_id": m["device_id"],
                    "nickname": p.get("nickname"),
                    "color": p.get("color"),
                    "teams": m["teams"],
                    "session_count": session_count,
                    "connected": False,  # enriched client-side from /sync/devices
                })
            return result
        finally:
            conn.close()

    return await loop.run_in_executor(None, _query)


@router.get("/preferences", response_model=dict[str, PreferencesResponse])
async def get_all_member_preferences():
    """Bulk fetch all member preferences. Used by frontend for color/nickname cache."""
    import asyncio
    loop = asyncio.get_event_loop()

    def _query():
        conn = _get_read_conn()
        try:
            return get_all_preferences(conn)
        finally:
            conn.close()

    return await loop.run_in_executor(None, _query)


@router.get("/{user_id}", response_model=MemberProfile)
async def get_member(user_id: str):
    """Get full member profile with stats, teams, and preferences."""
    import asyncio
    loop = asyncio.get_event_loop()

    def _query():
        conn = _get_read_conn()
        try:
            teams = _get_member_teams(conn, user_id)
            device_id = _get_member_device_id(conn, user_id)
            stats = _get_member_stats(conn, user_id)
            prefs = get_preferences(conn, user_id)

            if not teams and stats["session_count"] == 0:
                raise HTTPException(404, f"Member '{user_id}' not found")

            return {
                "user_id": user_id,
                "device_id": device_id,
                "nickname": prefs["nickname"] if prefs else None,
                "color": prefs["color"] if prefs else None,
                "teams": teams,
                "stats": stats,
                "connected": False,  # enriched client-side
            }
        finally:
            conn.close()

    return await loop.run_in_executor(None, _query)


@router.put("/{user_id}/preferences", response_model=PreferencesResponse)
async def update_preferences(user_id: str, body: PreferencesUpdate):
    """Update display nickname and/or color for a member."""
    import asyncio
    loop = asyncio.get_event_loop()

    # Validate color if provided
    if body.color and body.color not in VALID_COLORS:
        raise HTTPException(400, f"Invalid color '{body.color}'. Valid: {sorted(VALID_COLORS)}")

    # Validate nickname length
    if body.nickname is not None and len(body.nickname) > 50:
        raise HTTPException(400, "Nickname must be 50 characters or fewer")

    def _update():
        conn = _get_write_conn()
        try:
            return upsert_preferences(conn, user_id, body.nickname, body.color)
        finally:
            conn.close()

    return await loop.run_in_executor(None, _update)


@router.delete("/{user_id}/preferences")
async def reset_preferences(user_id: str):
    """Reset a member's preferences to defaults (hash-based color, original name)."""
    import asyncio
    loop = asyncio.get_event_loop()

    def _delete():
        conn = _get_write_conn()
        try:
            delete_preferences(conn, user_id)
        finally:
            conn.close()

    await loop.run_in_executor(None, _delete)
    return {"status": "ok", "user_id": user_id}
```

**Step 2: Register the router in main.py**

In `api/main.py`, after line 177 (`app.include_router(sync_status.router)`), add:

```python
app.include_router(members.router, prefix="/members", tags=["members"])
```

Also add the import at the top of main.py with the other router imports:

```python
from routers import members
```

**Step 3: Verify the server starts**

Run: `cd api && timeout 5 uvicorn main:app --port 8099 2>&1 | head -5`

Expected: Server starts without import errors.

**Step 4: Commit**

```bash
git add api/routers/members.py api/main.py
git commit -m "feat(api): add /members router with preferences and profile endpoints"
```

---

## Task 4: Backend — Member sessions endpoint

**Files:**
- Modify: `api/routers/members.py` (add sessions endpoint)

**Step 1: Add the sessions endpoint**

Add to the bottom of `api/routers/members.py`:

```python
@router.get("/{user_id}/sessions")
async def get_member_sessions(user_id: str, limit: int = 50, offset: int = 0):
    """List remote sessions for a specific member."""
    import asyncio
    loop = asyncio.get_event_loop()

    def _query():
        conn = _get_read_conn()
        try:
            rows = conn.execute(
                """SELECT s.uuid, s.slug, s.project_encoded_name,
                          s.message_count, s.start_time, s.end_time,
                          s.duration_seconds, s.models_used, s.subagent_count,
                          s.has_todos, s.todo_count, s.is_compacted,
                          s.remote_user_id, s.remote_machine_id,
                          p.path as project_path, p.display_name as project_name
                   FROM sessions s
                   LEFT JOIN projects p ON s.project_encoded_name = p.encoded_name
                   WHERE s.remote_user_id = ?
                   ORDER BY COALESCE(s.end_time, s.start_time) DESC
                   LIMIT ? OFFSET ?""",
                (user_id, limit, offset),
            ).fetchall()

            total_row = conn.execute(
                "SELECT COUNT(*) as cnt FROM sessions WHERE remote_user_id = ?",
                (user_id,),
            ).fetchone()

            sessions = []
            for r in rows:
                d = dict(r)
                # Parse JSON fields
                if d.get("models_used"):
                    try:
                        import json
                        d["models_used"] = json.loads(d["models_used"])
                    except (json.JSONDecodeError, TypeError):
                        d["models_used"] = []
                else:
                    d["models_used"] = []
                sessions.append(d)

            return {
                "sessions": sessions,
                "total": total_row["cnt"] if total_row else 0,
                "limit": limit,
                "offset": offset,
            }
        finally:
            conn.close()

    return await loop.run_in_executor(None, _query)
```

**Step 2: Commit**

```bash
git add api/routers/members.py
git commit -m "feat(api): add GET /members/{user_id}/sessions endpoint"
```

---

## Task 5: Frontend — Expand CSS color palette from 8 to 14

**Files:**
- Modify: `frontend/src/app.css` (after line 175: add 6 new color variables)

**Step 1: Add new CSS variables**

In `frontend/src/app.css`, after line 175 (`--team-teal-subtle: ...`), add:

```css
	--team-emerald: #10b981;
	--team-emerald-subtle: rgba(16, 185, 129, 0.1);
	--team-violet: #8b5cf6;
	--team-violet-subtle: rgba(139, 92, 246, 0.1);
	--team-orange: #f97316;
	--team-orange-subtle: rgba(249, 115, 22, 0.1);
	--team-sky: #0ea5e9;
	--team-sky-subtle: rgba(14, 165, 233, 0.1);
	--team-fuchsia: #d946ef;
	--team-fuchsia-subtle: rgba(217, 70, 239, 0.1);
	--team-slate: #64748b;
	--team-slate-subtle: rgba(100, 116, 139, 0.1);
```

Note: Team colors are not redefined in dark mode (the hex values + rgba subtle variants work in both themes, same as existing 8 colors).

**Step 2: Verify visually**

Run: `cd frontend && npm run dev` and check that the app loads without CSS errors.

**Step 3: Commit**

```bash
git add frontend/src/app.css
git commit -m "feat(css): expand team member color palette from 8 to 14"
```

---

## Task 6: Frontend — Update `utils.ts` color system with overrides

**Files:**
- Modify: `frontend/src/lib/utils.ts` (lines 683-721: palette + function)
- Modify: `frontend/src/lib/api-types.ts` (add MemberPreferences type)

**Step 1: Add types to api-types.ts**

Add near the other sync types (after `RemoteSessionUser` interface, ~line 1841):

```typescript
/** Per-member display preferences (cosmetic overrides) */
export interface MemberPreferences {
	user_id: string;
	nickname?: string | null;
	color?: string | null;
	updated_at?: string | null;
}

/** Full member profile from /members/{user_id} */
export interface MemberProfile {
	user_id: string;
	device_id?: string | null;
	nickname?: string | null;
	color?: string | null;
	teams: string[];
	stats: {
		session_count: number;
		project_count: number;
		total_messages: number;
		last_active?: string | null;
	};
	connected: boolean;
}

/** List item from /members */
export interface MemberListItem {
	user_id: string;
	device_id?: string | null;
	nickname?: string | null;
	color?: string | null;
	teams: string[];
	session_count: number;
	connected: boolean;
}
```

**Step 2: Update palette and color function in utils.ts**

Replace lines 683-721 in `frontend/src/lib/utils.ts`:

```typescript
/** Color palette for team members — 14 colors, avoiding model colors (purple/blue/green) */
const TEAM_MEMBER_PALETTE = [
	'coral',
	'rose',
	'amber',
	'cyan',
	'pink',
	'lime',
	'indigo',
	'teal',
	'emerald',
	'violet',
	'orange',
	'sky',
	'fuchsia',
	'slate'
] as const;

type TeamColor = (typeof TEAM_MEMBER_PALETTE)[number];

export interface TeamMemberColorConfig {
	border: string;
	badge: string;
	text: string;
	bg: string;
}

/** Cache of member preferences fetched from backend */
let _memberPrefsCache: Record<string, { nickname?: string | null; color?: string | null }> = {};
let _prefsCacheLoaded = false;

/** Load member preferences from backend. Call once on app init. */
export async function loadMemberPreferences(apiBase: string): Promise<void> {
	try {
		const res = await fetch(`${apiBase}/members/preferences`);
		if (res.ok) {
			_memberPrefsCache = await res.json();
			_prefsCacheLoaded = true;
		}
	} catch {
		// Silently fail — hash-based fallback will be used
	}
}

/** Set preferences cache directly (e.g., after a PUT update). */
export function updateMemberPrefsCache(userId: string, prefs: { nickname?: string | null; color?: string | null }): void {
	_memberPrefsCache[userId] = prefs;
}

/** Clear a member's cached preferences (after reset). */
export function clearMemberPrefsCache(userId: string): void {
	delete _memberPrefsCache[userId];
}

/** Get display name for a member: nickname override or original user_id. */
export function getMemberDisplayName(userId: string): string {
	const prefs = _memberPrefsCache[userId];
	return prefs?.nickname || userId;
}

function _colorConfigFor(color: TeamColor): TeamMemberColorConfig {
	return {
		border: `var(--team-${color})`,
		badge: `bg-[var(--team-${color}-subtle)] border-[var(--team-${color})]/20`,
		text: `text-[var(--team-${color})]`,
		bg: `var(--team-${color}-subtle)`
	};
}

/**
 * Deterministic hash-based color assignment for team members.
 * Checks preferences cache first for manual override.
 * Same userId always gets the same fallback color.
 */
export function getTeamMemberColor(userId: string): TeamMemberColorConfig {
	// Check for manual override
	const prefs = _memberPrefsCache[userId];
	if (prefs?.color && TEAM_MEMBER_PALETTE.includes(prefs.color as TeamColor)) {
		return _colorConfigFor(prefs.color as TeamColor);
	}

	// Hash-based fallback
	let hash = 0;
	for (let i = 0; i < userId.length; i++) {
		hash = (hash << 5) - hash + userId.charCodeAt(i);
		hash |= 0; // Convert to 32-bit int
	}
	const index = Math.abs(hash) % TEAM_MEMBER_PALETTE.length;
	return _colorConfigFor(TEAM_MEMBER_PALETTE[index]);
}
```

**Step 3: Verify types**

Run: `cd frontend && npm run check`

Expected: No type errors.

**Step 4: Commit**

```bash
git add frontend/src/lib/utils.ts frontend/src/lib/api-types.ts
git commit -m "feat(frontend): expand color palette to 14, add preference overrides to color system"
```

---

## Task 7: Frontend — Load preferences on app init

**Files:**
- Modify: `frontend/src/routes/+layout.svelte` (add preferences loading)

**Step 1: Find the root layout and add preferences loading**

Read `frontend/src/routes/+layout.svelte` to find where to add the init call. Add an `$effect` or `onMount` that calls `loadMemberPreferences`:

```svelte
<script>
	import { loadMemberPreferences } from '$lib/utils';
	import { API_BASE } from '$lib/config';
	import { onMount } from 'svelte';

	// ... existing code ...

	onMount(() => {
		loadMemberPreferences(API_BASE);
	});
</script>
```

Note: This is fire-and-forget. If it fails, the hash-based fallback works seamlessly.

**Step 2: Verify**

Run: `cd frontend && npm run check`

**Step 3: Commit**

```bash
git add frontend/src/routes/+layout.svelte
git commit -m "feat(frontend): load member preferences on app init"
```

---

## Task 8: Frontend — Use nicknames in SessionCard and GlobalSessionCard

**Files:**
- Modify: `frontend/src/lib/components/SessionCard.svelte` (line 45: add nickname lookup)
- Modify: `frontend/src/lib/components/GlobalSessionCard.svelte` (line 58: add nickname lookup)
- Modify: `frontend/src/lib/components/sync/ProjectTeamTab.svelte` (line 112: add nickname)

**Step 1: Update SessionCard.svelte**

Find line 45: `const remoteUserName = $derived(session.remote_user_id ?? null);`

Replace with:

```typescript
const remoteUserName = $derived(
	session.remote_user_id ? getMemberDisplayName(session.remote_user_id) : null
);
```

Add import at top (alongside existing utils imports):

```typescript
import { getMemberDisplayName } from '$lib/utils';
```

(It's likely already importing from `$lib/utils` — just add `getMemberDisplayName` to the existing import.)

**Step 2: Update GlobalSessionCard.svelte**

Same change — find `remoteUserName` derived and replace with `getMemberDisplayName` call. Add to imports.

**Step 3: Update ProjectTeamTab.svelte**

Find where `user.user_id` is displayed (around line 128 where the user name is rendered). Wrap with `getMemberDisplayName(user.user_id)`. Add to imports.

**Step 4: Verify**

Run: `cd frontend && npm run check`

**Step 5: Commit**

```bash
git add frontend/src/lib/components/SessionCard.svelte frontend/src/lib/components/GlobalSessionCard.svelte frontend/src/lib/components/sync/ProjectTeamTab.svelte
git commit -m "feat(frontend): show member nicknames in session cards and team tab"
```

---

## Task 9: Frontend — MemberCustomizeDialog component

**Files:**
- Create: `frontend/src/lib/components/team/MemberCustomizeDialog.svelte`

**Step 1: Create the dialog component**

Create `frontend/src/lib/components/team/MemberCustomizeDialog.svelte`:

```svelte
<script lang="ts">
	import { API_BASE } from '$lib/config';
	import { updateMemberPrefsCache, clearMemberPrefsCache, getTeamMemberColor } from '$lib/utils';
	import { X, RotateCcw, Loader2 } from 'lucide-svelte';

	const PALETTE = [
		'coral', 'rose', 'amber', 'cyan', 'pink', 'lime', 'indigo',
		'teal', 'emerald', 'violet', 'orange', 'sky', 'fuchsia', 'slate'
	] as const;

	let {
		userId,
		currentNickname = null,
		currentColor = null,
		open = $bindable(false),
		onsaved
	}: {
		userId: string;
		currentNickname?: string | null;
		currentColor?: string | null;
		open: boolean;
		onsaved?: () => void;
	} = $props();

	let nickname = $state('');
	let selectedColor = $state<string | null>(null);
	let saving = $state(false);
	let resetting = $state(false);

	$effect(() => {
		if (open) {
			nickname = currentNickname ?? '';
			selectedColor = currentColor ?? null;
		}
	});

	async function handleSave() {
		if (saving) return;
		saving = true;
		try {
			const body: Record<string, string | null> = {};
			if (nickname.trim()) body.nickname = nickname.trim();
			else body.nickname = null;
			if (selectedColor) body.color = selectedColor;

			const res = await fetch(`${API_BASE}/members/${encodeURIComponent(userId)}/preferences`, {
				method: 'PUT',
				headers: { 'Content-Type': 'application/json' },
				body: JSON.stringify(body)
			});

			if (res.ok) {
				const data = await res.json();
				updateMemberPrefsCache(userId, { nickname: data.nickname, color: data.color });
				open = false;
				onsaved?.();
			}
		} catch {
			// best-effort
		} finally {
			saving = false;
		}
	}

	async function handleReset() {
		if (resetting) return;
		resetting = true;
		try {
			const res = await fetch(`${API_BASE}/members/${encodeURIComponent(userId)}/preferences`, {
				method: 'DELETE'
			});
			if (res.ok) {
				clearMemberPrefsCache(userId);
				nickname = '';
				selectedColor = null;
				open = false;
				onsaved?.();
			}
		} catch {
			// best-effort
		} finally {
			resetting = false;
		}
	}
</script>

{#if open}
	<!-- Backdrop -->
	<!-- svelte-ignore a11y_click_events_have_key_events -->
	<!-- svelte-ignore a11y_no_static_element_interactions -->
	<div class="fixed inset-0 z-50 flex items-center justify-center bg-black/40" onclick={() => (open = false)}>
		<!-- Dialog -->
		<!-- svelte-ignore a11y_click_events_have_key_events -->
		<!-- svelte-ignore a11y_no_static_element_interactions -->
		<div
			class="bg-[var(--bg-base)] border border-[var(--border)] rounded-xl shadow-lg w-full max-w-sm p-5"
			onclick={(e) => e.stopPropagation()}
		>
			<div class="flex items-center justify-between mb-4">
				<h3 class="text-sm font-semibold text-[var(--text-primary)]">Customize Member</h3>
				<button
					onclick={() => (open = false)}
					class="p-1 rounded text-[var(--text-muted)] hover:bg-[var(--bg-muted)] transition-colors"
				>
					<X size={16} />
				</button>
			</div>

			<!-- Nickname -->
			<div class="mb-4">
				<label for="nickname" class="block text-xs font-medium text-[var(--text-secondary)] mb-1.5">
					Nickname
				</label>
				<input
					id="nickname"
					type="text"
					bind:value={nickname}
					placeholder={userId}
					maxlength={50}
					class="w-full px-3 py-1.5 text-sm rounded-lg border border-[var(--border)] bg-[var(--bg-subtle)]
						text-[var(--text-primary)] placeholder:text-[var(--text-muted)]
						focus:outline-none focus:border-[var(--accent)] transition-colors"
				/>
				<p class="text-[11px] text-[var(--text-muted)] mt-1">Original: {userId}</p>
			</div>

			<!-- Color Picker -->
			<div class="mb-5">
				<label class="block text-xs font-medium text-[var(--text-secondary)] mb-2">
					Color
				</label>
				<div class="flex flex-wrap gap-2">
					{#each PALETTE as color}
						{@const isSelected = selectedColor === color}
						{@const isDefault = !selectedColor && getTeamMemberColor(userId).border === `var(--team-${color})`}
						<button
							onclick={() => (selectedColor = color)}
							class="w-7 h-7 rounded-full border-2 transition-all
								{isSelected ? 'scale-110 border-[var(--text-primary)]' : isDefault ? 'border-[var(--border-hover)] opacity-80' : 'border-transparent opacity-60 hover:opacity-100'}"
							style="background-color: var(--team-{color})"
							title={color}
							aria-label="Select {color} color"
						/>
					{/each}
				</div>
			</div>

			<!-- Actions -->
			<div class="flex items-center justify-between">
				<button
					onclick={handleReset}
					disabled={resetting}
					class="flex items-center gap-1.5 px-3 py-1.5 text-xs rounded-lg
						text-[var(--text-muted)] hover:text-[var(--text-secondary)] hover:bg-[var(--bg-muted)]
						transition-colors disabled:opacity-50"
				>
					{#if resetting}
						<Loader2 size={12} class="animate-spin" />
					{:else}
						<RotateCcw size={12} />
					{/if}
					Reset to default
				</button>
				<button
					onclick={handleSave}
					disabled={saving}
					class="px-4 py-1.5 text-xs font-medium rounded-lg
						bg-[var(--accent)] text-white hover:bg-[var(--accent-hover)]
						transition-colors disabled:opacity-50"
				>
					{#if saving}
						<Loader2 size={12} class="animate-spin" />
					{:else}
						Save
					{/if}
				</button>
			</div>
		</div>
	</div>
{/if}
```

**Step 2: Verify types**

Run: `cd frontend && npm run check`

**Step 3: Commit**

```bash
git add frontend/src/lib/components/team/MemberCustomizeDialog.svelte
git commit -m "feat(frontend): add MemberCustomizeDialog component"
```

---

## Task 10: Frontend — Update TeamMemberCard with team colors and customize trigger

**Files:**
- Modify: `frontend/src/lib/components/team/TeamMemberCard.svelte`

**Step 1: Add team color and customize dialog**

Replace the full `TeamMemberCard.svelte` content. Key changes:
- Import `getTeamMemberColor`, `getMemberDisplayName` from utils
- Derive the team color from member.name
- Use team color on the avatar circle instead of plain green/muted
- Add click handler on avatar to open customize dialog
- Show nickname if set
- Add link to `/members/{member.name}`

```svelte
<script lang="ts">
	import { API_BASE } from '$lib/config';
	import { Trash2, Loader2, Wifi, WifiOff, Pencil } from 'lucide-svelte';
	import type { SyncTeamMember, SyncDevice } from '$lib/api-types';
	import { getTeamMemberColor, getMemberDisplayName } from '$lib/utils';
	import MemberCustomizeDialog from './MemberCustomizeDialog.svelte';

	let {
		member,
		teamName,
		devices = [],
		isSelf = false,
		onremoved
	}: {
		member: SyncTeamMember;
		teamName: string;
		devices?: SyncDevice[];
		isSelf?: boolean;
		onremoved?: () => void;
	} = $props();

	let confirmRemove = $state(false);
	let removing = $state(false);
	let customizeOpen = $state(false);

	// Enrich with live device connection data
	let deviceInfo = $derived(devices.find((d) => d.device_id === member.device_id));
	let isConnected = $derived(deviceInfo?.connected ?? member.connected ?? false);
	let teamColor = $derived(getTeamMemberColor(member.name));
	let displayName = $derived(getMemberDisplayName(member.name));

	async function handleRemove() {
		if (removing) return;
		removing = true;

		try {
			const res = await fetch(
				`${API_BASE}/sync/teams/${encodeURIComponent(teamName)}/members/${encodeURIComponent(member.name)}`,
				{ method: 'DELETE' }
			);

			if (res.ok) {
				onremoved?.();
			}
		} catch {
			// best-effort
		} finally {
			removing = false;
			confirmRemove = false;
		}
	}
</script>

<div
	class="flex items-center justify-between p-3 rounded-lg border border-[var(--border)] bg-[var(--bg-base)]"
>
	<div class="flex items-center gap-3">
		<button
			onclick={() => (customizeOpen = true)}
			class="w-8 h-8 rounded-full flex items-center justify-center text-xs font-semibold
				transition-transform hover:scale-110 cursor-pointer"
			style="background-color: {teamColor.bg}; color: {teamColor.border}"
			title="Customize {displayName}"
		>
			{member.name.charAt(0).toUpperCase()}
		</button>
		<div>
			<div class="flex items-center gap-2">
				<a
					href="/members/{encodeURIComponent(member.name)}"
					class="text-sm font-medium text-[var(--text-primary)] hover:text-[var(--accent)] transition-colors"
				>
					{displayName}
					{#if displayName !== member.name}
						<span class="text-[11px] text-[var(--text-muted)]">({member.name})</span>
					{/if}
					{#if isSelf}
						<span class="text-xs text-[var(--text-muted)]">(you)</span>
					{/if}
				</a>
				<span
					class="flex items-center gap-1 text-xs {isConnected || isSelf
						? 'text-[var(--success)]'
						: 'text-[var(--text-muted)]'}"
				>
					{#if isConnected || isSelf}
						<Wifi size={12} />
						Online
					{:else}
						<WifiOff size={12} />
						Offline
					{/if}
				</span>
			</div>
			{#if member.device_id}
				<p class="text-[11px] font-mono text-[var(--text-muted)]">
					{member.device_id.length > 20 ? member.device_id.slice(0, 20) + '...' : member.device_id}
				</p>
			{/if}
		</div>
	</div>

	<div class="flex items-center gap-1">
		<!-- Customize button -->
		<button
			onclick={() => (customizeOpen = true)}
			class="p-1.5 rounded text-[var(--text-muted)] hover:text-[var(--accent)] hover:bg-[var(--accent-subtle)] transition-colors"
			title="Customize display"
			aria-label="Customize {displayName}"
		>
			<Pencil size={14} />
		</button>

		{#if !isSelf}
			{#if confirmRemove}
				<div class="flex items-center gap-1.5">
					<button
						onclick={handleRemove}
						disabled={removing}
						class="px-2 py-1 text-xs font-medium rounded bg-[var(--error)] text-white hover:bg-[var(--error)]/80 transition-colors disabled:opacity-50"
					>
						{#if removing}
							<Loader2 size={12} class="animate-spin" />
						{:else}
							Remove
						{/if}
					</button>
					<button
						onclick={() => (confirmRemove = false)}
						class="px-2 py-1 text-xs rounded text-[var(--text-muted)] hover:bg-[var(--bg-muted)] transition-colors"
					>
						Cancel
					</button>
				</div>
			{:else}
				<button
					onclick={() => (confirmRemove = true)}
					class="p-1.5 rounded text-[var(--text-muted)] hover:text-[var(--error)] hover:bg-[var(--error)]/10 transition-colors"
					title="Remove member"
					aria-label="Remove member {displayName}"
				>
					<Trash2 size={14} />
				</button>
			{/if}
		{/if}
	</div>
</div>

<MemberCustomizeDialog
	userId={member.name}
	bind:open={customizeOpen}
/>
```

**Step 2: Verify types**

Run: `cd frontend && npm run check`

**Step 3: Commit**

```bash
git add frontend/src/lib/components/team/TeamMemberCard.svelte
git commit -m "feat(frontend): update TeamMemberCard with team colors, nickname display, and customize trigger"
```

---

## Task 11: Frontend — Member profile page

**Files:**
- Create: `frontend/src/routes/members/[user_id]/+page.server.ts`
- Create: `frontend/src/routes/members/[user_id]/+page.svelte`

**Step 1: Create the data loader**

Create `frontend/src/routes/members/[user_id]/+page.server.ts`:

```typescript
import { API_BASE } from '$lib/config';
import { error } from '@sveltejs/kit';
import type { PageServerLoad } from './$types';

export const load: PageServerLoad = async ({ params, fetch }) => {
	const userId = params.user_id;

	const [profileRes, sessionsRes] = await Promise.all([
		fetch(`${API_BASE}/members/${encodeURIComponent(userId)}`),
		fetch(`${API_BASE}/members/${encodeURIComponent(userId)}/sessions?limit=50`)
	]);

	if (!profileRes.ok) {
		throw error(profileRes.status, `Member '${userId}' not found`);
	}

	const profile = await profileRes.json();
	const sessionsData = sessionsRes.ok ? await sessionsRes.json() : { sessions: [], total: 0 };

	return {
		profile,
		sessions: sessionsData.sessions,
		totalSessions: sessionsData.total,
		userId
	};
};
```

**Step 2: Create the page component**

Create `frontend/src/routes/members/[user_id]/+page.svelte`:

```svelte
<script lang="ts">
	import { Activity, FolderGit2, MessageSquare, Clock, Wifi, WifiOff, Pencil } from 'lucide-svelte';
	import { getTeamMemberColor, getMemberDisplayName, formatRelativeTime } from '$lib/utils';
	import SessionCard from '$lib/components/SessionCard.svelte';
	import MemberCustomizeDialog from '$lib/components/team/MemberCustomizeDialog.svelte';
	import type { PageData } from './$types';

	let { data }: { data: PageData } = $props();

	let profile = $derived(data.profile);
	let sessions = $derived(data.sessions);
	let teamColor = $derived(getTeamMemberColor(data.userId));
	let displayName = $derived(getMemberDisplayName(data.userId));

	let customizeOpen = $state(false);

	function handleSaved() {
		// Force reactivity refresh — invalidate the page
		// The preferences cache is already updated by the dialog
	}
</script>

<svelte:head>
	<title>{displayName} — Claude Code Karma</title>
</svelte:head>

<div class="max-w-4xl mx-auto px-4 py-6 space-y-6">
	<!-- Header -->
	<div class="flex items-start justify-between">
		<div class="flex items-center gap-4">
			<div
				class="w-14 h-14 rounded-full flex items-center justify-center text-xl font-bold"
				style="background-color: {teamColor.bg}; color: {teamColor.border}"
			>
				{data.userId.charAt(0).toUpperCase()}
			</div>
			<div>
				<div class="flex items-center gap-2">
					<h1 class="text-xl font-semibold text-[var(--text-primary)]">{displayName}</h1>
					{#if displayName !== data.userId}
						<span class="text-sm text-[var(--text-muted)]">@{data.userId}</span>
					{/if}
				</div>
				<div class="flex items-center gap-3 mt-1">
					<span class="flex items-center gap-1 text-xs {profile.connected ? 'text-[var(--success)]' : 'text-[var(--text-muted)]'}">
						{#if profile.connected}
							<Wifi size={12} /> Online
						{:else}
							<WifiOff size={12} /> Offline
						{/if}
					</span>
					{#each profile.teams as team}
						<a
							href="/team/{encodeURIComponent(team)}"
							class="px-2 py-0.5 text-[11px] font-medium rounded-full
								bg-[var(--accent-subtle)] text-[var(--accent)] hover:bg-[var(--accent-muted)] transition-colors"
						>
							{team}
						</a>
					{/each}
				</div>
			</div>
		</div>
		<button
			onclick={() => (customizeOpen = true)}
			class="flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded-lg
				border border-[var(--border)] text-[var(--text-secondary)]
				hover:bg-[var(--bg-muted)] transition-colors"
		>
			<Pencil size={12} />
			Customize
		</button>
	</div>

	<!-- Stats -->
	<div class="grid grid-cols-4 gap-3">
		<div class="p-3 rounded-lg border border-[var(--border)] bg-[var(--bg-subtle)]">
			<div class="flex items-center gap-2 text-[var(--text-muted)] mb-1">
				<Activity size={14} />
				<span class="text-[11px] font-medium uppercase tracking-wide">Sessions</span>
			</div>
			<p class="text-lg font-semibold text-[var(--text-primary)]">{profile.stats.session_count}</p>
		</div>
		<div class="p-3 rounded-lg border border-[var(--border)] bg-[var(--bg-subtle)]">
			<div class="flex items-center gap-2 text-[var(--text-muted)] mb-1">
				<FolderGit2 size={14} />
				<span class="text-[11px] font-medium uppercase tracking-wide">Projects</span>
			</div>
			<p class="text-lg font-semibold text-[var(--text-primary)]">{profile.stats.project_count}</p>
		</div>
		<div class="p-3 rounded-lg border border-[var(--border)] bg-[var(--bg-subtle)]">
			<div class="flex items-center gap-2 text-[var(--text-muted)] mb-1">
				<MessageSquare size={14} />
				<span class="text-[11px] font-medium uppercase tracking-wide">Messages</span>
			</div>
			<p class="text-lg font-semibold text-[var(--text-primary)]">{profile.stats.total_messages}</p>
		</div>
		<div class="p-3 rounded-lg border border-[var(--border)] bg-[var(--bg-subtle)]">
			<div class="flex items-center gap-2 text-[var(--text-muted)] mb-1">
				<Clock size={14} />
				<span class="text-[11px] font-medium uppercase tracking-wide">Last seen</span>
			</div>
			<p class="text-sm font-semibold text-[var(--text-primary)]">
				{#if profile.stats.last_active}
					{formatRelativeTime(profile.stats.last_active)}
				{:else}
					Never
				{/if}
			</p>
		</div>
	</div>

	<!-- Sessions -->
	<div>
		<h2 class="text-sm font-semibold text-[var(--text-secondary)] mb-3">
			Sessions ({data.totalSessions})
		</h2>
		{#if sessions.length === 0}
			<p class="text-sm text-[var(--text-muted)] py-8 text-center">No sessions found for this member.</p>
		{:else}
			<div class="space-y-2">
				{#each sessions as session (session.uuid)}
					<SessionCard {session} mode="compact" />
				{/each}
			</div>
		{/if}
	</div>
</div>

<MemberCustomizeDialog
	userId={data.userId}
	currentNickname={profile.nickname}
	currentColor={profile.color}
	bind:open={customizeOpen}
	onsaved={handleSaved}
/>
```

**Step 3: Verify types**

Run: `cd frontend && npm run check`

Note: There may be type issues with `SessionCard` props if `session` shape doesn't match exactly. The member sessions endpoint returns a subset of fields — you may need to cast or add optional fields. Adjust as needed during implementation.

**Step 4: Commit**

```bash
git add frontend/src/routes/members/
git commit -m "feat(frontend): add /members/[user_id] profile page with stats, sessions, and customization"
```

---

## Task 12: Integration verification

**Step 1: Start the API**

Run: `cd api && uvicorn main:app --reload --port 8000`

**Step 2: Test the endpoints manually**

```bash
# List members (may be empty if no teams configured)
curl http://localhost:8000/members

# Get all preferences (empty initially)
curl http://localhost:8000/members/preferences

# Set a preference
curl -X PUT http://localhost:8000/members/testuser/preferences \
  -H 'Content-Type: application/json' \
  -d '{"nickname": "Test User", "color": "emerald"}'

# Verify it was saved
curl http://localhost:8000/members/preferences

# Reset
curl -X DELETE http://localhost:8000/members/testuser/preferences

# Verify reset
curl http://localhost:8000/members/preferences
```

**Step 3: Start the frontend**

Run: `cd frontend && npm run dev`

**Step 4: Visual check**

1. Visit `/team/{team_name}` — member cards should show team-colored avatars with pencil edit button
2. Click avatar or pencil → customize dialog opens
3. Set nickname and color → save → badge and avatar update
4. Click member name → navigates to `/members/{user_id}`
5. Member page shows stats, sessions, customize button

**Step 5: Commit final state**

```bash
git add -A
git commit -m "feat: team member customization — nicknames, color picker, and member profile pages"
```

---

## Summary of All Files

### New Files (5)
| File | Purpose |
|------|---------|
| `api/db/member_queries.py` | CRUD for member_preferences table |
| `api/routers/members.py` | /members API router |
| `frontend/src/lib/components/team/MemberCustomizeDialog.svelte` | Nickname + color edit dialog |
| `frontend/src/routes/members/[user_id]/+page.server.ts` | Member page data loader |
| `frontend/src/routes/members/[user_id]/+page.svelte` | Member profile page |

### Modified Files (7)
| File | Change |
|------|--------|
| `api/db/schema.py` | Add member_preferences table + v23 migration |
| `api/main.py` | Register members router |
| `frontend/src/app.css` | Add 6 new team color CSS variables |
| `frontend/src/lib/utils.ts` | Expand palette 8→14, add preference override system |
| `frontend/src/lib/api-types.ts` | Add MemberPreferences, MemberProfile, MemberListItem types |
| `frontend/src/lib/components/team/TeamMemberCard.svelte` | Team colors, nickname, link, customize trigger |
| `frontend/src/routes/+layout.svelte` | Load member preferences on app init |

### Display-Only Changes (3)
| File | Change |
|------|--------|
| `frontend/src/lib/components/SessionCard.svelte` | Use getMemberDisplayName for remote badge |
| `frontend/src/lib/components/GlobalSessionCard.svelte` | Use getMemberDisplayName for remote badge |
| `frontend/src/lib/components/sync/ProjectTeamTab.svelte` | Use getMemberDisplayName for user labels |

### NOT Touched (sync safety)
- `api/services/remote_sessions.py`
- `api/db/sync_queries.py`
- `api/routers/sync_status.py`
- Any `device_id` or `remote_user_id` resolution logic
