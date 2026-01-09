# Phase 6: Empty & Loading States

**Scope**: Meaningful empty states, skeleton loading components, shimmer animations.

**Files**: `public/app.js`, `public/style.css`

**Effort**: Low | **Impact**: Medium

---

## Overview

Replace generic "Loading..." and "No data" messages with purposeful empty states that guide users, and skeleton loaders that maintain layout during data fetch.

---

## 6.1 Empty State Component

### Design Principles

- Icon + heading (no "..." ellipsis)
- Brief explanation
- Actionable tip
- Consistent padding and centering

### HTML Structure

```html
<div class="empty-state">
  <span class="empty-state__icon">◇</span>
  <h3 class="empty-state__title">No agents yet</h3>
  <p class="empty-state__message">
    Run a Claude Code session to see real-time agent hierarchy here.
  </p>
  <div class="empty-state__tip">
    <span class="empty-state__tip-label">Tip:</span>
    Use <code>karma watch</code> in terminal for live session monitoring.
  </div>
</div>
```

### CSS

```css
.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  text-align: center;
  padding: 3rem 2rem;
  min-height: 200px;
}

.empty-state__icon {
  font-size: 2.5rem;
  color: var(--text-muted);
  margin-bottom: 1rem;
}

.empty-state__title {
  font-size: 1.125rem;
  font-weight: 600;
  color: var(--text-primary);
  margin-bottom: 0.5rem;
}

.empty-state__message {
  font-size: 0.875rem;
  color: var(--text-secondary);
  max-width: 280px;
  line-height: 1.5;
  margin-bottom: 1.5rem;
}

.empty-state__tip {
  font-size: 0.8125rem;
  color: var(--text-muted);
  padding: 0.75rem 1rem;
  background: var(--bg-hover);
  border-radius: 4px;
  border-left: 3px solid var(--primary);
}

.empty-state__tip-label {
  font-weight: 500;
  color: var(--text-secondary);
}

.empty-state__tip code {
  font-family: var(--font-mono);
  color: var(--primary);
  background: var(--bg-dark);
  padding: 0.125rem 0.375rem;
  border-radius: 3px;
}
```

---

## 6.2 Empty State Variations

### No Sessions

```html
<div class="empty-state">
  <span class="empty-state__icon">📊</span>
  <h3 class="empty-state__title">No sessions recorded</h3>
  <p class="empty-state__message">
    Start using Claude Code to see your session metrics and costs here.
  </p>
</div>
```

### No Projects

```html
<div class="empty-state">
  <span class="empty-state__icon">📁</span>
  <h3 class="empty-state__title">No projects found</h3>
  <p class="empty-state__message">
    Projects appear after you've had Claude Code sessions in different directories.
  </p>
</div>
```

### No History Data

```html
<div class="empty-state">
  <span class="empty-state__icon">📈</span>
  <h3 class="empty-state__title">No history for this period</h3>
  <p class="empty-state__message">
    No sessions were recorded in the selected date range.
  </p>
  <button class="btn">View All Time</button>
</div>
```

### Connection Required

```html
<div class="empty-state">
  <span class="empty-state__icon">⚡</span>
  <h3 class="empty-state__title">Waiting for connection</h3>
  <p class="empty-state__message">
    The dashboard will update automatically when a session starts.
  </p>
  <div class="empty-state__tip">
    <span class="empty-state__tip-label">Tip:</span>
    Keep this tab open while coding to see live metrics.
  </div>
</div>
```

---

## 6.3 Skeleton Loading

### Skeleton Base Styles

```css
.skeleton {
  background: var(--color-skeleton);
  border-radius: 4px;
  position: relative;
  overflow: hidden;
}

.skeleton::after {
  content: '';
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: linear-gradient(
    90deg,
    transparent 0%,
    rgba(255, 255, 255, 0.05) 50%,
    transparent 100%
  );
  animation: skeleton-shimmer 1.5s infinite;
}

@keyframes skeleton-shimmer {
  from { transform: translateX(-100%); }
  to { transform: translateX(100%); }
}

/* Reduced motion */
@media (prefers-reduced-motion: reduce) {
  .skeleton::after {
    animation: none;
  }
}
```

### Skeleton Metric Cards

```html
<div class="metrics-grid metrics-grid--4col">
  <article class="metric-card metric-card--compact metric-card--skeleton">
    <div class="metric-card__header">
      <span class="skeleton skeleton--icon"></span>
      <span class="skeleton skeleton--value"></span>
    </div>
    <span class="skeleton skeleton--label"></span>
  </article>
  <!-- Repeat 3 more times -->
</div>
```

```css
.metric-card--skeleton {
  pointer-events: none;
}

.skeleton--icon {
  width: 1rem;
  height: 1rem;
}

.skeleton--value {
  width: 4rem;
  height: 1.5rem;
}

.skeleton--label {
  width: 5rem;
  height: 0.75rem;
  margin-top: 0.25rem;
}
```

### Skeleton Project Card

```html
<article class="project-card project-card--skeleton">
  <div class="project-card__header">
    <span class="skeleton skeleton--title"></span>
    <span class="skeleton skeleton--cost"></span>
  </div>
  <div class="project-card__meta">
    <span class="skeleton skeleton--meta"></span>
  </div>
</article>
```

