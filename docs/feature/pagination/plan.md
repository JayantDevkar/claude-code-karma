# Pagination Improvement Plan

> Created: 2026-02-14 | Status: Draft

## Problem Statement

Pagination works across 4 pages but is implemented independently each time, leading to:
- **~200 lines of duplicated pagination UI** across 3 Svelte files (sessions, projects, plans)
- **2 incompatible API conventions** (limit/offset vs page/per_page)
- **No shared response schema** — each endpoint defines pagination fields inline
- **Hybrid client/server filtering** that won't scale past ~10K sessions

---

## Tiers

| Tier | Focus | ROI | Effort |
|------|-------|-----|--------|
| **1** | Shared components & schemas | High dev value | Low (2-3 days) |
| **2** | Server-side filtering migration | High user value at scale | Medium (3-5 days) |
| **3** | Paginate remaining endpoints | Future-proofing | Low (1-2 days) |

---

## Tier 1: Shared Components & Schemas

### 1A. Backend — Generic `PaginatedResponse[T]`

**Goal:** Eliminate repeated pagination fields from every response schema.

**Current state:** 4 response models define pagination fields independently:

| Schema | File:Line | Items field | Pagination fields |
|--------|-----------|-------------|-------------------|
| `AllSessionsResponse` | `schemas.py:1141` | `sessions` | `total, page, per_page, total_pages` |
| `PlanListResponse` | `schemas.py:666` | `plans` | `total, page, per_page, total_pages` |
| `AgentUsageListResponse` | `schemas.py:952` | `agents` | `total, page, per_page, total_pages` |
| `AgentInvocationHistoryResponse` | `schemas.py:969` | `items` | `total, page, per_page, total_pages` |

**Change:** Create a generic base in `schemas.py`:

```python
from typing import Generic, TypeVar
T = TypeVar("T")

class PaginationMeta(BaseModel):
    """Standard pagination metadata."""
    total: int = Field(0, description="Total items matching filters")
    page: int = Field(1, description="Current page (1-indexed)")
    per_page: int = Field(20, description="Items per page")
    total_pages: int = Field(0, description="Total pages")

class PaginatedResponse(PaginationMeta, Generic[T]):
    """Generic paginated response. Subclass and add your items field."""
    pass
```

Then each response becomes:

```python
class PlanListResponse(PaginatedResponse):
    plans: list[PlanWithContext] = Field(default_factory=list)
    # pagination fields inherited

class AllSessionsResponse(PaginatedResponse):
    sessions: list[SessionWithContext] = Field(default_factory=list)
    projects: list[ProjectFilterOption] = Field(default_factory=list)
    status_options: list[StatusFilterOption] = Field(default_factory=list)
    applied_filters: dict = Field(default_factory=dict)
```

**Also add a helper function** in routers to compute pagination:

```python
def paginate(total: int, page: int, per_page: int) -> dict:
    """Compute pagination metadata."""
    total_pages = max(1, -(-total // per_page))  # ceil division
    page = max(1, min(page, total_pages))
    offset = (page - 1) * per_page
    return {"total": total, "page": page, "per_page": per_page,
            "total_pages": total_pages, "offset": offset}
```

**Files to modify:**
- `api/schemas.py` — add `PaginationMeta`, refactor 4 response classes
- `api/routers/sessions.py` — use helper, convert limit/offset params to page/per_page
- `api/routers/projects.py` — same conversion
- `api/routers/agents.py` — use helper (already page-based)
- `api/routers/plans.py` — use helper (already page-based)

**Breaking change:** Sessions and project-detail endpoints switch from `limit`/`offset` to `page`/`per_page` query params. Frontend loaders must update simultaneously.

---

### 1B. Frontend — Shared `<Pagination>` Component

**Goal:** Replace 3 copy-pasted pagination UIs with one component.

**Current duplication:**

| File | Lines | Style |
|------|-------|-------|
| `sessions/+page.svelte` | 1186–1248 (logic) + 1752–1834 (UI) | Google-style with ellipsis |
| `projects/[encoded_name]/+page.svelte` | 777–822 (logic) + 1380–1450 (UI) | Google-style with ellipsis |
| `plans/+page.svelte` | 208–250 (logic) + 570–630 (UI) | Google-style with ellipsis |
| `agents/+page.svelte` | 529–587 (UI) | Simple prev/next |

