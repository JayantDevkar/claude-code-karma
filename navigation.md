# Navigation Guide

> How users move through Claude Karma, starting from the home screen.

---

## Home Screen (`/`)

The home screen is the central hub. It offers two navigation mechanisms:

1. **Navigation Grid** — 9 cards linking to top-level sections
2. **Live Sessions Panel** — quick access to active sessions

| Card | Route | Purpose |
|------|-------|---------|
| Projects | `/projects` | Browse all projects |
| Sessions | `/sessions` | View all sessions across projects |
| Analytics | `/analytics` | Global analytics dashboard |
| Plans | `/plans` | Browse work plans |
| Skills | `/skills` | Global skill/tool usage |
| Agents | `/agents` | Global agent usage |
| Plugins | `/plugins` | Plugin management |
| Settings | `/settings` | User configuration |
| Archived | `/archived` | Archived sessions |

---

## Persistent Navigation Bar

Present on **all pages except home**. Sticky top header with:

- **Desktop**: Inline links — Projects, Sessions, Plans, Agents, Skills, Plugins, Analytics, Archived
- **Mobile**: Hamburger menu with same links
- **Settings**: Gear icon (top-right, always visible)
- **Brand**: "Claude Karma" links back to `/`

---

## Section Flows

### Projects

```
/projects                              List all projects (search, sort, filter)
  └── /projects/[encoded_name]         Project detail (tabbed)
        ├── Overview (default)         Stats, live sessions, recent sessions
        │     └── [session card]  ───► /projects/[encoded_name]/[session_slug]
        ├── Agents tab            ───► /projects/[encoded_name]/agents
        │     └── [agent]         ───► /projects/[encoded_name]/agents/[name]
        ├── Skills tab            ───► /projects/[encoded_name]/skills
        │     └── [file path]     ───► /projects/[encoded_name]/skills/[...path]
        ├── Analytics tab              Inline charts
        └── Archived tab               Archived sessions for this project
```

### Sessions

```
/sessions                              All sessions across projects (filter, paginate)
  └── [session card]              ───► /projects/[encoded_name]/[session_slug]
```

**Session detail** (`/projects/[encoded_name]/[session_slug]`) shows:
- Conversation messages, timeline, file activity, tools, tasks, plan details
- Subagent links → subagent detail pages

### Agents

```
/agents                                All agents (search, category filter)
  └── [agent card]                ───► /agents/usage/[subagent_type]
```

### Skills

```
/skills                                Two tabs:
  ├── Usage Analytics (default)        Skill stats, category filter
  │     └── [skill]               ───► /skills/[skill_name]
  └── Browse Files                     File explorer
        └── [path]                ───► /skills/[...path]
```

### Plans

```
/plans                                 All plans (filter by project, branch)
  └── [plan card]                 ───► /plans/[slug]
```

### Analytics

```
/analytics                             Time-filtered dashboard (no sub-routes)
```

### Plugins

```
/plugins                               Plugin list
  └── [plugin]                    ───► /plugins/[plugin_id]
```

### Settings

```
/settings                              Sections: General, Permissions, Plugins, Advanced
```

### Archived

```
/archived                              Archived sessions list
```

---

## Cross-Cutting Patterns

### Breadcrumbs

Interior pages show a breadcrumb trail:

```
Dashboard > Projects > [Project Name] > Agents
Dashboard > Plans > [Plan Name]
Dashboard > Settings
```

### URL State

Filters persist via URL search params for shareability and back-button support:

| Param | Used On | Example |
|-------|---------|---------|
| `search` | Projects, Sessions, Agents | `?search=karma` |
| `filter` | Analytics | `?filter=7days` |
| `project` | Sessions, Plans | `?project=encoded_name` |
| `branch` | Plans | `?branch=main` |
| `page`, `per_page` | Sessions, Plans, Agents | `?page=2&per_page=24` |
| `path` | Skills | `?path=hooks/` |

### Command Palette

Global keyboard shortcut opens a search overlay for quick navigation to any page or entity.

### Skeleton Loaders

Each section has a dedicated skeleton displayed during navigation transitions (e.g., `ProjectsPageSkeleton`, `SessionDetailSkeleton`).

---

## Key Components

| Component | File | Role |
|-----------|------|------|
| Header | `src/lib/components/Header.svelte` | Top nav bar |
| NavigationCard | `src/lib/components/NavigationCard.svelte` | Home grid cards |
| PageHeader | `src/lib/components/layout/PageHeader.svelte` | Breadcrumbs + title |
| CommandPalette | `src/lib/components/command-palette/CommandPalette.svelte` | Global search |
| CommandFooter | `src/lib/components/CommandFooter.svelte` | Keyboard shortcuts help |

---

## Full Journey Map

```
/ (Home)
├─► /projects ─► /projects/[name] ─┬─► Overview ─► /projects/[name]/[session]
│                                   ├─► Agents  ─► /projects/[name]/agents/[agent]
│                                   ├─► Skills  ─► /projects/[name]/skills/[...path]
│                                   ├─► Analytics (inline)
│                                   └─► Archived (inline)
├─► /sessions ─► /projects/[name]/[session]
├─► /agents ──► /agents/usage/[type]
├─► /skills ──┬► /skills/[name]
│             └► /skills/[...path]
├─► /plans ───► /plans/[slug]
├─► /plugins ─► /plugins/[id]
├─► /analytics
├─► /archived
└─► /settings
```
