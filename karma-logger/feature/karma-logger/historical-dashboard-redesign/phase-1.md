# Phase 1: Layout Foundation

**Scope**: Compact header, denser metric cards, updated color system, typography scale.

**Files**: `public/style.css`, `public/index.html`

**Effort**: Low | **Impact**: High

---

## Overview

Phase 1 establishes the foundational layout changes that all subsequent phases build upon. Focus is on maximizing information density while maintaining readability.

---

## 1.1 Compact Single-Line Header

### Current (2 rows)
```
┌──────────────────────────────────────────────────────────────┐
│ Karma Dashboard    Session: 61288b4c...           ● CONNECTED │
├──────────────────────────────────────────────────────────────┤
│ Live           Projects           History                    │
└──────────────────────────────────────────────────────────────┘
```

### Proposed (1 row)
```
┌──────────────────────────────────────────────────────────────┐
│ ◈ Karma           61288b4c    Live   Projects   History    ● │
└──────────────────────────────────────────────────────────────┘
```

### HTML Changes

```html
<!-- Current -->
<header>
  <h1>Karma Dashboard</h1>
  <span class="session-id">Session: 61288b4c...</span>
  <span class="status">● CONNECTED</span>
</header>
<nav>
  <button>Live</button>
  <button>Projects</button>
  <button>History</button>
</nav>

<!-- Proposed -->
<header class="header--compact">
  <div class="header__brand">
    <span class="header__logo">◈</span>
    <span class="header__title">Karma</span>
  </div>
  <span class="header__session">61288b4c</span>
  <nav class="header__nav">
    <button class="nav-tab" data-view="live">Live</button>
    <button class="nav-tab" data-view="projects">Projects</button>
    <button class="nav-tab" data-view="history">History</button>
  </nav>
  <span class="header__status" title="Connected">●</span>
</header>
```

### CSS Changes

```css
.header--compact {
  display: flex;
  align-items: center;
  gap: 1rem;
  padding: 0.5rem 1rem;
  background: var(--bg-card);
  border-bottom: 1px solid var(--border-color);
  height: 48px;
}

.header__brand {
  display: flex;
  align-items: center;
  gap: 0.5rem;
}

.header__logo {
  font-size: 1.25rem;
  color: var(--primary);
}

.header__title {
  font-size: 1rem;
  font-weight: 600;
  color: var(--text-primary);
}

.header__session {
  font-family: var(--font-mono);
  font-size: 0.75rem;
  color: var(--text-muted);
}

.header__nav {
  display: flex;
  gap: 0.25rem;
  margin-left: auto;
}

.nav-tab {
  padding: 0.375rem 0.75rem;
  font-size: 0.8125rem;
  background: transparent;
  border: none;
  color: var(--text-secondary);
  cursor: pointer;
  border-radius: 4px;
}

.nav-tab.is-active {
  color: var(--primary);
  background: rgba(16, 185, 129, 0.1);
}

.header__status {
  font-size: 0.75rem;
  color: var(--primary);
}
```

---

## 1.2 Denser 4-Column Metric Cards

### Current (3 large cards, ~150px height)

```
┌─────────────────┐ ┌─────────────────┐ ┌─────────────────┐
│                 │ │                 │ │                 │
│     21,234      │ │      1,892      │ │    $0.2009      │
│   tokens in     │ │   tokens out    │ │   session cost  │
│                 │ │                 │ │                 │
└─────────────────┘ └─────────────────┘ └─────────────────┘
```

### Proposed (4 compact cards, ~80px height)

```
┌─────────────┬─────────────┬─────────────┬─────────────┐
│ ▲ 21.2K     │ ▼ 1.8K      │ $ 0.2009    │ ⚡ 45        │
│ tokens in   │ tokens out  │ session     │ agents      │
└─────────────┴─────────────┴─────────────┴─────────────┘
```

### HTML Structure

