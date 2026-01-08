# Phase 7: Projects & History Polish

**Scope**: Project cards with sparklines, chart improvements, inline summary stats, date range presets.

**Files**: `public/app.js`, `public/charts.js`, `public/style.css`

**Effort**: Medium | **Impact**: Medium

---

## Overview

Enhance the Projects and History views with sparklines for trend visualization, improved chart interactions, and streamlined date range controls.

---

## 7.1 Project Cards with Sparklines

### Current

```
┌───────────────────────────────────────────────────────┐
│ karma                                        $6.0843  │
│ 54 sessions   786.1K tokens   3 days                  │
│ Last: 6h ago                                          │
└───────────────────────────────────────────────────────┘
```

### Proposed

```
┌───────────────────────────────────────────────────────┐
│ karma                         ▂▃▄▅▇█▅▃      $6.0843  │
│ 54 sessions · 786K tokens · 3d active                 │
│ Last: 6h                                        →     │
└───────────────────────────────────────────────────────┘
```

### HTML

```html
<article class="project-card" tabindex="0" data-project="karma">
  <div class="project-card__header">
    <span class="project-card__name">karma</span>
    <canvas class="project-card__sparkline" width="80" height="24"></canvas>
    <span class="project-card__cost">$6.0843</span>
  </div>
  <div class="project-card__meta">
    54 sessions · 786K tokens · 3d active
  </div>
  <div class="project-card__footer">
    <span class="project-card__last">Last: 6h</span>
    <span class="project-card__arrow">→</span>
  </div>
</article>
```

### CSS

```css
.project-card {
  background: var(--bg-card);
  border: 1px solid var(--border-color);
  border-left: 3px solid transparent;
  border-radius: 6px;
  padding: 0.875rem 1rem;
  cursor: pointer;
  transition: all 150ms ease-out;
}

.project-card__header {
  display: flex;
  align-items: center;
  gap: 0.75rem;
}

.project-card__name {
  font-size: 1rem;
  font-weight: 600;
  color: var(--text-primary);
}

.project-card__sparkline {
  flex: 1;
  height: 24px;
  max-width: 80px;
}

.project-card__cost {
  font-family: var(--font-mono);
  font-size: 1rem;
  font-weight: 600;
  color: var(--primary);
}

.project-card__meta {
  font-size: 0.8125rem;
  color: var(--text-secondary);
  margin-top: 0.375rem;
}

.project-card__footer {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-top: 0.5rem;
}

.project-card__last {
  font-size: 0.75rem;
  color: var(--text-muted);
}

.project-card__arrow {
  font-size: 1rem;
  color: var(--text-muted);
  opacity: 0;
  transform: translateX(-4px);
  transition: all 150ms ease-out;
}

.project-card:hover .project-card__arrow {
  opacity: 1;
  transform: translateX(0);
}
```

---

## 7.2 Grid/List Toggle

```html
<div class="view-toggle">
  <button class="view-toggle__btn is-active" data-view="list" title="List view">
    ≡
  </button>
  <button class="view-toggle__btn" data-view="grid" title="Grid view">
    ⊞
  </button>
</div>
```

### Grid View CSS

```css
.projects-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(180px, 1fr));
  gap: 1rem;
}

.projects-grid .project-card {
  flex-direction: column;
  align-items: flex-start;
}

.projects-grid .project-card__sparkline {
  display: none; /* Hide in grid view */
}

.projects-grid .project-card__cost {
  font-size: 1.5rem;
  margin-top: 0.5rem;
}
```

---

## 7.3 History Chart Improvements

### Legend Repositioning

Move legend inline with controls:

```html
<div class="chart-controls">
  <select class="chart-filter" id="project-filter">
    <option value="">All Projects</option>
    <option value="karma">karma</option>
  </select>
  
  <div class="chart-range">
    <button class="range-btn" data-days="7">7d</button>
    <button class="range-btn is-active" data-days="30">30d</button>
    <button class="range-btn" data-days="90">90d</button>
  </div>
  
  <div class="chart-legend">
    <span class="legend-item legend-item--bars">■ Daily</span>
    <span class="legend-item legend-item--line">▲ Cumulative</span>
  </div>
</div>
```

### Hover Tooltip

```javascript
// Add to HistoryChart class
setupTooltip() {
  const tooltip = document.createElement('div');
  tooltip.className = 'chart-tooltip';
  tooltip.style.display = 'none';
  this.container.appendChild(tooltip);
  this.tooltip = tooltip;
  
  this.uplot.root.addEventListener('mousemove', (e) => {
    const idx = this.uplot.cursor.idx;
    if (idx !== null && idx !== undefined) {
      const data = this.getData(idx);
      this.showTooltip(e, data);
    } else {
      this.hideTooltip();
    }
  });
  
  this.uplot.root.addEventListener('mouseleave', () => {
    this.hideTooltip();
  });
}

showTooltip(e, data) {
  const { date, cost, sessions } = data;
  this.tooltip.innerHTML = `
    <strong>${this.formatDate(date)}</strong><br>
    $${cost.toFixed(2)} · ${sessions} sessions
  `;
  this.tooltip.style.display = 'block';
  this.tooltip.style.left = `${e.pageX + 10}px`;
  this.tooltip.style.top = `${e.pageY - 30}px`;
}

hideTooltip() {
  this.tooltip.style.display = 'none';
}
```

