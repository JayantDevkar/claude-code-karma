# Team Member Customization & Member Pages

**Date**: 2026-03-08
**Status**: Approved

## Problem

Team members are displayed with auto-generated hash-based colors and raw user IDs (e.g., Syncthing device names). Users cannot rename members locally or choose display colors. There's also no dedicated page to view a member's activity.

## Decisions

- **Storage**: Backend `member_preferences` table in `karma.db` (not localStorage, not sync-config)
- **Features**: Nickname + Color picker (no avatar customization)
- **Navigation**: Independent `/members/{user_id}` pages (not nested under teams)
- **Palette**: Expanded from 8 to 14 colors
- **Safety**: `device_id` and `remote_user_id` never modified. All sync logic untouched.

## Data Layer

### New Table: `member_preferences`

```sql
CREATE TABLE IF NOT EXISTS member_preferences (
    user_id     TEXT PRIMARY KEY,   -- matches remote_user_id / member.name
    nickname    TEXT,               -- local display name override (nullable)
    color       TEXT,               -- palette color name e.g. "emerald" (nullable)
    updated_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

### New API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/members` | List all known members (join sync_members + preferences) |
| `GET` | `/members/{user_id}` | Member profile: stats, teams, preferences |
| `GET` | `/members/{user_id}/sessions` | Their remote sessions |
| `PUT` | `/members/{user_id}/preferences` | Update nickname and/or color |

### `/members/{user_id}` Response Shape

```json
{
  "user_id": "alice",
  "device_id": "ABC123...",
  "nickname": "Alice M.",
  "color": "emerald",
  "teams": ["frontend-team", "backend-team"],
  "stats": {
    "session_count": 42,
    "last_active": "2026-03-07T...",
    "project_count": 3,
    "total_messages": 156
  },
  "connected": true
}
```

## Expanded Color Palette

### Existing 8 colors (unchanged)
coral, rose, amber, cyan, pink, lime, indigo, teal

### New 6 colors
emerald, violet, orange, sky, fuchsia, slate

Each gets `--team-{name}` and `--team-{name}-subtle` CSS variables in both light and dark mode.

### Color Function Changes

`getTeamMemberColor(userId)` behavior:
1. Check preferences cache for color override
2. If override exists, return config for that color
3. If no override, hash-based fallback (now mod 14)

**Note**: Expanding palette from 8→14 shifts hash assignments for users without overrides. Acceptable since the feature introduces manual overrides.

## Frontend: Member Page

### Route: `/members/[user_id]/`

```
┌─────────────────────────────────────────────────┐
│  [Avatar]  Alice M.  (@alice)     [Edit button] │
│  ● Online  •  frontend-team  •  backend-team    │
├─────────────────────────────────────────────────┤
│  Stats Row                                       │
│  ┌──────┐ ┌──────────┐ ┌────────┐ ┌───────────┐│
│  │ 42   │ │ 3        │ │ 156    │ │ Mar 7     ││
│  │ Sess │ │ Projects │ │ Msgs   │ │ Last seen ││
│  └──────┘ └──────────┘ └────────┘ └───────────┘│
├─────────────────────────────────────────────────┤
│  Sessions (reusing SessionCard component)        │
│  ┌─ Session 1 ──────────────────────────────┐   │
│  └──────────────────────────────────────────────┘│
│  ┌─ Session 2 ──────────────────────────────┐   │
│  └──────────────────────────────────────────────┘│
└─────────────────────────────────────────────────┘
```

### Customize Dialog (MemberCustomizeDialog.svelte)

```
┌─────────────────────────────┐
│  Customize Member           │
│                             │
│  Nickname: [Alice M.    ]   │
│  (Original: alice)          │
│                             │
│  Color:                     │
│  ● ● ● ● ● ● ●            │
│  ● ● ● ● ● ● ●            │
│  (14 color swatches)        │
│                             │
│  [Reset to default] [Save]  │
└─────────────────────────────┘
```

Triggered from:
- Edit button on member page
- Click on avatar in TeamMemberCard

## Navigation Flow

```
/team                     → list all teams
/team/{name}              → team detail (members, projects)
  └ member cards link to  → /members/{user_id}
/members/{user_id}        → member profile
  ├ Stats (sessions, last active, tools)
  ├ Customize (nickname, color)
  ├ Teams (badges showing membership)
  └ Sessions list (all projects)
```

## Files Changed

### Backend — New Files
- `api/routers/members.py` — member router (list, detail, preferences)
- `api/db/member_queries.py` — CRUD for member_preferences table

### Backend — Modified Files
- `api/db/schema.py` — add member_preferences table creation
- `api/main.py` — register members router

### Frontend — New Files
- `frontend/src/routes/members/[user_id]/+page.svelte` — member page
- `frontend/src/routes/members/[user_id]/+page.server.ts` — data loader
- `frontend/src/lib/components/team/MemberCustomizeDialog.svelte` — edit modal

### Frontend — Modified Files
- `frontend/src/lib/utils.ts` — expand palette 8→14, add override lookup
- `frontend/src/app.css` — add 6 new team color CSS variables (light + dark)
- `frontend/src/lib/api-types.ts` — add MemberPreferences, MemberProfile types
- `frontend/src/lib/components/team/TeamMemberCard.svelte` — use team colors on avatar, link to member page
- `frontend/src/lib/components/SessionCard.svelte` — show nickname in remote badge
- `frontend/src/lib/components/GlobalSessionCard.svelte` — show nickname in remote badge
- `frontend/src/lib/components/sync/ProjectTeamTab.svelte` — show nickname override

### NOT Touched (Sync Safety)
- `api/services/remote_sessions.py`
- `api/db/sync_queries.py`
- `api/routers/sync_status.py`
- Any device_id or remote_user_id resolution logic
- Any Syncthing integration code
