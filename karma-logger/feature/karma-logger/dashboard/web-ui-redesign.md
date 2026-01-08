# Karma Dashboard - Web UI Redesign

**Version:** 1.1  
**Date:** 2026-01-08  
**Status:** Design Phase  
**Last Updated:** Added interaction states, error states, celebrations, power user features

---

## Executive Summary

This document outlines the design philosophy and UI refinement strategy for the Karma Dashboard web interface. Based on analysis of the current implementation and screenshots, we propose a series of improvements that maintain the dashboard's core identity while enhancing usability, information density, and visual polish.

---

## Current State Analysis

### Screenshots Reviewed

| View | Screenshot | Status |
|------|------------|--------|
| Live | `live-view.png` | Functional, needs density |
| Projects | `projects-view.png` | Clean, clickable cards |
| History (30d) | `history-view.png` | Good chart, needs polish |
| History (7d) | `history-7d.png` | Dynamic scaling works |
| Filtered | `history-karma-7d.png` | Project filter works |

### Current Strengths

1. **Dark Theme Execution** - Slate/navy palette is professional and reduces eye strain
2. **Connected Status Indicator** - Real-time SSE state is clearly visible
3. **Monospace Typography** - Session IDs and costs use monospace fonts correctly
4. **Chart Clarity** - History chart with dual-axis (bars + cumulative line) is readable
5. **Card-Based Layout** - Metrics cards and project cards have good visual hierarchy

### Current Weaknesses

1. **Empty State Design** - "Waiting for data..." lacks visual interest
2. **Metric Cards Too Large** - 3 cards take too much vertical space
3. **Agent Tree Collapsed** - No visual preview of hierarchy depth
4. **Tab Bar Asymmetric** - Live/Projects/History positioning is unbalanced
5. **No Sparklines in Cards** - Static numbers miss trend context
6. **Footer Waste** - "Karma Logger - Real-time Claude Code metrics" adds no value
7. **Chart Legend Position** - Legend should be inline or below, not overlapping data

---

## Design Philosophy

### 1. Data Density Over Decoration

**Principle:** Every pixel should earn its space with meaningful information.

```
BAD:  Large empty metric cards with only a number
GOOD: Compact cards with number + sparkline + trend indicator
```

The dashboard serves developers who want quick insights. Minimize padding and maximize signal-to-noise ratio.

### 2. Glanceability

**Principle:** Key metrics should be readable in <2 seconds without scrolling.

**Target Metrics for Above-the-Fold:**
- Current session cost (live view)
- Today's total cost
- Active project count
- Session count (7d)

### 3. Progressive Disclosure

**Principle:** Summary first, details on demand.

```
Level 1: Dashboard header (cost, sessions, status)
Level 2: View-specific content (live/projects/history)
Level 3: Drill-down (click project → sessions → agents)
```

### 4. Terminal Aesthetic

**Principle:** Honor the developer tool heritage while remaining accessible.

- Use monospace fonts for data, sans-serif for labels
- Prefer line/bar charts over pie charts
- Tree structures should feel like `ls --tree`
- Status indicators should mimic CI/CD pipelines

### 5. Motion with Purpose

**Principle:** Animation should convey state, not entertain.

```
USE: Pulse animation on "Connected" status
USE: Fade transitions between views
AVOID: Bouncing, sliding, or attention-seeking motion
```

---

## Proposed Changes

### Phase 1: Layout Refinement

#### 1.1 Compact Header

**Current:**
```
┌──────────────────────────────────────────────────────────────┐
│ Karma Dashboard    Session: 61288b4c...           ● CONNECTED │
├──────────────────────────────────────────────────────────────┤
│ Live           Projects           History                    │
└──────────────────────────────────────────────────────────────┘
```

**Proposed:**
```
┌──────────────────────────────────────────────────────────────┐
│ ◈ Karma           61288b4c    Live   Projects   History    ● │
└──────────────────────────────────────────────────────────────┘
```

Changes:
- Single-line header (reduce from 2 rows to 1)
- Logo icon instead of full title
- Tabs inline with header
- Connection status as minimal dot with tooltip

#### 1.2 Denser Metric Cards

**Current:** 3 large cards (~150px height each)

**Proposed:** 4 compact cards in a row (~80px height)

```
┌─────────────┬─────────────┬─────────────┬─────────────┐
│ ▲ 21.2K     │ ▼ 1.8K      │ $ 0.2009    │ ⚡ 45        │
│ tokens in   │ tokens out  │ session     │ agents      │
│ ▁▂▃▄▅▆▇ +8% │ ▁▁▂▂▃▄▅ +2% │ ▂▃▄▅▆▇▇ 12% │ ▄▄▃▃▂▁▁ -4% │
└─────────────┴─────────────┴─────────────┴─────────────┘
```

