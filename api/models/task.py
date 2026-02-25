"""
Task model for Claude Code session tasks.

Tasks are stored in ~/.claude/tasks/{session-uuid}/ as individual JSON files (1.json, 2.json, etc.)
This is the newer task system that replaces/augments legacy todos with dependency tracking.

When task files are not persisted (ephemeral/cleaned up), tasks can be reconstructed
from TaskCreate/TaskUpdate tool_use events in the session JSONL file.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field


class Task(BaseModel):
    """
    A single task from a session's task list.

    Unlike legacy TodoItems which are simple content/status pairs,
    Tasks have rich metadata including dependency tracking (blocks/blockedBy).

    Attributes:
        id: Unique task identifier (typically numeric string like "1", "2")
        subject: Short title for the task
        description: Detailed description of what needs to be done
        status: Current status (pending, in_progress, completed)
        active_form: Active verb form for display (e.g., "Exploring codebase")
        blocks: List of task IDs that this task blocks
        blocked_by: List of task IDs that block this task
    """

    model_config = ConfigDict(frozen=True, populate_by_name=True)

    id: str = Field(..., description="Unique task identifier")
    subject: str = Field(..., description="Short title for the task")
    description: str = Field(..., description="Detailed task description")
    status: Literal["pending", "in_progress", "completed"] = Field(
        default="pending", description="Current task status"
    )
    active_form: Optional[str] = Field(
        default=None, alias="activeForm", description="Active verb form for display"
    )
    blocks: List[str] = Field(default_factory=list, description="Task IDs that this task blocks")
    blocked_by: List[str] = Field(
        default_factory=list,
        alias="blockedBy",
        description="Task IDs that block this task",
    )


def load_task_from_file(path: Path) -> Task:
    """
    Load a single task from a JSON file.

    Args:
        path: Path to the task JSON file (e.g., ~/.claude/tasks/{uuid}/1.json)

    Returns:
        Task instance

    Raises:
        FileNotFoundError: If file doesn't exist
        json.JSONDecodeError: If file is not valid JSON
        ValidationError: If JSON doesn't match Task schema
    """
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    return Task.model_validate(data)


def load_tasks_from_directory(tasks_dir: Path) -> List[Task]:
    """
    Load all tasks from a session's tasks directory.

    Args:
        tasks_dir: Path to the tasks directory (e.g., ~/.claude/tasks/{uuid}/)

    Returns:
        List of Task instances sorted by ID

    Note:
        Skips files that fail to load (invalid JSON, missing required fields).
        The .lock file is automatically ignored.
    """
    if not tasks_dir.exists() or not tasks_dir.is_dir():
        return []

    tasks: List[Task] = []
    for task_file in tasks_dir.glob("*.json"):
        # Skip non-task files
        if task_file.name.startswith("."):
            continue

        try:
            task = load_task_from_file(task_file)
            tasks.append(task)
        except (FileNotFoundError, json.JSONDecodeError, ValueError):
            continue

    # Sort by ID (numeric sort for proper ordering)
    return sorted(tasks, key=lambda t: int(t.id) if t.id.isdigit() else t.id)


def reconstruct_tasks_from_jsonl(jsonl_path: Path) -> List[Task]:
    """
    Reconstruct tasks from TaskCreate/TaskUpdate tool_use events in a JSONL file.

    This is a fallback mechanism for when task JSON files are not persisted
    (ephemeral during session, cleaned up after, or session ended abnormally).

    The algorithm:
    1. Parse JSONL file line by line
    2. Find AssistantMessage entries with tool_use content blocks
    3. Extract TaskCreate and TaskUpdate tool calls
    4. Replay events in order to reconstruct final task state

    Args:
        jsonl_path: Path to session JSONL file

    Returns:
        List of Task instances sorted by ID, or empty list if no task events found

    Note:
        - TaskCreate events auto-increment task IDs based on order of appearance
        - TaskUpdate events apply incremental changes (only update specified fields)
        - This matches how Claude Code assigns task IDs internally
    """
    from .content import ToolUseBlock
    from .message import AssistantMessage, parse_message

    if not jsonl_path.exists():
        return []

    # Mutable task data: id -> dict of task fields
    tasks_data: Dict[str, Dict[str, Any]] = {}
    task_counter = 0

    with open(jsonl_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue

            try:
                data = json.loads(line)
                msg = parse_message(data)
            except (json.JSONDecodeError, ValueError, KeyError):
                continue

            # Only process AssistantMessage with content blocks
            if not isinstance(msg, AssistantMessage):
                continue

            for block in msg.content_blocks:
                if not isinstance(block, ToolUseBlock):
                    continue

                if block.name == "TaskCreate":
                    task_counter += 1
                    task_id = str(task_counter)
                    input_data = block.input

                    tasks_data[task_id] = {
                        "id": task_id,
                        "subject": input_data.get("subject", ""),
                        "description": input_data.get("description", ""),
                        "status": "pending",
                        "active_form": input_data.get("activeForm"),
                        "blocks": [],
                        "blocked_by": [],
                    }

                elif block.name == "TaskUpdate":
                    input_data = block.input
                    task_id = input_data.get("taskId")

                    if not task_id or task_id not in tasks_data:
                        continue

                    task = tasks_data[task_id]

                    # Apply incremental updates (only update fields that are present)
                    if "status" in input_data:
                        task["status"] = input_data["status"]
                    if "subject" in input_data:
                        task["subject"] = input_data["subject"]
                    if "description" in input_data:
                        task["description"] = input_data["description"]
                    if "activeForm" in input_data:
                        task["active_form"] = input_data["activeForm"]

                    # Extend dependency lists (addBlocks/addBlockedBy are additive)
                    if "addBlocks" in input_data:
                        existing_blocks = set(task["blocks"])
                        for block_id in input_data["addBlocks"]:
                            if block_id not in existing_blocks:
                                task["blocks"].append(block_id)
                    if "addBlockedBy" in input_data:
                        existing_blocked_by = set(task["blocked_by"])
                        for block_id in input_data["addBlockedBy"]:
                            if block_id not in existing_blocked_by:
                                task["blocked_by"].append(block_id)

    # Convert to Task instances
    tasks: List[Task] = []
    for task_data in tasks_data.values():
        try:
            tasks.append(Task.model_validate(task_data))
        except ValueError:
            # Skip invalid tasks
            continue

    # Sort by ID (numeric sort for proper ordering)
    return sorted(tasks, key=lambda t: int(t.id) if t.id.isdigit() else t.id)
