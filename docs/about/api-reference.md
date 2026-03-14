# API Reference

Complete reference for the Claude Code Karma REST API. All endpoints are served from `http://localhost:8000`.

The API also provides interactive documentation:
- Swagger UI: `http://localhost:8000/docs`
- ReDoc: `http://localhost:8000/redoc`

## Projects

List and explore your projects.

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/projects` | List all projects with session counts and metadata |
| GET | `/projects/{encoded_name}` | Project details including all sessions and stats |
| GET | `/projects/{encoded_name}/chains` | Session chains (resumed/related sessions) |
| GET | `/projects/{encoded_name}/branches` | Session branches and history |
| GET | `/projects/{encoded_name}/analytics` | Project analytics (token usage, tools, costs) |
| GET | `/projects/{encoded_name}/memory` | Project memory and metadata |
| GET | `/projects/{encoded_name}/agents` | Agents spawned in this project |
| GET | `/projects/{encoded_name}/skills` | Skills invoked in this project |
| GET | `/projects/{encoded_name}/remote-sessions` | Remote sessions from team members |

**Path parameter:** `encoded_name` is the path-encoded project directory (e.g., `-Users-me-repo`). Use the value from `/projects` endpoint.

## Sessions

Browse, analyze, and interact with sessions.

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/sessions/all` | List all sessions across all projects |
| GET | `/sessions/{uuid}` | Session details: messages, metadata, token counts |
| GET | `/sessions/{uuid}/timeline` | Chronological event timeline |
| GET | `/sessions/{uuid}/tools` | Tool usage breakdown |
| GET | `/sessions/{uuid}/file-activity` | Files changed during the session |
| GET | `/sessions/{uuid}/subagents` | Subagent activity |
| GET | `/sessions/{uuid}/plan` | Plan details (if this was a plan-mode session) |
| GET | `/sessions/{uuid}/chain` | Full session chain (resumed sessions) |
| GET | `/sessions/{uuid}/initial-prompt` | The original user prompt that started the session |
| POST | `/sessions/{uuid}/title` | Update session title manually |

**Path parameter:** `uuid` is the session UUID matching the JSONL filename.

## Analytics

Analyze patterns and usage across projects and sessions.

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/agents` | Agent statistics across all sessions |
| GET | `/skills` | Skill invocation data |
| GET | `/tools` | MCP tool discovery and usage |

## Real-Time Monitoring

Watch active sessions as they happen (requires hooks installed).

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/live-sessions` | Current real-time session states |

Returns session state with: session ID, project, status (STARTING, LIVE, WAITING, STOPPED, STALE, ENDED), timestamps, and latest activity.

## Sync Status

Monitor session sync configuration and team status.

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/sync/status` | Sync configuration and status |
| GET | `/sync/teams` | List all teams with members |

Response includes: user ID, machine ID, backend type (syncthing), team info with member counts.

## Remote Sessions

Browse sessions synced from team members.

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/users` | List all remote users who synced sessions |
| GET | `/users/{user_id}/projects` | List projects synced by a remote user |
| GET | `/users/{user_id}/projects/{project}/sessions` | Sessions in a remote project |
| GET | `/users/{user_id}/projects/{project}/manifest` | Project manifest with metadata |

**Path parameters:**
- `user_id` — Remote user ID (e.g., `alice`, `bob`)
- `project` — Project encoded name (e.g., `-Users-alice-work-acme-app`)

**Example response — Remote user:**

```json
{
  "user_id": "alice",
  "project_count": 2,
  "total_sessions": 12
}
```

**Example response — Remote project:**

```json
{
  "encoded_name": "-Users-alice-work-acme-app",
  "session_count": 5,
  "synced_at": "2026-03-03T14:30:00Z",
  "machine_id": "alice-macbook-pro"
}
```

**Example response — Manifest:**

```json
{
  "version": 1,
  "user_id": "alice",
  "machine_id": "alice-macbook-pro",
  "project_path": "/Users/alice/work/acme-app",
  "synced_at": "2026-03-03T14:30:00Z",
  "session_count": 5,
  "sync_backend": "syncthing",
  "sessions": [
    {
      "uuid": "abc-123-def",
      "mtime": "2026-03-03T12:00:00Z",
      "size_bytes": 45000
    }
  ]
}
```

## Plans

Browse plan-mode sessions.

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/plans` | List plan-mode sessions |

## Hooks

Hook management and event logs.

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/hooks` | Hook configuration and event data |

## History

File change tracking across all sessions.

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/history` | All file changes across sessions |

## Settings

Dashboard configuration and preferences.

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/settings` | User preferences and configuration |

## Plugins & Tools

Discover available plugins and MCP tools.

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/plugins` | Plugin listing with MCP tool details |

## Health

System status check.

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/health` | API health check |

## Response Patterns

### Pagination

List endpoints support pagination:

| Parameter | Type | Description |
|-----------|------|-------------|
| `limit` | int | Maximum items to return (default: 50) |
| `offset` | int | Items to skip |

### Error Responses

Errors follow HTTP status codes with JSON bodies:

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

Project endpoints use encoded path names. The encoding converts filesystem paths to URL-safe strings:

```
/Users/me/project  →  -Users-me-project
```

Use the value from the `/projects` listing as the `encoded_name` parameter.

### Input Validation

Remote session endpoints validate input to prevent path traversal:
- `user_id` and `project` must be alphanumeric, dash, underscore, or dot only
- Values like `.` and `..` are rejected
- Invalid characters result in 400 Bad Request

## Authentication

The API does not require authentication. It's designed for local use on your machine. If you expose it to the network, add authentication using a reverse proxy or firewall.

## Rate Limiting

No rate limiting. The API is designed for local use.

## CORS

CORS is enabled for local development. The API accepts requests from `localhost:*` and other configured origins.
