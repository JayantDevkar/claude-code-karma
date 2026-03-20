"""
Unit tests for session_title_generator hook.

Covers rate-limit detection, retry enqueueing, local title persistence,
and fallback behaviour.
"""

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# The hook lives outside api/ — add it to the path.
HOOKS_DIR = Path(__file__).parent.parent.parent / "hooks"
sys.path.insert(0, str(HOOKS_DIR))

import session_title_generator as gen  # noqa: E402


# ---------------------------------------------------------------------------
# _is_rate_limit_error
# ---------------------------------------------------------------------------


class TestIsRateLimitError:
    def test_detects_usage_limit(self):
        assert gen._is_rate_limit_error("claude ai usage limit reached")

    def test_detects_rate_limit(self):
        assert gen._is_rate_limit_error("error: rate limit exceeded")

    def test_detects_too_many_requests(self):
        assert gen._is_rate_limit_error("too many requests, please retry")

    def test_detects_quota_exceeded(self):
        assert gen._is_rate_limit_error("quota exceeded for this billing period")

    def test_detects_overloaded(self):
        assert gen._is_rate_limit_error("api overloaded, try again later")

    def test_does_not_match_generic_error(self):
        assert not gen._is_rate_limit_error("connection refused")

    def test_does_not_match_empty(self):
        assert not gen._is_rate_limit_error("")

    def test_case_insensitive(self):
        assert gen._is_rate_limit_error("USAGE LIMIT")


# ---------------------------------------------------------------------------
# generate_title — rate-limit and timeout paths
# ---------------------------------------------------------------------------


class TestGenerateTitleRateLimit:
    """generate_title returns (None, 'rate_limited') when claude exits non-zero
    with a rate-limit message in stderr."""

    def _run_with_stderr(self, stderr_text: str, returncode: int = 1):
        mock_result = MagicMock()
        mock_result.returncode = returncode
        mock_result.stdout = ""
        mock_result.stderr = stderr_text

        with patch("subprocess.run", return_value=mock_result):
            return gen.generate_title("do something", "I did it", None)

    def test_rate_limited_returns_none_and_source(self):
        title, source = self._run_with_stderr("usage limit reached")
        assert title is None
        assert source == "rate_limited"

    def test_non_rate_limit_error_falls_back_to_prompt(self):
        title, source = self._run_with_stderr("unknown error", returncode=1)
        assert source == "fallback"
        assert title is not None

    def test_timeout_returns_none_and_timeout_source(self):
        import subprocess

        with patch("subprocess.run", side_effect=subprocess.TimeoutExpired("claude", 30)):
            title, source = gen.generate_title("do something", None, None)

        assert title is None
        assert source == "timeout"

    def test_successful_haiku_response(self):
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "Extract PDF budget to Excel"
        mock_result.stderr = ""

        with patch("subprocess.run", return_value=mock_result):
            title, source = gen.generate_title("extract pdf", "done", None)

        assert title == "Extract PDF budget to Excel"
        assert source == "haiku"

    def test_git_context_skips_haiku(self):
        """When git context is available, title comes from git without calling subprocess."""
        with patch("subprocess.run") as mock_run:
            title, source = gen.generate_title("anything", None, "abc1234 feat: add export button")

        mock_run.assert_not_called()
        assert source == "git"
        assert "add export button" in title

    def test_long_title_truncated_to_max_words(self):
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "one two three four five six seven eight nine ten eleven"
        mock_result.stderr = ""

        with patch("subprocess.run", return_value=mock_result):
            title, source = gen.generate_title("do something", None, None)

        assert len(title.split()) <= gen.TITLE_MAX_WORDS


# ---------------------------------------------------------------------------
# enqueue_title_retry
# ---------------------------------------------------------------------------


class TestEnqueueTitleRetry:
    def test_creates_retry_file(self, tmp_path: Path):
        with patch.object(gen, "KARMA_BASE", tmp_path):
            gen.enqueue_title_retry(
                session_id="test-uuid-123",
                transcript_path="/some/path.jsonl",
                initial_prompt="extract pdf",
                first_response="done",
                cwd="/home/user/project",
            )

        retry_file = tmp_path / "title-retry" / "test-uuid-123.json"
        assert retry_file.exists()

        payload = json.loads(retry_file.read_text())
        assert payload["session_id"] == "test-uuid-123"
        assert payload["initial_prompt"] == "extract pdf"
        assert payload["first_response"] == "done"
        assert payload["cwd"] == "/home/user/project"

    def test_none_first_response_stored(self, tmp_path: Path):
        with patch.object(gen, "KARMA_BASE", tmp_path):
            gen.enqueue_title_retry("uuid-abc", "/t.jsonl", "prompt", None, "/cwd")

        payload = json.loads((tmp_path / "title-retry" / "uuid-abc.json").read_text())
        assert payload["first_response"] is None

    def test_oserror_does_not_raise(self, tmp_path: Path):
        """enqueue_title_retry must never propagate OSError."""
        read_only = tmp_path / "ro"
        read_only.mkdir()
        read_only.chmod(0o444)

        with patch.object(gen, "KARMA_BASE", read_only):
            # Should not raise
            gen.enqueue_title_retry("uuid", "/t.jsonl", "prompt", None, "/cwd")


