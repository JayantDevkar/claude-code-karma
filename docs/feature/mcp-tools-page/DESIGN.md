# MCP Tools Page — Design Document

> Feature: Global MCP tool usage visibility across all sessions and projects.

---

## Problem Statement

Claude Code Karma surfaces **agents** (who performed work) and **skills** (what workflows were invoked), but has no dedicated view for **MCP tools** — the external systems Claude connects to via the Model Context Protocol.

MCP tool usage data already exists in SQLite (`session_tools`, `subagent_tools`) and is partially visible inside plugin detail pages, but users have no way to:

- See all MCP servers and tools in one place
- Understand which external integrations are most used
- Compare main session vs subagent tool usage
- Track MCP tool usage trends over time
- Navigate from a tool to the sessions that used it

---

## Data Landscape

### What We Already Have

**SQLite tables** (in `~/.claude_karma/metadata.db`):

| Table | Relevant Columns | MCP Data |
|-------|-----------------|----------|
| `session_tools` | `session_uuid`, `tool_name`, `count` | All tools with `mcp__` prefix |
| `subagent_tools` | `invocation_id`, `tool_name`, `count` | MCP tools used by subagents |
| `sessions` | `uuid`, `project_encoded_name`, `start_time` | Join for time/project context |

**Tool naming convention**: `mcp__{server}__{tool_name}`

Examples:
- `mcp__coderoots__query`
- `mcp__plugin_playwright_playwright__browser_click`
- `mcp__plane-project-task-manager__list_work_items`

**Natural two-level hierarchy**: server name (extracted from middle segment) → tool name (extracted from last segment).

### Current Data on This Machine

| MCP Server | Display Name | Tools | Total Calls | Sessions | Source |
|---|---|---|---|---|---|
| coderoots | CodeRoots | 18 | 3,961 | 153 | standalone |
| plugin_playwright_playwright | Playwright | 18 | 1,040 | 82 | plugin |
| plane-project-task-manager | Plane | 14 | 195 | 33 | standalone |
| claude-flow | Claude Flow | 14 | 179 | 22 | standalone |
| analyzer | Analyzer | 5 | 170 | 12 | standalone |
| plugin_github_github | GitHub | 4 | 17 | 7 | plugin |
| plugin_linear_linear | Linear | 3 | 3 | 3 | plugin |
| filesystem | Filesystem | ~8 | 434+ | — | standalone (subagent only) |

**Totals**: 8 servers, 77 distinct tools, ~5,700 invocations across 1,260 sessions.

**Main vs subagent split**: Some tools (coderoots) are 58% subagent-driven. Others (playwright) are 100% main session. This is a unique insight only the MCP tools view can surface.

### Existing API Support

The plugins router already has MCP aggregation logic:

- `_query_plugin_mcp_usage_sqlite()` — queries `session_tools` with `LIKE 'mcp__plugin_{name}_%'`
- `_extract_mcp_tool_short_name()` — strips prefix to get readable tool name
- `PluginUsageStats.by_mcp_tool` — tool-level breakdown per plugin
- `PluginCapabilities.mcp_tools` — discovered from `.mcp.json` files

This logic can be generalized for the new endpoints.

---

## Route Structure

```
/tools                          MCP Tools listing page
  └── /tools/[server_name]      Server detail page
```

### Navigation Integration

**Home screen grid**: Add 10th card — "Tools" with `Cable` icon, teal color.

**Header nav bar** (new order):
```
Projects, Sessions, Plans, Agents, Skills, Tools, Plugins, Analytics, Archived
```

**Command palette**: Register MCP servers as searchable entities.

**Breadcrumbs**:
```
Dashboard > Tools                        (listing)
Dashboard > Tools > CodeRoots            (server detail)
Dashboard > Tools > Playwright           (plugin-sourced server)
```

**URL state**:
```
/tools?search=browser&filter=plugin&view=all
/tools?filter=standalone
/tools/coderoots
```

---

## Page Designs

### Page 1: `/tools` — MCP Tools Overview

Follows the established pattern: `PageHeader` → `StatsGrid` hero → filters → grouped content.

#### Hero Stats

