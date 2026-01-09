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

class LoadingState {
  constructor(containerId) {
    this.container = document.getElementById(containerId);
  }

  setLoading(isLoading) {
    if (!this.container) return;
    this.container.classList.toggle('is-loading', Boolean(isLoading));
  }

  async transition(render) {
    if (!this.container) {
      render?.();
      return;
    }
    this.container.classList.add('is-transitioning');
    await new Promise(r => setTimeout(r, 200));
    render?.();
    this.container.classList.remove('is-transitioning');
  }
}

class MetricsBuffer {
  constructor(maxSize = 10) {
    this.maxSize = maxSize;
    this.buffers = {
      tokensIn: [],
      tokensOut: [],
      cost: [],
      agentCount: []
    };
  }

  push(metric, value) {
    if (!this.buffers[metric]) return;
    const v = typeof value === 'number' && Number.isFinite(value) ? value : 0;
    this.buffers[metric].push(v);
    if (this.buffers[metric].length > this.maxSize) {
      this.buffers[metric].shift();
    }
  }

  get(metric) {
    return this.buffers[metric] || [];
  }
}

function calculateTrend(current, history) {
  if (!history || history.length < 2) return null;
  const prev = history.slice(0, -1);
  if (prev.length === 0) return null;

  const avg = prev.reduce((a, b) => a + b, 0) / prev.length;
  if (!Number.isFinite(avg) || avg === 0) return null;

  const pct = ((current - avg) / avg) * 100;
  if (!Number.isFinite(pct)) return null;

  return {
    value: pct,
    direction: pct >= 0 ? 'up' : 'down',
    formatted: `${pct >= 0 ? '+' : ''}${pct.toFixed(0)}%`
  };
}

