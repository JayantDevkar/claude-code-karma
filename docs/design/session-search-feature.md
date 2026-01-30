# Session Search Feature - Design Specification

**Created:** 2026-01-29
**Status:** Design Phase
**Author:** Design Session with Claude

---

## Overview

A unified search feature for filtering sessions across the Claude Karma dashboard. The search will be available on `/projects/[encoded_name]` and potentially `/sessions` pages.

### Design Principles

1. **Single search bar** - One input for all text search
2. **Default searches both** titles and prompts
3. **Progressive disclosure** - Filters hidden behind dropdown
4. **Auto-apply** - Results update instantly as filters change
5. **URL persistence** - All filters reflected in URL for shareability

---

## Research & Inspiration

### Patterns Evaluated

| Pattern | Source | Decision |
|---------|--------|----------|
| GitHub token search | `is:open author:me` syntax | Too steep learning curve |
| Slack unified search | Search + filter dropdown | Partial adoption |
| Linear filter chips | Visible filter buttons + chips | Partial adoption |
| Command palette (⌘K) | Modal search | Future consideration |

### Final Choice: Hybrid Approach

Combines Slack-style unified search with Linear-style filter chips for active state visibility.

### References

- [GitHub Search Docs](https://docs.github.com/en/issues/tracking-your-work-with-issues/using-issues/filtering-and-searching-issues-and-pull-requests)
- [Eleken: Filter UI Examples](https://www.eleken.co/blog-posts/filter-ux-and-ui-for-saas)
- [Arounda: 20 Filter UI Patterns](https://arounda.agency/blog/filter-ui-examples)
- [Command Palette UX](https://maggieappleton.com/command-bar)
- [Figma: Search Filters with Tags/Chips](https://www.componentcollector.com/component/search-filters-with-tags-chips)

---

## Component: `SessionSearchBar`

### States & Layouts

#### State 1: Default (No filters active)

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                                                                             │
│   ┌───────────────────────────────────────────────────────────────────┐     │
│   │  🔍   Search by title or prompt...                      ⚙ Filters │     │
│   └───────────────────────────────────────────────────────────────────┘     │
│                                                                             │
│   156 sessions                                                              │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

- Placeholder text: "Search by title or prompt..."
- Filter button with gear/sliders icon
- Session count shown below

---

#### State 2: Search active (text entered)

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                                                                             │
│   ┌───────────────────────────────────────────────────────────────────┐     │
│   │  🔍   implement auth                               ✕    ⚙ Filters │     │
│   └───────────────────────────────────────────────────────────────────┘     │
│                                                                             │
│   12 sessions matching "implement auth"                                     │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

- Clear button (✕) appears when text entered
- Count updates with match context

---

#### State 3: Filters dropdown open

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                                                                             │
│   ┌───────────────────────────────────────────────────────────────────┐     │
│   │  🔍   implement auth                               ✕    ⚙ Filters │     │
│   └───────────────────────────────────────────────────────────────────┴──┐  │
│                                                                          │  │
│   ┌──────────────────────────────────────────────────────────────────────┤  │
│   │                                                                      │  │
│   │   SEARCH SCOPE                                                       │  │
│   │   ┌─────────────────────────────────────────────────────────────┐    │  │
│   │   │  Titles & Prompts  │  Titles only  │  Prompts only         │    │  │
│   │   │  ═══════════════                                            │    │  │
│   │   └─────────────────────────────────────────────────────────────┘    │  │
│   │                                                                      │  │
│   │   STATUS                                                             │  │
│   │   ┌──────────┐  ┌────────────┐  ┌─────────┐                         │  │
│   │   │ ✓ Active │  │ ✓ Completed│  │   Error │                         │  │
│   │   └──────────┘  └────────────┘  └─────────┘                         │  │
│   │                                                                      │  │
│   │   DATE RANGE                                                         │  │
│   │   ┌──────────┐  ┌─────────┐  ┌──────────┐  ┌──────────┐             │  │
│   │   │ All time │  │  Today  │  │  7 days  │  │  30 days │  [Custom]   │  │
│   │   │ ════════                                                         │  │
│   │   └──────────┘  └─────────┘  └──────────┘  └──────────┘             │  │
│   │                                                                      │  │
│   │   ─────────────────────────────────────────────────────────────      │  │
│   │   Reset all filters                                                  │  │
│   │                                                                      │  │
│   └──────────────────────────────────────────────────────────────────────┘  │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

**Filter sections:**

| Section | Type | Default | Options |
|---------|------|---------|---------|
| Search Scope | Segmented button | Titles & Prompts | Titles & Prompts / Titles only / Prompts only |
| Status | Multi-select chips | All selected | Active / Completed / Error |
| Date Range | Single-select chips | All time | All time / Today / 7 days / 30 days / Custom |

---

#### State 4: Filters active (with chips)

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                                                                             │
│   ┌───────────────────────────────────────────────────────────────────┐     │
│   │  🔍   implement auth                               ✕    ⚙ Filters │     │
│   └───────────────────────────────────────────────────────────────────┘     │
│                                                                             │
│   ┌────────────────┐  ┌─────────────────┐                                   │
│   │ ● Active    ✕  │  │ 📅 Last 7 days ✕│           Clear all filters      │
│   └────────────────┘  └─────────────────┘                                   │
│                                                                             │
│   3 sessions matching "implement auth"                                      │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

**Chip behaviors:**
- Each chip shows filter type + value
- ✕ removes that specific filter
- "Clear all filters" resets everything
- Chips only appear when filter differs from default

---

#### State 5: No results

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                                                                             │
│   ┌───────────────────────────────────────────────────────────────────┐     │
│   │  🔍   xyznonexistent                               ✕    ⚙ Filters │     │
│   └───────────────────────────────────────────────────────────────────┘     │
│                                                                             │
│   ┌────────────────┐                                                        │
│   │ ● Active    ✕  │                                   Clear all filters    │
│   └────────────────┘                                                        │
│                                                                             │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │                                                                     │   │
│   │                          🔍                                         │   │
│   │                                                                     │   │
│   │                 No sessions found                                   │   │
│   │                                                                     │   │
│   │        Try different search terms or adjust filters                 │   │
│   │                                                                     │   │
│   │                  [ Clear all filters ]                              │   │
│   │                                                                     │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Interaction Specifications

### Search Input

| Action | Behavior |
|--------|----------|
| Type text | Debounce 300ms, then filter results |
| Press Enter | No action (auto-apply) |
| Press Escape | Clear search text |
| Click ✕ | Clear search text |

### Filter Dropdown

| Action | Behavior |
|--------|----------|
| Click "Filters" button | Toggle dropdown open/close |
| Click outside | Close dropdown |
| Select option | Instantly apply filter, results update |
| Click "Reset all" | Reset to defaults, close dropdown |

### Filter Chips

| Action | Behavior |
|--------|----------|
| Click chip ✕ | Remove that filter, results update |
| Click "Clear all" | Remove all filters, reset to defaults |

---

## URL Persistence

```
/projects/[encoded_name]?
  q=implement+auth          # Search query
  &scope=titles             # Search scope (titles|prompts|both)
  &status=active            # Status filter (active|completed|error|all)
  &range=7d                 # Date range (all|today|7d|30d)
  &from=2025-01-20          # Custom date start
  &to=2025-01-27            # Custom date end
```

---

## Visual Design Tokens

```css
/* Search bar */
--search-height: 44px;
--search-bg: var(--surface-secondary);
--search-border: var(--border-muted);
--search-focus-ring: var(--accent);

/* Filter chips */
--chip-bg: var(--surface-tertiary);
--chip-bg-hover: var(--surface-quaternary);
--chip-text: var(--text-secondary);
--chip-radius: var(--radius-full);
--chip-padding: 6px 12px;

/* Dropdown */
--dropdown-bg: var(--surface-elevated);
--dropdown-shadow: var(--shadow-lg);
--dropdown-radius: var(--radius-lg);
--dropdown-max-width: 320px;
```

---

## Component Hierarchy

```
<SessionSearchBar>
  ├── <SearchInput>
  │     ├── SearchIcon
  │     ├── Input (text)
  │     └── ClearButton (conditional)
  │
  ├── <FiltersButton>
  │     └── onClick → toggle dropdown
  │
  ├── <FiltersDropdown> (conditional)
  │     ├── <SearchScopeSelector>
  │     ├── <StatusFilter>
  │     ├── <DateRangeFilter>
  │     └── ResetButton
  │
  └── <ActiveFilterChips> (conditional)
        ├── Chip[] (for each active filter)
        └── ClearAllButton
```

---

## Mobile Adaptation (< 768px)

```
┌─────────────────────────────────┐
│ 🔍  Search...              ⚙   │
└─────────────────────────────────┘

┌──────────┐ ┌─────────┐
│ Active ✕ │ │ 7d ✕    │  Clear
└──────────┘ └─────────┘

Tap ⚙ → Bottom sheet with filters:

┌─────────────────────────────────┐
│ ═══════════                     │  ← drag handle
│                                 │
│  Filters                    ✕   │
│                                 │
│  Search scope                   │
│  [Titles & Prompts ▾]           │
│                                 │
│  Status                         │
│  [●] Active  [●] Completed      │
│  [ ] Error                      │
│                                 │
│  Date range                     │
│  [All time ▾]                   │
│                                 │
│  ─────────────────────────────  │
│  [ Reset filters ]              │
│                                 │
└─────────────────────────────────┘
```

---

## Integration Points

### Pages using this component

1. `/projects/[encoded_name]` - Project sessions list
2. `/sessions` (future) - Global sessions view

### Data requirements

- Sessions must include `session_titles[]` and `initial_prompt`
- API already supports search via `/sessions/all` endpoint
- Frontend filtering can be done client-side for project page

### Available session fields for filtering

| Field | Type | Description |
|-------|------|-------------|
| `session_titles[]` | string[] | AI-generated descriptive titles |
| `initial_prompt` | string | First user message (truncated to 500 chars) |
| `slug` | string | System-generated short name |
| `status` | enum | active / completed / error |
| `start_time` | datetime | Session start timestamp |
| `end_time` | datetime | Session end timestamp |

---

## Filter Logic

### Text Search (AND between fields when scope is "both")

```typescript
const matchesSearch = (session: Session, query: string, scope: SearchScope) => {
  const q = query.toLowerCase();

  const matchesTitle = session.session_titles?.some(
    title => title.toLowerCase().includes(q)
  ) ?? false;

  const matchesPrompt = session.initial_prompt?.toLowerCase().includes(q) ?? false;

  switch (scope) {
    case 'titles': return matchesTitle;
    case 'prompts': return matchesPrompt;
    case 'both': return matchesTitle || matchesPrompt;
  }
};
```

### Combined Filter Logic (AND between filter types)

```typescript
const filteredSessions = sessions.filter(session =>
  matchesSearch(session, searchQuery, searchScope) &&
  matchesStatus(session, statusFilters) &&
  matchesDateRange(session, dateRange) &&
  matchesBranch(session, branchFilters)  // existing filter
);
```

---

## Existing Implementation Context

### Current state (from codebase analysis)

**Frontend (`/projects/[encoded_name]/+page.svelte`):**
- Has simple text search matching `slug`, `uuid`, `initial_prompt`
- Has branch filter via `ActiveBranches` component
- Uses Svelte 5 runes (`$state`, `$derived`, `$effect`)
- URL state persistence pattern already exists

**API (`/sessions/all`):**
- Supports `search` parameter (searches slug, initial_prompt, project_path)
- Supports `project` and `branch` filters
- Pagination with `limit` and `offset`

### What needs to be added

1. **Frontend:** `SessionSearchBar` component with filter dropdown
2. **Frontend:** Filter chips component
3. **API (optional):** Add `scope` parameter to search endpoint for title-only search
4. **API (optional):** Add `status` and `date_range` query parameters

---

## Open Questions

1. Should custom date range use a date picker modal or inline inputs?
2. Should we add keyboard shortcuts (e.g., `/` to focus search)?
3. Should search results highlight matching text in session cards?

---

## Next Steps

- [ ] Review design with stakeholders
- [ ] Create Figma mockups (optional)
- [ ] Implement `SessionSearchBar` component
- [ ] Add URL persistence for new filters
- [ ] Update API if server-side filtering needed
- [ ] Add mobile bottom sheet for filters
