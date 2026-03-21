"""Tests for remote session service and filtering."""

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from services.remote_sessions import (
    _is_local_user,
    _resolve_user_id,
    find_remote_session,
    get_project_mapping,
    iter_all_remote_session_metadata,
    list_remote_sessions_for_project,
)
from services.session_filter import SessionFilter, SessionMetadata, SessionSource

# ============================================================================
# Fixtures
# ============================================================================


def _make_session_jsonl(uuid: str, prompt: str = "hello") -> str:
    """Build minimal valid JSONL for a session."""
    lines = [
        json.dumps(
            {
                "type": "user",
                "uuid": f"msg-{uuid}",
                "message": {"role": "user", "content": prompt},
                "timestamp": "2026-03-03T12:00:00.000Z",
            }
        ),
        json.dumps(
            {
                "type": "assistant",
                "uuid": f"resp-{uuid}",
                "message": {"role": "assistant", "content": [{"type": "text", "text": "ok"}]},
                "timestamp": "2026-03-03T12:00:01.000Z",
            }
        ),
    ]
    return "\n".join(lines) + "\n"


@pytest.fixture
def karma_base(tmp_path: Path) -> Path:
    """Create fake karma base directory with remote sessions.

    Directory structure matches what Syncthing sync produces:
      remote-sessions/{user_id}/{encoded_name}/sessions/{uuid}.jsonl

    The local user's outbox is at remote-sessions/jayant/ and should be skipped.
    Remote users' inboxes use the LOCAL encoded name.
    """
    karma = tmp_path / ".claude_karma"
    karma.mkdir()

    local_encoded = "-Users-jayant-acme"

    # Alice's sessions (inbox from alice)
    alice_sessions = karma / "remote-sessions" / "alice" / local_encoded / "sessions"
    alice_sessions.mkdir(parents=True)
    (alice_sessions / "sess-001.jsonl").write_text(_make_session_jsonl("001", "hello"))
    (alice_sessions / "sess-002.jsonl").write_text(_make_session_jsonl("002", "build X"))

    # Bob's sessions (inbox from bob)
    bob_sessions = karma / "remote-sessions" / "bob" / local_encoded / "sessions"
    bob_sessions.mkdir(parents=True)
    (bob_sessions / "sess-003.jsonl").write_text(_make_session_jsonl("003", "fix bug"))

    # Local user's outbox (should be skipped by the service)
    jayant_sessions = karma / "remote-sessions" / "jayant" / local_encoded / "sessions"
    jayant_sessions.mkdir(parents=True)
    (jayant_sessions / "sess-local.jsonl").write_text(_make_session_jsonl("local", "my session"))

    # sync-config.json — Syncthing format
    sync_config = {
        "user_id": "jayant",
        "machine_id": "Jayants-MacBook-Pro.local",
        "teams": {
            "my-team": {
                "backend": "syncthing",
                "projects": {
                    "acme": {
                        "path": "/Users/jayant/acme",
                        "encoded_name": local_encoded,
                    }
                },
                "syncthing_members": {
                    "alice": {"syncthing_device_id": "ALICE-DEVICE-ID"},
                    "bob": {"syncthing_device_id": "BOB-DEVICE-ID"},
                },
            }
        },
    }
    (karma / "sync-config.json").write_text(json.dumps(sync_config))

    return karma


@pytest.fixture
def karma_base_legacy(tmp_path: Path) -> Path:
    """Create karma base with legacy paths-based config (for backwards compat)."""
    karma = tmp_path / ".claude_karma_legacy"
    karma.mkdir()

    local_encoded = "-Users-jayant-acme"

    # Alice's sessions
    alice_sessions = karma / "remote-sessions" / "alice" / local_encoded / "sessions"
    alice_sessions.mkdir(parents=True)
    (alice_sessions / "sess-001.jsonl").write_text(_make_session_jsonl("001", "hello"))

    # sync-config.json — legacy paths format
    sync_config = {
        "local_user_id": "jayant",
        "teams": {
            "my-team": {
                "projects": {
                    "acme": {
                        "paths": {
                            "jayant": "-Users-jayant-acme",
                            "alice": "-Users-alice-acme",
                            "bob": "-Users-bob-acme",
                        }
                    }
                }
            }
        },
    }
    (karma / "sync-config.json").write_text(json.dumps(sync_config))

    return karma


