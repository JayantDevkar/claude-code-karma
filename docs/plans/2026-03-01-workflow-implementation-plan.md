# Workflow Feature Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add a visual workflow builder and execution engine to Claude Karma that lets users define multi-step Claude Code pipelines and run them from the dashboard.

**Architecture:** FastAPI backend stores workflow definitions in SQLite, executes steps as `claude -p` subprocesses, and exposes REST endpoints. SvelteKit frontend provides a Svelte Flow node editor for building workflows and a live execution view with status-colored nodes.

**Tech Stack:** FastAPI, SQLite, asyncio subprocess, Svelte 5, SvelteKit, @xyflow/svelte, @dagrejs/dagre, Tailwind CSS 4

**Design Doc:** `docs/plans/2026-03-01-workflow-feature-design.md`

---

## Task 1: Database Schema Migration (v8 → v9)

**Files:**
- Modify: `api/db/schema.py`
- Test: `api/tests/test_workflow_schema.py`

**Step 1: Write the failing test**

Create `api/tests/test_workflow_schema.py`:

```python
"""Tests for workflow schema migration v9."""
import sqlite3
import pytest
from db.schema import ensure_schema, SCHEMA_VERSION


def test_schema_version_is_9():
    assert SCHEMA_VERSION == 9


def test_workflows_table_exists(tmp_path):
    db_path = tmp_path / "test.db"
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    ensure_schema(conn)

    # Verify all three tables exist
    tables = {
        row[0]
        for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
    }
    assert "workflows" in tables
    assert "workflow_runs" in tables
    assert "workflow_run_steps" in tables
    conn.close()


def test_workflows_table_columns(tmp_path):
    db_path = tmp_path / "test.db"
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    ensure_schema(conn)

    cols = {row[1] for row in conn.execute("PRAGMA table_info(workflows)").fetchall()}
    assert cols == {
        "id", "name", "description", "project_path",
        "graph", "steps", "inputs",
        "created_at", "updated_at",
    }
    conn.close()


def test_workflow_runs_table_columns(tmp_path):
    db_path = tmp_path / "test.db"
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    ensure_schema(conn)

    cols = {row[1] for row in conn.execute("PRAGMA table_info(workflow_runs)").fetchall()}
    assert cols == {
        "id", "workflow_id", "status", "input_values",
        "started_at", "completed_at", "error",
    }
    conn.close()


def test_workflow_run_steps_table_columns(tmp_path):
    db_path = tmp_path / "test.db"
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    ensure_schema(conn)

    cols = {row[1] for row in conn.execute("PRAGMA table_info(workflow_run_steps)").fetchall()}
    assert cols == {
        "id", "run_id", "step_id", "status",
        "session_id", "prompt", "output",
        "started_at", "completed_at", "error",
    }
    conn.close()


def test_migration_from_v8(tmp_path):
    """Test incremental migration from v8 to v9."""
    db_path = tmp_path / "test.db"
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row

    # Simulate v8 state
    conn.execute("CREATE TABLE schema_version (version INTEGER PRIMARY KEY, applied_at TEXT)")
    conn.execute("INSERT INTO schema_version (version) VALUES (8)")
    conn.commit()

    # Run migration
    ensure_schema(conn)

    # Check version updated
    row = conn.execute("SELECT MAX(version) FROM schema_version").fetchone()
    assert row[0] == 9

    # Check tables created
    tables = {
        row[0]
        for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
    }
    assert "workflows" in tables
    assert "workflow_runs" in tables
    assert "workflow_run_steps" in tables
    conn.close()
```

**Step 2: Run test to verify it fails**

Run: `cd api && pytest tests/test_workflow_schema.py -v`
Expected: FAIL — `SCHEMA_VERSION == 8`, tables don't exist

**Step 3: Implement the migration**

In `api/db/schema.py`:

1. Change `SCHEMA_VERSION = 8` to `SCHEMA_VERSION = 9`

2. Add to `SCHEMA_SQL` string (before the closing `"""`):

```sql
-- Workflow definitions
CREATE TABLE IF NOT EXISTS workflows (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    description TEXT,
    project_path TEXT,
    graph JSON NOT NULL,
    steps JSON NOT NULL,
    inputs JSON,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_workflows_project ON workflows(project_path);

-- Workflow execution runs
CREATE TABLE IF NOT EXISTS workflow_runs (
    id TEXT PRIMARY KEY,
    workflow_id TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    input_values JSON,
    started_at TIMESTAMP,
    completed_at TIMESTAMP,
    error TEXT,
    FOREIGN KEY(workflow_id) REFERENCES workflows(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_workflow_runs_workflow ON workflow_runs(workflow_id);
CREATE INDEX IF NOT EXISTS idx_workflow_runs_status ON workflow_runs(status);

-- Individual step execution within a run
CREATE TABLE IF NOT EXISTS workflow_run_steps (
    id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL,
    step_id TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    session_id TEXT,
    prompt TEXT,
    output TEXT,
    started_at TIMESTAMP,
    completed_at TIMESTAMP,
    error TEXT,
    FOREIGN KEY(run_id) REFERENCES workflow_runs(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_run_steps_run ON workflow_run_steps(run_id);
CREATE INDEX IF NOT EXISTS idx_run_steps_session ON workflow_run_steps(session_id);
```

3. Add incremental migration block after the `if current_version < 8:` block:

```python
if current_version < 9:
    logger.info("Migrating v8 → v9: adding workflow tables")
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS workflows (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            description TEXT,
            project_path TEXT,
            graph JSON NOT NULL,
            steps JSON NOT NULL,
            inputs JSON,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        CREATE INDEX IF NOT EXISTS idx_workflows_project ON workflows(project_path);

        CREATE TABLE IF NOT EXISTS workflow_runs (
            id TEXT PRIMARY KEY,
            workflow_id TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'pending',
            input_values JSON,
            started_at TIMESTAMP,
            completed_at TIMESTAMP,
            error TEXT,
            FOREIGN KEY(workflow_id) REFERENCES workflows(id) ON DELETE CASCADE
        );
        CREATE INDEX IF NOT EXISTS idx_workflow_runs_workflow ON workflow_runs(workflow_id);
        CREATE INDEX IF NOT EXISTS idx_workflow_runs_status ON workflow_runs(status);

        CREATE TABLE IF NOT EXISTS workflow_run_steps (
            id TEXT PRIMARY KEY,
            run_id TEXT NOT NULL,
            step_id TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'pending',
            session_id TEXT,
            prompt TEXT,
            output TEXT,
            started_at TIMESTAMP,
            completed_at TIMESTAMP,
            error TEXT,
            FOREIGN KEY(run_id) REFERENCES workflow_runs(id) ON DELETE CASCADE
        );
        CREATE INDEX IF NOT EXISTS idx_run_steps_run ON workflow_run_steps(run_id);
        CREATE INDEX IF NOT EXISTS idx_run_steps_session ON workflow_run_steps(session_id);
    """)
```

**Step 4: Run test to verify it passes**

Run: `cd api && pytest tests/test_workflow_schema.py -v`
Expected: All 5 tests PASS

**Step 5: Commit**

```bash
git add api/db/schema.py api/tests/test_workflow_schema.py
git commit -m "feat(db): add workflow tables (schema v9)"
```

---

## Task 2: Workflow Pydantic Schemas

**Files:**
- Create: `api/models/workflow.py`
- Modify: `api/schemas.py` (add response schemas)

**Step 1: Write the failing test**

Create `api/tests/test_workflow_models.py`:

