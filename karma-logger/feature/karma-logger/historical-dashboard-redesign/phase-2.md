# Phase 2: Interaction States

**Scope**: Hover, focus, active, and disabled states for all interactive elements.

**Files**: `public/style.css`

**Effort**: Low | **Impact**: High

---

## Overview

Every interactive element must define all four states. Consistency across components builds muscle memory and improves accessibility.

---

## State Definitions

| State | Trigger | Visual Change | Duration |
|-------|---------|---------------|----------|
| **Default** | Page load | Base styling | - |
| **Hover** | Mouse enter | Lighten bg, show affordance | 0ms in, 150ms out |
| **Focus** | Tab/click | Ring outline, high contrast | Immediate |
| **Active** | Mouse down | Darken bg, slight scale | 50ms |
| **Disabled** | Logic-based | 50% opacity, no cursor | - |

---

## 2.1 Metric Card States

```css
/* Default */
.metric-card {
  background: var(--bg-card);
  border: 1px solid var(--border-color);
  transform: translateY(0);
  cursor: default;
  transition: all 150ms ease-out;
}

/* Hover - subtle lift */
.metric-card:hover {
  background: var(--bg-hover);
  border-color: var(--text-muted);
  transform: translateY(-2px);
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.3);
}

/* Focus - keyboard navigation */
.metric-card:focus-visible {
  outline: 2px solid var(--primary);
  outline-offset: 2px;
  background: var(--bg-hover);
}

/* Active - click feedback */
.metric-card:active {
  transform: translateY(0);
  background: var(--bg-dark);
}
```

---

## 2.2 Button States

```css
/* Default */
.btn {
  padding: 0.375rem 0.75rem;
  background: transparent;
  border: 1px solid var(--border-color);
  color: var(--text-secondary);
  border-radius: 4px;
  cursor: pointer;
  transition: all 150ms ease-out;
}

/* Hover */
.btn:hover {
  background: var(--bg-hover);
  border-color: var(--text-muted);
  color: var(--text-primary);
}

/* Focus */
.btn:focus-visible {
  outline: none;
  box-shadow: 0 0 0 2px var(--bg-dark), 0 0 0 4px var(--primary);
}

/* Active */
.btn:active {
  background: var(--bg-dark);
  border-color: var(--primary);
  color: var(--primary);
}

/* Disabled */
.btn:disabled,
.btn[disabled] {
  opacity: 0.5;
  cursor: not-allowed;
  pointer-events: none;
}

/* Primary variant */
.btn--primary {
  background: var(--primary);
  border-color: var(--primary);
  color: var(--bg-dark);
}

.btn--primary:hover {
  background: #0ea572;
  border-color: #0ea572;
}
```

---

## 2.3 Project Card States

```css
/* Default */
.project-card {
  background: var(--bg-card);
  border: 1px solid var(--border-color);
  border-left: 3px solid transparent;
  border-radius: 6px;
  padding: 1rem;
  cursor: pointer;
  transform: translateX(0);
  transition: all 150ms ease-out;
}

/* Hover - slide right + accent border */
.project-card:hover {
  border-left-color: var(--primary);
  transform: translateX(4px);
  background: var(--bg-hover);
}

/* Focus - keyboard users */
.project-card:focus-visible {
  outline: none;
  border-left-color: var(--primary);
  box-shadow: inset 0 0 0 2px var(--primary);
}

/* Selected - when viewing project details */
.project-card.is-selected {
  background: rgba(16, 185, 129, 0.1);
  border-left-color: var(--primary);
}

/* Active */
.project-card:active {
  transform: translateX(2px);
  background: var(--bg-dark);
}
```

---

## 2.4 Tab States

```css
/* Default */
.nav-tab {
  padding: 0.375rem 0.75rem;
  background: transparent;
  border: none;
  border-bottom: 2px solid transparent;
  color: var(--text-muted);
  cursor: pointer;
  transition: all 150ms ease-out;
}

/* Hover */
.nav-tab:hover {
  color: var(--text-secondary);
}

/* Focus */
.nav-tab:focus-visible {
  outline: 1px dotted var(--primary);
  outline-offset: 2px;
}

/* Active (selected) */
.nav-tab.is-active {
  border-bottom-color: var(--primary);
  color: var(--primary);
}
```

