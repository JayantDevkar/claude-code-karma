# API Reference

Complete reference for the Claude Code Karma REST API. All endpoints are served from `http://localhost:8000`.

The API also provides interactive documentation via FastAPI's built-in Swagger UI at `/docs` and ReDoc at `/redoc`.

---

## Projects

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/projects` | List all discovered projects with session counts and metadata |
| GET | `/projects/{encoded_name}` | Project details including all sessions, recent activity, and aggregate stats |

**Path parameter:** `encoded_name` is the path-encoded project directory (e.g., `-Users-me-repo`).

---

## Sessions

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/sessions/{uuid}` | Session details: messages, metadata, token counts, duration, model |
| GET | `/sessions/{uuid}/timeline` | Chronological event timeline with messages, tool calls, and subagent events |
| GET | `/sessions/{uuid}/tools` | Tool usage breakdown: call counts, tool names, success/failure |
| GET | `/sessions/{uuid}/file-activity` | File operations performed during the session (read, write, edit, create) |
| GET | `/sessions/{uuid}/subagents` | Subagent (Task agent) activity: spawned agents, prompts, outcomes |

**Path parameter:** `uuid` is the session UUID matching the JSONL filename.

---

## Analytics

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/analytics/projects/{encoded_name}` | Project-level analytics: token trends, tool distribution, session frequency |

---

## Agents

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/agents` | List all subagents across sessions with usage statistics |

---

## Skills

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/skills` | Skill invocation data across all sessions |

---

## Live Sessions

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/live-sessions` | Current real-time session states (requires hooks to be installed) |

Returns session state objects with fields: session ID, project, status (STARTING, LIVE, WAITING, STOPPED, STALE, ENDED), timestamps, and latest activity.

---

## Plans

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/plans` | Browse plan-mode sessions and their approval status |

---

## Tools

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/tools` | MCP tool discovery and usage data across sessions |

---

## Hooks

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/hooks` | Hook configuration and event data |

---

## Plugins

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/plugins` | Plugin listing with MCP tool details |

---

## History

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/history` | File history across all sessions — which files were touched, when, and by whom |

---

## Settings

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/settings` | User preferences and dashboard configuration |

---

## About Docs

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/docs/about` | About page documentation files (overview, features, architecture, etc.) |

---

## Health

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/health` | Health check endpoint returning API status |

---

## Common Response Patterns

### Pagination

List endpoints that return large datasets support query parameters:

| Parameter | Type | Description |
|-----------|------|-------------|
| `limit` | int | Maximum number of items to return |
| `offset` | int | Number of items to skip |

### Error Responses

Errors follow standard HTTP status codes with JSON bodies:

```json
{
  "detail": "Session not found: abc-123"
}
```

| Status | Meaning |
|--------|---------|
| 200 | Success |
| 404 | Resource not found (invalid UUID, unknown project) |
| 422 | Validation error (malformed parameters) |
| 500 | Internal server error (JSONL parse failure, filesystem error) |

### Path Encoding

Project endpoints use encoded path names. The encoding converts filesystem paths to URL-safe strings by replacing `/` with `-` and prefixing with `-`:

```
/Users/me/project  -->  -Users-me-project
```

Use the value from the `/projects` listing as the `encoded_name` parameter.
