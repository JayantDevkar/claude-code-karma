"""Pydantic models for workflow definitions and execution."""

import uuid
from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field


class WorkflowStep(BaseModel):
    """A single step in a workflow pipeline."""

    model_config = ConfigDict(frozen=True)

    id: str
    label: Optional[str] = None
    prompt_template: str
    model: str = "sonnet"
    tools: list[str] = Field(default_factory=lambda: ["Read", "Edit"])
    max_turns: int = 10


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
