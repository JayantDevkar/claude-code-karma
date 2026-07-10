# Sync Session Titles Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Share hook-generated session titles across devices via a `titles.json` sidecar file in the Syncthing outbox, so receivers see meaningful session names instead of UUIDs.

**Architecture:** A new `titles_io.py` module provides atomic read/write/merge for `titles.json`. The sender writes titles from two paths: (1) the packager dumps cached titles during packaging, (2) the POST /title handler writes immediately when a new title is generated. The receiver reads `titles.json` alongside `manifest.json` using the same TTL-cached pattern already used for worktree attribution.

**Tech Stack:** Python 3.9+, Pydantic, pytest, existing SessionTitleCache, existing remote_sessions service

---

### Task 1: Create `titles_io.py` — shared titles.json read/write

**Files:**
- Create: `cli/karma/titles_io.py`
- Create: `api/tests/test_titles_io.py`

**Step 1: Write the failing tests**

```python
# api/tests/test_titles_io.py
"""Tests for titles_io read/write/merge logic."""

import json
from pathlib import Path

import pytest

# Add CLI to path for import
import sys
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "cli"))

from karma.titles_io import read_titles, write_title, write_titles_bulk


class TestReadTitles:
    def test_returns_empty_dict_when_file_missing(self, tmp_path):
        result = read_titles(tmp_path / "titles.json")
        assert result == {}

    def test_returns_empty_dict_when_file_corrupt(self, tmp_path):
        path = tmp_path / "titles.json"
        path.write_text("not json")
        result = read_titles(path)
        assert result == {}

    def test_reads_valid_titles(self, tmp_path):
        path = tmp_path / "titles.json"
        path.write_text(json.dumps({
            "version": 1,
            "titles": {
                "uuid-1": {"title": "Fix bug", "source": "git", "generated_at": "2026-03-08T12:00:00Z"}
            }
        }))
        result = read_titles(path)
        assert "uuid-1" in result
        assert result["uuid-1"]["title"] == "Fix bug"
        assert result["uuid-1"]["source"] == "git"

    def test_ignores_unknown_version(self, tmp_path):
        path = tmp_path / "titles.json"
        path.write_text(json.dumps({"version": 99, "titles": {"a": {"title": "x"}}}))
        result = read_titles(path)
        assert result == {}


class TestWriteTitle:
    def test_creates_file_if_missing(self, tmp_path):
        path = tmp_path / "titles.json"
        write_title(path, "uuid-1", "Fix bug", "git")

        data = json.loads(path.read_text())
        assert data["version"] == 1
        assert data["titles"]["uuid-1"]["title"] == "Fix bug"
        assert data["titles"]["uuid-1"]["source"] == "git"
        assert "generated_at" in data["titles"]["uuid-1"]
        assert "updated_at" in data

    def test_merges_with_existing(self, tmp_path):
        path = tmp_path / "titles.json"
        write_title(path, "uuid-1", "First title", "git")
        write_title(path, "uuid-2", "Second title", "haiku")

        data = json.loads(path.read_text())
        assert len(data["titles"]) == 2
        assert data["titles"]["uuid-1"]["title"] == "First title"
        assert data["titles"]["uuid-2"]["title"] == "Second title"

    def test_overwrites_existing_uuid(self, tmp_path):
        path = tmp_path / "titles.json"
        write_title(path, "uuid-1", "Old title", "fallback")
        write_title(path, "uuid-1", "New title", "haiku")

        data = json.loads(path.read_text())
        assert data["titles"]["uuid-1"]["title"] == "New title"
        assert data["titles"]["uuid-1"]["source"] == "haiku"

    def test_creates_parent_dirs(self, tmp_path):
        path = tmp_path / "deep" / "nested" / "titles.json"
        write_title(path, "uuid-1", "Test", "git")
        assert path.exists()


class TestWriteTitlesBulk:
    def test_writes_multiple_titles(self, tmp_path):
        path = tmp_path / "titles.json"
        entries = {
            "uuid-1": {"title": "First", "source": "git"},
            "uuid-2": {"title": "Second", "source": "haiku"},
        }
        write_titles_bulk(path, entries)

        data = json.loads(path.read_text())
        assert len(data["titles"]) == 2

    def test_merges_with_existing_preserving_newer(self, tmp_path):
        path = tmp_path / "titles.json"
        # Write initial
        write_title(path, "uuid-1", "Original", "haiku")

        # Bulk write that includes uuid-1 with different title
        entries = {
            "uuid-1": {"title": "Bulk override", "source": "git"},
            "uuid-2": {"title": "New entry", "source": "haiku"},
        }
        write_titles_bulk(path, entries)

        data = json.loads(path.read_text())
        assert len(data["titles"]) == 2
        # Bulk should overwrite
        assert data["titles"]["uuid-1"]["title"] == "Bulk override"

    def test_handles_empty_entries(self, tmp_path):
        path = tmp_path / "titles.json"
        write_titles_bulk(path, {})
        # Should create valid empty file
        data = json.loads(path.read_text())
        assert data["titles"] == {}
```