@pytest.fixture(autouse=True)
def _clear_cache():
    """Clear caches before each test."""
    import services.remote_sessions as mod

    mod._local_user_cache = None
    mod._local_user_cache_time = 0.0
    mod._project_mapping_cache = None
    mod._project_mapping_cache_time = 0.0
    mod._manifest_worktree_cache = {}
    mod._titles_cache = {}
    mod._resolved_user_cache = {}
    yield
    mod._local_user_cache = None
    mod._local_user_cache_time = 0.0
    mod._project_mapping_cache = None
    mod._project_mapping_cache_time = 0.0
    mod._manifest_worktree_cache = {}
    mod._titles_cache = {}
    mod._resolved_user_cache = {}


# ============================================================================
# Tests: get_project_mapping
# ============================================================================


class TestGetProjectMapping:
    def test_returns_mapping_syncthing_format(self, karma_base):
        with patch("services.remote_sessions.settings") as mock_settings:
            mock_settings.karma_base = karma_base
            mapping = get_project_mapping()

        # Syncthing members mapped to local encoded name
        assert mapping[("alice", "-Users-jayant-acme")] == "-Users-jayant-acme"
        assert mapping[("bob", "-Users-jayant-acme")] == "-Users-jayant-acme"

    def test_excludes_local_user(self, karma_base):
        with patch("services.remote_sessions.settings") as mock_settings:
            mock_settings.karma_base = karma_base
            mapping = get_project_mapping()

        # Local user should NOT appear in mapping
        assert ("jayant", "-Users-jayant-acme") not in mapping

    def test_returns_mapping_legacy_paths_format(self, karma_base_legacy):
        with patch("services.remote_sessions.settings") as mock_settings:
            mock_settings.karma_base = karma_base_legacy
            mapping = get_project_mapping()

        assert mapping[("alice", "-Users-alice-acme")] == "-Users-jayant-acme"
        assert mapping[("bob", "-Users-bob-acme")] == "-Users-jayant-acme"

    def test_returns_empty_when_no_config(self, tmp_path):
        with patch("services.remote_sessions.settings") as mock_settings:
            mock_settings.karma_base = tmp_path
            mapping = get_project_mapping()

        assert mapping == {}

    def test_caches_result(self, karma_base):
        with patch("services.remote_sessions.settings") as mock_settings:
            mock_settings.karma_base = karma_base
            mapping1 = get_project_mapping()
            mapping2 = get_project_mapping()

        assert mapping1 is mapping2  # Same object = cached


# ============================================================================
# Tests: find_remote_session
# ============================================================================


class TestFindRemoteSession:
    def test_finds_existing_session(self, karma_base):
        with patch("services.remote_sessions.settings") as mock_settings:
            mock_settings.karma_base = karma_base
            result = find_remote_session("sess-001")

        assert result is not None
        assert result.user_id == "alice"
        assert result.local_encoded_name == "-Users-jayant-acme"

    def test_finds_session_from_different_user(self, karma_base):
        with patch("services.remote_sessions.settings") as mock_settings:
            mock_settings.karma_base = karma_base
            result = find_remote_session("sess-003")

        assert result is not None
        assert result.user_id == "bob"

    def test_skips_local_user_outbox(self, karma_base):
        """Sessions in local user's outbox should NOT be found."""
        with patch("services.remote_sessions.settings") as mock_settings:
            mock_settings.karma_base = karma_base
            result = find_remote_session("sess-local")

        assert result is None

    def test_returns_none_for_missing_session(self, karma_base):
        with patch("services.remote_sessions.settings") as mock_settings:
            mock_settings.karma_base = karma_base
            result = find_remote_session("nonexistent-uuid")

        assert result is None

    def test_returns_none_when_no_remote_dir(self, tmp_path):
        with patch("services.remote_sessions.settings") as mock_settings:
            mock_settings.karma_base = tmp_path
            result = find_remote_session("sess-001")

        assert result is None


# ============================================================================
# Tests: list_remote_sessions_for_project
# ============================================================================


