# Session ↔ Ticket Linking — Design

**Status:** Draft for review
**Date:** 2026-05-13
**Author:** Jayant Devkar (with Claude)

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

## Architecture overview

Karma stays a recipient/observer. Nothing in the karma backend talks to Linear,
Jira, or GitHub directly.

```
                                    ┌──────────────────────────┐
  user types "/link-ticket-to-      │  Agent (Claude Code)     │
  session LINEAR-123" in session    │  invokes skill →         │
                ─────────────────►  │  fetches title/status    │
                                    │  via Linear/GitHub MCP   │
                                    └────────────┬─────────────┘
                                                 │ POST /sessions/{uuid}/tickets
                                                 │   {ref, url, title, status, source}
                                                 ▼
git checkout feat/LINEAR-123   ┌─────────────────────────────────────┐
       │                       │  Karma API (FastAPI)                │
       ▼                       │  - URL parser (provider + key)      │
SessionStart hook              │  - Idempotent upsert into           │
ticket_branch_detector.py ───► │    tickets + session_tickets        │
(bare-ref, no metadata)        └──────────────┬──────────────────────┘
                                              ▼
dashboard "Link ticket" ───►   ~/.claude_karma/metadata.db (SQLite)
input on /sessions/[uuid]                       │
                                                ▼
                                Frontend: /tickets, /tickets/[id],
                                badges on session/project pages
```

### Components

1. `api/db/schema.py` — schema migration v11 adds two tables (current version is 10).
2. `api/services/ticket_parser.py` — pure function: ref/URL → `(provider, external_key, url)`.
3. `api/models/ticket.py` — Pydantic models (`Ticket`, `SessionTicketLink`, `TicketRef`).
4. `api/routers/tickets.py` — REST endpoints, registered in `main.py`.
5. `api/db/queries.py` — new functions for link/unlink/list/upsert.
6. `hooks/ticket_branch_detector.py` — SessionStart hook, posts bare ref if branch matches a configured pattern. Silent on any failure.
7. `~/.claude/commands/link-ticket-to-session.md` — slash command driving the agent's MCP-fetch + karma-POST flow. Installed via setup script or manually.
8. Frontend additions in `frontend/src/routes/`:
   - `tickets/+page.svelte` (index)
   - `tickets/[ticket_id]/+page.svelte` (detail)
   - `<TicketBadge>` component (3 variants: inline, card, pill)
   - `<TicketLinkInput>` component (paste URL or key + provider hint)
   - Updates to `sessions/[uuid]/+page.svelte` (tickets section)
   - Updates to `projects/[encoded_name]/+page.svelte` (tickets tab/card)

No new Python or npm dependencies.

## Data model

Two new tables, added in schema migration v11. No FK to `sessions` (it's a
JSONL-mirror table and may not exist yet when the branch-detect hook fires at
`SessionStart`). Soft references via `session_uuid TEXT` follow the existing
reconciler pattern.

```sql
CREATE TABLE IF NOT EXISTS tickets (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  provider TEXT NOT NULL,            -- 'linear' | 'jira' | 'github' | 'other'
  external_key TEXT NOT NULL,        -- 'LINEAR-123' | 'PROJ-45' | 'owner/repo#42'
  url TEXT NOT NULL,
  title TEXT,                        -- agent-supplied (via MCP) or user-edited
  status TEXT,                       -- agent-supplied provider-native string
  metadata_json TEXT,                -- raw MCP payload, for future use
  metadata_updated_at TIMESTAMP,     -- when title/status were last refreshed
  first_seen_at TIMESTAMP NOT NULL,
  UNIQUE(provider, external_key)
);

CREATE INDEX IF NOT EXISTS idx_tickets_provider ON tickets(provider);

CREATE TABLE IF NOT EXISTS session_tickets (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  session_uuid TEXT NOT NULL,        -- soft ref, no FK
  ticket_id INTEGER NOT NULL,
  link_source TEXT NOT NULL,         -- 'branch' | 'slash_command' | 'dashboard'
  linked_at TIMESTAMP NOT NULL,
  FOREIGN KEY (ticket_id) REFERENCES tickets(id) ON DELETE CASCADE,
  UNIQUE(session_uuid, ticket_id)
);

CREATE INDEX IF NOT EXISTS idx_session_tickets_session ON session_tickets(session_uuid);
CREATE INDEX IF NOT EXISTS idx_session_tickets_ticket  ON session_tickets(ticket_id);
```