### Tooltip CSS

```css
.chart-tooltip {
  position: absolute;
  background: var(--bg-dark);
  border: 1px solid var(--border-color);
  padding: 0.5rem 0.75rem;
  border-radius: 4px;
  font-size: 0.8125rem;
  color: var(--text-primary);
  pointer-events: none;
  z-index: 100;
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.3);
}

.chart-tooltip strong {
  color: var(--text-primary);
}
```

---

## 7.4 Y-Axis Auto-Scaling Fix

```javascript
// Fix Y-axis to match actual data range
function calculateYAxisRange(values) {
  const max = Math.max(...values);
  const min = Math.min(...values, 0);
  
  // Add 10% padding
  const range = max - min;
  const padding = range * 0.1;
  
  return {
    min: Math.floor(min),
    max: Math.ceil(max + padding)
  };
}

// Apply to uPlot options
const opts = {
  scales: {
    y: {
      range: (u, dataMin, dataMax) => {
        const { min, max } = calculateYAxisRange([dataMin, dataMax]);
        return [min, max];
      }
    }
  }
};
```

---

## 7.5 Inline Summary Stats

Replace summary cards with inline stats bar:

```html
<div class="history-summary">
  <span class="summary-stat">
    <span class="summary-stat__label">Total:</span>
    <span class="summary-stat__value">$52.48</span>
  </span>
  <span class="summary-stat">
    <span class="summary-stat__label">Sessions:</span>
    <span class="summary-stat__value">335</span>
  </span>
  <span class="summary-stat">
    <span class="summary-stat__label">Avg/day:</span>
    <span class="summary-stat__value">$3.50</span>
  </span>
  <span class="summary-stat summary-stat--highlight">
    <span class="summary-stat__label">Peak:</span>
    <span class="summary-stat__value">$9.80 (Jan 4)</span>
  </span>
</div>
```

```css
.history-summary {
  display: flex;
  flex-wrap: wrap;
  gap: 1.5rem;
  padding: 0.75rem 0;
  border-top: 1px solid var(--border-color);
  font-size: 0.875rem;
}

.summary-stat {
  display: flex;
  gap: 0.375rem;
}

.summary-stat__label {
  color: var(--text-muted);
}

.summary-stat__value {
  font-family: var(--font-mono);
  color: var(--text-primary);
  font-weight: 500;
}

.summary-stat--highlight .summary-stat__value {
  color: var(--primary);
}
```

---

## 7.6 Quick Date Range Presets

```javascript
const DATE_PRESETS = [
  { label: 'Today', days: 1 },
  { label: 'Yesterday', days: 1, offset: 1 },
  { label: 'This week', days: 7 },
  { label: 'Last week', days: 7, offset: 7 },
  { label: 'This month', days: 30 },
  { label: 'Last month', days: 30, offset: 30 },
  { label: 'This quarter', days: 90 },
  { label: 'Year to date', days: 'ytd' }
];

function applyDatePreset(preset) {
  const now = new Date();
  let startDate, endDate;
  
  if (preset.days === 'ytd') {
    startDate = new Date(now.getFullYear(), 0, 1);
    endDate = now;
  } else {
    endDate = new Date(now);
    if (preset.offset) {
      endDate.setDate(endDate.getDate() - preset.offset);
    }
    startDate = new Date(endDate);
    startDate.setDate(startDate.getDate() - preset.days);
  }
  
  return { startDate, endDate };
}
```

---

## 7.7 Compact Metadata Formatting

```javascript
function formatProjectMeta(project) {
  const parts = [
    `${project.sessionCount} sessions`,
    formatTokens(project.totalTokens) + ' tokens',
    `${project.activeDays}d active`
  ];
  return parts.join(' · ');
}

function formatLastActivity(date) {
  const diff = Date.now() - new Date(date).getTime();
  const hours = Math.floor(diff / (1000 * 60 * 60));
  
  if (hours < 1) return 'Just now';
  if (hours < 24) return `${hours}h`;
  const days = Math.floor(hours / 24);
  if (days < 7) return `${days}d`;
  return `${Math.floor(days / 7)}w`;
}
```

---

## Acceptance Criteria

- [ ] Project cards display sparklines (7-day cost trend)
- [ ] Grid/list toggle switches view layout
- [ ] Chart tooltip shows date, cost, sessions on hover
- [ ] Y-axis scales correctly to data range
- [ ] Inline summary replaces summary cards
- [ ] Date presets (7d, 30d, 90d) work correctly
- [ ] Metadata is compact with bullet separators
- [ ] Arrow indicator appears on project card hover

---

## Dependencies

- Phase 4 (Sparklines & Trends - sparkline component)

---

## Testing Checklist

- [ ] Sparklines render for each project
- [ ] Grid view shows compact cards
- [ ] List view shows full details
- [ ] Chart tooltip follows cursor
- [ ] Y-axis matches actual data
- [ ] Date range buttons update chart
- [ ] Project click navigates correctly
- [ ] Summary stats are accurate
