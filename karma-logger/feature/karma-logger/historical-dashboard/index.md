# Historical Dashboard — Phase Index

**Feature**: Transform karma-logger from session-centric to project-centric historical analysis.

**Source Plan**: [v0.md](./plan/v0.md)

---

## Phases

| Phase | Scope | Files | Complexity | Dependencies |
|-------|-------|-------|------------|--------------|
| [Phase 1](./phase-1.md) | Data Layer | `src/db.ts`, `src/types.ts` | Low | None |
| [Phase 2](./phase-2.md) | API Routes | `src/dashboard/api.ts` | Low | Phase 1 |
| [Phase 3](./phase-3.md) | Projects View | `public/*` | Medium | Phase 2 |
| [Phase 4](./phase-4.md) | Agent Tree | `public/*` | Medium | Phase 2 |
| [Phase 5](./phase-5.md) | History Chart | `public/*`, `charts.js` | Medium-High | Phase 2, 3 |

---

## Dependency Graph

```
Phase 1: Data Layer (db.ts)
    │
    ▼
Phase 2: API Routes ─────────────────────┐
    │                                     │
    ├─────────────┬─────────────┐         │
    ▼             ▼             ▼         │
Phase 3      Phase 4       Phase 5 ◄──────┘
Projects     Agent Tree    History Chart
```

---

## Execution Strategy

**Sequential** within each track, **parallel** where possible:

1. **Phase 1** → Must complete first (data foundation)
2. **Phase 2** → Depends on Phase 1
3. **Phases 3, 4, 5** → Can run in parallel after Phase 2

---

## Success Criteria

From v0 plan:

- [ ] Project list renders with aggregated costs
- [ ] Agent tree displays correct parent-child relationships
- [ ] History chart shows 30-day cost trend
- [ ] Filter by project works across all views
- [ ] Page loads < 1s with 100+ sessions

---

## Quick Reference

### New DB Methods (Phase 1)
- `listProjects()` → `ProjectSummary[]`
- `getProjectSummary(name)` → `ProjectDetail`
- `getDailyMetrics(project?, days)` → `DailyMetric[]`

### New API Endpoints (Phase 2)
- `GET /api/projects`
- `GET /api/projects/:name`
- `GET /api/projects/:name/history?days=30`
- `GET /api/totals/history?days=30`

### New UI Views (Phases 3-5)
- Project list with cards
- Agent hierarchy tree
- Cost trend chart with date range selector