# ---------------------------------------------------------------------------
# save_title_locally
# ---------------------------------------------------------------------------


class TestSaveTitleLocally:
    def test_writes_title_to_txt_file(self, tmp_path: Path):
        with patch.object(gen, "PENDING_TITLES_DIR", tmp_path / "session-titles"):
            gen.save_title_locally("my-uuid", "My Title")

        txt = tmp_path / "session-titles" / "my-uuid.txt"
        assert txt.exists()
        assert txt.read_text() == "My Title"

    def test_oserror_does_not_raise(self, tmp_path: Path):
        read_only = tmp_path / "ro"
        read_only.mkdir()
        read_only.chmod(0o444)

        with patch.object(gen, "PENDING_TITLES_DIR", read_only / "subdir"):
            gen.save_title_locally("uuid", "Title")


# ---------------------------------------------------------------------------
# post_title — fallback on API failure
# ---------------------------------------------------------------------------


class TestPostTitle:
    def test_saves_locally_when_api_unavailable(self, tmp_path: Path):
        import urllib.error

        with (
            patch("urllib.request.urlopen", side_effect=urllib.error.URLError("refused")),
            patch.object(gen, "PENDING_TITLES_DIR", tmp_path / "session-titles"),
        ):
            result = gen.post_title("uuid-offline", "Offline Title")

        assert result is False
        txt = tmp_path / "session-titles" / "uuid-offline.txt"
        assert txt.exists()
        assert txt.read_text() == "Offline Title"

    def test_returns_true_on_success(self):
        mock_response = MagicMock()
        with patch("urllib.request.urlopen", return_value=mock_response):
            result = gen.post_title("uuid-ok", "My Title")

        assert result is True


# ---------------------------------------------------------------------------
# main() integration — enqueue on rate_limited / timeout
# ---------------------------------------------------------------------------


class TestMainEnqueuesOnRateLimit:
    def _make_minimal_jsonl(self, tmp_path: Path) -> Path:
        jsonl = tmp_path / "session.jsonl"
        lines = [
            json.dumps({"type": "user", "message": {"role": "user", "content": "help me"}, "timestamp": "2026-01-01T00:00:00Z"}),
            json.dumps({"type": "assistant", "message": {"role": "assistant", "content": [{"type": "text", "text": "sure"}]}}),
        ]
        jsonl.write_text("\n".join(lines))
        return jsonl

    def test_enqueues_when_rate_limited(self, tmp_path: Path):
        jsonl = self._make_minimal_jsonl(tmp_path)
        hook_input = json.dumps({
            "session_id": "rate-uuid",
            "transcript_path": str(jsonl),
            "cwd": str(tmp_path),
            "reason": "normal",
        })

        import subprocess

        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stdout = ""
        mock_result.stderr = "usage limit reached"

        with (
            patch("subprocess.run", return_value=mock_result),
            patch.object(gen, "KARMA_BASE", tmp_path),
            patch("sys.stdin") as mock_stdin,
        ):
            mock_stdin.read.return_value = hook_input
            gen.main()

        retry_file = tmp_path / "title-retry" / "rate-uuid.json"
        assert retry_file.exists()

    def test_does_not_enqueue_on_fallback_error(self, tmp_path: Path):
        jsonl = self._make_minimal_jsonl(tmp_path)
        hook_input = json.dumps({
            "session_id": "fallback-uuid",
            "transcript_path": str(jsonl),
            "cwd": str(tmp_path),
            "reason": "normal",
        })

        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stdout = ""
        mock_result.stderr = "some unknown error"

        with (
            patch("subprocess.run", return_value=mock_result),
            patch.object(gen, "KARMA_BASE", tmp_path),
            patch("sys.stdin") as mock_stdin,
            patch.object(gen, "post_title", return_value=True),
        ):
            mock_stdin.read.return_value = hook_input
            gen.main()

        retry_file = tmp_path / "title-retry" / "fallback-uuid.json"
        assert not retry_file.exists()
