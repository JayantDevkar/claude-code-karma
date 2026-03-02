"""Pydantic models for workflow definitions and execution."""

import uuid
from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator


ALLOWED_MODELS = {"haiku", "sonnet", "opus"}
ALLOWED_TOOLS = {
    "Read", "Edit", "Write", "Bash", "Glob", "Grep",
    "WebFetch", "WebSearch", "Agent", "Skill",
}


class WorkflowStep(BaseModel):
    """A single step in a workflow pipeline."""

    model_config = ConfigDict(frozen=True)

    id: str
    label: Optional[str] = None
    prompt_template: str = Field(max_length=100_000)
    model: str = "sonnet"
    tools: list[str] = Field(default_factory=lambda: ["Read", "Edit"])
    max_turns: int = Field(default=10, ge=1, le=100)

    @field_validator("model")
    @classmethod
    def validate_model(cls, v: str) -> str:
        if v not in ALLOWED_MODELS:
            raise ValueError(f"Unknown model '{v}'. Allowed: {sorted(ALLOWED_MODELS)}")
        return v

    @field_validator("tools")
    @classmethod
    def validate_tools(cls, v: list[str]) -> list[str]:
        invalid = set(v) - ALLOWED_TOOLS
        if invalid:
            raise ValueError(f"Unknown tools: {sorted(invalid)}. Allowed: {sorted(ALLOWED_TOOLS)}")
        return v


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