function buildConnector(depth, isLast, parentConnectors) {
  if (depth === 0) return isLast ? '└──' : '├──';

  let prefix = '';
  for (let i = 0; i < depth; i++) {
    prefix += parentConnectors[i] ? '│   ' : '    ';
  }
  return prefix + (isLast ? '└──' : '├──');
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
  projectsLoading: false,
  dateRange: 30,
  expandedAgents: {},
  allAgentsExpanded: false,
  
  // === Live View Project/Session State ===
  liveProject: '', // Selected project for live view (empty = all)
  liveSessionId: null, // Currently viewing session
  projectSessions: [], // Sessions for selected project
  
  // === Phase 1: Active Sessions Panel State ===
  activeSessions: [],        // Sessions with isRunning = true
  completedSessions: [],     // Sessions with isRunning = false
  sessionFilter: 'all',      // all | active | completed
  sessionDurations: {},      // { sessionId: durationMs } - live counters
  durationInterval: null,    // Interval handle for duration updates

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
  // Session-specific metrics (separate from aggregate)
  sessionMetrics: null,
  // Metrics context: 'aggregate' (all/project) or 'session' (single session selected)
  metricsContext: 'aggregate',
  // Phase 4: sparkline + trend state
  metricsBuffer: null,
  sparklines: null,
  trends: {
    tokensIn: { text: '—', cls: 'trend--neutral' },
    tokensOut: { text: '—', cls: 'trend--neutral' },
    cost: { text: '—', cls: 'trend--neutral' },
    agentCount: { text: '—', cls: 'trend--neutral' }
  },
  agentTree: [],
  agentsLoading: true,
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
  historyLoading: false,
  historySummary: {
    totalCost: 0,
    totalSessions: 0,
    avgCost: 0
  },
  loadingStates: null,

  // Lifecycle
  init() {
    // Initialize chart manager with configurable retention
    this.chartManager = new ChartManager('chart', {
      maxDataPoints: window.CHART_DATA_RETENTION_POINTS || 3600
    });
    this.metricsBuffer = new MetricsBuffer(10);
    this.sparklines = {};
    this.initSparklines();

    // Phase 6: state managers for subtle transitions/loading opacity
    this.loadingStates = {
      projects: new LoadingState('project-list'),
      chart: new LoadingState('chart')
    };

    // Restore saved project preference for live view
    this.liveProject = localStorage.getItem('karma-live-project') || '';

    // Fetch projects first (needed for live view dropdown)
    this.fetchProjects().then(() => {
      // If saved project no longer exists, clear it
      if (this.liveProject && !this.projects.find(p => p.projectName === this.liveProject)) {
        this.liveProject = '';
        localStorage.removeItem('karma-live-project');
      }
    });

    this.connectSSE({ resetRetries: true });
    this.fetchInitialData();
  },

  // Phase 4: Sparkline initialization and updates
  initSparklines() {
    const Sparkline = window.Sparkline;
    if (!Sparkline) return;

    const COLORS = {
      tokensIn: { lineColor: '#22c55e', fillColor: 'rgba(34, 197, 94, 0.2)' },
      tokensOut: { lineColor: '#3b82f6', fillColor: 'rgba(59, 130, 246, 0.2)' },
      cost: { lineColor: '#10b981', fillColor: 'rgba(16, 185, 129, 0.2)' },
      agentCount: { lineColor: '#f59e0b', fillColor: 'rgba(245, 158, 11, 0.2)' }
    };

    const canvases = [
      { key: 'tokensIn', id: 'tokens-in-sparkline' },
      { key: 'tokensOut', id: 'tokens-out-sparkline' },
      { key: 'cost', id: 'cost-sparkline' },
      { key: 'agentCount', id: 'agents-sparkline' }
    ];

    for (const { key, id } of canvases) {
      const canvas = document.getElementById(id);
      if (!canvas) continue;
      const spark = new Sparkline(canvas, COLORS[key] || {});
      this.sparklines[key] = spark;
      spark.setData([]);
    }
  },

  updateSparklineAndTrend(key, current) {
    if (!this.metricsBuffer) return;

    const history = this.metricsBuffer.get(key);
    const trend = calculateTrend(current, history);

    if (!trend) {
      this.trends[key] = { text: '—', cls: 'trend--neutral' };
    } else {
      this.trends[key] = {
        text: trend.formatted,
        cls: trend.direction === 'up' ? 'trend--up' : 'trend--down'
      };
    }

    const spark = this.sparklines?.[key];
    if (spark) spark.setData(history);
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

        if (data.sessions) {
          // Categorize sessions into active/completed
          this.categorizeSessions(data.sessions);
          
          // Start duration counters
          this.startDurationCounters();
          
          // Filter sessions by project if set
          let sessions = data.sessions;
          if (this.liveProject) {
            sessions = sessions.filter(s => s.projectName === this.liveProject);
          }
          
          this.sessions = data.sessions; // Keep all sessions
          this.projectSessions = sessions; // Filtered for live view
          
          if (sessions.length > 0) {
            // Use the most recent session for the selected project
            const targetSession = sessions[0];
            this.sessionId = targetSession.id;
            this.liveSessionId = targetSession.id;
            // Fetch agents for this session
            this.fetchSessionData(targetSession.id);
          } else {
            this.liveSessionId = null;
            this.agentsLoading = false;
          }
        }

        if (data.metrics) {
          this.updateMetrics(data.metrics);
          // Phase 4: seed sparklines with initial totals once
          this.metricsBuffer?.push('tokensIn', data.metrics.tokensIn ?? this.metrics.tokensIn);
          this.metricsBuffer?.push('tokensOut', data.metrics.tokensOut ?? this.metrics.tokensOut);
          this.metricsBuffer?.push('cost', data.metrics.cost ?? this.metrics.cost);
          this.metricsBuffer?.push('agentCount', data.metrics.agents ?? this.metrics.agents);
          this.updateSparklineAndTrend('tokensIn', this.metrics.tokensIn);
          this.updateSparklineAndTrend('tokensOut', this.metrics.tokensOut);
          this.updateSparklineAndTrend('cost', this.metrics.cost);
          this.updateSparklineAndTrend('agentCount', this.metrics.agents);
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
        // Phase 4: buffer + sparkline updates only for real-time events
        this.metricsBuffer?.push('tokensIn', data.tokensIn ?? this.metrics.tokensIn);
        this.metricsBuffer?.push('tokensOut', data.tokensOut ?? this.metrics.tokensOut);
        this.metricsBuffer?.push('cost', data.cost ?? this.metrics.cost);
        this.metricsBuffer?.push('agentCount', data.agents ?? this.metrics.agents);

        this.updateSparklineAndTrend('tokensIn', this.metrics.tokensIn);
        this.updateSparklineAndTrend('tokensOut', this.metrics.tokensOut);
        this.updateSparklineAndTrend('cost', this.metrics.cost);
        this.updateSparklineAndTrend('agentCount', this.metrics.agents);

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
        this.agentsLoading = false;
      } catch (err) {
        console.error('Failed to parse agents event:', err);
      }
    });

    // Handle session start
    es.addEventListener('session:start', (event) => {
      markData();
      try {
        const data = JSON.parse(event.data);
        
        // Add to active sessions
        const newSession = {
          id: data.sessionId,
          projectName: data.projectName,
          startedAt: data.startedAt,
          isRunning: true,
          status: 'active',
          cost: 0,
          agentCount: 0,
          tokensIn: 0,
          tokensOut: 0
        };
        
        // Add to active sessions and start tracking duration
        this.activeSessions.unshift(newSession);
        const started = new Date(data.startedAt).getTime();
        this.sessionDurations[data.sessionId] = Date.now() - started;
        
        // Check if this session matches our project filter
        const matchesFilter = !this.liveProject || data.projectName === this.liveProject;
        
        if (matchesFilter) {
          this.sessionId = data.sessionId;
          this.liveSessionId = data.sessionId;
          // Fetch agents for this session
          this.fetchSessionData(data.sessionId);
        }
        
        // Refresh the sessions list
        this.fetchProjectSessions();
      } catch (err) {
        console.error('Failed to parse session:start event:', err);
      }
    });

    // Handle session end (Phase 1)
    es.addEventListener('session:end', (event) => {
      markData();
      try {
        const data = JSON.parse(event.data);
        this.markSessionCompleted(data.sessionId, data.endedAt, data.finalCost);
      } catch (err) {
        console.error('Failed to parse session:end event:', err);
      }
    });

    // Handle agent spawn (Phase 3 prep)
    es.addEventListener('agent:spawn', (event) => {
      markData();
      try {
        const data = JSON.parse(event.data);

        // Only process if viewing this session
        if (data.sessionId !== this.liveSessionId) return;

        // Find if agent already exists in tree
        const existing = this.agentTree.find(a => a.id === data.agentId);
        if (existing) return;

        // Add new agent with animation flag
        const newAgent = {
          id: data.agentId,
          parent_id: data.parentId,
          type: data.type,
          model: data.model,
          started_at: data.spawnedAt,
          isNew: true,
          metrics: { cost: { total: 0 }, tokensIn: 0, tokensOut: 0 }
        };

        this.agentTree.push(newAgent);

        // Clear animation flag after 2s
        setTimeout(() => {
          const agent = this.agentTree.find(a => a.id === data.agentId);
          if (agent) agent.isNew = false;
        }, 2000);
      } catch (err) {
        console.error('Failed to parse agent:spawn event:', err);
      }
    });

    // Phase 3: Handle agent status updates from walkie-talkie
    es.addEventListener('agent:status', (event) => {
      markData();
      try {
        const data = JSON.parse(event.data);
        this.handleAgentStatus(data.agentId, data.status);
      } catch (err) {
        console.error('Failed to parse agent:status:', err);
      }
    });

    // Phase 3: Handle agent progress updates from walkie-talkie
    es.addEventListener('agent:progress', (event) => {
      markData();
      try {
        const data = JSON.parse(event.data);
        this.handleAgentProgress(data.agentId, data.progress);
      } catch (err) {
        console.error('Failed to parse agent:progress:', err);
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
          // Store session-specific metrics separately
          this.sessionMetrics = {
            tokensIn: data.metrics.tokensIn || 0,
            tokensOut: data.metrics.tokensOut || 0,
            cost: data.metrics.cost || 0,
            cacheRead: data.metrics.cacheRead || 0,
            cacheCreation: data.metrics.cacheCreation || 0,
            toolCalls: data.metrics.toolCalls || 0,
            sessions: 1,
            agents: data.agents?.length || 0
          };
          // Switch to session context
          this.metricsContext = 'session';
        }
        if (data.agents) {
          this.agentTree = data.agents;
          this.agentsLoading = false;
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
    if (view === 'live') {
      // Refresh live view data
      this.refreshLiveView();
    }
    if (view === 'projects') {
      this.fetchProjects();
    }
    if (view === 'history') {
      this.initHistoryChart();
      this.fetchProjects(); // Ensure projects dropdown is populated
      this.updateHistory();
    }
  },

  // === Live View Project/Session Methods ===
  onLiveProjectChange() {
    // Save preference
    if (this.liveProject) {
      localStorage.setItem('karma-live-project', this.liveProject);
    } else {
      localStorage.removeItem('karma-live-project');
    }
    
    // Refresh the live view with new project filter
    this.refreshLiveView();
  },

  async refreshLiveView() {
    // Fetch sessions filtered by project
    await this.fetchProjectSessions();
    
    // If we have sessions, select the most recent one
    if (this.projectSessions.length > 0) {
      const mostRecent = this.projectSessions[0];
      this.selectLiveSession(mostRecent.id);
    } else {
      // No sessions for this project
      this.liveSessionId = null;
      this.agentTree = [];
      this.agentsLoading = false;
      this.resetMetrics();
    }
  },

  async fetchProjectSessions() {
    try {
      let url = '/api/sessions?limit=20';
      const res = await fetch(url);
      const data = await res.json();
      let sessions = data.sessions || [];
      
      // Filter by project if selected
      if (this.liveProject) {
        sessions = sessions.filter(s => s.projectName === this.liveProject);
      }
      
      this.projectSessions = sessions;
      this.sessions = sessions; // Also update the main sessions list
    } catch (err) {
      console.error('Failed to fetch project sessions:', err);
      this.projectSessions = [];
    }
  },

  selectLiveSession(sessionId) {
    this.liveSessionId = sessionId;
    this.fetchSessionData(sessionId);
  },

  isSessionActive(session) {
    // Consider a session active if it had activity in the last 5 minutes
    if (!session.lastActivity) return false;
    const lastActivity = new Date(session.lastActivity);
    const fiveMinutesAgo = Date.now() - (5 * 60 * 1000);
    return lastActivity.getTime() > fiveMinutesAgo;
  },

  resetMetrics() {
    this.metrics = {
      tokensIn: 0,
      tokensOut: 0,
      cost: 0,
      cacheRead: 0,
      cacheCreation: 0,
      toolCalls: 0,
      sessions: 0,
      agents: 0
    };
    // Reset session context
    this.sessionMetrics = null;
    this.metricsContext = 'aggregate';
  },

  // === Phase 1: Session Lifecycle Methods ===
  
  // Computed: filtered sessions based on sessionFilter
  get filteredSessions() {
    if (this.sessionFilter === 'active') return this.activeSessions;
    if (this.sessionFilter === 'completed') return this.completedSessions;
    return [...this.activeSessions, ...this.completedSessions];
  },

  // Computed: sessions to display in stats (respects project filter)
  get displaySessions() {
    // When a project is selected, show only that project's sessions
    if (this.liveProject) {
      return this.sessions.filter(s => s.projectName === this.liveProject);
    }
    // Otherwise show all sessions
    return this.sessions;
  },

  // Computed: metrics to display (session-specific or aggregate)
  get displayMetrics() {
    // When a specific session is selected and we have its metrics, show those
    if (this.metricsContext === 'session' && this.sessionMetrics) {
      return this.sessionMetrics;
    }
    // Otherwise show aggregate metrics
    return this.metrics;
  },

  // Computed: label for metrics context
  get metricsLabel() {
    if (this.metricsContext === 'session' && this.liveSessionId) {
      return 'session';
    }
    if (this.liveProject) {
      return 'project';
    }
    return 'total';
  },

  // Categorize sessions into active/completed
  categorizeSessions(sessions) {
    this.activeSessions = sessions.filter(s => s.isRunning);
    this.completedSessions = sessions.filter(s => !s.isRunning);
    
    // Update durations for active sessions
    for (const session of this.activeSessions) {
      if (!this.sessionDurations[session.id]) {
        const started = new Date(session.startedAt).getTime();
        this.sessionDurations[session.id] = Date.now() - started;
      }
    }
  },

  // Start duration counters for active sessions
  startDurationCounters() {
    if (this.durationInterval) {
      clearInterval(this.durationInterval);
    }
    
    this.durationInterval = setInterval(() => {
      const now = Date.now();
      for (const session of this.activeSessions) {
        const started = new Date(session.startedAt).getTime();
        this.sessionDurations[session.id] = now - started;
      }
    }, 1000);
  },

  // Stop duration counters
  stopDurationCounters() {
    if (this.durationInterval) {
      clearInterval(this.durationInterval);
      this.durationInterval = null;
    }
  },

  // Format duration in ms to human readable
  formatDuration(ms) {
    if (!ms || ms < 0) return '0s';
    const seconds = Math.floor(ms / 1000);
    if (seconds < 60) return `${seconds}s`;
    const minutes = Math.floor(seconds / 60);
    const secs = seconds % 60;
    if (minutes < 60) return `${minutes}m ${secs.toString().padStart(2, '0')}s`;
    const hours = Math.floor(minutes / 60);
    const mins = minutes % 60;
    return `${hours}h ${mins.toString().padStart(2, '0')}m`;
  },

  // Get duration for a session
  getSessionDuration(sessionId) {
    return this.sessionDurations[sessionId] || 0;
  },

  // Handle session filter change
  onSessionFilterChange() {
    // Filter change just updates the view via computed property
  },

  // Move session from active to completed
  markSessionCompleted(sessionId, endedAt, finalCost) {
    const idx = this.activeSessions.findIndex(s => s.id === sessionId);
    if (idx !== -1) {
      const session = this.activeSessions.splice(idx, 1)[0];
      session.isRunning = false;
      session.endedAt = endedAt;
      session.cost = finalCost;
      session.status = 'ended';
      this.completedSessions.unshift(session);
      
      // Remove from duration tracking
      delete this.sessionDurations[sessionId];
    }
  },

  async fetchProjects() {
    try {
      this.projectsLoading = true;
      this.loadingStates?.projects?.setLoading(true);
      const res = await fetch('/api/projects');
      const next = await res.json();
      await this.loadingStates?.projects?.transition(() => {
        this.projects = next;
      });
    } catch (err) {
      console.error('Failed to fetch projects:', err);
    } finally {
      this.projectsLoading = false;
      this.loadingStates?.projects?.setLoading(false);
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
      this.historyLoading = true;
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
    } finally {
      this.historyLoading = false;
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
  get agentRoots() {
    return this.buildAgentTree(this.agentTree);
  },

  get agentRows() {
    const roots = this.agentRoots || [];
    if (roots.length === 0) return [];

    const rows = [];

    const walk = (nodes, depth, parentConnectors) => {
      nodes.forEach((node, index) => {
        const isLast = index === nodes.length - 1;
        const connector = buildConnector(depth, isLast, parentConnectors);
        const hasChildren = Boolean(node.children && node.children.length > 0);
        const isExpanded = Boolean(this.expandedAgents[node.id]);
        const isRunning = !(node.ended_at || node.endedAt);

        const costCents = node.metrics?.cost?.total ?? node.cost_total ?? 0;
        const tokensIn = node.metrics?.tokensIn ?? node.tokens_in ?? 0;
        const tokensOut = node.metrics?.tokensOut ?? node.tokens_out ?? 0;
        const tokensTotal = tokensIn + tokensOut;

        rows.push({
          id: node.id,
          depth,
          connector,
          indicator: hasChildren ? '◈' : '◇',
          hasChildren,
          isExpanded,
          isRunning,
          isNew: node.isNew || false, // Animation flag from spawn event
          // Phase 2: Status display
          statusIcon: isRunning ? '⟳' : '✓',
          statusText: isRunning ? 'running' : 'done',
          modelClass: this.getModelClass(node.model),
          modelText: this.getModelShort(node.model),
          typeText: node.type || node.agent_type || 'unknown',
          costCents,
          tokensTotal
        });

        const childConnectors = [...parentConnectors];
        childConnectors[depth] = !isLast;

        if (hasChildren && isExpanded) {
          walk(node.children, depth + 1, childConnectors);
        }
      });
    };

    walk(roots, 0, []);
    return rows;
  },

  get agentExpandableCount() {
    const roots = this.agentRoots || [];
    let total = 0;
    const walk = (nodes) => {
      nodes.forEach(n => {
        if (n.children && n.children.length > 0) total += 1;
        if (n.children && n.children.length > 0) walk(n.children);
      });
    };
    walk(roots);
    return total;
  },

  get agentExpandedCount() {
    const roots = this.agentRoots || [];
    let expanded = 0;
    const walk = (nodes) => {
      nodes.forEach(n => {
        const hasChildren = Boolean(n.children && n.children.length > 0);
        if (hasChildren && this.expandedAgents[n.id]) expanded += 1;
        if (hasChildren) walk(n.children);
      });
    };
    walk(roots);
    return expanded;
  },

  // Phase 2: Running agent count
  get runningAgentCount() {
    return this.agentRows.filter(r => r.isRunning).length;
  },

  // Phase 2: Total agent count
  get totalAgentCount() {
    return this.agentRows.length;
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
    setAll(this.agentRoots, this.allAgentsExpanded);
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

  // Phase 5: formatting helpers
  formatTokens(tokens) {
    const t = typeof tokens === 'number' ? tokens : 0;
    if (t >= 1_000_000) return (t / 1_000_000).toFixed(1) + 'M';
    if (t >= 1_000) return (t / 1_000).toFixed(0) + 'K';
    return String(t);
  },

  formatCostCompact(cents) {
    const c = typeof cents === 'number' ? cents : 0;
    return '$' + (c / 100).toFixed(2);
  },

  // === Phase 3: Agent Status Panel Methods (walkie-talkie bridge) ===

  handleAgentStatus(agentId, status) {
    console.log(`Agent ${agentId} status: ${status.state}`);
    this.agentStatuses = this.agentStatuses || {};
    this.agentStatuses[agentId] = status;
    this.renderAgentPanel();
  },

  handleAgentProgress(agentId, progress) {
    console.log(`Agent ${agentId} progress: ${progress.percent}%`);
    this.agentProgress = this.agentProgress || {};
    this.agentProgress[agentId] = progress;
    this.renderAgentPanel();
  },

  renderAgentPanel() {
    const panel = document.getElementById('agent-panel');
    const container = document.getElementById('agent-cards');

    if (!panel || !container) return;

    const statuses = this.agentStatuses || {};
    const progress = this.agentProgress || {};

    if (Object.keys(statuses).length === 0) {
      panel.classList.add('hidden');
      return;
    }

    panel.classList.remove('hidden');
    container.innerHTML = Object.entries(statuses)
      .map(([id, status]) => this.renderAgentCard(id, status, progress[id]))
      .join('');
  },

  renderAgentCard(agentId, status, progress) {
    const stateClass = `agent-state-${status.state}`;
    const progressBar = progress
      ? `<div class="progress-bar"><div class="progress-fill" style="width:${progress.percent}%"></div></div>`
      : '';

    return `
      <div class="agent-card ${stateClass}">
        <div class="agent-header">
          <span class="agent-id">${agentId}</span>
          <span class="agent-state">${status.state}</span>
        </div>
        ${status.message ? `<div class="agent-message">${status.message}</div>` : ''}
        ${progressBar}
        <div class="agent-meta">
          <span>${status.model || 'unknown'}</span>
          <span>${status.agentType || 'agent'}</span>
        </div>
      </div>
    `;
  },

  // Cleanup
  destroy() {
    this.sseConnection?.close();
    this.stopDurationCounters();
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
