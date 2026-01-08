/**
 * Karma Dashboard - Petite-Vue Application
 * Real-time metrics visualization with SSE
 */

// Agent Node Component (registered via v-scope in template)
function AgentNode(props) {
  return {
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
  // Make AgentNode available for nested components
  AgentNode,
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
  chartManager: null,
  eventSource: null,

  // Lifecycle
  init() {
    // Initialize chart manager with configurable retention
    this.chartManager = new ChartManager('chart', {
      maxDataPoints: window.CHART_DATA_RETENTION_POINTS || 3600
    });
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
            // Fetch agents for this session
            this.fetchSessionData(data.sessions[0].id);
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
        // Refresh sessions list and refetch session data with agents
        this.fetchSessions();
        this.fetchSessionData(data.sessionId);
      } catch (err) {
        console.error('Failed to parse session:start event:', err);
      }
    });
  },

  // Fetch initial data from REST API
  // Note: Agent data is fetched via SSE init event to ensure consistency
  async fetchInitialData() {
    try {
      // Fetch totals for aggregate metrics
      const totalsRes = await fetch('/api/totals');
      const totals = await totalsRes.json();
      this.updateMetrics(totals);

      // Sessions and agents are handled by SSE init event
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

  // Fetch session data including agents for a specific session
  async fetchSessionData(sessionId) {
    try {
      const res = await fetch(`/api/session/${sessionId}`);
      const data = await res.json();
      if (data.sessionId) {
        if (data.metrics) {
          this.updateMetrics(data.metrics);
        }
        if (data.agents) {
          this.agentTree = data.agents;
        }
      }
    } catch (err) {
      console.error('Failed to fetch session data:', err);
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

  // Add data point to chart (delegates to ChartManager)
  addChartDataPoint(data) {
    if (this.chartManager) {
      this.chartManager.addDataPoint(data);
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
    if (this.chartManager) {
      this.chartManager.destroy();
    }
  }
}).mount('#app');

// Handle window resize for chart
let resizeTimeout;
window.addEventListener('resize', () => {
  clearTimeout(resizeTimeout);
  resizeTimeout = setTimeout(() => {
    const app = document.getElementById('app').__vue_app__;
    if (app && app.chartManager) {
      app.chartManager.resize();
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
