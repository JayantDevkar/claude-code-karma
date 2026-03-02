"""
Workflow router — CRUD for workflow definitions + execution triggers.

Endpoints:
    GET    /workflows                     List all workflows
    POST   /workflows                     Create workflow
    GET    /workflows/{id}                Get workflow
    PUT    /workflows/{id}                Update workflow
    DELETE /workflows/{id}                Delete workflow
    POST   /workflows/{id}/run            Trigger execution
    GET    /workflows/{id}/runs            List runs
    GET    /workflows/{id}/runs/{run_id}   Get run status
"""

import asyncio
import json
import logging
import uuid
from collections import defaultdict
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, HTTPException

from db.workflow_db import create_wf_read_conn, get_wf_writer
from schemas import (
    WorkflowCreateRequest,
    WorkflowResponse,
    WorkflowRunRequest,
    WorkflowRunResponse,
    WorkflowRunStepResponse,
    WorkflowStepSchema,
)
from services.workflow_engine import execute_workflow, topological_sort

logger = logging.getLogger(__name__)

router = APIRouter()

# Track active background workflow tasks so they aren't garbage-collected
_active_tasks: dict[str, asyncio.Task] = {}


def _load_workflow_response(conn, wf_id: str) -> dict | None:
    """
    Load a workflow from normalized tables and reconstruct the response dict
    that the frontend expects (graph: {nodes, edges}, steps, inputs).

    Returns None if the workflow is not found.
    """
    row = conn.execute(
        "SELECT * FROM workflows WHERE id = ?", (wf_id,)
    ).fetchone()
    if not row:
        return None

    # Rebuild graph.nodes from stored node_positions JSON
    node_positions = json.loads(row["node_positions"]) if row["node_positions"] else {}
    graph_nodes = [
        {"id": step_id, **pos_data}
        for step_id, pos_data in node_positions.items()
    ]

    # Rebuild graph.edges from workflow_edges table
    edge_rows = conn.execute(
        "SELECT * FROM workflow_edges WHERE workflow_id = ? ORDER BY id",
        (wf_id,),
    ).fetchall()
    graph_edges = []
    for e in edge_rows:
        edge = {"id": e["id"], "source": e["source"], "target": e["target"]}
        if e["condition"] is not None:
            edge["condition"] = e["condition"]
        graph_edges.append(edge)

    # Load steps from workflow_steps table
    step_rows = conn.execute(
        "SELECT * FROM workflow_steps WHERE workflow_id = ? ORDER BY sort_order",
        (wf_id,),
    ).fetchall()
    steps = [
        {
            "id": s["id"],
            "label": s["label"] if "label" in s.keys() else None,
            "prompt_template": s["prompt_template"],
            "model": s["model"],
            "tools": json.loads(s["tools"]) if s["tools"] else [],
            "max_turns": s["max_turns"],
        }
        for s in step_rows
    ]

    # Load inputs from workflow_inputs table
    input_rows = conn.execute(
        "SELECT * FROM workflow_inputs WHERE workflow_id = ? ORDER BY sort_order",
        (wf_id,),
    ).fetchall()
    inputs = [
        {
            "name": i["name"],
            "type": i["type"],
            "required": bool(i["required"]),
            "default": i["default_val"],
            "description": i["description"],
        }
        for i in input_rows
    ]

    return {
        "id": row["id"],
        "name": row["name"],
        "description": row["description"],
        "project_path": row["project_path"],
        "graph": {"nodes": graph_nodes, "edges": graph_edges},
        "steps": steps,
        "inputs": inputs,
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


def _save_workflow_normalized(
    conn,
    wf_id: str,
    req: WorkflowCreateRequest,
    now: str,
    *,
    is_update: bool = False,
) -> None:
    """
    Persist a workflow to the normalized tables.

    For create (is_update=False): INSERTs the workflow row and all child rows.
    For update (is_update=True): DELETEs existing child rows, UPDATEs the
    workflow row, then INSERTs fresh child rows.

    Raises HTTPException(422) if the edge graph contains a cycle.
    """
    # Validate no cycle in the edge graph
    step_ids = [s.id for s in req.steps]
    raw_edges = req.graph.get("edges", [])
    edge_dicts = [
        {"source": e["source"], "target": e["target"]} for e in raw_edges
    ]
    try:
        topological_sort(step_ids, edge_dicts)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    # Extract node_positions from graph.nodes
    nodes = req.graph.get("nodes", [])
    node_positions: dict = {}
    for node in nodes:
        node_id = node.get("id")
        if node_id:
            node_positions[node_id] = {k: v for k, v in node.items() if k != "id"}

    if is_update:
        # Remove old child rows
        conn.execute("DELETE FROM workflow_steps WHERE workflow_id = ?", (wf_id,))
        conn.execute("DELETE FROM workflow_edges WHERE workflow_id = ?", (wf_id,))
        conn.execute("DELETE FROM workflow_inputs WHERE workflow_id = ?", (wf_id,))
        # Update the workflow row
        conn.execute(
            """UPDATE workflows
               SET name=?, description=?, project_path=?, node_positions=?, updated_at=?
               WHERE id=?""",
            (
                req.name,
                req.description,
                req.project_path,
                json.dumps(node_positions),
                now,
                wf_id,
            ),
        )
    else:
        # Insert the workflow row
        conn.execute(
            """INSERT INTO workflows (id, name, description, project_path, node_positions, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (
                wf_id,
                req.name,
                req.description,
                req.project_path,
                json.dumps(node_positions),
                now,
                now,
            ),
        )

    # Insert steps
    for order, step in enumerate(req.steps):
        conn.execute(
            """INSERT INTO workflow_steps (id, workflow_id, label, prompt_template, model, tools, max_turns, sort_order)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                step.id,
                wf_id,
                step.label,
                step.prompt_template,
                step.model,
                json.dumps(step.tools),
                step.max_turns,
                order,
            ),
        )

    # Insert edges
    for edge in raw_edges:
        edge_id = edge.get("id") or f"{edge['source']}_{edge['target']}"
        condition = edge.get("condition")
        conn.execute(
            """INSERT INTO workflow_edges (id, workflow_id, source, target, condition)
               VALUES (?, ?, ?, ?, ?)""",
            (edge_id, wf_id, edge["source"], edge["target"], condition),
        )

    # Insert inputs
    for order, inp in enumerate(req.inputs):
        conn.execute(
            """INSERT INTO workflow_inputs
               (workflow_id, name, type, required, default_val, description, sort_order)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (
                wf_id,
                inp.name,
                inp.type,
                1 if inp.required else 0,
                inp.default,
                inp.description,
                order,
            ),
        )


@router.get("", response_model=list[WorkflowResponse])
def list_workflows():
    conn = create_wf_read_conn()
    try:
        rows = conn.execute(
            "SELECT id FROM workflows ORDER BY updated_at DESC"
        ).fetchall()
        result = []
        for row in rows:
            data = _load_workflow_response(conn, row["id"])
            if data is not None:
                result.append(WorkflowResponse(**data))
        return result
    finally:
        conn.close()


@router.post("", response_model=WorkflowResponse, status_code=201)
def create_workflow(req: WorkflowCreateRequest):
    wf_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()

    conn = get_wf_writer()
    _save_workflow_normalized(conn, wf_id, req, now, is_update=False)
    conn.commit()

    # Read back through a fresh read connection for consistency
    read_conn = create_wf_read_conn()
    try:
        data = _load_workflow_response(read_conn, wf_id)
    finally:
        read_conn.close()

    return WorkflowResponse(**data)


@router.get("/{workflow_id}", response_model=WorkflowResponse)
def get_workflow(workflow_id: str):
    conn = create_wf_read_conn()
    try:
        data = _load_workflow_response(conn, workflow_id)
        if data is None:
            raise HTTPException(status_code=404, detail="Workflow not found")
        return WorkflowResponse(**data)
    finally:
        conn.close()


@router.put("/{workflow_id}", response_model=WorkflowResponse)
def update_workflow(workflow_id: str, req: WorkflowCreateRequest):
    now = datetime.now(timezone.utc).isoformat()

    conn = get_wf_writer()
    exists = conn.execute(
        "SELECT id FROM workflows WHERE id = ?", (workflow_id,)
    ).fetchone()
    if not exists:
        raise HTTPException(status_code=404, detail="Workflow not found")

    _save_workflow_normalized(conn, workflow_id, req, now, is_update=True)
    conn.commit()

    read_conn = create_wf_read_conn()
    try:
        data = _load_workflow_response(read_conn, workflow_id)
    finally:
        read_conn.close()

    return WorkflowResponse(**data)


@router.delete("/{workflow_id}", status_code=204)
def delete_workflow(workflow_id: str):
    conn = get_wf_writer()
    result = conn.execute("DELETE FROM workflows WHERE id = ?", (workflow_id,))
    conn.commit()
    if result.rowcount == 0:
        raise HTTPException(status_code=404, detail="Workflow not found")


@router.post("/{workflow_id}/run", response_model=WorkflowRunResponse)
async def trigger_run(workflow_id: str, req: Optional[WorkflowRunRequest] = None):
    # Load workflow definition from normalized tables
    read_conn = create_wf_read_conn()
    try:
        wf_row = read_conn.execute(
            "SELECT id, name, project_path FROM workflows WHERE id = ?", (workflow_id,)
        ).fetchone()
        if not wf_row:
            raise HTTPException(status_code=404, detail="Workflow not found")

        project_path = wf_row["project_path"]
        workflow_name = wf_row["name"]

        step_rows = read_conn.execute(
            "SELECT * FROM workflow_steps WHERE workflow_id = ? ORDER BY sort_order",
            (workflow_id,),
        ).fetchall()
        edge_rows = read_conn.execute(
            "SELECT * FROM workflow_edges WHERE workflow_id = ?",
            (workflow_id,),
        ).fetchall()

        # Convert rows to dicts for the engine
        steps = [
            {
                "id": s["id"],
                "prompt_template": s["prompt_template"],
                "model": s["model"],
                "tools": json.loads(s["tools"]) if s["tools"] else [],
                "max_turns": s["max_turns"],
            }
            for s in step_rows
        ]
        edges = [
            {
                "source": e["source"],
                "target": e["target"],
                "condition": e["condition"],
            }
            for e in edge_rows
        ]

        # Check concurrent run limit
        active_count = read_conn.execute(
            "SELECT COUNT(*) FROM workflow_runs WHERE workflow_id = ? AND status IN ('pending', 'running')",
            (workflow_id,),
        ).fetchone()[0]
        if active_count >= 3:
            raise HTTPException(
                status_code=429, detail="Maximum 3 concurrent runs per workflow"
            )
    finally:
        read_conn.close()

    # Create run + step records
    run_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()
    input_values = req.input_values if req else None

    wconn = get_wf_writer()
    step_responses = []
    wconn.execute(
        """INSERT INTO workflow_runs (id, workflow_id, status, input_values, started_at)
           VALUES (?, ?, 'pending', ?, ?)""",
        (run_id, workflow_id, json.dumps(input_values) if input_values else None, now),
    )
    for s in steps:
        step_record_id = str(uuid.uuid4())
        wconn.execute(
            """INSERT INTO workflow_run_steps (id, run_id, step_id, status)
               VALUES (?, ?, ?, 'pending')""",
            (step_record_id, run_id, s["id"]),
        )
        step_responses.append(
            WorkflowRunStepResponse(id=step_record_id, step_id=s["id"], status="pending")
        )
    wconn.commit()

    # Launch background execution with task tracking
    task = asyncio.create_task(
        execute_workflow(
            run_id=run_id,
            workflow_id=workflow_id,
            steps=steps,
            edges=edges,
            input_values=input_values or {},
            project_path=project_path,
            workflow_name=workflow_name,
        )
    )
    _active_tasks[run_id] = task

    def _on_task_done(t: asyncio.Task, rid: str = run_id):
        _active_tasks.pop(rid, None)
        if not t.cancelled() and t.exception():
            logger.error(
                "Workflow run %s failed with unhandled error: %s", rid, t.exception()
            )

    task.add_done_callback(_on_task_done)

    return WorkflowRunResponse(
        id=run_id,
        workflow_id=workflow_id,
        status="pending",
        input_values=input_values,
        started_at=now,
        steps=step_responses,
    )


@router.get("/{workflow_id}/runs", response_model=list[WorkflowRunResponse])
def list_runs(workflow_id: str):
    conn = create_wf_read_conn()
    try:
        rows = conn.execute(
            "SELECT * FROM workflow_runs WHERE workflow_id = ? ORDER BY started_at DESC",
            (workflow_id,),
        ).fetchall()

        # Batch fetch ALL steps for these runs in one query
        run_ids = [r["id"] for r in rows]
        if run_ids:
            placeholders = ",".join("?" * len(run_ids))
            step_rows = conn.execute(
                f"SELECT * FROM workflow_run_steps WHERE run_id IN ({placeholders})",
                run_ids,
            ).fetchall()
        else:
            step_rows = []

        # Group steps by run_id
        steps_by_run: dict[str, list[WorkflowRunStepResponse]] = defaultdict(list)
        for s in step_rows:
            steps_by_run[s["run_id"]].append(
                WorkflowRunStepResponse(
                    id=s["id"],
                    step_id=s["step_id"],
                    status=s["status"],
                    session_id=s.get("session_id"),
                    prompt=s.get("prompt"),
                    output=s.get("output"),
                    started_at=s.get("started_at"),
                    completed_at=s.get("completed_at"),
                    error=s.get("error"),
                )
            )

        result = []
        for r in rows:
            result.append(
                WorkflowRunResponse(
                    id=r["id"],
                    workflow_id=r["workflow_id"],
                    status=r["status"],
                    input_values=json.loads(r["input_values"]) if r["input_values"] else None,
                    started_at=r.get("started_at"),
                    completed_at=r.get("completed_at"),
                    error=r.get("error"),
                    steps=steps_by_run.get(r["id"], []),
                )
            )
        return result
    finally:
        conn.close()


@router.get("/{workflow_id}/runs/{run_id}", response_model=WorkflowRunResponse)
def get_run(workflow_id: str, run_id: str):
    conn = create_wf_read_conn()
    try:
        row = conn.execute(
            "SELECT * FROM workflow_runs WHERE id = ? AND workflow_id = ?",
            (run_id, workflow_id),
        ).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Run not found")

        step_rows = conn.execute(
            "SELECT * FROM workflow_run_steps WHERE run_id = ?", (run_id,)
        ).fetchall()

        return WorkflowRunResponse(
            id=row["id"],
            workflow_id=row["workflow_id"],
            status=row["status"],
            input_values=json.loads(row["input_values"]) if row["input_values"] else None,
            started_at=row["started_at"],
            completed_at=row["completed_at"],
            error=row["error"],
            steps=[
                WorkflowRunStepResponse(
                    id=s["id"],
                    step_id=s["step_id"],
                    status=s["status"],
                    session_id=s["session_id"],
                    prompt=s["prompt"],
                    output=s["output"],
                    started_at=s["started_at"],
                    completed_at=s["completed_at"],
                    error=s["error"],
                )
                for s in step_rows
            ],
        )
    finally:
        conn.close()