```
┌──────────────┐  ┌──────────────┐  ┌──────────────┐  ┌───────────────┐
│  8 Servers    │  │ 77 Tools     │  │ 5,677 Calls  │  │ 153 Sessions  │
│  Cable icon   │  │ Wrench icon  │  │ Play icon    │  │ Activity icon │
│  teal         │  │ blue         │  │ purple       │  │ green         │
└──────────────┘  └──────────────┘  └──────────────┘  └───────────────┘
```

#### Filters

```
┌─────────────────────────────────────────────────────────────────────────┐
│ [By Server ▾] [All Tools]    [All] [Plugin] [Standalone]    [🔍 Search]│
│  ↑ view toggle                ↑ source filter                          │
└─────────────────────────────────────────────────────────────────────────┘
```

- **View toggle** (SegmentedControl): "By Server" (default grouped) | "All Tools" (flat table)
- **Source filter** (SegmentedControl): All | Plugin | Standalone | Custom
- **Search**: Filters by server name or tool name

#### "By Server" View — CollapsibleGroup per server

Each server is a collapsible section with tool cards inside:

```
▼ CodeRoots                                         3,961 calls · 153 sessions
  ┌─────────────────────────────────────────────────────────────────────────┐
  │                                                                         │
  │  ┌───────────────┐  ┌───────────────┐  ┌───────────────┐               │
  │  │ query          │  │ mutate        │  │ add_project_  │               │
  │  │ 2,072 calls    │  │ 176 calls     │  │ knowledge     │  ...          │
  │  │ ████████░░ 52% │  │ ██░░░░░░  4%  │  │ 690 calls     │               │
  │  │ ⬤ 19% main     │  │ ⬤ 55% main    │  │ ███░░░░░ 17%  │               │
  │  │ ⬤ 81% subagent │  │ ⬤ 45% subagent│  │ ⬤ 8% main     │               │
  │  └───────────────┘  └───────────────┘  └───────────────┘               │
  │                                                                         │
  │  Source: standalone    First: Jan 26    Last: Feb 14                     │
  └─────────────────────────────────────────────────────────────────────────┘

▼ Playwright                                        1,040 calls · 82 sessions
  ┌─────────────────────────────────────────────────────────────────────────┐
  │  browser_take_screenshot 278 · browser_navigate 275 · browser_click 196│
  │  browser_snapshot 72 · browser_run_code 66 · browser_close 55 · ...    │
  │                                                                         │
  │  Source: plugin (playwright)    First: Jan 27    Last: Feb 16            │
  └─────────────────────────────────────────────────────────────────────────┘

► Plane                                              195 calls · 33 sessions
► Claude Flow                                        179 calls · 22 sessions
► Analyzer                                           170 calls · 12 sessions
► GitHub                                              17 calls · 7 sessions
► Linear                                               3 calls · 3 sessions
```

**Group metadata snippet**: call count badge + session count + expand/collapse all toggle.

**Tool cards inside groups**: CSS grid (3-4 columns on desktop, 2 on tablet, 1 on mobile).

#### "All Tools" View — Flat sortable table

| Tool | Server | Calls | Sessions | Main % | Sub % | Last Used |
|---|---|---|---|---|---|---|
| query | CodeRoots | 2,072 | 153 | 19% | 81% | Feb 14 |
| browser_take_screenshot | Playwright | 278 | 82 | 100% | 0% | Feb 16 |
| browser_navigate | Playwright | 275 | 82 | 100% | 0% | Feb 16 |
| add_project_knowledge | CodeRoots | 690 | — | 8% | 92% | Feb 12 |
| ... | | | | | | |

Sortable by any column. Click tool name → server detail page (scrolled to that tool).

---

### Page 2: `/tools/[server_name]` — Server Detail

Follows the pattern of `/agents/[name]` and `/plugins/[plugin_name]`.

#### Header

```
Dashboard > Tools > CodeRoots
═══════════════════════════════════════════════════════
  [Database icon]  CodeRoots                [standalone]
                   Knowledge graph management server

  18 tools · 3,961 total calls · 153 sessions
  First used: Jan 26 · Last used: Feb 14
```

#### Hero Stats

