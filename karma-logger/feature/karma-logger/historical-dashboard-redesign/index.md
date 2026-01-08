# Historical Dashboard Redesign — Phase Index

**Feature**: Transform karma-logger web dashboard with improved data density, interaction states, and power user features.

**Source Plan**: [web-ui-redesign.md](../dashboard/web-ui-redesign.md)

---

## Implementation Status (this branch)

**Implemented (2026-01-08)**:
- **Phase 1**: Compact single-line header + denser 4-up metric cards
- **Phase 2**: Hover/focus/active/disabled interaction states + reduced-motion support
- **Phase 3**: Connection indicator + reconnect banner with exponential backoff + manual retry

**Files touched for Phases 1–3** (actual implementation):
- `src/dashboard/public/index.html`
- `src/dashboard/public/style.css`
- `src/dashboard/public/app.js`

**Notes**:
- Connection dot now reflects `connected/reconnecting/disconnected/error` via `connectionState` in `app.js`.
- Banner UI is wired and dismissible; retry triggers a fresh SSE connect.

---

## Phases

| Phase | Focus | Files | Effort | Impact | Dependencies |
|-------|-------|-------|--------|--------|--------------|
| [Phase 1](./phase-1.md) | Layout Foundation | `style.css`, `index.html` | Low | High | None |
| [Phase 2](./phase-2.md) | Interaction States | `style.css` | Low | High | Phase 1 |
| [Phase 3](./phase-3.md) | Error & Connection States | `app.js`, `style.css`, `index.html` | Low | High | Phase 1-2 |
| [Phase 4](./phase-4.md) | Sparklines & Trends | `charts.js`, `app.js`, `style.css` | Medium | High | Phase 1 |
| [Phase 5](./phase-5.md) | Agent Tree Redesign | `app.js`, `style.css` | Medium | High | Phase 1-2 |
| [Phase 6](./phase-6.md) | Empty & Loading States | `app.js`, `style.css` | Low | Medium | Phase 1-2 |
| [Phase 7](./phase-7.md) | Projects & History Polish | `app.js`, `charts.js`, `style.css` | Medium | Medium | Phase 4 |
| [Phase 8](./phase-8.md) | Keyboard Navigation | `app.js`, `style.css` | Medium | High | Phase 1-2 |
| [Phase 9](./phase-9.md) | Celebrations & Alerts | `app.js`, `style.css` | Medium | Medium | Phase 4, 6 |
| [Phase 10](./phase-10.md) | Power Features | `app.js`, `style.css` | High | Medium | Phase 8 |

---

## Dependency Graph

```
Phase 1: Layout Foundation
    │
    ├───────────────────────────────────────┐
    ▼                                       ▼
Phase 2: Interaction States          Phase 4: Sparklines
    │                                       │
    ├───────┬───────┬───────┐               │
    ▼       ▼       ▼       ▼               │
Phase 3  Phase 5  Phase 6  Phase 8          │
Error    Agent    Empty    Keyboard         │
States   Tree     States   Nav              │
    │                                       │
    │       ┌───────────────────────────────┘
    ▼       ▼
Phase 7: Projects & History Polish
    │
    ├───────┐
    ▼       ▼
Phase 9  Phase 10
Alerts   Power Features
```

---

## Priority Matrix (Effort vs Impact)

```
                    LOW EFFORT          HIGH EFFORT
              ┌─────────────────────┬─────────────────────┐
  HIGH        │ ★ Phase 1 (Layout)  │ Phase 7 (Projects)  │
  IMPACT      │ ★ Phase 2 (States)  │ Phase 8 (Keyboard)  │
              │ ★ Phase 3 (Errors)  │                     │
              │   Phase 4 (Sparklines)                    │
              │   Phase 5 (Tree)    │                     │
              ├─────────────────────┼─────────────────────┤
  LOW         │ Phase 6 (Empty)     │ Phase 10 (Power)    │
  IMPACT      │ Phase 9 (Alerts)    │                     │
              └─────────────────────┴─────────────────────┘
              
              ★ = Implement first (Week 1-2)
```

---

## Execution Strategy

**Recommended Order:** 1 → 2 → 3 → 4 → 5 → 6 → 7 → 8 → 9 → 10

**Parallel Opportunities:**
- After Phase 2: Phases 3, 5, 6, 8 can run in parallel
- After Phase 4: Phase 7 can start

**MVP Definition (Phases 1-6):**
- New layout with compact header
- Interaction states for polish
- Error handling for reliability
- Sparklines for trend visibility
- Agent tree for hierarchy clarity
- Empty states for UX completeness

---

## Success Criteria

From original design doc:

### Core Metrics
- [ ] Above-the-fold metrics: 4+ (currently 3)
- [ ] Time to key insight: <2s (currently ~3s)
- [ ] Vertical scroll in live view: Optional (currently required)
- [ ] Empty state helpfulness: High (currently low)

### Interaction Quality
- [ ] 100% interactive elements with all states (currently ~20%)
- [ ] All errors actionable
- [ ] Full keyboard-only navigation
- [ ] WCAG AA compliant focus visibility

### Power User Adoption (90-day targets)
- [ ] Keyboard shortcut usage: 30% of sessions
- [ ] Custom date range usage: 20% of history views
- [ ] Cost alerts configured: 50% of users

---

## Files Modified

### Primary Files
| File | Phases |
|------|--------|
| `public/style.css` | 1, 2, 3, 4, 5, 6, 7, 8, 9, 10 |
| `public/app.js` | 3, 4, 5, 6, 7, 8, 9, 10 |
| `public/index.html` | 1, 3, 6 |
| `public/charts.js` | 4, 7 |

### New Components
- `<metric-card>` with sparkline (Phase 4)
- `<agent-tree-node>` with ASCII connectors (Phase 5)
- Skeleton loading components (Phase 6)
- Command palette modal (Phase 10)

---

## Color System Additions

| Name | Hex | Usage |
|------|-----|-------|
| Opus Purple | `#7c3aed` | Opus model badge |
| Sonnet Blue | `#3b82f6` | Sonnet model badge |
| Haiku Green | `#10b981` | Haiku model badge |
| Trend Up | `#22c55e` | Positive change |
| Trend Down | `#ef4444` | Negative change |
| Skeleton | `#334155` | Loading placeholders |

---

## Quick Reference

### CSS Variables to Add (Phase 1)
```css
--color-opus: #7c3aed;
--color-sonnet: #3b82f6;
--color-haiku: #10b981;
--color-trend-up: #22c55e;
--color-trend-down: #ef4444;
--color-skeleton: #334155;
```

### Keyboard Shortcuts (Phase 8)
| Key | Action |
|-----|--------|
| `1` | Live view |
| `2` | Projects view |
| `3` | History view |
| `r` | Refresh |
| `?` | Help modal |
| `e` | Expand all |
| `c` | Collapse all |

### Component Classes (All Phases)
- `.metric-card--compact` (Phase 1)
- `.metric-card__sparkline` (Phase 4)
- `.agent-node__connector` (Phase 5)
- `.skeleton` (Phase 6)
- `.error-card` (Phase 3)
- `.toast` (Phase 9)
