"""Integration test: create workflow, verify it's retrievable, delete it."""


def test_workflow_crud_lifecycle(workflow_client):
    """Full CRUD lifecycle for a workflow."""
    # Create
    payload = {
        "name": "e2e-test",
        "graph": {"nodes": [{"id": "s1", "position": {"x": 0, "y": 0}}], "edges": []},
        "steps": [{"id": "s1", "prompt_template": "Say hello"}],
        "inputs": [],
    }
    resp = workflow_client.post("/workflows", json=payload)
    assert resp.status_code == 201
    wf_id = resp.json()["id"]

    # Read
    resp = workflow_client.get(f"/workflows/{wf_id}")
    assert resp.status_code == 200
    assert resp.json()["name"] == "e2e-test"

    # Update
    payload["name"] = "e2e-updated"
    resp = workflow_client.put(f"/workflows/{wf_id}", json=payload)
    assert resp.status_code == 200
    assert resp.json()["name"] == "e2e-updated"

    # List
    resp = workflow_client.get("/workflows")
    assert any(w["id"] == wf_id for w in resp.json())

    # Runs (empty)
    resp = workflow_client.get(f"/workflows/{wf_id}/runs")
    assert resp.status_code == 200
    assert resp.json() == []

    # Delete
    resp = workflow_client.delete(f"/workflows/{wf_id}")
    assert resp.status_code == 204

    # Verify deleted
    resp = workflow_client.get(f"/workflows/{wf_id}")
    assert resp.status_code == 404
