# Dashboard MVP Feature Phases

**Source:** [DASHBOARD_MVP_PLAN.md](../../../karma-logger/DASHBOARD_MVP_PLAN.md)
**Strategy:** TUI-first, Web-second

---

## Phase Overview

| Phase | Name | Deliverable | Dependencies |
|-------|------|-------------|--------------|
| [1](./phase-1.md) | TUI Core Setup | Ink scaffold, base App, layout | CLI Core |
| [2](./phase-2.md) | TUI MetricsCard | Token/cost display boxes | Phase 1 |
| [3](./phase-3.md) | TUI AgentTree | Hierarchy visualization | Phase 1 |
| [4](./phase-4.md) | TUI Sparkline & Commands | Charts, keyboard, `karma watch --ui` | Phase 1-3 |
| [5](./phase-5.md) | Web Server & SSE | Hono, SSE, API routes | Phase 1-4 |
| [6](./phase-6.md) | Web Dashboard UI | Charts, UI, `karma dashboard` | Phase 5 |

---

## Dependency Graph

```
CLI Core (MVP_PLAN.md)
    │
    ▼
┌─────────────────────────────────────────────┐
│ Phase 1: TUI Core Setup                     │
└─────────────────────────────────────────────┘
    │
    ├──────────────────┬──────────────────┐
    ▼                  ▼                  │
┌────────────┐  ┌────────────┐           │
│ Phase 2:   │  │ Phase 3:   │           │
│ MetricsCard│  │ AgentTree  │           │
└────────────┘  └────────────┘           │
    │                  │                  │
    └──────────────────┴──────────────────┤
                       │                  │
                       ▼                  │
           ┌─────────────────────────────────────┐
           │ Phase 4: Sparkline & Commands       │
           │ (`karma watch --ui`)                │
           └─────────────────────────────────────┘
                       │
                       ▼
           ┌─────────────────────────────────────┐
           │ Phase 5: Web Server & SSE           │
           └─────────────────────────────────────┘
                       │
                       ▼
           ┌─────────────────────────────────────┐
           │ Phase 6: Web Dashboard UI           │
           │ (`karma dashboard`)                 │
           └─────────────────────────────────────┘
```

---

## Tech Stack Summary

### TUI (Phase 1-4)
- **Ink v5** — React-based terminal UI
- **asciichart** — ASCII sparkline charts
- **Yoga** — Flexbox layout (built into Ink)

### Web (Phase 5-6)
- **Hono** — Minimal web server (14KB)
- **Petite-Vue** — Reactive UI (no build step)
- **uPlot** — Time-series charts (40KB)
- **Pico CSS** — Classless styling
- **SSE** — Real-time updates

---

## Commands After MVP

```bash
# TUI Dashboard
karma watch --ui

# Web Dashboard
karma dashboard
karma dashboard --port 8080
karma dashboard --no-open
```

---

## Success Metrics

| Metric | TUI | Web |
|--------|-----|-----|
| Startup | <100ms | <200ms |
| Page Load | N/A | <500KB |
| Refresh Rate | 1Hz | 1Hz |
| Reconnect | N/A | Auto (SSE) |
