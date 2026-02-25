# UI Redesign Phases - Overview

**Reference:** `docs/research/redisgn_dashboard_ui/philosophy.md`
**Review:** `docs/improvement/ui-redesign/review.md`

---

## Phase Summary

| Phase | Focus | Dependencies |
|-------|-------|--------------|
| [Phase 1](./phase-1.md) | Project View Tab Structure | None |
| [Phase 2](./phase-2.md) | Project View Branch Features | Phase 1 |
| [Phase 3](./phase-3.md) | Session View Restructure | None |
| [Phase 4](./phase-4.md) | Time-Boxing Analytics | Phase 1, Phase 3 |

---

## Execution Order

```
Phase 1 ─────┬────► Phase 2
             │
             └────► Phase 4
                      ▲
Phase 3 ─────────────┘
```

**Parallel tracks possible:**
- Phase 1 + Phase 3 can run in parallel (independent views)
- Phase 2 requires Phase 1
- Phase 4 requires Phase 1 and Phase 3

---

## Agent Types Reference

| Agent | When to Use |
|-------|-------------|
| `feature-dev:code-architect` | Designing component structure, route architecture, data flow |
| `feature-dev:code-explorer` | Understanding existing implementation, tracing data flow |
| `Explore` | Quick searches, locating files, finding patterns |

---

## Scope Per Phase

### Phase 1: Project View Tab Structure
- Route restructure for Project pages
- Tab navigation component
- Content distribution across tabs
- **Outcome:** Project View has Overview / Sessions / Analytics tabs

### Phase 2: Project View Branch Features
- Active Branches display in Overview
- Sessions grouped by branch in Sessions tab
- **Outcome:** Branch-aware Project View for git projects

### Phase 3: Session View Restructure
- Initial prompt prominent in Overview
- Tools tab renamed to Analytics
- Time format standardization
- **Outcome:** Session View matches philosophy spec

### Phase 4: Time-Boxing Analytics
- Date range selector component
- API integration for date filtering
- Charts respond to date selection
- **Outcome:** Interactive time-boxed analytics

---

## Files Touched Summary

### Phase 1
- `apps/web/app/project/[encodedName]/` (restructure)

### Phase 2
- `apps/web/components/` (new branch components)
- `apps/web/app/project/[encodedName]/` (integrate)
- Possibly `apps/api/` (branch aggregation)

### Phase 3
- `apps/web/app/session/[uuid]/` (restructure)
- `apps/web/app/session/[uuid]/tools/` → `analytics/`

### Phase 4
- `apps/web/components/` (date picker)
- `apps/web/app/project/` and `session/` analytics pages
- `apps/web/hooks/` (date params)
- Possibly `apps/api/` (date query support)
