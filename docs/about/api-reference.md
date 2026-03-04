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

## Sync Status

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/sync/status` | Sync configuration and status: backend type, teams, project counts |
| GET | `/sync/teams` | List all teams with their backend (IPFS or Syncthing) and members |

**Response:** Sync status endpoint returns configured status, user ID, machine ID, and per-team information (backend type, project count, member count).

---

## Remote Sessions (Synced from Team Members)

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/users` | List all remote users who have synced sessions |
| GET | `/users/{user_id}/projects` | List projects synced by a remote user |
| GET | `/users/{user_id}/projects/{project}/sessions` | List sessions in a remote user's project |
| GET | `/users/{user_id}/projects/{project}/manifest` | Get the full manifest for a remote user's project (metadata + session list) |

**Path parameters:**
- `user_id` — Remote freelancer/contributor ID (e.g., `alice`, `bob`)
- `project` — Project encoded name (e.g., `-Users-alice-work-acme-app`)

**Response examples:**

Remote user:
```json
{
  "user_id": "alice",
  "project_count": 2,
  "total_sessions": 12
}
```

Remote project:
```json
{
  "encoded_name": "-Users-alice-work-acme-app",
  "session_count": 5,
  "synced_at": "2026-03-03T14:30:00Z",
  "machine_id": "alice-macbook-pro"
}
```

Manifest:
```json
{
  "version": 1,
  "user_id": "alice",
  "machine_id": "alice-macbook-pro",
  "project_path": "/Users/alice/work/acme-app",
  "project_encoded": "-Users-alice-work-acme-app",
  "synced_at": "2026-03-03T14:30:00Z",
  "session_count": 5,
  "sync_backend": "syncthing",
  "sessions": [
    {
      "uuid": "abc123def456...",
      "mtime": "2026-03-03T12:00:00Z",
      "size_bytes": 45000
    }
  ]
}
```

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

### Sync Data Validation

Remote session endpoints validate input to prevent path traversal attacks:
- `user_id` and `project` parameters must be alphanumeric, dash, underscore, or dot only
- Values like `.` and `..` are rejected
- Invalid characters result in 400 Bad Request with error details
