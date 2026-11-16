# Live Tracker Interruptions Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Sessions stopped by an API error or usage limit show as `interrupted` with the reason, and subagents never stay `running` after their session ended.

**Architecture:** The hook (`hooks/live_session_tracker.py`) handles `StopFailure` and writes a new `INTERRUPTED` state plus a `stop_error` record. The API maps it to status `interrupted` (no idle decay), reports `running` subagents of ended sessions as `interrupted` at read time, and lets the reaper end dead `INTERRUPTED` sessions. The frontend adds the new status values and a one-line reason.

**Tech Stack:** Python 3.9+ hook script, FastAPI + Pydantic 2 API, SvelteKit 2 / Svelte 5 frontend, pytest.

**Spec:** `docs/superpowers/specs/2026-11-13-live-tracker-interruptions-design.md`

## Global Constraints

- Hook code runs on Python 3.9+ (no `match`, no `X | Y` types at runtime; `from __future__ import annotations` is already in the file).
- The hook must never raise to Claude Code: keep everything inside the existing `main()` try/except.
- State name `INTERRUPTED`, status `interrupted`, subagent statuses `error` and `interrupted`.
- `stop_error` = `{kind, code, details, message, at}`; `kind` is `"limit"` if `error == "rate_limit"`, else `"api_error"`.
- No transcript reading in the hook. No change to `api/services/session_reconciler.py`.
- Tests use synthetic data only (ids like `s-int-1`, `agent-x1`; no real paths, project names or transcript text).
- Test rules: one flow test per behaviour, guards at their limits, no tests for wiring or wording.

## Review Focus

1. `PostToolUse` arriving after `StopFailure` (background subagent tool call) must leave `INTERRUPTED` and `stop_error` intact. Test in Task 1.
2. `StopFailure` payload with no `last_assistant_message` / `error_details` (both optional) must still write a valid `stop_error` with nulls. Test in Task 1.
3. A `SubagentStop` after a subagent `StopFailure` must not turn `error` back into `completed`. Test in Task 1.
4. Old state files with no `stop_error` and `STARTING` sessions past `STARTING_TIMEOUT` (computed `ended`) must still parse, and their `running` subagents read `interrupted`. Test in Task 2.
5. `active_subagent_count` for an ended session must be 0, not the stale `running` count (the live cards show this number). Test in Task 2.

---

### Task 1: Hook handles `StopFailure`

**Files:**
- Modify: `hooks/live_session_tracker.py` (docstring `:8-23`, `complete_subagent` `:308-362`, `write_state` `:365-443`, `_handle_event` `:463-556`)
- Test: `hooks/tests/test_live_session_tracker.py`

**Interfaces:**
- Produces: state file fields `state: "INTERRUPTED"`, `stop_error: {kind, code, details, message, at} | null` on the session; subagent record `status: "error"` with `stop_error`. Task 2 reads these.
- `write_state(..., stop_error: Optional[Dict[str, Any]] = None, skip_if_current_state: Optional[Collection[str]] = None)` — `skip_if_current_state` becomes a set/tuple of states (update the existing `idle_prompt` caller to `("WAITING", "INTERRUPTED")`).
- `_stop_error(hook) -> Dict[str, Any]` builds the record.
- `mark_subagent_error(session_id: str, agent_id: str, stop_error: Dict[str, Any]) -> None`.

- [ ] **Step 1: Write the failing tests** (reuse `live_dir` fixture and the `resolve_terminal` monkeypatch pattern)

```python
def _stop_failure(sid, error="rate_limit", **extra):
    return {"hook_event_name": "StopFailure", "session_id": sid, "error": error, **extra}

def test_stop_failure_interrupts_until_next_prompt(live_dir, monkeypatch):
    # UserPromptSubmit → StopFailure(rate_limit, message, details) → state INTERRUPTED,
    # stop_error.kind == "limit", code == "rate_limit", message/details stored.
    # Then UserPromptSubmit → state LIVE, stop_error is None.

def test_stop_failure_survives_idle_prompt_and_post_tool_use(live_dir, monkeypatch):
    # StopFailure, then Notification(idle_prompt), then PostToolUse
    # → still INTERRUPTED, stop_error unchanged.

def test_session_end_keeps_stop_error(live_dir, monkeypatch):
    # StopFailure(server_error) then SessionEnd(reason="other")
    # → ENDED, stop_error.kind == "api_error", code == "server_error".

def test_stop_failure_without_optional_fields(live_dir, monkeypatch):
    # StopFailure with only error="overloaded" → stop_error.details is None, message is None,
    # kind == "api_error", "at" is an ISO string.

def test_subagent_stop_failure_marks_only_that_subagent(live_dir, monkeypatch):
    # UserPromptSubmit, SubagentStart(agent-x1), SubagentStart(agent-x2),
    # StopFailure(agent_id="agent-x1", error="rate_limit")
    # → session state LIVE, agent-x1 status "error" with stop_error.kind "limit",
    #   completed_at set, duration_ms is an int >= 0; agent-x2 still "running".
    # Then SubagentStop(agent-x1) → agent-x1 status still "error".
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd hooks && pytest tests/test_live_session_tracker.py -v -k "stop_failure or stop_error"`
Expected: FAIL (no `StopFailure` branch; state file missing or not `INTERRUPTED`).