class TestListRemoteSessionsForProject:
    def test_lists_sessions_for_project(self, karma_base):
        with patch("services.remote_sessions.settings") as mock_settings:
            mock_settings.karma_base = karma_base
            results = list_remote_sessions_for_project("-Users-jayant-acme")

        # Should find Alice's 2 sessions + Bob's 1 session (NOT local user's)
        assert len(results) == 3
        uuids = {r.uuid for r in results}
        assert uuids == {"sess-001", "sess-002", "sess-003"}

    def test_excludes_local_user_outbox(self, karma_base):
        with patch("services.remote_sessions.settings") as mock_settings:
            mock_settings.karma_base = karma_base
            results = list_remote_sessions_for_project("-Users-jayant-acme")

        uuids = {r.uuid for r in results}
        assert "sess-local" not in uuids

    def test_all_results_have_remote_source(self, karma_base):
        with patch("services.remote_sessions.settings") as mock_settings:
            mock_settings.karma_base = karma_base
            results = list_remote_sessions_for_project("-Users-jayant-acme")

        for meta in results:
            assert meta.source == "remote"
            assert meta.remote_user_id is not None
            assert meta.remote_machine_id is not None

    def test_returns_empty_for_unknown_project(self, karma_base):
        with patch("services.remote_sessions.settings") as mock_settings:
            mock_settings.karma_base = karma_base
            results = list_remote_sessions_for_project("-Users-jayant-unknown")

        assert results == []

    def test_returns_empty_when_no_remote_dir(self, tmp_path):
        with patch("services.remote_sessions.settings") as mock_settings:
            mock_settings.karma_base = tmp_path
            results = list_remote_sessions_for_project("-Users-jayant-acme")

        assert results == []


# ============================================================================
# Tests: iter_all_remote_session_metadata
# ============================================================================


class TestIterAllRemoteSessionMetadata:
    def test_yields_all_remote_sessions(self, karma_base):
        with patch("services.remote_sessions.settings") as mock_settings:
            mock_settings.karma_base = karma_base
            results = list(iter_all_remote_session_metadata())

        # 3 remote sessions (NOT the local user's outbox session)
        assert len(results) == 3
        uuids = {r.uuid for r in results}
        assert uuids == {"sess-001", "sess-002", "sess-003"}

    def test_excludes_local_user_outbox(self, karma_base):
        with patch("services.remote_sessions.settings") as mock_settings:
            mock_settings.karma_base = karma_base
            results = list(iter_all_remote_session_metadata())

        uuids = {r.uuid for r in results}
        assert "sess-local" not in uuids

    def test_yields_correct_user_ids(self, karma_base):
        with patch("services.remote_sessions.settings") as mock_settings:
            mock_settings.karma_base = karma_base
            results = list(iter_all_remote_session_metadata())

        user_ids = {r.remote_user_id for r in results}
        assert user_ids == {"alice", "bob"}

    def test_yields_nothing_when_no_remote_dir(self, tmp_path):
        with patch("services.remote_sessions.settings") as mock_settings:
            mock_settings.karma_base = tmp_path
            results = list(iter_all_remote_session_metadata())

        assert results == []


# ============================================================================
# Tests: SessionFilter source filtering
# ============================================================================


class TestSessionFilterSource:
    def _make_meta(self, uuid: str, source: str = "local", user_id: str = None) -> SessionMetadata:
        return SessionMetadata(
            uuid=uuid,
            encoded_name="-Users-jayant-acme",
            project_path="/Users/jayant/acme",
            message_count=5,
            start_time=None,
            end_time=None,
            slug=None,
            initial_prompt=None,
            git_branch=None,
            source=source,
            remote_user_id=user_id,
            remote_machine_id="mbp" if user_id else None,
        )

    def test_source_all_returns_everything(self):
        filt = SessionFilter(source=SessionSource.ALL)
        local = self._make_meta("s1", source="local")
        remote = self._make_meta("s2", source="remote", user_id="alice")
        assert filt.matches_metadata(local)
        assert filt.matches_metadata(remote)

    def test_source_local_excludes_remote(self):
        filt = SessionFilter(source=SessionSource.LOCAL)
        local = self._make_meta("s1", source="local")
        remote = self._make_meta("s2", source="remote", user_id="alice")
        assert filt.matches_metadata(local)
        assert not filt.matches_metadata(remote)

    def test_source_remote_excludes_local(self):
        filt = SessionFilter(source=SessionSource.REMOTE)
        local = self._make_meta("s1", source="local")
        remote = self._make_meta("s2", source="remote", user_id="alice")
        assert not filt.matches_metadata(local)
        assert filt.matches_metadata(remote)

    def test_none_source_treated_as_local(self):
        filt = SessionFilter(source=SessionSource.LOCAL)
        meta = self._make_meta("s1", source=None)
        assert filt.matches_metadata(meta)


