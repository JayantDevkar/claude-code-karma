# UI/UX Improvement Plan - Phase 1: Foundation & Design System

**Priority**: Critical
**Effort**: Medium
**Impact**: High (affects all views)

---

## Overview

This phase establishes a robust design foundation that will support all subsequent improvements. It addresses core issues in the CSS variables, typography, and visual hierarchy.

---

## Issue 1: Identical Background & Card Colors

### Current State

```css
/* globals.css */
.dark {
  --background: 224 71% 4%;  /* Same as card */
  --card: 224 71% 4%;        /* Same as background */
}
```

Cards blend into the background, creating a flat visual appearance with no depth hierarchy.

### Improvement

Introduce a layered elevation system with distinct surface levels:

```css
/* globals.css - Dark Mode */
.dark {
  /* Base layer - deepest */
  --background: 225 71% 3%;

  /* Surface elevation tiers */
  --surface-1: 224 71% 5%;     /* Cards on background */
  --surface-2: 224 68% 8%;     /* Elevated cards, dropdowns */
  --surface-3: 224 65% 12%;    /* Modals, popovers */

  /* Card uses surface-1 by default */
  --card: var(--surface-1);
}
```

### Implementation Files

| File | Change |
|------|--------|
| `apps/web/app/globals.css` | Add `--surface-1`, `--surface-2`, `--surface-3` variables |
| `apps/web/components/ui/card.tsx` | Use `bg-card` (already correct) |
| `apps/web/components/timeline-rail.tsx` | Use `bg-surface-2` for event cards |

### Visual Result

```
┌─────────────────────────────────────────┐  ← surface-3 (modal)
│ ┌─────────────────────────────────────┐ │
│ │ Stats Card                          │ │  ← surface-2 (hover state)
│ └─────────────────────────────────────┘ │
│ ┌─────────────────────────────────────┐ │
│ │ Session Card                        │ │  ← surface-1 (card)
│ └─────────────────────────────────────┘ │
└─────────────────────────────────────────┘  ← background (base)
```

---

## Issue 2: Typography - Missing Tabular Numbers

### Current State

Metric values (session counts, token counts, durations) use proportional figures, causing visual misalignment in grids.

```typescript
// stats-card.tsx
<p className="text-2xl font-bold">{value}</p>  // Sans-serif, proportional
```

### Improvement

Add tabular number styling for all metric displays:

```css
/* globals.css */
@layer utilities {
  .tabular-nums {
    font-variant-numeric: tabular-nums;
    font-feature-settings: 'tnum' 1;
  }

  .metric-value {
    @apply tabular-nums font-mono text-2xl font-semibold tracking-tight;
  }

  .metric-label {
    @apply text-sm font-medium text-muted-foreground;
  }
}
```

### Implementation Files

| File | Change |
|------|--------|
| `apps/web/app/globals.css` | Add `.tabular-nums`, `.metric-value` utilities |
| `apps/web/components/stats-card.tsx` | Apply `metric-value` class to value |
| `apps/web/components/session-card.tsx` | Apply `tabular-nums` to counts |
| `apps/web/components/metric-badge.tsx` | Apply `tabular-nums` to badge values |

### Visual Result

Before:
```
Sessions: 11
Sessions: 450
Sessions: 1326
```

After (aligned):
```
Sessions:   11
Sessions:  450
Sessions: 1326
```

---

## Issue 3: Stats Card Missing Description

### Current State

```typescript
// Home view observation
| Card | Title | Description |
| 3 | Total Sessions | (none) |  // Missing!
```

### Improvement

Ensure all StatsCards have meaningful descriptions:

```typescript
// apps/web/app/page.tsx
<StatsCard
  title="Total Sessions"
  value={totalSessions}
  description={`Across ${gitRepoCount + otherProjectCount} projects`}  // Add this
  icon={LayersIcon}
/>
```

### All Stats Card Descriptions

| Location | Card | Description Template |
|----------|------|----------------------|
| Home | Git Repositories | `"{n} projects across {m} repos"` |
| Home | Non-Git Projects | `"Projects without git"` |
| Home | Total Sessions | `"Across {n} projects"` |
| Home | Total Agents | `"Standalone agents across projects"` |
| Project Overview | Sessions | `"In this project"` |
| Project Overview | Duration | `"Total time spent"` |
| Session Overview | Messages | `"User + assistant messages"` |
| Session Overview | Duration | `"Last activity: {timestamp}"` |

---

## Issue 4: Primary Color Contrast

### Current State

Purple primary color (`262 83% 58%` light / `263 70% 50%` dark) may have accessibility issues on certain backgrounds.

### Improvement

Validate and adjust for WCAG AA compliance (4.5:1 contrast ratio):

```css
/* globals.css */
:root {
  --primary: 262 83% 58%;
  --primary-foreground: 0 0% 100%;  /* Pure white for better contrast */
}

.dark {
  --primary: 265 70% 60%;           /* Slightly lighter for dark mode */
  --primary-foreground: 0 0% 100%;
}
```

### Verification

Use Chrome DevTools contrast checker or [WebAIM Contrast Checker](https://webaim.org/resources/contrastchecker/).

---

## Issue 5: Border Radius Inconsistency

### Current State

```css
--radius: 0.5rem;  /* 8px base */
```

Various components may use inconsistent border radius values.

### Improvement

Establish a radius scale and apply consistently:

```css
/* globals.css */
:root {
  --radius-sm: 0.25rem;   /* 4px - small elements, badges */
  --radius: 0.5rem;       /* 8px - cards, buttons */
  --radius-lg: 0.75rem;   /* 12px - modals, large cards */
  --radius-xl: 1rem;      /* 16px - hero sections */
}
```

### Component Mapping

| Component | Radius |
|-----------|--------|
| Badge, Pill | `--radius-sm` |
| Card, Button | `--radius` |
| Modal, Sheet | `--radius-lg` |
| Stats card on home | `--radius` |

---

## Implementation Checklist

### globals.css Changes

```css
@layer base {
  :root {
    /* Existing variables... */

    /* New: Surface elevation */
    --surface-1: 220 14% 98%;
    --surface-2: 220 14% 96%;
    --surface-3: 220 14% 93%;

    /* New: Radius scale */
    --radius-sm: 0.25rem;
    --radius-lg: 0.75rem;
    --radius-xl: 1rem;
  }

  .dark {
    /* Updated: Separated background and surfaces */
    --background: 225 71% 3%;
    --surface-1: 224 71% 5%;
    --surface-2: 224 68% 8%;
    --surface-3: 224 65% 12%;
    --card: 224 71% 5%;  /* Explicit, not identical to background */

    /* Updated: Better primary contrast */
    --primary: 265 70% 60%;
  }
}

@layer utilities {
  .tabular-nums {
    font-variant-numeric: tabular-nums;
    font-feature-settings: 'tnum' 1;
  }

  .metric-value {
    @apply tabular-nums font-mono text-2xl font-semibold tracking-tight;
  }
}
```

---

## Verification Steps

1. **Visual Inspection**: Open the dashboard in dark mode, verify cards are visually distinct from background
2. **Typography Check**: Verify numbers align properly in stats grids
3. **Contrast Check**: Run Lighthouse accessibility audit, target score >= 90
4. **Responsive Check**: Test on mobile, tablet, desktop breakpoints

---

## Dependencies

None - this is a foundational phase.

---

## Next Phase

Phase 2: Data Sanitization & Display - addresses the XML tag and edge case issues visible in session cards and timeline.