```
┌──────────────┐  ┌──────────────┐  ┌──────────────┐  ┌───────────────┐
│  18 Tools     │  │ 3,961 Calls  │  │ 153 Sessions │  │ 58% Subagent  │
│  Wrench       │  │ Play         │  │ FolderOpen   │  │ Bot           │
│  teal         │  │ blue         │  │ green        │  │ purple        │
└──────────────┘  └──────────────┘  └──────────────┘  └───────────────┘
```

#### Tabs (SegmentedControl)

**Overview** | **Sessions**

##### Overview Tab

**Tool Breakdown** — Horizontal bar chart showing each tool's invocation count. Bars colored by the server's accent color. Each bar is clickable.

```
query                 ████████████████████████████████████████  2,072
add_project_knowledge ████████████████                           690
add_project_rel       ███████████████                            589
coderoots_query       ██████████                                 538
mutate                ████                                       176
...
```

**Context Split** — Donut chart (or two-segment bar) showing main vs subagent usage for the entire server.

```
  ┌─────────────────────────────┐
  │    Main Session: 42%        │
  │    ████████░░░░░░░░░░░░     │
  │    Subagent: 58%            │
  │    ░░░░░░░░████████████     │
  └─────────────────────────────┘
```

**Usage Trend** — Line chart (daily invocations over time, reuse `DailyUsage` type and Chart.js pattern from analytics page).

**Related Plugin** (if source is plugin) — Link card to `/plugins/[name]`.

##### Sessions Tab

Reuse existing session list components (`GlobalSessionCard` grouped by date). Filter: sessions that used any `mcp__{server}__*` tool.

Includes search, date grouping, list/grid toggle — same as agent detail sessions tab.

---

## Visual Design

### Color Identity

**Primary**: Teal/cyan (`--nav-teal` or new CSS variable). Infrastructure-coded — cool-toned, distinct from agents (purple) and skills (green).

### Server Icons

Map known servers to semantic lucide icons:

| Server | Icon | Rationale |
|---|---|---|
| coderoots | `Database` | Knowledge graph storage |
| plugin_playwright_playwright | `Globe` | Browser automation |
| plane-project-task-manager | `KanbanSquare` | Project management |
| claude-flow | `GitBranch` | Agent orchestration |
| plugin_github_github | `Github` | GitHub integration |
| plugin_linear_linear | `BarChart3` | Linear issue tracking |
| filesystem | `HardDrive` | File system access |
| analyzer | `Microscope` | Code analysis |
| *(fallback)* | `Plug` | Unknown/custom MCP server |

### Source Badges

| Source | Badge Color | When |
|---|---|---|
| `plugin` | violet | Server name starts with `plugin_` |
| `standalone` | teal | Non-plugin, known server |
| `custom` | amber | User-configured `.mcp.json` |

### Tool Cards

```
┌──────────────────────────────────┐
│  query                        ▸  │   ← short name, link arrow
│  2,072 calls                     │   ← total invocations
│  ████████████░░░░░  52%          │   ← proportion bar (% of server)
│  ⬤ main 19%  ⬤ sub 81%          │   ← two-dot context indicator
└──────────────────────────────────┘
```

- 4px left border with server accent color (matches existing card pattern)
- Proportion bar uses server color at varying opacity
- Main/subagent dots are small inline indicators

### Responsive Breakpoints

| Breakpoint | Tool card grid | Table columns |
|---|---|---|
| Desktop (lg+) | 4 columns | All columns |
| Tablet (md) | 2 columns | Hide Main/Sub split |
| Mobile (sm) | 1 column | Tool + Calls only |

---

## API Endpoints

### `GET /tools`

Returns aggregated MCP tool usage across all sessions.

**Query params**:
- `project` (optional) — filter by project encoded name
- `period` (optional) — `day`, `week`, `month`, `all` (default: `all`)

**Response**: `McpToolsOverview`

```json
{
  "total_servers": 8,
  "total_tools": 77,
  "total_calls": 5677,
  "total_sessions": 153,
  "servers": [
    {
      "name": "coderoots",
      "display_name": "CodeRoots",
      "source": "standalone",
      "plugin_name": null,
      "tool_count": 18,
      "total_calls": 3961,
      "session_count": 153,
      "main_calls": 1663,
      "subagent_calls": 2298,
      "first_used": "2026-01-26T...",
      "last_used": "2026-02-14T...",
      "tools": [
        {
          "name": "query",
          "full_name": "mcp__coderoots__query",
          "calls": 2072,
          "session_count": 120,
          "main_calls": 392,
          "subagent_calls": 1680
        }
      ]
    }
  ]
}
```