Features:
- Add 4th card for agent count
- Include mini sparkline (last 10 data points)
- Add trend indicator (+/- % vs previous session)
- Reduce vertical padding

#### 1.3 Agent Tree Visual Improvements

**Current:**
```
Agent Hierarchy                          [Expand All]
└── (empty or flat list)
```

**Proposed:**
```
Agents                                     2/8 expanded
├── ◈ opus  main              $26.10  1.2M  
│   ├── ◇ opus  general-purpose   $11.62  450K
│   ├── ◇ opus  general-purpose   $5.18   200K
│   └── ◇ haiku Explore           $0.71   12K
└── ◇ sonnet unknown            $0.09   5K
```

Changes:
- ASCII tree connectors (`├──`, `└──`, `│`)
- Filled/outline icons to show expanded state
- Model badges as minimal colored text
- Cost and tokens right-aligned
- Expansion counter instead of toggle button

### Phase 2: Projects View Enhancement

#### 2.1 Project Cards with Sparklines

**Current:**
```
┌───────────────────────────────────────────────────────┐
│ karma                                        $6.0843  │
│ 54 sessions   786.1K tokens   3 days                  │
│ Last: 6h ago                                          │
└───────────────────────────────────────────────────────┘
```

**Proposed:**
```
┌───────────────────────────────────────────────────────┐
│ karma                         ▂▃▄▅▇█▅▃      $6.0843  │
│ 54 sessions · 786K tokens · 3d active                 │
│ Last: 6h                                        →     │
└───────────────────────────────────────────────────────┘
```

Changes:
- Add cost trend sparkline
- Compact metadata with bullet separators
- Arrow indicator for clickable navigation
- Abbreviated time display

#### 2.2 Project Grid vs List Toggle

For users with many projects, offer a grid view:

```
[≡ List] [⊞ Grid]

┌────────────┐ ┌────────────┐ ┌────────────┐
│   karma    │ │   root     │ │    go      │
│  $6.08     │ │  $18.66    │ │   $0.37    │
│  54 sess   │ │  96 sess   │ │   5 sess   │
└────────────┘ └────────────┘ └────────────┘
```

### Phase 3: History View Polish

#### 3.1 Chart Improvements

**Current Issues:**
- Y-axis shows $1000.00 scale for $10 data (history-view.png shows mismatch)
- Legend overlaps chart area
- No data point tooltips

**Proposed:**
```
Cost History                      karma ▾    7d [30d] 90d
┌──────────────────────────────────────────────────────┐
│  ██████████████                         ▲ Cumulative │
│  ██    ██  ██  ████    ██  ██████████   ■ Daily      │
│  ██    ██  ██  ████    ██  ██  ██  ██                │
│──██────██──██──████────██──██──██──██───────────────│
│  1/1   1/2 1/3  1/4    1/5 1/6  1/7                  │
└──────────────────────────────────────────────────────┘
                          Hover: Jan 7 · $4.23 · 12 sessions
```

Changes:
- Move legend to top-right, inline with controls
- Add hover tooltip with date/cost/sessions
- Fix Y-axis auto-scaling to match actual data range
- Reduce bar gap for denser visualization

#### 3.2 Summary Cards Refinement

**Current:** 3 large cards below chart

**Proposed:** Inline stats bar

```
Total: $52.48 · 335 sessions · $3.50/day avg · peak: $9.80 (Jan 4)
```

### Phase 4: Empty States & Loading

#### 4.1 Meaningful Empty States

**Current:** "Waiting for data..." / "No agents spawned yet"

**Proposed:**

```
┌─────────────────────────────────────────┐
│                                         │
│         ◇ No agents yet                 │
│                                         │
│   Run a Claude Code session to see      │
│   real-time agent hierarchy here.       │
│                                         │
│   ─────────────────────────────────     │
│   Tip: Use 'karma watch' in terminal    │
│   for live session monitoring.          │
│                                         │
└─────────────────────────────────────────┘
```

Features:
- Icon + heading
- Brief explanation
- Actionable tip
- No "..."  (ellipsis implies something is happening)

#### 4.2 Skeleton Loading

Replace static "Loading..." with skeleton cards:

```
┌─────────────┬─────────────┬─────────────┐
│ ░░░░░░░     │ ░░░░░       │ ░░░░░░░░    │
│ tokens in   │ tokens out  │ cost        │
└─────────────┴─────────────┴─────────────┘
```

---

## Color System

### Current Palette