```python
"""Tests for workflow Pydantic models."""
import pytest
from models.workflow import WorkflowStep, WorkflowInput, WorkflowDefinition


def test_workflow_step_defaults():
    step = WorkflowStep(id="test", prompt_template="Do something")
    assert step.model == "sonnet"
    assert step.tools == ["Read", "Edit", "Bash"]
    assert step.max_turns == 10
    assert step.condition is None


def test_workflow_input_required():
    inp = WorkflowInput(name="feature", type="string", required=True)
    assert inp.default is None
    assert inp.description is None


def test_workflow_definition_minimal():
    wf = WorkflowDefinition(
        name="test-flow",
        graph={"nodes": [], "edges": []},
        steps=[WorkflowStep(id="s1", prompt_template="hello")],
    )
    assert wf.id is not None  # auto-generated UUID
    assert wf.description is None
    assert wf.inputs == []


def test_workflow_step_with_condition():
    step = WorkflowStep(
        id="fix",
        prompt_template="Fix: {{ steps.review.output }}",
        model="opus",
        condition="{{ steps.review.has_issues }}",
    )
    assert step.condition == "{{ steps.review.has_issues }}"
    assert step.model == "opus"
```

**Step 2: Run test to verify it fails**

Run: `cd api && pytest tests/test_workflow_models.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'models.workflow'`

**Step 3: Implement the models**

Create `api/models/workflow.py`:

```python
"""Pydantic models for workflow definitions and execution."""

import uuid
from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field


class WorkflowStep(BaseModel):
    """A single step in a workflow pipeline."""

    model_config = ConfigDict(frozen=True)

    id: str
    prompt_template: str
    model: str = "sonnet"
    tools: list[str] = Field(default_factory=lambda: ["Read", "Edit", "Bash"])
    max_turns: int = 10
    condition: Optional[str] = None


class WorkflowInput(BaseModel):
    """An input parameter for a workflow."""

    model_config = ConfigDict(frozen=True)

    name: str
    type: str = "string"
    required: bool = True
    default: Optional[str] = None
    description: Optional[str] = None


class WorkflowDefinition(BaseModel):
    """A complete workflow definition."""

    model_config = ConfigDict(frozen=True)

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    name: str
    description: Optional[str] = None
    project_path: Optional[str] = None
    graph: dict[str, Any]  # Svelte Flow {nodes, edges}
    steps: list[WorkflowStep]
    inputs: list[WorkflowInput] = Field(default_factory=list)
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class WorkflowRunStep(BaseModel):
    """Execution state of a single step within a run."""

    model_config = ConfigDict(frozen=True)

    id: str
    run_id: str
    step_id: str
    status: str = "pending"  # pending | running | completed | failed | skipped
    session_id: Optional[str] = None
    prompt: Optional[str] = None
    output: Optional[str] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    error: Optional[str] = None


class WorkflowRun(BaseModel):
    """Execution state of a workflow run."""

    model_config = ConfigDict(frozen=True)

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    workflow_id: str
    status: str = "pending"  # pending | running | completed | failed
    input_values: Optional[dict[str, Any]] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    error: Optional[str] = None
    steps: list[WorkflowRunStep] = Field(default_factory=list)
```

**Step 4: Run test to verify it passes**

Run: `cd api && pytest tests/test_workflow_models.py -v`
Expected: All 4 tests PASS

**Step 5: Add response schemas to `api/schemas.py`**

Add at the end of `api/schemas.py`:

```python
# --- Workflow schemas ---

class WorkflowStepSchema(BaseModel):
    id: str
    prompt_template: str
    model: str = "sonnet"
    tools: list[str] = []
    max_turns: int = 10
    condition: Optional[str] = None

class WorkflowInputSchema(BaseModel):
    name: str
    type: str = "string"
    required: bool = True
    default: Optional[str] = None
    description: Optional[str] = None

class WorkflowCreateRequest(BaseModel):
    name: str
    description: Optional[str] = None
    project_path: Optional[str] = None
    graph: dict
    steps: list[WorkflowStepSchema]
    inputs: list[WorkflowInputSchema] = []

class WorkflowResponse(BaseModel):
    id: str
    name: str
    description: Optional[str] = None
    project_path: Optional[str] = None
    graph: dict
    steps: list[WorkflowStepSchema]
    inputs: list[WorkflowInputSchema] = []
    created_at: Optional[str] = None
    updated_at: Optional[str] = None

class WorkflowRunStepResponse(BaseModel):
    id: str
    step_id: str
    status: str
    session_id: Optional[str] = None
    prompt: Optional[str] = None
    output: Optional[str] = None
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    error: Optional[str] = None

class WorkflowRunResponse(BaseModel):
    id: str
    workflow_id: str
    status: str
    input_values: Optional[dict] = None
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    error: Optional[str] = None
    steps: list[WorkflowRunStepResponse] = []

class WorkflowRunRequest(BaseModel):
    input_values: Optional[dict] = None
```

**Step 6: Commit**

```bash
git add api/models/workflow.py api/schemas.py api/tests/test_workflow_models.py
git commit -m "feat(models): add workflow Pydantic models and response schemas"
```

---

## Task 3: Workflow Execution Engine

**Files:**
- Create: `api/services/workflow_engine.py`
- Test: `api/tests/test_workflow_engine.py`

**Step 1: Write the failing test**

Create `api/tests/test_workflow_engine.py`:

```python
"""Tests for workflow execution engine."""
import pytest
from services.workflow_engine import resolve_template, topological_sort


def test_resolve_template_simple():
    ctx = {"inputs": {"feature": "auth module"}}
    result = resolve_template("Test {{ inputs.feature }}", ctx)
    assert result == "Test auth module"


def test_resolve_template_step_output():
    ctx = {
        "steps": {"extract": {"output": "found 3 files", "session_id": "abc"}},
        "inputs": {},
    }
    result = resolve_template(
        "Review: {{ steps.extract.output }}", ctx
    )
    assert result == "Review: found 3 files"


def test_resolve_template_missing_var():
    ctx = {"inputs": {}, "steps": {}}
    result = resolve_template("Test {{ inputs.missing }}", ctx)
    assert result == "Test "


def test_topological_sort_linear():
    edges = [
        {"source": "a", "target": "b"},
        {"source": "b", "target": "c"},
    ]
    step_ids = ["a", "b", "c"]
    result = topological_sort(step_ids, edges)
    assert result == ["a", "b", "c"]


def test_topological_sort_fan_out():
    edges = [
        {"source": "a", "target": "b"},
        {"source": "a", "target": "c"},
    ]
    step_ids = ["a", "b", "c"]
    result = topological_sort(step_ids, edges)
    assert result[0] == "a"
    assert set(result[1:]) == {"b", "c"}


def test_topological_sort_fan_in():
    edges = [
        {"source": "a", "target": "c"},
        {"source": "b", "target": "c"},
    ]
    step_ids = ["a", "b", "c"]
    result = topological_sort(step_ids, edges)
    assert result[-1] == "c"
    assert set(result[:2]) == {"a", "b"}


def test_evaluate_condition_true():
    from services.workflow_engine import evaluate_condition

    ctx = {"steps": {"review": {"output": "found issues", "has_issues": "true"}}}
    assert evaluate_condition("{{ steps.review.has_issues }} == true", ctx) is True


def test_evaluate_condition_false():
    from services.workflow_engine import evaluate_condition

    ctx = {"steps": {"review": {"output": "all good", "has_issues": "false"}}}
    assert evaluate_condition("{{ steps.review.has_issues }} == true", ctx) is False


def test_evaluate_condition_none():
    from services.workflow_engine import evaluate_condition

    assert evaluate_condition(None, {}) is True  # No condition = always run
```

**Step 2: Run test to verify it fails**

Run: `cd api && pytest tests/test_workflow_engine.py -v`
Expected: FAIL — `ModuleNotFoundError`

**Step 3: Implement the engine**

Create `api/services/workflow_engine.py`:

```python
"""
Workflow execution engine.

Orchestrates multi-step Claude Code workflows by:
1. Topologically sorting steps based on graph edges
2. Resolving prompt templates with step outputs
3. Spawning `claude -p` subprocesses for each step
4. Tracking execution state in SQLite
"""

import asyncio
import json
import logging
import re
import sqlite3
import uuid
from collections import defaultdict, deque
from datetime import datetime, timezone
from typing import Any, Optional

logger = logging.getLogger(__name__)

# Template variable pattern: {{ inputs.name }} or {{ steps.id.field }}
TEMPLATE_PATTERN = re.compile(r"\{\{\s*([\w.]+)\s*\}\}")


def resolve_template(template: str, context: dict[str, Any]) -> str:
    """
    Replace {{ var.path }} placeholders with values from context.

    Context structure:
        {
            "inputs": {"feature": "auth"},
            "steps": {"extract": {"output": "...", "session_id": "..."}},
            "workflow": {"name": "...", "project_path": "..."},
            "run": {"id": "..."},
        }
    """

    def replacer(match: re.Match) -> str:
        path = match.group(1)
        parts = path.split(".")
        obj: Any = context
        for part in parts:
            if isinstance(obj, dict):
                obj = obj.get(part, "")
            else:
                return ""
            if obj is None:
                return ""
        return str(obj) if obj != "" else ""

    return TEMPLATE_PATTERN.sub(replacer, template)


def topological_sort(step_ids: list[str], edges: list[dict]) -> list[str]:
    """
    Topologically sort step IDs based on edges.

    Each edge is {"source": "step_a", "target": "step_b"} meaning
    step_a must run before step_b.

    Returns ordered list of step IDs.
    """
    in_degree: dict[str, int] = {sid: 0 for sid in step_ids}
    adjacency: dict[str, list[str]] = defaultdict(list)

    for edge in edges:
        src = edge.get("source", "")
        tgt = edge.get("target", "")
        if src in in_degree and tgt in in_degree:
            adjacency[src].append(tgt)
            in_degree[tgt] += 1

    queue = deque(sid for sid in step_ids if in_degree[sid] == 0)
    result: list[str] = []

    while queue:
        node = queue.popleft()
        result.append(node)
        for neighbor in adjacency[node]:
            in_degree[neighbor] -= 1
            if in_degree[neighbor] == 0:
                queue.append(neighbor)

    return result


def evaluate_condition(condition: Optional[str], context: dict[str, Any]) -> bool:
    """
    Evaluate a simple condition string.

    Supports: "{{ var }} == value" and "{{ var }} != value"
    Returns True if condition is None (no condition = always run).
    """
    if condition is None:
        return True

    # Resolve template variables first
    resolved = resolve_template(condition, context)

    # Simple equality/inequality check
    if "!=" in resolved:
        left, right = resolved.split("!=", 1)
        return left.strip() != right.strip()
    elif "==" in resolved:
        left, right = resolved.split("==", 1)
        return left.strip() == right.strip()

    # If just a value, treat truthy
    val = resolved.strip().lower()
    return val not in ("", "false", "none", "0", "null")


async def run_claude_step(
    prompt: str,
    *,
    model: str = "sonnet",
    tools: list[str] | None = None,
    max_turns: int = 10,
    cwd: str | None = None,
) -> dict[str, Any]:
    """
    Run a single Claude Code step via `claude -p` subprocess.

    Returns dict with:
        - result: str (Claude's response)
        - session_id: str (session UUID from JSON output)
        - exit_code: int
    """
    cmd = [
        "claude",
        "-p",
        prompt,
        "--output-format",
        "json",
        "--model",
        model,
        "--max-turns",
        str(max_turns),
    ]

    if tools:
        cmd.extend(["--allowedTools", ",".join(tools)])

    logger.info("Running claude step: model=%s, cwd=%s", model, cwd)

    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        cwd=cwd,
    )

    stdout, stderr = await proc.communicate()
    exit_code = proc.returncode or 0

    result_text = ""
    session_id = None

    if stdout:
        try:
            data = json.loads(stdout.decode())
            result_text = data.get("result", "")
            session_id = data.get("session_id", None)
        except json.JSONDecodeError:
            result_text = stdout.decode()

    if exit_code != 0 and stderr:
        logger.warning("Claude step stderr: %s", stderr.decode()[:500])

    return {
        "result": result_text,
        "session_id": session_id,
        "exit_code": exit_code,
    }


def _get_write_conn() -> sqlite3.Connection:
    """Get a write connection for workflow state updates."""
    from db.connection import get_db_path

    db_path = get_db_path()
    conn = sqlite3.connect(str(db_path), timeout=10.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA busy_timeout=5000")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def _update_step_status(
    run_id: str,
    step_id: str,
    status: str,
    *,
    session_id: str | None = None,
    prompt: str | None = None,
    output: str | None = None,
    error: str | None = None,
) -> None:
    """Update a workflow run step's status in SQLite."""
    conn = _get_write_conn()
    try:
        now = datetime.now(timezone.utc).isoformat()
        if status == "running":
            conn.execute(
                "UPDATE workflow_run_steps SET status=?, started_at=?, prompt=? WHERE run_id=? AND step_id=?",
                (status, now, prompt, run_id, step_id),
            )
        elif status in ("completed", "failed", "skipped"):
            conn.execute(
                "UPDATE workflow_run_steps SET status=?, completed_at=?, session_id=?, output=?, error=? WHERE run_id=? AND step_id=?",
                (status, now, session_id, output, error, run_id, step_id),
            )
        conn.commit()
    finally:
        conn.close()


def _update_run_status(run_id: str, status: str, error: str | None = None) -> None:
    """Update a workflow run's status in SQLite."""
    conn = _get_write_conn()
    try:
        now = datetime.now(timezone.utc).isoformat()
        if status == "running":
            conn.execute(
                "UPDATE workflow_runs SET status=?, started_at=? WHERE id=?",
                (status, now, run_id),
            )
        else:
            conn.execute(
                "UPDATE workflow_runs SET status=?, completed_at=?, error=? WHERE id=?",
                (status, now, error, run_id),
            )
        conn.commit()
    finally:
        conn.close()


async def execute_workflow(
    run_id: str,
    workflow_id: str,
    steps: list[dict],
    edges: list[dict],
    input_values: dict[str, Any],
    project_path: str | None = None,
    workflow_name: str = "",
) -> None:
    """
    Execute a full workflow run.

    Called as an asyncio background task from the API endpoint.
    Updates SQLite with step-by-step progress.
    """
    _update_run_status(run_id, "running")

    # Build step lookup
    step_map = {s["id"]: s for s in steps}
    step_ids = [s["id"] for s in steps]
    ordered = topological_sort(step_ids, edges)

    # Execution context for template resolution
    context: dict[str, Any] = {
        "inputs": input_values or {},
        "steps": {},
        "workflow": {"name": workflow_name, "project_path": project_path or ""},
        "run": {"id": run_id},
    }

    try:
        for step_id in ordered:
            step_def = step_map.get(step_id)
            if not step_def:
                continue

            # Check condition
            if not evaluate_condition(step_def.get("condition"), context):
                _update_step_status(run_id, step_id, "skipped")
                context["steps"][step_id] = {"output": "", "session_id": ""}
                continue

            # Resolve prompt template
            prompt = resolve_template(step_def["prompt_template"], context)
            _update_step_status(run_id, step_id, "running", prompt=prompt)

            # Execute
            result = await run_claude_step(
                prompt,
                model=step_def.get("model", "sonnet"),
                tools=step_def.get("tools"),
                max_turns=step_def.get("max_turns", 10),
                cwd=project_path,
            )

            if result["exit_code"] != 0:
                _update_step_status(
                    run_id,
                    step_id,
                    "failed",
                    session_id=result.get("session_id"),
                    output=result.get("result"),
                    error=f"Exit code {result['exit_code']}",
                )
                _update_run_status(
                    run_id, "failed", f"Step '{step_id}' failed with exit code {result['exit_code']}"
                )
                return

            # Success
            _update_step_status(
                run_id,
                step_id,
                "completed",
                session_id=result.get("session_id"),
                output=result.get("result"),
            )

            # Update context for downstream steps
            context["steps"][step_id] = {
                "output": result.get("result", ""),
                "session_id": result.get("session_id", ""),
            }

        _update_run_status(run_id, "completed")

    except Exception as e:
        logger.exception("Workflow run %s failed", run_id)
        _update_run_status(run_id, "failed", str(e))
```

