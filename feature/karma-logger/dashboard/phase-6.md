# Phase 6: Web Dashboard UI

**Status:** Complete
**Depends On:** Phase 5 (Web Server & SSE)
**Blocks:** None (MVP Complete)

---

## Objective

Build frontend with charts, agent tree visualization, session history, and `karma dashboard` command.

---

## Scope

### In Scope
- HTML template with Pico CSS
- Petite-Vue for reactivity
- uPlot time-series charts
- Agent tree visualization
- Session history table
- SSE connection handling with auto-reconnect
- `karma dashboard` command (with `--port`, `--open` flags)

### Out of Scope
- Light theme (MVP = dark only)
- Data export
- Custom timeframes

---

## Implementation

### 1. HTML Template

```html
<!-- src/dashboard/public/index.html -->
<!DOCTYPE html>
<html lang="en" data-theme="dark">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Karma Logger Dashboard</title>
  <link rel="stylesheet" href="https://unpkg.com/@picocss/pico@2/css/pico.min.css">
  <link rel="stylesheet" href="https://unpkg.com/uplot@1.6.30/dist/uPlot.min.css">
  <link rel="stylesheet" href="style.css">
</head>
<body>
  <main class="container" id="app" @vue:mounted="init">
    <!-- Header -->
    <header>
      <h1>Karma Logger</h1>
      <span class="session-id">Session: {{ sessionId || '---' }}</span>
      <span :class="['status', connected ? 'connected' : 'disconnected']">
        {{ connected ? 'Live' : 'Disconnected' }}
      </span>
    </header>

    <!-- Token Chart -->
    <section class="chart-section">
      <h2>Token Usage Over Time</h2>
      <div id="token-chart"></div>
    </section>

    <!-- Metrics Cards -->
    <section class="metrics-row">
      <article class="metric-card">
        <header>Tokens In</header>
        <data :value="metrics.tokensIn">{{ formatNumber(metrics.tokensIn) }}</data>
        <small>+{{ formatNumber(metrics.tokensInRate) }}/s</small>
      </article>
      <article class="metric-card">
        <header>Tokens Out</header>
        <data :value="metrics.tokensOut">{{ formatNumber(metrics.tokensOut) }}</data>
        <small>+{{ formatNumber(metrics.tokensOutRate) }}/s</small>
      </article>
      <article class="metric-card">
        <header>Total Cost</header>
        <data :value="metrics.cost">{{ formatCost(metrics.cost) }}</data>
        <small>+{{ formatCost(metrics.costRate) }}/s</small>
      </article>
    </section>

    <!-- Agent Tree -->
    <section class="agent-section">
      <h2>Agent Hierarchy</h2>
      <div class="agent-tree" v-if="agentTree">
        <agent-node :node="agentTree" :depth="0"></agent-node>
      </div>
      <p v-else class="empty-state">No active agents</p>
    </section>

    <!-- Session History -->
    <section class="history-section">
      <h2>Recent Sessions</h2>
      <table>
        <thead>
          <tr>
            <th>ID</th>
            <th>Project</th>
            <th>Agents</th>
            <th>Tokens</th>
            <th>Cost</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="session in sessions" :key="session.id">
            <td><code>{{ session.id.slice(0, 7) }}</code></td>
            <td>{{ session.project }}</td>
            <td>{{ session.agentCount }}</td>
            <td>{{ formatNumber(session.tokensTotal) }}</td>
            <td>{{ formatCost(session.cost) }}</td>
          </tr>
        </tbody>
      </table>
    </section>
  </main>

  <script src="https://unpkg.com/petite-vue@0.4.1/dist/petite-vue.iife.js"></script>
  <script src="https://unpkg.com/uplot@1.6.30/dist/uPlot.iife.min.js"></script>
  <script src="app.js"></script>
</body>
</html>
```

### 2. Styles