| Name | Hex | Usage |
|------|-----|-------|
| Primary | `#10b981` | Costs, success states |
| Secondary | `#6366f1` | Session IDs, links |
| Accent | `#f59e0b` | Agent costs, warnings |
| BG Dark | `#0f172a` | Page background |
| BG Card | `#1e293b` | Card surfaces |
| Text Primary | `#f1f5f9` | Main text |
| Text Secondary | `#94a3b8` | Labels |
| Text Muted | `#64748b` | Hints |

### Proposed Additions

| Name | Hex | Usage |
|------|-----|-------|
| Opus Purple | `#7c3aed` | Opus model badge |
| Sonnet Blue | `#3b82f6` | Sonnet model badge |
| Haiku Green | `#10b981` | Haiku model badge |
| Trend Up | `#22c55e` | Positive change |
| Trend Down | `#ef4444` | Negative change |
| Skeleton | `#334155` | Loading placeholders |

---

## Typography Scale

### Current
- Headers: System font, 1.125rem-1.5rem
- Body: System font, 0.875rem
- Monospace: Monaco/Menlo for IDs and costs

### Proposed Refinement

| Element | Font | Size | Weight |
|---------|------|------|--------|
| Page Title | System | 1.25rem | 600 |
| Section Header | System | 1rem | 600 |
| Card Value | Monospace | 1.75rem | 700 |
| Card Label | System | 0.75rem | 400 |
| Table Header | System | 0.6875rem | 500 |
| Table Cell | System | 0.8125rem | 400 |
| Code/ID | Monospace | 0.8125rem | 400 |

---

## Component Library

### Proposed Components

#### `<metric-card>`

```html
<article class="metric-card metric-card--compact">
  <div class="metric-card__value">$0.2009</div>
  <div class="metric-card__label">session cost</div>
  <div class="metric-card__sparkline" data-values="[1,2,3,4,5,6,7,8]"></div>
  <div class="metric-card__trend metric-card__trend--up">+12%</div>
</article>
```

#### `<agent-tree-node>`

```html
<div class="agent-node" style="--depth: 1">
  <span class="agent-node__connector">├──</span>
  <span class="agent-node__model agent-node__model--opus">opus</span>
  <span class="agent-node__type">general-purpose</span>
  <span class="agent-node__cost">$11.62</span>
  <span class="agent-node__tokens">450K</span>
</div>
```

#### `<project-card>`

```html
<article class="project-card">
  <div class="project-card__header">
    <span class="project-card__name">karma</span>
    <span class="project-card__sparkline"></span>
    <span class="project-card__cost">$6.08</span>
  </div>
  <div class="project-card__meta">54 sessions · 786K tokens · 3d</div>
  <div class="project-card__footer">
    <span class="project-card__last">6h ago</span>
    <span class="project-card__arrow">→</span>
  </div>
</article>
```

---

## Responsive Behavior

### Breakpoints

| Name | Width | Layout Change |
|------|-------|---------------|
| Mobile | <640px | Stack cards, hide sparklines |
| Tablet | 640-1024px | 2-column cards, condensed header |
| Desktop | >1024px | Full layout as designed |

### Mobile Adaptations

1. **Header:** Collapse to hamburger menu for navigation
2. **Metric Cards:** Stack vertically, show 2 per row
3. **Agent Tree:** Collapse to 2 levels max, expand on tap
4. **History Chart:** Reduce bar count, show 7 days only
5. **Projects:** Full-width cards, hide sparklines

---

## Animation Specifications

### Transitions

| Property | Duration | Easing |
|----------|----------|--------|
| Background color | 150ms | ease-out |
| Transform (hover) | 100ms | ease-out |
| Opacity (fade) | 200ms | ease-in-out |
| Width/Height | 250ms | ease-out |

### Keyframe Animations

```css
/* Connection status pulse */
@keyframes status-pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.4; }
}

/* Chart data point appear */
@keyframes data-appear {
  from { opacity: 0; transform: scale(0.8); }
  to { opacity: 1; transform: scale(1); }
}

/* Skeleton shimmer */
@keyframes skeleton-shimmer {
  from { background-position: -200% 0; }
  to { background-position: 200% 0; }
}
```

---

## Interaction States

### State Definitions

Every interactive element must define all four states. Consistency across components builds muscle memory.

#### State Matrix

| State | Trigger | Visual Change | Duration |
|-------|---------|---------------|----------|
| **Default** | Page load | Base styling | - |
| **Hover** | Mouse enter | Lighten bg, show affordance | 0ms in, 150ms out |
| **Focus** | Tab/click | Ring outline, high contrast | Immediate |
| **Active** | Mouse down | Darken bg, slight scale | 50ms |
| **Disabled** | Logic-based | 50% opacity, no cursor | - |

### Component State Specifications

#### Metric Card States

