# karma-logger

**Local metrics and cost tracking for Claude Code sessions.**

karma-logger is a CLI tool and dashboard that monitors Claude Code sessions in real-time, tracking token usage, costs, and tool activity. All data stays local on your machine in SQLite.

## Table of Contents

- [Features](#features)
- [Architecture Overview](#architecture-overview)
- [Tech Stack](#tech-stack)
- [Data Flow](#data-flow)
- [Installation](#installation)
- [Quick Start](#quick-start)
- [Commands](#commands)
- [Configuration](#configuration)
- [Project Structure](#project-structure)
- [Development](#development)
- [Testing](#testing)
- [License](#license)

---

## Features

- **Real-time metrics** - Track token usage and costs as you code with instant updates
- **Session history** - Browse and export past session data with filtering and sorting
- **Cost breakdown** - See detailed pricing by input, output, and cache tokens with custom pricing support
- **Agent tracking** - Visualize agent hierarchies and per-agent metrics in real-time
- **Multiple interfaces** - CLI, streaming watch mode, interactive TUI, and web dashboard
- **Offline-first** - All data stays local in SQLite with optional cloud sync
- **Extensible pricing** - Override model pricing via config files or environment variables
- **Walkie-Talkie IPC** - Unix socket-based inter-agent communication with:
  - Agent status tracking (pending/active/waiting/completed/failed/cancelled)
  - Progress reporting with tool names and percentages
  - Parent-child agent hierarchy coordination
  - Batch operations (wait for multiple agents, wait for all children)
  - JSON metadata for rich context sharing
  - Schema validation for structured data
- **Subagent monitoring** - Inference-based tracking of subagents via JSONL file polling
- **Persistent cache** - Optional WAL + snapshot persistence for agent state and metadata that survives restarts
- **Agent visualization** - ASCII tree view of agent hierarchies, status summaries, and relationship graphs

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              USER INTERFACES                                 │
├──────────────────┬──────────────────┬───────────────────┬───────────────────┤
│   CLI Commands   │  Streaming Watch │    TUI (Ink)      │  Web Dashboard    │
│  (status/report) │  (karma watch)   │  (karma watch -u) │ (karma dashboard) │
└────────┬─────────┴────────┬─────────┴─────────┬─────────┴─────────┬─────────┘
         │                  │                   │                   │
         │                  ▼                   ▼                   ▼
         │         ┌────────────────────────────────────────────────────────┐
         │         │                  MetricsAggregator                      │
         │         │  • In-memory session/agent metrics                      │
         │         │  • Activity buffer (ring buffer)                        │
         │         │  • Session lifecycle management                         │
         │         │  • EventEmitter for real-time updates                   │
         │         └────────────────────────────────────────────────────────┘
         │                              ▲
         │                              │ processEntry()
         │                              │ registerAgent()
         │         ┌────────────────────┴───────────────────────────────────┐
         │         │                    LogWatcher                           │
         │         │  • File system watcher (chokidar)                       │
         │         │  • Tails JSONL files for new entries                    │
         │         │  • Emits entry, session:start, agent:spawn events       │
         │         └────────────────────────────────────────────────────────┘
         │                              ▲
         │                              │ reads & tails
         ▼                              │
┌─────────────────┐            ┌────────┴────────────────────────────────────┐
│    KarmaDB      │◀───save────│           Claude Code Logs                  │
│   (SQLite)      │            │   ~/.claude/projects/<project>/*.jsonl      │
│                 │            │                                              │
│  • sessions     │            │  • Session files: <uuid>.jsonl               │
│  • agents       │            │  • Agent files: agent-<id>.jsonl             │
│  • activity     │            │  • Each line: JSON entry with usage data     │
│  • schema       │            └─────────────────────────────────────────────┘
└─────────────────┘

         │
         ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                            Web Dashboard                                     │
├─────────────────────────────────────────────────────────────────────────────┤
│  ┌─────────────┐    ┌─────────────┐    ┌─────────────────────────────────┐  │
│  │ Hono Server │───▶│  REST API   │───▶│   /api/session, /api/totals    │  │
│  │  (Node.js)  │    └─────────────┘    └─────────────────────────────────┘  │
│  │             │    ┌─────────────┐    ┌─────────────────────────────────┐  │
│  │             │───▶│  SSE Stream │───▶│   /events (real-time updates)   │  │
│  │             │    └─────────────┘    └─────────────────────────────────┘  │
│  │             │    ┌─────────────┐    ┌─────────────────────────────────┐  │
│  │             │───▶│   Static    │───▶│   HTML/CSS/JS frontend          │  │
│  └─────────────┘    └─────────────┘    └─────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Component Responsibilities

| Component | File(s) | Purpose |
|-----------|---------|---------|
| **Parser** | `parser.ts` | Parse JSONL log files, extract token usage, tool calls |
| **Discovery** | `discovery.ts` | Find Claude logs directory, enumerate sessions and agents |
| **Watcher** | `watcher.ts` | Watch for file changes, tail new entries in real-time |
| **Aggregator** | `aggregator.ts` | Accumulate metrics, manage session lifecycle, emit events |
| **Cost** | `cost.ts` | Model pricing tables, cost calculation, pricing overrides |
| **Database** | `db.ts` | SQLite persistence for sessions, agents, activity |
| **Converters** | `converters.ts` | Type-safe conversion between in-memory and DB formats |
| **CLI** | `cli.ts` | Commander.js-based CLI with subcommands |
| **TUI** | `tui/*.tsx` | Interactive terminal UI built with Ink (React) |
| **Dashboard** | `dashboard/*` | Web server with REST API and SSE streaming |

---

## Tech Stack

### Runtime & Language

| Technology | Version | Purpose |
|------------|---------|---------|
| **Node.js** | ≥20.0.0 | JavaScript runtime |
| **TypeScript** | ^5.9 | Type-safe development |
| **ESM** | ES2022 | Native ES modules |

### Core Dependencies

| Package | Purpose |
|---------|---------|
| **commander** | CLI argument parsing and subcommands |
| **chalk** | Terminal styling and colors |
| **chokidar** | Cross-platform file system watching |
| **better-sqlite3** | Fast, synchronous SQLite bindings |

### Web Dashboard

| Package | Purpose |
|---------|---------|
| **hono** | Lightweight web framework (Express-like) |
| **@hono/node-server** | Node.js adapter for Hono |

### Terminal UI

| Package | Purpose |
|---------|---------|
| **ink** | React for interactive CLIs |
| **@inkjs/ui** | Pre-built Ink components |
| **react** | Component framework for TUI |
| **ink-spinner** | Loading spinners for TUI |
| **asciichart** | ASCII charts for sparklines |

### Development

| Package | Purpose |
|---------|---------|
| **vitest** | Fast unit testing framework |
| **tsx** | TypeScript execution without build step |
| **ink-testing-library** | Testing utilities for Ink components |

---

## Data Flow

### 1. Log Discovery & Parsing

```
Claude Code writes JSONL logs:
~/.claude/projects/<encoded-path>/<session-uuid>.jsonl

Each line is a JSON object:
{
  "type": "assistant",
  "uuid": "entry-uuid",
  "sessionId": "session-uuid",
  "timestamp": "2026-01-08T10:00:00Z",
  "message": {
    "model": "claude-sonnet-4-20250514",
    "content": [...],
    "usage": {
      "input_tokens": 1500,
      "output_tokens": 500,
      "cache_read_input_tokens": 1000,
      "cache_creation_input_tokens": 200
    }
  }
}
```

### 2. Real-Time Watching Pipeline

```
                    File Change Event
                          │
                          ▼
┌─────────────────────────────────────────┐
│           LogWatcher (watcher.ts)       │
│  1. Detects file change via chokidar    │
│  2. Reads new bytes since last position │
│  3. Parses JSON lines                   │
│  4. Emits 'entry' event per log entry   │
└─────────────────────────────────────────┘
                          │
                          ▼ entry event
┌─────────────────────────────────────────┐
│       MetricsAggregator (aggregator.ts) │
│  1. Updates session token counts        │
│  2. Calculates costs via cost.ts        │
│  3. Tracks tool usage                   │
│  4. Emits 'activity' for UI updates     │
└─────────────────────────────────────────┘
                          │
            ┌─────────────┴─────────────┐
            ▼                           ▼
┌───────────────────┐       ┌───────────────────┐
│   TUI/Watch CLI   │       │   Web Dashboard   │
│   Reads from      │       │   SSE broadcast   │
│   aggregator      │       │   to all clients  │
└───────────────────┘       └───────────────────┘
```

### 3. Persistence Flow

```
┌─────────────────────────────────────────┐
│          MetricsAggregator              │
│  In-memory SessionMetrics/AgentMetrics  │
└─────────────────────────────────────────┘
                    │
                    │ saveSessionMetrics()
                    │ saveAgentMetrics()
                    ▼
┌─────────────────────────────────────────┐
│          Converters (converters.ts)     │
│  • Set<string> → JSON array string      │
│  • Map<string, number> → JSON object    │
│  • Date → ISO 8601 string               │
│  • CostBreakdown → separate columns     │
└─────────────────────────────────────────┘
                    │
                    ▼
┌─────────────────────────────────────────┐
│          KarmaDB (db.ts)                │
│  SQLite database at ~/.karma/karma.db  │
│                                          │
│  Tables:                                 │
│  • sessions (metrics, costs, tools)     │
│  • agents (per-agent metrics)           │
│  • activity (tool call history)         │
│  • schema_version (migrations)          │
└─────────────────────────────────────────┘
```

### 4. Dashboard Data Flow

```
Browser connects to http://localhost:3333
                    │
                    ▼
┌───────────────────────────────────────────────┐
│          Hono Server (server.ts)              │
├───────────────────────────────────────────────┤
│ GET /                   → Static HTML                │
│ GET /events             → SSE stream                 │
├──────────────────────────────────────────────────────┤
│ Session APIs:                                        │
│ GET /api/session             → Current session       │
│ GET /api/session/:id         → Session by ID         │
│ GET /api/sessions            → Session list          │
├──────────────────────────────────────────────────────┤
│ Project APIs:                                        │
│ GET /api/projects            → List all projects     │
│ GET /api/projects/:name      → Project details       │
│ GET /api/projects/:name/history → Session history    │
├──────────────────────────────────────────────────────┤
│ Metrics APIs:                                        │
│ GET /api/totals              → Aggregate metrics     │
│ GET /api/totals/history      → Metrics over time     │
│ GET /api/health              → Health check          │
├──────────────────────────────────────────────────────┤
│ Radio APIs (Walkie-Talkie):                          │
│ GET /api/radio/agents        → All agent statuses    │
│ GET /api/radio/agent/:id     → Single agent status   │
│ GET /api/radio/session/:id/tree → Agent hierarchy    │
└───────────────────────────────────────────────┘
                    │
                    │ Real-time updates
                    ▼
┌───────────────────────────────────────────────┐
│          SSEManager (sse.ts)                  │
│  • Listens to LogWatcher events               │
│  • Broadcasts to all connected clients        │
│  • Events: init, metrics, agents, agent:spawn │
│    session:start, session:end, agent:status,  │
│    agent:progress                             │
└───────────────────────────────────────────────┘
```

---

## Installation

### From npm (when published)

```bash
npm install -g karma-logger
```

### From source

```bash
git clone https://github.com/anthropics/claude-karma.git
cd claude-karma/karma-logger
npm install
npm run build
npm link  # Makes 'karma' available globally
```

### Requirements

- Node.js 20.0.0 or higher
- Claude Code installed (logs at `~/.claude/projects/`)

---

## Quick Start

```bash
# Show current session metrics
karma status

# Watch sessions in real-time (streaming mode)
karma watch

# Launch interactive TUI dashboard
karma watch --ui

# View session history
karma report

# Launch web dashboard on port 3333
karma dashboard
```

---

## Commands

### `karma status`

Display metrics for the current or specified session.

```bash
karma status                  # Current project session
karma status --all            # All active sessions
karma status -p myproject     # Specific project
karma status --json           # JSON output
karma status --tree           # Show agent hierarchy tree
```

### `karma watch`

Monitor sessions in real-time with live updates.

```bash
karma watch                   # Streaming mode
karma watch --ui              # Interactive TUI dashboard
karma watch --compact         # Compact view (streaming mode only)
karma watch --activity-only   # Tool activity feed only
karma watch --no-persist      # Disable auto-save to SQLite
karma watch --persist-radio   # Enable persistent Walkie-Talkie radio cache (WAL + snapshots)
```

### `karma report`

View session history with filtering and export options.

```bash
karma report                  # List recent sessions
karma report <session-id>     # Session details
karma report --since 7d       # Last 7 days
karma report --json           # JSON export
karma report --csv            # CSV export
karma report --sync           # Sync before reporting
```

### `karma dashboard`

Launch a web-based metrics dashboard with optional Walkie-Talkie integration.

```bash
karma dashboard               # Open on port 3333
karma dashboard -p 8080       # Custom port
karma dashboard --no-open     # Don't open browser
karma dashboard --radio       # Enable live radio agent coordination
karma dashboard --persist-radio # Enable persistent radio cache (WAL + snapshots)
```

### `karma config`

Manage configuration settings.

```bash
karma config                  # Show all settings
karma config get <key>        # Get a value
karma config set <key> <val>  # Set a value
karma config reset            # Reset to defaults
karma config list             # List available keys
```

### `karma radio`

Agent coordination via Walkie-Talkie IPC system (Unix socket-based).

```bash
# Status management
karma radio set-status <state>        # Set agent status (pending|active|waiting|completed|failed|cancelled)
karma radio set-status <state> --tool <name> --percent <0-100> --message <text> --metadata <json>
karma radio get-status                # Get current agent status
karma radio get-status --agent <id>   # Get status for specific agent
karma radio list-agents               # List all registered agents

# Progress reporting
karma radio report-progress           # Report progress update
karma radio report-progress --tool <name> --percent <0-100> --message <text>

# Results and communication
karma radio publish-result <json-file>  # Publish agent result from JSON file
karma radio send <agent-id> <msg-json>  # Send JSON message to another agent
karma radio listen                      # Listen for incoming messages

# Agent coordination
karma radio wait-for <agent-id> <state>              # Wait for single agent to reach state
karma radio wait-for <agent-id> <state> --timeout <ms> --poll
karma radio wait-for-all <agent1> <agent2> <state>   # Wait for multiple agents (last arg is state)
karma radio wait-for-children <state>                # Wait for all child agents to reach state

# Monitoring (inference-based, via JSONL)
karma radio watch-subagents           # Watch subagents with live updates
karma radio watch-subagents --json    # One-shot JSON output
karma radio watch-subagents --interval <ms>
karma radio scan                      # One-shot subagent scan
karma radio scan --json

# Visualization
karma radio summary                   # Show summary of all agents in session
karma radio summary --json
karma radio tree                      # Display agent hierarchy as ASCII tree
karma radio tree --session <id>       # Show tree for specific session
karma radio tree --json
```

**State Values:**
- `pending` - Agent ready to start
- `active` - Agent actively working
- `waiting` - Agent blocked waiting for something
- `completed` - Agent finished successfully
- `failed` - Agent encountered an error
- `cancelled` - Agent was cancelled

**Required Environment Variables:**
- `KARMA_AGENT_ID` - Unique agent identifier (alphanumeric, hyphens, underscores; max 64 chars)
- `KARMA_SESSION_ID` - Session identifier

**Optional Environment Variables:**
- `KARMA_PARENT_ID` - Parent agent ID (for hierarchical coordination)
- `KARMA_AGENT_TYPE` - Agent type (e.g., "code-reviewer", "analyzer")
- `KARMA_MODEL` - Model being used (e.g., "claude-sonnet-4")

---

## Configuration

### Config File Location

Configuration is stored in `~/.karma/config.json`.

### Available Settings

| Key | Description | Default |
|-----|-------------|---------|
| `logsDir` | Claude Code logs directory | `~/.claude/projects` |
| `dataDir` | Karma data directory | `~/.karma` |
| `retentionDays` | Days to retain history | `30` |
| `defaultProject` | Default project filter | `null` |
| `debug` | Enable debug output | `false` |
| `pricing.*` | Custom token pricing | Claude defaults |

### Environment Variables

| Variable | Config Key |
|----------|------------|
| `KARMA_LOGS_DIR` | `logsDir` |
| `KARMA_DATA_DIR` | `dataDir` |
| `KARMA_RETENTION_DAYS` | `retentionDays` |
| `KARMA_DEFAULT_PROJECT` | `defaultProject` |
| `KARMA_DEBUG` | `debug` |

### Custom Pricing

Override model pricing in `~/.karma/pricing.json` or `.karma-pricing.json` (project-level):

```json
{
  "models": {
    "claude-sonnet-4-20250514": {
      "inputPer1k": 0.003,
      "outputPer1k": 0.015,
      "cacheReadPer1k": 0.0003,
      "cacheCreationPer1k": 0.00375
    }
  }
}
```

---

## Data Storage

| Location | Purpose |
|----------|---------|
| `~/.claude/projects/` | Claude Code logs (read-only) |
| `~/.karma/karma.db` | SQLite database |
| `~/.karma/config.json` | Configuration file |
| `~/.karma/pricing.json` | Custom pricing (optional) |
| `~/.karma/radio/wal.log` | Radio WAL transaction log (optional) |
| `~/.karma/radio/snapshot.json` | Radio cache snapshot (optional) |

### Database Schema

```sql
-- Sessions table
CREATE TABLE sessions (
  id TEXT PRIMARY KEY,
  project_path TEXT NOT NULL,
  project_name TEXT NOT NULL,
  started_at TEXT NOT NULL,
  ended_at TEXT,
  models TEXT DEFAULT '[]',           -- JSON array
  tokens_in INTEGER DEFAULT 0,
  tokens_out INTEGER DEFAULT 0,
  cache_read_tokens INTEGER DEFAULT 0,
  cache_creation_tokens INTEGER DEFAULT 0,
  cost_total REAL DEFAULT 0,
  cost_input REAL DEFAULT 0,
  cost_output REAL DEFAULT 0,
  cost_cache_read REAL DEFAULT 0,
  cost_cache_creation REAL DEFAULT 0,
  agent_count INTEGER DEFAULT 0,
  tool_calls INTEGER DEFAULT 0,
  tool_usage TEXT DEFAULT '{}'        -- JSON object
);

-- Agents table
CREATE TABLE agents (
  id TEXT PRIMARY KEY,
  session_id TEXT NOT NULL,
  parent_id TEXT,
  agent_type TEXT,
  model TEXT,
  started_at TEXT NOT NULL,
  ended_at TEXT,
  tokens_in INTEGER DEFAULT 0,
  tokens_out INTEGER DEFAULT 0,
  cache_read_tokens INTEGER DEFAULT 0,
  cache_creation_tokens INTEGER DEFAULT 0,
  cost_total REAL DEFAULT 0,
  tools_used TEXT DEFAULT '[]',
  tool_calls INTEGER DEFAULT 0,
  FOREIGN KEY (session_id) REFERENCES sessions(id) ON DELETE CASCADE
);

-- Activity table
CREATE TABLE activity (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  session_id TEXT NOT NULL,
  timestamp TEXT NOT NULL,
  tool TEXT NOT NULL,
  type TEXT NOT NULL,
  agent_id TEXT,
  model TEXT,
  FOREIGN KEY (session_id) REFERENCES sessions(id) ON DELETE CASCADE
);
```

---

## Project Structure

```
karma-logger/
├── src/
│   ├── index.ts              # Entry point (CLI bootstrap)
│   ├── cli.ts                # Commander.js CLI definition
│   ├── types.ts              # Core TypeScript interfaces
│   │
│   ├── # Core Modules
│   ├── parser.ts             # JSONL log parsing
│   ├── discovery.ts          # Session/project enumeration
│   ├── watcher.ts            # File system watching
│   ├── aggregator.ts         # Metrics aggregation
│   ├── cost.ts               # Pricing & cost calculation
│   ├── db.ts                 # SQLite database layer
│   ├── converters.ts         # Type conversion utilities
│   ├── config.ts             # Configuration management
│   ├── errors.ts             # Error handling utilities
│   │
│   ├── commands/             # CLI command implementations
│   │   ├── status.ts
│   │   ├── watch.ts
│   │   ├── report.ts
│   │   ├── config.ts
│   │   └── radio.ts          # Agent coordination CLI
│   │
│   ├── dashboard/            # Web dashboard
│   │   ├── index.ts          # Dashboard entry point
│   │   ├── server.ts         # Hono web server
│   │   ├── api.ts            # REST API routes
│   │   ├── sse.ts            # Server-Sent Events
│   │   └── public/           # Static frontend files
│   │       ├── index.html
│   │       ├── style.css
│   │       ├── app.js
│   │       └── charts.js
│   │
│   ├── walkie-talkie/         # Agent coordination (KV cache + IPC)
│   │   ├── index.ts
│   │   ├── types.ts
│   │   ├── cache-store.ts     # In-memory KV with TTL & pub/sub
│   │   ├── persistent-cache.ts # WAL + snapshot persistence
│   │   ├── agent-radio.ts     # High-level agent coordination API
│   │   ├── socket-server.ts   # Unix domain socket server
│   │   ├── socket-client.ts   # Unix domain socket client
│   │   ├── schema-registry.ts # Type validation for metadata
│   │   ├── wal.ts             # Write-Ahead Log
│   │   ├── snapshot.ts        # Snapshot management
│   │   ├── subagent-watcher.ts # Inference-based JSONL subagent tracking
│   │   ├── README.md          # Walkie-Talkie docs
│   │   ├── SETUP.md           # Deployment/integration guide
│   │   └── SUBAGENT_TRACKING.md # Subagent discovery via JSONL files
│   │
│   └── tui/                  # Terminal UI (Ink/React)
│       ├── index.ts          # TUI entry point
│       ├── App.tsx           # Main TUI component
│       ├── components/
│       │   ├── MetricsCard.tsx
│       │   ├── AgentTree.tsx
│       │   ├── Sparkline.tsx
│       │   └── StatusBar.tsx
│       ├── hooks/
│       │   ├── useMetrics.ts
│       │   ├── useAgentTree.ts
│       │   ├── useTokenFlow.ts
│       │   └── useKeyboard.ts
│       ├── context/
│       │   └── AggregatorContext.tsx
│       └── utils/
│           └── format.ts
│
├── tests/                    # Test suites (Vitest)
│   ├── parser.test.ts
│   ├── discovery.test.ts
│   ├── aggregator.test.ts
│   ├── db.test.ts
│   ├── cost.test.ts
│   ├── config.test.ts
│   ├── converters.test.ts
│   ├── commands/
│   ├── dashboard/
│   │   ├── server.test.ts
│   │   ├── sse.test.ts
│   │   └── api-historical.test.ts
│   ├── tui/
│   ├── walkie-talkie/        # Agent coordination tests
│   │   ├── cache-store.test.ts
│   │   ├── persistent-cache.test.ts
│   │   ├── agent-radio.test.ts
│   │   ├── schema-registry.test.ts
│   │   ├── socket/radio-client.test.ts
│   │   ├── integration.test.ts
│   │   ├── wal.test.ts
│   │   ├── snapshot.test.ts
│   │   └── subscription.test.ts
│   └── fixtures/             # Test JSONL files
│
├── scripts/                  # Development utilities
│   ├── test-server.ts
│   └── verify-parser.ts
│
├── dist/                     # Compiled output (TypeScript → JS)
├── package.json
├── tsconfig.json
└── README.md
```

---

## Development

### Setup

```bash
git clone https://github.com/anthropics/claude-karma.git
cd claude-karma/karma-logger
npm install
```

### Running in Development

```bash
# Run directly with tsx (no build needed)
npm run dev

# Or run specific commands
npx tsx src/index.ts status
npx tsx src/index.ts watch
npx tsx src/index.ts dashboard
```

### Building

```bash
npm run build          # Compile TypeScript to dist/
npm run typecheck      # Check types without emitting
npm run clean          # Remove dist/
```

### Code Quality

```bash
npm run typecheck      # TypeScript type checking
```

---

## Testing

Tests use **Vitest** and include unit tests for all core modules.

```bash
npm test               # Run all tests once
npm run test:watch     # Watch mode
npm run test:coverage  # With coverage report
```

### Test Structure

| Directory | Tests |
|-----------|-------|
| `tests/*.test.ts` | Core module tests |
| `tests/commands/` | CLI command tests |
| `tests/dashboard/` | Web server and SSE tests |
| `tests/tui/` | Ink component tests |
| `tests/fixtures/` | Sample JSONL files |

---

## Metrics Tracked

### Token Usage

| Metric | Description |
|--------|-------------|
| Input tokens | Tokens sent to the model |
| Output tokens | Tokens generated by the model |
| Cache read tokens | Tokens read from prompt cache |
| Cache creation tokens | Tokens used to create cache |

### Costs

| Metric | Description |
|--------|-------------|
| Per-request cost | Cost of each API call |
| Session totals | Accumulated session cost |
| Cost breakdown | By input/output/cache categories |

### Activity

| Metric | Description |
|--------|-------------|
| Tool calls | Tools invoked with timing |
| Model usage | Which models were used |
| Session duration | Start to last activity time |
| Agent hierarchy | Parent-child agent relationships |

---

## Default Pricing

Pricing per 1 million tokens (Claude models as of 2025):

| Model | Input | Output | Cache Read | Cache Create |
|-------|-------|--------|------------|--------------|
| Claude 4.5 Opus | $15.00 | $75.00 | $1.50 | $18.75 |
| Claude 4 Opus | $15.00 | $75.00 | $1.50 | $18.75 |
| Claude 4 Sonnet | $3.00 | $15.00 | $0.30 | $3.75 |
| Claude 4.5 Haiku | $0.80 | $4.00 | $0.08 | $1.00 |

Override with `karma config set pricing.inputTokenCost <value>` or via pricing config files.

---

## License

MIT
