# Karma Logger Dashboard MVP Plan

**Date:** 2026-01-08
**Status:** Planning
**Depends On:** MVP_PLAN.md (CLI Core)

---

## Executive Summary

The Dashboard MVP adds visual metrics exploration to Karma Logger. This plan evaluates TUI vs Web approaches and recommends a **phased strategy**: TUI-first for immediate value, web dashboard as upgrade path.

---

## Research Summary

### Approach Comparison

| Approach | Startup | Bundle | Complexity | Real-time | User Reach |
|----------|---------|--------|------------|-----------|------------|
| **TUI (Ink)** | <50ms | 0 | Low | Native | Devs only |
| **Local Web** | 100-300ms | ~500KB | Medium | SSE | Browser |
| **Tauri App** | 500ms+ | 2-10MB | High | Native | All users |
| **Electron** | 1-3s | 100MB+ | High | Native | All users |

### TUI Frameworks (Node.js)

| Library | Style | TypeScript | Status | Best For |
|---------|-------|------------|--------|----------|
| **Ink** | React components | Native | Active | Dynamic UIs |
| **Neo-blessed** | Widget-based | Partial | Fork | Complex layouts |
| **Charm** | Minimal | Yes | Active | Simple output |

**Recommendation:** Ink for React familiarity, Flexbox layouts, active ecosystem.

### Web Frameworks (Local Server)

| Framework | Bundle | Requests/sec | TypeScript | Best For |
|-----------|--------|--------------|------------|----------|
| **Hono** | ~14KB | 70k+ | Native | Edge, minimal |
| **Fastify** | ~200KB | 76k | Native | Validation, plugins |
| **Express** | ~500KB | 15k | Via types | Ecosystem, legacy |

**Recommendation:** Hono for minimal footprint, Web Standards, Bun compatibility.

### Chart Libraries

| Library | Bundle Size | Render | TypeScript | Best For |
|---------|-------------|--------|------------|----------|
| **uPlot** | ~40KB | Canvas | Yes | Time-series, performance |
| **Chart.js** | ~200KB | Canvas | Yes | General charts |
| **Plotly** | ~3MB | SVG/WebGL | Yes | Complex analytics |

**Recommendation:** uPlot for minimal size and time-series optimization.

### Real-time Updates

| Method | Direction | Reconnect | Complexity | Best For |
|--------|-----------|-----------|------------|----------|
| **SSE** | Server→Client | Built-in | Low | Metrics streaming |
| **WebSocket** | Bidirectional | Manual | Medium | Interactive apps |
| **Polling** | Pull-based | N/A | Lowest | Simple cases |

**Recommendation:** SSE for one-way metrics flow with automatic reconnection.

---

## Architecture Decision

### Recommended: Phased Approach

```
Phase 1: TUI Dashboard (karma watch --ui)
Phase 2: Local Web Dashboard (karma dashboard)
Phase 3: Optional Tauri wrapper (future)
```

### Rationale

1. **TUI First** — Zero additional dependencies, instant startup, stays in terminal workflow
2. **Web Second** — Richer visualization, shareable views, browser already open
3. **Skip Electron** — 100MB+ overhead unjustifiable for local metrics tool

---

## Phase 1: TUI Dashboard

### Tech Stack

| Component | Choice | Rationale |
|-----------|--------|-----------|
| **Framework** | Ink v5 | React model, TypeScript native |
| **Layout** | Yoga (Flexbox) | Built into Ink |
| **Charts** | ASCII (cli-chart, asciichart) | Terminal-native |
| **Colors** | Chalk | Ink dependency |

### Commands

```bash
karma watch --ui          # Interactive TUI dashboard
karma status --tree       # Agent hierarchy tree
karma watch --compact     # Minimal live metrics
```

### UI Layout