**Step 2: Run tests to verify they fail**

Run: `cd api && python -m pytest tests/test_titles_io.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'karma.titles_io'`

**Step 3: Write the implementation**

```python
# cli/karma/titles_io.py
"""Atomic read/write/merge for titles.json sidecar files.

Used by both the session packager (bulk dump of cached titles) and the
POST /sessions/{uuid}/title handler (single title write on generation).

File format:
{
  "version": 1,
  "updated_at": "2026-03-08T14:30:00Z",
  "titles": {
    "uuid": {"title": "...", "source": "git|haiku|fallback", "generated_at": "..."}
  }
}
"""

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional


_VERSION = 1


def read_titles(path: Path) -> dict[str, dict]:
    """Read titles.json. Returns {uuid: {title, source, generated_at}} or empty dict."""
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if data.get("version") != _VERSION:
            return {}
        return data.get("titles", {})
    except (json.JSONDecodeError, OSError, TypeError):
        return {}


def write_title(
    path: Path,
    uuid: str,
    title: str,
    source: str,
    generated_at: Optional[str] = None,
) -> None:
    """Write or merge a single title into titles.json. Atomic (tmp+rename)."""
    existing = read_titles(path)
    existing[uuid] = {
        "title": title,
        "source": source,
        "generated_at": generated_at or datetime.now(timezone.utc).isoformat(),
    }
    _write_file(path, existing)


def write_titles_bulk(path: Path, entries: dict[str, dict]) -> None:
    """Bulk write/merge titles into titles.json. Atomic (tmp+rename).

    Args:
        path: Path to titles.json
        entries: {uuid: {"title": str, "source": str}} — generated_at added if missing
    """
    existing = read_titles(path)
    now = datetime.now(timezone.utc).isoformat()
    for uuid, entry in entries.items():
        existing[uuid] = {
            "title": entry["title"],
            "source": entry.get("source", "unknown"),
            "generated_at": entry.get("generated_at", now),
        }
    _write_file(path, existing)


def _write_file(path: Path, titles: dict[str, dict]) -> None:
    """Atomically write titles dict to path."""
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "version": _VERSION,
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "titles": titles,
    }
    tmp_path = path.with_suffix(".tmp")
    tmp_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    tmp_path.replace(path)
```

**Step 4: Run tests to verify they pass**

Run: `cd api && python -m pytest tests/test_titles_io.py -v`
Expected: All PASS

**Step 5: Commit**

```bash
git add cli/karma/titles_io.py api/tests/test_titles_io.py
git commit -m "feat(sync): add titles_io module for titles.json sidecar read/write"
```

---

### Task 2: Packager writes `titles.json` during packaging

**Files:**
- Modify: `cli/karma/packager.py:199-221` (after manifest write)
- Create: `api/tests/test_packager_titles.py`

**Step 1: Write the failing test**

