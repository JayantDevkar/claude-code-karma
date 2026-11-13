# Live tracker: sessions and subagents stopped by a limit or API error

Status: draft for approval · 2026-11-13

## Intent

When a usage limit or API error ends a turn, Claude Code fires `StopFailure`
instead of `Stop`. Karma's live tracker doesn't listen for it, so the session
stays `LIVE` until some other hook moves it. Subagents are worse: a subagent
that dies without a `SubagentStop` (API error, user interrupt, killed process)
stays `running` forever, even after its session has ended. On the operator's
machine 5 such subagents exist: 2 died on API errors, 1 on a user interrupt,
2 when the process died.

This change makes the live view:

1. Show a session stopped by an API error or limit as **interrupted**, with
   the reason, until the operator resumes or the session ends.
2. Never show a subagent as `running` once its session has ended.

It is the second of three threads. Thread 1 (`limit-detection`, spec
`2026-11-13-api-error-turn-detection-design.md`) detects error turns in
transcripts. Thread 3 groups workflow agents under the Subagents tab.

## Goals

- `StopFailure` puts the session in a new state `INTERRUPTED`, status
  `interrupted`, carrying the error kind, code and message.
- `interrupted` doesn't decay to `stale` after 60s. It persists until the
  operator types again (`LIVE`), a turn finishes normally (`STOPPED`), the
  session ends (`ENDED`), or the process dies (reaper → `ENDED`).
- A `StopFailure` that names a subagent (`agent_id`) marks that subagent
  `error` and leaves the session state alone.
- A subagent still `running` when its session is ended (by any path) reads
  as `interrupted`.
- The `StopFailure` hook is documented in Tier 2 setup.

## Non-goals

- Reset time ("resets 11:30pm") as structured data. It comes from thread 1's
  transcript parser once that merges (follow-up, below). Until then the
  human-readable message from the hook already contains it as text when
  Claude Code includes it.
- Transcript parsing of any kind (thread 1 owns it).
- Workflow-agent grouping (thread 3).
- Adding `StopFailure` to `captain-hook`'s typed models or the `/hooks` page.
- The legacy copy `api/scripts/live_session_tracker.py` (unmaintained since the
  monorepo conversion; not what Tier 2 installs).
- Editing the operator's `~/.claude/settings.json`. The PR documents the hook;
  the operator registers it.

## Anti-goals

- A session that hit a limit and was resumed must not stay `interrupted`.
- An `interrupted` session must not stay live after its process is gone.
- No second error-detection path: no reading the transcript in the hook.

## Hook facts (Claude Code hooks reference, fetched 2026-11-13)

- `StopFailure` "runs instead of Stop when the turn ends due to an API error".
  Output and exit code are ignored.
- Payload adds `error` (one of `rate_limit`, `overloaded`,
  `authentication_failed`, `oauth_org_not_allowed`, `account_on_hold`,
  `billing_error`, `invalid_request`, `model_not_found`, `server_error`,
  `max_output_tokens`, `cloud_credential_error`, `unknown`), optional
  `error_details` (e.g. `"429 Too Many Requests"`) and optional
  `last_assistant_message` (the error string shown to the user).
- `Stop` doesn't fire on API errors or user interrupts.
- Not documented: whether `StopFailure` fires for subagents and whether it then
  carries `agent_id`. The design handles both (below).

## Approaches

1. **Hook sets the state; reset time later from thread 1's parser** (picked).
   Hook handles `StopFailure`; the API derives the subagent fix at read time;
   the reset time comes from the transcript parse the API already does for live
   sessions, once thread 1 lands. One detection path, no hook I/O.