# ============================================================================
# Tests: Schema migration
# ============================================================================


class TestRemoteSessionSubagentAccess:
    def test_subagent_dir_resolves_correctly(self, karma_base):
        """Subagent files should be findable from remote session paths."""
        # Add a subagent file alongside a remote session
        alice_sessions = (
            karma_base / "remote-sessions" / "alice" / "-Users-jayant-acme" / "sessions"
        )
        sub_dir = alice_sessions / "sess-001" / "subagents"
        sub_dir.mkdir(parents=True)
        (sub_dir / "agent-abc.jsonl").write_text(
            json.dumps(
                {
                    "type": "user",
                    "message": {"role": "user", "content": "sub task"},
                    "timestamp": "2026-03-03T12:00:00Z",
                }
            )
            + "\n"
        )

        with patch("services.remote_sessions.settings") as mock_settings:
            mock_settings.karma_base = karma_base
            result = find_remote_session("sess-001")

        assert result is not None
        session = result.session
        # subagents_dir should point to the correct location
        assert session.subagents_dir == sub_dir
        assert session.subagents_dir.exists()
        agents = session.list_subagents()
        assert len(agents) >= 1


class TestRemoteSessionTodos:
    def test_todos_resolve_for_remote_session(self, karma_base):
        """Todos packaged into remote staging dir should be loadable."""
        encoded = "-Users-jayant-acme"
        alice_dir = karma_base / "remote-sessions" / "alice" / encoded

        sessions_dir = alice_dir / "sessions"
        sessions_dir.mkdir(parents=True, exist_ok=True)
        (sessions_dir / "sess-todo-001.jsonl").write_text(
            _make_session_jsonl("todo-001")
        )

        # Create todo file in staging structure
        todos_dir = alice_dir / "todos"
        todos_dir.mkdir(parents=True, exist_ok=True)
        (todos_dir / "sess-todo-001-task1.json").write_text(
            json.dumps([{
                "content": "Fix the bug",
                "status": "in_progress",
            }])
        )

        with patch("services.remote_sessions.settings") as mock_settings:
            mock_settings.karma_base = karma_base
            result = find_remote_session("sess-todo-001")

        assert result is not None
        session = result.session

        # Verify todos_dir points to correct location
        assert session.todos_dir == todos_dir
        assert session.todos_dir.exists()

        # Verify todos are loadable
        todos = session.list_todos()
        assert len(todos) >= 1
        assert todos[0].content == "Fix the bug"


class TestRemoteSessionTasks:
    def test_tasks_resolve_for_remote_session(self, karma_base):
        """Tasks packaged into remote staging dir should be loadable."""
        encoded = "-Users-jayant-acme"
        alice_dir = karma_base / "remote-sessions" / "alice" / encoded

        sessions_dir = alice_dir / "sessions"
        sessions_dir.mkdir(parents=True, exist_ok=True)
        (sessions_dir / "sess-task-001.jsonl").write_text(
            _make_session_jsonl("task-001")
        )

        # Create task files in staging structure
        task_dir = alice_dir / "tasks" / "sess-task-001"
        task_dir.mkdir(parents=True)
        (task_dir / "1.json").write_text(
            json.dumps({
                "id": "1",
                "subject": "Implement feature",
                "description": "Build the thing",
                "status": "in_progress",
            })
        )

        with patch("services.remote_sessions.settings") as mock_settings:
            mock_settings.karma_base = karma_base
            result = find_remote_session("sess-task-001")

        assert result is not None
        session = result.session

        assert session.tasks_dir == task_dir
        assert session.tasks_dir.exists()

        tasks = session.list_tasks()
        assert len(tasks) >= 1


