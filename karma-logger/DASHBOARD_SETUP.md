# Karma Logger Dashboard Setup

## Overview

Karma Logger provides two dashboard interfaces for visualizing Claude Code session metrics:

1. **TUI Dashboard** — Terminal-based interface using Ink (React for CLI)
2. **Web Dashboard** — Browser-based interface with real-time updates via SSE

---

## Quick Start

### TUI Dashboard (Terminal)

```bash
# Launch interactive TUI dashboard
karma watch --ui

# With project filter
karma watch --ui --project my-project

# Compact mode (minimal display)
karma watch --compact
```

**Keyboard Shortcuts:**
| Key | Action |
|-----|--------|
| `q` | Quit dashboard |
| `r` | Refresh metrics |
| `t` | Toggle agent tree |
| `h` | Show help |

### Web Dashboard (Browser)

```bash
# Launch web dashboard at localhost:3333
karma dashboard

# Custom port
karma dashboard --port 8080

# Disable auto-open browser (browser won't auto-open)
karma dashboard --no-open

# Enable radio agent coordination
karma dashboard --radio
```

---

## Architecture

### TUI Dashboard

```
src/tui/
├── App.tsx                 # Main Ink application
├── index.ts                # Entry point (startTUI)
├── components/
│   ├── MetricsCard.tsx     # Token/cost display boxes
│   ├── AgentTree.tsx       # Hierarchical agent view
│   ├── Sparkline.tsx       # ASCII token flow chart
│   └── StatusBar.tsx       # Keyboard hints footer
├── hooks/
│   ├── useMetrics.ts       # Subscribe to MetricsAggregator
│   ├── useKeyboard.ts      # Input handling
│   ├── useAgentTree.ts     # Tree data processing
│   └── useTokenFlow.ts     # Sparkline data buffer
├── context/
│   └── AggregatorContext.tsx  # React context for aggregator
└── utils/
    └── format.ts           # Number/cost formatting
```

### Web Dashboard

```
src/dashboard/
├── server.ts               # Hono HTTP server
├── sse.ts                  # Server-Sent Events manager
├── api.ts                  # REST API routes
├── index.ts                # Entry point (startServer)
└── public/
    ├── index.html          # Single-page app
    ├── style.css           # Pico CSS + dark theme
    └── app.js              # Petite-Vue + uPlot
```

---

## Dependencies

### TUI Dependencies

```json
{
  "ink": "^5.2.1",
  "ink-spinner": "^5.0.0",
  "@inkjs/ui": "^2.0.0",
  "asciichart": "^1.5.25"
}
```

### Web Dependencies

```json
{
  "hono": "^4.11.3"
}
```

**Client-side (CDN, no install required):**
- [Petite-Vue](https://unpkg.com/petite-vue@0.4.1) — Reactive UI
- [uPlot](https://unpkg.com/uplot@1.6.30) — Time-series charts
- [Pico CSS](https://unpkg.com/@picocss/pico@2) — Minimal styling

---

## API Endpoints

### Core Metrics Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/` | GET | Dashboard HTML |
| `/events` | GET | SSE stream for real-time updates |
| `/api/session` | GET | Current session metrics |
| `/api/session/:id` | GET | Specific session by ID |
| `/api/sessions` | GET | All session history |
| `/api/totals` | GET | Aggregate totals |
| `/api/health` | GET | Health check |

### Radio Agent Coordination Endpoints (--radio flag)

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/radio/agents` | GET | All agent statuses |
| `/api/radio/agent/:id` | GET | Specific agent status |
| `/api/radio/session/:id/tree` | GET | Agent hierarchy tree for session |

---

## SSE Events

The `/events` endpoint streams these event types:

```javascript
// Initial state on connection
event: init
data: {"tokensIn":0,"tokensOut":0,"cost":0,"agents":[]}

// Metrics update (on new log entry)
event: metrics
data: {"tokensIn":1234,"tokensOut":567,"cost":0.05,...}

// New session started
event: session:start
data: {"sessionId":"abc123","projectName":"my-project"}

// Agent spawned
event: agent:spawn
data: {"agentId":"xyz","parentId":"abc","model":"haiku"}
```

---

## Radio Agent Coordination

When `--radio` or `--persist-radio` flags are enabled:

1. **Radio Socket Server** starts at `/tmp/karma-radio.sock`
2. **Subagent Watcher** auto-starts to bridge Claude Code's JSONL files → Radio
3. Agent statuses flow to frontend via SSE (`agent:status`, `agent:progress` events)
4. Hierarchical agent tree visualized in Agent Status Panel

### Usage

```bash
# Enable radio for real-time agent tracking
karma dashboard --radio

# Enable radio with persistent cache (WAL + snapshots)
karma dashboard --persist-radio
```

See [FRONTEND_RADIO_GUIDE.md](docs/FRONTEND_RADIO_GUIDE.md) for detailed radio integration documentation.

---

## Configuration

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `KARMA_PORT` | `3333` | Web dashboard port |
| `KARMA_HOST` | `localhost` | Web dashboard host |
| `DEBUG` | (unset) | Enable debug logs: `DEBUG=subagent-watcher` for watcher logs |

### CLI Options

```bash
# TUI options
karma watch --ui [options]
  -p, --project <name>      Filter by project
  -c, --compact             Compact display mode
  --activity-only           Show only active sessions

# Web options
karma dashboard [options]
  -p, --port <number>       Port (default: 3333)
  --no-open                 Don't auto-open browser
  --radio                   Enable radio agent coordination
  --persist-radio           Enable persistent radio cache (WAL + snapshots)
```

---

## Troubleshooting

### TUI not rendering correctly

1. Ensure terminal supports 256 colors
2. Try a different terminal emulator
3. Check `TERM` environment variable

### Web dashboard not loading

1. Check if port is already in use: `lsof -i :3333`
2. Try different port: `karma dashboard --port 8080`
3. Check firewall settings

### SSE connection dropping

1. Browser DevTools > Network > filter by `events`
2. Check for proxy/load balancer timeouts
3. SSE auto-reconnects after 3 seconds

---

## Development

### Running Tests

```bash
cd karma-logger
npm test -- --grep "dashboard"
npm test -- --grep "tui"
npm test -- --grep "sse"
```

### Building

```bash
npm run build
```

### Local Development

```bash
# Watch mode for TUI development
npm run dev

# Test web dashboard
karma dashboard --port 3333
```