**Step 4: Run test to verify it passes**

Run: `cd api && pytest tests/test_workflow_engine.py -v`
Expected: All 9 tests PASS

**Step 5: Commit**

```bash
git add api/services/workflow_engine.py api/tests/test_workflow_engine.py
git commit -m "feat(engine): add workflow execution engine with template resolution"
```

---

## Task 4: Workflow API Router

**Files:**
- Create: `api/routers/workflows.py`
- Modify: `api/main.py` (register router)
- Test: `api/tests/api/test_workflow_endpoints.py`

**Step 1: Write the failing test**

Create `api/tests/api/test_workflow_endpoints.py`:

```python
"""Tests for workflow API endpoints."""
import json
import pytest
from fastapi.testclient import TestClient


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
```

**Step 2: Run test to verify it fails**

Run: `cd api && pytest tests/api/test_workflow_endpoints.py -v`
Expected: FAIL — no `/workflows` route

**Step 3: Implement the router**

Create `api/routers/workflows.py`:

```python
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
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, HTTPException

from db.connection import create_read_connection
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


def _get_write_conn():
    from db.connection import get_db_path
    import sqlite3

    db_path = get_db_path()
    conn = sqlite3.connect(str(db_path), timeout=10.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA busy_timeout=5000")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


@router.get("/workflows", response_model=list[WorkflowResponse])
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


@router.post("/workflows", response_model=WorkflowResponse, status_code=201)
def create_workflow(req: WorkflowCreateRequest):
    wf_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()

    conn = _get_write_conn()
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


@router.get("/workflows/{workflow_id}", response_model=WorkflowResponse)
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


@router.put("/workflows/{workflow_id}", response_model=WorkflowResponse)
def update_workflow(workflow_id: str, req: WorkflowCreateRequest):
    now = datetime.now(timezone.utc).isoformat()
    conn = _get_write_conn()
    try:
        existing = conn.execute(
            "SELECT id FROM workflows WHERE id = ?", (workflow_id,)
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
        updated_at=now,
    )


@router.delete("/workflows/{workflow_id}", status_code=204)
def delete_workflow(workflow_id: str):
    conn = _get_write_conn()
    try:
        result = conn.execute("DELETE FROM workflows WHERE id = ?", (workflow_id,))
        conn.commit()
        if result.rowcount == 0:
            raise HTTPException(status_code=404, detail="Workflow not found")
    finally:
        conn.close()


@router.post("/workflows/{workflow_id}/run", response_model=WorkflowRunResponse)
async def trigger_run(workflow_id: str, req: WorkflowRunRequest = None):
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

    # Create run + step records
    run_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()
    input_values = req.input_values if req else None

    wconn = _get_write_conn()
    try:
        wconn.execute(
            """INSERT INTO workflow_runs (id, workflow_id, status, input_values, started_at)
               VALUES (?, ?, 'pending', ?, ?)""",
            (run_id, workflow_id, json.dumps(input_values) if input_values else None, now),
        )
        for step in steps:
            wconn.execute(
                """INSERT INTO workflow_run_steps (id, run_id, step_id, status)
                   VALUES (?, ?, ?, 'pending')""",
                (str(uuid.uuid4()), run_id, step["id"]),
            )
        wconn.commit()
    finally:
        wconn.close()

    # Launch background execution
    asyncio.create_task(
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

    return WorkflowRunResponse(
        id=run_id,
        workflow_id=workflow_id,
        status="pending",
        input_values=input_values,
        started_at=now,
        steps=[
            WorkflowRunStepResponse(id="", step_id=s["id"], status="pending")
            for s in steps
        ],
    )


@router.get("/workflows/{workflow_id}/runs", response_model=list[WorkflowRunResponse])
def list_runs(workflow_id: str):
    conn = create_read_connection()
    try:
        rows = conn.execute(
            "SELECT * FROM workflow_runs WHERE workflow_id = ? ORDER BY started_at DESC",
            (workflow_id,),
        ).fetchall()
        result = []
        for r in rows:
            step_rows = conn.execute(
                "SELECT * FROM workflow_run_steps WHERE run_id = ?", (r["id"],)
            ).fetchall()
            result.append(
                WorkflowRunResponse(
                    id=r["id"],
                    workflow_id=r["workflow_id"],
                    status=r["status"],
                    input_values=json.loads(r["input_values"]) if r["input_values"] else None,
                    started_at=r["started_at"],
                    completed_at=r["completed_at"],
                    error=r["error"],
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
            )
        return result
    finally:
        conn.close()


@router.get("/workflows/{workflow_id}/runs/{run_id}", response_model=WorkflowRunResponse)
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
```

**Step 4: Register router in `api/main.py`**

Add import:
```python
from routers import (
    ...
    workflows,
)
```

Add include:
```python
app.include_router(workflows.router, prefix="/workflows", tags=["workflows"])
```

**Step 5: Run test to verify it passes**

Run: `cd api && pytest tests/api/test_workflow_endpoints.py -v`
Expected: All 7 tests PASS

**Step 6: Commit**

```bash
git add api/routers/workflows.py api/main.py api/tests/api/test_workflow_endpoints.py
git commit -m "feat(api): add workflow CRUD and execution endpoints"
```

---

## Task 5: Install Frontend Dependencies

**Files:**
- Modify: `frontend/package.json`

**Step 1: Install Svelte Flow and Dagre**

```bash
cd frontend && npm install @xyflow/svelte @dagrejs/dagre
```

**Step 2: Install type definitions for Dagre**

```bash
cd frontend && npm install -D @types/dagre
```

**Step 3: Verify install**

```bash
cd frontend && npm run check
```
Expected: No new type errors

**Step 4: Commit**

```bash
git add frontend/package.json frontend/package-lock.json
git commit -m "chore(frontend): add @xyflow/svelte and @dagrejs/dagre"
```

---

## Task 6: Frontend API Types

**Files:**
- Modify: `frontend/src/lib/api-types.ts`

**Step 1: Add workflow TypeScript interfaces**

Add to `frontend/src/lib/api-types.ts`:

```typescript
// --- Workflow types ---

export interface WorkflowStep {
	id: string;
	prompt_template: string;
	model: string;
	tools: string[];
	max_turns: number;
	condition: string | null;
}

export interface WorkflowInput {
	name: string;
	type: string;
	required: boolean;
	default: string | null;
	description: string | null;
}

export interface Workflow {
	id: string;
	name: string;
	description: string | null;
	project_path: string | null;
	graph: { nodes: any[]; edges: any[] };
	steps: WorkflowStep[];
	inputs: WorkflowInput[];
	created_at: string | null;
	updated_at: string | null;
}

export interface WorkflowRunStep {
	id: string;
	step_id: string;
	status: 'pending' | 'running' | 'completed' | 'failed' | 'skipped';
	session_id: string | null;
	prompt: string | null;
	output: string | null;
	started_at: string | null;
	completed_at: string | null;
	error: string | null;
}

export interface WorkflowRun {
	id: string;
	workflow_id: string;
	status: 'pending' | 'running' | 'completed' | 'failed';
	input_values: Record<string, any> | null;
	started_at: string | null;
	completed_at: string | null;
	error: string | null;
	steps: WorkflowRunStep[];
}
```

**Step 2: Run type check**

```bash
cd frontend && npm run check
```
Expected: PASS (types only, no consumers yet)

**Step 3: Commit**

```bash
git add frontend/src/lib/api-types.ts
git commit -m "feat(frontend): add workflow TypeScript types"
```

---

## Task 7: Workflow List Page

**Files:**
- Create: `frontend/src/routes/workflows/+page.server.ts`
- Create: `frontend/src/routes/workflows/+page.svelte`

