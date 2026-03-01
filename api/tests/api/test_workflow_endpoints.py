"""Tests for workflow API endpoints."""
import json
import sqlite3
import sys
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

# Set up paths before any imports from the project
_tests_dir = Path(__file__).parent
_api_dir = _tests_dir.parent.parent
if str(_api_dir) not in sys.path:
    sys.path.insert(0, str(_api_dir))


@pytest.fixture
def client(tmp_path):
    """Create a test client with a real SQLite DB."""
    db_path = tmp_path / "test.db"
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")

    from db.schema import ensure_schema

    ensure_schema(conn)
    conn.close()

    with (
        patch("db.connection.get_db_path", return_value=db_path),
        patch("config.settings.use_sqlite", True),
    ):
        from main import app

        yield TestClient(app)


@pytest.fixture
def sample_workflow():
    return {
        "name": "test-workflow",
        "description": "A test workflow",
        "graph": {
            "nodes": [
                {"id": "s1", "position": {"x": 0, "y": 0}},
                {"id": "s2", "position": {"x": 0, "y": 100}},
            ],
            "edges": [{"source": "s1", "target": "s2"}],
        },
        "steps": [
            {"id": "s1", "prompt_template": "Hello {{ inputs.name }}"},
            {"id": "s2", "prompt_template": "Review: {{ steps.s1.output }}"},
        ],
        "inputs": [{"name": "name", "type": "string", "required": True}],
    }


def test_create_workflow(client, sample_workflow):
    resp = client.post("/workflows", json=sample_workflow)
    assert resp.status_code == 201
    data = resp.json()
    assert data["name"] == "test-workflow"
    assert data["id"] is not None
    assert len(data["steps"]) == 2


def test_list_workflows(client, sample_workflow):
    client.post("/workflows", json=sample_workflow)
    resp = client.get("/workflows")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) >= 1
    assert data[0]["name"] == "test-workflow"


def test_get_workflow(client, sample_workflow):
    create_resp = client.post("/workflows", json=sample_workflow)
    wf_id = create_resp.json()["id"]

    resp = client.get(f"/workflows/{wf_id}")
    assert resp.status_code == 200
    assert resp.json()["id"] == wf_id


def test_get_workflow_not_found(client):
    resp = client.get("/workflows/nonexistent")
    assert resp.status_code == 404


def test_update_workflow(client, sample_workflow):
    create_resp = client.post("/workflows", json=sample_workflow)
    wf_id = create_resp.json()["id"]

    sample_workflow["name"] = "updated-workflow"
    resp = client.put(f"/workflows/{wf_id}", json=sample_workflow)
    assert resp.status_code == 200
    assert resp.json()["name"] == "updated-workflow"


def test_delete_workflow(client, sample_workflow):
    create_resp = client.post("/workflows", json=sample_workflow)
    wf_id = create_resp.json()["id"]

    resp = client.delete(f"/workflows/{wf_id}")
    assert resp.status_code == 204

    resp = client.get(f"/workflows/{wf_id}")
    assert resp.status_code == 404


def test_list_runs_empty(client, sample_workflow):
    create_resp = client.post("/workflows", json=sample_workflow)
    wf_id = create_resp.json()["id"]

    resp = client.get(f"/workflows/{wf_id}/runs")
    assert resp.status_code == 200
    assert resp.json() == []