### Constraint rationale

- **`UNIQUE(provider, external_key)`** — exactly one `tickets` row per
  real-world ticket; linking from multiple sessions reuses the row.
- **`UNIQUE(session_uuid, ticket_id)`** — re-invoking the slash command on the
  same session for the same ticket is a no-op. Use `INSERT OR IGNORE` to
  preserve the original `linked_at`.
- **`link_source`** — auditable distinction between human-confirmed
  (`slash_command`, `dashboard`) and auto-derived (`branch`) links. The
  dashboard can offer a filter to hide branch-detected noise.
- **`metadata_json`** — raw MCP payload future-proofs for assignee, labels, due
  date, etc., without further schema migrations.
- **Resumed sessions** get separate `session_uuid` rows. The existing
  `api/services/session_relationships.py` service can group them on display so
  a tickets-detail page can collapse a resume-chain into one "session" if
  desired.

## Link establishment

All three paths converge on `POST /sessions/{uuid}/tickets`. The endpoint does
the dedup; callers provide the richest payload they can.

### Path 1 — Slash command (richest payload, agent-driven)

`~/.claude/commands/link-ticket-to-session.md` (illustrative; exact template
syntax to be verified against Claude Code custom-command docs during
implementation):

```markdown
---
description: Link the current Claude Code session to a ticket and cache its title/status in karma
argument-hint: <ticket-ref-or-url>
---

You are linking the current Claude Code session to ticket: **$ARGUMENTS**

Steps:
1. Determine the current session's UUID (use the available env var or look it
   up from the running JSONL — verify per Claude Code custom-command docs).
2. Parse $ARGUMENTS — it may be a URL or a short ref (e.g. `LINEAR-123`,
   `PROJ-45`, `owner/repo#42`, `https://linear.app/.../issue/ABC-123`).
3. Identify the provider (linear | jira | github).
4. Use the appropriate MCP server to fetch the ticket — Linear MCP for linear,
   Atlassian MCP for jira, GitHub MCP for github. Fetch at minimum: `title`,
   `status`, `url`. If the MCP isn't available, proceed with title/status
   omitted.
5. POST to karma:
   curl -s -X POST http://localhost:8000/sessions/<uuid>/tickets \
        -H 'Content-Type: application/json' \
        -d '{"ref":"<key>","url":"<url>","provider":"<provider>",
             "title":"<title>","status":"<status>","source":"slash_command"}'
6. Confirm success to the user with a one-line summary.
```

The skill delegates the MCP lookup to the agent, so karma never needs creds. If
MCP isn't installed for that provider, we still record the link with bare
metadata; the user can backfill via the dashboard or another invocation.

**Implementation note:** the exact mechanism for the agent to obtain its own
session UUID inside a custom command (env var, slash-command frontmatter, or
parsing the JSONL path) needs verification — the writing-plans phase will use
context7 / WebFetch against Claude Code docs to pin this down.

### Path 2 — Branch auto-detect (silent, no metadata)

`hooks/ticket_branch_detector.py` runs on `SessionStart`:

```python
# Pseudocode
payload = json.load(sys.stdin)              # captain-hook SessionStart event
cwd = payload["cwd"]
branch = git_current_branch(cwd)            # 'feat/LINEAR-123-fix-login'
if not branch:
    sys.exit(0)

for pattern in load_config("ticket_branch_patterns"):
    m = re.search(pattern["regex"], branch)
    if m:
        ref = m.group("key") if "key" in m.groupdict() else m.group(0)
        post_karma(
            f"/sessions/{payload['session_id']}/tickets",
            {"ref": ref, "provider": pattern["provider"], "source": "branch"},
        )
        break