**Step 1: Create the server load function**

Create `frontend/src/routes/workflows/+page.server.ts`:

```typescript
import type { Workflow } from '$lib/api-types';
import { API_BASE } from '$lib/config';
import { fetchWithFallback } from '$lib/utils/api-fetch';

export async function load({ fetch }) {
	const workflows = await fetchWithFallback<Workflow[]>(fetch, `${API_BASE}/workflows`, []);
	return { workflows };
}
```

**Step 2: Create the list page**

Create `frontend/src/routes/workflows/+page.svelte`:

```svelte
<script lang="ts">
	import type { Workflow } from '$lib/api-types';
	import PageHeader from '$lib/components/layout/PageHeader.svelte';

	let { data } = $props();
	let workflows: Workflow[] = $derived(data.workflows);
</script>

<PageHeader title="Workflows" description="Automated Claude Code pipelines" />

<div class="container mx-auto px-4 py-6">
	<div class="flex justify-between items-center mb-6">
		<p class="text-[var(--text-secondary)]">{workflows.length} workflow{workflows.length !== 1 ? 's' : ''}</p>
		<a
			href="/workflows/new"
			class="px-4 py-2 bg-[var(--accent)] text-white rounded-lg hover:opacity-90 transition-opacity"
		>
			+ New Workflow
		</a>
	</div>

	{#if workflows.length === 0}
		<div class="text-center py-16 text-[var(--text-muted)]">
			<p class="text-lg mb-2">No workflows yet</p>
			<p>Create your first automated pipeline</p>
		</div>
	{:else}
		<div class="grid gap-4 grid-cols-1 md:grid-cols-2 lg:grid-cols-3">
			{#each workflows as wf}
				<a
					href="/workflows/{wf.id}"
					class="block p-4 rounded-xl border border-[var(--border)] bg-[var(--bg-subtle)] hover:border-[var(--accent)] transition-colors"
				>
					<h3 class="font-semibold text-[var(--text-primary)] mb-1">{wf.name}</h3>
					{#if wf.description}
						<p class="text-sm text-[var(--text-secondary)] mb-3">{wf.description}</p>
					{/if}
					<div class="flex items-center gap-3 text-xs text-[var(--text-muted)]">
						<span>{wf.steps.length} step{wf.steps.length !== 1 ? 's' : ''}</span>
						{#if wf.inputs.length > 0}
							<span>{wf.inputs.length} input{wf.inputs.length !== 1 ? 's' : ''}</span>
						{/if}
					</div>
				</a>
			{/each}
		</div>
	{/if}
</div>
```

**Step 3: Run type check**

```bash
cd frontend && npm run check
```
Expected: PASS

**Step 4: Commit**

```bash
git add frontend/src/routes/workflows/
git commit -m "feat(frontend): add workflow list page"
```

---

## Task 8: Svelte Flow Workflow Editor Component

**Files:**
- Create: `frontend/src/lib/components/workflows/WorkflowEditor.svelte`
- Create: `frontend/src/lib/components/workflows/StepNode.svelte`
- Create: `frontend/src/lib/components/workflows/StepConfigPanel.svelte`
- Create: `frontend/src/lib/components/workflows/dagre-layout.ts`

This is the largest task. Build the visual node editor with:
- Custom step nodes (name + model badge)
- Dagre auto-layout
- Config panel for editing step properties
- Save/Run actions

**Step 1: Create Dagre layout utility**

Create `frontend/src/lib/components/workflows/dagre-layout.ts`:

```typescript
import dagre from '@dagrejs/dagre';
import type { Node, Edge } from '@xyflow/svelte';

export function getLayoutedElements(
	nodes: Node[],
	edges: Edge[],
	direction: 'TB' | 'LR' = 'TB'
): { nodes: Node[]; edges: Edge[] } {
	const g = new dagre.graphlib.Graph();
	g.setDefaultEdgeLabel(() => ({}));
	g.setGraph({ rankdir: direction, nodesep: 50, ranksep: 80 });

	nodes.forEach((node) => {
		g.setNode(node.id, { width: 200, height: 60 });
	});

	edges.forEach((edge) => {
		g.setEdge(edge.source, edge.target);
	});

	dagre.layout(g);

	return {
		nodes: nodes.map((node) => {
			const pos = g.node(node.id);
			return {
				...node,
				position: { x: pos.x - 100, y: pos.y - 30 }
			};
		}),
		edges
	};
}
```

**Step 2: Create custom StepNode component**

Create `frontend/src/lib/components/workflows/StepNode.svelte`:

```svelte
<script lang="ts">
	import { Handle, Position } from '@xyflow/svelte';

	let { data, id } = $props();

	const modelColors: Record<string, string> = {
		sonnet: '#8b5cf6',
		opus: '#f59e0b',
		haiku: '#10b981'
	};

	let bgColor = $derived(modelColors[data?.model || 'sonnet'] || '#8b5cf6');
</script>

<Handle type="target" position={Position.Top} />

<div
	class="px-4 py-3 rounded-lg border border-[var(--border)] bg-[var(--bg-subtle)] min-w-[180px] cursor-pointer hover:border-[var(--accent)] transition-colors"
>
	<div class="flex items-center justify-between gap-2">
		<span class="font-medium text-sm text-[var(--text-primary)] truncate">{data?.label || id}</span>
		<span
			class="text-[10px] px-1.5 py-0.5 rounded-full text-white font-medium"
			style="background-color: {bgColor}"
		>
			{data?.model || 'sonnet'}
		</span>
	</div>
</div>

<Handle type="source" position={Position.Bottom} />
```

**Step 3: Create StepConfigPanel component**

Create `frontend/src/lib/components/workflows/StepConfigPanel.svelte`:

```svelte
<script lang="ts">
	import type { WorkflowStep } from '$lib/api-types';

	let {
		step = $bindable(),
		ondelete
	}: {
		step: WorkflowStep;
		ondelete: () => void;
	} = $props();

	const availableTools = ['Read', 'Edit', 'Write', 'Bash', 'Glob', 'Grep', 'WebFetch', 'WebSearch'];

	function toggleTool(tool: string) {
		if (step.tools.includes(tool)) {
			step = { ...step, tools: step.tools.filter((t) => t !== tool) };
		} else {
			step = { ...step, tools: [...step.tools, tool] };
		}
	}
</script>

<div class="p-4 border-l border-[var(--border)] bg-[var(--bg-subtle)] w-80 overflow-y-auto">
	<div class="flex justify-between items-center mb-4">
		<h3 class="font-semibold text-[var(--text-primary)]">Step Config</h3>
		<button onclick={ondelete} class="text-xs text-red-500 hover:text-red-400">Delete</button>
	</div>

	<label class="block mb-3">
		<span class="text-xs text-[var(--text-muted)] mb-1 block">Name</span>
		<input
			type="text"
			bind:value={step.id}
			class="w-full px-3 py-1.5 rounded border border-[var(--border)] bg-[var(--bg-base)] text-sm text-[var(--text-primary)]"
		/>
	</label>

	<label class="block mb-3">
		<span class="text-xs text-[var(--text-muted)] mb-1 block">Model</span>
		<select
			bind:value={step.model}
			class="w-full px-3 py-1.5 rounded border border-[var(--border)] bg-[var(--bg-base)] text-sm text-[var(--text-primary)]"
		>
			<option value="haiku">haiku</option>
			<option value="sonnet">sonnet</option>
			<option value="opus">opus</option>
		</select>
	</label>

	<label class="block mb-3">
		<span class="text-xs text-[var(--text-muted)] mb-1 block">Prompt Template</span>
		<textarea
			bind:value={step.prompt_template}
			rows="6"
			class="w-full px-3 py-1.5 rounded border border-[var(--border)] bg-[var(--bg-base)] text-sm text-[var(--text-primary)] font-mono"
			placeholder="Use {{ inputs.name }} or {{ steps.prev.output }}"
		></textarea>
	</label>

	<label class="block mb-3">
		<span class="text-xs text-[var(--text-muted)] mb-1 block">Max Turns</span>
		<input
			type="number"
			bind:value={step.max_turns}
			min="1"
			max="100"
			class="w-full px-3 py-1.5 rounded border border-[var(--border)] bg-[var(--bg-base)] text-sm text-[var(--text-primary)]"
		/>
	</label>

	<label class="block mb-3">
		<span class="text-xs text-[var(--text-muted)] mb-1 block">Condition (optional)</span>
		<input
			type="text"
			bind:value={step.condition}
			placeholder="{{ steps.review.has_issues }} == true"
			class="w-full px-3 py-1.5 rounded border border-[var(--border)] bg-[var(--bg-base)] text-sm text-[var(--text-primary)] font-mono"
		/>
	</label>

	<div class="mb-3">
		<span class="text-xs text-[var(--text-muted)] mb-2 block">Tools</span>
		<div class="flex flex-wrap gap-1.5">
			{#each availableTools as tool}
				<button
					onclick={() => toggleTool(tool)}
					class="text-xs px-2 py-1 rounded border transition-colors {step.tools.includes(tool)
						? 'bg-[var(--accent)] text-white border-[var(--accent)]'
						: 'border-[var(--border)] text-[var(--text-secondary)] hover:border-[var(--accent)]'}"
				>
					{tool}
				</button>
			{/each}
		</div>
	</div>
</div>
```