2. Same, but the hook reads the transcript's last line for
   `quotaLimits.resetsAt`. Reset time immediately and no dependency, but a
   second detection path (thread 1's anti-goal). Rejected.
3. API only: inspect how each live transcript ends on every poll. Duplicates
   thread 1 and can't tell "stopped" from "still retrying". Rejected.

The operator chose a distinct `INTERRUPTED` state over "STOPPED + reason"
because a limit-stopped session is waiting on them and shouldn't fade to
stale after 60s.

## Design

### Hook: `hooks/live_session_tracker.py`

New branch in `_handle_event`:

```
StopFailure:
  agent_id present → mark_subagent_error(session_id, agent_id, stop_error)
  else             → write_state(session_id, "INTERRUPTED", data, stop_error=…)
```

`stop_error` (stored on the session or on the subagent record):

| Field | Source |
|---|---|
| `kind` | `"limit"` if `error == "rate_limit"`, else `"api_error"` (thread 1's names) |
| `code` | raw `error` |
| `details` | `error_details` or null |
| `message` | `last_assistant_message` or null |
| `at` | hook time, ISO UTC |

State rules in `write_state`:

- Only `UserPromptSubmit` (→ `LIVE`), `Stop` (→ `STOPPED`), `SessionEnd`
  (→ `ENDED`) and the reaper move a session out of `INTERRUPTED`.
  `PostToolUse` doesn't: after the turn has failed, a straggling tool hook (a
  background subagent's tool call carries the parent's `session_id`) would
  otherwise flip it back to `LIVE` and drop the reason. *(Builder-check call.)*
- `Notification(idle_prompt)` doesn't demote `INTERRUPTED` to `STALE`.
- Both skips use the existing in-lock `skip_if_current_state`, widened from one
  state to a set: `idle_prompt` skips `{WAITING, INTERRUPTED}`, `PostToolUse`
  skips `{INTERRUPTED}`.
- `stop_error` is sticky like `pending_permission_message`, cleared on `LIVE`
  and `STOPPED`. `ENDED` keeps it, so an ended session still says why it
  stopped.
- `StopFailure` for a session with no state file yet creates it, like every
  other `write_state` event does today.

Subagent with `agent_id`: set `status: "error"`, `completed_at`, `duration_ms`
(same math as `complete_subagent`), `stop_error`. If `SubagentStart` was never
seen, create the record the way `complete_subagent` does. A later
`SubagentStop` for the same agent keeps `error` (doesn't overwrite it with
`completed`). Builder's call: share the record-closing code with
`complete_subagent` instead of copying it.

Module docstring: add `INTERRUPTED` and `StopFailure` to the state and mapping
lists.

### API

- `api/models/live_session.py`: `SessionState.INTERRUPTED`,
  `SessionStatus.INTERRUPTED = "interrupted"`, `SubagentStatus.INTERRUPTED =
  "interrupted"` (`ERROR` already exists, unused until now). New frozen model
  `StopError {kind, code, details, message, at}`; `LiveSessionState.stop_error:
  Optional[StopError]`; same optional field on `SubagentState`.
- `api/routers/live_sessions.py` status mapping: `INTERRUPTED` →
  `interrupted`, no idle decay.
- Subagent read-time fix: when the session's computed status is `ended`, any
  subagent with `status == "running"` is reported as `interrupted`. Derived at
  read time like `stopped → stale`, so it covers every end path (`SessionEnd`,
  reaper, reconciler, `STARTING` timeout, old files already on disk) without
  touching the writers. Applied where subagent states are serialised for the
  live endpoints (builder locates the one place; if there are several, one
  helper).
- `api/schemas.py`: add `INTERRUPTED` / `interrupted` to the `Literal`s, add
  `stop_error` to `LiveSessionSummary` and the subagent schema.
- `api/services/live_session_store.py`: add `INTERRUPTED` to
  `_NON_TERMINAL_STATES` (reaper).
- `api/services/session_reconciler.py`: unchanged. It ends any session idle
  120s+ when *any* newer JSONL exists in the same project folder, so including
  `INTERRUPTED` would end a still-open interrupted session as soon as the
  operator opens another session in that project. The reaper (dead pid) and
  `SessionEnd` cover the real ends. *(Builder-check call.)*
- Subagents of a session that is `INTERRUPTED` (not ended) keep their reported
  status. They may still be running in the background, and nothing tells the
  API they aren't; once the session ends they read as `interrupted`.
  *(Builder-check call.)*

### Frontend

- `api-types.ts`: mirror the new status values and `stop_error`.
- `live-session-config.ts`: `interrupted` entry, warning colour, label
  "interrupted", no pulse (pulse means "act now"; a limit usually can't be
  acted on until it resets). Builder's call on the token.
- Live session card / terminal list / home strip: when `stop_error` is set,
  show a one-line reason under the status: `message` if present, else a label
  from `kind` ("Stopped by usage limit" / "Stopped by API error"), with `code`
  and `details` in the tooltip.
- Subagent badge/card (`SubagentTypeBadge`, `SubagentCard`,
  `ConversationHeader`, `ConversationView`'s finished check, `SubagentGroup`'s
  running count): handle `error` and `interrupted` as finished, not running.
  `error` uses the error colour with the reason in the tooltip; `interrupted`
  is muted.
- Every `Record<LiveSessionStatus, …>` and status-count site (`npm run check`
  finds them).

### Docs

- `SETUP.md` Tier 2: add `StopFailure` to the hook table and the
  `settings.json` snippet, noting the Claude Code version that added it if the
  builder can confirm it (else "recent Claude Code").
- `CLAUDE.md` hook table only if it lists the tracker's events (it lists 8
  generic ones; leave it unless one is stated wrong).

