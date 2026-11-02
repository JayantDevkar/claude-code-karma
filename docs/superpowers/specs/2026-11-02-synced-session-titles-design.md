# Titles for synced sessions — design

## Problem

The `session_title_generator.py` hook titles a session on `SessionEnd` and POSTs the
title to the Karma API on `localhost:8020`. Sessions that run on another machine and
reach Karma through an extra session root (Syncthing, rsync, ...) never get a title:

- The other machine (a VPS, say) runs no Karma API, so the POST fails silently.
- Claude Code launched through the Agent SDK only loads hooks from the setting sources
  its caller enables, so the hook may not run there at all.
- The title is not written to the JSONL, so syncing the file later carries nothing.

Synced sessions do end cleanly: a session that exits normally ends its JSONL with a
`{"type": "cost-state", ...}` line. A crashed or killed session does not.

## Goal

Karma titles synced sessions itself, on the machine that runs Karma, once they have
ended. Each title costs one Haiku call, so the feature is **off unless the user turns
it on per root**, and it never titles a backlog on its own.

## Non-goals

- No UI toggle. Turning it on is a config edit, like installing the hook.
- No automatic backlog. Older sessions are titled only by the manual backfill script.
- No git context for synced sessions (see "Why no git context").
- No change to how the hook titles local sessions.

## Design

### 1. Opt-in per root

`extra-roots.json` (and `CLAUDE_KARMA_EXTRA_ROOTS`) entries get an optional key:

```json
[{"name": "vps", "path": "D:/Sync/vps/.claude", "auto_titles": true}]
```

`_parse_root()` reads it into a new `SessionRoot.auto_titles: bool = False`, next to
`match_by_name`. Missing or false means off: no Haiku call, no DB write.

### 2. Which sessions qualify

A session is titled automatically when all of these hold:

- `source_root` names a root with `auto_titles` on.
- `session_titles` is empty (no compaction summary, no earlier title).
- `title_attempted_at IS NULL`.
- `end_time` is within the last 24 hours (`AUTO_TITLE_WINDOW_HOURS = 24`).
- The session's JSONL ends with a `cost-state` line (it ended cleanly, so it will not
  grow further and its first prompt is final).

The 24-hour window bounds the cost of turning the flag on: at most one day of sessions.
No "enabled at" timestamp needs to be stored. A session that the sync tool delivers more
than 24 hours after it ended is skipped; the manual backfill (section 6) catches it.

### 3. Prompt source

The title is generated from the indexed `sessions.initial_prompt`, not re-extracted from
the JSONL. The indexer's `prompt_from_user_message()` already skips
`<local-command-caveat>` messages, and once the spawn-relay fix (PR #148) lands it
returns a coordinator's `<note>` body for `<relay reason="spawn">` first messages
instead of the wrapper. This design depends on that PR.

### 4. Title generation: reuse the hook

`api/services/synced_titles.py` imports `generate_title()` from
`hooks/session_title_generator.py` (the module is loaded by path from the repo's
`hooks/` dir; the hook stays a standalone script on Python 3.9) and calls
`generate_title(initial_prompt, None, None)`: Haiku through `claude -p`, falling back to
the truncated prompt when the CLI fails. If the hook module cannot be loaded, the
service logs one warning and does nothing.

The title is stored through the same code path as `POST /sessions/{uuid}/title`: that
endpoint's body moves into a helper (`set_session_title_record(uuid, title)`) that both
the endpoint and the service call. It updates `SessionTitleCache` and SQLite.

### 5. Trigger and attempt tracking

- `run_periodic_sync()` calls `title_synced_sessions(conn)` in a worker thread
  (`asyncio.to_thread`) after each `sync_all_projects()` pass. Calls run one at a time
  and at most `AUTO_TITLE_BATCH = 20` sessions per pass, so a pass stays bounded.
- Schema **v28** (PRs #148 and #149 take v26 and v27) adds
  `sessions.title_attempted_at TEXT`. The service sets it before calling Haiku, whatever
  the outcome, so each session gets at most one call. Rows are not reset on reindex.
- A session indexed from this machine (`source_root IS NULL`) is never touched; the
  hook owns it.

### 6. Manual backlog

`api/scripts/backfill_titles.py` gets `--synced`: only sessions with
`source_root IS NOT NULL`. It ignores `auto_titles`, the 24-hour window and
`title_attempted_at` (the user runs it on purpose). `--dry-run` and `--limit` already
exist for checking the count before spending. The script switches to the hook's
`generate_title()` too, removing its own copy of the prompt and Haiku call.

### 7. Docs

`SETUP.md`'s extra-roots section documents `auto_titles`, its cost (one Haiku call per
ended session through the local `claude` login), the 24-hour window, and the backfill
command for older sessions.

## Why no git context

The hook prefers the latest commit message over Haiku. For synced sessions Karma often
maps the remote project to a local checkout with the same git identity, so `git log`
there is possible, but it gives wrong answers:

- The local checkout only has the remote machine's commits after a `git fetch`. Karma
  would have to fetch in the user's repo, a network call that moves their refs.
- Commits from both machines usually share one committer identity, and several remote
  sessions can work on the same branch at once, so a time window cannot tell which
  session made a commit.
- The transcript is no fallback: `git commit -q` prints no `[branch hash] msg` line.

Haiku on the first prompt is used instead.

## Error handling

- `claude` CLI missing or failing: the hook's fallback title (truncated prompt).
- No `initial_prompt`: skip and mark attempted.
- JSONL unreadable while checking for `cost-state`: skip without marking, retry next pass.
- Any exception in a pass: log a warning; the periodic sync loop keeps running.

## Testing

Haiku is stubbed in every test.

1. Flow: a synced root with `auto_titles` on, one session that ended an hour ago with a
   relay first prompt and a `cost-state` end. After a sync plus a titling pass, the
   session has exactly one title from the note text. A second pass makes no Haiku call.
2. Guards: root without `auto_titles`, session without `cost-state`, session ended 25
   hours ago, local session: no Haiku call, no title.
3. Backfill `--synced`: titles an old synced session that the automatic pass skipped.