```
┌─────────────────────────────────────────────────────────────┐
│  KARMA LOGGER                           Session: abc123     │
├─────────────────────────────────────────────────────────────┤
│  LIVE METRICS                                               │
│  ┌─────────────┐ ┌─────────────┐ ┌─────────────┐           │
│  │ Tokens In   │ │ Tokens Out  │ │ Total Cost  │           │
│  │   124,500   │ │    45,200   │ │    $2.34    │           │
│  └─────────────┘ └─────────────┘ └─────────────┘           │
├─────────────────────────────────────────────────────────────┤
│  AGENT TREE                                                 │
│  ├── main (sonnet)          $1.20  [████████░░] 80%        │
│  │   ├── explore-a3b (haiku)  $0.15  ✓                     │
│  │   ├── bash-c4d (haiku)     $0.08  ✓                     │
│  │   └── refactor-e5f (sonnet) $0.91  ⟳ running            │
│  └── total agents: 4                                        │
├─────────────────────────────────────────────────────────────┤
│  TOKEN FLOW (last 60s)                                      │
│  ▁▂▃▄▅▆▇█▇▆▅▄▃▂▁▂▃▄▅▆▇█▇▆▅▄▃▂▁▂▃▄▅▆▇█▇▆▅▄▃▂▁              │
│                                                             │
│  [q] Quit  [r] Refresh  [t] Toggle tree  [h] Help          │
└─────────────────────────────────────────────────────────────┘
```

### Implementation

```
karma-logger/
├── src/
│   └── tui/
│       ├── App.tsx              # Main Ink component
│       ├── components/
│       │   ├── MetricsCard.tsx  # Token/cost boxes
│       │   ├── AgentTree.tsx    # Hierarchy display
│       │   ├── Sparkline.tsx    # ASCII chart
│       │   └── StatusBar.tsx    # Keyboard hints
│       └── hooks/
│           ├── useMetrics.ts    # Subscribe to aggregator
│           └── useKeyboard.ts   # Input handling
```

### Dependencies

```json
{
  "ink": "^5.0.0",
  "ink-spinner": "^5.0.0",
  "@inkjs/ui": "^2.0.0",
  "asciichart": "^1.5.0"
}
```

---

## Phase 2: Web Dashboard

### Tech Stack

| Component | Choice | Rationale |
|-----------|--------|-----------|
| **Server** | Hono | 14KB, Web Standards, Bun-ready |
| **Frontend** | Vanilla + Petite-Vue | Minimal, no build step |
| **Charts** | uPlot | 40KB, time-series optimized |
| **Updates** | Server-Sent Events | One-way, auto-reconnect |
| **Styling** | Pico CSS | Classless, minimal |

### Commands

```bash
karma dashboard           # Launch web UI at localhost:3333
karma dashboard --port 8080
karma dashboard --open    # Auto-open browser
```

### Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                     Browser (localhost:3333)                 │
│  ┌───────────────────────────────────────────────────────┐  │
│  │  Vanilla JS + Petite-Vue                              │  │
│  │  • uPlot charts (token flow, cost over time)          │  │
│  │  • Agent tree visualization                           │  │
│  │  • Session history table                              │  │
│  └────────────────────────┬──────────────────────────────┘  │
│                           │ SSE                              │
└───────────────────────────┼─────────────────────────────────┘
                            │