---

## 2.5 Agent Tree Node States

```css
/* Default */
.agent-node {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  padding: 0.25rem 0.5rem;
  background: transparent;
  border-radius: 4px;
  cursor: default;
  transition: background 100ms ease-out;
}

/* Hover - highlight row */
.agent-node:hover {
  background: var(--bg-hover);
}

/* Focus - keyboard navigation through tree */
.agent-node:focus-visible {
  outline: 1px solid var(--primary);
  outline-offset: -1px;
}

/* Expanded - visual indicator */
.agent-node.is-expanded > .agent-node__icon {
  transform: rotate(90deg);
  transition: transform 150ms ease-out;
}

/* Running - animated status */
.agent-node.is-running::before {
  content: '';
  width: 6px;
  height: 6px;
  background: var(--primary);
  border-radius: 50%;
  animation: status-pulse 2s infinite;
}

@keyframes status-pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.4; }
}
```

---

## 2.6 Cursor Guidelines

```css
/* Clickable cards - navigates to detail view */
.project-card,
.session-card {
  cursor: pointer;
}

/* Metric cards - informational only */
.metric-card {
  cursor: default;
}

/* Expand buttons - toggle action */
.btn-expand,
.agent-node__toggle {
  cursor: pointer;
}

/* Disabled buttons - blocked action */
.btn:disabled {
  cursor: not-allowed;
}

/* Chart canvas - precision hover */
.chart-container canvas {
  cursor: crosshair;
}

/* Resize handles */
.resize-handle {
  cursor: ew-resize;
}
```

---

## 2.7 Transition Specifications

```css
/* Standard transition mixin */
:root {
  --transition-fast: 100ms ease-out;
  --transition-normal: 150ms ease-out;
  --transition-slow: 250ms ease-out;
}

/* Background color changes */
.transition-bg {
  transition: background-color var(--transition-normal);
}

/* Transform (hover lift) */
.transition-transform {
  transition: transform var(--transition-fast);
}

/* Opacity (fade) */
.transition-opacity {
  transition: opacity 200ms ease-in-out;
}

/* Width/Height (expand) */
.transition-size {
  transition: width var(--transition-slow), height var(--transition-slow);
}

/* All properties */
.transition-all {
  transition: all var(--transition-normal);
}
```

---

## 2.8 Focus Ring Utility

```css
/* Universal focus ring for accessibility */
.focus-ring:focus-visible {
  outline: 2px solid var(--primary);
  outline-offset: 2px;
}

/* Remove default focus styles when using custom */
.focus-ring:focus {
  outline: none;
}

/* High contrast focus for dark backgrounds */
.focus-ring--high-contrast:focus-visible {
  outline-color: var(--text-primary);
}
```

---

## Acceptance Criteria

- [ ] All buttons have hover/focus/active/disabled states
- [ ] All cards have hover/focus states
- [ ] Tab navigation has clear focus ring
- [ ] Agent tree nodes highlight on hover
- [ ] Transitions are 150ms or less for responsiveness
- [ ] Focus is visible for keyboard navigation (WCAG AA)
- [ ] `prefers-reduced-motion` disables animations

---

## Dependencies

- Phase 1 (Layout Foundation - for card structure)

---

## Reduced Motion Support

```css
@media (prefers-reduced-motion: reduce) {
  *,
  *::before,
  *::after {
    animation-duration: 0.01ms !important;
    animation-iteration-count: 1 !important;
    transition-duration: 0.01ms !important;
  }
}
```

---

## Testing Checklist

- [ ] Tab through all interactive elements
- [ ] Verify focus ring visibility
- [ ] Test with keyboard only (no mouse)
- [ ] Verify disabled state blocks interaction
- [ ] Test hover states with mouse
- [ ] Check transitions are smooth
- [ ] Test with `prefers-reduced-motion` enabled
