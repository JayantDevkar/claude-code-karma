# Karma Logger MVP Plan

**Date:** 2026-01-08
**Status:** Planning
**Owner:** Senior Agent Orchestrator

---

## Executive Summary

Karma Logger is a local-first metrics system that transforms Claude Code agent activity into actionable insights. This MVP focuses on **core visibility**: parsing JSONL logs, tracking token usage, and calculating costs in real-time.

---

## Tech Stack Decision

### Recommended Stack

| Component | Choice | Rationale |
|-----------|--------|-----------|
| **Runtime** | Node.js 20+ / Bun | Native ESM, fast file watching |
| **Language** | TypeScript | Type safety, ecosystem compatibility |
| **CLI Framework** | Commander.js | Simple, proven, 15M+ weekly downloads |
| **File Watching** | Chokidar v5 | Cross-platform, mature, low resource |
| **Storage** | SQLite (better-sqlite3) | Synchronous, embedded, transactional |
| **JSONL Parsing** | Native readline + JSON | Simple, streaming, memory-efficient |

### Alternatives Considered

| Option | Why Not For MVP |
|--------|-----------------|
| **Rust** | Higher complexity, slower iteration |
| **DuckDB** | Overkill for transactional writes; better for analytics phase |
| **oclif** | Too heavy for MVP; upgrade path exists |
| **Ink (React CLI)** | Adds complexity for simple status output |

