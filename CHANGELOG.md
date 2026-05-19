# Changelog

All notable changes to Claude Code Karma are documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/)
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.2.0] — 2026-05-19

The "tickets" release. Karma now understands work as well as activity:
attach Linear / Jira / GitHub Issues to Claude Code sessions, then see
the dashboard pivot around tickets the same way it pivots around projects.

### Added

- **Session ↔ Ticket linking** for Linear, Jira, and GitHub Issues.
  Karma stays read-only — it stores the link and caches metadata, never
  writes back to your ticket provider.
- **Three ways to link a session to a ticket:**
  - **Dashboard paste** — open a session, paste a ticket URL or key into
    the Tickets section, done.
  - **Slash command / skill** — `/link-ticket-to-session ABC-123` in a
    Claude Code session. The agent fetches title + status via your
    Linear / Atlassian / GitHub MCP server (if installed) and posts the
    link to karma. Honors `KARMA_API_URL` for non-default hosts.
  - **Branch-name auto-detect** (opt-in hook) — when you start a session
    on `feat/LINEAR-123-foo`, the link is created automatically. Silent
    on every failure; never blocks `SessionStart`.
- **`/tickets`** index page with provider, project, and search filters.
- **`/tickets/{provider}/{key}`** detail page listing every linked
  session for a ticket, with live-session enrichment for unindexed
  active sessions.
- **Tickets tab on every project page** showing every ticket touched by
  any session in that project — and across **every checkout of the same
  repo** (worktrees, subdir CWDs, submodules) via the new `git_identity`
  column. So a session linked from `claude-karma/frontend/` shows the
  ticket on the main `claude-karma` project too.
- **GitHub key heuristic** — tickets like `owner/repo#42` surface under
  any project whose `git_identity` is `owner/repo`, even if no local
  session has linked them yet. Useful when a teammate has linked the
  ticket on a different machine.
- **Cross-encoded ticket aggregation** powered by `projects.git_identity`
  (canonical `owner/repo` lowercase, derived from `git remote get-url
  origin` at index time). Lets karma treat every checkout of the same
  repo as one logical project for ticket views.

### Changed

- **Frontend route param renamed `[project_slug]` → `[project_id]`.**
  The route accepts either form (slug or `encoded_name`), so existing
  URLs and bookmarks continue to work. The new name is honest about
  what it accepts.
- **All API endpoints with a project filter now accept either form**
  uniformly via the new `safely_resolve_project()` helper. Applied to
  `/tickets`, `/skills`, `/skills/usage`, `/commands` (5 endpoints),
  `/agents` filters, and `/live-sessions/project/{id}`. Endpoints that
  previously matched `encoded_name` exactly and returned an empty list
  for slugs now resolve cleanly.

### Fixed

- **`/projects → card → Tickets tab` showed empty** for sessions linked
  via the dashboard. Cause: project cards link via slug, the tickets
  API matched `encoded_name` exactly. Fix: unified data flow with a
  clean "slug at the boundary, encoded_name inside" architecture across
  every project-by-identifier endpoint. Locked in by a regression test.

### Internal

- **Schema v12.** Adds `projects.git_identity TEXT` + index. Migration
  runs automatically on first start (idempotent against any phantom
  column from out-of-band branches) and nudges session mtimes so the
  periodic indexer backfills `git_identity` within ~5 minutes. To
  populate immediately: `POST /admin/reindex`.
- **New service module** `api/services/git_identity.py` —
  `normalize_git_url()` (pure parser, handles https / ssh / scp-style
  with or without `.git`) and `read_git_identity()` (timeout-guarded
  `git remote get-url origin` shellout).
- **New helper** `safely_resolve_project()` in `api/routers/projects.py`
  — filter-friendly variant of `resolve_project_identifier` that returns
  the raw input verbatim on unknown identifiers (so downstream queries
  yield empty lists, not 404s).
- **New frontend helper** `src/lib/utils/project-url.ts` —
  `projectHref()` + `projectHrefFromSession()` centralize the
  `slug || encoded_name` policy in one place. Migrated 5 call sites
  (`GlobalSessionCard`, `LiveSessionsTerminal`, `LiveSessionsSection`,
  `CommandPalette`, plans page, `ConversationOverview`).

### Tests

- 1580 passing (was 1474). Added: 40 ticket endpoint tests, 23
  `normalize_git_url` parser tests, 7 `safely_resolve_project` /
  `resolve_project_identifier` unit tests, plus parser, enrichment,
  branch-detector hook (299 LOC), and schema-migration regression tests.

### Upgrading from 0.1.x

No manual steps required. On first start:

1. Schema migrates v11 → v12 automatically. The migration is idempotent
   and safe to re-run.
2. `projects.git_identity` is backfilled by the periodic indexer (default
   interval: 5 minutes). To trigger immediately:
   `curl -X POST http://localhost:8000/admin/reindex`.
3. The route rename `[project_slug]` → `[project_id]` is internal —
   existing URLs continue to work.

If you used the syncthing prototype in an earlier branch, the
`sync_*` tables and any `jayantdevkar-claude-code-karma`-style project
rows are left over from that prototype (not part of this branch's
schema). Safe to delete manually if you want a clean dashboard:

```sql
DROP TABLE IF EXISTS sync_subscriptions;
DROP TABLE IF EXISTS sync_removed_members;
DROP TABLE IF EXISTS sync_events;
DROP TABLE IF EXISTS sync_projects;
DROP TABLE IF EXISTS sync_members;
DROP TABLE IF EXISTS sync_teams;
DELETE FROM projects WHERE encoded_name NOT LIKE '-%';
```

---

## [0.1.0] — Earlier

Initial public release. The first 224 stars 🌟.

See [git history](https://github.com/JayantDevkar/claude-code-karma/commits/main)
for changes prior to the introduction of this changelog.
