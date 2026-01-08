# Phase 6: SQLite Persistence & `karma report`

**Status:** Complete
**Estimated Effort:** Medium
**Dependencies:** Phase 4
**Deliverable:** Persistent storage and historical reporting

---

## Objective

Add SQLite persistence to store session history and implement the `karma report` command for historical analysis.

---

## Tasks

### 6.1 Install Dependencies
```bash
npm install better-sqlite3
npm install -D @types/better-sqlite3
```

### 6.2 Create Database Module
- [ ] Create `src/db.ts`
- [ ] Initialize database at `~/.karma/karma.db`
- [ ] Implement schema migrations
- [ ] Create CRUD operations

```typescript
// src/db.ts
export class KarmaDB {
  private db: Database;

  constructor() {
    const dbPath = path.join(os.homedir(), '.karma', 'karma.db');
    fs.mkdirSync(path.dirname(dbPath), { recursive: true });
    this.db = new Database(dbPath);
    this.migrate();
  }

  migrate(): void;
  saveSession(session: SessionMetrics): void;
  saveAgent(agent: AgentMetrics): void;
  getSession(id: string): SessionMetrics | null;
  listSessions(options: ListOptions): SessionSummary[];
}
```

### 6.3 Implement Schema
```sql
-- migrations/001_initial.sql
CREATE TABLE IF NOT EXISTS sessions (
  id TEXT PRIMARY KEY,
  project_path TEXT NOT NULL,
  started_at TEXT NOT NULL,
  ended_at TEXT,
  model TEXT,
  tokens_in INTEGER DEFAULT 0,
  tokens_out INTEGER DEFAULT 0,
  tokens_cached INTEGER DEFAULT 0,
  cost_total REAL DEFAULT 0,
  cost_input REAL DEFAULT 0,
  cost_output REAL DEFAULT 0,
  cost_cache REAL DEFAULT 0,
  agent_count INTEGER DEFAULT 0,
  tool_calls INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS agents (
  id TEXT PRIMARY KEY,
  session_id TEXT NOT NULL,
  parent_id TEXT,
  agent_type TEXT,
  model TEXT,
  started_at TEXT NOT NULL,
  ended_at TEXT,
  tokens_in INTEGER DEFAULT 0,
  tokens_out INTEGER DEFAULT 0,
  tokens_cached INTEGER DEFAULT 0,
  cost_total REAL DEFAULT 0,
  tools_used TEXT,
  FOREIGN KEY (session_id) REFERENCES sessions(id)
);

CREATE INDEX idx_sessions_project ON sessions(project_path);
CREATE INDEX idx_sessions_started ON sessions(started_at);
CREATE INDEX idx_agents_session ON agents(session_id);
```

### 6.4 Session Lifecycle
- [ ] Detect session end (file unchanged for 5 min)
- [ ] Persist session on end
- [ ] Update existing session if reopened
- [ ] Handle crashes gracefully

### 6.5 Create Report Command
- [ ] Create `src/commands/report.ts`
- [ ] List recent sessions
- [ ] Show detailed session breakdown
- [ ] Support date range filtering

```bash
# List recent sessions
karma report

# Specific session
karma report abc1234

# Filter by project
karma report --project claude-karma

# Date range
karma report --since 2026-01-01

# Output formats
karma report --json
karma report --csv
```

### 6.6 Design Report Output
```
╭──────────────────────────────────────────────────────────────╮
│  SESSION REPORT: abc1234                                     │
│  Project: claude-karma                                       │
│  Duration: 2h 15m (14:00 - 16:15)                            │
├──────────────────────────────────────────────────────────────┤
│  SUMMARY                                                     │
│    Total Cost:     $4.52                                     │
│    Tokens In:      523.4K                                    │
│    Tokens Out:     187.2K                                    │
│    Tokens Cached:  312.1K                                    │
│    Agents:         15                                        │
│    Tool Calls:     142                                       │
├──────────────────────────────────────────────────────────────┤
│  TOP AGENTS BY COST                                          │
│  1. main (sonnet)           $2.34  (52%)                     │
│  2. 7a3f2b1 refactor        $0.89  (20%)                     │
│  3. 8b4e3c2 explore         $0.45  (10%)                     │
├──────────────────────────────────────────────────────────────┤
│  TOP TOOLS                                                   │
│  1. Read              45 calls                               │
│  2. Edit              32 calls                               │
│  3. Bash              28 calls                               │
│  4. Grep              21 calls                               │
╰──────────────────────────────────────────────────────────────╯
```

### 6.7 Session List View
```
╭──────────────────────────────────────────────────────────────╮
│  RECENT SESSIONS                                             │
├──────────────────────────────────────────────────────────────┤
│  ID       PROJECT           DATE        DURATION    COST     │
│  abc1234  claude-karma      Today       2h 15m      $4.52    │
│  def5678  other-project     Yesterday   45m         $1.23    │
│  ghi9012  claude-karma      Jan 6       1h 30m      $2.87    │
├──────────────────────────────────────────────────────────────┤
│  TOTALS (7 days)                                             │
│    Sessions: 12  |  Cost: $24.56  |  Tokens: 2.3M            │
╰──────────────────────────────────────────────────────────────╯
```

---

## Acceptance Criteria

1. Sessions persist to SQLite correctly
2. `karma report` shows last 10 sessions by default
3. `karma report <id>` shows detailed breakdown
4. Data survives process restart
5. Database < 10MB for 30 days of typical usage

---

## Exit Condition

Phase complete when historical sessions are queryable via `karma report`.
