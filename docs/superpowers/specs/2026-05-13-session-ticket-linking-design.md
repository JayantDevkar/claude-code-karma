# Session ↔ Ticket Linking — Design

**Status:** Draft — revised post-review
**Date:** 2026-05-13
**Author:** Jayant Devkar (with Claude)
**Reviewers:** oh-my-claudecode:critic, feature-dev:code-reviewer (both REVISE → addressed inline below)

## Problem

Today, a Claude Code session in karma has no concept of *why* it exists. Users
often start a session to work on a specific ticket (GitHub Issue, Linear, Jira),
but karma has no way to surface that context. Reviewing "what work was done for
ticket X" requires manual correlation across the dashboard, the ticket tracker,
and git history.

We want karma to **organize sessions around tickets**: store the link, display
ticket context next to sessions, and let a ticket page show every session that
touched it. This is a *post-hoc audit* feature, not a workflow-automation one.

## Goals

- A session can be linked to one or more tickets (Linear, Jira, GitHub Issues).
- Links can be established three ways: an in-session slash command, a
  branch-name auto-detector, and a dashboard input.
- The karma dashboard shows ticket badges on session cards, a `/tickets` index,
  and a per-ticket detail page listing linked sessions.
- Ticket metadata (title, status) is cached in karma's SQLite DB; the agent
  populates it via its already-configured MCP servers (Linear MCP, GitHub MCP,
  Atlassian MCP) at link time.
- The system works in a degraded mode (URL-only) when MCP isn't available.
- Resumed sessions (which share a slug but get new UUIDs each resume) are
  deduplicated to a single link per ticket.

## Non-goals (v1)

- **No write-back to providers.** Karma never modifies ticket state, posts
  comments, or moves cards. Read-only by design.
- **No karma-side provider adapters.** Karma's backend has no Linear/Jira/GitHub
  API client and no provider credentials. The agent + MCP is the only metadata
  source.
- **No fuzzy auto-detection from user prompts.** Heuristics like scanning chat
  for `LINEAR-123` are explicitly excluded — false positives outweigh value.
- **No SessionStart context injection.** The agent is not told about linked
  tickets via a hook. If the agent needs ticket details in-session, the user
  invokes the appropriate MCP directly.
- **No status-change automation, webhooks, or pull notifications.**
- **No primary-ticket flag.** All links on a session are displayed equally.
- **No API auth.** Karma assumes its API is loopback-only (`localhost:8000`),
  same as today. If that changes, this feature inherits whatever scheme is
  added globally.

## Architecture overview

Karma stays a recipient/observer. Nothing in the karma backend talks to Linear,
Jira, or GitHub directly.

```
                                    ┌──────────────────────────┐
  user types "/link-ticket-to-      │  Agent (Claude Code)     │
  session LINEAR-123" in session    │  invokes skill →         │
                ─────────────────►  │  resolves session UUID,  │
                                    │  fetches title/status    │
                                    │  via Linear/GitHub MCP,  │
                                    │  POSTs link + refresh    │
                                    └────────────┬─────────────┘
                                                 │ 1) POST /sessions/{uuid}/tickets
                                                 │    {ref, provider, source}
                                                 │ 2) PUT  /tickets/{provider}/{key}
                                                 │    {title, status, metadata_json}
                                                 ▼
git checkout feat/LINEAR-123   ┌─────────────────────────────────────┐
       │                       │  Karma API (FastAPI)                │
       ▼                       │  - URL/ref parser                   │
SessionStart hook              │  - Transactional upsert into        │
ticket_branch_detector.py ───► │    tickets + session_tickets        │
(bare-ref + slug from          │  - link_source precedence on conflict│
 live-sessions/)               └──────────────┬──────────────────────┘
                                              ▼
dashboard "Link ticket" ───►   ~/.claude_karma/metadata.db (SQLite)
input on /sessions/[uuid]                       │
                                                ▼
                                Frontend: /tickets,
                                /tickets/[provider]/[external_key],
                                badges on session/project pages
```

### Components