All three Google-style implementations share identical `pageNumbers` derivation logic (ellipsis calculation with `...` placeholders).

**New component:** `frontend/src/lib/components/Pagination.svelte`

```svelte
<script lang="ts">
  interface Props {
    total: number;
    page: number;
    perPage: number;
    totalPages: number;
    onPageChange: (page: number) => void;
    variant?: 'full' | 'simple';  // full = Google-style, simple = prev/next
  }
  let { total, page, perPage, totalPages, onPageChange, variant = 'full' }: Props = $props();

  // pageNumbers derivation (moved from 3 files)
  const pageNumbers = $derived.by(() => { /* ellipsis logic */ });
</script>
```

**Props:**

| Prop | Type | Default | Description |
|------|------|---------|-------------|
| `total` | `number` | required | Total items matching filters |
| `page` | `number` | required | Current page (1-indexed) |
| `perPage` | `number` | required | Items per page |
| `totalPages` | `number` | required | Total pages |
| `onPageChange` | `(page: number) => void` | required | Called when user clicks a page |
| `variant` | `'full' \| 'simple'` | `'full'` | Google-style or prev/next |

**Also add a loader utility** in `frontend/src/lib/utils.ts`:

```typescript
export function parsePaginationParams(url: URL, defaults = { page: 1, perPage: 50 }) {
  return {
    page: Math.max(1, parseInt(url.searchParams.get('page') ?? String(defaults.page))),
    perPage: Math.max(1, Math.min(100, parseInt(url.searchParams.get('per_page') ?? String(defaults.perPage)))),
  };
}

export function buildPaginatedUrl(base: string, params: Record<string, any>) {
  const url = new URL(base);
  for (const [k, v] of Object.entries(params)) {
    if (v != null) url.searchParams.set(k, String(v));
  }
  return url.toString();
}
```

**Files to modify:**
- `frontend/src/lib/components/Pagination.svelte` — **new file**
- `frontend/src/lib/utils.ts` — add pagination helpers
- `frontend/src/routes/sessions/+page.svelte` — replace inline pagination with `<Pagination>`
- `frontend/src/routes/sessions/+page.server.ts` — switch to page/per_page params
- `frontend/src/routes/projects/[encoded_name]/+page.svelte` — same
- `frontend/src/routes/projects/[encoded_name]/+page.server.ts` — same
- `frontend/src/routes/plans/+page.svelte` — same
- `frontend/src/routes/agents/+page.svelte` — same (use `variant="simple"` or upgrade to full)

**Lines removed:** ~200 across 3 files (duplicated `pageNumbers` logic + pagination markup).

---

## Tier 2: Server-Side Filtering Migration

### Problem

Sessions (`/sessions/all`) and project-detail (`/projects/{encoded_name}`) use a hybrid pattern:

```
No filters  → server pagination (fast initial load)
Any filter  → lazy-load ALL sessions → filter client-side → hide pagination
```

This means filtering 5,000 sessions requires downloading all 5,000 to the browser. The agents and plans pages already do server-side filtering correctly.

### Solution

Move search, project, branch, status, and scope filters to the API:

1. **API:** Accept filter params and apply them in the SQL/JSONL query BEFORE pagination
2. **Frontend:** Always use server pagination — filter changes trigger `goto()` with new URL params, resetting to page 1
3. **Remove:** Client-side filter logic and lazy-load-all codepath

**API changes (sessions.py):**
- `get_all_sessions()` already accepts `search`, `project`, `branch`, `status` params
- Ensure all filters apply BEFORE the `LIMIT/OFFSET` (or `page/per_page` after Tier 1)
- Currently filters are applied but hybrid mode bypasses them when frontend requests all data

**API changes (projects.py):**
- `get_project()` needs `search`, `branch`, `status`, `scope` params applied server-side before pagination
- Remove the "no limit" codepath that returns all sessions

**Frontend changes:**
- Remove `allSessions` lazy-loading state in sessions and project-detail pages
- Remove client-side filter functions
- On filter change: `goto(newUrl)` with filter + `page=1`
- Always show pagination controls

