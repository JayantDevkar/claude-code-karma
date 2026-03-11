"""
Pytest configuration for API tests.

Sets up proper Python paths for importing the API modules.
"""

import sqlite3
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

# Get paths
tests_dir = Path(__file__).parent
api_dir = tests_dir.parent
apps_dir = api_dir.parent
root_dir = apps_dir.parent

# Add the apps directory (so 'api' can be imported as a package)
# Add the root directory (so 'models' can be imported)
# The order matters - insert in reverse order of priority
sys.path.insert(0, str(root_dir))
sys.path.insert(0, str(apps_dir))
sys.path.insert(0, str(api_dir))


@pytest.fixture
def mock_claude_base(tmp_path, monkeypatch):
    """
    Fixture that redirects settings.claude_base to a temp directory.

    Creates the necessary directory structure and patches settings.
    Returns the temp .claude directory path.
    """
    claude_dir = tmp_path / ".claude"
    claude_dir.mkdir(parents=True, exist_ok=True)
    (claude_dir / "projects").mkdir(exist_ok=True)

    from config import settings

    monkeypatch.setattr(settings, "claude_base", claude_dir)

    return claude_dir


@pytest.fixture
def workflow_client(tmp_path):
    """Test client with workflow schema initialized in a temp workflow.db."""
    from fastapi.testclient import TestClient

    wf_db_path = tmp_path / "workflow.db"
    meta_db_path = tmp_path / "metadata.db"

    with patch("db.workflow_db.get_workflow_db_path", return_value=wf_db_path), \
         patch("db.workflow_db._wf_writer", None), \
         patch("db.connection.get_db_path", return_value=meta_db_path), \
         patch("config.settings.use_sqlite", True):
        # Initialize workflow DB schema
        conn = sqlite3.connect(str(wf_db_path))
        conn.row_factory = sqlite3.Row
        from db.workflow_schema import ensure_workflow_schema
        ensure_workflow_schema(conn)
        conn.close()

        # Initialize metadata DB schema (needed for app startup)
        meta_conn = sqlite3.connect(str(meta_db_path))
        meta_conn.row_factory = sqlite3.Row
        from db.schema import ensure_schema
        ensure_schema(meta_conn)
        meta_conn.close()

        from main import app
        yield TestClient(app)


@pytest.fixture
def sample_workflow():
    """Sample workflow payload for testing."""
    return {
        "name": "Test Workflow",
        "description": "A test workflow",
        "project_path": None,
        "graph": {
            "nodes": [
                {"id": "step_1", "type": "step", "position": {"x": 0, "y": 0}, "data": {"label": "Step 1"}},
                {"id": "step_2", "type": "step", "position": {"x": 200, "y": 0}, "data": {"label": "Step 2"}},
            ],
            "edges": [{"id": "e1", "source": "step_1", "target": "step_2"}],
        },
        "steps": [
            {"id": "step_1", "prompt_template": "Do task 1", "model": "sonnet", "tools": ["Read"], "max_turns": 5},
            {"id": "step_2", "prompt_template": "Do task 2 based on {{ steps.step_1.output }}", "model": "sonnet", "tools": ["Read", "Edit"], "max_turns": 10},
        ],
        "inputs": [],
    }
