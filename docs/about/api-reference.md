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

## Sync — System

Initialize, detect, and manage your Syncthing sync setup.

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/sync/detect` | Check if Syncthing is installed and running |
| POST | `/sync/init` | Initialize sync — saves your user ID, detects Syncthing |
| GET | `/sync/status` | Current sync config, member tag, Syncthing status, and team summary |
| POST | `/sync/reconcile` | Manually trigger the 3-phase reconciliation cycle |
| POST | `/sync/reset` | Full teardown — deletes all sync data and optionally uninstalls Syncthing |

**Example — `/sync/status` response:**

```json
{
  "configured": true,
  "user_id": "jayant",
  "machine_tag": "macbook",
  "member_tag": "jayant.macbook",
  "syncthing": { "installed": true, "running": true, "device_id": "ABCDE-FGHIJ-..." },
  "teams": [{ "name": "backend-crew", "status": "active", "member_count": 3 }]
}
```

## Sync — Teams & Members

Create teams, manage members, and view team details. Only the team leader can modify membership.

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/sync/teams` | Create a new team (caller becomes leader) |
| GET | `/sync/teams` | List all teams |
| GET | `/sync/teams/{name}` | Team detail — includes members, projects, and subscriptions |
| DELETE | `/sync/teams/{name}` | Dissolve a team (leader only) |
| POST | `/sync/teams/{name}/members` | Add member via pairing code (leader only) |
| DELETE | `/sync/teams/{name}/members/{tag}` | Remove a member (leader only) |
| GET | `/sync/teams/{name}/members` | List team members |
| GET | `/sync/teams/{name}/join-code` | Generate a join code for inviting teammates |
| GET | `/sync/teams/{name}/activity?limit=20` | Recent activity events for the team |
| GET | `/sync/teams/{name}/project-status` | Per-project subscription counts |
| GET | `/sync/teams/{name}/session-stats?days=30` | Per-member stats and subscription counts |

**Path parameter:** `{tag}` is the member's `member_tag` (e.g., `jayant.macbook`).

**Example — `/sync/teams/{name}` response:**

```json
{
  "name": "backend-crew",
  "leader_member_tag": "jayant.macbook",
  "status": "active",
  "created_at": "2026-03-18T10:00:00+00:00",
  "members": [
    { "member_tag": "jayant.macbook", "device_id": "ABCDE-...", "user_id": "jayant", "machine_tag": "macbook", "status": "active" }
  ],
  "projects": [
    { "git_identity": "jayantdevkar/claude-karma", "folder_suffix": "jayantdevkar-claude-karma", "status": "shared" }
  ],
  "subscriptions": [
    { "member_tag": "jayant.macbook", "project": "jayantdevkar/claude-karma", "status": "accepted", "direction": "both" }
  ]
}
```

## Sync — Projects & Subscriptions

Share projects with teams and manage how you receive them.

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/sync/teams/{name}/projects` | Share a project with the team (leader only) |
| DELETE | `/sync/teams/{name}/projects/{git_identity}` | Remove a project from the team (leader only) |
| GET | `/sync/teams/{name}/projects` | List shared projects |
| POST | `/sync/subscriptions/{team}/{git_identity}/accept` | Accept a subscription (set direction) |
| POST | `/sync/subscriptions/{team}/{git_identity}/pause` | Pause a subscription |
| POST | `/sync/subscriptions/{team}/{git_identity}/resume` | Resume a paused subscription |
| POST | `/sync/subscriptions/{team}/{git_identity}/decline` | Decline a subscription |
| PATCH | `/sync/subscriptions/{team}/{git_identity}/direction` | Change sync direction |
| GET | `/sync/subscriptions` | List all your subscriptions across teams |

**Subscription statuses:** `offered` → `accepted` / `declined`. Accepted subscriptions can be `paused` and `resumed`.

**Sync directions:** `send` (share yours), `receive` (get theirs), `both` (default).

## Sync — Pending Devices & Folders

Manage incoming connection requests and folder offers from other Syncthing devices.

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/sync/pending-devices` | Devices requesting to connect |
| POST | `/sync/pending-devices/{device_id}/accept` | Accept a pending device into Syncthing |
| DELETE | `/sync/pending-devices/{device_id}` | Dismiss a pending device |
| GET | `/sync/pending` | Folders offered by peers |
| POST | `/sync/pending/accept/{folder_id}` | Accept a pending folder |
| POST | `/sync/pending/reject/{folder_id}` | Reject a pending folder |

## Sync — Pairing

Generate and validate pairing codes for adding teammates.

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/sync/pairing/code` | Generate your permanent pairing code |
| POST | `/sync/pairing/validate` | Validate and decode a pairing code |
| GET | `/sync/devices` | List connected Syncthing devices |

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
| 201 | Created (team, member, project) |
| 400 | Bad request (invalid name, missing config) |
| 403 | Forbidden (not the team leader) |
| 404 | Resource not found (invalid UUID, unknown project or team) |
| 409 | Conflict (invalid state transition — e.g., dissolving an already dissolved team) |
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