**Files to modify:**
- `api/routers/sessions.py` — ensure filters apply before pagination, remove unlimited codepath
- `api/routers/projects.py` — add server-side filter params
- `frontend/src/routes/sessions/+page.svelte` — remove client-side filtering
- `frontend/src/routes/sessions/+page.server.ts` — always pass page/per_page
- `frontend/src/routes/projects/[encoded_name]/+page.svelte` — same
- `frontend/src/routes/projects/[encoded_name]/+page.server.ts` — same

**Risk:** Slightly slower filter UX (network round-trip per filter change vs instant client-side). Mitigate with debounced search input (already exists) and SvelteKit's streaming.

---

## Tier 3: Paginate Remaining Endpoints

### 3A. Timeline (`GET /sessions/{uuid}/timeline`)

- **File:** `api/routers/sessions.py:1325-1365`
- **Risk:** Long sessions produce 1000+ timeline events
- **Fix:** Add `page`/`per_page` params, return `PaginatedResponse`
- **Frontend:** Virtual scroll or "load more" button in timeline view

### 3B. File Activity (`GET /sessions/{uuid}/file-activity`)

- **File:** `api/routers/sessions.py:1109-1139`
- **Risk:** Same as timeline — long sessions = hundreds of file ops
- **Fix:** Same approach as 3A

### 3C. Skills Usage (`GET /skills/usage`)

- **File:** `api/routers/skills.py:426-519`
- **Issue:** Has `limit` param but no `offset` — can't page past first N
- **Fix:** Add `page`/`per_page` to match standard convention

### 3D. Not needed

These endpoints return small, bounded datasets and don't need pagination:
- `GET /sessions/{uuid}/subagents` (5-30 items)
- `GET /sessions/{uuid}/tasks` (5-20 items)
- `GET /sessions/{uuid}/todos` (3-10 items)
- `GET /projects` (<100 items)
- `GET /skills` (<50 items)

---

## Implementation Order

```
Tier 1A (backend schema)
  ↓
Tier 1B (frontend component)  ← can be done in parallel with 1A
  ↓
Integration: wire new component to new API convention
  ↓
Tier 2 (server-side filtering) ← depends on Tier 1
  ↓
Tier 3 (remaining endpoints)   ← independent, can be done anytime
```

### Tier 1 Checklist

- [ ] Create `PaginationMeta` base class in `schemas.py`
- [ ] Create `paginate()` helper function
- [ ] Refactor `AllSessionsResponse` to inherit `PaginationMeta`
- [ ] Refactor `PlanListResponse` to inherit `PaginationMeta`
- [ ] Refactor `AgentUsageListResponse` to inherit `PaginationMeta`
- [ ] Refactor `AgentInvocationHistoryResponse` to inherit `PaginationMeta`
- [ ] Convert sessions endpoint from limit/offset to page/per_page
- [ ] Convert project-detail endpoint from limit/offset to page/per_page
- [ ] Create `<Pagination>` component
- [ ] Add `parsePaginationParams()` utility
- [ ] Replace pagination in sessions page
- [ ] Replace pagination in project-detail page
- [ ] Replace pagination in plans page
- [ ] Replace/upgrade pagination in agents page
- [ ] Update all `+page.server.ts` loaders for new param convention
- [ ] Test all 4 paginated pages end-to-end

### Tier 2 Checklist

- [ ] Audit sessions endpoint filter application order
- [ ] Audit project-detail endpoint filter application order
- [ ] Remove "load all" codepath from sessions frontend
- [ ] Remove "load all" codepath from project-detail frontend
- [ ] Remove client-side filter logic from both pages
- [ ] Add debounce to search inputs (verify existing)
- [ ] Test filters + pagination interaction on all pages

---

## Metrics of Success

| Metric | Before | After Tier 1 | After Tier 2 |
|--------|--------|--------------|--------------|
| Duplicated pagination UI lines | ~200 | 0 | 0 |
| Pagination param conventions | 2 | 1 | 1 |
| Response schemas with inline pagination | 4 | 0 | 0 |
| Pages with client-side filtering | 2 | 2 | 0 |
| New paginated page effort | ~80 lines | ~5 lines | ~5 lines |