1. `api/db/schema.py` — add new tables to **both** the `SCHEMA_SQL` block
   (fresh-install path, lines ~15–217) **and** an incremental migration block
   `if current_version < 11:` (current `SCHEMA_VERSION = 10`). The repo
   pattern is to update both every time; this is verified in
   `api/db/schema.py:247-249`.
2. `api/services/ticket_parser.py` — pure function: ref/URL → `TicketRef`. No
   I/O, no git shell-outs.
3. `api/models/ticket.py` — Pydantic models (`Ticket`, `SessionTicketLink`,
   `TicketRef`, `TicketUpsertRequest`, `TicketMetadataUpdate`). All use
   `ConfigDict(frozen=True)` per the repo pattern (`api/CLAUDE.md` →
   "Frozen Models").
4. `api/routers/tickets.py` — REST endpoints. Registered in `api/main.py`
   following the existing `app.include_router(...)` pattern (see
   `api/main.py:23-40`). Mounted with **no** prefix; endpoint paths are
   spelled out explicitly because the router serves both session-scoped
   (`/sessions/{uuid}/tickets`) and ticket-centric (`/tickets/...`) routes.
5. `api/db/queries.py` — new functions for upsert/link/unlink/list. Reads use
   `sqlite_read()`; writes use `get_writer_db()` from `api/db/connection.py`
   (the existing pattern, see `api/routers/sessions.py:1737` and
   `api/routers/admin.py:31,55,73`).
6. `hooks/ticket_branch_detector.py` — SessionStart hook. POSTs to karma's
   API following the same pattern as `hooks/session_title_generator.py:241`
   (`post_title()` uses `urllib.request` to POST to `localhost:8000`). Silent
   on any failure.
7. `~/.claude/commands/link-ticket-to-session.md` — slash command. Agent
   resolves its own session UUID via `~/.claude_karma/live-sessions/`
   lookup (see *Path 1* below for the locked-down recipe).
8. Frontend additions in `frontend/src/routes/`:
   - `tickets/+page.svelte` (index)
   - `tickets/[provider]/[external_key]/+page.svelte` (detail — keyed on
     the stable external identifier, not the SQLite PK; matches the repo's
     convention of semantic slugs in routes)
   - `frontend/src/lib/components/TicketBadge.svelte` (3 variants: inline,
     card, pill)
   - `frontend/src/lib/components/TicketLinkInput.svelte`
   - Updates to `sessions/[uuid]/+page.svelte` (tickets section)
   - Updates to `projects/[encoded_name]/+page.svelte` (tickets tab/card)
   - Reuses existing `SessionCard` from
     `frontend/src/lib/components/SessionCard.svelte` (verified to exist;
     exported from `frontend/src/lib/index.ts:7`).

No new Python or npm dependencies.

## Data model

Two new tables. No FK to `sessions` (it's a JSONL-mirror table and may not
exist yet when the branch-detect hook fires at `SessionStart`). Soft
references via `session_uuid TEXT` follow the existing reconciler pattern.

**Both tables must be added to two places in `api/db/schema.py`:**

1. The `SCHEMA_SQL` constant (fresh-install path), so a brand-new DB has them.
2. A new `if current_version < 11: conn.executescript(...)` block, so existing
   DBs at v10 get upgraded. The block bumps `SCHEMA_VERSION` to 11.

Omitting either breaks one install path. The repo's pattern is to maintain
both (verified against the v8 → v10 history in the same file).