```html
<div class="metrics-grid metrics-grid--4col">
  <article class="metric-card metric-card--compact">
    <div class="metric-card__header">
      <span class="metric-card__icon">▲</span>
      <span class="metric-card__value">21.2K</span>
    </div>
    <div class="metric-card__label">tokens in</div>
    <!-- Phase 4 will add sparkline here -->
  </article>
  
  <article class="metric-card metric-card--compact">
    <div class="metric-card__header">
      <span class="metric-card__icon">▼</span>
      <span class="metric-card__value">1.8K</span>
    </div>
    <div class="metric-card__label">tokens out</div>
  </article>
  
  <article class="metric-card metric-card--compact">
    <div class="metric-card__header">
      <span class="metric-card__icon">$</span>
      <span class="metric-card__value">0.2009</span>
    </div>
    <div class="metric-card__label">session</div>
  </article>
  
  <article class="metric-card metric-card--compact">
    <div class="metric-card__header">
      <span class="metric-card__icon">⚡</span>
      <span class="metric-card__value">45</span>
    </div>
    <div class="metric-card__label">agents</div>
  </article>
</div>
```

### CSS Changes

```css
.metrics-grid--4col {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 0.75rem;
}

.metric-card--compact {
  padding: 0.75rem;
  min-height: auto;
  background: var(--bg-card);
  border: 1px solid var(--border-color);
  border-radius: 6px;
}

.metric-card__header {
  display: flex;
  align-items: baseline;
  gap: 0.375rem;
}

.metric-card__icon {
  font-size: 0.875rem;
  color: var(--text-muted);
}

.metric-card__value {
  font-family: var(--font-mono);
  font-size: 1.5rem;
  font-weight: 700;
  color: var(--text-primary);
}

.metric-card__label {
  font-size: 0.75rem;
  color: var(--text-secondary);
  margin-top: 0.25rem;
}
```

---

## 1.3 Color System Variables

Add to CSS root:

```css
:root {
  /* Existing */
  --primary: #10b981;
  --secondary: #6366f1;
  --accent: #f59e0b;
  --bg-dark: #0f172a;
  --bg-card: #1e293b;
  --bg-hover: #334155;
  --border-color: #334155;
  --text-primary: #f1f5f9;
  --text-secondary: #94a3b8;
  --text-muted: #64748b;
  
  /* New: Model Colors */
  --color-opus: #7c3aed;
  --color-sonnet: #3b82f6;
  --color-haiku: #10b981;
  
  /* New: Trend Colors */
  --color-trend-up: #22c55e;
  --color-trend-down: #ef4444;
  
  /* New: State Colors */
  --color-skeleton: #334155;
  --color-error: #ef4444;
  --color-warning: #f59e0b;
  --color-info: #3b82f6;
  
  /* New: Fonts */
  --font-sans: system-ui, -apple-system, sans-serif;
  --font-mono: 'Monaco', 'Menlo', 'Consolas', monospace;
}
```

---

## 1.4 Typography Scale

```css
/* Page Title */
.title-page {
  font-size: 1.25rem;
  font-weight: 600;
}

/* Section Header */
.title-section {
  font-size: 1rem;
  font-weight: 600;
}

/* Card Value (metrics) */
.text-value {
  font-family: var(--font-mono);
  font-size: 1.75rem;
  font-weight: 700;
}

/* Card Value Compact */
.text-value--compact {
  font-size: 1.5rem;
}

/* Card Label */
.text-label {
  font-size: 0.75rem;
  font-weight: 400;
}

/* Table Header */
.text-th {
  font-size: 0.6875rem;
  font-weight: 500;
  text-transform: uppercase;
  letter-spacing: 0.05em;
}

/* Table Cell */
.text-td {
  font-size: 0.8125rem;
  font-weight: 400;
}

/* Code/ID */
.text-code {
  font-family: var(--font-mono);
  font-size: 0.8125rem;
  font-weight: 400;
}
```

---

## Acceptance Criteria

- [ ] Header collapses to single row with inline navigation
- [ ] Metric cards display 4 columns on desktop
- [ ] All new CSS variables are defined in `:root`
- [ ] Typography scale classes are available
- [ ] Session ID truncates to 8 characters
- [ ] Connection status shows as minimal dot with tooltip
- [ ] No visual regressions in existing functionality

---

## Dependencies

None (foundation for all other phases)

---

## Testing Checklist

- [ ] Header renders correctly at 1024px+ width
- [ ] Metric cards display 4 columns
- [ ] Tab switching still works
- [ ] Connection status reflects SSE state
- [ ] Dark theme colors are consistent
