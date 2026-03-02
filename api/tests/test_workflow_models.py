"""Tests for workflow Pydantic models."""
import pytest
from models.workflow import WorkflowStep, WorkflowInput, WorkflowDefinition


def test_workflow_step_defaults():
    step = WorkflowStep(id="test", prompt_template="Do something")
    assert step.model == "sonnet"
    assert step.tools == ["Read", "Edit"]
    assert step.max_turns == 10


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


def test_workflow_step_custom_model():
    step = WorkflowStep(
        id="fix",
        prompt_template="Fix: {{ steps.review.output }}",
        model="opus",
    )
    assert step.model == "opus"