```sql
CREATE TABLE IF NOT EXISTS tickets (
  id                   INTEGER PRIMARY KEY AUTOINCREMENT,
  provider             TEXT NOT NULL CHECK (provider IN ('linear','jira','github')),
  external_key         TEXT NOT NULL,
  url                  TEXT NOT NULL,
  title                TEXT,
  status               TEXT,
  metadata_json        TEXT CHECK (metadata_json IS NULL OR length(metadata_json) <= 65536),
  metadata_updated_at  TEXT,
  first_seen_at        TEXT NOT NULL DEFAULT (datetime('now')),
  UNIQUE(provider, external_key)
);

CREATE INDEX IF NOT EXISTS idx_tickets_provider ON tickets(provider);

CREATE TABLE IF NOT EXISTS session_tickets (
  id            INTEGER PRIMARY KEY AUTOINCREMENT,
  session_uuid  TEXT NOT NULL,           -- soft ref, no FK
  session_slug  TEXT,                    -- nullable; populated when known
  ticket_id     INTEGER NOT NULL,
  link_source   TEXT NOT NULL CHECK (link_source IN ('branch','slash_command','dashboard')),
  linked_at     TEXT NOT NULL DEFAULT (datetime('now')),
  FOREIGN KEY (ticket_id) REFERENCES tickets(id) ON DELETE CASCADE,
  UNIQUE(session_uuid, ticket_id)
);

CREATE INDEX IF NOT EXISTS idx_session_tickets_session ON session_tickets(session_uuid);
CREATE INDEX IF NOT EXISTS idx_session_tickets_slug    ON session_tickets(session_slug);
CREATE INDEX IF NOT EXISTS idx_session_tickets_ticket  ON session_tickets(ticket_id);

-- Partial unique index: dedupes resumed-session links by slug.
-- Each resume gets a new session_uuid but shares a slug; without this,
-- the branch-detect hook would create a fresh row on every resume.
CREATE UNIQUE INDEX IF NOT EXISTS uniq_session_tickets_slug_ticket
  ON session_tickets(session_slug, ticket_id)
  WHERE session_slug IS NOT NULL;
```

### Constraint rationale

- **`provider` CHECK** — three providers in v1. New providers add a row to
  the CHECK constraint in a future migration. Rejects typos at write time.
- **`metadata_json` length cap (64 KB)** — Linear payloads with comments and
  custom fields can easily exceed 50 KB. The slash command MUST strip
  description, comments, and labels arrays before POSTing; only assignee,
  state, and short fields belong in the cache. Future work: switch to a
  separate `ticket_metadata_blob` table if 64 KB isn't enough.
- **`UNIQUE(provider, external_key)`** — exactly one `tickets` row per
  real-world ticket; linking from multiple sessions reuses the row.
- **`UNIQUE(session_uuid, ticket_id)`** — re-invoking the slash command on
  the same session for the same ticket is a no-op.
- **Partial unique `(session_slug, ticket_id) WHERE session_slug IS NOT NULL`** —
  resumed sessions share a slug but get new UUIDs. This index ensures that
  three resumes of `feat/LINEAR-123` produce one link, not three, **provided
  the writer populates `session_slug`**. Writers without slug context (early
  SessionStart, before live-sessions file is written) skip this dedup and
  fall back to per-UUID linking, which is acceptable.
- **`link_source` precedence on conflict** — see *Endpoint behavior* below.
  Higher-trust sources upgrade lower-trust ones; never the reverse.
- **Datetime defaults** — `TEXT DEFAULT (datetime('now'))` matches the
  existing schema convention (see `schema_version`, `projects.updated_at` in
  `api/db/schema.py`). Removes clock-skew risk across hook / agent / dashboard.

## Link establishment

All three paths converge on `POST /sessions/{uuid}/tickets`. The slash-command
path additionally calls `PUT /tickets/{provider}/{external_key}` to publish
the MCP-fetched metadata. Split into two calls so each is a proper idempotent
operation in the HTTP sense (the original spec conflated "create link" with
"refresh metadata"; the critic flagged this and we fixed it).

### Path 1 — Slash command (richest payload, agent-driven)

`~/.claude/commands/link-ticket-to-session.md`:

```markdown
---
description: Link the current Claude Code session to a ticket and cache its title/status in karma
argument-hint: <ticket-ref-or-url>
---

You are linking the current Claude Code session to ticket: **$ARGUMENTS**

Steps:

1. **Resolve the current session UUID and slug.** Read the directory
   `~/.claude_karma/live-sessions/`. Pick the JSON entry whose `cwd` matches
   the current working directory (`pwd`) and whose `last_updated` is the most
   recent. From that entry, take `session_id` and `slug`. If no entry matches,
   abort and tell the user "karma can't see this session — is the karma API
   running and is the live-session tracker hook installed?"

2. **Parse $ARGUMENTS.** It may be a URL or a short ref. Recognized forms:
   - Linear:  `LINEAR-123` or `https://linear.app/.../issue/ABC-123`
   - Jira:    `PROJ-45` or `https://*.atlassian.net/browse/PROJ-45`
   - GitHub:  `owner/repo#42` or `https://github.com/owner/repo/issues/42`.
              A bare `#N` is NOT accepted — always qualify with `owner/repo`.