class TestRemoteSessionToolResults:
    def test_tool_results_resolve_for_remote_session(self, karma_base):
        """Tool result files packaged alongside JSONL should be accessible."""
        encoded = "-Users-jayant-acme"
        alice_sessions = (
            karma_base / "remote-sessions" / "alice" / encoded / "sessions"
        )
        alice_sessions.mkdir(parents=True, exist_ok=True)

        (alice_sessions / "sess-tr-001.jsonl").write_text(
            _make_session_jsonl("tr-001")
        )

        # Create tool-results directory
        tr_dir = alice_sessions / "sess-tr-001" / "tool-results"
        tr_dir.mkdir(parents=True)
        (tr_dir / "toolu_abc123.txt").write_text("Tool output here")

        with patch("services.remote_sessions.settings") as mock_settings:
            mock_settings.karma_base = karma_base
            result = find_remote_session("sess-tr-001")

        assert result is not None
        session = result.session
        assert session.tool_results_dir == tr_dir
        assert session.tool_results_dir.exists()

        tool_results = session.list_tool_results()
        assert len(tool_results) >= 1


class TestRemoteSessionFileHistory:
    def test_file_history_resolves_for_remote_session(self, karma_base):
        """File-history packaged into remote staging should be accessible."""
        encoded = "-Users-jayant-acme"
        alice_dir = karma_base / "remote-sessions" / "alice" / encoded

        sessions_dir = alice_dir / "sessions"
        sessions_dir.mkdir(parents=True, exist_ok=True)
        (sessions_dir / "sess-fh-001.jsonl").write_text(
            _make_session_jsonl("fh-001")
        )

        # Create file-history in staging structure
        fh_dir = alice_dir / "file-history" / "sess-fh-001"
        fh_dir.mkdir(parents=True)
        (fh_dir / "snapshot.json").write_text('{"file": "main.py"}')

        with patch("services.remote_sessions.settings") as mock_settings:
            mock_settings.karma_base = karma_base
            result = find_remote_session("sess-fh-001")

        assert result is not None
        session = result.session
        assert session.file_history_dir == fh_dir
        assert session.has_file_history is True


class TestRemoteSessionDebugLog:
    def test_debug_log_resolves_for_remote_session(self, karma_base):
        """Debug logs packaged into remote staging should be readable."""
        encoded = "-Users-jayant-acme"
        alice_dir = karma_base / "remote-sessions" / "alice" / encoded

        sessions_dir = alice_dir / "sessions"
        sessions_dir.mkdir(parents=True, exist_ok=True)
        (sessions_dir / "sess-dbg-001.jsonl").write_text(
            _make_session_jsonl("dbg-001")
        )

        debug_dir = alice_dir / "debug"
        debug_dir.mkdir(parents=True)
        (debug_dir / "sess-dbg-001.txt").write_text("DEBUG: started")

        with patch("services.remote_sessions.settings") as mock_settings:
            mock_settings.karma_base = karma_base
            result = find_remote_session("sess-dbg-001")

        assert result is not None
        session = result.session
        assert session.has_debug_log is True
        assert session.read_debug_log() == "DEBUG: started"


class TestRemoteSessionMissingResources:
    def test_missing_todos_returns_empty(self, karma_base):
        """Remote session without todos dir should return empty list."""
        encoded = "-Users-jayant-acme"
        alice_dir = karma_base / "remote-sessions" / "alice" / encoded
        sessions_dir = alice_dir / "sessions"
        sessions_dir.mkdir(parents=True, exist_ok=True)
        (sessions_dir / "sess-empty-001.jsonl").write_text(
            _make_session_jsonl("empty-001")
        )

        with patch("services.remote_sessions.settings") as mock_settings:
            mock_settings.karma_base = karma_base
            result = find_remote_session("sess-empty-001")

        session = result.session
        assert session.list_todos() == []
        assert session.list_tasks() == []
        assert session.has_file_history is False
        assert session.has_debug_log is False


