"""Tests for workflow API endpoints."""
from unittest.mock import AsyncMock, patch

import pytest


def test_create_workflow(workflow_client, sample_workflow):
    resp = workflow_client.post("/workflows", json=sample_workflow)
    assert resp.status_code == 201
    data = resp.json()
    assert data["name"] == "Test Workflow"
    assert data["id"] is not None
    assert len(data["steps"]) == 2


def test_list_workflows(workflow_client, sample_workflow):
    workflow_client.post("/workflows", json=sample_workflow)
    resp = workflow_client.get("/workflows")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) >= 1
    assert data[0]["name"] == "Test Workflow"


def test_get_workflow(workflow_client, sample_workflow):
    create_resp = workflow_client.post("/workflows", json=sample_workflow)
    wf_id = create_resp.json()["id"]

    resp = workflow_client.get(f"/workflows/{wf_id}")
    assert resp.status_code == 200
    assert resp.json()["id"] == wf_id


def test_get_workflow_not_found(workflow_client):
    resp = workflow_client.get("/workflows/nonexistent")
    assert resp.status_code == 404


def test_update_workflow(workflow_client, sample_workflow):
    create_resp = workflow_client.post("/workflows", json=sample_workflow)
    wf_id = create_resp.json()["id"]

    sample_workflow["name"] = "updated-workflow"
    resp = workflow_client.put(f"/workflows/{wf_id}", json=sample_workflow)
    assert resp.status_code == 200
    assert resp.json()["name"] == "updated-workflow"


def test_delete_workflow(workflow_client, sample_workflow):
    create_resp = workflow_client.post("/workflows", json=sample_workflow)
    wf_id = create_resp.json()["id"]

    resp = workflow_client.delete(f"/workflows/{wf_id}")
    assert resp.status_code == 204

    resp = workflow_client.get(f"/workflows/{wf_id}")
    assert resp.status_code == 404


def test_list_runs_empty(workflow_client, sample_workflow):
    create_resp = workflow_client.post("/workflows", json=sample_workflow)
    wf_id = create_resp.json()["id"]

    resp = workflow_client.get(f"/workflows/{wf_id}/runs")
    assert resp.status_code == 200
    assert resp.json() == []


def test_trigger_run(workflow_client, sample_workflow):
    # Create workflow first
    create_resp = workflow_client.post("/workflows", json=sample_workflow)
    assert create_resp.status_code == 201
    wf_id = create_resp.json()["id"]

    with patch("routers.workflows.execute_workflow", new_callable=AsyncMock):
        resp = workflow_client.post(f"/workflows/{wf_id}/run", json={"input_values": {}})
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "pending"
        assert data["workflow_id"] == wf_id
        assert len(data["steps"]) == 2


def test_update_workflow_not_found(workflow_client, sample_workflow):
    resp = workflow_client.put("/workflows/nonexistent", json=sample_workflow)
    assert resp.status_code == 404


def test_delete_workflow_not_found(workflow_client):
    resp = workflow_client.delete("/workflows/nonexistent")
    assert resp.status_code == 404


def test_get_run_not_found(workflow_client, sample_workflow):
    create_resp = workflow_client.post("/workflows", json=sample_workflow)
    wf_id = create_resp.json()["id"]
    resp = workflow_client.get(f"/workflows/{wf_id}/runs/nonexistent")
    assert resp.status_code == 404


def test_create_workflow_with_cycle_rejected(workflow_client):
    """POST a workflow with cyclic edges should return 422."""
    payload = {
        "name": "Cyclic Workflow",
        "graph": {
            "nodes": [
                {"id": "a", "position": {"x": 0, "y": 0}},
                {"id": "b", "position": {"x": 100, "y": 0}},
            ],
            "edges": [
                {"id": "e1", "source": "a", "target": "b"},
                {"id": "e2", "source": "b", "target": "a"},
            ],
        },
        "steps": [
            {"id": "a", "prompt_template": "Step A"},
            {"id": "b", "prompt_template": "Step B"},
        ],
        "inputs": [],
    }
    resp = workflow_client.post("/workflows", json=payload)
    assert resp.status_code == 422


def test_create_workflow_with_edge_condition(workflow_client):
    """Edges can carry conditions."""
    payload = {
        "name": "Conditional Workflow",
        "graph": {
            "nodes": [
                {"id": "s1", "position": {"x": 0, "y": 0}},
                {"id": "s2", "position": {"x": 100, "y": 0}},
            ],
            "edges": [
                {"id": "e1", "source": "s1", "target": "s2", "condition": "{{ steps.s1.output }} == yes"},
            ],
        },
        "steps": [
            {"id": "s1", "prompt_template": "Check something"},
            {"id": "s2", "prompt_template": "Conditional step"},
        ],
        "inputs": [],
    }
    resp = workflow_client.post("/workflows", json=payload)
    assert resp.status_code == 201
    data = resp.json()
    # Verify edge condition is stored and returned
    edges = data["graph"]["edges"]
    assert len(edges) == 1
    assert edges[0]["condition"] == "{{ steps.s1.output }} == yes"
