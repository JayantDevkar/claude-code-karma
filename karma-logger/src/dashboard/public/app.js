/**
 * Karma Dashboard - Petite-Vue Application
 * Real-time metrics visualization with SSE
 */

class SSEConnection {
  constructor(url, handlers) {
    this.url = url;
    this.handlers = handlers;
    this.eventSource = null;
    this.retryCount = 0;
    this.maxRetries = 5;
    this.retryDelay = 1000; // exponential backoff from 1s
    this.lastDataTime = null;
  }

  connect({ resetRetries = false } = {}) {
    if (resetRetries) {
      this.retryCount = 0;
      this.retryDelay = 1000;
    }

    if (this.eventSource) {
      this.eventSource.close();
      this.eventSource = null;
    }

    this.handlers?.onState?.('reconnecting');

    const es = new EventSource(this.url);
    this.eventSource = es;

    es.onopen = () => {
      this.retryCount = 0;
      this.retryDelay = 1000;
      this.handlers?.onState?.('connected');
      this.handlers?.onBanner?.({ type: 'hide' });
    };

    es.onerror = () => {
      try {
        es.close();
      } catch {
        // ignore
      }
      this.eventSource = null;
      this.handleDisconnect();
    };

    const markData = () => {
      this.lastDataTime = new Date();
      this.handlers?.onData?.(this.lastDataTime);
    };

    // Some servers emit default message events; we treat them as "data seen".
    es.onmessage = () => markData();

    // Custom event handlers are attached by caller (Petite-Vue app)
    this.handlers?.attach?.(es, markData);
  }

  handleDisconnect() {
    if (this.retryCount < this.maxRetries) {
      this.handlers?.onState?.('reconnecting');
      this.handlers?.onBanner?.({ type: 'reconnecting', lastDataTime: this.lastDataTime });

      const delay = this.retryDelay;
      this.retryCount += 1;
      this.retryDelay = Math.min(this.retryDelay * 2, 30000);

      setTimeout(() => this.connect(), delay);
      return;
    }

    this.handlers?.onState?.('error');
    this.handlers?.onBanner?.({ type: 'retry', lastDataTime: this.lastDataTime });
  }

  retry() {
    this.retryCount = 0;
    this.retryDelay = 1000;
    this.connect();
  }

