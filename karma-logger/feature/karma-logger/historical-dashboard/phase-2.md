# Phase 2: API Routes

**Scope**: Expose project and historical data via REST endpoints.

**File**: `src/dashboard/api.ts`

---

## Endpoints to Implement

### 1. `GET /api/projects`

List all projects with aggregated metrics.

**Handler**:
```typescript
app.get('/api/projects', (c) => {
  const projects = db.listProjects();
  return c.json(projects);
});
```

**Response**: `ProjectSummary[]`

---

### 2. `GET /api/projects/:name`

Get project detail with sessions.

**Handler**:
```typescript
app.get('/api/projects/:name', (c) => {
  const name = decodeURIComponent(c.req.param('name'));
  const detail = db.getProjectSummary(name);
  if (!detail) {
    return c.json({ error: 'Project not found' }, 404);
  }
  return c.json(detail);
});
```

**Response**: `ProjectDetail`

**Note**: Project names may contain special characters — use `decodeURIComponent`.

---

### 3. `GET /api/projects/:name/history`

Get daily metrics for a project.

**Query Params**:
- `days` (optional, default: 30)

**Handler**:
```typescript
app.get('/api/projects/:name/history', (c) => {
  const name = decodeURIComponent(c.req.param('name'));
  const days = parseInt(c.req.query('days') || '30', 10);
  const metrics = db.getDailyMetrics(name, days);
  return c.json(metrics);
});
```

**Response**: `DailyMetric[]`

---

### 4. `GET /api/totals/history`

Get daily metrics across all projects.

**Query Params**:
- `days` (optional, default: 30)

**Handler**:
```typescript
app.get('/api/totals/history', (c) => {
  const days = parseInt(c.req.query('days') || '30', 10);
  const metrics = db.getDailyMetrics(undefined, days);
  return c.json(metrics);
});
```

**Response**: `DailyMetric[]`

---

## Route Registration Order

Add routes before the catch-all static handler:

```typescript
// Historical dashboard routes (new)
app.get('/api/projects', ...);
app.get('/api/projects/:name', ...);
app.get('/api/projects/:name/history', ...);
app.get('/api/totals/history', ...);

// Existing routes
app.get('/api/session', ...);
app.get('/api/sessions', ...);
app.get('/api/totals', ...);
```

---

## Error Handling

| Scenario | Response |
|----------|----------|
| Project not found | `404 { error: "Project not found" }` |
| Invalid days param | Default to 30 |
| DB error | `500 { error: "Internal error" }` |

---

## Acceptance Criteria

- [ ] `/api/projects` returns all projects sorted by last activity
- [ ] `/api/projects/:name` returns 404 for unknown projects
- [ ] `/api/projects/:name/history` respects `days` query param
- [ ] `/api/totals/history` aggregates across all projects
- [ ] URL-encoded project names are handled correctly
- [ ] Integration tests verify all endpoints

---

## Dependencies

- **Phase 1**: `db.listProjects()`, `db.getProjectSummary()`, `db.getDailyMetrics()`

## Estimated Complexity

Low — straightforward Hono route handlers.
