# Phase 5: Frontend — History Chart

**Scope**: Visualize cost and token trends over time.

**Files**: `public/index.html`, `public/app.js`, `public/charts.js`, `public/style.css`

---

## UI Components

### 1. History View

```html
<div id="history-view" class="view hidden">
  <div class="view-header">
    <h2>Cost History</h2>
    <div class="history-controls">
      <select id="history-project-filter">
        <option value="">All Projects</option>
        <!-- Project options populated dynamically -->
      </select>
      <div class="date-range-buttons">
        <button class="range-btn" data-days="7">7d</button>
        <button class="range-btn active" data-days="30">30d</button>
        <button class="range-btn" data-days="90">90d</button>
      </div>
    </div>
  </div>

  <div class="chart-container">
    <canvas id="history-chart"></canvas>
  </div>

  <div class="history-summary">
    <div class="summary-card">
      <span class="label">Total Cost</span>
      <span class="value" id="summary-cost">$0.00</span>
    </div>
    <div class="summary-card">
      <span class="label">Sessions</span>
      <span class="value" id="summary-sessions">0</span>
    </div>
    <div class="summary-card">
      <span class="label">Avg/Day</span>
      <span class="value" id="summary-avg">$0.00</span>
    </div>
  </div>
</div>
```

---

## JavaScript (charts.js)

### Chart Configuration

Using lightweight canvas charting (no external dependencies):

```javascript
class HistoryChart {
  constructor(canvasId) {
    this.canvas = document.getElementById(canvasId);
    this.ctx = this.canvas.getContext('2d');
    this.data = [];
    this.padding = { top: 20, right: 20, bottom: 40, left: 50 };
  }

  setData(dailyMetrics) {
    this.data = dailyMetrics;
    this.render();
  }

  render() {
    const { width, height } = this.canvas.getBoundingClientRect();
    this.canvas.width = width * 2;  // Retina
    this.canvas.height = height * 2;
    this.ctx.scale(2, 2);

    this.ctx.clearRect(0, 0, width, height);

    if (this.data.length === 0) {
      this.renderEmpty(width, height);
      return;
    }

    this.renderAxes(width, height);
    this.renderBars(width, height);
    this.renderLine(width, height);
  }

  renderEmpty(width, height) {
    this.ctx.fillStyle = '#666';
    this.ctx.textAlign = 'center';
    this.ctx.fillText('No data for selected period', width / 2, height / 2);
  }

  renderAxes(width, height) {
    const { padding } = this;
    const chartWidth = width - padding.left - padding.right;
    const chartHeight = height - padding.top - padding.bottom;

    // Y-axis (cost)
    const maxCost = Math.max(...this.data.map(d => d.cost), 0.01);
    const yTicks = this.getNiceScale(0, maxCost, 5);

    this.ctx.strokeStyle = '#333';
    this.ctx.fillStyle = '#666';
    this.ctx.textAlign = 'right';
    this.ctx.font = '10px monospace';

    yTicks.forEach(tick => {
      const y = padding.top + chartHeight * (1 - tick / maxCost);
      this.ctx.fillText(`$${tick.toFixed(2)}`, padding.left - 5, y + 3);

      this.ctx.beginPath();
      this.ctx.strokeStyle = '#222';
      this.ctx.moveTo(padding.left, y);
      this.ctx.lineTo(width - padding.right, y);
      this.ctx.stroke();
    });

    // X-axis (dates)
    this.ctx.textAlign = 'center';
    const barWidth = chartWidth / this.data.length;

    this.data.forEach((d, i) => {
      if (i % Math.ceil(this.data.length / 7) === 0) {
        const x = padding.left + barWidth * (i + 0.5);
        const date = new Date(d.day);
        const label = `${date.getMonth() + 1}/${date.getDate()}`;
        this.ctx.fillText(label, x, height - padding.bottom + 15);
      }
    });
  }

  renderBars(width, height) {
    const { padding, data } = this;
    const chartWidth = width - padding.left - padding.right;
    const chartHeight = height - padding.top - padding.bottom;
    const maxCost = Math.max(...data.map(d => d.cost), 0.01);
    const barWidth = chartWidth / data.length;
    const barPadding = Math.max(1, barWidth * 0.1);

    data.forEach((d, i) => {
      const barHeight = (d.cost / maxCost) * chartHeight;
      const x = padding.left + barWidth * i + barPadding;
      const y = padding.top + chartHeight - barHeight;

      this.ctx.fillStyle = d.cost > 0 ? '#3b82f6' : '#333';
      this.ctx.fillRect(x, y, barWidth - barPadding * 2, barHeight);
    });
  }

  renderLine(width, height) {
    // Cumulative cost line
    const { padding, data } = this;
    const chartWidth = width - padding.left - padding.right;
    const chartHeight = height - padding.top - padding.bottom;
    const barWidth = chartWidth / data.length;

    let cumulative = 0;
    const cumData = data.map(d => {
      cumulative += d.cost;
      return cumulative;
    });
    const maxCum = Math.max(...cumData, 0.01);

    this.ctx.beginPath();
    this.ctx.strokeStyle = '#f59e0b';
    this.ctx.lineWidth = 2;

    cumData.forEach((cum, i) => {
      const x = padding.left + barWidth * (i + 0.5);
      const y = padding.top + chartHeight * (1 - cum / maxCum);
      if (i === 0) this.ctx.moveTo(x, y);
      else this.ctx.lineTo(x, y);
    });

    this.ctx.stroke();
  }

  getNiceScale(min, max, ticks) {
    const range = max - min;
    const step = range / ticks;
    const magnitude = Math.pow(10, Math.floor(Math.log10(step)));
    const residual = step / magnitude;

    let niceStep;
    if (residual <= 1.5) niceStep = magnitude;
    else if (residual <= 3) niceStep = 2 * magnitude;
    else if (residual <= 7) niceStep = 5 * magnitude;
    else niceStep = 10 * magnitude;

    const result = [];
    for (let v = 0; v <= max; v += niceStep) {
      result.push(v);
    }
    return result;
  }
}
```

