# Phase 3: Session View Restructure

## Agents

| Agent Type | Purpose |
|------------|---------|
| `feature-dev:code-architect` | Design Analytics tab structure and data requirements |
| `feature-dev:code-explorer` | Analyze current Session Overview and Tools tab implementation |
| `Explore` | Locate initial prompt data in API response and existing components |

---

## Objective

Restructure Session View to match philosophy spec: Add Initial Prompt to Overview, rename Tools to Analytics, fix time format.

---

## Current State

- Session has 5 tabs: Overview, Timeline, Files, Agents, Tools
- Initial prompt not prominently displayed in Overview
- Tools tab shows tool breakdown table and chart
- Last Message time shows relative time with tooltip
- Analytics metrics (cost, tokens, duration) in Overview stats cards

## Target State

- Session has 5 tabs: Overview, Timeline, Files, Agents, Analytics
- Overview prominently displays Initial Prompt
- Overview shows Last Message time as "Jan 9, 10am PST" format
- Analytics tab contains: Cost, Tokens, Duration, Tools count, Cache Hit Rate + charts

---

## Tasks

### 1. Initial Prompt Display (Overview)
- Investigate where initial prompt data exists in API response
- Add prominent display section in Overview tab
- Reference `ExpandablePrompt` component pattern
- Position: top of Overview, before stats cards

### 2. Last Message Time Format
- Change from relative time to absolute format
- Format: "Jan 9, 10am PST" per spec
- Identify timezone handling approach
- Update relevant component

### 3. Rename Tools Tab to Analytics
- Rename route from `/tools` to `/analytics`
- Update tab navigation labels
- Update any internal references

### 4. Analytics Tab Content
- Move/add metrics: Total Cost, Total Tokens, Total Duration, Total Tools, Cache Hit Rate
- Keep existing tool breakdown table and chart
- Add stats cards section at top
- Consider: should some stats remain in Overview as summary?

### 5. Total Tools Metric
- Add "Total Tools" count to Analytics
- Count unique tools used in session
- Display as stats card

---

## Files to Modify/Create

| Action | Path |
|--------|------|
| Modify | `apps/web/app/session/[uuid]/page.tsx` (add initial prompt, fix time format) |
| Rename | `apps/web/app/session/[uuid]/tools/` → `apps/web/app/session/[uuid]/analytics/` |
| Modify | `apps/web/app/session/[uuid]/layout.tsx` (update tab labels) |
| Modify | `apps/web/app/session/[uuid]/analytics/page.tsx` (add stats cards) |
| Create | Component for formatted timestamp if needed |

---

## Dependencies

- None (independent of Project View phases)

## Blocks

- Phase 4 (time-boxing applies to Analytics tab)