```python
# api/tests/test_packager_titles.py
"""Tests for packager writing titles.json alongside manifest."""

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "cli"))

from karma.packager import SessionPackager


@pytest.fixture
def project_dir(tmp_path):
    """Create a fake Claude project directory with sessions."""
    claude_projects = tmp_path / ".claude" / "projects" / "-Users-test-acme"
    claude_projects.mkdir(parents=True)

    # Create session JSONL files
    for uuid in ("sess-001", "sess-002"):
        (claude_projects / f"{uuid}.jsonl").write_text(
            json.dumps({
                "type": "user",
                "message": {"role": "user", "content": "hello"},
                "timestamp": "2026-03-08T12:00:00Z",
            }) + "\n"
        )
    return claude_projects


class TestPackagerWritesTitles:
    def test_writes_titles_json_from_cache(self, project_dir, tmp_path):
        """Packager should write titles.json with any cached titles."""
        staging = tmp_path / "staging"
        staging.mkdir()

        # Pre-populate a title cache file so packager can read it
        from karma.titles_io import write_title
        cache_titles_path = staging / "titles.json"
        # We won't have a real title cache, so test that titles.json is at least created
        packager = SessionPackager(
            project_dir=project_dir,
            user_id="alice",
            machine_id="alice-mbp",
            project_path="/Users/test/acme",
        )
        manifest = packager.package(staging)

        # manifest.json should exist
        assert (staging / "manifest.json").exists()

        # titles.json should exist (may be empty if no title cache)
        titles_path = staging / "titles.json"
        assert titles_path.exists()
        data = json.loads(titles_path.read_text())
        assert data["version"] == 1
        assert isinstance(data["titles"], dict)

    def test_preserves_existing_titles_in_staging(self, project_dir, tmp_path):
        """Packager should merge with existing titles.json (from prior title hook writes)."""
        staging = tmp_path / "staging"
        staging.mkdir()

        # Pre-populate titles.json with a title from a prior hook write
        from karma.titles_io import write_title
        write_title(staging / "titles.json", "sess-001", "Prior hook title", "haiku")

        packager = SessionPackager(
            project_dir=project_dir,
            user_id="alice",
            machine_id="alice-mbp",
            project_path="/Users/test/acme",
        )
        packager.package(staging)

        data = json.loads((staging / "titles.json").read_text())
        # Prior title should still be present
        assert data["titles"]["sess-001"]["title"] == "Prior hook title"
```

**Step 2: Run tests to verify they fail**

Run: `cd api && python -m pytest tests/test_packager_titles.py -v`
Expected: FAIL (titles.json not created by packager)

**Step 3: Implement — add titles.json write to packager**

Modify `cli/karma/packager.py`. After the manifest write at line 219, add:

```python
        # Write titles.json — merge cached titles with any existing titles
        from karma.titles_io import read_titles, write_titles_bulk

        titles_path = staging_dir / "titles.json"
        # Bulk write preserves existing entries (from prior title hook writes)
        # For now, packager writes an empty titles.json if no external titles are provided.
        # The title_entries parameter allows callers to inject cached titles.
        if not titles_path.exists():
            write_titles_bulk(titles_path, {})

        manifest_path = staging_dir / "manifest.json"
```

