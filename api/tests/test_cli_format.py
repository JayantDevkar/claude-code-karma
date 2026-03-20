"""Tests for CLI output formatters."""
from cli.formatters import format_table, format_for_claude


def _sample_sessions():
    return [
        {
            "uuid": "abc12345-1234-1234-1234-123456789012",
            "slug": "happy-coding-turing",
            "git_branch": "feat/1610",
            "start_time": "2026-03-15T10:00:00+00:00",
            "duration_seconds": 2520.0,
            "message_count": 45,
            "total_cost": 1.25,
            "initial_prompt": "Vamos criar um plano para refatorar o auth",
            "session_titles": "Refactor auth middleware",
            "skills": "ralph-loop, tlc-spec-driven",
            "tools": "Bash(10), Read(25), Edit(8)",
            "project_path": "/home/user/my-project",
        }
    ]


def test_format_table_returns_string():
    result = format_table(_sample_sessions())
    assert isinstance(result, str)
    assert "feat/1610" in result
    assert "abc123" in result


def test_format_for_claude_returns_markdown():
    result = format_for_claude(_sample_sessions())
    assert "## Session" in result
    assert "feat/1610" in result
    assert "ralph-loop" in result
    assert "Refactor auth middleware" in result


def test_format_for_claude_empty_list():
    result = format_for_claude([])
    assert "No sessions found" in result


def test_format_table_empty_list():
    result = format_table([])
    assert "No sessions found" in result
