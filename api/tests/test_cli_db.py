"""Tests for CLI database reader."""
import sqlite3
from pathlib import Path
from unittest.mock import patch

import pytest

from cli.db import get_read_connection, DB_PATH


def test_db_path_points_to_karma_metadata():
    """DB_PATH should resolve to ~/.claude_karma/metadata.db."""
    expected = Path.home() / ".claude_karma" / "metadata.db"
    assert DB_PATH == expected


def test_get_read_connection_returns_readonly_connection(tmp_path):
    """get_read_connection should return a read-only sqlite3 connection."""
    db_file = tmp_path / "test.db"
    conn = sqlite3.connect(str(db_file))
    conn.execute("CREATE TABLE t (id INTEGER)")
    conn.commit()
    conn.close()

    with patch("cli.db.DB_PATH", db_file):
        read_conn = get_read_connection()
        assert read_conn is not None
        read_conn.execute("SELECT * FROM t")
        read_conn.close()


def test_get_read_connection_raises_if_db_missing(tmp_path):
    """get_read_connection should raise if database file does not exist."""
    fake_path = tmp_path / "nonexistent.db"
    with patch("cli.db.DB_PATH", fake_path):
        with pytest.raises(FileNotFoundError):
            get_read_connection()