- [ ] **Step 3: Implement**
  - `_handle_event`: `StopFailure` branch. `agent_id` present → `mark_subagent_error`; else `write_state(session_id, "INTERRUPTED", data, stop_error=_stop_error(hook))`.
  - `PostToolUse` → `write_state(..., skip_if_current_state=("INTERRUPTED",))`; `idle_prompt` → `("WAITING", "INTERRUPTED")`.
  - `write_state`: `stop_error` param wins when given; else kept from `existing` unless the new state is `LIVE` or `STOPPED` (then null).
  - `mark_subagent_error` and `complete_subagent` share one record-closing helper (status, `completed_at`, `duration_ms`, missing-start record). `complete_subagent` doesn't downgrade a record whose status is already `"error"` (still fills `transcript_path`).
  - Module docstring: add `INTERRUPTED` and `StopFailure → INTERRUPTED (or subagent error when agent_id is set)`.

- [ ] **Step 4: Run the whole hook test file**

Run: `cd hooks && pytest tests/test_live_session_tracker.py -v`
Expected: all PASS (old tests included).

- [ ] **Step 5: Commit**

```bash
git add hooks/live_session_tracker.py hooks/tests/test_live_session_tracker.py
git commit -m "feat(hooks): mark sessions interrupted on StopFailure"
```

### Task 2: API status, `stop_error` and ended-session subagents

**Files:**
- Modify: `api/models/live_session.py` (`SessionState` `:47-55`, `SessionStatus` `:58-67`, `SubagentStatus` `:70-75`, `SubagentState` `:78-108`, `LiveSessionState` fields near `:192-215`)
- Modify: `api/routers/live_sessions.py` (`determine_status` `:123-170`, `state_to_summary` `:205-270`)
- Modify: `api/schemas.py` (`LiveSessionSummary` `:1066-1110`)
- Modify: `api/services/live_session_store.py:234` (`_NON_TERMINAL_STATES`)
- Test: `api/tests/api/test_live_sessions_interrupted.py` (new), `api/tests/test_live_session_store.py`

**Interfaces:**
- Consumes: Task 1's state-file fields.
- Produces (JSON from `/live-sessions` endpoints, Task 3 consumes):
  - `state: "INTERRUPTED"`, `status: "interrupted"`.
  - `stop_error: {kind: "limit"|"api_error", code: str, details: str|null, message: str|null, at: datetime} | null` on the summary and on each entry of `subagents`.
  - subagent `status` in `"running"|"completed"|"error"|"interrupted"`.
  - `active_subagent_count` counts only subagents reported as `running`.
- New model `StopError` (frozen, `extra="allow"`) in `api/models/live_session.py`; `LiveSessionState.stop_error: Optional[StopError] = None`; `SubagentState.stop_error: Optional[StopError] = None`.
- `reported_subagent_status(s: SubagentState, session_status: SessionStatus) -> SubagentStatus` in `api/routers/live_sessions.py`: `RUNNING` + session `ENDED` → `INTERRUPTED`, else `s.status`.

- [ ] **Step 1: Write the failing tests** (`api/tests/api/test_live_sessions_interrupted.py`; build `LiveSessionState` from dicts like `test_live_sessions_terminal.py` does, call `determine_status` / `state_to_summary` directly)

```python
def test_interrupted_never_decays_to_stale():
    # state INTERRUPTED, updated_at 10 minutes ago → determine_status == SessionStatus.INTERRUPTED

def test_summary_carries_stop_error():
    # INTERRUPTED with stop_error {kind:"limit", code:"rate_limit", message:"limit msg", ...}
    # → summary.status == "interrupted", summary.stop_error.kind == "limit"

def test_running_subagents_of_ended_session_read_interrupted():
    # ENDED session, subagents: a1 running, a2 completed, a3 error(with stop_error)
    # → a1 "interrupted", a2 "completed", a3 "error" + stop_error kept; active_subagent_count == 0

def test_running_subagent_of_live_session_stays_running():
    # LIVE session, a1 running → "running", active_subagent_count == 1

def test_stuck_starting_counts_as_ended_for_subagents():
    # STARTING, updated_at older than STARTING_TIMEOUT, a1 running → a1 "interrupted"

def test_old_file_without_stop_error_parses():
    # ENDED file with no stop_error key → summary.stop_error is None
```