---

## JavaScript (app.js)

### Data Fetching

```javascript
async function fetchHistory(project = null, days = 30) {
  const endpoint = project
    ? `/api/projects/${encodeURIComponent(project)}/history?days=${days}`
    : `/api/totals/history?days=${days}`;

  const res = await fetch(endpoint);
  const data = await res.json();
  return data;
}
```

### State & Event Handlers

```javascript
// State
let historyChart = null;
let historyProject = null;
let historyDays = 30;

// Initialize
function initHistoryView() {
  historyChart = new HistoryChart('history-chart');

  // Project filter
  document.getElementById('history-project-filter')
    .addEventListener('change', (e) => {
      historyProject = e.target.value || null;
      updateHistory();
    });

  // Date range buttons
  document.querySelectorAll('.range-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      document.querySelectorAll('.range-btn').forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
      historyDays = parseInt(btn.dataset.days, 10);
      updateHistory();
    });
  });
}

async function updateHistory() {
  const data = await fetchHistory(historyProject, historyDays);
  historyChart.setData(data);
  updateHistorySummary(data);
}

function updateHistorySummary(data) {
  const totalCost = data.reduce((sum, d) => sum + d.cost, 0);
  const totalSessions = data.reduce((sum, d) => sum + d.sessions, 0);
  const avgCost = data.length > 0 ? totalCost / data.length : 0;

  document.getElementById('summary-cost').textContent = `$${totalCost.toFixed(2)}`;
  document.getElementById('summary-sessions').textContent = totalSessions;
  document.getElementById('summary-avg').textContent = `$${avgCost.toFixed(2)}`;
}

// Populate project dropdown
async function populateProjectFilter() {
  const projects = await fetchProjects();
  const select = document.getElementById('history-project-filter');
  select.innerHTML = '<option value="">All Projects</option>' +
    projects.map(p =>
      `<option value="${escapeHtml(p.projectName)}">${escapeHtml(p.projectName)}</option>`
    ).join('');
}
```

---

## CSS (style.css)

```css
/* History view */
.history-controls {
  display: flex;
  gap: 1rem;
  align-items: center;
}

.date-range-buttons {
  display: flex;
  gap: 0.25rem;
}

.range-btn {
  padding: 0.25rem 0.75rem;
  border: 1px solid var(--border);
  background: transparent;
  border-radius: 4px;
  cursor: pointer;
  font-size: 0.875rem;
}

.range-btn:hover {
  background: var(--muted-bg);
}

.range-btn.active {
  background: var(--accent);
  border-color: var(--accent);
  color: white;
}

/* Chart container */
.chart-container {
  height: 300px;
  margin: 1rem 0;
  background: var(--card-bg);
  border-radius: 8px;
  padding: 1rem;
}

#history-chart {
  width: 100%;
  height: 100%;
}

/* Summary cards */
.history-summary {
  display: flex;
  gap: 1rem;
  margin-top: 1rem;
}

.summary-card {
  flex: 1;
  background: var(--card-bg);
  padding: 1rem;
  border-radius: 8px;
  text-align: center;
}

.summary-card .label {
  display: block;
  font-size: 0.75rem;
  color: var(--muted);
  margin-bottom: 0.25rem;
}

.summary-card .value {
  font-size: 1.5rem;
  font-weight: 600;
  font-family: monospace;
}
```

---

## Data Flow

```
History View Opened
      │
      ▼
populateProjectFilter()
      │
      ├─ GET /api/projects
      │
      ▼
updateHistory()
      │
      ├─ GET /api/totals/history?days=30
      │
      ▼
historyChart.setData(data)
      │
      ▼
User changes project/range
      │
      ├─ GET /api/projects/:name/history?days=X
      │
      ▼
historyChart.setData(data)
```

---

## Acceptance Criteria

- [ ] Bar chart renders daily cost data
- [ ] Cumulative line overlay shows trend
- [ ] Y-axis auto-scales with nice tick values
- [ ] X-axis shows date labels (not too dense)
- [ ] Project dropdown filters to single project
- [ ] Date range buttons (7d/30d/90d) work correctly
- [ ] Summary shows total cost, sessions, avg/day
- [ ] Empty state handled gracefully
- [ ] Chart resizes with window (responsive)
- [ ] Retina display support

---

## Dependencies

- **Phase 2**: `/api/totals/history`, `/api/projects/:name/history`
- **Phase 3**: `fetchProjects()` function

## Estimated Complexity

Medium-High — Canvas charting requires math for scales/positioning.