class TestSchemaMigration:
    def test_schema_v17_adds_remote_columns(self):
        import sqlite3

        from db.schema import SCHEMA_VERSION, ensure_schema

        assert SCHEMA_VERSION >= 13  # v13 added remote columns; now at v17+

        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        ensure_schema(conn)

        cols = {r[1] for r in conn.execute("PRAGMA table_info(sessions)").fetchall()}
        assert "source" in cols
        assert "remote_user_id" in cols
        assert "remote_machine_id" in cols

        indexes = {r[1] for r in conn.execute("PRAGMA index_list(sessions)").fetchall()}
        assert "idx_sessions_source" in indexes

        conn.close()


# ============================================================================
# Tests: SessionSummary schema
# ============================================================================


class TestSessionSummaryRemoteFields:
    def test_schema_accepts_remote_fields(self):
        from schemas import SessionSummary

        s = SessionSummary(
            uuid="test",
            message_count=1,
            source="remote",
            remote_user_id="alice",
            remote_machine_id="alice-mbp",
        )
        assert s.source == "remote"
        assert s.remote_user_id == "alice"
        assert s.remote_machine_id == "alice-mbp"

    def test_schema_defaults_none(self):
        from schemas import SessionSummary

        s = SessionSummary(uuid="test", message_count=1)
        assert s.source is None
        assert s.remote_user_id is None
        assert s.remote_machine_id is None


# ============================================================================
# Tests: Remote session titles
# ============================================================================


class TestRemoteSessionTitles:
    def test_loads_title_from_titles_json(self, karma_base):
        """Sessions should have session_titles populated from titles.json."""
        # Write titles.json into alice's inbox
        titles_dir = karma_base / "remote-sessions" / "alice" / "-Users-jayant-acme"
        titles_data = {
            "version": 1,
            "titles": {
                "sess-001": {"title": "Refactor auth module", "source": "git", "generated_at": "2026-03-08T12:00:00Z"},
                "sess-002": {"title": "Build new dashboard", "source": "haiku", "generated_at": "2026-03-08T13:00:00Z"},
            },
        }
        (titles_dir / "titles.json").write_text(json.dumps(titles_data))

        with patch("services.remote_sessions.settings") as mock_settings:
            mock_settings.karma_base = karma_base
            results = list_remote_sessions_for_project("-Users-jayant-acme")

        # Find alice's sessions and check titles
        by_uuid = {r.uuid: r for r in results}
        assert by_uuid["sess-001"].session_titles == ["Refactor auth module"]
        assert by_uuid["sess-002"].session_titles == ["Build new dashboard"]
        # Bob has no titles.json, so his session should have no titles
        assert by_uuid["sess-003"].session_titles is None

    def test_handles_missing_titles_json(self, karma_base):
        """Sessions should still work without titles.json (backward compat)."""
        with patch("services.remote_sessions.settings") as mock_settings:
            mock_settings.karma_base = karma_base
            results = list_remote_sessions_for_project("-Users-jayant-acme")

        # All sessions should have session_titles=None (no titles.json exists)
        for meta in results:
            assert meta.session_titles is None

    def test_iter_all_includes_titles(self, karma_base):
        """iter_all_remote_session_metadata() should also include titles."""
        # Write titles.json for alice
        titles_dir = karma_base / "remote-sessions" / "alice" / "-Users-jayant-acme"
        titles_data = {
            "version": 1,
            "titles": {
                "sess-001": {"title": "Refactor auth module", "source": "git", "generated_at": "2026-03-08T12:00:00Z"},
            },
        }
        (titles_dir / "titles.json").write_text(json.dumps(titles_data))

        with patch("services.remote_sessions.settings") as mock_settings:
            mock_settings.karma_base = karma_base
            results = list(iter_all_remote_session_metadata())

        by_uuid = {r.uuid: r for r in results}
        assert by_uuid["sess-001"].session_titles == ["Refactor auth module"]
        # sess-002 has no title entry
        assert by_uuid["sess-002"].session_titles is None
        # Bob's session has no titles.json at all
        assert by_uuid["sess-003"].session_titles is None


# ============================================================================
# Tests: member_tag directory support
# ============================================================================


