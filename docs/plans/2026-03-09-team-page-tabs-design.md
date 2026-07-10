# Team Detail Page — Tabbed Redesign

**Date:** 2026-03-09
**Status:** Approved

## Goal

Reimagine the `/team/[name]` page from a flat section layout to a tabbed dashboard matching the project detail page pattern (`bits-ui` Tabs, URL-persisted `?tab=` state).

## Tab Order

**Overview | Members | Projects | Activity**

## Layout

```
PageHeader (team name, breadcrumbs, Refresh button)
SyncStatusBanner
[Pending device requests — alert banners, above tabs]
[Pending folder shares — alert banners, above tabs]
Tabs.Root (?tab= URL state)
  Tabs.List: Overview | Members | Projects | Activity
  Tabs.Content: (per tab below)
```

Pending requests stay above tabs as actionable notifications — not hidden behind a tab.

## Tab 1: Overview (default)

Minimal "inbox + pulse" view:
- **Join Code card** (if available)
- **Stat row**: 3 compact stat cards
  - Members: online/total
  - Projects: in-sync/total
  - Sessions Shared: sent + received total
- **Sessions sent/received summary**: Grouped bar chart showing total sessions sent vs received per member, using their assigned palette color
- **Danger Zone** (leave team button)

## Tab 2: Members

- **Grid layout** (2 columns desktop, 1 mobile)
- Each member card:
  - Left border/accent stripe in their assigned palette color
  - Name + connection status dot (green/gray)
  - Data transferred (in/out bytes, formatted)
  - Mini sparkline (~80x30px) showing session activity over last 14 days
  - "Self" badge if current user
  - Remove button (non-self)
- Diagnostic hints section when <= 1 member

## Tab 3: Projects

- **Header row**: "Sync Now" + "Add Projects" buttons, SessionLimitSelector
- **Card per project**:
  - Project name (linked to `/projects/{encoded_name}`), path, sync status badge
  - Mini horizontal bar chart: session volume by member (each member segment in their color)
  - Packaged/local session count
  - Remove button with confirm flow

## Tab 4: Activity

- **Time period selector**: 7d / 30d / 90d / All (pill buttons)
- **Line chart** (Chart.js):
  - One line per member in their assigned palette color
  - X-axis: dates, Y-axis: session count
  - Member filter/selector: toggleable chips below chart to show/hide lines
- **Activity feed** below chart (existing `TeamActivityFeed` component)

## Color Palette Expansion

Expand `TEAM_MEMBER_PALETTE` from 8 to 16 colors:
- **Keep**: coral, rose, amber, cyan, pink, lime, indigo, teal
- **Add**: sky, violet, emerald, orange, fuchsia, slate, gold, ruby
- Update CSS vars (`--team-*`, `--team-*-subtle`) in `app.css`
- Update `TEAM_HEX_COLORS` map in `utils.ts`

## New API Requirement

Activity tab line chart needs a new endpoint or query param to fetch session counts per member over a time range. Options:
- Extend existing `/sync/teams/{name}/activity` with aggregation params
- New endpoint: `GET /sync/teams/{name}/session-stats?period=30d`

## New Components

- `TeamOverviewTab.svelte` — overview tab content
- `TeamMembersTab.svelte` — members grid with sparklines
- `TeamProjectsTab.svelte` — projects with mini bar charts
- `TeamActivityTab.svelte` — line chart + activity feed
- `MemberSparkline.svelte` — tiny Chart.js line for member cards
- `MemberSessionChart.svelte` — main line chart for activity tab
- `ProjectMemberBar.svelte` — mini horizontal bar for project cards

## Patterns to Follow

- `bits-ui` Tabs (Root, List, Trigger, Content) — same as project detail page
- URL state persistence via `?tab=` search param
- `TabsTrigger` with lucide icons
- Svelte 5 runes ($state, $derived, $effect, $props)
- Design tokens from `app.css`
