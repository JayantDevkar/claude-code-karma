"""
Tests for hooks/ticket_branch_detector.py.

The hook is invoked by Claude Code via stdin → SessionStart JSON payload.
We exercise it via subprocess so we cover the real entry point, with
HOME pointed at a tmp dir so config and live-sessions don't pollute the
user's machine.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Optional

import pytest

HOOK = Path(__file__).resolve().parent.parent / "ticket_branch_detector.py"


@pytest.fixture
def home(tmp_path, monkeypatch) -> Path:
    """Re-home the user so ~/.claude_karma/* lives under tmp."""
    monkeypatch.setenv("HOME", str(tmp_path))
    return tmp_path


@pytest.fixture
def repo(tmp_path) -> Path:
    """A real git repo on a branch named feat/LINEAR-123-fix-login."""
    repo_dir = tmp_path / "repo"
    repo_dir.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=repo_dir, check=True)
    subprocess.run(
        ["git", "config", "user.email", "test@example.com"], cwd=repo_dir, check=True
    )
    subprocess.run(["git", "config", "user.name", "test"], cwd=repo_dir, check=True)
    subprocess.run(
        ["git", "commit", "--allow-empty", "-m", "init", "-q"], cwd=repo_dir, check=True
    )
    subprocess.run(
        ["git", "checkout", "-q", "-b", "feat/LINEAR-123-fix-login"],
        cwd=repo_dir,
        check=True,
    )
    return repo_dir


def _run_hook(
    payload: dict,
    *,
    home: Path,
    karma_api: Optional[str] = None,
    extra_env: Optional[dict] = None,
) -> subprocess.CompletedProcess:
    env = dict(os.environ)
    env["HOME"] = str(home)
    if karma_api is not None:
        env["CLAUDE_KARMA_API"] = karma_api
    if extra_env:
        env.update(extra_env)
    return subprocess.run(
        [sys.executable, str(HOOK)],
        input=json.dumps(payload),
        text=True,
        capture_output=True,
        env=env,
        timeout=15,
    )


def _write_config(home: Path, cfg: dict) -> None:
    karma = home / ".claude_karma"
    karma.mkdir(parents=True, exist_ok=True)
    (karma / "config.json").write_text(json.dumps(cfg))


def test_silent_exit_when_no_config(home, repo):
    """No config file → opt-in default False → no-op, exit 0."""
    result = _run_hook(
        {"session_id": "sess-1", "cwd": str(repo)},
        home=home,
        karma_api="http://127.0.0.1:1",  # unroutable port
    )
    assert result.returncode == 0
    # No log entry because we exited before any I/O
    log = home / ".claude_karma" / "logs" / "ticket_branch_detector.log"
    assert not log.exists()


def test_silent_exit_when_disabled(home, repo):
    """Explicit disabled flag → no-op."""
    _write_config(home, {"branch_detect_enabled": False, "ticket_branch_patterns": []})
    result = _run_hook(
        {"session_id": "sess-1", "cwd": str(repo)},
        home=home,
        karma_api="http://127.0.0.1:1",
    )
    assert result.returncode == 0


def test_silent_exit_when_no_branch_match(home, repo):
    """Enabled but the configured regex doesn't match this branch name."""
    _write_config(
        home,
        {
            "branch_detect_enabled": True,
            "ticket_branch_patterns": [{"regex": r"^WONT-MATCH-\d+$", "provider": "linear"}],
        },
    )
    result = _run_hook(
        {"session_id": "sess-1", "cwd": str(repo)},
        home=home,
        karma_api="http://127.0.0.1:1",
    )
    assert result.returncode == 0


def test_silent_exit_with_unreachable_karma(home, repo):
    """When the API is unreachable, the hook logs but still exits 0."""
    _write_config(
        home,
        {
            "branch_detect_enabled": True,
            "ticket_branch_patterns": [
                {"regex": r"(?P<key>[A-Z][A-Z0-9_]+-\d+)", "provider": "linear"}
            ],
        },
    )
    result = _run_hook(
        {"session_id": "sess-1", "cwd": str(repo)},
        home=home,
        karma_api="http://127.0.0.1:1",  # unroutable
    )
    assert result.returncode == 0
    # Log should record the POST failure.
    log = home / ".claude_karma" / "logs" / "ticket_branch_detector.log"
    assert log.exists()
    assert "POST" in log.read_text()


def test_silent_exit_with_non_git_cwd(home, tmp_path):
    """cwd that isn't a git repo → git lookup returns None → no-op."""
    _write_config(
        home,
        {
            "branch_detect_enabled": True,
            "ticket_branch_patterns": [
                {"regex": r"(?P<key>[A-Z][A-Z0-9_]+-\d+)", "provider": "linear"}
            ],
        },
    )
    non_git = tmp_path / "no-git"
    non_git.mkdir()
    result = _run_hook(
        {"session_id": "sess-1", "cwd": str(non_git)},
        home=home,
        karma_api="http://127.0.0.1:1",
    )
    assert result.returncode == 0
    log = home / ".claude_karma" / "logs" / "ticket_branch_detector.log"
    assert not log.exists(), "should never have reached POST"


def test_silent_exit_with_missing_session_id(home, repo):
    """Malformed payload (no session_id) — never raises."""
    _write_config(
        home,
        {
            "branch_detect_enabled": True,
            "ticket_branch_patterns": [
                {"regex": r"(?P<key>[A-Z][A-Z0-9_]+-\d+)", "provider": "linear"}
            ],
        },
    )
    result = _run_hook(
        {"cwd": str(repo)},  # no session_id
        home=home,
        karma_api="http://127.0.0.1:1",
    )
    assert result.returncode == 0


def test_silent_exit_with_corrupt_config(home, repo):
    """Garbage config.json — falls back to defaults, hook exits 0."""
    karma = home / ".claude_karma"
    karma.mkdir(parents=True, exist_ok=True)
    (karma / "config.json").write_text("{not json")
    result = _run_hook(
        {"session_id": "sess-1", "cwd": str(repo)},
        home=home,
        karma_api="http://127.0.0.1:1",
    )
    assert result.returncode == 0


def test_silent_exit_with_bad_regex(home, repo):
    """Invalid regex in config is logged and skipped, doesn't crash."""
    _write_config(
        home,
        {
            "branch_detect_enabled": True,
            "ticket_branch_patterns": [
                {"regex": "(unclosed", "provider": "linear"},
            ],
        },
    )
    result = _run_hook(
        {"session_id": "sess-1", "cwd": str(repo)},
        home=home,
        karma_api="http://127.0.0.1:1",
    )
    assert result.returncode == 0


# Pure-function tests on the hook module's helpers
# Module-import variant — exercises non-stdin paths directly.


def _import_hook_module():
    """Import the hook script as a module for direct unit testing."""
    import importlib.util

    spec = importlib.util.spec_from_file_location("ticket_branch_detector", HOOK)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


def test_git_current_branch_returns_branch(repo):
    mod = _import_hook_module()
    assert mod.git_current_branch(str(repo)) == "feat/LINEAR-123-fix-login"


def test_git_current_branch_returns_none_for_non_git(tmp_path):
    mod = _import_hook_module()
    no_git = tmp_path / "x"
    no_git.mkdir()
    assert mod.git_current_branch(str(no_git)) is None


def test_match_pattern_extracts_named_group():
    mod = _import_hook_module()
    patterns = [{"regex": r"(?P<key>[A-Z][A-Z0-9_]+-\d+)", "provider": "linear"}]
    assert mod.match_pattern("feat/LINEAR-123-fix-login", patterns) == ("linear", "LINEAR-123")


def test_match_pattern_returns_whole_match_when_no_named_group():
    mod = _import_hook_module()
    patterns = [{"regex": r"[A-Z][A-Z0-9_]+-\d+", "provider": "jira"}]
    assert mod.match_pattern("PROJ-45-stuff", patterns) == ("jira", "PROJ-45")


def test_match_pattern_first_match_wins():
    mod = _import_hook_module()
    patterns = [
        {"regex": r"NOPE-\d+", "provider": "linear"},
        {"regex": r"(?P<key>[A-Z][A-Z0-9_]+-\d+)", "provider": "jira"},
    ]
    assert mod.match_pattern("FOO-1", patterns) == ("jira", "FOO-1")


def test_match_pattern_skips_unknown_provider():
    mod = _import_hook_module()
    patterns = [{"regex": r"FOO-\d+", "provider": "bitbucket"}]
    assert mod.match_pattern("FOO-1", patterns) is None


def test_lookup_slug_from_live_sessions_returns_best_match(home):
    mod = _import_hook_module()
    live = home / ".claude_karma" / "live-sessions"
    live.mkdir(parents=True, exist_ok=True)
    (live / "a.json").write_text(
        json.dumps({"cwd": "/x/y", "slug": "old-slug", "last_updated": "2026-01-01T00:00:00Z"})
    )
    (live / "b.json").write_text(
        json.dumps({"cwd": "/x/y", "slug": "new-slug", "last_updated": "2026-05-01T00:00:00Z"})
    )
    (live / "c.json").write_text(
        json.dumps({"cwd": "/other", "slug": "wrong", "last_updated": "2026-12-01T00:00:00Z"})
    )
    assert mod.lookup_slug_from_live_sessions("/x/y") == "new-slug"


def test_lookup_slug_returns_none_when_no_match(home):
    mod = _import_hook_module()
    (home / ".claude_karma" / "live-sessions").mkdir(parents=True, exist_ok=True)
    assert mod.lookup_slug_from_live_sessions("/no-match") is None


def test_load_config_uses_defaults_when_missing(home):
    mod = _import_hook_module()
    cfg = mod.load_config()
    assert cfg["branch_detect_enabled"] is False
    assert cfg["ticket_branch_patterns"] == []