@pytest.fixture
def karma_base_member_tag(tmp_path: Path) -> Path:
    """Create karma base with member_tag directory names.

    Uses ``{user_id}.{machine_tag}`` format for remote user directories,
    mixing with bare user_id directories for backward compatibility.
    """
    karma = tmp_path / ".claude_karma_mt"
    karma.mkdir()

    local_encoded = "-Users-jayant-acme"

    # Alice with member_tag directory (alice.macbook-pro)
    alice_sessions = (
        karma / "remote-sessions" / "alice.macbook-pro" / local_encoded / "sessions"
    )
    alice_sessions.mkdir(parents=True)
    (alice_sessions / "sess-mt-001.jsonl").write_text(
        _make_session_jsonl("mt-001", "member tag session")
    )

    # Bob with bare user_id directory (legacy)
    bob_sessions = karma / "remote-sessions" / "bob" / local_encoded / "sessions"
    bob_sessions.mkdir(parents=True)
    (bob_sessions / "sess-mt-002.jsonl").write_text(
        _make_session_jsonl("mt-002", "bare user session")
    )

    # Local user with member_tag directory (jayant.mac-mini)
    jayant_sessions = (
        karma / "remote-sessions" / "jayant.mac-mini" / local_encoded / "sessions"
    )
    jayant_sessions.mkdir(parents=True)
    (jayant_sessions / "sess-mt-local.jsonl").write_text(
        _make_session_jsonl("mt-local", "local outbox")
    )

    # Local user with bare directory too (jayant)
    jayant_bare = karma / "remote-sessions" / "jayant" / local_encoded / "sessions"
    jayant_bare.mkdir(parents=True)
    (jayant_bare / "sess-mt-local2.jsonl").write_text(
        _make_session_jsonl("mt-local2", "local outbox bare")
    )

    # sync-config.json
    sync_config = {
        "user_id": "jayant",
        "machine_id": "Jayants-Mac-mini.local",
        "teams": {
            "my-team": {
                "backend": "syncthing",
                "projects": {
                    "acme": {
                        "path": "/Users/jayant/acme",
                        "encoded_name": local_encoded,
                    }
                },
                "syncthing_members": {
                    "alice.macbook-pro": {"syncthing_device_id": "ALICE-DEVICE-ID"},
                    "bob": {"syncthing_device_id": "BOB-DEVICE-ID"},
                },
            }
        },
    }
    (karma / "sync-config.json").write_text(json.dumps(sync_config))

    return karma


class TestIsLocalUser:
    def test_bare_match(self):
        assert _is_local_user("jayant", "jayant") is True

    def test_bare_no_match(self):
        assert _is_local_user("alice", "jayant") is False

    def test_member_tag_match(self):
        assert _is_local_user("jayant.mac-mini", "jayant") is True

    def test_member_tag_no_match(self):
        assert _is_local_user("alice.macbook-pro", "jayant") is False

    def test_none_local_user(self):
        assert _is_local_user("jayant", None) is False

    def test_empty_local_user(self):
        assert _is_local_user("jayant", "") is False

    def test_dot_in_machine_tag_only(self):
        # user_id "alice" with machine_tag "mbp.local"
        assert _is_local_user("alice.mbp.local", "alice") is True

    def test_different_user_with_dot(self):
        assert _is_local_user("bob.desktop", "jayant") is False


class TestResolveUserIdMemberTag:
    def test_bare_dirname_no_manifest(self, tmp_path):
        """Bare dir name without manifest returns the dir name."""
        user_dir = tmp_path / "alice"
        user_dir.mkdir()
        assert _resolve_user_id(user_dir) == "alice"

    def test_member_tag_dirname_no_manifest(self, tmp_path):
        """member_tag dir name without manifest extracts user_id."""
        user_dir = tmp_path / "alice.macbook-pro"
        user_dir.mkdir()
        assert _resolve_user_id(user_dir) == "alice"

    def test_manifest_takes_precedence_over_member_tag(self, tmp_path):
        """Manifest user_id wins over member_tag parsing."""
        user_dir = tmp_path / "hostname.local"
        user_dir.mkdir()
        project_dir = user_dir / "-Users-alice-proj"
        project_dir.mkdir()
        manifest = {"user_id": "alice", "device_id": "DEVICE-123"}
        (project_dir / "manifest.json").write_text(json.dumps(manifest))
        assert _resolve_user_id(user_dir) == "alice"

    def test_hostname_with_multi_dots_not_treated_as_member_tag(self, tmp_path):
        """alice.mbp.local is a hostname (machine_part has dots), not a member_tag.
        _sanitize_machine_tag would produce 'mbp-local', not 'mbp.local'."""
        user_dir = tmp_path / "alice.mbp.local"
        user_dir.mkdir()
        # Dots in machine_part → not a valid sanitized machine_tag → treat as raw dirname
        assert _resolve_user_id(user_dir) == "alice.mbp.local"


