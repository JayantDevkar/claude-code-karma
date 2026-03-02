"""Tests for workflow schema — normalized tables in workflow.db."""
import json
import sqlite3

import pytest
from unittest.mock import patch, PropertyMock

from config import Settings
from db.schema import ensure_schema, SCHEMA_VERSION
from db.workflow_schema import ensure_workflow_schema, migrate_from_metadata_db, WORKFLOW_SCHEMA_VERSION


def test_metadata_schema_version_is_10():
    assert SCHEMA_VERSION == 10


def test_workflow_schema_version_is_1():
    assert WORKFLOW_SCHEMA_VERSION == 1


def test_workflow_tables_in_workflow_db(tmp_path):
    """Workflow tables should exist in workflow.db."""
    db_path = tmp_path / "workflow.db"
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    ensure_workflow_schema(conn)

    tables = {
        row[0]
        for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
    }
    assert "workflows" in tables
    assert "workflow_steps" in tables
    assert "workflow_edges" in tables
    assert "workflow_inputs" in tables
    assert "workflow_runs" in tables
    assert "workflow_run_steps" in tables
    conn.close()


def test_workflow_tables_not_in_metadata_db(tmp_path):
    """After v10 migration, workflow tables should NOT exist in metadata.db."""
    wf_path = tmp_path / "workflow.db"
    db_path = tmp_path / "metadata.db"

    # Create workflow.db with migration log (simulates completed migration)
    wf_conn = sqlite3.connect(str(wf_path))
    ensure_workflow_schema(wf_conn)
    wf_conn.execute("INSERT OR IGNORE INTO wf_migration_log (source) VALUES ('metadata_db')")
    wf_conn.commit()
    wf_conn.close()

    with patch.object(Settings, "workflow_db_path", new_callable=PropertyMock, return_value=wf_path):
        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
        ensure_schema(conn)

        tables = {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
        assert "workflows" not in tables
        assert "workflow_runs" not in tables
        assert "workflow_run_steps" not in tables
        conn.close()


def test_workflows_table_columns(tmp_path):
    """Normalized workflows table should have node_positions instead of graph/steps/inputs."""
    db_path = tmp_path / "workflow.db"
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    ensure_workflow_schema(conn)

    cols = {row[1] for row in conn.execute("PRAGMA table_info(workflows)").fetchall()}
    assert cols == {
        "id", "name", "description", "project_path",
        "node_positions", "created_at", "updated_at",
    }
    conn.close()


def test_workflow_steps_table_columns(tmp_path):
    db_path = tmp_path / "workflow.db"
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    ensure_workflow_schema(conn)

    cols = {row[1] for row in conn.execute("PRAGMA table_info(workflow_steps)").fetchall()}
    assert cols == {
        "id", "workflow_id", "prompt_template", "model",
        "tools", "max_turns", "sort_order",
    }
    conn.close()


def test_workflow_edges_table_columns(tmp_path):
    db_path = tmp_path / "workflow.db"
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    ensure_workflow_schema(conn)

    cols = {row[1] for row in conn.execute("PRAGMA table_info(workflow_edges)").fetchall()}
    assert cols == {"id", "workflow_id", "source", "target", "condition"}
    conn.close()


def test_migration_from_v9_to_v10(tmp_path):
    """Test incremental migration from v9 to v10 drops workflow tables."""
    wf_path = tmp_path / "workflow.db"
    db_path = tmp_path / "metadata.db"

    # Create workflow.db with migration log
    wf_conn = sqlite3.connect(str(wf_path))
    ensure_workflow_schema(wf_conn)
    wf_conn.execute("INSERT OR IGNORE INTO wf_migration_log (source) VALUES ('metadata_db')")
    wf_conn.commit()
    wf_conn.close()

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row

    # Simulate v9 state with workflow tables
    conn.execute("CREATE TABLE schema_version (version INTEGER PRIMARY KEY, applied_at TEXT)")
    conn.execute("INSERT INTO schema_version (version) VALUES (9)")
    conn.execute("CREATE TABLE workflows (id TEXT PRIMARY KEY, name TEXT)")
    conn.execute("CREATE TABLE workflow_runs (id TEXT PRIMARY KEY)")
    conn.execute("CREATE TABLE workflow_run_steps (id TEXT PRIMARY KEY)")
    conn.commit()

    with patch.object(Settings, "workflow_db_path", new_callable=PropertyMock, return_value=wf_path):
        ensure_schema(conn)

    row = conn.execute("SELECT MAX(version) FROM schema_version").fetchone()
    assert row[0] == 10

    tables = {
        row[0]
        for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
    }
    assert "workflows" not in tables
    assert "workflow_runs" not in tables
    assert "workflow_run_steps" not in tables
    conn.close()


def test_migration_data_transfer(tmp_path):
    """Test that migrate_from_metadata_db copies workflow data correctly."""
    meta_path = tmp_path / "metadata.db"
    wf_path = tmp_path / "workflow.db"

    # Set up metadata.db with a workflow
    meta_conn = sqlite3.connect(str(meta_path))
    meta_conn.row_factory = sqlite3.Row
    meta_conn.execute("""
        CREATE TABLE workflows (
            id TEXT PRIMARY KEY, name TEXT, description TEXT,
            project_path TEXT, graph JSON, steps JSON, inputs JSON,
            created_at TEXT, updated_at TEXT
        )
    """)
    meta_conn.execute(
        "INSERT INTO workflows VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            "wf-1", "Test WF", "desc", None,
            json.dumps({
                "nodes": [{"id": "s1", "position": {"x": 0, "y": 0}, "type": "step"}],
                "edges": [{"id": "e1", "source": "s1", "target": "s2"}],
            }),
            json.dumps([
                {"id": "s1", "prompt_template": "Do A", "model": "sonnet", "tools": ["Read"], "max_turns": 5},
                {"id": "s2", "prompt_template": "Do B", "model": "opus", "tools": ["Edit"], "max_turns": 10, "condition": "old_cond"},
            ]),
            json.dumps([{"name": "feat", "type": "string", "required": True}]),
            "2026-01-01", "2026-01-02",
        ),
    )
    meta_conn.commit()
    meta_conn.close()

    # Set up workflow.db
    wf_conn = sqlite3.connect(str(wf_path))
    wf_conn.row_factory = sqlite3.Row
    ensure_workflow_schema(wf_conn)

    # Run migration (patch sqlite_db_path to our temp metadata.db)
    with patch.object(Settings, "sqlite_db_path", new_callable=PropertyMock, return_value=meta_path):
        migrate_from_metadata_db(wf_conn)

    # Verify data
    wf = wf_conn.execute("SELECT * FROM workflows WHERE id = 'wf-1'").fetchone()
    assert wf["name"] == "Test WF"

    steps = wf_conn.execute(
        "SELECT * FROM workflow_steps WHERE workflow_id = 'wf-1' ORDER BY sort_order"
    ).fetchall()
    assert len(steps) == 2
    assert steps[0]["id"] == "s1"
    assert steps[1]["model"] == "opus"

    edges = wf_conn.execute(
        "SELECT * FROM workflow_edges WHERE workflow_id = 'wf-1'"
    ).fetchall()
    assert len(edges) == 1
    assert edges[0]["source"] == "s1"
    assert edges[0]["condition"] is None  # Old step conditions are dropped

    inputs = wf_conn.execute(
        "SELECT * FROM workflow_inputs WHERE workflow_id = 'wf-1'"
    ).fetchall()
    assert len(inputs) == 1
    assert inputs[0]["name"] == "feat"

    # Verify migration log recorded
    log = wf_conn.execute(
        "SELECT 1 FROM wf_migration_log WHERE source = 'metadata_db'"
    ).fetchone()
    assert log is not None

    wf_conn.close()
