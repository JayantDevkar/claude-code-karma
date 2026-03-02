"""Tests for workflow execution engine."""
import json as json_mod
import sqlite3
import uuid

import pytest
from unittest.mock import patch, AsyncMock

from services.workflow_engine import (
    evaluate_condition,
    resolve_template,
    topological_sort,
)


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
    ctx = {"steps": {"review": {"output": "found issues", "has_issues": "true"}}}
    assert evaluate_condition("{{ steps.review.has_issues }} == true", ctx) is True


def test_evaluate_condition_false():
    ctx = {"steps": {"review": {"output": "all good", "has_issues": "false"}}}
    assert evaluate_condition("{{ steps.review.has_issues }} == true", ctx) is False


def test_evaluate_condition_none():
    assert evaluate_condition(None, {}) is True  # No condition = always run


# --- 4d: Cycle detection test ---


def test_topological_sort_cycle_raises():
    """Cycles in the graph should raise ValueError."""
    edges = [
        {"source": "a", "target": "b"},
        {"source": "b", "target": "a"},
    ]
    with pytest.raises(ValueError, match="cycle"):
        topological_sort(["a", "b"], edges)


# --- 4f: evaluate_condition coverage ---


def test_evaluate_condition_not_equal_true():
    ctx = {"steps": {"review": {"status": "pass"}}}
    assert evaluate_condition("{{ steps.review.status }} != fail", ctx) is True


def test_evaluate_condition_not_equal_false():
    ctx = {"steps": {"review": {"status": "pass"}}}
    assert evaluate_condition("{{ steps.review.status }} != pass", ctx) is False


def test_evaluate_condition_truthy_fallback():
    ctx = {"steps": {"check": {"ready": "yes"}}}
    assert evaluate_condition("{{ steps.check.ready }}", ctx) is True


def test_evaluate_condition_falsy_values():
    ctx = {"steps": {"check": {"ready": "false"}}}
    assert evaluate_condition("{{ steps.check.ready }}", ctx) is False
    ctx2 = {"steps": {"check": {"ready": "0"}}}
    assert evaluate_condition("{{ steps.check.ready }}", ctx2) is False
    ctx3 = {"steps": {"check": {"ready": ""}}}
    assert evaluate_condition("{{ steps.check.ready }}", ctx3) is False


# --- 4c: run_claude_step test ---


@pytest.mark.asyncio
async def test_run_claude_step_success():
    mock_proc = AsyncMock()
    mock_proc.communicate.return_value = (
        json_mod.dumps({"result": "hello world", "session_id": "sess-abc"}).encode(),
        b"",
    )
    mock_proc.returncode = 0

    with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
        from services.workflow_engine import run_claude_step
        result = await run_claude_step("Say hello", model="sonnet")
        assert result["result"] == "hello world"
        assert result["session_id"] == "sess-abc"
        assert result["exit_code"] == 0


# --- 4a: execute_workflow tests ---


@pytest.fixture
def engine_db(tmp_path):
    """Set up a test DB for engine tests."""
    db_path = tmp_path / "engine_test.db"
    with patch("db.connection.get_db_path", return_value=db_path):
        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
        from db.schema import ensure_schema
        ensure_schema(conn)
        conn.close()
        yield db_path


@pytest.mark.asyncio
async def test_execute_workflow_success(engine_db):
    db_path = engine_db
    run_id = str(uuid.uuid4())
    workflow_id = str(uuid.uuid4())

    # Create workflow and run records
    wconn = sqlite3.connect(str(db_path), timeout=10.0)
    wconn.row_factory = sqlite3.Row
    wconn.execute("INSERT INTO workflows (id, name, graph, steps) VALUES (?, ?, '{}', '[]')", (workflow_id, "test"))
    wconn.execute("INSERT INTO workflow_runs (id, workflow_id, status) VALUES (?, ?, 'pending')", (run_id, workflow_id))
    wconn.execute("INSERT INTO workflow_run_steps (id, run_id, step_id, status) VALUES (?, ?, 'step_1', 'pending')", (str(uuid.uuid4()), run_id))
    wconn.commit()
    wconn.close()

    mock_result = {"result": "Task completed", "session_id": "sess-123", "exit_code": 0}

    with patch("services.workflow_engine.run_claude_step", new_callable=AsyncMock, return_value=mock_result):
        from services.workflow_engine import execute_workflow
        await execute_workflow(
            run_id=run_id,
            workflow_id=workflow_id,
            steps=[{"id": "step_1", "prompt_template": "Do something", "model": "sonnet", "tools": ["Read"], "max_turns": 5}],
            edges=[],
            input_values={},
        )

    # Verify run is completed
    vconn = sqlite3.connect(str(db_path))
    vconn.row_factory = sqlite3.Row
    run = vconn.execute("SELECT status FROM workflow_runs WHERE id = ?", (run_id,)).fetchone()
    assert run["status"] == "completed"
    vconn.close()


@pytest.mark.asyncio
async def test_execute_workflow_step_failure(engine_db):
    db_path = engine_db
    run_id = str(uuid.uuid4())
    workflow_id = str(uuid.uuid4())

    wconn = sqlite3.connect(str(db_path), timeout=10.0)
    wconn.row_factory = sqlite3.Row
    wconn.execute("INSERT INTO workflows (id, name, graph, steps) VALUES (?, ?, '{}', '[]')", (workflow_id, "test"))
    wconn.execute("INSERT INTO workflow_runs (id, workflow_id, status) VALUES (?, ?, 'pending')", (run_id, workflow_id))
    wconn.execute("INSERT INTO workflow_run_steps (id, run_id, step_id, status) VALUES (?, ?, 'step_1', 'pending')", (str(uuid.uuid4()), run_id))
    wconn.execute("INSERT INTO workflow_run_steps (id, run_id, step_id, status) VALUES (?, ?, 'step_2', 'pending')", (str(uuid.uuid4()), run_id))
    wconn.commit()
    wconn.close()

    mock_result = {"result": "", "session_id": None, "exit_code": 1}

    with patch("services.workflow_engine.run_claude_step", new_callable=AsyncMock, return_value=mock_result):
        from services.workflow_engine import execute_workflow
        await execute_workflow(
            run_id=run_id,
            workflow_id=workflow_id,
            steps=[
                {"id": "step_1", "prompt_template": "Fail", "model": "sonnet", "tools": ["Read"], "max_turns": 5},
                {"id": "step_2", "prompt_template": "Never reached", "model": "sonnet", "tools": ["Read"], "max_turns": 5},
            ],
            edges=[{"source": "step_1", "target": "step_2"}],
            input_values={},
        )

    vconn = sqlite3.connect(str(db_path))
    vconn.row_factory = sqlite3.Row
    run = vconn.execute("SELECT status FROM workflow_runs WHERE id = ?", (run_id,)).fetchone()
    assert run["status"] == "failed"
    vconn.close()