```css
/* Default */
.metric-card {
  background: var(--bg-card);           /* #1e293b */
  border: 1px solid var(--border-color); /* #334155 */
  transform: translateY(0);
  cursor: default;
}

/* Hover - subtle lift */
.metric-card:hover {
  background: var(--bg-hover);           /* #334155 */
  border-color: var(--text-muted);       /* #64748b */
  transform: translateY(-2px);
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.3);
}

/* Focus - keyboard navigation */
.metric-card:focus-visible {
  outline: 2px solid var(--primary);     /* #10b981 */
  outline-offset: 2px;
  background: var(--bg-hover);
}

/* Active - click feedback */
.metric-card:active {
  transform: translateY(0);
  background: var(--bg-dark);            /* #0f172a */
}
```

#### Button States

```
┌─────────────────────────────────────────────────────────────┐
│  State      │  Background   │  Border       │  Text        │
├─────────────┼───────────────┼───────────────┼──────────────┤
│  Default    │  transparent  │  #334155      │  #94a3b8     │
│  Hover      │  #334155      │  #64748b      │  #f1f5f9     │
│  Focus      │  #334155      │  #10b981 2px  │  #f1f5f9     │
│  Active     │  #1e293b      │  #10b981      │  #10b981     │
│  Disabled   │  transparent  │  #334155 50%  │  #64748b 50% │
└─────────────────────────────────────────────────────────────┘
```

#### Project Card States

```css
/* Default */
.project-card {
  border-left: 3px solid transparent;
  transform: translateX(0);
}

/* Hover - slide right + accent border */
.project-card:hover {
  border-left-color: var(--primary);
  transform: translateX(4px);
  background: var(--bg-hover);
}

/* Focus - for keyboard users */
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
```

#### Agent Tree Node States

```css
/* Default */
.agent-node {
  background: transparent;
  border-radius: 4px;
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
```

#### Tab States

```
Default:    ─────────────  (no underline, muted text)
Hover:      ─────────────  (lighter text, no underline yet)
Focus:      ═════════════  (dotted outline around text)
Active:     ▬▬▬▬▬▬▬▬▬▬▬▬▬  (solid primary underline, primary text)
```

### Cursor Guidelines

| Element | Cursor | Reason |
|---------|--------|--------|
| Clickable cards | `pointer` | Navigates to detail view |
| Metric cards | `default` | Informational only |
| Expand buttons | `pointer` | Toggle action |
| Disabled buttons | `not-allowed` | Blocked action |
| Chart canvas | `crosshair` | Precision hover |
| Resize handles | `ew-resize` | Draggable |

---

## Error States

### Design Principle

Errors should be **informative, actionable, and non-blocking** where possible. The dashboard should degrade gracefully.

### Connection States

#### SSE Disconnected

```
┌──────────────────────────────────────────────────────────────┐
│ ◈ Karma           61288b4c    Live   Projects   History    ○ │
└──────────────────────────────────────────────────────────────┘
                                                          ↑
                                              Hollow dot = disconnected
```

**Banner Treatment:**

```
┌──────────────────────────────────────────────────────────────┐
│ ⚠ Connection lost · Reconnecting...                [Retry]  │
└──────────────────────────────────────────────────────────────┘
```

**States:**
1. **Reconnecting** (auto): Yellow banner, animated spinner, "Reconnecting..."
2. **Retry Available**: Yellow banner, retry button, "Connection lost · Last data: 2m ago"
3. **Offline Mode**: Gray banner, "Offline · Showing cached data"

#### SSE Error Codes

| Code | Message | Action |
|------|---------|--------|
| `ECONNREFUSED` | "Dashboard server not running" | "Run `karma dashboard` to start" |
| `TIMEOUT` | "Server not responding" | Auto-retry with backoff |
| `PARSE_ERROR` | "Invalid server response" | Log to console, continue |

### API Failure States

#### Fetch Errors

```
┌───────────────────────────────────────────────────────────┐
│                                                           │
│           ✕ Failed to load projects                       │
│                                                           │
│   Could not connect to the Karma API.                     │
│   Error: ECONNREFUSED 127.0.0.1:3737                     │
│                                                           │
│            [Retry]    [View Logs]                         │
│                                                           │
└───────────────────────────────────────────────────────────┘
```

**Error Card Styling:**
```css
.error-card {
  background: rgba(239, 68, 68, 0.1);  /* red-500 @ 10% */
  border: 1px solid rgba(239, 68, 68, 0.3);
  border-left: 3px solid var(--error);
}

.error-card__icon {
  color: var(--error);
}

.error-card__message {
  color: var(--text-primary);
  font-weight: 500;
}

.error-card__details {
  font-family: monospace;
  font-size: 0.75rem;
  color: var(--text-muted);
  background: var(--bg-dark);
  padding: 0.5rem;
  border-radius: 4px;
  margin-top: 0.5rem;
}
```