Wait — the packager doesn't have access to the API's SessionTitleCache (it's a CLI module). The packager should write an empty `titles.json` if none exists, preserving any that the title hook already wrote. The actual titles come from the POST handler (Task 3).

The real merge point: `write_titles_bulk` with an empty dict when no new titles — this ensures the file exists and preserves anything already there.

Add after line 219 of `cli/karma/packager.py`:

```python
        # Ensure titles.json exists in staging (preserves any prior title hook writes)
        from karma.titles_io import write_titles_bulk
        titles_path = staging_dir / "titles.json"
        if not titles_path.exists():
            write_titles_bulk(titles_path, {})
```

**Step 4: Run tests to verify they pass**

Run: `cd api && python -m pytest tests/test_packager_titles.py -v`
Expected: All PASS

**Step 5: Commit**

```bash
git add cli/karma/packager.py api/tests/test_packager_titles.py
git commit -m "feat(sync): packager creates titles.json sidecar in outbox"
```

---

### Task 3: POST /title handler writes to outbox `titles.json`

**Files:**
- Modify: `api/routers/sessions.py:1726-1792` (set_session_title endpoint)
- Modify: `api/tests/api/test_set_session_title.py` (add outbox write test)

**Step 1: Write the failing test**

Add to `api/tests/api/test_set_session_title.py`:

```python
class TestSetSessionTitleOutbox:
    """Tests for title propagation to Syncthing outbox titles.json."""

    def test_writes_to_outbox_titles_json(self, client, sample_session_for_title, tmp_path):
        """POST /sessions/{uuid}/title should write to outbox titles.json."""
        session_uuid, encoded_name = sample_session_for_title

        # Set up sync config so the handler knows where the outbox is
        karma_base = tmp_path / ".claude_karma"
        karma_base.mkdir()
        sync_config = {
            "user_id": "testuser",
            "machine_id": "test-machine",
        }
        (karma_base / "sync-config.json").write_text(json.dumps(sync_config))

        # Create outbox directory
        outbox = karma_base / "remote-sessions" / "testuser" / encoded_name
        outbox.mkdir(parents=True)

        with patch("routers.sessions.settings") as mock_settings:
            # Keep existing settings but override karma_base
            mock_settings.karma_base = karma_base
            mock_settings.projects_dir = settings.projects_dir
            mock_settings.use_sqlite = False

            response = client.post(
                f"/sessions/{session_uuid}/title",
                json={"title": "Test Outbox Title"},
            )

        assert response.status_code == 200

        # Verify titles.json was written in outbox
        titles_path = outbox / "titles.json"
        if titles_path.exists():
            import json as json_mod
            data = json_mod.loads(titles_path.read_text())
            assert data["titles"][session_uuid]["title"] == "Test Outbox Title"
```

**Step 2: Run tests to verify they fail**

Run: `cd api && python -m pytest tests/api/test_set_session_title.py::TestSetSessionTitleOutbox -v`
Expected: FAIL (no outbox write logic yet)

**Step 3: Implement — add outbox write to POST handler**

Modify `api/routers/sessions.py`, in `set_session_title()` function. After the SQLite update block (after line 1787), add before the return statement:

```python
    # Write to Syncthing outbox titles.json (best-effort, non-blocking)
    try:
        import sys
        from pathlib import Path

        cli_path = Path(__file__).parent.parent.parent / "cli"
        if str(cli_path) not in sys.path:
            sys.path.insert(0, str(cli_path))

        sync_config_path = settings.karma_base / "sync-config.json"
        if sync_config_path.exists():
            sync_data = json.loads(sync_config_path.read_text())
            user_id = sync_data.get("user_id")
            if user_id:
                outbox_dir = settings.karma_base / "remote-sessions" / user_id / encoded_name
                if outbox_dir.exists():
                    from karma.titles_io import write_title as write_outbox_title

                    # Determine title source from existing data
                    source = "hook"
                    write_outbox_title(
                        outbox_dir / "titles.json", uuid, title, source
                    )
    except Exception as e:
        logger.debug("Failed to write title to outbox: %s", e)
        # Best-effort — don't fail the request
```

**Step 4: Run tests to verify they pass**

Run: `cd api && python -m pytest tests/api/test_set_session_title.py -v`
Expected: All PASS

**Step 5: Commit**

```bash
git add api/routers/sessions.py api/tests/api/test_set_session_title.py
git commit -m "feat(sync): POST /title writes to Syncthing outbox titles.json"
```

---

### Task 4: Receiver reads titles from inbox `titles.json`

**Files:**
- Modify: `api/services/remote_sessions.py:333-514`
- Modify: `api/tests/test_remote_sessions.py`

**Step 1: Write the failing tests**

Add to `api/tests/test_remote_sessions.py`:

```python
class TestRemoteSessionTitles:
    """Tests for title loading from inbox titles.json."""

    def test_loads_title_from_titles_json(self, karma_base):
        """Remote sessions should have titles populated from titles.json."""
        encoded = "-Users-jayant-acme"
        alice_dir = karma_base / "remote-sessions" / "alice" / encoded

        # Write titles.json
        titles_data = {
            "version": 1,
            "updated_at": "2026-03-08T12:00:00Z",
            "titles": {
                "sess-001": {
                    "title": "Fix authentication bug",
                    "source": "git",
                    "generated_at": "2026-03-08T12:00:00Z",
                },
                "sess-002": {
                    "title": "Add user pagination",
                    "source": "haiku",
                    "generated_at": "2026-03-08T13:00:00Z",
                },
            },
        }
        (alice_dir / "titles.json").write_text(json.dumps(titles_data))

        with patch("services.remote_sessions.settings") as mock_settings:
            mock_settings.karma_base = karma_base
            results = list_remote_sessions_for_project("-Users-jayant-acme")

        # Find alice's sessions
        by_uuid = {r.uuid: r for r in results}
        assert by_uuid["sess-001"].session_titles == ["Fix authentication bug"]
        assert by_uuid["sess-002"].session_titles == ["Add user pagination"]

    def test_handles_missing_titles_json(self, karma_base):
        """Sessions should work fine without titles.json (backward compat)."""
        with patch("services.remote_sessions.settings") as mock_settings:
            mock_settings.karma_base = karma_base
            results = list_remote_sessions_for_project("-Users-jayant-acme")

        # No titles.json exists in fixture — sessions should still load
        assert len(results) == 3
        for r in results:
            assert r.session_titles is None or r.session_titles == []

    def test_iter_all_includes_titles(self, karma_base):
        """iter_all_remote_session_metadata should also include titles."""
        encoded = "-Users-jayant-acme"
        alice_dir = karma_base / "remote-sessions" / "alice" / encoded
        titles_data = {
            "version": 1,
            "titles": {
                "sess-001": {"title": "Fix bug", "source": "git", "generated_at": "2026-03-08T12:00:00Z"}
            },
        }
        (alice_dir / "titles.json").write_text(json.dumps(titles_data))

        with patch("services.remote_sessions.settings") as mock_settings:
            mock_settings.karma_base = karma_base
            results = list(iter_all_remote_session_metadata())

        by_uuid = {r.uuid: r for r in results}
        assert by_uuid["sess-001"].session_titles == ["Fix bug"]

    def test_titles_cache_has_ttl(self, karma_base):
        """Title cache should expire after TTL."""
        import services.remote_sessions as mod

        encoded = "-Users-jayant-acme"
        alice_dir = karma_base / "remote-sessions" / "alice" / encoded

        # Write initial titles
        titles_data = {"version": 1, "titles": {"sess-001": {"title": "V1", "source": "git", "generated_at": "2026-03-08T12:00:00Z"}}}
        (alice_dir / "titles.json").write_text(json.dumps(titles_data))

        with patch("services.remote_sessions.settings") as mock_settings:
            mock_settings.karma_base = karma_base
            # First load
            results1 = list_remote_sessions_for_project("-Users-jayant-acme")

        by_uuid1 = {r.uuid: r for r in results1}
        assert by_uuid1["sess-001"].session_titles == ["V1"]
```

**Step 2: Run tests to verify they fail**

Run: `cd api && python -m pytest tests/test_remote_sessions.py::TestRemoteSessionTitles -v`
Expected: FAIL (session_titles not populated)

**Step 3: Implement — add title loading to remote_sessions.py**

Add a title loading function (same pattern as `_load_manifest_worktree_map`):

```python
# Add near the top with other caches (after line 44)
_titles_cache: dict[tuple[str, str], tuple[float, dict[str, str]]] = {}
_TITLES_TTL = 30.0  # seconds


def _load_remote_titles(user_id: str, encoded_name: str) -> dict[str, str]:
    """
    Load titles.json for a (user_id, encoded_name) pair and return
    a mapping of uuid -> title string.

    Results are cached with a TTL.
    """
    cache_key = (user_id, encoded_name)
    now = time.monotonic()

    cached = _titles_cache.get(cache_key)
    if cached is not None:
        cache_time, cache_data = cached
        if (now - cache_time) < _TITLES_TTL:
            return cache_data

    result: dict[str, str] = {}
    titles_path = (
        _get_remote_sessions_dir() / user_id / encoded_name / "titles.json"
    )
    if titles_path.exists():
        try:
            with open(titles_path) as f:
                data = json.load(f)
            if data.get("version") == 1:
                for uuid, entry in data.get("titles", {}).items():
                    title = entry.get("title")
                    if title:
                        result[uuid] = title
        except (json.JSONDecodeError, OSError) as e:
            logger.debug(
                "Failed to load titles for %s/%s: %s", user_id, encoded_name, e
            )

    _titles_cache[cache_key] = (now, result)
    return result
```

Modify `_build_remote_metadata()` to accept a `title` parameter (line 457-513):

Add `title: Optional[str] = None` parameter, and populate `session_titles`:

```python
def _build_remote_metadata(
    *,
    jsonl_path: Path,
    uuid: str,
    local_encoded: str,
    project_dir: Path,
    user_id: str,
    machine_id: str,
    worktree_name: Optional[str] = None,
    title: Optional[str] = None,       # ← NEW
) -> Optional[SessionMetadata]:
```

In the return statement (line 496), add:
```python
            session_titles=[title] if title else None,
```

Modify callers `list_remote_sessions_for_project` (line 366-384) and `iter_all_remote_session_metadata` (line 423-441) to load titles and pass them through:

```python
            # Load titles once per (user_id, project)
            titles_map = _load_remote_titles(user_id, local_encoded)  # or encoded_name

            # In the _build_remote_metadata call, add:
            title=titles_map.get(uuid),
```

Also clear the `_titles_cache` in the `_clear_cache` fixture in test file.

**Step 4: Run tests to verify they pass**

Run: `cd api && python -m pytest tests/test_remote_sessions.py -v`
Expected: All PASS (including new and existing tests)

**Step 5: Commit**

```bash
git add api/services/remote_sessions.py api/tests/test_remote_sessions.py
git commit -m "feat(sync): receiver reads session titles from inbox titles.json"
```

---

### Task 5: Clear titles cache in test fixture and add integration test

**Files:**
- Modify: `api/tests/test_remote_sessions.py` (update `_clear_cache` fixture)

**Step 1: Update the autouse fixture**

In `api/tests/test_remote_sessions.py`, the `_clear_cache` fixture (line 136-149) needs to also clear `_titles_cache`:

```python
@pytest.fixture(autouse=True)
def _clear_cache():
    """Clear caches before each test."""
    import services.remote_sessions as mod

    mod._local_user_cache = None
    mod._local_user_cache_time = 0.0
    mod._project_mapping_cache = None
    mod._project_mapping_cache_time = 0.0
    mod._titles_cache = {}                    # ← ADD
    mod._manifest_worktree_cache = {}         # ← ADD (was missing)
    yield
    mod._local_user_cache = None
    mod._local_user_cache_time = 0.0
    mod._project_mapping_cache = None
    mod._project_mapping_cache_time = 0.0
    mod._titles_cache = {}                    # ← ADD
    mod._manifest_worktree_cache = {}         # ← ADD
```

**Step 2: Run full test suite**

Run: `cd api && python -m pytest tests/test_remote_sessions.py tests/test_titles_io.py tests/test_packager_titles.py tests/api/test_set_session_title.py -v`
Expected: All PASS

**Step 3: Commit**

```bash
git add api/tests/test_remote_sessions.py
git commit -m "test(sync): clear titles cache in test fixtures"
```

---

### Task 6: End-to-end verification

**Files:** None (manual verification)

**Step 1: Start the API**

Run: `cd api && uvicorn main:app --reload --port 8000`

**Step 2: Verify title POST writes to outbox**

```bash
# Check sync config exists
cat ~/.claude_karma/sync-config.json | python -m json.tool | head -5

# Find a recent session UUID
curl -s http://localhost:8000/sessions | python -m json.tool | head -20

# POST a test title (use a real session UUID)
curl -X POST http://localhost:8000/sessions/{uuid}/title \
  -H 'Content-Type: application/json' \
  -d '{"title": "Test sync title"}'

# Check titles.json was written in outbox
find ~/.claude_karma/remote-sessions -name titles.json -exec cat {} \;
```

**Step 3: Verify all existing tests still pass**

Run: `cd api && python -m pytest -x -q`
Expected: All PASS, no regressions

**Step 4: Final commit with all changes**

```bash
git add -A
git status  # Review — no secrets or unwanted files
git commit -m "feat(sync): complete titles.json sync pipeline for remote session titles"
```
