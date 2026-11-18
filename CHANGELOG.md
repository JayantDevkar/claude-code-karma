# Changelog

All notable changes to Claude Code Karma are documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/)
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- **The session timeline shows who sent each event.** Every event now
  carries its sender: you, Claude, a named agent, another Claude
  session, or Claude Code itself. Messages from other sessions, agents
  and Claude Code are no longer labelled "User prompt".
- **New timeline event kinds:**
  - **Messages** between agents and sessions, incoming and outgoing
    (`SendMessage` calls are shown as messages, with the recipient).
  - **Background reports** from agents, background commands, monitors,
    workflows and MCP tasks, linked to the agent they are about.
  - **Scheduled task fires** (wakeups and cron jobs).
  - **Context compaction**, with its trigger, token count and summary.
  - **Shell commands** you ran with `!`, with their output.
  - **Notices** Claude Code showed you: recaps, model fallback, remote
    control status and interruptions.
- **Prompts sent while Claude was working** now appear on the timeline,
  marked as such. They were missing before.
- **Named, coloured agents.** On the timeline, the Subagents tab and the
  agent page, an agent shows its teammate name, its type and its Claude
  Code colour instead of a raw id. The Subagents tab and agent page also
  show the spawn description, and the team and model when the agent has
  its own.
- **Spawn events link to named teammates.** Before, only agents with a
  plain hex id were linked to the agent they started.
- **API:** `TimelineEvent` gains `actor_name`, `actor_color` and
  `actor_agent_type`, two new `actor_type` values (`peer_session`,
  `system`) and seven new `event_type` values (`message`,
  `task_notification`, `scheduled_fire`, `compaction`, `shell_command`,
  `system_notice`, `system_context`). `GET /sessions/{uuid}/subagents`
  and the agent detail endpoint gain `name`, `color`, `team_name`,
  `model` and `description`.

### Changed

- **Timeline filters are grouped by who acts:** you, Claude, tools,
  agents, and Claude Code. Todos and Tasks are one **Tasks** chip,
  **Commands** includes `!` shell commands, and there are new
  **Messages**, **Background** and **Notices** chips.
- **System filter.** Reminders, a teammate's idle signals and other text
  added for Claude are left out of the timeline unless you select the
  **System** chip.
- **Skill instructions and slash-command output attach to their event.**
  A skill's instructions open with the skill event instead of showing as
  a separate prompt, and a built-in command shows its output.
- **A subagent's first message is its task prompt** from the session
  that started it, not a user prompt. Its `initial_prompt` in the API
  is plain text, without the `<teammate-message>` wrapper.
- **Timeline event ids changed** from `evt-<n>` to
  `evt-<entry uuid>-<n>`. An id stays the same while a live session
  grows.
- **The first start re-indexes every session** (schema v32). Message
  counts, initial prompts, and skill and command counts are
  recalculated. It runs in the background when the API starts and takes
  a couple of minutes for about a thousand sessions.

### Fixed

- **Entries written at the same timestamp were dropped.** When two user
  entries shared a timestamp, only the first was kept, so built-in
  commands, command output, task notifications, workflow task text and
  some tool results never reached the timeline. Entries are now merged
  only when they are parts of one prompt, such as a prompt and its
  image.
- **Tool error status was guessed from the word "error".** It now comes
  from the `is_error` flag Claude Code writes, so a file that mentions
  "error" is no longer marked failed and a failed command is no longer
  marked done.
- **A session's initial prompt could be a teammate's message.**
  Messages from agents, other sessions and Claude Code are now skipped
  when the initial prompt is chosen.
- **The agent page reported the type `_teammate`** for named agents. It
  now reports the agent's real type, the same one the Subagents tab and
  the timeline show.

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
- **GitHub PRs were stored with `/issues/N` URLs** instead of `/pull/N`.
  Cause: the ticket parser hard-coded `/issues/` in the canonical URL
  it built, throwing away which path segment the input URL had used.
  Fix: parser now captures `(?P<kind>issues|pull)` and uses the
  captured segment in the canonical URL. The frontend grew a small
  `PR` pill (with GitHub's pull-request glyph) next to the GH provider
  badge so issues and PRs are visually distinguishable everywhere.
  Old rows self-heal on re-link; users wanting immediate repair can hit
  the new `POST /admin/repair-github-urls` endpoint (see Upgrading).

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

**Optional: repair stale GitHub PR URLs.** If you linked GitHub PRs in
0.1.x, their stored URLs point at `/issues/N` even though they were
PRs. Links still work (GitHub redirects), but the new `PR` pill won't
show. Rows self-heal on re-link, or you can repair them in one shot:

```bash
curl -X POST http://localhost:8000/admin/repair-github-urls
# {"status":"ok","rewritten":N}
```

The repair is conservative — it only rewrites rows whose
`status='MERGED'` (a state unique to PRs). Open or closed-unmerged PRs
remain ambiguous from cached data alone and self-heal on next re-link.

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