#### Partial Data Errors

When some data loads but not all:

```
┌─────────────────────────────────────────────────────────────┐
│ Projects                                    Last 30 days ▾  │
├─────────────────────────────────────────────────────────────┤
│ karma                    ▂▃▄▅▇█▅▃              $6.0843     │
│ 54 sessions · 786K tokens · 3d                              │
├─────────────────────────────────────────────────────────────┤
│ ⚠ 2 projects failed to load                    [Retry]     │
└─────────────────────────────────────────────────────────────┘
```

### Data Integrity Errors

#### Corrupted Session

```
┌─────────────────────────────────────────────────────────────┐
│ ⚠ Session 4d4c8731 has parsing errors                      │
│   3 of 127 entries could not be parsed                      │
│   Metrics may be incomplete                   [View Details]│
└─────────────────────────────────────────────────────────────┘
```

#### Missing Agent Data

In the agent tree:

```
Agents                                          3/5 expanded
├── ◈ opus  main                    $26.10  1.2M  
│   ├── ◇ opus  general-purpose     $11.62  450K
│   ├── ⚠ ??? agent-a1b2c3d         ---.--  ???   ← Missing data
│   └── ◇ haiku Explore             $0.71   12K
└── ◇ sonnet unknown                $0.09   5K

 ⚠ 1 agent has incomplete data
```

### Error Hierarchy

| Severity | Color | Icon | Behavior |
|----------|-------|------|----------|
| **Critical** | Red `#ef4444` | ✕ | Blocks view, requires action |
| **Warning** | Yellow `#f59e0b` | ⚠ | Inline notice, data may be stale |
| **Info** | Blue `#3b82f6` | ℹ | Dismissible tooltip |

---

## Celebration States

### Design Principle

Celebrate wins subtly. Developers appreciate recognition without distraction. Use **ephemeral highlights** that fade after acknowledgment.

### Cost Efficiency Achievements

#### New Record Low (Session)

When a session completes with lower cost than previous average:

```
┌─────────────┬─────────────┬─────────────┬─────────────┐
│ ▲ 21.2K     │ ▼ 1.8K      │ ★ $0.0892   │ ⚡ 12       │
│ tokens in   │ tokens out  │ session     │ agents      │
│             │             │ 56% below   │             │
│             │             │ avg ↓       │             │
└─────────────┴─────────────┴─────────────┴─────────────┘
                               ↑
                    Highlighted card with star + "below avg" label
```

**CSS Treatment:**
```css
.metric-card.is-celebrating {
  background: linear-gradient(
    135deg,
    rgba(16, 185, 129, 0.15) 0%,
    var(--bg-card) 50%
  );
  border-color: var(--primary);
  animation: celebrate-pulse 2s ease-out;
}

@keyframes celebrate-pulse {
  0% { box-shadow: 0 0 0 0 rgba(16, 185, 129, 0.4); }
  70% { box-shadow: 0 0 0 10px rgba(16, 185, 129, 0); }
  100% { box-shadow: 0 0 0 0 rgba(16, 185, 129, 0); }
}
```

#### Weekly Cost Down

In the History view summary:

```
Total: $42.18 · 280 sessions · $6.03/day avg
                                    ↓
         ┌────────────────────────────────────────┐
         │  ✓ 18% less than last week ($51.42)   │
         └────────────────────────────────────────┘
```

### Efficiency Milestones

#### Cache Hit Rate Achievement

```
┌─────────────────────────────────────────────────────────────┐
│  ✦ Great cache usage!                                       │
│    This session: 78% cache hit rate (vs 45% avg)            │
│    Saved approximately $0.42 in API costs                   │
│                                              [Dismiss]      │
└─────────────────────────────────────────────────────────────┘
```

#### Agent Efficiency

When a complex task completes with fewer agents than typical:

```
Agents                                          Completed ✓
├── ◈ opus  main                    $8.20   500K  
│   └── ◇ haiku Explore             $0.12   8K
└── Total: 2 agents (avg for similar: 5)  ← Efficiency note
```

### Streak Celebrations

#### Consistent Low-Cost Days

```
History                                    7d [30d] 90d
┌─────────────────────────────────────────────────────────────┐
│  🔥 5-day streak under $5/day                               │
└─────────────────────────────────────────────────────────────┘
│  ██  ██  ██  ██  ██  ← Green bars for streak days          │
```

### Toast Notifications

Ephemeral celebrations appear as toasts:

```
┌─────────────────────────────────────────┐
│  ✓ Session complete · $0.42 (record!)   │  ← Slides in from bottom-right
└─────────────────────────────────────────┘
```

**Toast Behavior:**
- Appear for 4 seconds
- Fade out automatically
- Stack if multiple (max 3 visible)
- Click to dismiss early
- Include action link when relevant