```css
.project-card--skeleton {
  pointer-events: none;
}

.skeleton--title {
  width: 40%;
  height: 1rem;
}

.skeleton--cost {
  width: 3rem;
  height: 1rem;
}

.skeleton--meta {
  width: 60%;
  height: 0.75rem;
  margin-top: 0.5rem;
}
```

### Skeleton Agent Tree

```html
<div class="agent-tree__list agent-tree__list--skeleton">
  <div class="skeleton skeleton--node"></div>
  <div class="skeleton skeleton--node skeleton--node-indent"></div>
  <div class="skeleton skeleton--node skeleton--node-indent"></div>
  <div class="skeleton skeleton--node"></div>
</div>
```

```css
.skeleton--node {
  height: 1.5rem;
  margin: 0.375rem 1rem;
}

.skeleton--node-indent {
  margin-left: 2.5rem;
}
```

---

## 6.4 Loading State Management

```javascript
class LoadingState {
  constructor(containerId) {
    this.container = document.getElementById(containerId);
    this.originalContent = null;
  }

  showSkeleton(skeletonType) {
    if (!this.originalContent) {
      this.originalContent = this.container.innerHTML;
    }
    this.container.innerHTML = this.getSkeletonHTML(skeletonType);
    this.container.classList.add('is-loading');
  }

  showEmpty(type) {
    this.container.innerHTML = this.getEmptyStateHTML(type);
    this.container.classList.remove('is-loading');
  }

  showContent() {
    if (this.originalContent) {
      this.container.innerHTML = this.originalContent;
      this.originalContent = null;
    }
    this.container.classList.remove('is-loading');
  }

  getSkeletonHTML(type) {
    const skeletons = {
      metrics: `
        <div class="metrics-grid metrics-grid--4col">
          ${Array(4).fill(`
            <article class="metric-card metric-card--compact metric-card--skeleton">
              <div class="metric-card__header">
                <span class="skeleton skeleton--icon"></span>
                <span class="skeleton skeleton--value"></span>
              </div>
              <span class="skeleton skeleton--label"></span>
            </article>
          `).join('')}
        </div>
      `,
      projects: `
        <div class="projects-list">
          ${Array(3).fill(`
            <article class="project-card project-card--skeleton">
              <div class="project-card__header">
                <span class="skeleton skeleton--title"></span>
                <span class="skeleton skeleton--cost"></span>
              </div>
              <span class="skeleton skeleton--meta"></span>
            </article>
          `).join('')}
        </div>
      `,
      agents: `
        <div class="agent-tree__list agent-tree__list--skeleton">
          <div class="skeleton skeleton--node"></div>
          <div class="skeleton skeleton--node skeleton--node-indent"></div>
          <div class="skeleton skeleton--node skeleton--node-indent"></div>
        </div>
      `
    };
    return skeletons[type] || '';
  }

  getEmptyStateHTML(type) {
    const states = {
      'no-agents': `
        <div class="empty-state">
          <span class="empty-state__icon">◇</span>
          <h3 class="empty-state__title">No agents yet</h3>
          <p class="empty-state__message">
            Run a Claude Code session to see real-time agent hierarchy here.
          </p>
        </div>
      `,
      'no-sessions': `
        <div class="empty-state">
          <span class="empty-state__icon">📊</span>
          <h3 class="empty-state__title">No sessions recorded</h3>
          <p class="empty-state__message">
            Start using Claude Code to see your session metrics here.
          </p>
        </div>
      `,
      'no-projects': `
        <div class="empty-state">
          <span class="empty-state__icon">📁</span>
          <h3 class="empty-state__title">No projects found</h3>
          <p class="empty-state__message">
            Projects appear after you've used Claude Code in different directories.
          </p>
        </div>
      `
    };
    return states[type] || '';
  }
}
```

---

## 6.5 Transition Between States

```css
/* Fade transition for state changes */
.view-container {
  transition: opacity 200ms ease-out;
}

.view-container.is-loading {
  opacity: 0.7;
}

.view-container.is-transitioning {
  opacity: 0;
}
```

```javascript
async function transitionToContent(container, renderContent) {
  container.classList.add('is-transitioning');
  
  await new Promise(r => setTimeout(r, 200));
  
  renderContent();
  
  container.classList.remove('is-transitioning');
}
```

---

## Acceptance Criteria

- [ ] All views have empty states with icons and helpful messages
- [ ] Skeleton loaders maintain layout during loading
- [ ] Shimmer animation indicates loading progress
- [ ] Transitions between states are smooth (200ms)
- [ ] `prefers-reduced-motion` disables shimmer
- [ ] Empty states provide actionable guidance
- [ ] No "..." ellipsis in empty states

---

## Dependencies

- Phase 1 (Layout Foundation)
- Phase 2 (Interaction States)

---

## Testing Checklist

- [ ] Empty state renders for each view type
- [ ] Skeleton cards match layout of real cards
- [ ] Shimmer animation runs smoothly
- [ ] Loading state transitions are visible
- [ ] Empty state tips are helpful and accurate
- [ ] Screen reader announces state changes
- [ ] Reduced motion preference is respected