### `GET /tools/{server_name}`

Returns detailed usage for a specific MCP server.

**Query params**:
- `project` (optional)
- `period` (optional)

**Response**: `McpServerDetail`

```json
{
  "name": "coderoots",
  "display_name": "CodeRoots",
  "source": "standalone",
  "plugin_name": null,
  "tool_count": 18,
  "total_calls": 3961,
  "session_count": 153,
  "main_calls": 1663,
  "subagent_calls": 2298,
  "first_used": "2026-01-26T...",
  "last_used": "2026-02-14T...",
  "tools": [ ... ],
  "trend": [
    { "date": "2026-02-14", "calls": 2, "sessions": 1 },
    { "date": "2026-02-13", "calls": 30, "sessions": 3 }
  ],
  "top_sessions": [
    { "uuid": "...", "slug": "...", "project_encoded_name": "...", "tool_calls": 45 }
  ]
}
```

### SQL Queries

```sql
-- Server-level aggregation (for GET /tools)
SELECT
  CASE
    WHEN tool_name LIKE 'mcp__%__%' THEN
      SUBSTR(tool_name, 6, INSTR(SUBSTR(tool_name, 6), '__') - 1)
    ELSE tool_name
  END as server_name,
  COUNT(DISTINCT tool_name) as tool_count,
  SUM(count) as total_calls,
  COUNT(DISTINCT session_uuid) as session_count
FROM session_tools
WHERE tool_name LIKE 'mcp__%'
GROUP BY server_name
ORDER BY total_calls DESC;

-- Tool-level detail (for a specific server)
SELECT
  tool_name,
  SUM(count) as total_calls,
  COUNT(DISTINCT session_uuid) as session_count
FROM session_tools
WHERE tool_name LIKE 'mcp__coderoots__%'
GROUP BY tool_name
ORDER BY total_calls DESC;

-- Main vs subagent split
SELECT tool_name, SUM(count) as main_calls
FROM session_tools
WHERE tool_name LIKE 'mcp__coderoots__%'
GROUP BY tool_name;

SELECT tool_name, SUM(count) as sub_calls
FROM subagent_tools
WHERE tool_name LIKE 'mcp__coderoots__%'
GROUP BY tool_name;

-- Daily trend for a server
SELECT
  DATE(s.start_time) as day,
  SUM(st.count) as calls,
  COUNT(DISTINCT st.session_uuid) as sessions
FROM session_tools st
JOIN sessions s ON st.session_uuid = s.uuid
WHERE st.tool_name LIKE 'mcp__coderoots__%'
GROUP BY day
ORDER BY day DESC;
```

---

## TypeScript Types

```typescript
// New types in frontend/src/lib/api-types.ts

export interface McpToolSummary {
  name: string;            // short: "query", "browser_click"
  full_name: string;       // full: "mcp__coderoots__query"
  calls: number;
  session_count: number;
  main_calls: number;
  subagent_calls: number;
}

export interface McpServer {
  name: string;            // "coderoots"
  display_name: string;    // "CodeRoots"
  source: 'plugin' | 'standalone' | 'custom';
  plugin_name: string | null;
  tool_count: number;
  total_calls: number;
  session_count: number;
  main_calls: number;
  subagent_calls: number;
  first_used: string | null;
  last_used: string | null;
  tools: McpToolSummary[];
}

export interface McpToolsOverview {
  total_servers: number;
  total_tools: number;
  total_calls: number;
  total_sessions: number;
  servers: McpServer[];
}

export interface McpServerTrend {
  date: string;
  calls: number;
  sessions: number;
}

export interface McpServerDetail extends McpServer {
  trend: McpServerTrend[];
  top_sessions: SessionSummary[];
}
```

---

## New Components