**Step 4: Create the main WorkflowEditor component**

Create `frontend/src/lib/components/workflows/WorkflowEditor.svelte`:

```svelte
<script lang="ts">
	import { SvelteFlow, Controls, Background, type Node, type Edge } from '@xyflow/svelte';
	import '@xyflow/svelte/dist/style.css';
	import type { WorkflowStep, WorkflowInput } from '$lib/api-types';
	import StepNode from './StepNode.svelte';
	import StepConfigPanel from './StepConfigPanel.svelte';
	import { getLayoutedElements } from './dagre-layout';

	let {
		initialNodes = [],
		initialEdges = [],
		initialSteps = [],
		initialInputs = [],
		workflowName = $bindable(''),
		workflowDescription = $bindable(''),
		onsave,
		onrun
	}: {
		initialNodes?: Node[];
		initialEdges?: Edge[];
		initialSteps?: WorkflowStep[];
		initialInputs?: WorkflowInput[];
		workflowName?: string;
		workflowDescription?: string;
		onsave: (data: { nodes: Node[]; edges: Edge[]; steps: WorkflowStep[]; inputs: WorkflowInput[] }) => void;
		onrun: () => void;
	} = $props();

	let nodes = $state<Node[]>(initialNodes);
	let edges = $state<Edge[]>(initialEdges);
	let steps = $state<WorkflowStep[]>(initialSteps);
	let inputs = $state<WorkflowInput[]>(initialInputs);
	let selectedStepId = $state<string | null>(null);

	const nodeTypes = { step: StepNode };

	let selectedStep = $derived(
		selectedStepId ? steps.find((s) => s.id === selectedStepId) ?? null : null
	);

	function addStep() {
		const id = `step_${Date.now()}`;
		const newStep: WorkflowStep = {
			id,
			prompt_template: '',
			model: 'sonnet',
			tools: ['Read', 'Edit', 'Bash'],
			max_turns: 10,
			condition: null
		};
		steps = [...steps, newStep];

		const newNode: Node = {
			id,
			type: 'step',
			position: { x: 200, y: nodes.length * 120 },
			data: { label: id, model: 'sonnet' }
		};
		nodes = [...nodes, newNode];
		autoLayout();
	}

	function deleteStep(stepId: string) {
		steps = steps.filter((s) => s.id !== stepId);
		nodes = nodes.filter((n) => n.id !== stepId);
		edges = edges.filter((e) => e.source !== stepId && e.target !== stepId);
		selectedStepId = null;
		autoLayout();
	}

	function autoLayout() {
		const result = getLayoutedElements(nodes, edges);
		nodes = result.nodes;
		edges = result.edges;
	}

	function handleNodeClick(_event: Event, node: Node) {
		selectedStepId = node.id;
	}

	function handleSave() {
		// Sync node data with step data
		nodes = nodes.map((n) => {
			const step = steps.find((s) => s.id === n.id);
			return step ? { ...n, data: { ...n.data, label: step.id, model: step.model } } : n;
		});
		onsave({ nodes, edges, steps, inputs });
	}

	function updateSelectedStep(updated: WorkflowStep) {
		steps = steps.map((s) => (s.id === selectedStepId ? updated : s));
		// Sync node data
		nodes = nodes.map((n) =>
			n.id === selectedStepId ? { ...n, data: { ...n.data, label: updated.id, model: updated.model } } : n
		);
	}
</script>

<div class="flex flex-col h-full">
	<!-- Toolbar -->
	<div class="flex items-center gap-3 p-3 border-b border-[var(--border)] bg-[var(--bg-subtle)]">
		<input
			type="text"
			bind:value={workflowName}
			placeholder="Workflow name"
			class="px-3 py-1.5 rounded border border-[var(--border)] bg-[var(--bg-base)] text-sm text-[var(--text-primary)] font-semibold"
		/>
		<input
			type="text"
			bind:value={workflowDescription}
			placeholder="Description"
			class="flex-1 px-3 py-1.5 rounded border border-[var(--border)] bg-[var(--bg-base)] text-sm text-[var(--text-secondary)]"
		/>
		<button
			onclick={addStep}
			class="px-3 py-1.5 text-sm border border-[var(--border)] rounded hover:border-[var(--accent)] text-[var(--text-secondary)] transition-colors"
		>
			+ Add Step
		</button>
		<button
			onclick={autoLayout}
			class="px-3 py-1.5 text-sm border border-[var(--border)] rounded hover:border-[var(--accent)] text-[var(--text-secondary)] transition-colors"
		>
			Auto Layout
		</button>
		<button
			onclick={handleSave}
			class="px-4 py-1.5 text-sm bg-[var(--accent)] text-white rounded hover:opacity-90 transition-opacity"
		>
			Save
		</button>
		<button
			onclick={onrun}
			class="px-4 py-1.5 text-sm bg-green-600 text-white rounded hover:opacity-90 transition-opacity"
		>
			Run
		</button>
	</div>

	<!-- Editor -->
	<div class="flex flex-1 min-h-0">
		<div class="flex-1">
			<SvelteFlow
				{nodes}
				{edges}
				{nodeTypes}
				fitView
				on:nodeclick={handleNodeClick}
				on:connect={(e) => {
					const newEdge = { id: `e-${e.detail.source}-${e.detail.target}`, source: e.detail.source, target: e.detail.target };
					edges = [...edges, newEdge];
				}}
			>
				<Controls />
				<Background />
			</SvelteFlow>
		</div>

		{#if selectedStep}
			<StepConfigPanel
				step={selectedStep}
				ondelete={() => deleteStep(selectedStepId!)}
			/>
		{/if}
	</div>
</div>
```

**Step 5: Run type check**

