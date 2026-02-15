# Pagination State Analysis

> Audit date: 2026-02-14

## Pages WITH Pagination

### 1. `/sessions` (Global Sessions)

| Aspect | Detail |
|--------|--------|
| **Frontend file** | `frontend/src/routes/sessions/+page.svelte` |
| **Loader** | `frontend/src/routes/sessions/+page.server.ts` |
| **API endpoint** | `GET /sessions/all` (`api/routers/sessions.py:307-370`) |
| **Param convention** | Offset-based: `limit=50`, `offset=0` |
| **Default page size** | 50 |
| **Pagination UI** | Google-style page numbers with ellipsis (lines 1191-1256) |
| **URL state** | `?limit=50&offset=0&search=...&project=...&branch=...` |

**Filters:** search, project, branch, status

**Filter + Pagination interaction:**
- No filters active: server-side pagination, controls visible
- Any filter active: pagination **disabled**, lazy-loads ALL sessions client-side, filters in-browser
- Display switches from "Showing 1-50 of 500 sessions" to "Showing 125 filtered sessions"

---

### 2. `/projects/[encoded_name]` (Project Detail)

| Aspect | Detail |
|--------|--------|
| **Frontend file** | `frontend/src/routes/projects/[encoded_name]/+page.svelte` |
| **Loader** | `frontend/src/routes/projects/[encoded_name]/+page.server.ts` |
| **API endpoint** | `GET /projects/{encoded_name}` (`api/routers/projects.py:286-474`) |
| **Param convention** | Offset-based: `limit=50`, `offset=0` |
| **Default page size** | 50 |
| **Pagination UI** | Google-style page numbers with ellipsis (lines 754-822) |
| **URL state** | `?limit=50&offset=0&search=...&branch=...` |

**Filters:** search, tokens, scope, status, branch

**Filter + Pagination interaction:** Identical to `/sessions` — filters disable pagination and lazy-load all sessions for client-side filtering.

---

### 3. `/agents` (Agent Usage)

| Aspect | Detail |
|--------|--------|
| **Frontend file** | `frontend/src/routes/agents/+page.svelte` |
| **Loader** | `frontend/src/routes/agents/+page.server.ts` |
| **API endpoint** | `GET /agents/usage` (`api/routers/agents.py:266-355`) |
| **Param convention** | Page-based: `page=1`, `per_page=20` (max 100) |
| **Default page size** | 20 |
| **Pagination UI** | Simple prev/next (lines 529-587) |
| **URL state** | `?page=1&per_page=20&search=...&category=...` |

**Filters:** category, search

**Filter + Pagination interaction:** Filters applied **server-side before** pagination. Category or search change resets page to 1. No client-side filtering.

---

### 4. `/plans` (Plans List)

| Aspect | Detail |
|--------|--------|
| **Frontend file** | `frontend/src/routes/plans/+page.svelte` |
| **Loader** | `frontend/src/routes/plans/+page.server.ts` |
| **API endpoint** | `GET /plans/with-context` (`api/routers/plans.py:258-385`) |
| **Param convention** | Page-based: `page=1`, `per_page=24` (max 100) |
| **Default page size** | 24 |
| **Pagination UI** | Google-style with ellipsis (lines 570-630) |
| **URL state** | `?page=1&per_page=24&search=...&project=...&branch=...` |

**Filters:** project, branch, search

**Filter + Pagination interaction:** Server-side filtering + pagination. Filter change resets page to 1. Uses `replaceState()` for URL sync without full navigation.

---

## Pages WITHOUT Pagination

| Page | Route | Reason |
|------|-------|--------|
| Projects list | `/projects` | Typically <100 projects |
| Analytics | `/analytics` | Aggregated stats, not item lists |
| Skills | `/skills` | Typically <50 skills |
| Settings | `/settings` | Single resource |
| History | `/history` | Single resource view |

---

## Two Frontend Pagination Patterns

### Pattern A: Hybrid Server/Client (Sessions, Project Detail)

```
Initial load → server pagination (limit/offset)
Filter activated → lazy-load ALL items → client-side filter → hide pagination UI
```

- Pros: instant filter results, no server round-trips per keystroke
- Cons: O(n) memory when filtering, won't scale past ~10K sessions

### Pattern B: Pure Server-Side (Agents, Plans)

```
Every load → server handles filtering + pagination → returns page
Filter change → reset to page 1 → server re-queries
```

- Pros: constant memory, scales to any dataset size
- Cons: network round-trip per filter change

---

## Parameter Convention Inconsistency

| Convention | Used By | Parameters |
|-----------|---------|------------|
| Offset-based | Sessions, Project Detail | `limit` + `offset` |
| Page-based | Agents, Plans | `page` + `per_page` |

No shared pagination utility exists. Each endpoint implements pagination independently.

---

## API Response Shapes

**Offset-based endpoints** return:
```json
{
  "session_count": 500,
  "sessions": [...]
}
```

**Page-based endpoints** return:
```json
{
  "total": 500,
  "page": 1,
  "per_page": 20,
  "total_pages": 25,
  "items": [...]
}
```

---

## API Endpoints Missing Pagination

| Endpoint | File | Data Volume Risk | Priority |
|----------|------|-----------------|----------|
| `GET /sessions/{uuid}/timeline` | `api/routers/sessions.py:1325-1365` | 100s-1000s of events | **HIGH** |
| `GET /sessions/{uuid}/file-activity` | `api/routers/sessions.py:1109-1139` | 100s-1000s of file ops | **HIGH** |
| `GET /skills/usage` | `api/routers/skills.py:426-519` | Has `limit` but no `offset` | LOW |
| `GET /sessions/{uuid}/subagents` | `api/routers/sessions.py:1142-1201` | 5-30 typically, could grow | LOW |
| `GET /sessions/{uuid}/tasks` | `api/routers/sessions.py:1019-1106` | 5-20 per session | NONE |
| `GET /sessions/{uuid}/todos` | `api/routers/sessions.py:990-1016` | 3-10 per session | NONE |

---

## Key Insight: Filter + Pagination Tension

The hybrid pattern (sessions/project detail) reveals the core tension:

1. **Server pagination** gives fast initial loads, but the server doesn't know about client-side filters
2. **Client filtering** needs ALL data loaded, defeating pagination's purpose
3. **Current solution**: lazy-load everything when filters activate, disable pagination UI

This works at current scale but won't scale to 10K+ sessions. The long-term fix is moving all filters server-side (like agents/plans already do).

---

## Recommendations

1. **Standardize** on one param convention (`page`/`per_page` preferred — more intuitive)
2. **Add pagination** to `/sessions/{uuid}/timeline` and `/sessions/{uuid}/file-activity`
3. **Create shared utilities** — Pydantic response model for pagination metadata, frontend pagination component
4. **Migrate hybrid pages** to pure server-side filtering for scalability
5. **Add `offset`** to `/skills/usage` for full pagination support
