# UI/UX Improvement Plan - Overview

**Project**: Claude Karma Dashboard
**Date**: January 2026
**Status**: Planning Complete

---

## Executive Summary

This improvement plan transforms the Claude Karma dashboard from a functional data display into a beautiful, accessible, and delightful analytics experience. Based on the comprehensive UI/UX review in [`../review/ui-ux-observations.md`](../review/ui-ux-observations.md), we have identified 30+ issues organized into 6 implementation phases.

---

## Phase Overview

| Phase | Title | Priority | Effort | Impact | Status |
|-------|-------|----------|--------|--------|--------|
| [1](./ui-ux--phase-1.md) | Foundation & Design System | Critical | Medium | High | Planned |
| [2](./ui-ux--phase-2.md) | Data Sanitization & Display | Critical | Medium | High | Planned |
| [3](./ui-ux--phase-3.md) | Session Cards & Components | High | Medium | High | Planned |
| [4](./ui-ux--phase-4.md) | Timeline & Interactivity | High | High | High | Planned |
| [5](./ui-ux--phase-5.md) | Navigation & Accessibility | Medium | Medium | High | Planned |
| [6](./ui-ux--phase-6.md) | Dashboard Polish & Delight | Medium | Medium | Medium | Planned |

---

## Key Issues Addressed

### Critical Issues (Phase 1-2)

1. **Identical background/card colors** - No visual depth or hierarchy
2. **Missing tabular numbers** - Metric misalignment in grids
3. **XML tags visible in prompts** - Raw `<local-command-caveat>` tags shown
4. **Negative durations** - `-1s` displayed instead of handling edge case
5. **Raw model names** - `opus-4-5-20251101` instead of "4.5 Opus"
6. **Generic session titles** - "Session" instead of slug or UUID

### High Priority Issues (Phase 3-4)

7. **Session card visual hierarchy** - Flat information presentation
8. **UUID-only session names** - No context for sessions without slugs
9. **Timeline filter clarity** - Filter states unclear
10. **Tool call detail formatting** - Raw JSON instead of formatted display
11. **Elapsed time calculation** - All events showing `+0:00`

### Medium Priority Issues (Phase 5-6)

12. **No command palette** - No keyboard-first navigation
13. **Missing skip-to-content** - Accessibility gap
14. **No ARIA labels on charts** - Screen reader inaccessible
15. **No trend indicators** - No historical context on stats
16. **No activity sparklines** - No at-a-glance activity visualization

---

## Dependency Graph

```
Phase 1 (Foundation)
    ↓
Phase 2 (Data Sanitization)
    ↓
Phase 3 (Components) ←──────┐
    ↓                       │
Phase 4 (Timeline) ─────────┤
    ↓                       │
Phase 5 (Navigation) ───────┘
    ↓
Phase 6 (Polish)
```

---

## Implementation Order

### Sprint 1: Foundation (Phase 1 + 2)
- Design tokens and CSS variables
- Typography improvements
- Content sanitization utilities
- Duration/token/model formatters

### Sprint 2: Core Components (Phase 3 + 4)
- Session card redesign
- Project card enhancements
- Timeline filter bar
- Event card formatting
- Keyboard navigation

### Sprint 3: Polish (Phase 5 + 6)
- Command palette
- Accessibility improvements
- Trend indicators
- Sparklines
- Micro-animations

---

## New Files Created

| File | Phase | Purpose |
|------|-------|---------|
| `lib/content-sanitizer.ts` | 2 | Remove XML tags from content |
| `lib/session-display.ts` | 3 | Session naming utilities |
| `components/model-badge.tsx` | 2 | Formatted model display |
| `components/trend-indicator.tsx` | 6 | Trend arrows and values |
| `components/sparkline.tsx` | 6 | Mini activity charts |
| `components/freshness-indicator.tsx` | 6 | Last updated badges |
| `components/command-palette.tsx` | 5 | Cmd+K navigation |
| `components/skip-link.tsx` | 5 | Accessibility skip link |
| `components/accessible-chart.tsx` | 5 | ARIA wrapper for charts |
| `components/breadcrumb.tsx` | 5 | Full navigation path |
| `components/timeline-filter-bar.tsx` | 4 | Enhanced filter UI |
| `components/tool-call-detail.tsx` | 4 | Formatted tool content |
| `components/todo-update-detail.tsx` | 4 | Todo list in timeline |
| `hooks/use-command-palette.ts` | 5 | Keyboard shortcut hook |
| `hooks/use-timeline-keyboard.ts` | 4 | Timeline navigation |
| `hooks/use-focus-management.ts` | 5 | Focus trap utilities |

---

## Modified Files

| File | Phases | Changes |
|------|--------|---------|
| `globals.css` | 1, 6 | Design tokens, animations |
| `stats-card.tsx` | 1, 6 | Tabular nums, trends, sparklines |
| `session-card.tsx` | 2, 3 | Sanitizer, redesign |
| `project-card.tsx` | 3 | Enhanced layout |
| `timeline-rail.tsx` | 2, 4 | Sanitizer, event formatting |
| `loading-skeletons.tsx` | 6 | Shimmer effect |
| `empty-state.tsx` | 6 | Contextual illustrations |
| `layout.tsx` | 5, 6 | Command palette, skip link, toasts |

---

## Dependencies to Install

```bash
pnpm add cmdk sonner
```

---

## Verification Milestones

### After Phase 2
- [ ] No XML tags visible anywhere in UI
- [ ] No negative durations displayed
- [ ] Model names show "4.5 Opus" format

### After Phase 4
- [ ] Timeline filters toggle with visual feedback
- [ ] Tool calls show formatted input/output
- [ ] Keyboard navigation works (j/k/Enter/Esc)

### After Phase 6
- [ ] Stats cards show trend indicators
- [ ] Shimmer loading skeletons work
- [ ] Lighthouse accessibility score >= 90

---

## Success Metrics

| Metric | Current | Target |
|--------|---------|--------|
| Lighthouse Accessibility | ~70 | >= 90 |
| Data Display Errors | ~10 issues | 0 |
| Keyboard-Navigable Views | ~30% | 100% |
| Design Token Coverage | ~40% | 100% |

---

## Related Documentation

- [UI/UX Observations](../review/ui-ux-observations.md) - Raw findings
- [Backend Observations](../review/observations.md) - API data flow
- [Home View Logic](../home-view.md) - Home page data flow
- [Project View Logic](../project-view.md) - Project page data flow
- [Session View Logic](../session-view.md) - Session page data flow

---

## Next Steps

1. Review and approve this plan
2. Create implementation tickets for Sprint 1
3. Begin Phase 1 implementation
4. Schedule design review after Phase 2 completion
