"""
Todo item model for Claude Code session todos.

Todos are stored in ~/.claude/todos/{session-uuid}-agent-{session-uuid}.json
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field


class TodoItem(BaseModel):
    """
    A single todo item from a session's todo list.

    Attributes:
        content: The todo description/task
        status: Current status (pending, in_progress, completed)
        active_form: Active verb form for display (e.g., "Exploring codebase")
    """

    model_config = ConfigDict(frozen=True, populate_by_name=True)

    content: str = Field(..., description="Todo item description")
    status: Literal["pending", "in_progress", "completed"] = Field(
        default="pending", description="Current todo status"
    )
    active_form: Optional[str] = Field(
        default=None, alias="activeForm", description="Active verb form for display"
    )


def load_todos_from_file(path: Path) -> List[TodoItem]:
    """
    Load todo items from a session's todo JSON file.

    Args:
        path: Path to the todo JSON file

    Returns:
        List of TodoItem instances

    Raises:
        FileNotFoundError: If file doesn't exist
        json.JSONDecodeError: If file is not valid JSON
    """
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    if not isinstance(data, list):
        return []

    return [TodoItem.model_validate(item) for item in data]