### Sources
- [Building CLI apps with TypeScript in 2026](https://dev.to/hongminhee/building-cli-apps-with-typescript-in-2026-5c9d)
- [oclif Framework](https://oclif.io/)
- [Chokidar GitHub](https://github.com/paulmillr/chokidar)
- [DuckDB vs SQLite Comparison](https://betterstack.com/community/guides/scaling-python/duckdb-vs-sqlite/)

---

## MVP Scope

### In Scope (Phase 1)

1. **Log Discovery**
   - Auto-detect `~/.claude/projects/` directory
   - Identify active session JSONL files
   - Distinguish main session from agent files

2. **Real-Time Watching**
   - Tail active JSONL files
   - Parse new entries as they arrive
   - Handle file rotation gracefully

3. **Metrics Collection**
   - Token counts (input, output, cached)
   - Model identification (haiku/opus/sonnet)
   - Agent hierarchy (via parentUuid)
   - Tool usage extraction

4. **Cost Calculation**
   - Current Anthropic pricing:
     - Haiku: $0.25/$1.25 per 1M tokens (input/output)
     - Sonnet: $3/$15 per 1M tokens
     - Opus: $15/$75 per 1M tokens
   - Session totals and per-agent breakdown

5. **CLI Interface**
   - `karma status` - Current session overview
   - `karma watch` - Real-time activity stream
   - `karma report [session-id]` - Detailed breakdown

### Out of Scope (Future Phases)

- Pattern detection and optimization suggestions
- Web UI dashboard
- Cross-session trend analysis
- Team/org aggregation
- Export to external systems (OTEL, Grafana)
- Budget alerts and thresholds

---

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                      CLI Layer                              │
│  karma status | karma watch | karma report                  │
└──────────────────────┬──────────────────────────────────────┘
                       │
┌──────────────────────▼──────────────────────────────────────┐
│                   Core Engine                               │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────┐  │
│  │ Log Watcher │  │ JSONL Parser│  │ Metrics Aggregator  │  │
│  │ (chokidar)  │──▶│ (readline)  │──▶│ (in-memory + SQL)   │  │
│  └─────────────┘  └─────────────┘  └─────────────────────┘  │
└──────────────────────┬──────────────────────────────────────┘
                       │
┌──────────────────────▼──────────────────────────────────────┐
│                  Storage Layer                              │
│  ~/.karma/                                                  │
│  ├── karma.db          (SQLite - metrics history)           │
│  └── config.json       (user preferences)                   │
└─────────────────────────────────────────────────────────────┘
```

### Component Breakdown

#### 1. Log Watcher (`src/watcher.ts`)
- Uses chokidar to watch `~/.claude/projects/*/`
- Detects new session files and agent files
- Emits events: `session:start`, `agent:spawn`, `entry:new`

#### 2. JSONL Parser (`src/parser.ts`)
- Streaming parser using readline
- Extracts: agentId, model, usage, parentUuid, tools
- Handles malformed entries gracefully

#### 3. Metrics Aggregator (`src/aggregator.ts`)
- In-memory cache for active session
- Calculates running totals
- Builds agent hierarchy tree
- Persists to SQLite on session end

#### 4. Cost Calculator (`src/cost.ts`)
- Model-specific pricing lookup
- Token-to-cost conversion
- Currency formatting

#### 5. CLI Commands (`src/commands/`)
- `status.ts` - Snapshot of current session
- `watch.ts` - Real-time streaming output
- `report.ts` - Historical session details

---

## Data Model (SQLite)

```sql
-- Sessions table
CREATE TABLE sessions (
  id TEXT PRIMARY KEY,           -- Session UUID
  project_path TEXT NOT NULL,
  started_at TEXT NOT NULL,
  ended_at TEXT,
  model TEXT,
  total_tokens_in INTEGER DEFAULT 0,
  total_tokens_out INTEGER DEFAULT 0,
  total_tokens_cached INTEGER DEFAULT 0,
  total_cost REAL DEFAULT 0,
  agent_count INTEGER DEFAULT 0
);

-- Agents table
CREATE TABLE agents (
  id TEXT PRIMARY KEY,           -- 7-char hex ID
  session_id TEXT NOT NULL,
  parent_uuid TEXT,
  agent_type TEXT,               -- explore, bash, refactor, etc.
  model TEXT,
  created_at TEXT NOT NULL,
  completed_at TEXT,
  tokens_in INTEGER DEFAULT 0,
  tokens_out INTEGER DEFAULT 0,
  tokens_cached INTEGER DEFAULT 0,
  cost REAL DEFAULT 0,
  tools_used TEXT,               -- JSON array
  FOREIGN KEY (session_id) REFERENCES sessions(id)
);

-- Tool usage tracking
CREATE TABLE tool_calls (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  agent_id TEXT NOT NULL,
  tool_name TEXT NOT NULL,
  timestamp TEXT NOT NULL,
  FOREIGN KEY (agent_id) REFERENCES agents(id)
);
```

---

## Implementation Phases

### Phase 1: Foundation (MVP Core)
- [ ] Project setup (TypeScript, ESM, dependencies)
- [ ] Log watcher implementation
- [ ] JSONL parser with streaming
- [ ] In-memory metrics aggregation
- [ ] `karma status` command
- [ ] Basic cost calculation

### Phase 2: Persistence & History
- [ ] SQLite schema and migrations
- [ ] Session persistence on close
- [ ] `karma report` command
- [ ] Historical session listing

### Phase 3: Real-Time Experience
- [ ] `karma watch` with live updates
- [ ] Agent hierarchy visualization (ASCII tree)
- [ ] Running cost display
- [ ] Graceful interrupt handling (Ctrl+C)

### Phase 4: Polish
- [ ] Error handling and edge cases
- [ ] Configuration file support
- [ ] npm package setup
- [ ] Documentation and README

---

## File Structure

```
karma-logger/
├── package.json
├── tsconfig.json
├── README.md
├── src/
│   ├── index.ts              # Entry point
│   ├── cli.ts                # Commander setup
│   ├── watcher.ts            # File watching
│   ├── parser.ts             # JSONL parsing
│   ├── aggregator.ts         # Metrics aggregation
│   ├── cost.ts               # Cost calculation
│   ├── db.ts                 # SQLite operations
│   ├── types.ts              # TypeScript interfaces
│   ├── config.ts             # Configuration
│   └── commands/
│       ├── status.ts
│       ├── watch.ts
│       └── report.ts
├── migrations/
│   └── 001_initial.sql
└── tests/
    ├── parser.test.ts
    └── aggregator.test.ts
```

---

## Pricing Reference

| Model | Input (per 1M) | Output (per 1M) |
|-------|----------------|-----------------|
| claude-haiku-4-5-20251001 | $0.80 | $4.00 |
| claude-sonnet-4-20250514 | $3.00 | $15.00 |
| claude-opus-4-5-20251101 | $15.00 | $75.00 |

*Prices as of January 2026. Cache read tokens are typically 10% of input cost.*

---

## Success Criteria

### MVP Complete When:
1. `karma status` shows current session metrics
2. Token counts match manual JSONL inspection
3. Costs calculated within 1% accuracy
4. Agent hierarchy correctly reconstructed
5. Works across macOS/Linux

### Quality Gates:
- No memory leaks in watch mode
- Handles 100+ agents per session
- Startup time < 100ms
- Watch mode CPU < 1%

---

## Open Questions

1. **Pricing API**: Should we fetch live pricing or use static values?
   - *Recommendation*: Static for MVP, with config override option

2. **Project scope**: Track all projects or allow filtering?
   - *Recommendation*: Default to current project, flag for all

3. **Data retention**: How long to keep historical data?
   - *Recommendation*: 30 days default, configurable

---

## Next Steps

1. Initialize npm project with TypeScript
2. Implement Log Watcher (chokidar setup)
3. Build JSONL Parser with test fixtures
4. Create `karma status` command
5. Test with live Claude Code session
