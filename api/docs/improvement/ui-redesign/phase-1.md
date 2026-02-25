# Phase 1: Project View Tab Structure

## Agents

| Agent Type | Purpose |
|------------|---------|
| `feature-dev:code-architect` | Design route structure and component architecture for tabbed Project view |
| `feature-dev:code-explorer` | Analyze existing Project page implementation and data flow |
| `Explore` | Locate existing tab patterns from Session view to replicate |

---

## Objective

Introduce tab-based navigation to Project View with three tabs: Overview, Sessions, Analytics.

---

## Current State

- Project page exists at `/project/[encodedName]/page.tsx`
- Single page layout with stats, charts, and session grid combined
- No sub-routes or tab navigation

## Target State

- Project page with tab layout similar to Session view
- Three sub-routes:
  - `/project/[encodedName]/` (Overview)
  - `/project/[encodedName]/sessions`
  - `/project/[encodedName]/analytics`

---

## Tasks

### 1. Route Structure
- Convert `/project/[encodedName]/page.tsx` to layout with tab navigation
- Create `page.tsx` for Overview (default tab)
- Create `sessions/page.tsx` for Sessions tab
- Create `analytics/page.tsx` for Analytics tab

### 2. Tab Navigation Component
- Reference existing Session tab navigation in `/session/[uuid]/layout.tsx`
- Create or reuse tab navigation component for Project view
- Tabs: Overview | Sessions | Analytics

### 3. Content Distribution
- **Overview tab**: Stats cards (sessions, tokens, duration, cost, cache rate), Working Directory
- **Sessions tab**: Session grid (currently on main page)
- **Analytics tab**: Charts (Token Usage, Sessions Over Time, Top Tools)

### 4. Data Fetching
- Review current data fetching in Project page
- Ensure each tab fetches only required data
- Maintain TanStack Query patterns

---

## Files to Modify/Create

| Action | Path |
|--------|------|
| Convert to layout | `apps/web/app/project/[encodedName]/layout.tsx` |
| Create | `apps/web/app/project/[encodedName]/page.tsx` (Overview) |
| Create | `apps/web/app/project/[encodedName]/sessions/page.tsx` |
| Create | `apps/web/app/project/[encodedName]/analytics/page.tsx` |
| Reference | `apps/web/app/session/[uuid]/layout.tsx` (tab pattern) |

---

## Dependencies

- None (foundational phase)

## Blocks

- Phase 2 (branch features depend on tab structure)
