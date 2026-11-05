# Synced Session Titles Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Karma titles sessions synced from other machines through Haiku once they end cleanly, opt-in per extra root, with a manual backfill for older sessions.

**Architecture:** A new `api/services/synced_titles.py` picks qualifying synced sessions after each periodic index pass and titles them with the hook's `generate_title()`, loaded by path from `hooks/`. Title storage moves out of the `POST /sessions/{uuid}/title` handler into a shared helper. `backfill_titles.py --synced` covers the backlog by hand.

**Tech Stack:** Python 3.10+, FastAPI, SQLite, pytest.

**Spec:** `docs/superpowers/specs/2026-11-02-synced-session-titles-design.md`

## Global Constraints

- Off unless the root entry has `"auto_titles": true`; with no such root, no Haiku call, no DB write, no extra file reads (byte-identical behaviour to main).
- `AUTO_TITLE_WINDOW_HOURS = 24`, `AUTO_TITLE_BATCH = 20`.
- At most one automatic Haiku call per session (`sessions.title_attempted_at`).
- Sessions with `source_root IS NULL` are never titled by this feature.
- `hooks/session_title_generator.py` is not modified (it must keep running on Python 3.9).
- Code comments are one line; docstring summaries one line.
- Prompt source is `sessions.initial_prompt`. Relay-wrapper cleanup comes from PR #148; tests here must not depend on it.
- Test data is synthetic (`/home/alice/...`, made-up prompts); no real paths or project names.

## Review Focus