3. **Identify the provider** (`linear` | `jira` | `github`).

4. **Fetch ticket details via MCP.** Use the appropriate MCP server:
   - linear → Linear MCP
   - jira → Atlassian MCP
   - github → GitHub MCP
   Fetch at minimum: `title`, `status` (provider-native string), `url`.
   **Strip large fields** (description, comments, labels arrays) — the karma
   cache caps at 64 KB. If the MCP isn't available, skip this step and
   proceed with title/status omitted.

5. **POST the link** (idempotent — creates link, does NOT touch metadata):
   ```
   curl -s -X POST http://localhost:8000/sessions/<session_id>/tickets \
        -H 'Content-Type: application/json' \
        -d '{"ref":"<key>","provider":"<provider>","url":"<url>",
             "session_slug":"<slug>","source":"slash_command"}'
   ```

6. **PUT the metadata** (only if MCP fetch succeeded):
   ```
   curl -s -X PUT http://localhost:8000/tickets/<provider>/<key> \
        -H 'Content-Type: application/json' \
        -d '{"title":"<title>","status":"<status>",
             "metadata_json":"<stripped-json>"}'
   ```

7. **Confirm to the user** with a one-line summary.
```

The skill delegates the MCP lookup to the agent, so karma never needs creds.
If MCP isn't installed for that provider, we still record the link with bare
metadata; the user can backfill via the dashboard or another invocation.

**Why look up the session UUID from live-sessions instead of an env var?**
Claude Code custom commands don't expose a documented "current session UUID"
interpolation token. The live-sessions file is the most reliable source we
already maintain (see `hooks/live_session_tracker.py`). The `cwd` + recency
filter handles the multi-session-per-repo case correctly (you'll only have
one LIVE session per cwd at a time).

### Path 2 — Branch auto-detect (silent, metadata-less)

`hooks/ticket_branch_detector.py` runs on `SessionStart`:

```python
# Pseudocode
import json, re, sys, subprocess
from pathlib import Path
import urllib.request

payload = json.load(sys.stdin)             # captain-hook SessionStart event
session_uuid = payload.get("session_id")
cwd = payload.get("cwd")
if not (session_uuid and cwd):
    sys.exit(0)

config = load_config()                      # see "Config file" below
if not config.get("branch_detect_enabled", False):
    sys.exit(0)

branch = git_current_branch(cwd)            # 'feat/LINEAR-123-fix-login'
if not branch:
    sys.exit(0)

slug = lookup_slug_from_live_sessions(cwd)  # nullable; populated if known

for pattern in config["ticket_branch_patterns"]:
    m = re.search(pattern["regex"], branch)
    if not m:
        continue
    ref = m.group("key") if "key" in m.groupdict() else m.group(0)
    body = {
        "ref": ref,
        "provider": pattern["provider"],
        "session_slug": slug,
        "source": "branch",
    }
    post_karma(f"/sessions/{session_uuid}/tickets", body)
    break
