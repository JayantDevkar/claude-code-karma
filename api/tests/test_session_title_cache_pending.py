"""
Unit tests for SessionTitleCache — pending titles (offline hook fallback).

Covers _load_pending_titles and the integration with _build_from_jsonl.
"""

import json
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from services.session_title_cache import SessionTitleCache, TitleEntry  # noqa: E402


# ---------------------------------------------------------------------------
# _load_pending_titles
# ---------------------------------------------------------------------------


class TestLoadPendingTitles:
    def test_returns_empty_when_dir_missing(self, tmp_path: Path):
        with patch("services.session_title_cache.settings") as mock_settings:
            mock_settings.karma_base = tmp_path / "nonexistent"
            result = SessionTitleCache._load_pending_titles()
        assert result == {}

    def test_reads_txt_files(self, tmp_path: Path):
        pending_dir = tmp_path / "session-titles"
        pending_dir.mkdir()
        (pending_dir / "uuid-abc.txt").write_text("Extract PDF to Excel")
        (pending_dir / "uuid-def.txt").write_text("Fix login bug")

        with patch("services.session_title_cache.settings") as mock_settings:
            mock_settings.karma_base = tmp_path
            result = SessionTitleCache._load_pending_titles()

        assert result["uuid-abc"] == "Extract PDF to Excel"
        assert result["uuid-def"] == "Fix login bug"

    def test_skips_empty_files(self, tmp_path: Path):
        pending_dir = tmp_path / "session-titles"
        pending_dir.mkdir()
        (pending_dir / "empty-uuid.txt").write_text("   ")

        with patch("services.session_title_cache.settings") as mock_settings:
            mock_settings.karma_base = tmp_path
            result = SessionTitleCache._load_pending_titles()

        assert "empty-uuid" not in result

    def test_skips_unreadable_files(self, tmp_path: Path):
        pending_dir = tmp_path / "session-titles"
        pending_dir.mkdir()
        txt = pending_dir / "bad-uuid.txt"
        txt.write_text("A title")
        txt.chmod(0o000)

        with patch("services.session_title_cache.settings") as mock_settings:
            mock_settings.karma_base = tmp_path
            result = SessionTitleCache._load_pending_titles()

        # Should not raise, and bad file should be absent
        assert "bad-uuid" not in result

        txt.chmod(0o644)  # restore for cleanup


# ---------------------------------------------------------------------------
# set_title — also writes pending-titles txt
# ---------------------------------------------------------------------------


class TestSetTitleWritesPendingFile:
    def _make_cache_and_project(self, tmp_path: Path):
        project_dir = tmp_path / "projects" / "-home-user-repo"
        project_dir.mkdir(parents=True)
        jsonl = project_dir / "test-uuid.jsonl"
        jsonl.write_text(
            json.dumps({"type": "user", "message": {"role": "user", "content": "hello"}}) + "\n"
        )
        return project_dir, jsonl

    def test_set_title_writes_txt(self, tmp_path: Path):
        project_dir, jsonl = self._make_cache_and_project(tmp_path)
        cache_dir = tmp_path / "cache" / "titles"
        cache_dir.mkdir(parents=True)

        with patch("services.session_title_cache.settings") as mock_settings:
            mock_settings.projects_dir = tmp_path / "projects"
            mock_settings.karma_base = tmp_path
            mock_settings.use_sqlite = False

            tc = SessionTitleCache()
            tc.set_title("-home-user-repo", "test-uuid", "My New Title")

        txt = tmp_path / "session-titles" / "test-uuid.txt"
        assert txt.exists()
        assert txt.read_text() == "My New Title"

    def test_set_title_txt_oserror_does_not_raise(self, tmp_path: Path):
        project_dir, jsonl = self._make_cache_and_project(tmp_path)

        # Make karma_base a file so mkdir fails
        fake_base = tmp_path / "not-a-dir"
        fake_base.write_text("blocker")

        with patch("services.session_title_cache.settings") as mock_settings:
            mock_settings.projects_dir = tmp_path / "projects"
            mock_settings.karma_base = fake_base
            mock_settings.use_sqlite = False

            tc = SessionTitleCache()
            # Must not raise
            tc.set_title("-home-user-repo", "test-uuid", "Title")


# ---------------------------------------------------------------------------
# _build_from_jsonl — picks up pending titles for sessions without summary
# ---------------------------------------------------------------------------


class TestBuildFromJsonlUsesPendingTitles:
    def _write_session(self, project_dir: Path, uuid: str) -> Path:
        """Write a minimal JSONL with no summary entry."""
        jsonl = project_dir / f"{uuid}.jsonl"
        lines = [
            json.dumps({"type": "user", "slug": "test-slug", "message": {"role": "user", "content": "help"}}),
            json.dumps({"type": "assistant", "message": {"role": "assistant", "content": [{"type": "text", "text": "ok"}]}}),
        ]
        jsonl.write_text("\n".join(lines))
        return jsonl

    def test_pending_title_used_when_no_summary(self, tmp_path: Path):
        project_dir = tmp_path / "projects" / "-home-user-repo"
        project_dir.mkdir(parents=True)
        uuid = "pending-session-uuid"
        self._write_session(project_dir, uuid)

        # Write a pending title
        pending_dir = tmp_path / "session-titles"
        pending_dir.mkdir()
        (pending_dir / f"{uuid}.txt").write_text("Pending Generated Title")

        with patch("services.session_title_cache.settings") as mock_settings:
            mock_settings.projects_dir = tmp_path / "projects"
            mock_settings.karma_base = tmp_path
            mock_settings.use_sqlite = False

            tc = SessionTitleCache()
            # Bypass SessionIndex loading
            with patch("services.session_title_cache.SessionIndex") as mock_index:
                mock_index.load.return_value = None
                data = tc._build_from_jsonl("-home-user-repo")

        assert uuid in data
        assert data[uuid].titles == ["Pending Generated Title"]

    def test_summary_entry_takes_priority_over_pending(self, tmp_path: Path):
        project_dir = tmp_path / "projects" / "-home-user-repo"
        project_dir.mkdir(parents=True)
        uuid = "summary-session-uuid"

        # Write a JSONL with a summary entry
        jsonl = project_dir / f"{uuid}.jsonl"
        lines = [
            json.dumps({"type": "user", "message": {"role": "user", "content": "help"}}),
            json.dumps({"type": "assistant", "message": {"role": "assistant", "content": [{"type": "text", "text": "ok"}]}}),
            json.dumps({"type": "summary", "summary": "Title From JSONL Summary"}),
        ]
        jsonl.write_text("\n".join(lines))

        # Also write a pending title (should be ignored)
        pending_dir = tmp_path / "session-titles"
        pending_dir.mkdir()
        (pending_dir / f"{uuid}.txt").write_text("Should Be Ignored")

        with patch("services.session_title_cache.settings") as mock_settings:
            mock_settings.projects_dir = tmp_path / "projects"
            mock_settings.karma_base = tmp_path
            mock_settings.use_sqlite = False

            tc = SessionTitleCache()
            with patch("services.session_title_cache.SessionIndex") as mock_index:
                mock_index.load.return_value = None
                data = tc._build_from_jsonl("-home-user-repo")

        assert data[uuid].titles == ["Title From JSONL Summary"]
