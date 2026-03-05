"""Tests for remote session service and filtering."""

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from services.remote_sessions import (
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
    yield
    mod._local_user_cache = None
    mod._local_user_cache_time = 0.0
    mod._project_mapping_cache = None
    mod._project_mapping_cache_time = 0.0


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
        alice_sessions = karma_base / "remote-sessions" / "alice" / "-Users-jayant-acme" / "sessions"
        sub_dir = alice_sessions / "sess-001" / "subagents"
        sub_dir.mkdir(parents=True)
        (sub_dir / "agent-abc.jsonl").write_text(
            json.dumps({"type": "user", "message": {"role": "user", "content": "sub task"},
                         "timestamp": "2026-03-03T12:00:00Z"}) + "\n"
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


class TestSchemaMigration:
    def test_schema_v17_adds_remote_columns(self):
        import sqlite3

        from db.schema import SCHEMA_VERSION, ensure_schema

        assert SCHEMA_VERSION == 17

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