### Celebration Thresholds

| Achievement | Threshold | Frequency |
|-------------|-----------|-----------|
| Record low session | < 50% of 7-day avg | Per session |
| Weekly improvement | < 10% vs prev week | Weekly |
| Cache efficiency | > 70% cache hit | Per session |
| Agent efficiency | < 50% typical agents | Per task type |
| Cost streak | 5+ days under target | Daily |

### Opt-Out

```
Settings > Notifications
├── ☑ Show efficiency achievements
├── ☑ Show cost milestones  
├── ☐ Show streak celebrations
└── [Set daily cost target: $____]
```

---

## Power User Features

### Custom Date Ranges

#### Date Picker Component

Replace fixed 7d/30d/90d buttons with hybrid control:

```
┌─────────────────────────────────────────────────────────────┐
│ Cost History                    karma ▾                     │
│                                                             │
│  [7d] [30d] [90d] │ Custom: [Jan 1] to [Jan 8] [Apply]    │
└─────────────────────────────────────────────────────────────┘
```

**Keyboard Shortcuts:**
- `1` → Last 7 days
- `2` → Last 30 days  
- `3` → Last 90 days
- `c` → Open custom date picker
- `t` → Today only
- `w` → This week
- `m` → This month

#### Quick Range Presets

```
Custom Range
├── Today
├── Yesterday
├── This week
├── Last week
├── This month
├── Last month
├── This quarter
├── Year to date
└── Custom...
    ├── From: [2026-01-01] 📅
    └── To:   [2026-01-08] 📅
```

### Cost Alerts

#### Alert Configuration

```
Settings > Cost Alerts

Daily Budget                              
├── Threshold: [$10.00    ]
├── ☑ Show warning at 80%
├── ☑ Show alert at 100%
└── ☐ Block new sessions at limit

Session Budget
├── Threshold: [$5.00     ]
├── ☑ Show inline warning
└── ☐ Require confirmation to continue

Project Budgets
├── karma:       [$50/month ]
├── root:        [$100/month]
└── [+ Add project budget]
```

#### Alert Display

**Header Warning (approaching limit):**
```
┌──────────────────────────────────────────────────────────────┐
│ ◈ Karma     61288b4c    Live   Projects   History    ●      │
├──────────────────────────────────────────────────────────────┤
│ ⚠ Daily: $8.42 / $10.00 (84%)                    [Dismiss]  │
└──────────────────────────────────────────────────────────────┘
```

**Metric Card Warning:**
```
┌─────────────┬─────────────┬─────────────┬─────────────┐
│ ▲ 21.2K     │ ▼ 1.8K      │ ⚠ $8.42     │ ⚡ 45       │
│ tokens in   │ tokens out  │ 84% of $10  │ agents      │
└─────────────┴─────────────┴─────────────┴─────────────┘
                               ↑
                   Yellow background, progress ring
```

#### Alert Rules Engine

```
Rules                                         [+ New Rule]

┌─────────────────────────────────────────────────────────────┐
│ Rule: High-cost session warning                             │
│ When: session.cost > $3.00                                  │
│ Action: Show toast notification                             │
│ Status: Active                               [Edit] [Delete]│
└─────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────┐
│ Rule: Opus agent spawn                                      │
│ When: agent.model contains "opus"                           │
│ Action: Log to console                                      │
│ Status: Active                               [Edit] [Delete]│
└─────────────────────────────────────────────────────────────┘
```

### Bulk Operations

#### Multi-Select Mode

```
Projects                          [Select Mode: ON]  Last 30 days ▾

☑ karma                           ▂▃▄▅▇█▅▃          $6.0843
☑ root                            ▅▆▇▆▅▄▃▂          $18.6633
☐ go                              ▁▁▂▁▂▃▂▁          $0.3697
☐ integration                     ▂▃▂▃▄▃▂▁          $0.9091

Selected: 2 projects · $24.75 total

[Export CSV] [Compare] [Set Budget] [Cancel]
```

#### Bulk Actions

| Action | Description | Shortcut |
|--------|-------------|----------|
| Export CSV | Download selected as CSV | `⌘+E` |
| Compare | Side-by-side view | `⌘+K` |
| Set Budget | Apply budget to all selected | - |
| Archive | Hide from main list | - |
| Tag | Add label to selected | `⌘+T` |

### Export Options

#### Export Modal

```
┌─────────────────────────────────────────────────────────────┐
│ Export Data                                            ✕    │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│ Format:   ◉ CSV   ○ JSON   ○ Markdown                      │
│                                                             │
│ Scope:    ◉ Current view (karma, 7d)                       │
│           ○ All projects                                    │
│           ○ Selected only (2 projects)                      │
│                                                             │
│ Include:  ☑ Daily summaries                                │
│           ☑ Session details                                 │
│           ☐ Agent-level data                                │
│           ☐ Raw JSONL events                                │
│                                                             │
│                              [Cancel]  [Export]             │
└─────────────────────────────────────────────────────────────┘
```