```css
/* src/dashboard/public/style.css */
:root {
  --primary: #10b981;
  --secondary: #6366f1;
  --accent: #f59e0b;
}

header {
  display: flex;
  align-items: center;
  gap: 1rem;
  margin-bottom: 2rem;
}

header h1 {
  margin: 0;
}

.session-id {
  color: var(--muted-color);
  margin-left: auto;
}

.status {
  padding: 0.25rem 0.5rem;
  border-radius: 4px;
  font-size: 0.875rem;
}

.status.connected {
  background: var(--primary);
  color: white;
}

.status.disconnected {
  background: var(--del-color);
  color: white;
}

.metrics-row {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 1rem;
  margin: 2rem 0;
}

.metric-card {
  text-align: center;
  padding: 1.5rem;
}

.metric-card header {
  display: block;
  color: var(--muted-color);
  margin-bottom: 0.5rem;
}

.metric-card data {
  display: block;
  font-size: 2rem;
  font-weight: bold;
  color: var(--primary);
}

.metric-card small {
  color: var(--muted-color);
}

.chart-section {
  margin: 2rem 0;
}

#token-chart {
  height: 200px;
}

.agent-tree {
  font-family: monospace;
  padding: 1rem;
  background: var(--card-background-color);
  border-radius: 8px;
}

.agent-node {
  margin-left: 1.5rem;
}

.agent-node:first-child {
  margin-left: 0;
}

.agent-status {
  margin-left: 0.5rem;
}

.agent-status.complete { color: var(--primary); }
.agent-status.running { color: var(--accent); }
.agent-status.error { color: var(--del-color); }

.history-section table {
  margin-top: 1rem;
}

.empty-state {
  color: var(--muted-color);
  text-align: center;
  padding: 2rem;
}
```

### 3. App JavaScript

```js
// src/dashboard/public/app.js
const { createApp, reactive } = PetiteVue;

// Agent node component
function AgentNode({ node, depth }) {
  const statusIcons = { complete: '✓', running: '⟳', error: '✗' };

  return {
    $template: `
      <div class="agent-node">
        <span>
          <strong>{{ node.name }}</strong>
          <span class="muted">({{ node.model }})</span>
          {{ formatCost(node.cost) }}
          <span :class="['agent-status', node.status]">
            {{ statusIcons[node.status] }}
          </span>
        </span>
        <div v-for="child in node.children" :key="child.id">
          <agent-node :node="child" :depth="depth + 1"></agent-node>
        </div>
      </div>
    `,
    node,
    depth,
    statusIcons,
    formatCost: (cents) => `$${(cents / 100).toFixed(2)}`,
  };
}

// Main app
createApp({
  // State
  sessionId: null,
  connected: false,
  metrics: reactive({
    tokensIn: 0,
    tokensOut: 0,
    cost: 0,
    tokensInRate: 0,
    tokensOutRate: 0,
    costRate: 0,
  }),
  agentTree: null,
  sessions: [],
  chart: null,
  chartData: { timestamps: [], tokensIn: [], tokensOut: [] },

  // Lifecycle
  init() {
    this.connectSSE();
    this.fetchSessions();
    this.initChart();
  },

  // SSE Connection
  connectSSE() {
    const eventSource = new EventSource('/events');

    eventSource.onopen = () => {
      this.connected = true;
    };

    eventSource.onerror = () => {
      this.connected = false;
      // Auto-reconnect handled by EventSource
    };

    eventSource.addEventListener('init', (e) => {
      const data = JSON.parse(e.data);
      this.sessionId = data.sessionId;
      this.updateMetrics(data);
    });

    eventSource.addEventListener('metrics', (e) => {
      const data = JSON.parse(e.data);
      this.updateMetrics(data);
      this.updateChart(data);
    });

    eventSource.addEventListener('agents', (e) => {
      this.agentTree = JSON.parse(e.data).root;
    });
  },

  updateMetrics(data) {
    // Calculate rates
    const prevIn = this.metrics.tokensIn;
    const prevOut = this.metrics.tokensOut;
    const prevCost = this.metrics.cost;

    this.metrics.tokensIn = data.tokensIn;
    this.metrics.tokensOut = data.tokensOut;
    this.metrics.cost = data.cost;
    this.metrics.tokensInRate = data.tokensIn - prevIn;
    this.metrics.tokensOutRate = data.tokensOut - prevOut;
    this.metrics.costRate = data.cost - prevCost;
  },

  // Fetch sessions
  async fetchSessions() {
    const res = await fetch('/api/sessions?limit=10');
    const data = await res.json();
    this.sessions = data.sessions;
  },

  // Chart
  initChart() {
    const opts = {
      width: document.getElementById('token-chart').clientWidth,
      height: 200,
      series: [
        {},
        { stroke: '#10b981', label: 'Tokens In' },
        { stroke: '#6366f1', label: 'Tokens Out' },
      ],
      axes: [
        { show: false },
        { size: 60 },
      ],
    };

    const data = [[], [], []];
    this.chart = new uPlot(opts, data, document.getElementById('token-chart'));
  },

  updateChart(data) {
    const now = Date.now() / 1000;
    this.chartData.timestamps.push(now);
    this.chartData.tokensIn.push(data.tokensIn);
    this.chartData.tokensOut.push(data.tokensOut);

    // Keep last 60 points
    if (this.chartData.timestamps.length > 60) {
      this.chartData.timestamps.shift();
      this.chartData.tokensIn.shift();
      this.chartData.tokensOut.shift();
    }

    this.chart.setData([
      this.chartData.timestamps,
      this.chartData.tokensIn,
      this.chartData.tokensOut,
    ]);
  },

  // Helpers
  formatNumber(n) {
    if (n >= 1000000) return `${(n / 1000000).toFixed(1)}M`;
    if (n >= 1000) return `${(n / 1000).toFixed(1)}K`;
    return n.toLocaleString();
  },

  formatCost(cents) {
    return `$${(cents / 100).toFixed(2)}`;
  },

  // Components
  AgentNode,
}).mount('#app');
```

