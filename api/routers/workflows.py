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

from db.connection import create_read_connection, get_write_conn
from schemas import (
    WorkflowCreateRequest,
    WorkflowResponse,
    WorkflowRunRequest,
    WorkflowRunResponse,
    WorkflowRunStepResponse,
)
from services.workflow_engine import execute_workflow

logger = logging.getLogger(__name__)

router = APIRouter()

# Track active background workflow tasks so they aren't garbage-collected
_active_tasks: dict[str, asyncio.Task] = {}


@router.get("", response_model=list[WorkflowResponse])
def list_workflows():
    conn = create_read_connection()
    try:
        rows = conn.execute(
            "SELECT * FROM workflows ORDER BY updated_at DESC"
        ).fetchall()
        return [
            WorkflowResponse(
                id=r["id"],
                name=r["name"],
                description=r["description"],
                project_path=r["project_path"],
                graph=json.loads(r["graph"]),
                steps=json.loads(r["steps"]),
                inputs=json.loads(r["inputs"]) if r["inputs"] else [],
                created_at=r["created_at"],
                updated_at=r["updated_at"],
            )
            for r in rows
        ]
    finally:
        conn.close()


@router.post("", response_model=WorkflowResponse, status_code=201)
def create_workflow(req: WorkflowCreateRequest):
    wf_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()

    conn = get_write_conn()
    try:
        conn.execute(
            """INSERT INTO workflows (id, name, description, project_path, graph, steps, inputs, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                wf_id,
                req.name,
                req.description,
                req.project_path,
                json.dumps(req.graph),
                json.dumps([s.model_dump() for s in req.steps]),
                json.dumps([i.model_dump() for i in req.inputs]),
                now,
                now,
            ),
        )
        conn.commit()
    finally:
        conn.close()

    return WorkflowResponse(
        id=wf_id,
        name=req.name,
        description=req.description,
        project_path=req.project_path,
        graph=req.graph,
        steps=[s.model_dump() for s in req.steps],
        inputs=[i.model_dump() for i in req.inputs],
        created_at=now,
        updated_at=now,
    )


@router.get("/{workflow_id}", response_model=WorkflowResponse)
def get_workflow(workflow_id: str):
    conn = create_read_connection()
    try:
        row = conn.execute(
            "SELECT * FROM workflows WHERE id = ?", (workflow_id,)
        ).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Workflow not found")
        return WorkflowResponse(
            id=row["id"],
            name=row["name"],
            description=row["description"],
            project_path=row["project_path"],
            graph=json.loads(row["graph"]),
            steps=json.loads(row["steps"]),
            inputs=json.loads(row["inputs"]) if row["inputs"] else [],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )
    finally:
        conn.close()


@router.put("/{workflow_id}", response_model=WorkflowResponse)
def update_workflow(workflow_id: str, req: WorkflowCreateRequest):
    now = datetime.now(timezone.utc).isoformat()
    conn = get_write_conn()
    try:
        existing = conn.execute(
            "SELECT id, created_at FROM workflows WHERE id = ?", (workflow_id,)
        ).fetchone()
        if not existing:
            raise HTTPException(status_code=404, detail="Workflow not found")

        conn.execute(
            """UPDATE workflows SET name=?, description=?, project_path=?,
               graph=?, steps=?, inputs=?, updated_at=? WHERE id=?""",
            (
                req.name,
                req.description,
                req.project_path,
                json.dumps(req.graph),
                json.dumps([s.model_dump() for s in req.steps]),
                json.dumps([i.model_dump() for i in req.inputs]),
                now,
                workflow_id,
            ),
        )
        conn.commit()
    finally:
        conn.close()

    return WorkflowResponse(
        id=workflow_id,
        name=req.name,
        description=req.description,
        project_path=req.project_path,
        graph=req.graph,
        steps=[s.model_dump() for s in req.steps],
        inputs=[i.model_dump() for i in req.inputs],
        created_at=existing["created_at"],
        updated_at=now,
    )


@router.delete("/{workflow_id}", status_code=204)
def delete_workflow(workflow_id: str):
    conn = get_write_conn()
    try:
        result = conn.execute("DELETE FROM workflows WHERE id = ?", (workflow_id,))
        conn.commit()
        if result.rowcount == 0:
            raise HTTPException(status_code=404, detail="Workflow not found")
    finally:
        conn.close()


@router.post("/{workflow_id}/run", response_model=WorkflowRunResponse)
async def trigger_run(workflow_id: str, req: Optional[WorkflowRunRequest] = None):
    # Load workflow
    conn = create_read_connection()
    try:
        row = conn.execute(
            "SELECT * FROM workflows WHERE id = ?", (workflow_id,)
        ).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Workflow not found")
        steps = json.loads(row["steps"])
        graph = json.loads(row["graph"])
        edges = graph.get("edges", [])
        project_path = row["project_path"]
        workflow_name = row["name"]
    finally:
        conn.close()

    # Check concurrent run limit
    check_conn = create_read_connection()
    try:
        active_count = check_conn.execute(
            "SELECT COUNT(*) FROM workflow_runs WHERE workflow_id = ? AND status IN ('pending', 'running')",
            (workflow_id,),
        ).fetchone()[0]
        if active_count >= 3:
            raise HTTPException(status_code=429, detail="Maximum 3 concurrent runs per workflow")
    finally:
        check_conn.close()

    # Create run + step records
    run_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()
    input_values = req.input_values if req else None

    wconn = get_write_conn()
    step_responses = []
    try:
        wconn.execute(
            """INSERT INTO workflow_runs (id, workflow_id, status, input_values, started_at)
               VALUES (?, ?, 'pending', ?, ?)""",
            (run_id, workflow_id, json.dumps(input_values) if input_values else None, now),
        )
        for s in steps:
            step_id = str(uuid.uuid4())
            wconn.execute(
                """INSERT INTO workflow_run_steps (id, run_id, step_id, status)
                   VALUES (?, ?, ?, 'pending')""",
                (step_id, run_id, s["id"]),
            )
            step_responses.append(
                WorkflowRunStepResponse(id=step_id, step_id=s["id"], status="pending")
            )
        wconn.commit()
    finally:
        wconn.close()

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
            logger.error("Workflow run %s failed with unhandled error: %s", rid, t.exception())

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
    conn = create_read_connection()
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
    conn = create_read_connection()
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