### Keyboard Shortcuts

#### Global Shortcuts

| Key | Action | Context |
|-----|--------|---------|
| `1` | Switch to Live view | Global |
| `2` | Switch to Projects view | Global |
| `3` | Switch to History view | Global |
| `r` | Refresh data | Global |
| `?` | Show keyboard shortcuts | Global |
| `/` | Focus search/filter | Global |
| `Esc` | Close modal / cancel | Global |

#### View-Specific Shortcuts

**Live View:**
| Key | Action |
|-----|--------|
| `e` | Expand all agents |
| `c` | Collapse all agents |
| `↑/↓` | Navigate agent tree |
| `←/→` | Collapse/expand node |

**Projects View:**
| Key | Action |
|-----|--------|
| `j/k` | Navigate project list |
| `Enter` | Open selected project |
| `s` | Toggle select mode |
| `a` | Select all |

**History View:**
| Key | Action |
|-----|--------|
| `[` | Previous time period |
| `]` | Next time period |
| `p` | Cycle project filter |
| `d` | Download current view |

### Command Palette

Invoke with `⌘+K` (Mac) or `Ctrl+K` (Windows/Linux):

```
┌─────────────────────────────────────────────────────────────┐
│ > _                                                         │
├─────────────────────────────────────────────────────────────┤
│ Recent                                                      │
│   ↩ View project: karma                                     │
│   ↩ Export CSV                                              │
│   ↩ Set date range: Last 7 days                            │
├─────────────────────────────────────────────────────────────┤
│ Commands                                                    │
│   → Export data...                                          │
│   → Set cost alert...                                       │
│   → Compare projects...                                     │
│   → Filter by model...                                      │
│   → Jump to date...                                         │
└─────────────────────────────────────────────────────────────┘
```

### URL State & Deep Linking

All view state persisted in URL for shareability:

```
/dashboard?view=history&project=karma&days=7&compare=root
/dashboard?view=live&session=4d4c8731&expand=all
/dashboard?view=projects&sort=cost&order=desc&range=30
```

### Data Comparison Mode

Side-by-side project comparison:

```
┌───────────────────────────┬───────────────────────────┐
│ karma                     │ root                      │
├───────────────────────────┼───────────────────────────┤
│ Sessions: 54              │ Sessions: 96      (+78%)  │
│ Tokens: 786K              │ Tokens: 3.4M     (+332%)  │
│ Cost: $6.08               │ Cost: $18.66     (+207%)  │
│ Avg/session: $0.11        │ Avg/session: $0.19 (+73%) │
│ Peak day: Jan 4 ($2.10)   │ Peak day: Jan 3 ($4.50)   │
├───────────────────────────┴───────────────────────────┤
│            [7d comparison chart here]                 │
└───────────────────────────────────────────────────────┘
```

---

## Implementation Priority

### Core UI Improvements

| Phase | Effort | Impact | Items |
|-------|--------|--------|-------|
| **P1** | Low | High | Compact header, metric card sparklines |
| **P2** | Medium | High | Agent tree ASCII connectors, empty states |
| **P3** | Medium | Medium | Project sparklines, chart polish |
| **P4** | High | Medium | Grid/list toggle, responsive mobile |

### Interaction & States

| Phase | Effort | Impact | Items |
|-------|--------|--------|-------|
| **P1** | Low | High | Hover/focus states for all interactive elements |
| **P1** | Low | High | Connection error banner with reconnect |
| **P2** | Medium | Medium | Error cards with actionable messages |
| **P3** | Low | Low | Celebration toasts for efficiency wins |
| **P4** | Medium | Low | Configurable celebration thresholds |

### Power User Features

| Phase | Effort | Impact | Items |
|-------|--------|--------|-------|
| **P2** | Medium | High | Keyboard shortcuts (view switching, navigation) |
| **P3** | High | High | Custom date range picker |
| **P3** | Medium | High | Cost alerts with threshold configuration |
| **P4** | High | Medium | Command palette (`⌘+K`) |
| **P4** | Medium | Medium | Bulk operations (multi-select, export) |
| **P5** | High | Medium | URL state persistence & deep linking |
| **P5** | High | Low | Project comparison mode |

### Effort/Impact Matrix

