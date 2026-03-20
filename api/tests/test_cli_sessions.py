"""Tests for karma sessions get command."""
import sqlite3
from unittest.mock import patch

import pytest
from click.testing import CliRunner

from cli.main import cli


@pytest.fixture
def sample_db(tmp_path):
    """Create a temporary SQLite database with a sample session."""
    db_file = tmp_path / "metadata.db"
    conn = sqlite3.connect(str(db_file))
    conn.executescript("""
        CREATE TABLE sessions (
            uuid TEXT PRIMARY KEY,
            slug TEXT,
            project_encoded_name TEXT NOT NULL,
            project_path TEXT,
            start_time TEXT,
            end_time TEXT,
            message_count INTEGER DEFAULT 0,
            duration_seconds REAL,
            input_tokens INTEGER DEFAULT 0,
            output_tokens INTEGER DEFAULT 0,
            cache_creation_tokens INTEGER DEFAULT 0,
            cache_read_tokens INTEGER DEFAULT 0,
            total_cost REAL DEFAULT 0,
            initial_prompt TEXT,
            git_branch TEXT,
            models_used TEXT,
            session_titles TEXT,
            is_continuation_marker INTEGER DEFAULT 0,
            was_compacted INTEGER DEFAULT 0,
            compaction_count INTEGER DEFAULT 0,
            file_snapshot_count INTEGER DEFAULT 0,
            subagent_count INTEGER DEFAULT 0,
            jsonl_mtime REAL NOT NULL,
            jsonl_size INTEGER DEFAULT 0,
            session_source TEXT,
            source_encoded_name TEXT,
            indexed_at TEXT DEFAULT (datetime('now'))
        );
        CREATE TABLE session_tools (
            session_uuid TEXT NOT NULL,
            tool_name TEXT NOT NULL,
            count INTEGER DEFAULT 1,
            PRIMARY KEY (session_uuid, tool_name)
        );
        CREATE TABLE session_skills (
            session_uuid TEXT NOT NULL,
            skill_name TEXT NOT NULL,
            invocation_source TEXT NOT NULL DEFAULT 'skill_tool',
            count INTEGER DEFAULT 1,
            PRIMARY KEY (session_uuid, skill_name, invocation_source)
        );
    """)
    conn.execute("""
        INSERT INTO sessions (uuid, slug, project_encoded_name, project_path,
            start_time, duration_seconds, message_count, total_cost,
            initial_prompt, git_branch, session_titles, jsonl_mtime)
        VALUES ('aaaa-1111-2222-3333', 'happy-turing', '-home-user-project',
            '/home/user/project',
            '2026-03-15T10:00:00+00:00', 2520, 45, 1.25,
            'Vamos criar um plano', 'feat/1610',
            'Refactor auth', 1710500000)
    """)
    conn.execute("INSERT INTO session_tools VALUES ('aaaa-1111-2222-3333', 'Read', 25)")
    conn.execute("INSERT INTO session_skills VALUES ('aaaa-1111-2222-3333', 'ralph-loop', 'skill_tool', 1)")
    conn.commit()
    conn.close()
    return db_file


def test_sessions_get_metadata(sample_db):
    runner = CliRunner()
    with patch("cli.db.DB_PATH", sample_db):
        result = runner.invoke(cli, ["sessions", "get", "aaaa-1111-2222-3333"])
    assert result.exit_code == 0
    assert "aaaa" in result.output


def test_sessions_get_for_claude(sample_db):
    runner = CliRunner()
    with patch("cli.db.DB_PATH", sample_db):
        result = runner.invoke(cli, ["sessions", "get", "aaaa-1111-2222-3333", "--for-claude"])
    assert result.exit_code == 0
    assert "## Session" in result.output
    assert "ralph-loop" in result.output


def test_sessions_get_not_found(sample_db):
    runner = CliRunner()
    with patch("cli.db.DB_PATH", sample_db):
        result = runner.invoke(cli, ["sessions", "get", "nonexistent"])
    assert result.exit_code == 0
    assert "not found" in result.output.lower()


def test_sessions_get_partial_uuid(sample_db):
    """Should find session by partial UUID prefix."""
    runner = CliRunner()
    with patch("cli.db.DB_PATH", sample_db):
        result = runner.invoke(cli, ["sessions", "get", "aaaa-1111"])
    assert result.exit_code == 0
    assert "aaaa" in result.output