| Component | Path | Purpose |
|---|---|---|
| `McpServerCard.svelte` | `lib/components/tools/McpServerCard.svelte` | Server card in grouped view |
| `McpToolCard.svelte` | `lib/components/tools/McpToolCard.svelte` | Individual tool card within server |
| `McpToolTable.svelte` | `lib/components/tools/McpToolTable.svelte` | Flat sortable tool table |
| `McpContextBar.svelte` | `lib/components/tools/McpContextBar.svelte` | Main vs subagent split indicator |
| `McpServerIcon.svelte` | `lib/components/tools/McpServerIcon.svelte` | Maps server name to lucide icon |
| `SkeletonToolsPage.svelte` | `lib/components/skeleton/SkeletonToolsPage.svelte` | Loading skeleton |

### Reused Components

| Component | From | Usage |
|---|---|---|
| `PageHeader` | `lib/components/layout/` | Page title + breadcrumbs |
| `StatsGrid` | `lib/components/` | Hero stats |
| `SegmentedControl` | `lib/components/ui/` | View toggle + source filter |
| `CollapsibleGroup` | `lib/components/ui/` | Server sections |
| `Badge` | `lib/components/ui/` | Source badges |
| `Pagination` | `lib/components/` | All Tools table pagination |
| `GlobalSessionCard` | `lib/components/sessions/` | Sessions in server detail |

---

## Cross-Page Integration

### Session Detail (`/projects/[slug]/[session]`)

The tools tab already shows MCP tools in the flat list. Enhancements:

- Add `[MCP]` badge to tools with `mcp__` prefix
- Make MCP tool names clickable → link to `/tools/[server]`
- Show server name in parentheses: `query (coderoots)`

### Plugins Detail (`/plugins/[name]`)

Already has `by_mcp_tool` data. Add:

- "View in Tools" link next to MCP tools section → `/tools/[server]`

### Analytics (`/analytics`)

Add "MCP Usage" section or chart showing server usage over time (stretch goal).

### Project Detail (`/projects/[slug]`)

Consider adding `?tab=tools` showing MCP tool usage scoped to that project (stretch goal).

---

## Implementation Phases

### Phase 1: API Layer ✅
- [x] New router: `api/routers/tools.py`
- [x] `GET /tools` endpoint with server/tool aggregation
- [x] `GET /tools/{server_name}` endpoint with detail + trend + paginated sessions
- [x] Server name → display name mapping (`_server_display_name()`)
- [x] Source detection (plugin vs standalone) (`_detect_source()`)
- [x] Main vs subagent split queries (session_tools + subagent_tools)
- [x] Register router in `main.py`
- [x] Pydantic response models in `schemas.py` (McpToolSummary, McpServer, McpToolsOverview, McpServerTrend, McpServerDetail)
- [x] SQLite query functions in `db/queries.py` (query_mcp_tools_overview, query_mcp_server_detail, query_mcp_server_trend, query_sessions_by_mcp_server)
- [x] Period filtering (day, week, month, quarter, all) and project filtering
- [x] HTTP caching via @cacheable decorator (60s fresh, 300s stale-while-revalidate)

### Phase 2: Frontend Listing Page
- [ ] Route: `frontend/src/routes/tools/+page.server.ts` (data loader)
- [ ] Route: `frontend/src/routes/tools/+page.svelte` (page)
- [ ] Components: `McpServerCard`, `McpToolCard`, `McpContextBar`, `McpServerIcon`
- [ ] "By Server" grouped view with CollapsibleGroup
- [ ] "All Tools" flat table view
- [ ] Search + source filter
- [ ] Skeleton loader

### Phase 3: Frontend Detail Page
- [ ] Route: `frontend/src/routes/tools/[server_name]/+page.server.ts`
- [ ] Route: `frontend/src/routes/tools/[server_name]/+page.svelte`
- [ ] Tool breakdown bar chart
- [ ] Context split visualization
- [ ] Usage trend line chart
- [ ] Sessions tab with filtered session list
- [ ] Related plugin link

### Phase 4: Navigation Integration
- [ ] Add "Tools" to Header nav bar
- [ ] Add "Tools" card to home screen grid
- [ ] Register in command palette
- [ ] Add to `navigation.md`

### Phase 5: Cross-Page Links (Stretch)
- [ ] MCP badges + links in session detail tools tab
- [ ] "View in Tools" from plugin detail
- [ ] `?tab=tools` on project detail
- [ ] MCP chart on analytics page