class TestFindRemoteSessionMemberTag:
    def test_finds_session_in_member_tag_dir(self, karma_base_member_tag):
        with patch("services.remote_sessions.settings") as mock_settings:
            mock_settings.karma_base = karma_base_member_tag
            result = find_remote_session("sess-mt-001")

        assert result is not None
        assert result.user_id == "alice"
        assert result.machine_id == "alice.macbook-pro"

    def test_finds_session_in_bare_dir(self, karma_base_member_tag):
        with patch("services.remote_sessions.settings") as mock_settings:
            mock_settings.karma_base = karma_base_member_tag
            result = find_remote_session("sess-mt-002")

        assert result is not None
        assert result.user_id == "bob"
        assert result.machine_id == "bob"

    def test_skips_local_member_tag_outbox(self, karma_base_member_tag):
        """Local user's member_tag dir (jayant.mac-mini) should be skipped."""
        with patch("services.remote_sessions.settings") as mock_settings:
            mock_settings.karma_base = karma_base_member_tag
            result = find_remote_session("sess-mt-local")

        assert result is None

    def test_skips_local_bare_outbox(self, karma_base_member_tag):
        """Local user's bare dir (jayant) should also be skipped."""
        with patch("services.remote_sessions.settings") as mock_settings:
            mock_settings.karma_base = karma_base_member_tag
            result = find_remote_session("sess-mt-local2")

        assert result is None


class TestListRemoteSessionsMemberTag:
    def test_lists_both_formats(self, karma_base_member_tag):
        with patch("services.remote_sessions.settings") as mock_settings:
            mock_settings.karma_base = karma_base_member_tag
            results = list_remote_sessions_for_project("-Users-jayant-acme")

        # Should find alice.macbook-pro's session + bob's session (NOT local user's)
        assert len(results) == 2
        uuids = {r.uuid for r in results}
        assert uuids == {"sess-mt-001", "sess-mt-002"}

    def test_excludes_local_member_tag_and_bare(self, karma_base_member_tag):
        with patch("services.remote_sessions.settings") as mock_settings:
            mock_settings.karma_base = karma_base_member_tag
            results = list_remote_sessions_for_project("-Users-jayant-acme")

        uuids = {r.uuid for r in results}
        assert "sess-mt-local" not in uuids
        assert "sess-mt-local2" not in uuids

    def test_user_id_resolved_from_member_tag(self, karma_base_member_tag):
        with patch("services.remote_sessions.settings") as mock_settings:
            mock_settings.karma_base = karma_base_member_tag
            results = list_remote_sessions_for_project("-Users-jayant-acme")

        by_uuid = {r.uuid: r for r in results}
        # alice.macbook-pro dir -> user_id resolved to "alice"
        assert by_uuid["sess-mt-001"].remote_user_id == "alice"
        # machine_id is the raw dir name
        assert by_uuid["sess-mt-001"].remote_machine_id == "alice.macbook-pro"
        # bob (bare) -> user_id stays "bob"
        assert by_uuid["sess-mt-002"].remote_user_id == "bob"


class TestIterAllMemberTag:
    def test_yields_both_formats_skips_local(self, karma_base_member_tag):
        with patch("services.remote_sessions.settings") as mock_settings:
            mock_settings.karma_base = karma_base_member_tag
            results = list(iter_all_remote_session_metadata())

        assert len(results) == 2
        uuids = {r.uuid for r in results}
        assert uuids == {"sess-mt-001", "sess-mt-002"}
        # No local user sessions
        assert "sess-mt-local" not in uuids
        assert "sess-mt-local2" not in uuids