  close() {
    if (this.eventSource) {
      this.eventSource.close();
      this.eventSource = null;
    }
  }
}

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
  connectionState: 'disconnected', // connected | reconnecting | disconnected | error
  connectionTitle: 'Disconnected',
  bannerDismissed: false,
  banner: {
    visible: false,
    className: 'error-banner--warning',
    icon: '⚠',
    message: '',
    showRetry: false
  },
  currentView: 'live',
  selectedProject: null,
  projects: [],
  dateRange: 30,
  expandedAgents: {},
  allAgentsExpanded: false,
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
  sseConnection: null,
  lastDataTime: null,
  // History view state
  historyChart: null,
  historyProject: '',
  historyDays: 30,
  historyData: [],
  historySummary: {
    totalCost: 0,
    totalSessions: 0,
    avgCost: 0
  },

  // Lifecycle
  init() {
    // Initialize chart manager with configurable retention
    this.chartManager = new ChartManager('chart', {
      maxDataPoints: window.CHART_DATA_RETENTION_POINTS || 3600
    });
    this.connectSSE({ resetRetries: true });
    this.fetchInitialData();
  },

  // SSE Connection
  connectSSE({ resetRetries = false } = {}) {
    if (!this.sseConnection) {
      this.sseConnection = new SSEConnection('/events', {
        onState: (state) => this.setConnectionState(state),
        onData: (dt) => { this.lastDataTime = dt; },
        onBanner: (payload) => this.handleSSEBanner(payload),
        attach: (es, markData) => this.attachSSEHandlers(es, markData)
      });
    }

    // Backward-compat: keep eventSource updated for destroy()
    this.sseConnection.connect({ resetRetries });
    this.eventSource = this.sseConnection.eventSource;
  },

  attachSSEHandlers(es, markData) {
    // Handle init event
    es.addEventListener('init', (event) => {
      markData();
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
    es.addEventListener('metrics', (event) => {
      markData();
      try {
        const data = JSON.parse(event.data);
        this.updateMetrics(data);
        this.addChartDataPoint(data);
      } catch (err) {
        console.error('Failed to parse metrics event:', err);
      }
    });

    // Handle agents updates
    es.addEventListener('agents', (event) => {
      markData();
      try {
        const data = JSON.parse(event.data);
        this.agentTree = data;
      } catch (err) {
        console.error('Failed to parse agents event:', err);
      }
    });

    // Handle session start
    es.addEventListener('session:start', (event) => {
      markData();
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

  // Phase 1: metric card numeric cost (icon provides "$")
  formatCostNumber(cents) {
    if (cents == null) return '0.0000';
    return (cents / 100).toFixed(4);
  },

  // Phase 3 (structure): connection + banner helpers
  setConnectionState(state) {
    this.connectionState = state;
    this.connected = state === 'connected';
    if (state === 'connected') {
      this.bannerDismissed = false;
    }
    const titles = {
      connected: 'Connected',
      reconnecting: 'Reconnecting...',
      disconnected: 'Disconnected',
      error: 'Connection failed'
    };
    this.connectionTitle = titles[state] || state;
  },

  showBanner({ type, message, showRetry }) {
    const classes = {
      warning: 'error-banner--warning',
      error: 'error-banner--error',
      info: 'error-banner--info'
    };
    const icons = {
      warning: '⚠',
      error: '✕',
      info: 'ℹ'
    };
    this.banner = {
      visible: true,
      className: classes[type] || classes.warning,
      icon: icons[type] || icons.warning,
      message: message || 'Something went wrong',
      showRetry: Boolean(showRetry)
    };
  },

  hideBanner() {
    this.banner.visible = false;
  },

  dismissBanner() {
    this.bannerDismissed = true;
    this.hideBanner();
  },

  retrySSE() {
    this.hideBanner();
    this.setConnectionState('reconnecting');
    this.sseConnection?.retry();
  },

  handleSSEBanner(payload) {
    if (!payload || payload.type === 'hide') {
      this.hideBanner();
      return;
    }

    if (payload.type === 'reconnecting') {
      if (this.bannerDismissed) return;
      this.showBanner({
        type: 'warning',
        message: 'Connection lost · Reconnecting...',
        showRetry: false
      });
      return;
    }

    if (payload.type === 'retry') {
      const ago = payload.lastDataTime ? this.formatTimeAgo(payload.lastDataTime) : 'unknown';
      this.showBanner({
        type: 'warning',
        message: `Connection lost · Last data: ${ago}`,
        showRetry: true
      });
    }
  },

  formatTimeAgo(date) {
    const seconds = Math.floor((Date.now() - date.getTime()) / 1000);
    if (seconds < 0) return '0s ago';
    if (seconds < 60) return `${seconds}s ago`;
    if (seconds < 3600) return `${Math.floor(seconds / 60)}m ago`;
    return `${Math.floor(seconds / 3600)}h ago`;
  },

  formatRelativeTime(iso) {
    if (!iso) return 'never';
    const diff = Date.now() - new Date(iso).getTime();
    const hours = Math.floor(diff / 3600000);
    if (hours < 1) return 'just now';
    if (hours < 24) return hours + 'h ago';
    const days = Math.floor(hours / 24);
    return days + 'd ago';
  },

  // View switching
  switchView(view) {
    this.currentView = view;
    if (view === 'projects') {
      this.fetchProjects();
    }
    if (view === 'history') {
      this.initHistoryChart();
      this.fetchProjects(); // Ensure projects dropdown is populated
      this.updateHistory();
    }
  },

  async fetchProjects() {
    try {
      const res = await fetch('/api/projects');
      this.projects = await res.json();
    } catch (err) {
      console.error('Failed to fetch projects:', err);
    }
  },

  selectProject(name) {
    this.selectedProject = name;
    // Will be enhanced in later phases
    console.log('Selected project:', name);
  },

  // === Phase 5: History Chart Methods ===
  initHistoryChart() {
    if (!this.historyChart) {
      this.historyChart = new HistoryChart('history-chart');
    }
  },

  setHistoryDays(days) {
    this.historyDays = days;
    this.updateHistory();
  },

  async updateHistory() {
    try {
      const endpoint = this.historyProject
        ? `/api/projects/${encodeURIComponent(this.historyProject)}/history?days=${this.historyDays}`
        : `/api/totals/history?days=${this.historyDays}`;

      const res = await fetch(endpoint);
      this.historyData = await res.json();

      if (this.historyChart) {
        this.historyChart.setData(this.historyData);
      }

      this.updateHistorySummary();
    } catch (err) {
      console.error('Failed to fetch history:', err);
    }
  },

  updateHistorySummary() {
    const data = this.historyData || [];
    const totalCost = data.reduce((sum, d) => sum + (d.cost || 0), 0);
    const totalSessions = data.reduce((sum, d) => sum + (d.sessions || 0), 0);
    const avgCost = data.length > 0 ? totalCost / data.length : 0;

    this.historySummary = {
      totalCost: totalCost,
      totalSessions: totalSessions,
      avgCost: avgCost
    };
  },

  // === Phase 4: Agent Tree Methods ===
  get computedAgentTree() {
    return this.buildAgentTree(this.agentTree);
  },

  buildAgentTree(agents) {
    if (!agents || agents.length === 0) return [];

    // Create lookup map
    const map = new Map();
    agents.forEach(a => {
      map.set(a.id, { ...a, children: [] });
    });

    // Build hierarchy
    const roots = [];
    for (const agent of map.values()) {
      const parentId = agent.parent_id || agent.parentId;
      if (parentId && map.has(parentId)) {
        map.get(parentId).children.push(agent);
      } else {
        roots.push(agent);
      }
    }

    // Sort children by start time
    const sortChildren = (node) => {
      node.children.sort((a, b) => {
        const aTime = new Date(a.started_at || a.startedAt || 0);
        const bTime = new Date(b.started_at || b.startedAt || 0);
        return aTime - bTime;
      });
      node.children.forEach(sortChildren);
    };
    roots.forEach(sortChildren);

    return roots;
  },

  toggleAgent(agentId) {
    this.expandedAgents[agentId] = !this.expandedAgents[agentId];
  },

  expandAllAgents() {
    const setAll = (nodes, expanded) => {
      nodes.forEach(node => {
        this.expandedAgents[node.id] = expanded;
        if (node.children) setAll(node.children, expanded);
      });
    };
    this.allAgentsExpanded = !this.allAgentsExpanded;
    setAll(this.computedAgentTree, this.allAgentsExpanded);
  },

  getModelClass(model) {
    if (!model) return 'unknown';
    if (model.includes('opus')) return 'opus';
    if (model.includes('sonnet')) return 'sonnet';
    if (model.includes('haiku')) return 'haiku';
    return 'other';
  },

  getModelShort(model) {
    if (!model) return '?';
    if (model.includes('opus')) return 'opus';
    if (model.includes('sonnet')) return 'sonnet';
    if (model.includes('haiku')) return 'haiku';
    return model.split('-')[0] || '?';
  },

  // Cleanup
  destroy() {
    this.sseConnection?.close();
    if (this.chartManager) {
      this.chartManager.destroy();
    }
    if (this.historyChart) {
      this.historyChart.destroy();
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