```

The pattern `lookup_slug_from_live_sessions(cwd)` scans
`~/.claude_karma/live-sessions/*.json` for the entry matching `cwd`. If no
entry exists yet (live-sessions tracker runs concurrently and may write after
us), `slug` is `None` — that's fine; the dedup-on-resume falls back to the
per-UUID unique constraint.

The hook follows the prior-art pattern of
`hooks/session_title_generator.py:241` (`post_title()` already does
hook → `localhost:8000` POSTs via `urllib.request`). All errors are caught
and the hook exits 0 (silent) so it never blocks `SessionStart`. Errors are
appended to `~/.claude_karma/logs/ticket_branch_detector.log`.

### Path 3 — Dashboard manual

Two surfaces:

- **On `/sessions/[uuid]`** — a "Link ticket" input (paste URL or key) →
  `POST /sessions/{uuid}/tickets` with `source=dashboard`. Title/status start
  empty. Bare `#N` for GitHub is rejected with an inline error
  ("include the `owner/repo` prefix").
- **On `/tickets`** — an "Add ticket" form (paste URL) creates the `tickets`
  row standalone; from there, the user can multi-select sessions to link.

### URL / ref parser (shared)

`api/services/ticket_parser.py` — pure function, no I/O, no git shell-outs:

```python
def parse_ticket_ref(s: str, hint_provider: str | None = None) -> TicketRef | None:
    """Tries in order:
    1. Linear URL    linear.app/.../issue/ABC-123
    2. Jira URL      *.atlassian.net/browse/ABC-123
    3. GitHub URL    github.com/owner/repo/issues/N      → key='owner/repo#N'
    4. GitHub short  owner/repo#N                        → key='owner/repo#N'
    5. ALPHA-NUM key e.g. ABC-123 — requires hint_provider; never assumed.

    Returns TicketRef(provider, external_key, url) or None.

    A bare '#N' (no owner/repo) is NOT supported — the API server cannot
    resolve git remotes; callers must qualify GitHub refs themselves. The
    slash command does this from shell context; the branch hook composes
    from git remote in the hook process; the dashboard surfaces an error.
    """
```

This removes the v1-draft's `git remote get-url` fallback inside the parser,
which the critic correctly flagged as impossible from the API server (the
POST body has no `cwd` and uvicorn has no notion of the caller's directory).

### Endpoint behavior

#### `POST /sessions/{uuid}/tickets` — create link (idempotent)

Body: `{ref, provider?, url?, session_slug?, source}`. The body does NOT
include `title` or `status` — those are set exclusively via `PUT /tickets/...`.

```
BEGIN TRANSACTION;

1. ticket_ref = parse_ticket_ref(ref, hint_provider=provider)
   if ticket_ref is None → ROLLBACK, return 400 {error, hint}

2. ticket_id = upsert into tickets:
     INSERT INTO tickets (provider, external_key, url, first_seen_at)
     VALUES (?, ?, ?, datetime('now'))
     ON CONFLICT (provider, external_key) DO UPDATE
       SET url = excluded.url
     RETURNING id;

3. INSERT INTO session_tickets
        (session_uuid, session_slug, ticket_id, link_source, linked_at)
   VALUES (?, ?, ?, ?, datetime('now'))
   ON CONFLICT (session_uuid, ticket_id) DO UPDATE
     SET link_source = CASE
       -- precedence: slash_command (3) > dashboard (2) > branch (1)
       WHEN session_tickets.link_source = 'branch' AND excluded.link_source IN ('dashboard','slash_command')
         THEN excluded.link_source
       WHEN session_tickets.link_source = 'dashboard' AND excluded.link_source = 'slash_command'
         THEN excluded.link_source
       ELSE session_tickets.link_source
     END,
     session_slug = COALESCE(session_tickets.session_slug, excluded.session_slug)
   RETURNING id;

COMMIT;

Return 200 {link, ticket}.
```

The whole upsert runs in **one transaction** so concurrent POSTs can't see
half-state. `RETURNING id` is supported in SQLite 3.35+; the project already
uses modern SQLite features.

The `link_source` precedence rule means: a branch-detect link followed by a
user-confirmed slash command upgrades to `slash_command`; the reverse never
happens. Auditing "which links did the user explicitly confirm" works
cleanly.

`session_slug` is filled in on conflict if it was previously NULL — so a
hook that wrote without slug, followed by a slash command that knows the
slug, ends up populated.

#### `PUT /tickets/{provider}/{external_key}` — refresh metadata

Body: `{title?, status?, metadata_json?}`. Each field is independently
optional. Behavior:

```sql
UPDATE tickets
   SET title         = COALESCE(?, title),
       status        = COALESCE(?, status),
       metadata_json = COALESCE(?, metadata_json),
       metadata_updated_at = datetime('now')
 WHERE provider = ? AND external_key = ?;
```

`COALESCE` preserves existing non-null values when the caller passes `null`.
The slash command's degraded-mode fallback (MCP fetch failed → skip PUT)
relies on this.

Returns 200 `{ticket}` (full row) or 404 if the ticket isn't in the registry
(the caller forgot the POST first).

#### `DELETE /sessions/{uuid}/tickets/{ticket_id}` — unlink

Removes the `session_tickets` row. Does NOT delete the `tickets` row
(another session may still be linked).

#### Other read endpoints

| Method | Path | Purpose |
|---|---|---|
| GET | `/sessions/{uuid}/tickets` | List tickets linked to one session. |
| GET | `/tickets` | List all tickets with `session_count` per row. Query: `?provider=`, `?q=`. |
| GET | `/tickets/{provider}/{external_key}` | Ticket detail. |
| GET | `/tickets/{provider}/{external_key}/sessions` | Sessions linked to this ticket (joined with `sessions`). |
| PATCH | `/tickets/{provider}/{external_key}` | Manual edit of title/status from the dashboard (URL-only fallback). Same semantics as PUT but distinguished in the audit log. |

All ticket-centric routes use the stable `(provider, external_key)` pair as
the URL identifier, **not** the SQLite autoincrement `id`. URLs survive a
DB rebuild and are human-readable.

### Orphan cleanup

A `session_tickets` row whose `session_uuid` never appears in `sessions`
(e.g., session was killed before its JSONL was written) becomes an orphan.
Policy: delete orphans on a TTL of 7 days, via a periodic task in
`api/services/` (mirrors existing reconciler pattern). Implementation
detail for v1 plan: a simple `DELETE FROM session_tickets WHERE
session_uuid NOT IN (SELECT uuid FROM sessions) AND linked_at < datetime('now','-7 days')`
run from a startup hook or a cron-style task.

### Config file

`~/.claude_karma/config.json` (new):

```json
{
  "branch_detect_enabled": false,
  "ticket_branch_patterns": [
    {"regex": "(?P<key>[A-Z][A-Z0-9_]+-\\d+)", "provider": "linear"}
  ]
}
```

Loader (in `hooks/ticket_branch_detector.py`):

```python
import json
from pathlib import Path

DEFAULT_CONFIG = {
    "branch_detect_enabled": False,
    "ticket_branch_patterns": [],
}

def load_config() -> dict:
    path = Path.home() / ".claude_karma" / "config.json"
    if not path.exists():
        return DEFAULT_CONFIG
    try:
        return {**DEFAULT_CONFIG, **json.loads(path.read_text())}
    except Exception:
        return DEFAULT_CONFIG
```

**Opt-in by default.** `branch_detect_enabled=False` until the user creates
the config. This prevents surprise links on personal-projects directories
and contains the blast radius of a regex bug.

A future PR can add per-project overrides; out of scope for v1.

## API surface (full)

`api/routers/tickets.py`, registered in `api/main.py` with no prefix:

| Method | Path | Purpose | Idempotent |
|---|---|---|---|
| POST | `/sessions/{uuid}/tickets` | Create link. Body: `{ref, provider?, url?, session_slug?, source}`. Returns `{link, ticket}`. | Yes (link only; metadata untouched) |
| GET | `/sessions/{uuid}/tickets` | List tickets linked to one session. | Yes |
| DELETE | `/sessions/{uuid}/tickets/{ticket_id}` | Unlink. | Yes |
| PUT | `/tickets/{provider}/{external_key}` | Refresh metadata (agent-driven, post-MCP fetch). Body: `{title?, status?, metadata_json?}`. Returns `{ticket}` or 404. | Yes (per HTTP semantics — same input yields same state) |
| PATCH | `/tickets/{provider}/{external_key}` | Manual metadata edit from dashboard. | Yes |
| GET | `/tickets` | List with `session_count` per row. Query: `?provider=`, `?q=`. | Yes |
| GET | `/tickets/{provider}/{external_key}` | Ticket detail. | Yes |
| GET | `/tickets/{provider}/{external_key}/sessions` | Sessions linked to one ticket. | Yes |

Reads use `sqlite_read()` (from `api/db/connection.py:144`). Writes use
`get_writer_db()` (from `api/db/connection.py:45`) — the same pattern used
in `api/routers/sessions.py:1737` and `api/routers/admin.py:31`. Pydantic
models in `api/models/ticket.py` use `ConfigDict(frozen=True)`.

## Frontend surfaces

SvelteKit + Svelte 5 runes.

| Route / surface | What it shows |
|---|---|
| `/tickets` (new) | Table: provider icon · key · title (or `—`) · status · session count · last linked. Filter by provider; search by key or title. |
| `/tickets/[provider]/[external_key]` (new) | Header: ticket badge + click-through to provider URL. Body: list of linked sessions (reuses `SessionCard`) with project, model, time. |
| `/sessions/[uuid]` (existing) | New "Tickets" section near the top. Linked-ticket badges with unlink buttons; `<TicketLinkInput>` for adding more. |
| `/projects/[encoded_name]` (existing) | New "Tickets" tab/card. Tickets touched by any session in this project — derived join (`SELECT DISTINCT tickets.* FROM tickets JOIN session_tickets ON ... JOIN sessions ON sessions.uuid = session_tickets.session_uuid WHERE sessions.project_encoded_name = ?`). |

**Route param choice**: `[provider]/[external_key]` (not `[ticket_id]`)
because the SQLite autoincrement PK isn't a stable external identifier — a
DB rebuild would break all bookmarked URLs. Matches the repo's convention
of semantic slugs (`[session_slug]`, `[project_slug]`, `[plugin_id]`).

`<TicketBadge>` component (in `frontend/src/lib/components/`): provider
icon (lucide-svelte) + monospace key + optional title + click-through to
`url`. Three variants: `inline` (in lists), `card` (on ticket detail),
`pill` (on session cards).

`<TicketLinkInput>` (in `frontend/src/lib/components/`): text input +
optional provider dropdown (only shown if input parses as a bare key).
Calls `POST /sessions/{uuid}/tickets`. Optimistic update.

**Scaling note**: the `/tickets` index query is `GROUP BY ticket_id COUNT(*)`
over `session_tickets`. Acceptable through ~100K rows. If `session_tickets`
grows large (heavy branch-detect usage), add a materialized counter on
`tickets.session_count` updated via trigger. Out of scope for v1.

## Error handling

| Failure | Behavior |
|---|---|
| Slash command, MCP unavailable | Agent posts the link, skips the PUT; karma stores bare link. Agent tells user "linked, but couldn't fetch title". |
| Slash command, karma API down | Agent reports "couldn't reach karma at :8000". User can retry later via dashboard. |
| Slash command, live-sessions lookup fails | Agent tells user "karma can't see this session — is the live-session tracker hook installed?" — does NOT silently link to a wrong session. |
| Branch-detect hook, any error | Silent exit 0. Never blocks `SessionStart`. Errors logged to `~/.claude_karma/logs/ticket_branch_detector.log`. No retry queue — a 4-hour offline period during a feature branch means lost links. Acceptable for v1. |
| Branch-detect hook, slug lookup empty | Proceeds without slug. Falls back to per-UUID linking. Slug gets populated later if a slash command runs. |
| Parser can't recognize ref | API returns `400 {error, hint}`. Dashboard surfaces inline; slash-command agent reports it. |
| Bare GitHub `#N` from dashboard | 400 with hint "include `owner/repo` prefix". |
| Duplicate POST (same session + ticket) | Per upsert behavior: idempotent for link itself; `link_source` may upgrade per precedence rule. Returns 200. |
| Concurrent POSTs racing on same `(provider, external_key)` | Wrapped in one transaction with `INSERT ... ON CONFLICT DO UPDATE RETURNING`. SQLite serializes writers via the writer connection — no torn writes. |
| PUT with no prior POST | 404 — caller forgot to create the link first. |
| `metadata_json` over 64 KB | DB CHECK constraint fails → 400 returned to caller. Slash command should never trigger this (instructions say strip large fields), but it's a safety net. |

## Testing

| Layer | Tests | Path |
|---|---|---|
| Parser | Table-driven: every URL format, bare keys, ambiguous input, bare `#N` rejection, garbage. | `api/tests/test_ticket_parser.py` |
| Schema | (a) Fresh install applies SCHEMA_SQL and both tables exist + indices + CHECK constraints fire. (b) v10 → v11 upgrade applies the incremental block. (c) Replay (v11 → v11) is a no-op. | `api/tests/test_schema.py` |
| Endpoints | POST link / PUT refresh / DELETE unlink / GET list. Idempotency: re-POST yields same link, no spurious row. Precedence: branch → slash_command upgrades; slash_command → branch does not downgrade. PUT-before-POST = 404. Slug dedup: resumed sessions share one row. metadata cap rejection. | `api/tests/api/test_tickets.py` |
| Hook | Feed JSON payload via stdin, mock `git symbolic-ref`, assert POST. Negatives: no branch, no match, hook disabled, karma down (silent exit 0), config file missing (silent exit 0). | `hooks/tests/test_ticket_branch_detector.py` |
| Frontend | Playwright: (1) link from session page → see on `/tickets` → click through to detail; (2) branch-detect bare link (no metadata) → badge renders correctly; (3) unlink → row disappears; (4) URL-only fallback PATCH from dashboard. | `frontend/tests/` |

Test paths: hook tests live with the hook code under `hooks/tests/`, not
under `api/tests/`, matching the project structure (`hooks/` is at the repo
root, not inside `api/`).

## Risks accepted for v1

- **Loopback-only API.** No auth. A user with port-forwarding open exposes
  the karma DB to drive-by writes. Karma's existing API has no auth either —
  this feature inherits the same posture, doesn't make it worse.
- **No hook retry queue.** If karma is down when the branch-detect hook
  fires, the link is lost. Manual recovery via dashboard.
- **Slug-less branch-detect at very early SessionStart.** If `SessionStart`
  fires before `live_session_tracker.py` writes the live-sessions file, our
  hook can't populate slug. Resumed sessions linked in this window get
  per-UUID rows; the dashboard sees them as separate links. Cosmetic only.
- **`metadata_json` 64 KB cap.** Future heavy fields (long Jira descriptions)
  may be truncated.

## What's explicitly out of scope for v1

- **Write-back to providers** (no comments, no state moves).
- **Built-in provider adapters in karma backend** (karma never holds creds).
- **Auto-detection from user prompts.**
- **Status-change automation** (link → "In Progress", PR open → "In Review").
- **Webhooks / pull notifications.**
- **Per-project branch-detect config.**
- **Materialized `tickets.session_count`** (until rows justify it).
- **Linking subagents directly to tickets** (inherit from parent session).

## Verified facts (post-review)

- `SCHEMA_VERSION = 10` at `api/db/schema.py:12` → spec proposes v11. ✅
- `sqlite_read()` exists at `api/db/connection.py:144`. ✅
- `get_writer_db()` exists at `api/db/connection.py:45` and is the writer
  pattern (verified used in `api/routers/sessions.py:1737`,
  `api/routers/admin.py:31`). ✅ (The previous draft incorrectly referenced
  a nonexistent `sync_queries.py` — fixed.)
- `hooks/session_title_generator.py:241` already POSTs to `localhost:8000`
  from a hook via `urllib.request.post_title()` — prior art, not a new
  pattern. ✅
- `SessionCard` exists at `frontend/src/lib/components/SessionCard.svelte`. ✅
- `CORSMiddleware` allows `http://localhost:5173` and `http://localhost:3000`
  in `api/main.py:146-152`. No auth middleware. ✅
- `api/CLAUDE.md` confirms `ConfigDict(frozen=True)` for all models. ✅
- Existing routes use semantic slugs as params (`[session_slug]`,
  `[project_slug]`, `[plugin_id]`) — spec aligns by using
  `[provider]/[external_key]` instead of `[ticket_id]`. ✅

## Open questions

None blocking. All review findings are addressed inline above.
