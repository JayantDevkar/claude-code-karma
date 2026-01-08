/**
 * Karma Dashboard - Petite-Vue Application
 * Real-time metrics visualization with SSE
 */

// Agent Node Component
function AgentNode(props) {
  return {
    $template: '#agent-node-template',
    agent: props.agent,
    depth: props.depth || 0,
    formatCost(cents) {
      if (cents == null) return '$0.00';
      return '$' + (cents / 100).toFixed(4);
    }
  };
}

// Main App
PetiteVue.createApp({
  // State
  sessionId: null,
  connected: false,
  metrics: {
    tokensIn: 0,
    tokensOut: 0,
    cost: 0,
    cacheRead: 0,
    cacheCreation: 0,
    toolCalls: 0,
    sessions: 0,
    agents: 0
  },
  agentTree: [],
  sessions: [],
  chart: null,
  chartData: [],
  chartTimestamps: [],
  eventSource: null,
  maxDataPoints: 100,

  // Lifecycle
  init() {
    this.connectSSE();
    this.fetchInitialData();
  },

  // SSE Connection
  connectSSE() {
    if (this.eventSource) {
      this.eventSource.close();
    }

    this.eventSource = new EventSource('/events');

    this.eventSource.onopen = () => {
      console.log('SSE connected');
      this.connected = true;
    };

    this.eventSource.onerror = (err) => {
      console.error('SSE error:', err);
      this.connected = false;
      // EventSource auto-reconnects
    };

    // Handle init event
    this.eventSource.addEventListener('init', (event) => {
      try {
        const data = JSON.parse(event.data);
        console.log('Init data:', data);

        if (data.metrics) {
          this.updateMetrics(data.metrics);
        }

        if (data.sessions) {
          this.sessions = data.sessions;
          if (data.sessions.length > 0) {
            this.sessionId = data.sessions[0].id;
          }
        }
      } catch (err) {
        console.error('Failed to parse init event:', err);
      }
    });

    // Handle metrics updates
    this.eventSource.addEventListener('metrics', (event) => {
      try {
        const data = JSON.parse(event.data);
        this.updateMetrics(data);
        this.addChartDataPoint(data);
      } catch (err) {
        console.error('Failed to parse metrics event:', err);
      }
    });

    // Handle agents updates
    this.eventSource.addEventListener('agents', (event) => {
      try {
        const data = JSON.parse(event.data);
        this.agentTree = data;
      } catch (err) {
        console.error('Failed to parse agents event:', err);
      }
    });

    // Handle session start
    this.eventSource.addEventListener('session:start', (event) => {
      try {
        const data = JSON.parse(event.data);
        this.sessionId = data.sessionId;
        // Refresh sessions list
        this.fetchSessions();
      } catch (err) {
        console.error('Failed to parse session:start event:', err);
      }
    });
  },

  // Fetch initial data from REST API
  async fetchInitialData() {
    try {
      // Fetch current session
      const sessionRes = await fetch('/api/session');
      const sessionData = await sessionRes.json();

      if (sessionData.sessionId) {
        this.sessionId = sessionData.sessionId;
        if (sessionData.metrics) {
          this.updateMetrics(sessionData.metrics);
        }
        if (sessionData.agents) {
          this.agentTree = sessionData.agents;
        }
      }

      // Fetch all sessions
      await this.fetchSessions();

      // Fetch totals
      const totalsRes = await fetch('/api/totals');
      const totals = await totalsRes.json();
      this.updateMetrics(totals);

    } catch (err) {
      console.error('Failed to fetch initial data:', err);
    }
  },

  async fetchSessions() {
    try {
      const res = await fetch('/api/sessions?limit=10');
      const data = await res.json();
      this.sessions = data.sessions || [];
    } catch (err) {
      console.error('Failed to fetch sessions:', err);
    }
  },

  // Update metrics state
  updateMetrics(data) {
    if (data.tokensIn != null) this.metrics.tokensIn = data.tokensIn;
    if (data.tokensOut != null) this.metrics.tokensOut = data.tokensOut;
    if (data.cost != null) this.metrics.cost = data.cost;
    if (data.cacheRead != null) this.metrics.cacheRead = data.cacheRead;
    if (data.cacheCreation != null) this.metrics.cacheCreation = data.cacheCreation;
    if (data.toolCalls != null) this.metrics.toolCalls = data.toolCalls;
    if (data.sessions != null) this.metrics.sessions = data.sessions;
    if (data.agents != null) this.metrics.agents = data.agents;
  },

  // Add data point to chart
  addChartDataPoint(data) {
    const timestamp = data.timestamp || Date.now();
    const tokensIn = data.tokensIn || 0;
    const tokensOut = data.tokensOut || 0;

    this.chartTimestamps.push(timestamp / 1000); // uPlot uses seconds
    this.chartData.push([tokensIn, tokensOut]);

    // Keep only last N data points
    if (this.chartTimestamps.length > this.maxDataPoints) {
      this.chartTimestamps.shift();
      this.chartData.shift();
    }

    this.updateChart();
  },

  // Initialize or update uPlot chart
  updateChart() {
    if (this.chartData.length < 2) return;

    const container = document.getElementById('chart');
    if (!container) return;

    // Clear empty state
    const emptyState = container.querySelector('.empty-state');
    if (emptyState) {
      emptyState.remove();
    }

    // Prepare data for uPlot [timestamps, series1, series2, ...]
    const data = [
      this.chartTimestamps,
      this.chartData.map(d => d[0]), // tokensIn
      this.chartData.map(d => d[1])  // tokensOut
    ];

    const opts = {
      width: container.clientWidth || 800,
      height: 200,
      series: [
        {},
        {
          label: 'Tokens In',
          stroke: '#10b981',
          width: 2,
          fill: 'rgba(16, 185, 129, 0.1)'
        },
        {
          label: 'Tokens Out',
          stroke: '#6366f1',
          width: 2,
          fill: 'rgba(99, 102, 241, 0.1)'
        }
      ],
      axes: [
        {
          stroke: '#64748b',
          grid: { stroke: '#334155', width: 1 }
        },
        {
          stroke: '#64748b',
          grid: { stroke: '#334155', width: 1 },
          values: (self, ticks) => ticks.map(v => this.formatNumber(v))
        }
      ],
      scales: {
        x: { time: true },
        y: { auto: true }
      },
      legend: {
        show: true
      }
    };

    if (this.chart) {
      // Update existing chart
      this.chart.setData(data);
    } else {
      // Create new chart
      this.chart = new uPlot(opts, data, container);
    }
  },

  // Format helpers
  formatNumber(num) {
    if (num == null) return '0';
    if (num >= 1000000) {
      return (num / 1000000).toFixed(1) + 'M';
    }
    if (num >= 1000) {
      return (num / 1000).toFixed(1) + 'K';
    }
    return num.toLocaleString();
  },

  formatCost(cents) {
    if (cents == null) return '$0.00';
    return '$' + (cents / 100).toFixed(4);
  },

  // Cleanup
  destroy() {
    if (this.eventSource) {
      this.eventSource.close();
    }
    if (this.chart) {
      this.chart.destroy();
    }
  }
})
.component('AgentNode', AgentNode)
.mount('#app');

// Handle window resize for chart
let resizeTimeout;
window.addEventListener('resize', () => {
  clearTimeout(resizeTimeout);
  resizeTimeout = setTimeout(() => {
    const app = document.getElementById('app').__vue_app__;
    if (app && app.chart) {
      const container = document.getElementById('chart');
      if (container) {
        app.chart.setSize({ width: container.clientWidth, height: 200 });
      }
    }
  }, 250);
});

// Cleanup on page unload
window.addEventListener('beforeunload', () => {
  const app = document.getElementById('app').__vue_app__;
  if (app && app.destroy) {
    app.destroy();
  }
});