In `api/tests/test_live_session_store.py`, extend `test_reap_ends_nonterminal_sessions_with_dead_pid` loops to include `"INTERRUPTED"` (count 6).

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd api && pytest tests/api/test_live_sessions_interrupted.py tests/test_live_session_store.py -v`
Expected: FAIL (`INTERRUPTED` not a valid `SessionState`; reaper count 5).

- [ ] **Step 3: Implement**
  - Enums and `StopError` model as in Interfaces. Parse `stop_error.at` like the other timestamps.
  - `determine_status`: `INTERRUPTED` → `SessionStatus.INTERRUPTED`, checked before any idle logic.
  - `state_to_summary`: compute `status` first, use `reported_subagent_status` in `subagents_dict`, add `stop_error` to each entry and to the summary; pass `active_subagent_count` as the count of reported `running`.
  - `schemas.py`: add `"INTERRUPTED"` / `"interrupted"` to the `Literal`s; `stop_error: Optional[Dict[str, Any]] = None` on `LiveSessionSummary`.
  - `_NON_TERMINAL_STATES`: add `"INTERRUPTED"`.

- [ ] **Step 4: Run API tests**

Run: `cd api && pytest tests/api/ tests/test_live_session_store.py -q` then `ruff check models/ routers/ services/ tests/ && ruff format --check models/ routers/ services/ tests/`
Expected: all PASS, ruff clean.

- [ ] **Step 5: Commit**

```bash
git add api/models/live_session.py api/routers/live_sessions.py api/schemas.py api/services/live_session_store.py api/tests/api/test_live_sessions_interrupted.py api/tests/test_live_session_store.py
git commit -m "feat(live-sessions): interrupted status, stop_error, ended-session subagents"
```

### Task 3: Frontend and setup docs

**Files:**
- Modify: `frontend/src/lib/api-types.ts` (`:638-660` types, `LiveSessionSummary`, `LiveSubStatus` / `ALL_LIVE_SUB_STATUSES` / `LiveStatusCounts` `:1330-1365`)
- Modify: `frontend/src/lib/live-session-config.ts` (`statusConfig`)
- Modify: `frontend/src/lib/components/LiveSessionsSection.svelte`, `LiveSessionsTerminal.svelte`, `home/HomeSessionsStrip.svelte` (reason line)
- Modify: `frontend/src/lib/components/subagents/SubagentTypeBadge.svelte`, `SubagentCard.svelte`, `SubagentGroup.svelte`, `conversation/ConversationHeader.svelte`, `conversation/ConversationView.svelte:281`
- Modify: every other site `npm run check` flags (filter components, `search.ts`, `stores/sessionFilters.svelte.ts`, sessions/project pages)
- Modify: `SETUP.md` (Tier 2 hook table `:270-281` and `settings.json` snippet `:284-375`)

**Interfaces:**
- Consumes: Task 2's JSON.
- Produces: `LiveSessionState` adds `'INTERRUPTED'`; `LiveSessionStatus` and `LiveSubStatus` add `'interrupted'`; `SubagentStatus = 'running' | 'completed' | 'error' | 'interrupted'`; `interface StopError { kind: 'limit' | 'api_error'; code: string; details: string | null; message: string | null; at: string }`; `stop_error?: StopError | null` on `LiveSessionSummary` and `SubagentState`.

- [ ] **Step 1: Types and status config.** `statusConfig.interrupted`: warning colour, label `interrupted`, `pulse: false`, a bg tint token following the existing `--status-*-bg` pattern (add the token in `app.css` if none fits). Add `interrupted` to `ALL_LIVE_SUB_STATUSES` and `LiveStatusCounts`.

- [ ] **Step 2: Reason line.** Where a live card shows status, when `stop_error` is set show one line: `message` if present, else `"Stopped by usage limit"` for `limit` / `"Stopped by API error"` for `api_error`; `title` tooltip = `code` plus `details`. One small shared helper or component, not three copies.

- [ ] **Step 3: Subagent statuses.** `error` → error colour, tooltip from `stop_error`; `interrupted` → muted, label `interrupted`. `ConversationView` finished check and `SubagentGroup`'s running count treat both as not running.

- [ ] **Step 4: Verify**

Run: `cd frontend && npm run check && npm run lint`
Expected: 0 errors.

- [ ] **Step 5: `SETUP.md`.** Add `StopFailure | Turn ended by an API error or usage limit` to the hook table and a `StopFailure` block (same command, `timeout: 5`) to the snippet. Version: state it only if confirmed from the official changelog; else "recent Claude Code".

- [ ] **Step 6: Manual smoke.** Feed the hook a synthetic `StopFailure` for a throwaway session id via stdin (`python hooks/live_session_tracker.py < payload.json` with a scratch payload), confirm the card shows `interrupted` + reason at `http://localhost:5180`, then delete that state file.

- [ ] **Step 7: Commit**

```bash
git add frontend SETUP.md
git commit -m "feat(frontend): show interrupted live sessions and subagent errors"
```