1. A JSONL that is mid-copy (last line truncated, not valid JSON) does not count as ended; it is skipped without being marked attempted, and titled on a later pass once complete. Test in Task 2.
2. A forced reindex (`POST /admin/reindex` resets `jsonl_mtime`, the upsert rewrites `session_titles` to `[]`) must not cause a second Haiku call. Test in Task 2.
3. `hooks/session_title_generator.py` missing (API installed without the repo's `hooks/`): the titling pass logs one warning and returns; the periodic sync keeps running. Test in Task 2.
4. A session with `end_time` NULL or older than 24 h never qualifies, even with the flag on. Test in Task 2 (the 25-hour case).
5. Turning the flag on for a root with years of history costs at most the last 24 h of sessions, `AUTO_TITLE_BATCH` per pass. Covered by the window test; no extra test.

## Prerequisite

Branch from `main` after PR #148 merges (or stack on its branch and say so in the PR body). The schema change uses `_SESSION_COLUMNS`, which runs regardless of `SCHEMA_VERSION`, so no version bump and no conflict with the v26/v27 PRs.

---

### Task 1: Shared title-store helper

Refactor only; no new behaviour, so no new test. `api/tests/api/test_set_session_title.py` must stay green.

**Files:**
- Create: `api/services/session_title_store.py`
- Modify: `api/routers/sessions.py:1836-1902` (`set_session_title`)

**Interfaces:**
- Produces: `store_session_title(encoded_name: str, uuid: str, title: str, conn: Optional[sqlite3.Connection] = None) -> None` — updates `title_cache`, then (when `settings.use_sqlite`) prepends the title to `sessions.session_titles` in the given connection, or `get_writer_db()` when `conn` is None. SQLite errors are logged and swallowed, as today.

- [ ] **Step 1:** Move the body of `set_session_title` after `encoded_name`/`title` are known into `store_session_title`. The handler keeps the 404 lookup and the `JSONResponse`.
- [ ] **Step 2:** Run `cd api && pytest tests/api/test_set_session_title.py -v`. Expected: all PASS.
- [ ] **Step 3:** Commit: `refactor(api): move session title storage into a shared helper`.

### Task 2: Automatic titles for synced sessions

**Files:**
- Modify: `api/services/session_roots.py` (`SessionRoot`, `_parse_root`)
- Modify: `api/db/schema.py` (`SCHEMA_SQL` sessions table, `_SESSION_COLUMNS`, `_NO_REINDEX_COLUMNS`)
- Create: `api/services/synced_titles.py`
- Modify: `api/db/indexer.py:1095-1123` (`run_periodic_sync`)
- Modify: `SETUP.md` (Multiple Machines section, around line 830)
- Test: `api/tests/test_synced_titles.py`

**Interfaces:**
- Consumes: `store_session_title(...)` from Task 1; `session_jsonl_path(encoded_name, uuid)` and `get_extra_roots()` from `services/session_roots.py`.
- Produces:
  - `SessionRoot.auto_titles: bool = False`, read from the entry key `"auto_titles"` with `bool(entry.get("auto_titles", False))`.
  - Column `sessions.title_attempted_at TEXT` (in `_SESSION_COLUMNS` and `_NO_REINDEX_COLUMNS`; not in the indexer's upsert, so a reindex keeps it).
  - `load_title_generator() -> Optional[Callable[[str, Optional[str], Optional[str]], tuple[Optional[str], str]]]` — imports `generate_title` from `<repo>/hooks/session_title_generator.py` via `importlib.util.spec_from_file_location`; cached; returns None and logs one warning when the file is missing.
  - `title_synced_sessions(conn: sqlite3.Connection, now: Optional[datetime] = None) -> int` — returns the number of sessions titled.

- [ ] **Step 1: Write the failing tests** in `api/tests/test_synced_titles.py`. Reuse the `machines` / `mem_db` fixture shapes from `tests/test_session_roots.py` (copy them; synthetic paths). Helper `_write_synced(dir, uuid, prompt, end="2026-11-02T10:00:05.000Z", cost_state=True, truncated=False)` writes a user + assistant line, then a `{"type": "cost-state", "sessionId": uuid}` line, or a cut-off last line when `truncated`. Stub the generator with `monkeypatch.setattr(synced_titles, "load_title_generator", lambda: fake)` where `fake` records its calls and returns `("Fix login redirect", "haiku")`. `NOW = datetime(2026, 11, 2, 11, 0, tzinfo=timezone.utc)`.

```python
def test_ended_synced_session_gets_one_title(machines, mem_db, fake): ...
    # configure(auto_titles=True); write r1 with prompt "Fix the login redirect"; sync_all_projects
    assert title_synced_sessions(mem_db, now=NOW) == 1
    assert fake.calls == [("Fix the login redirect", None, None)]
    assert json.loads(row("r1")["session_titles"]) == ["Fix login redirect"]
    assert title_synced_sessions(mem_db, now=NOW) == 0 and len(fake.calls) == 1

def test_reindex_does_not_retitle(machines, mem_db, fake): ...
    # after one titled pass: UPDATE sessions SET jsonl_mtime = jsonl_mtime - 1; sync_all_projects; pass again
    assert len(fake.calls) == 1 and row("r1")["title_attempted_at"] is not None

@pytest.mark.parametrize("case", ["flag_off", "no_cost_state", "ended_25h_ago", "local_session"])
def test_not_titled(case, machines, mem_db, fake): ...
    assert title_synced_sessions(mem_db, now=NOW) == 0 and fake.calls == []

def test_mid_copy_file_is_retried_once_complete(machines, mem_db, fake): ...
    # truncated=True: pass titles 0 and leaves title_attempted_at NULL; rewrite complete file, re-sync: pass titles 1

def test_missing_hook_module_is_a_no_op(machines, mem_db, monkeypatch): ...
    # load_title_generator -> None
    assert title_synced_sessions(mem_db, now=NOW) == 0
```

- [ ] **Step 2:** Run `cd api && pytest tests/test_synced_titles.py -v`. Expected: FAIL (`ModuleNotFoundError: services.synced_titles`).
- [ ] **Step 3: Implement.**
  - `SessionRoot.auto_titles` and `_parse_root` as in Interfaces.
  - Schema: add `title_attempted_at TEXT` to the `CREATE TABLE sessions` in `SCHEMA_SQL`, to `_SESSION_COLUMNS`, and to `_NO_REINDEX_COLUMNS`.
  - `title_synced_sessions`: return 0 at once when no root in `get_extra_roots()` has `auto_titles` (no query). Otherwise select up to `AUTO_TITLE_BATCH` rows with `source_root IN (<enabled names>)`, `(session_titles IS NULL OR session_titles IN ('', '[]'))`, `title_attempted_at IS NULL`, `julianday(:now) - julianday(end_time) <= AUTO_TITLE_WINDOW_HOURS / 24.0`, ordered by `end_time DESC`. Per row: `_ended_cleanly(session_jsonl_path(...))` reads the last non-empty line (seek to the last 64 KiB) and returns True only for valid JSON with `type == "cost-state"`, False otherwise, None on `OSError`. Skip without marking unless True. Set `title_attempted_at` and commit **before** the Haiku call. No `initial_prompt`: marked, no call. Call `generate_title(initial_prompt, None, None)` and pass a non-empty title to `store_session_title(encoded_name, uuid, title, conn=conn)`.
  - `run_periodic_sync`: after the sync, `await asyncio.to_thread(title_synced_sessions, conn)` inside its own `try`/`except Exception` that logs a warning.
- [ ] **Step 4:** Run `cd api && pytest tests/test_synced_titles.py tests/test_session_roots.py tests/test_schema_v25.py -v`. Expected: all PASS.
- [ ] **Step 5: Docs.** In `SETUP.md` add `"auto_titles": false` to the `extra-roots.json` example, and one short paragraph: titles that root's sessions through Haiku once they end cleanly, one call per session through this machine's `claude` login, only sessions that ended in the last 24 h; older ones via `python api/scripts/backfill_titles.py --synced`.
- [ ] **Step 6:** Run `cd api && ruff check services/ db/ tests/ && ruff format --check services/ db/ tests/`. Expected: clean.
- [ ] **Step 7:** Commit: `feat(api): title synced sessions through Haiku, opt-in per root`.

### Task 3: Backfill `--synced`

**Files:**
- Modify: `api/scripts/backfill_titles.py`
- Test: `api/tests/test_backfill_titles.py`

**Interfaces:**
- Consumes: `load_title_generator()` from Task 2.
- Produces: `get_titleless_sessions(db_path, project_filter=None, limit=None, synced_only=False)`; CLI flag `--synced`.

- [ ] **Step 1: Write the failing test.**

```python
def test_synced_filter_selects_only_synced_rows(tmp_path):
    # file DB via ensure_schema; insert one local (source_root NULL) and one synced ("vps") untitled row, message_count 1
    rows = get_titleless_sessions(db_path, synced_only=True)
    assert [r[0] for r in rows] == ["synced-1"]
```

- [ ] **Step 2:** Run `cd api && pytest tests/test_backfill_titles.py -v`. Expected: FAIL (`unexpected keyword argument 'synced_only'`).
- [ ] **Step 3: Implement.** `synced_only` adds `AND source_root IS NOT NULL`. `--synced` passes it and ignores `auto_titles`, the window and `title_attempted_at`. Delete the script's own `generate_title`; call the generator from `load_title_generator()` (exit with an error message when it is None). For `--synced` rows use the DB `initial_prompt` and `None` git context; local rows keep the current JSONL extraction and git lookup. Drop `HAIKU_MODEL` if unused.
- [ ] **Step 4:** Run `cd api && pytest tests/test_backfill_titles.py -v && python scripts/backfill_titles.py --synced --dry-run`. Expected: PASS; the dry run lists only synced sessions (or "No sessions need titles.").
- [ ] **Step 5:** Commit: `feat(scripts): backfill_titles --synced for older synced sessions`.

### Final check

- [ ] Run `cd api && pytest`. Expected: all PASS.
- [ ] Manual: with a real synced root and `"auto_titles": true`, start the API, wait one periodic pass (300 s), and confirm a session that ended within 24 h shows a title in the dashboard. Note in the PR body what was and was not checked.