## Follow-up (after thread 1 merges)

`live_active_duration` already parses each live transcript through a cache.
Thread 1 adds `Session.api_error_summary` (`ended_by`, `ended_resets_at`,
`limit_hit_count`, `ended_turn_uuid`). Read it from that same parse and add
`resets_at` to the live `stop_error` when `kind == "limit"`, so the card can
show "resets 23:30" as a time and "reset passed" afterwards. Small PR; not here.

The same follow-up can take `kind` from `ended_by`. The hook can't tell a hard
refusal from other errors: Claude Code reports safeguard refusals as
`error: invalid_request`, and the hook payload has no `stop_reason`. So until
then the live view calls them `api_error`, while thread 1's session page calls
them `refusal`. Known and accepted; no text matching in the hook.

## Tests (synthetic fixtures only)

Hook (`hooks/tests/test_live_session_tracker.py`):

1. Flow: `SessionStart` → `UserPromptSubmit` → `StopFailure(rate_limit,
   message)` → state file is `INTERRUPTED` with `stop_error.kind == "limit"`
   and the message; then `UserPromptSubmit` → `LIVE` with `stop_error` null.
2. `idle_prompt` or `PostToolUse` after `StopFailure` keeps `INTERRUPTED` and
   `stop_error`.
3. `SessionEnd` after `StopFailure` → `ENDED`, `stop_error` kept.
4. `StopFailure` with `agent_id` → that subagent `error` with duration; session
   state unchanged; later `SubagentStop` keeps `error`.
5. `StopFailure(server_error)` → `kind == "api_error"`.

API:

6. Status: `INTERRUPTED` idle for 10 minutes → `interrupted`, not `stale`.
7. Live endpoint: ended session with one `running` and one `completed`
   subagent → `interrupted` and `completed`; a `LIVE` session's `running`
   subagent stays `running`.
8. Reaper: `INTERRUPTED` session with a dead pid → `ENDED`, `process_died`.

Frontend: no unit tests (lookups only); `npm run check` and `npm run lint`.

## Left to the builder

- Exact colour tokens, icon, and where the reason line sits on each card.
- Whether `stop_error.at` duplicates `updated_at` enough to drop it (keep it
  if `ENDED` overwrites `updated_at`, which it does).
- Locating the subagent serialisation sites in the live router.
