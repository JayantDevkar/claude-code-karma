# Bridge: Dashboard ↔ Walkie-Talkie Implementation Plan

> **Total Phases:** 11 | **Estimated Complexity:** Low-Medium
> **Source:** `karma-logger/bridge_walkie_talkie_and_dashboard.md`

## Phase Overview

```
Phase 1: Wire Socket Server (Backend Plumbing) ✅ COMPLETED
├── 1a: Import SocketServer        [Low] ✅
├── 1b: Start server conditionally [Low] ✅
├── 1c: Cleanup on shutdown        [Low] ✅
└── 1d: Add --radio CLI flag       [Low] ✅

Phase 2: Session Agent Tracking (Cache Population)
├── 2a: Register agents in cache   [Low]
└── 2b: Unregister agents          [Low]

Phase 3: Frontend Visualization (UI Implementation)
├── 3a: SSE event handlers         [Medium]
├── 3b: Agent status panel HTML    [Medium]
└── 3c: CSS styles                 [Low]

Phase 4: End-to-End Testing (Validation)
├── 4a: Hook configuration         [Medium]
├── 4b: Integration testing        [Medium]
└── 4c: Documentation updates      [Low]
```

## Execution Order

| # | Phase | Dependencies | Priority |
|---|-------|--------------|----------|
| 1 | 1a | None | High |
| 2 | 1b | 1a | High |
| 3 | 1c | 1b | High |
| 4 | 1d | None (parallel with 1a-1c) | High |
| 5 | 2a | 1d | High |
| 6 | 2b | 2a | High |
| 7 | 3a | 2b | Medium |
| 8 | 3b | 3a | Medium |
| 9 | 3c | 3b | Medium |
| 10 | 4a | 3c | Medium |
| 11 | 4b | 4a | Medium |
| 12 | 4c | 4b | Medium |

## Milestones

| Milestone | After Phase | Deliverable |
|-----------|-------------|-------------|
| **M1** | 1d | `karma radio` CLI communicates with dashboard |
| **M2** | 2b | `/api/radio/session/:id/tree` returns hierarchies |
| **M3** | 3c | Dashboard shows real-time agent status |
| **M4** | 4c | Full E2E integration with documentation |

## Quick Links

### Phase 1: Socket Server
- [1a: Import](phase-1a-socket-server-import.md)
- [1b: Start](phase-1b-socket-server-start.md)
- [1c: Cleanup](phase-1c-socket-cleanup.md)
- [1d: CLI Flag](phase-1d-radio-flag.md)

### Phase 2: Session Tracking
- [2a: Register](phase-2a-session-agents-register.md)
- [2b: Unregister](phase-2b-session-agents-unregister.md)

### Phase 3: Frontend
- [3a: SSE Handlers](phase-3a-frontend-sse-handlers.md)
- [3b: Status Panel](phase-3b-agent-status-panel.md)
- [3c: Styles](phase-3c-agent-status-styles.md)

### Phase 4: Testing
- [4a: Hooks](phase-4a-hook-configuration.md)
- [4b: Integration](phase-4b-integration-testing.md)
- [4c: Documentation](phase-4c-documentation.md)

## Files Modified Summary

| File | Phases |
|------|--------|
| `src/dashboard/server.ts` | 1a, 1b, 1c |
| `src/commands/dashboard.ts` | 1d |
| `src/aggregator.ts` | 2a, 2b |
| `src/dashboard/public/app.js` | 3a, 3b |
| `src/dashboard/public/index.html` | 3b |
| `src/dashboard/public/style.css` | 3c |
| `src/walkie-talkie/SETUP.md` | 4c |
| `FRONTEND_RADIO_GUIDE.md` (new) | 4c |