### 4. Command Integration

```ts
// src/cli/commands/dashboard.ts
import { startServer } from '../dashboard/index.js';

interface DashboardOptions {
  port?: number;
  open?: boolean;
}

export async function dashboardCommand(options: DashboardOptions) {
  await startServer({
    port: options.port || 3333,
    open: options.open ?? true,
  });
}
```

```ts
// Update CLI entry point
program
  .command('dashboard')
  .description('Launch web dashboard')
  .option('-p, --port <number>', 'Port to listen on', '3333')
  .option('--no-open', 'Do not auto-open browser')
  .action(dashboardCommand);
```

---

## Success Criteria

1. Dashboard loads in <500KB total
2. Charts render 1000+ data points smoothly
3. SSE reconnects automatically on disconnect
4. Agent tree displays hierarchy correctly
5. Session history loads and displays
6. Works in Chrome, Firefox, Safari
7. `karma dashboard` command launches server and opens browser
8. `--port` and `--no-open` flags work

---

## Test Plan

```ts
// tests/dashboard/frontend.test.ts
// E2E tests using Playwright or similar

describe('Dashboard Frontend', () => {
  it('loads and connects to SSE', async () => {
    // Start server, open browser, verify connected status
  });

  it('displays metrics from API', async () => {
    // Verify metric cards show values
  });

  it('updates chart on SSE events', async () => {
    // Verify chart updates when metrics change
  });
});
```

---

## Browser Compatibility

| Browser | Version | Status |
|---------|---------|--------|
| Chrome | 90+ | Required |
| Firefox | 88+ | Required |
| Safari | 14+ | Required |
| Edge | 90+ | Nice to have |

---

## Acceptance

- [ ] index.html created with structure
- [ ] style.css provides dark theme
- [ ] app.js handles SSE and reactivity
- [ ] uPlot chart renders and updates
- [ ] Agent tree displays correctly
- [ ] Session history table works
- [ ] SSE auto-reconnects
- [ ] `karma dashboard` command works
- [ ] `--port` and `--no-open` flags work
- [ ] Tests pass
- [ ] Works in Chrome, Firefox, Safari

---

## MVP Complete Checklist

After Phase 6, the Dashboard MVP is complete:

- [x] Phase 1: TUI Core Setup
- [x] Phase 2: TUI MetricsCard
- [x] Phase 3: TUI AgentTree
- [x] Phase 4: TUI Sparkline & Commands
- [x] Phase 5: Web Server & SSE
- [x] Phase 6: Web Dashboard UI

Commands available:
```bash
karma watch --ui        # TUI dashboard
karma dashboard         # Web dashboard at localhost:3333
karma dashboard --port 8080 --no-open
```
