# Phase 2: Project View Branch Features

## Agents

| Agent Type | Purpose |
|------------|---------|
| `feature-dev:code-architect` | Design branch grouping data structure and component hierarchy |
| `feature-dev:code-explorer` | Trace how branch data flows from API to frontend |
| `Explore` | Find existing branch-related components and API endpoints |

---

## Objective

Add branch-aware features to Project View: Active Branches in Overview, Sessions grouped by branch.

---

## Current State

- Branch information exists in Session data (observed as pills in Session Overview)
- Sessions displayed in flat grid on Project page
- No branch aggregation at Project level

## Target State

- Overview tab shows Active Branches for git projects
- Sessions tab groups sessions by branch with visual hierarchy

---

## Tasks

### 1. API Investigation
- Determine if branch data available in `/projects/{encoded_name}` endpoint
- Determine if branch data available in session list response
- Identify if new endpoint needed for branch aggregation

### 2. Active Branches Component (Overview Tab)
- Display branches that sessions interacted with
- Filter: "in the last day" per philosophy spec
- Only render for git projects
- Visual: pills or badges similar to Session Overview

### 3. Sessions Grouped by Branch (Sessions Tab)
- Group `SessionCard` components under branch headers
- Collapsible branch sections (reference agent grouping pattern)
- Handle sessions with multiple branches
- Handle sessions with no branch (non-git or untracked)

### 4. Visual Distinction
- Branch header styling
- Session count per branch
- Expand/collapse controls per branch group

---

## Files to Modify/Create

| Action | Path |
|--------|------|
| Create | `apps/web/components/active-branches.tsx` |
| Create | `apps/web/components/sessions-by-branch.tsx` |
| Modify | `apps/web/app/project/[encodedName]/page.tsx` (add Active Branches) |
| Modify | `apps/web/app/project/[encodedName]/sessions/page.tsx` (add grouping) |
| Possibly modify | `apps/api/main.py` (if branch aggregation endpoint needed) |

---

## Dependencies

- Phase 1 (tab structure must exist)

## Blocks

- None
