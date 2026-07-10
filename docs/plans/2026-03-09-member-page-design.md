# Member Page — Tab-Based Detail View

**Date**: 2026-03-09
**Status**: Approved
**Scope**: Read-only member page (customization deferred to follow-up)

## Problem

Members are only visible inline on team detail pages. There's no dedicated page to view a member's full activity, sessions, team memberships, and contribution history.

## Decisions

- **Route**: `/members/[user_id]/` — independent of teams
- **Navigation**: TeamMembersTab cards link to member page (no sidebar entry)
- **Layout**: Color-themed profile header + 4 tabs (Overview, Sessions, Teams, Activity)
- **Color**: Uses existing 16-color palette — member's hash-assigned color themes the entire page
- **Scope**: Read-only. No customization (nickname/color picker) in this pass.
- **Data**: No new tables. Aggregates from existing sync_members, sync_events, session-stats, devices.

## Data Requirements

### Existing Endpoints (reused)

| Endpoint | Data |
|----------|------|
| `GET /sync/teams` | All teams → filter to teams containing this member |
| `GET /sync/devices` | Connection status, bytes transferred |
| `GET /sync/teams/{team}/session-stats` | Per-member daily sent/received stats |
| `GET /sync/teams/{team}/activity` | Sync events filtered by member |
| `GET /sync/teams/{team}/project-status` | Per-project sync stats with member breakdown |

### New Endpoint

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/sync/members/{user_id}` | Aggregated member profile: teams, stats, device info |

Response shape:
```json
{
  "user_id": "alice",
  "device_id": "ABC123...",
  "connected": true,
  "in_bytes_total": 1234567,
  "out_bytes_total": 3456789,
  "teams": [
    {
      "name": "frontend-team",
      "member_count": 3,
      "project_count": 2,
      "online_count": 2,
      "projects": [
        { "encoded_name": "project-alpha", "name": "project-alpha", "received_count": 12 }
      ]
    }
  ],
  "stats": {
    "total_sessions": 42,
    "total_projects": 3,
    "last_active": "2026-03-07T..."
  },
  "session_stats": [
    { "date": "2026-03-09", "packaged": 2, "received": 1 }
  ],
  "activity": [
    { "id": 1, "event_type": "session_received", "team_name": "frontend-team", "created_at": "..." }
  ]
}
```

## Page Layout

### Profile Header (always visible above tabs)

```
┌─────────────────────────────────────────────────────┐
│  ← Back to {team}                                    │
│                                                      │
│  ┌─ Profile Card (left border: member color) ─────┐ │
│  │  [Avatar: initial + color ring]                 │ │
│  │  alice  •  ● Online  •  ABC12...7DEF            │ │
│  │  ↓ 1.2 MB received  •  ↑ 3.4 MB sent           │ │
│  └─────────────────────────────────────────────────┘ │
│                                                      │
│  [Overview] [Sessions] [Teams] [Activity]            │
└─────────────────────────────────────────────────────┘
```

- Card background: `--team-{color}-subtle`
- Avatar: first letter of user_id, ring uses member color
- Connection status from device data
- Data transfer from device bytes

### Tab 1: Overview

- **Stats Grid** (3 cols): Total Sessions, Projects, Last Active
- **Sessions Over Time**: Bar chart (daily sent/received, member-colored, same pattern as TeamOverviewTab)
- **Projects Contributed To**: Simple card list linking to `/projects/[encoded_name]`, showing session count per project

### Tab 2: Sessions

- Reuse `SessionCard` / `GlobalSessionCard` component
- Filter to sessions where `remote_user_id === user_id`
- Search/filter bar + pagination

### Tab 3: Teams

- Card per team (reuse TeamCard styling)
- Shows: member count, project count, online count
- Per-team project contribution breakdown for this member
- Each card links to `/team/[name]`

### Tab 4: Activity

- Reuse `TeamActivityFeed` pattern, pre-filtered to this member
- Type filter pills (All, Joins, Shares, Sessions, Syncs, Rejections, Settings)
- No member filter needed (already scoped)
- Pagination with load-more

## Files

### Backend — New
- `api/routers/sync_status.py` — add `GET /sync/members/{user_id}` endpoint

### Frontend — New
- `frontend/src/routes/members/[user_id]/+page.svelte` — member page
- `frontend/src/routes/members/[user_id]/+page.server.ts` — data loader
- `frontend/src/lib/components/team/MemberOverviewTab.svelte`
- `frontend/src/lib/components/team/MemberSessionsTab.svelte`
- `frontend/src/lib/components/team/MemberTeamsTab.svelte`
- `frontend/src/lib/components/team/MemberActivityTab.svelte`

### Frontend — Modified
- `frontend/src/lib/components/team/TeamMembersTab.svelte` — make member cards link to `/members/[user_id]`

### NOT Touched
- No new database tables
- No sync logic changes
- No device_id or remote_user_id resolution changes