```

Config lives in `~/.claude_karma/config.json`:

```json
{
  "ticket_branch_patterns": [
    {"regex": "(?P<key>[A-Z][A-Z0-9_]+-\\d+)", "provider": "linear"}
  ],
  "branch_detect_enabled": true
}
```

Bare-ref only — no title until an agent runs the slash command, the user clicks
"refresh" on the dashboard, or someone edits the title inline. The hook is
silent on any error (exit 0) so it never blocks `SessionStart`. Errors are
logged to `~/.claude_karma/logs/ticket_branch_detector.log`.

### Path 3 — Dashboard manual

Two surfaces:

- **On `/sessions/[uuid]`** — a "Link ticket" input (paste URL or key) →
  `POST /sessions/{uuid}/tickets` with `source=dashboard`. Title/status start
  empty.
- **On `/tickets`** — an "Add ticket" form (paste URL) creates the `tickets`
  row standalone; from there, the user can multi-select sessions to link.

### URL / ref parser (shared)

`api/services/ticket_parser.py` — pure function, no I/O:

```python
def parse_ticket_ref(s: str, hint_provider: str | None = None) -> TicketRef | None:
    """Tries in order:
    1. Linear URL    linear.app/.../issue/ABC-123
    2. Jira URL      *.atlassian.net/browse/ABC-123
    3. GitHub URL    github.com/owner/repo/issues/N
    4. github short  owner/repo#N
    5. ALPHA-NUM key e.g. ABC-123 — requires hint_provider
    Returns TicketRef(provider, external_key, url) or None.
    """
```

A bare `ABC-123` is ambiguous (Linear or Jira), so the parser requires
`hint_provider` for the short-key case. The slash command supplies it from
agent-side detection; branch-detect supplies it from the matched pattern's
`provider` field; the dashboard makes the user pick from a small dropdown if
the input is a bare key.

For GitHub, when only `#N` is supplied (no `owner/repo`), the parser falls back
to reading `git remote get-url origin` from the session's `cwd` if available;
otherwise returns `None` and the caller surfaces the error.

### Endpoint behavior

`POST /sessions/{uuid}/tickets`:

1. `parse_ticket_ref(ref, hint_provider=provider)` → `TicketRef` or **400**.
2. `INSERT OR IGNORE` into `tickets` keyed on `(provider, external_key)`.
3. If the request includes `title`/`status` and the row already exists,
   `UPDATE` those fields and `metadata_updated_at` so a fresh slash-command
   invocation refreshes the cache. Existing non-null values are not overwritten
   with `null` (so a degraded slash-command call doesn't wipe earlier data).
4. `INSERT OR IGNORE` into `session_tickets` keyed on `(session_uuid, ticket_id)`.
5. Return `200 {link, ticket}` either way (idempotent).

## API surface

`api/routers/tickets.py`, registered in `main.py`.

| Method | Path | Purpose |
|---|---|---|
| POST | `/sessions/{uuid}/tickets` | Link ticket → session. Body: `{ref, provider?, url?, title?, status?, source}`. Idempotent. Returns `{link, ticket}`. |
| GET | `/sessions/{uuid}/tickets` | List tickets linked to one session. |
| DELETE | `/sessions/{uuid}/tickets/{ticket_id}` | Unlink. |
| GET | `/tickets` | List all tickets with `session_count` per row. Query: `?provider=`, `?q=` (search key/title). |
| GET | `/tickets/{ticket_id}` | Ticket detail. |
| GET | `/tickets/{ticket_id}/sessions` | Sessions linked to one ticket (joined with `sessions` for title/project). |
| PATCH | `/tickets/{ticket_id}` | Manual edit of `title` / `status` (for the URL-only fallback case). |

Reads use `sqlite_read()` from `api/db/connection.py`. Writes extend
`api/db/queries.py` following the `sync_queries.py` style. Pydantic models in
`api/models/ticket.py` use `ConfigDict(frozen=True)` per the existing pattern.

## Frontend surfaces

SvelteKit + Svelte 5 runes.

| Route / surface | What it shows |
|---|---|
| `/tickets` (new) | Table: provider icon · key · title (or `—`) · status · session count · last linked. Filter by provider; search by key or title. |
| `/tickets/[ticket_id]` (new) | Header: ticket badge + click-through to provider URL. Body: list of linked sessions (reuses existing `SessionCard`) with project, model, time. |
| `/sessions/[uuid]` (existing) | New "Tickets" section near the top. Linked-ticket badges with unlink buttons; `<TicketLinkInput>` for adding more. |
| `/projects/[encoded_name]` (existing) | New "Tickets" tab/card. Tickets touched by any session in this project — derived join, no extra storage. |

`<TicketBadge>` component: provider icon (lucide-svelte) + monospace key +
optional title + click-through to `url`. Three variants: `inline` (in lists),
`card` (on ticket detail), `pill` (on session cards).

`<TicketLinkInput>`: text input + optional provider dropdown (only shown if
input parses as a bare key). Calls `POST /sessions/{uuid}/tickets`. Optimistic
update.

## Error handling

| Failure | Behavior |
|---|---|
| Slash command, MCP unavailable | Agent posts with `title` / `status` omitted; karma stores the bare link. User sees "linked, but couldn't fetch title". |
| Slash command, karma API down | Agent reports "couldn't reach karma at :8000". User can retry later via dashboard. |
| Branch-detect hook, any error | Silent exit 0. Never blocks `SessionStart`. Errors logged to `~/.claude_karma/logs/ticket_branch_detector.log`. |
| Parser can't recognize ref | API returns `400 {error, hint}`; dashboard surfaces the hint inline; slash-command agent reports it. |
| Duplicate link (same session + ticket) | `INSERT OR IGNORE` → returns existing row, 200. |
| Two sessions, same ticket | Reuses `tickets` row via `(provider, external_key)` unique. |
| Slash-command POST sends `null` title to a row with non-null title | Endpoint preserves existing non-null values; degraded fetches never wipe cached data. |

## Testing

| Layer | Tests |
|---|---|
| Parser | `api/tests/test_ticket_parser.py` — table-driven cases for every URL format, bare keys, ambiguous input, garbage. |
| Schema | `api/tests/test_schema.py` — v11 migration creates both tables, indices, and unique constraints; replays cleanly on an existing DB. |
| Endpoints | `api/tests/api/test_tickets.py` — link/unlink/list/refresh/dedup/idempotency. Uses existing tmp-DB fixtures. |
| Hook | `api/tests/test_ticket_branch_detector.py` — feed JSON payload via stdin, mock `git symbolic-ref`, assert POST. Negative: no branch, no match, no karma reachable, hook disabled. |
| Frontend | One playwright journey: link a ticket from session page → see it on `/tickets` → click through to detail page. |

## Future work (not in v1)

- **Built-in provider adapters in karma backend.** The Pydantic models and
  endpoint contracts are designed so a future `MetadataProvider` interface can
  be added without breaking changes — `POST /tickets/{id}/refresh` could
  delegate to a registered adapter instead of (or in addition to) the
  agent-driven slash command.
- **Write-back to providers.** Adding `POST /tickets/{id}/comment` and the
  corresponding adapter methods would be additive.
- **Auto-detection from chat prompts.** If we ever want it, a hook on
  `UserPromptSubmit` with a configurable regex could feed `source=auto_prompt`
  links. Excluded from v1 to avoid noise.
- **Status-change automation** (link → "In Progress", PR open → "In Review",
  merge → "Done") would require adapter write methods.
- **Subagent-level links.** Currently subagents inherit their parent session's
  links via the existing join. A separate table could be added if needed.

## Open questions

None blocking. Confirmed during brainstorming:

- Link establishment paths: branch + slash command + dashboard ✅
- Data flow: read-only ✅
- Storage: cache + on-demand refresh, agent-sourced ✅
- Cardinality: many-to-many, no primary ✅
- Agent awareness: pure observer; MCP handles in-session needs ✅
- Metadata source: agent + MCP (Approach C) ✅
