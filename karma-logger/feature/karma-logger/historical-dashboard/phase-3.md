# Phase 3: Frontend — Projects View

**Scope**: Build project list UI with selection and navigation.

**Files**: `public/index.html`, `public/app.js`, `public/style.css`

---

## UI Components

### 1. Project List

Display all projects as selectable cards.

```html
<div id="projects-view" class="view">
  <div class="view-header">
    <h2>Projects</h2>
    <select id="date-range-filter">
      <option value="7">Last 7 days</option>
      <option value="30" selected>Last 30 days</option>
      <option value="90">Last 90 days</option>
    </select>
  </div>
  <div id="project-list" class="project-list">
    <!-- Project cards rendered here -->
  </div>
</div>
```

### 2. Project Card

Individual project with key metrics.

```html
<div class="project-card" data-project="karma-logger">
  <div class="project-header">
    <span class="project-name">karma-logger</span>
    <span class="project-cost">$4.52</span>
  </div>
  <div class="project-meta">
    <span>12 sessions</span>
    <span>8.2M tokens</span>
    <span>3 active days</span>
  </div>
  <div class="project-last-activity">
    Last: 2h ago
  </div>
</div>
```

### 3. Navigation Tabs

Switch between views.

```html
<nav class="view-tabs">
  <button class="tab active" data-view="live">Live</button>
  <button class="tab" data-view="projects">Projects</button>
  <button class="tab" data-view="history">History</button>
</nav>
```

---

## JavaScript (app.js)

### State Management

```javascript
const state = {
  currentView: 'live',      // 'live' | 'projects' | 'history'
  selectedProject: null,     // string | null
  projects: [],             // ProjectSummary[]
  dateRange: 30,            // days
};
```

### API Functions

```javascript
async function fetchProjects() {
  const res = await fetch('/api/projects');
  state.projects = await res.json();
  renderProjects();
}

async function selectProject(name) {
  state.selectedProject = name;
  const res = await fetch(`/api/projects/${encodeURIComponent(name)}`);
  const detail = await res.json();
  renderProjectDetail(detail);
}
```

### Render Functions

```javascript
function renderProjects() {
  const container = document.getElementById('project-list');
  container.innerHTML = state.projects.map(p => `
    <div class="project-card" onclick="selectProject('${p.projectName}')">
      <div class="project-header">
        <span class="project-name">${escapeHtml(p.projectName)}</span>
        <span class="project-cost">${formatCost(p.totalCost)}</span>
      </div>
      <div class="project-meta">
        <span>${p.sessionCount} sessions</span>
        <span>${formatTokens(p.totalTokensIn + p.totalTokensOut)}</span>
        <span>${p.activeDays} days</span>
      </div>
      <div class="project-last-activity">
        Last: ${formatRelativeTime(p.lastActivity)}
      </div>
    </div>
  `).join('');
}

function renderProjectDetail(detail) {
  // Show sessions list for selected project
  // Enable drill-down to session view
}
```

### Utility Functions

```javascript
function formatCost(cost) {
  return `$${cost.toFixed(2)}`;
}

function formatTokens(tokens) {
  if (tokens >= 1_000_000) return `${(tokens / 1_000_000).toFixed(1)}M`;
  if (tokens >= 1_000) return `${(tokens / 1_000).toFixed(1)}k`;
  return tokens.toString();
}

function formatRelativeTime(iso) {
  const diff = Date.now() - new Date(iso).getTime();
  const hours = Math.floor(diff / 3600000);
  if (hours < 1) return 'just now';
  if (hours < 24) return `${hours}h ago`;
  const days = Math.floor(hours / 24);
  return `${days}d ago`;
}

function escapeHtml(str) {
  const div = document.createElement('div');
  div.textContent = str;
  return div.innerHTML;
}
```

---

## CSS (style.css)

```css
/* View tabs */
.view-tabs {
  display: flex;
  gap: 0.5rem;
  border-bottom: 1px solid var(--border);
  margin-bottom: 1rem;
}

.tab {
  padding: 0.5rem 1rem;
  border: none;
  background: transparent;
  cursor: pointer;
  border-bottom: 2px solid transparent;
}

.tab.active {
  border-bottom-color: var(--accent);
  color: var(--accent);
}

/* Project list */
.project-list {
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
}

.project-card {
  padding: 1rem;
  border: 1px solid var(--border);
  border-radius: 8px;
  cursor: pointer;
  transition: border-color 0.2s;
}

.project-card:hover {
  border-color: var(--accent);
}

.project-header {
  display: flex;
  justify-content: space-between;
  margin-bottom: 0.5rem;
}

.project-name {
  font-weight: 600;
}

.project-cost {
  color: var(--cost-color);
  font-family: monospace;
}

.project-meta {
  display: flex;
  gap: 1rem;
  font-size: 0.875rem;
  color: var(--muted);
}

.project-last-activity {
  font-size: 0.75rem;
  color: var(--muted);
  margin-top: 0.5rem;
}
```

---

## Acceptance Criteria

- [ ] Project list loads on view switch
- [ ] Cards display name, cost, sessions, tokens, active days
- [ ] Clicking card selects project and shows sessions
- [ ] Relative time shows correct format (Xh ago, Xd ago)
- [ ] Large token counts formatted (k, M)
- [ ] Tab navigation switches views correctly
- [ ] Selected project state persists during view switches

---

## Dependencies

- **Phase 2**: `/api/projects` endpoint

## Estimated Complexity

Medium — state management, rendering, and styling.