```
                    LOW EFFORT          HIGH EFFORT
              ┌─────────────────────┬─────────────────────┐
  HIGH        │ ★ Hover states      │ Custom date ranges  │
  IMPACT      │ ★ Error banners     │ Cost alerts         │
              │ ★ Keyboard nav      │ Command palette     │
              ├─────────────────────┼─────────────────────┤
  LOW         │ Celebration toasts  │ Comparison mode     │
  IMPACT      │ Skeleton loading    │ Deep linking        │
              └─────────────────────┴─────────────────────┘
              
              ★ = Prioritize these first (P1-P2)
```

---

## Technical Considerations

### Framework Compatibility

Current stack: Petite-Vue + Pico CSS + uPlot

Recommendations:
1. **Keep Petite-Vue** - Lightweight and sufficient for this scale
2. **Replace Pico CSS** - Too opinionated; switch to Tailwind CSS or custom CSS
3. **Keep uPlot** - Performant for live streaming data
4. **Add Canvas sparklines** - Use same HistoryChart approach for inline charts

### Performance Budget

| Metric | Target |
|--------|--------|
| Initial load (3G) | <2s |
| Time to Interactive | <1.5s |
| SSE reconnection | <500ms |
| Chart update (60fps) | <16ms |

### Accessibility

1. **Keyboard Navigation:** Tab through cards, arrow keys in tree
2. **Screen Readers:** Announce metric values and trends
3. **Color Contrast:** All text meets WCAG AA (4.5:1 ratio)
4. **Reduced Motion:** Respect `prefers-reduced-motion` media query

---

## Success Metrics

### Core Metrics

| Metric | Current | Target |
|--------|---------|--------|
| Above-the-fold metrics | 3 | 4+ |
| Time to key insight | ~3s | <2s |
| Vertical scroll (live view) | Required | Optional |
| Empty state helpfulness | Low | High |
| Mobile usability | Poor | Good |

### Interaction Quality

| Metric | Current | Target |
|--------|---------|--------|
| Interactive elements with all states | ~20% | 100% |
| Error recovery options | None | All errors actionable |
| Keyboard-only navigation | Partial | Full coverage |
| Focus visibility | Inconsistent | WCAG AA compliant |

### Power User Adoption

| Metric | Baseline | Target (90 days) |
|--------|----------|------------------|
| Keyboard shortcut usage | 0% | 30% of sessions |
| Custom date range usage | N/A | 20% of history views |
| Cost alert configured | N/A | 50% of users |
| Export feature usage | N/A | 10% of users/week |

### Engagement Quality

| Metric | Target |
|--------|--------|
| Celebration toast seen | 80% of eligible sessions |
| Celebration dismissed (not annoying) | <20% immediate dismiss |
| Error recovery success | 90% resolved without refresh |
| Deep link shares | Tracked for adoption |

---

## Appendix: Screenshot Analysis

### `live-view.png`
- Metric cards are functional but too tall
- Empty chart state is bland
- Agent hierarchy section header and button work well
- Connection indicator is clear and professional

### `projects-view.png`
- Project cards are clean and scannable
- Cost placement (right-aligned) is correct
- Metadata density is good
- "Last: 6h ago" could be just "6h"

### `history-view.png`
- Chart dual-axis design is effective
- Summary cards duplicate header information
- Date range buttons are well-designed
- Project dropdown needs clearer "All Projects" state

### `history-7d.png` & `history-karma-7d.png`
- Y-axis scaling adjusts correctly per filter
- Bar widths adapt to date range
- Cumulative line provides good trend context

---

## Next Steps

### Immediate (Week 1)

1. **Review this document** with stakeholders
2. **Prototype P1 changes** in CodePen or local branch
   - Compact header
   - Metric card sparklines
   - Hover/focus states
   - Connection error banner

### Short-term (Weeks 2-4)

3. **User testing** with 3-5 developers using Karma Logger
   - Observe keyboard navigation patterns
   - Note error recovery attempts
   - Track celebration engagement
4. **Iterate** based on feedback
5. **Implement P1-P2** with feature flags

### Medium-term (Months 2-3)

6. **Implement P3** (custom date ranges, cost alerts)
7. **Build command palette** infrastructure
8. **Add URL state persistence**
9. **Document keyboard shortcuts** in help modal

### Long-term (Quarters 2+)

10. **Comparison mode** for enterprise users
11. **Team dashboard** for shared visibility (optional cloud sync)
12. **API for integrations** (Slack alerts, CI/CD webhooks)

---

## Document History

| Version | Date | Changes |
|---------|------|---------|
| 1.0 | 2026-01-08 | Initial design philosophy and layout proposals |
| 1.1 | 2026-01-08 | Added interaction states, error states, celebrations, power user features |

---

*This document aligns with the Karma Logger philosophy of local-first, real-time, hierarchical truth. The proposed UI changes prioritize developer productivity and glanceable insights while building for AI models 6 months from now—when these patterns will inform the next generation of developer tools.*
