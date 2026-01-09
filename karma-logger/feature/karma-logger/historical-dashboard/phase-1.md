# Phase 1: Data Layer

**Scope**: Add database query methods for project aggregation and historical metrics.

**File**: `src/db.ts`

---

## Methods to Implement

### 1. `listProjects(): ProjectSummary[]`

Returns aggregated metrics for all projects.

```sql
SELECT
  project_name,
  COUNT(*) as session_count,
  COUNT(DISTINCT DATE(started_at)) as active_days,
  SUM(tokens_in) as total_tokens_in,
  SUM(tokens_out) as total_tokens_out,
  SUM(cost_total) as total_cost,
  MAX(started_at) as last_activity
FROM sessions
GROUP BY project_name
ORDER BY last_activity DESC;
```

**Return Type**:
```typescript
interface ProjectSummary {
  projectName: string;
  sessionCount: number;
  activeDays: number;
  totalTokensIn: number;
  totalTokensOut: number;
  totalCost: number;
  lastActivity: string; // ISO 8601
}
```

---

### 2. `getProjectSummary(projectName: string): ProjectDetail`

Returns summary + sessions for a specific project.

```sql
-- Summary (same as above with WHERE)
SELECT ... FROM sessions WHERE project_name = ?;

-- Sessions list
SELECT * FROM sessions
WHERE project_name = ?
ORDER BY started_at DESC;
```

**Return Type**:
```typescript
interface ProjectDetail {
  summary: ProjectSummary;
  sessions: SessionRow[];
}
```

---

### 3. `getDailyMetrics(projectName?: string, days: number = 30): DailyMetric[]`

Returns daily rollup for trend charts.

```sql
SELECT
  DATE(started_at) as day,
  SUM(tokens_in) as tokens_in,
  SUM(tokens_out) as tokens_out,
  SUM(cost_total) as cost,
  COUNT(*) as sessions
FROM sessions
WHERE started_at >= date('now', '-' || ? || ' days')
  AND (? IS NULL OR project_name = ?)
GROUP BY DATE(started_at)
ORDER BY day;
```

**Return Type**:
```typescript
interface DailyMetric {
  day: string;       // YYYY-MM-DD
  tokensIn: number;
  tokensOut: number;
  cost: number;
  sessions: number;
}
```

---

## Types to Add

Add to `src/types.ts`:

```typescript
export interface ProjectSummary {
  projectName: string;
  sessionCount: number;
  activeDays: number;
  totalTokensIn: number;
  totalTokensOut: number;
  totalCost: number;
  lastActivity: string;
}

export interface ProjectDetail {
  summary: ProjectSummary;
  sessions: SessionRow[];
}

export interface DailyMetric {
  day: string;
  tokensIn: number;
  tokensOut: number;
  cost: number;
  sessions: number;
}
```

---

## Acceptance Criteria

- [ ] `listProjects()` returns all projects sorted by last activity
- [ ] `getProjectSummary()` returns summary + sessions for given project
- [ ] `getDailyMetrics()` supports optional project filter and days param
- [ ] All methods handle empty results gracefully
- [ ] Unit tests cover edge cases (no sessions, single day, etc.)

---

## Dependencies

- None (builds on existing `better-sqlite3` setup)

## Estimated Complexity

Low — SQL aggregation queries, no schema changes.