```bash
cd frontend && npm run check
```
Expected: PASS (may need minor type adjustments based on Svelte Flow's exact API)

**Step 6: Commit**

```bash
git add frontend/src/lib/components/workflows/
git commit -m "feat(frontend): add Svelte Flow workflow editor components"
```

---

## Task 9: Workflow Editor Page (New + Edit)

**Files:**
- Create: `frontend/src/routes/workflows/new/+page.svelte`
- Create: `frontend/src/routes/workflows/[id]/+page.server.ts`
- Create: `frontend/src/routes/workflows/[id]/+page.svelte`

**Step 1: Create the "new workflow" page**

Create `frontend/src/routes/workflows/new/+page.svelte`:

```svelte
<script lang="ts">
	import { goto } from '$app/navigation';
	import { API_BASE } from '$lib/config';
	import WorkflowEditor from '$lib/components/workflows/WorkflowEditor.svelte';

	let workflowName = $state('');
	let workflowDescription = $state('');

	async function handleSave(data: any) {
		const resp = await fetch(`${API_BASE}/workflows`, {
			method: 'POST',
			headers: { 'Content-Type': 'application/json' },
			body: JSON.stringify({
				name: workflowName,
				description: workflowDescription,
				graph: { nodes: data.nodes, edges: data.edges },
				steps: data.steps,
				inputs: data.inputs
			})
		});
		if (resp.ok) {
			const wf = await resp.json();
			goto(`/workflows/${wf.id}`);
		}
	}
</script>

<div class="h-[calc(100vh-4rem)]">
	<WorkflowEditor
		bind:workflowName
		bind:workflowDescription
		onsave={handleSave}
		onrun={() => {}}
	/>
</div>
```

**Step 2: Create edit page server loader**

Create `frontend/src/routes/workflows/[id]/+page.server.ts`:

```typescript
import type { Workflow } from '$lib/api-types';
import { API_BASE } from '$lib/config';
import { error } from '@sveltejs/kit';

export async function load({ fetch, params }) {
	const resp = await fetch(`${API_BASE}/workflows/${params.id}`);
	if (!resp.ok) {
		throw error(404, 'Workflow not found');
	}
	const workflow: Workflow = await resp.json();
	return { workflow };
}
```

**Step 3: Create edit page**

Create `frontend/src/routes/workflows/[id]/+page.svelte`:

```svelte
<script lang="ts">
	import { goto } from '$app/navigation';
	import { API_BASE } from '$lib/config';
	import WorkflowEditor from '$lib/components/workflows/WorkflowEditor.svelte';
	import type { Workflow } from '$lib/api-types';

	let { data } = $props();
	let workflow: Workflow = $derived(data.workflow);

	let workflowName = $state(workflow.name);
	let workflowDescription = $state(workflow.description || '');

	async function handleSave(editorData: any) {
		await fetch(`${API_BASE}/workflows/${workflow.id}`, {
			method: 'PUT',
			headers: { 'Content-Type': 'application/json' },
			body: JSON.stringify({
				name: workflowName,
				description: workflowDescription,
				graph: { nodes: editorData.nodes, edges: editorData.edges },
				steps: editorData.steps,
				inputs: editorData.inputs
			})
		});
	}

	async function handleRun() {
		const resp = await fetch(`${API_BASE}/workflows/${workflow.id}/run`, {
			method: 'POST',
			headers: { 'Content-Type': 'application/json' },
			body: JSON.stringify({ input_values: {} })
		});
		if (resp.ok) {
			const run = await resp.json();
			goto(`/workflows/${workflow.id}/runs/${run.id}`);
		}
	}
</script>

<div class="h-[calc(100vh-4rem)]">
	<WorkflowEditor
		initialNodes={workflow.graph.nodes}
		initialEdges={workflow.graph.edges}
		initialSteps={workflow.steps}
		initialInputs={workflow.inputs}
		bind:workflowName
		bind:workflowDescription
		onsave={handleSave}
		onrun={handleRun}
	/>
</div>
```

**Step 4: Run type check**

```bash
cd frontend && npm run check
```

**Step 5: Commit**

```bash
git add frontend/src/routes/workflows/
git commit -m "feat(frontend): add workflow editor pages (new + edit)"
```

---

## Task 10: Workflow Execution View Page

**Files:**
- Create: `frontend/src/routes/workflows/[id]/runs/+page.server.ts`
- Create: `frontend/src/routes/workflows/[id]/runs/+page.svelte`
- Create: `frontend/src/routes/workflows/[id]/runs/[run_id]/+page.server.ts`
- Create: `frontend/src/routes/workflows/[id]/runs/[run_id]/+page.svelte`
- Create: `frontend/src/lib/components/workflows/ExecutionView.svelte`

**Step 1: Create ExecutionView component**

Create `frontend/src/lib/components/workflows/ExecutionView.svelte`:

```svelte
<script lang="ts">
	import { SvelteFlow, Controls, Background, type Node, type Edge } from '@xyflow/svelte';
	import '@xyflow/svelte/dist/style.css';
	import type { WorkflowRun } from '$lib/api-types';
	import StepNode from './StepNode.svelte';
	import { getLayoutedElements } from './dagre-layout';

	let { run, graphNodes, graphEdges }: {
		run: WorkflowRun;
		graphNodes: Node[];
		graphEdges: Edge[];
	} = $props();

	const statusColors: Record<string, string> = {
		pending: '#6b7280',
		running: '#3b82f6',
		completed: '#22c55e',
		failed: '#ef4444',
		skipped: '#9ca3af'
	};

	let nodes = $derived.by(() => {
		const stepMap = new Map(run.steps.map((s) => [s.step_id, s]));
		const colored = graphNodes.map((n) => {
			const stepRun = stepMap.get(n.id);
			const status = stepRun?.status || 'pending';
			return {
				...n,
				data: {
					...n.data,
					status,
					borderColor: statusColors[status] || '#6b7280'
				}
			};
		});
		return getLayoutedElements(colored, graphEdges).nodes;
	});

	let edges = $derived(getLayoutedElements(graphNodes, graphEdges).edges);

	const nodeTypes = { step: StepNode };
</script>

<div class="flex flex-col h-full">
	<!-- Status bar -->
	<div class="flex items-center gap-4 p-3 border-b border-[var(--border)] bg-[var(--bg-subtle)]">
		<span class="font-semibold text-[var(--text-primary)]">Run: {run.id.slice(0, 8)}</span>
		<span
			class="text-xs px-2 py-0.5 rounded-full text-white"
			style="background-color: {statusColors[run.status]}"
		>
			{run.status}
		</span>
		{#if run.started_at}
			<span class="text-xs text-[var(--text-muted)]">Started: {new Date(run.started_at).toLocaleString()}</span>
		{/if}
		{#if run.error}
			<span class="text-xs text-red-400">{run.error}</span>
		{/if}
	</div>

	<!-- Step details sidebar -->
	<div class="flex flex-1 min-h-0">
		<div class="flex-1">
			<SvelteFlow {nodes} {edges} {nodeTypes} fitView nodesDraggable={false} nodesConnectable={false}>
				<Controls />
				<Background />
			</SvelteFlow>
		</div>

		<div class="w-72 border-l border-[var(--border)] bg-[var(--bg-subtle)] overflow-y-auto p-3">
			<h3 class="font-semibold text-sm text-[var(--text-primary)] mb-3">Steps</h3>
			{#each run.steps as stepRun}
				<div class="mb-3 p-2 rounded border border-[var(--border)] bg-[var(--bg-base)]">
					<div class="flex items-center justify-between mb-1">
						<span class="text-sm font-medium text-[var(--text-primary)]">{stepRun.step_id}</span>
						<span
							class="text-[10px] px-1.5 py-0.5 rounded-full text-white"
							style="background-color: {statusColors[stepRun.status]}"
						>
							{stepRun.status}
						</span>
					</div>
					{#if stepRun.session_id}
						<a
							href="/sessions/{stepRun.session_id}"
							class="text-xs text-[var(--accent)] hover:underline"
						>
							View session
						</a>
					{/if}
					{#if stepRun.error}
						<p class="text-xs text-red-400 mt-1">{stepRun.error}</p>
					{/if}
				</div>
			{/each}
		</div>
	</div>
</div>
```

**Step 2: Create run list page**

Create `frontend/src/routes/workflows/[id]/runs/+page.server.ts`:

```typescript
import type { WorkflowRun, Workflow } from '$lib/api-types';
import { API_BASE } from '$lib/config';
import { fetchWithFallback } from '$lib/utils/api-fetch';
import { error } from '@sveltejs/kit';

export async function load({ fetch, params }) {
	const [workflow, runs] = await Promise.all([
		fetch(`${API_BASE}/workflows/${params.id}`).then((r) => {
			if (!r.ok) throw error(404, 'Workflow not found');
			return r.json() as Promise<Workflow>;
		}),
		fetchWithFallback<WorkflowRun[]>(fetch, `${API_BASE}/workflows/${params.id}/runs`, [])
	]);
	return { workflow, runs };
}
```

Create `frontend/src/routes/workflows/[id]/runs/+page.svelte`:

```svelte
<script lang="ts">
	import PageHeader from '$lib/components/layout/PageHeader.svelte';

	let { data } = $props();
</script>

<PageHeader title="Runs: {data.workflow.name}" description="Execution history" />

<div class="container mx-auto px-4 py-6">
	{#if data.runs.length === 0}
		<p class="text-center text-[var(--text-muted)] py-8">No runs yet</p>
	{:else}
		<div class="space-y-2">
			{#each data.runs as run}
				<a
					href="/workflows/{data.workflow.id}/runs/{run.id}"
					class="block p-3 rounded-lg border border-[var(--border)] bg-[var(--bg-subtle)] hover:border-[var(--accent)] transition-colors"
				>
					<div class="flex items-center gap-3">
						<span class="font-mono text-sm text-[var(--text-primary)]">{run.id.slice(0, 8)}</span>
						<span class="text-xs px-2 py-0.5 rounded-full text-white bg-{run.status === 'completed' ? 'green' : run.status === 'failed' ? 'red' : 'blue'}-500">
							{run.status}
						</span>
						{#if run.started_at}
							<span class="text-xs text-[var(--text-muted)]">{new Date(run.started_at).toLocaleString()}</span>
						{/if}
					</div>
				</a>
			{/each}
		</div>
	{/if}
</div>
```

**Step 3: Create individual run page (execution view)**

Create `frontend/src/routes/workflows/[id]/runs/[run_id]/+page.server.ts`:

```typescript
import type { WorkflowRun, Workflow } from '$lib/api-types';
import { API_BASE } from '$lib/config';
import { error } from '@sveltejs/kit';

export async function load({ fetch, params }) {
	const [workflow, run] = await Promise.all([
		fetch(`${API_BASE}/workflows/${params.id}`).then((r) => {
			if (!r.ok) throw error(404, 'Workflow not found');
			return r.json() as Promise<Workflow>;
		}),
		fetch(`${API_BASE}/workflows/${params.id}/runs/${params.run_id}`).then((r) => {
			if (!r.ok) throw error(404, 'Run not found');
			return r.json() as Promise<WorkflowRun>;
		})
	]);
	return { workflow, run };
}
```

Create `frontend/src/routes/workflows/[id]/runs/[run_id]/+page.svelte`:

```svelte
<script lang="ts">
	import { onMount } from 'svelte';
	import { invalidateAll } from '$app/navigation';
	import ExecutionView from '$lib/components/workflows/ExecutionView.svelte';

	let { data } = $props();

	// Poll for updates while running
	let interval: ReturnType<typeof setInterval>;

	onMount(() => {
		if (data.run.status === 'pending' || data.run.status === 'running') {
			interval = setInterval(() => invalidateAll(), 3000);
		}
		return () => clearInterval(interval);
	});

	$effect(() => {
		if (data.run.status !== 'pending' && data.run.status !== 'running') {
			clearInterval(interval);
		}
	});
</script>

<div class="h-[calc(100vh-4rem)]">
	<ExecutionView
		run={data.run}
		graphNodes={data.workflow.graph.nodes}
		graphEdges={data.workflow.graph.edges}
	/>
</div>
```

**Step 4: Run type check**

```bash
cd frontend && npm run check
```

**Step 5: Commit**

```bash
git add frontend/src/routes/workflows/ frontend/src/lib/components/workflows/ExecutionView.svelte
git commit -m "feat(frontend): add workflow execution view with live polling"
```

---

## Task 11: Add Workflows to Navigation

**Files:**
- Modify: `frontend/src/lib/components/Header.svelte` (or wherever nav links live)

**Step 1: Find the navigation component**

Check `frontend/src/routes/+layout.svelte` or `frontend/src/lib/components/Header.svelte` for the nav links list.

**Step 2: Add "Workflows" link**

Add a nav link for `/workflows` between the existing entries (near Plans or Tools):

```svelte
<a href="/workflows" ...>Workflows</a>
```

**Step 3: Verify visually**

```bash
cd frontend && npm run dev
```
Navigate to the app, confirm "Workflows" appears in the header.

**Step 4: Commit**

```bash
git add frontend/src/lib/components/Header.svelte
git commit -m "feat(frontend): add Workflows to navigation header"
```

---

## Task 12: Integration Test — End-to-End Workflow

**Files:**
- Create: `api/tests/api/test_workflow_integration.py`

**Step 1: Write integration test**

Create `api/tests/api/test_workflow_integration.py`:

```python
"""Integration test: create workflow, verify it's retrievable, delete it."""
import pytest


def test_workflow_crud_lifecycle(client):
    """Full CRUD lifecycle for a workflow."""
    # Create
    payload = {
        "name": "e2e-test",
        "graph": {"nodes": [{"id": "s1", "position": {"x": 0, "y": 0}}], "edges": []},
        "steps": [{"id": "s1", "prompt_template": "Say hello"}],
        "inputs": [],
    }
    resp = client.post("/workflows", json=payload)
    assert resp.status_code == 201
    wf_id = resp.json()["id"]

    # Read
    resp = client.get(f"/workflows/{wf_id}")
    assert resp.status_code == 200
    assert resp.json()["name"] == "e2e-test"

    # Update
    payload["name"] = "e2e-updated"
    resp = client.put(f"/workflows/{wf_id}", json=payload)
    assert resp.status_code == 200
    assert resp.json()["name"] == "e2e-updated"

    # List
    resp = client.get("/workflows")
    assert any(w["id"] == wf_id for w in resp.json())

    # Runs (empty)
    resp = client.get(f"/workflows/{wf_id}/runs")
    assert resp.status_code == 200
    assert resp.json() == []

    # Delete
    resp = client.delete(f"/workflows/{wf_id}")
    assert resp.status_code == 204

    # Verify deleted
    resp = client.get(f"/workflows/{wf_id}")
    assert resp.status_code == 404
```

**Step 2: Run the test**

```bash
cd api && pytest tests/api/test_workflow_integration.py -v
```
Expected: PASS

**Step 3: Run full test suite**

```bash
cd api && pytest -v
```
Expected: All existing tests still pass + new workflow tests pass

**Step 4: Commit**

```bash
git add api/tests/api/test_workflow_integration.py
git commit -m "test: add workflow CRUD integration test"
```

---

## Summary

| Task | Component | Files Created/Modified |
|------|-----------|----------------------|
| 1 | DB Schema v9 | `api/db/schema.py`, test |
| 2 | Pydantic Models | `api/models/workflow.py`, `api/schemas.py`, test |
| 3 | Execution Engine | `api/services/workflow_engine.py`, test |
| 4 | API Router | `api/routers/workflows.py`, `api/main.py`, test |
| 5 | NPM Dependencies | `frontend/package.json` |
| 6 | TypeScript Types | `frontend/src/lib/api-types.ts` |
| 7 | Workflow List Page | `frontend/src/routes/workflows/` |
| 8 | Editor Components | `frontend/src/lib/components/workflows/` (4 files) |
| 9 | Editor Pages | `frontend/src/routes/workflows/new/`, `[id]/` |
| 10 | Execution View | `frontend/src/routes/workflows/[id]/runs/` (4 files) |
| 11 | Navigation | `frontend/src/lib/components/Header.svelte` |
| 12 | Integration Test | `api/tests/api/test_workflow_integration.py` |

**Total: 12 tasks, ~20 new files, ~4 modified files**