┌───────────────────────────▼─────────────────────────────────┐
│                      Hono Server                             │
│  GET /                    → Dashboard HTML                   │
│  GET /api/session         → Current session data             │
│  GET /api/sessions        → Historical sessions              │
│  GET /events              → SSE stream                       │
└──────────────────────────────────────────────────────────────┘
```

### UI Wireframe

```
┌─────────────────────────────────────────────────────────────┐
│  🔥 Karma Logger                        Session: abc123     │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  ┌──────────────────────────────────────────────────────┐  │
│  │  Token Usage Over Time                    [uPlot]    │  │
│  │  ▄▄▄                                                 │  │
│  │ ▄████▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄      │  │
│  │ 2m ago                                      now      │  │
│  └──────────────────────────────────────────────────────┘  │
│                                                             │
│  ┌────────────┐ ┌────────────┐ ┌────────────┐              │
│  │ Tokens In  │ │ Tokens Out │ │ Total Cost │              │
│  │  124,500   │ │   45,200   │ │   $2.34    │              │
│  │   +2.3k/s  │ │   +890/s   │ │  +$0.02/s  │              │
│  └────────────┘ └────────────┘ └────────────┘              │
│                                                             │
│  ┌──────────────────────────────────────────────────────┐  │
│  │  Agent Hierarchy                                     │  │
│  │  ├── main (claude-sonnet-4)                          │  │
│  │  │   ├── explore-a3b (claude-haiku) ✓ $0.15         │  │
│  │  │   └── refactor-e5f (claude-sonnet) ⟳ $0.91       │  │
│  └──────────────────────────────────────────────────────┘  │
│                                                             │
│  ┌──────────────────────────────────────────────────────┐  │
│  │  Recent Sessions                                     │  │
│  │  ┌────────┬───────────┬─────────┬────────┬────────┐ │  │
│  │  │ ID     │ Project   │ Agents  │ Tokens │ Cost   │ │  │
│  │  ├────────┼───────────┼─────────┼────────┼────────┤ │  │
│  │  │ abc123 │ karma     │ 4       │ 170K   │ $2.34  │ │  │
│  │  │ xyz789 │ karma     │ 12      │ 450K   │ $5.67  │ │  │
│  │  └────────┴───────────┴─────────┴────────┴────────┘ │  │
│  └──────────────────────────────────────────────────────┘  │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### File Structure

```
karma-logger/
├── src/
│   └── dashboard/
│       ├── server.ts           # Hono routes
│       ├── sse.ts              # Event streaming
│       └── public/
│           ├── index.html      # Single page
│           ├── style.css       # Pico + custom
│           ├── app.js          # Petite-Vue app
│           └── charts.js       # uPlot setup
```

### Dependencies

```json
{
  "hono": "^4.0.0"
}
```

Client-side (CDN, no install):
- Petite-Vue: https://unpkg.com/petite-vue
- uPlot: https://unpkg.com/uplot
- Pico CSS: https://unpkg.com/@picocss/pico

---

## Implementation Phases

### Phase 1: TUI Dashboard
- [ ] Install Ink and dependencies
- [ ] Create base App component with layout
- [ ] Implement MetricsCard component
- [ ] Build AgentTree component
- [ ] Add Sparkline for token flow
- [ ] Wire up keyboard navigation
- [ ] Integrate with existing aggregator
- [ ] Add `karma watch --ui` command

### Phase 2: Web Dashboard
- [ ] Set up Hono server
- [ ] Create HTML template with Pico CSS
- [ ] Implement SSE endpoint
- [ ] Add API routes for session data
- [ ] Build uPlot charts
- [ ] Create agent tree visualization
- [ ] Add session history table
- [ ] Implement `karma dashboard` command

---

## Success Criteria

### TUI Dashboard
1. Renders within 100ms of command
2. Updates smoothly at 1Hz refresh rate
3. Agent tree correctly reflects hierarchy
4. Keyboard shortcuts work reliably
5. No flicker or rendering artifacts

### Web Dashboard
1. Server starts in <200ms
2. Initial page load <500KB total
3. SSE reconnects automatically
4. Charts render 1000+ data points smoothly
5. Works in Chrome, Firefox, Safari

---

## Open Questions

1. **Chart data retention**: How many data points to keep in memory?
   - *Recommendation*: 3600 points (1 hour at 1Hz)

2. **Multi-session view**: Show all active sessions or just current?
   - *Recommendation*: Current session focus, history in table

3. **Theme support**: Light/dark mode?
   - *Recommendation*: System preference detection, MVP = dark only

4. **Export**: Allow chart/data export?
   - *Recommendation*: Out of scope for MVP, add later

---

## References

- [Ink Documentation](https://github.com/vadimdemedes/ink)
- [Hono Documentation](https://hono.dev/)
- [uPlot Documentation](https://github.com/leeoniya/uPlot)
- [Pico CSS](https://picocss.com/)
- [Server-Sent Events MDN](https://developer.mozilla.org/en-US/docs/Web/API/Server-sent_events)

---

## Next Steps

1. Complete CLI MVP from MVP_PLAN.md
2. Implement TUI dashboard (`karma watch --ui`)
3. Gather user feedback on TUI
4. Proceed to web dashboard if demand exists
