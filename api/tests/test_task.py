"""
Unit tests for Task model and task loading functions.

Tests cover:
- Task instantiation with all status values
- Field aliases "activeForm" -> active_form, "blockedBy" -> blocked_by
- Optional active_form field
- Default values for blocks and blocked_by
- Immutability (frozen=True)
- load_task_from_file() functionality
- load_tasks_from_directory() functionality and edge cases
- reconstruct_tasks_from_jsonl() fallback functionality
"""

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from models import Task, load_task_from_file, load_tasks_from_directory
from models.task import reconstruct_tasks_from_jsonl


class TestTaskInstantiation:
    """Tests for Task instantiation with various status values."""

    def test_instantiation_with_pending_status(self):
        """Test Task with pending status."""
        task = Task(
            id="1",
            subject="Write documentation",
            description="Write the API docs",
            status="pending",
        )
        assert task.id == "1"
        assert task.subject == "Write documentation"
        assert task.description == "Write the API docs"
        assert task.status == "pending"

    def test_instantiation_with_in_progress_status(self):
        """Test Task with in_progress status."""
        task = Task(
            id="2",
            subject="Implement feature",
            description="Implement the new feature",
            status="in_progress",
        )
        assert task.status == "in_progress"

    def test_instantiation_with_completed_status(self):
        """Test Task with completed status."""
        task = Task(
            id="3",
            subject="Fix bug",
            description="Fix the login bug",
            status="completed",
        )
        assert task.status == "completed"

    def test_default_status_is_pending(self):
        """Test that status defaults to pending when not provided."""
        task = Task(
            id="4",
            subject="New task",
            description="New task description",
        )
        assert task.status == "pending"

    def test_invalid_status_raises_validation_error(self):
        """Test that invalid status value raises ValidationError."""
        with pytest.raises(ValidationError):
            Task(
                id="5",
                subject="Invalid task",
                description="This will fail",
                status="invalid_status",
            )


class TestTaskFieldAliases:
    """Tests for field aliases: activeForm -> active_form, blockedBy -> blocked_by."""

    def test_active_form_alias_on_instantiation(self):
        """Test that activeForm alias works during instantiation."""
        task = Task(
            id="1",
            subject="Test task",
            description="Test description",
            activeForm="Testing task",
        )
        assert task.active_form == "Testing task"

    def test_active_form_direct_field_name(self):
        """Test that active_form field name also works."""
        task = Task(
            id="1",
            subject="Test task",
            description="Test description",
            active_form="Testing task",
        )
        assert task.active_form == "Testing task"

    def test_blocked_by_alias_on_instantiation(self):
        """Test that blockedBy alias works during instantiation."""
        task = Task(
            id="1",
            subject="Test task",
            description="Test description",
            blockedBy=["2", "3"],
        )
        assert task.blocked_by == ["2", "3"]

    def test_blocked_by_direct_field_name(self):
        """Test that blocked_by field name also works."""
        task = Task(
            id="1",
            subject="Test task",
            description="Test description",
            blocked_by=["2", "3"],
        )
        assert task.blocked_by == ["2", "3"]

    def test_model_validate_with_aliases(self):
        """Test model_validate with aliases in dict."""
        data = {
            "id": "1",
            "subject": "Validate task",
            "description": "Test validation",
            "status": "pending",
            "activeForm": "Validating task",
            "blockedBy": ["2"],
            "blocks": ["3"],
        }
        task = Task.model_validate(data)
        assert task.active_form == "Validating task"
        assert task.blocked_by == ["2"]
        assert task.blocks == ["3"]

    def test_model_dump_with_alias(self):
        """Test that model_dump can output with alias."""
        task = Task(
            id="1",
            subject="Dump task",
            description="Test dump",
            active_form="Dumping task",
            blocked_by=["2"],
        )
        dumped = task.model_dump(by_alias=True)
        assert "activeForm" in dumped
        assert dumped["activeForm"] == "Dumping task"
        assert "blockedBy" in dumped
        assert dumped["blockedBy"] == ["2"]


class TestTaskDefaultValues:
    """Tests for default values of blocks and blocked_by."""

    def test_blocks_defaults_to_empty_list(self):
        """Test that blocks defaults to empty list."""
        task = Task(
            id="1",
            subject="Task",
            description="Description",
        )
        assert task.blocks == []

    def test_blocked_by_defaults_to_empty_list(self):
        """Test that blocked_by defaults to empty list."""
        task = Task(
            id="1",
            subject="Task",
            description="Description",
        )
        assert task.blocked_by == []

    def test_active_form_defaults_to_none(self):
        """Test that active_form defaults to None."""
        task = Task(
            id="1",
            subject="Task",
            description="Description",
        )
        assert task.active_form is None


class TestTaskImmutability:
    """Tests for Task immutability (frozen=True)."""

    def test_cannot_modify_id(self):
        """Test that id field cannot be modified after creation."""
        task = Task(id="1", subject="Task", description="Desc")
        with pytest.raises(ValidationError):
            task.id = "2"

    def test_cannot_modify_subject(self):
        """Test that subject field cannot be modified after creation."""
        task = Task(id="1", subject="Original", description="Desc")
        with pytest.raises(ValidationError):
            task.subject = "Modified"

    def test_cannot_modify_status(self):
        """Test that status field cannot be modified after creation."""
        task = Task(id="1", subject="Task", description="Desc", status="pending")
        with pytest.raises(ValidationError):
            task.status = "completed"

    def test_task_not_hashable_due_to_lists(self):
        """Test that Task is not hashable due to list fields (blocks, blocked_by)."""
        task = Task(id="1", subject="Task 1", description="Desc 1")
        # Even though frozen=True, the model contains list fields which are unhashable
        with pytest.raises(TypeError, match="unhashable type"):
            hash(task)


class TestLoadTaskFromFile:
    """Tests for load_task_from_file function."""

    def test_load_valid_task_file(self, tmp_path: Path):
        """Test loading a valid task JSON file."""
        task_file = tmp_path / "1.json"
        task_data = {
            "id": "1",
            "subject": "Implement feature",
            "description": "Detailed description here",
            "status": "in_progress",
            "activeForm": "Implementing feature",
            "blocks": ["2", "3"],
            "blockedBy": [],
        }
        task_file.write_text(json.dumps(task_data))

        task = load_task_from_file(task_file)

        assert task.id == "1"
        assert task.subject == "Implement feature"
        assert task.description == "Detailed description here"
        assert task.status == "in_progress"
        assert task.active_form == "Implementing feature"
        assert task.blocks == ["2", "3"]
        assert task.blocked_by == []

    def test_load_minimal_task_file(self, tmp_path: Path):
        """Test loading task with only required fields."""
        task_file = tmp_path / "2.json"
        task_data = {
            "id": "2",
            "subject": "Minimal task",
            "description": "Only required fields",
        }
        task_file.write_text(json.dumps(task_data))

        task = load_task_from_file(task_file)

        assert task.id == "2"
        assert task.status == "pending"  # default
        assert task.active_form is None  # default
        assert task.blocks == []  # default
        assert task.blocked_by == []  # default

    def test_file_not_found_raises_error(self, tmp_path: Path):
        """Test that FileNotFoundError is raised for missing file."""
        nonexistent_path = tmp_path / "nonexistent.json"

        with pytest.raises(FileNotFoundError):
            load_task_from_file(nonexistent_path)

    def test_invalid_json_raises_decode_error(self, tmp_path: Path):
        """Test that invalid JSON raises JSONDecodeError."""
        invalid_file = tmp_path / "invalid.json"
        invalid_file.write_text("not valid json {")

        with pytest.raises(json.JSONDecodeError):
            load_task_from_file(invalid_file)

    def test_missing_required_field_raises_validation_error(self, tmp_path: Path):
        """Test that missing required field raises ValidationError."""
        task_file = tmp_path / "incomplete.json"
        task_data = {"id": "1", "subject": "Missing description"}
        task_file.write_text(json.dumps(task_data))

        with pytest.raises(ValidationError):
            load_task_from_file(task_file)


class TestLoadTasksFromDirectory:
    """Tests for load_tasks_from_directory function."""

    def test_load_tasks_from_valid_directory(self, tmp_path: Path):
        """Test loading multiple tasks from a directory."""
        tasks_dir = tmp_path / "tasks"
        tasks_dir.mkdir()

        # Create task files
        (tasks_dir / "1.json").write_text(
            json.dumps(
                {
                    "id": "1",
                    "subject": "First task",
                    "description": "First description",
                    "status": "completed",
                }
            )
        )
        (tasks_dir / "2.json").write_text(
            json.dumps(
                {
                    "id": "2",
                    "subject": "Second task",
                    "description": "Second description",
                    "status": "in_progress",
                    "blockedBy": ["1"],
                }
            )
        )
        (tasks_dir / "3.json").write_text(
            json.dumps(
                {
                    "id": "3",
                    "subject": "Third task",
                    "description": "Third description",
                    "status": "pending",
                    "blockedBy": ["2"],
                }
            )
        )

        tasks = load_tasks_from_directory(tasks_dir)

        assert len(tasks) == 3
        assert all(isinstance(t, Task) for t in tasks)
        # Should be sorted by ID
        assert tasks[0].id == "1"
        assert tasks[1].id == "2"
        assert tasks[2].id == "3"

    def test_empty_directory_returns_empty_list(self, tmp_path: Path):
        """Test that empty directory returns empty list."""
        tasks_dir = tmp_path / "empty_tasks"
        tasks_dir.mkdir()

        tasks = load_tasks_from_directory(tasks_dir)

        assert tasks == []

    def test_nonexistent_directory_returns_empty_list(self, tmp_path: Path):
        """Test that nonexistent directory returns empty list."""
        nonexistent_dir = tmp_path / "nonexistent"

        tasks = load_tasks_from_directory(nonexistent_dir)

        assert tasks == []

    def test_skips_invalid_json_files(self, tmp_path: Path):
        """Test that invalid JSON files are skipped."""
        tasks_dir = tmp_path / "mixed_tasks"
        tasks_dir.mkdir()

        # Valid task
        (tasks_dir / "1.json").write_text(
            json.dumps({"id": "1", "subject": "Valid", "description": "Valid task"})
        )
        # Invalid JSON
        (tasks_dir / "2.json").write_text("not valid json")
        # Missing required field
        (tasks_dir / "3.json").write_text(json.dumps({"id": "3"}))

        tasks = load_tasks_from_directory(tasks_dir)

        assert len(tasks) == 1
        assert tasks[0].id == "1"

    def test_skips_lock_files(self, tmp_path: Path):
        """Test that .lock files are skipped."""
        tasks_dir = tmp_path / "tasks_with_lock"
        tasks_dir.mkdir()

        (tasks_dir / "1.json").write_text(
            json.dumps({"id": "1", "subject": "Task", "description": "Desc"})
        )
        (tasks_dir / ".lock").write_text("")

        tasks = load_tasks_from_directory(tasks_dir)

        assert len(tasks) == 1
        assert tasks[0].id == "1"

    def test_skips_hidden_files(self, tmp_path: Path):
        """Test that hidden files (starting with .) are skipped."""
        tasks_dir = tmp_path / "tasks_with_hidden"
        tasks_dir.mkdir()

        (tasks_dir / "1.json").write_text(
            json.dumps({"id": "1", "subject": "Task", "description": "Desc"})
        )
        (tasks_dir / ".hidden.json").write_text(
            json.dumps({"id": "hidden", "subject": "Hidden", "description": "Hidden"})
        )

        tasks = load_tasks_from_directory(tasks_dir)

        assert len(tasks) == 1
        assert tasks[0].id == "1"

    def test_sorts_tasks_by_numeric_id(self, tmp_path: Path):
        """Test that tasks are sorted numerically by ID."""
        tasks_dir = tmp_path / "tasks_unsorted"
        tasks_dir.mkdir()

        # Create in non-numeric order
        (tasks_dir / "10.json").write_text(
            json.dumps({"id": "10", "subject": "Tenth", "description": "Desc"})
        )
        (tasks_dir / "2.json").write_text(
            json.dumps({"id": "2", "subject": "Second", "description": "Desc"})
        )
        (tasks_dir / "1.json").write_text(
            json.dumps({"id": "1", "subject": "First", "description": "Desc"})
        )

        tasks = load_tasks_from_directory(tasks_dir)

        assert len(tasks) == 3
        assert tasks[0].id == "1"
        assert tasks[1].id == "2"
        assert tasks[2].id == "10"

    def test_file_path_returns_empty_list(self, tmp_path: Path):
        """Test that passing a file path (not directory) returns empty list."""
        file_path = tmp_path / "not_a_dir.json"
        file_path.write_text("{}")

        tasks = load_tasks_from_directory(file_path)

        assert tasks == []


class TestReconstructTasksFromJsonl:
    """Tests for reconstruct_tasks_from_jsonl fallback functionality."""

    _msg_counter = 0

    def _create_assistant_message_with_tool_use(self, tool_name: str, tool_input: dict) -> dict:
        """Helper to create a valid AssistantMessage with a tool_use block."""
        TestReconstructTasksFromJsonl._msg_counter += 1
        return {
            "type": "assistant",
            "uuid": f"uuid_{TestReconstructTasksFromJsonl._msg_counter}",
            "timestamp": "2026-01-24T12:00:00.000Z",
            "message": {
                "id": f"msg_test_{TestReconstructTasksFromJsonl._msg_counter}",
                "role": "assistant",
                "model": "claude-3-opus",
                "content": [
                    {
                        "type": "tool_use",
                        "id": f"toolu_test_{TestReconstructTasksFromJsonl._msg_counter}",
                        "name": tool_name,
                        "input": tool_input,
                    }
                ],
                "usage": {
                    "input_tokens": 100,
                    "output_tokens": 50,
                },
            },
        }

    def test_reconstruct_from_task_create_events(self, tmp_path: Path):
        """Test reconstruction from TaskCreate events."""
        jsonl_file = tmp_path / "session.jsonl"

        messages = [
            self._create_assistant_message_with_tool_use(
                "TaskCreate",
                {
                    "subject": "First task",
                    "description": "First task description",
                    "activeForm": "Creating first task",
                },
            ),
            self._create_assistant_message_with_tool_use(
                "TaskCreate",
                {
                    "subject": "Second task",
                    "description": "Second task description",
                    "activeForm": "Creating second task",
                },
            ),
        ]
        jsonl_file.write_text("\n".join(json.dumps(m) for m in messages))

        tasks = reconstruct_tasks_from_jsonl(jsonl_file)

        assert len(tasks) == 2
        assert tasks[0].id == "1"
        assert tasks[0].subject == "First task"
        assert tasks[0].description == "First task description"
        assert tasks[0].active_form == "Creating first task"
        assert tasks[0].status == "pending"
        assert tasks[1].id == "2"
        assert tasks[1].subject == "Second task"

    def test_reconstruct_with_task_updates(self, tmp_path: Path):
        """Test reconstruction with TaskUpdate events for status changes."""
        jsonl_file = tmp_path / "session.jsonl"

        messages = [
            self._create_assistant_message_with_tool_use(
                "TaskCreate",
                {
                    "subject": "Task to update",
                    "description": "Will be updated",
                },
            ),
            self._create_assistant_message_with_tool_use(
                "TaskUpdate",
                {
                    "taskId": "1",
                    "status": "in_progress",
                },
            ),
            self._create_assistant_message_with_tool_use(
                "TaskUpdate",
                {
                    "taskId": "1",
                    "status": "completed",
                },
            ),
        ]
        jsonl_file.write_text("\n".join(json.dumps(m) for m in messages))

        tasks = reconstruct_tasks_from_jsonl(jsonl_file)

        assert len(tasks) == 1
        assert tasks[0].status == "completed"

    def test_reconstruct_with_dependencies(self, tmp_path: Path):
        """Test reconstruction with addBlocks and addBlockedBy updates."""
        jsonl_file = tmp_path / "session.jsonl"

        messages = [
            self._create_assistant_message_with_tool_use(
                "TaskCreate",
                {"subject": "Task 1", "description": "First task"},
            ),
            self._create_assistant_message_with_tool_use(
                "TaskCreate",
                {"subject": "Task 2", "description": "Second task"},
            ),
            self._create_assistant_message_with_tool_use(
                "TaskCreate",
                {"subject": "Task 3", "description": "Third task"},
            ),
            self._create_assistant_message_with_tool_use(
                "TaskUpdate",
                {
                    "taskId": "1",
                    "addBlocks": ["2", "3"],
                },
            ),
            self._create_assistant_message_with_tool_use(
                "TaskUpdate",
                {
                    "taskId": "3",
                    "addBlockedBy": ["1", "2"],
                },
            ),
        ]
        jsonl_file.write_text("\n".join(json.dumps(m) for m in messages))

        tasks = reconstruct_tasks_from_jsonl(jsonl_file)

        assert len(tasks) == 3
        assert tasks[0].blocks == ["2", "3"]
        assert tasks[2].blocked_by == ["1", "2"]

    def test_reconstruct_empty_jsonl(self, tmp_path: Path):
        """Test that empty JSONL returns empty list."""
        jsonl_file = tmp_path / "empty.jsonl"
        jsonl_file.write_text("")

        tasks = reconstruct_tasks_from_jsonl(jsonl_file)

        assert tasks == []

    def test_reconstruct_nonexistent_file(self, tmp_path: Path):
        """Test that nonexistent file returns empty list."""
        nonexistent = tmp_path / "nonexistent.jsonl"

        tasks = reconstruct_tasks_from_jsonl(nonexistent)

        assert tasks == []

    def test_reconstruct_skips_invalid_lines(self, tmp_path: Path):
        """Test that invalid JSON lines are skipped."""
        jsonl_file = tmp_path / "mixed.jsonl"

        valid_message = self._create_assistant_message_with_tool_use(
            "TaskCreate",
            {"subject": "Valid task", "description": "Valid"},
        )
        lines = [
            "not valid json",
            json.dumps(valid_message),
            "also not valid",
        ]
        jsonl_file.write_text("\n".join(lines))

        tasks = reconstruct_tasks_from_jsonl(jsonl_file)

        assert len(tasks) == 1
        assert tasks[0].subject == "Valid task"

    def test_reconstruct_ignores_other_tool_use(self, tmp_path: Path):
        """Test that non-task tool_use blocks are ignored."""
        jsonl_file = tmp_path / "mixed_tools.jsonl"

        messages = [
            self._create_assistant_message_with_tool_use(
                "Read",
                {"file_path": "/some/file.txt"},
            ),
            self._create_assistant_message_with_tool_use(
                "TaskCreate",
                {"subject": "Task", "description": "Desc"},
            ),
            self._create_assistant_message_with_tool_use(
                "Write",
                {"file_path": "/some/file.txt", "content": "hello"},
            ),
        ]
        jsonl_file.write_text("\n".join(json.dumps(m) for m in messages))

        tasks = reconstruct_tasks_from_jsonl(jsonl_file)

        assert len(tasks) == 1
        assert tasks[0].subject == "Task"

    def test_reconstruct_update_for_nonexistent_task_is_ignored(self, tmp_path: Path):
        """Test that TaskUpdate for nonexistent task is silently ignored."""
        jsonl_file = tmp_path / "orphan_update.jsonl"

        messages = [
            self._create_assistant_message_with_tool_use(
                "TaskUpdate",
                {
                    "taskId": "999",  # No task with this ID exists
                    "status": "completed",
                },
            ),
            self._create_assistant_message_with_tool_use(
                "TaskCreate",
                {"subject": "Task", "description": "Desc"},
            ),
        ]
        jsonl_file.write_text("\n".join(json.dumps(m) for m in messages))

        tasks = reconstruct_tasks_from_jsonl(jsonl_file)

        assert len(tasks) == 1
        assert tasks[0].status == "pending"  # Not affected by orphan update

    def test_reconstruct_incremental_dependency_updates(self, tmp_path: Path):
        """Test that dependency updates are additive (don't replace)."""
        jsonl_file = tmp_path / "incremental.jsonl"

        messages = [
            self._create_assistant_message_with_tool_use(
                "TaskCreate",
                {"subject": "Task", "description": "Desc"},
            ),
            self._create_assistant_message_with_tool_use(
                "TaskUpdate",
                {
                    "taskId": "1",
                    "addBlocks": ["2"],
                },
            ),
            self._create_assistant_message_with_tool_use(
                "TaskUpdate",
                {
                    "taskId": "1",
                    "addBlocks": ["3"],  # Should add, not replace
                },
            ),
        ]
        jsonl_file.write_text("\n".join(json.dumps(m) for m in messages))

        tasks = reconstruct_tasks_from_jsonl(jsonl_file)

        assert tasks[0].blocks == ["2", "3"]  # Both preserved

    def test_reconstruct_no_duplicate_dependencies(self, tmp_path: Path):
        """Test that duplicate dependencies are not added."""
        jsonl_file = tmp_path / "duplicates.jsonl"

        messages = [
            self._create_assistant_message_with_tool_use(
                "TaskCreate",
                {"subject": "Task", "description": "Desc"},
            ),
            self._create_assistant_message_with_tool_use(
                "TaskUpdate",
                {
                    "taskId": "1",
                    "addBlocks": ["2"],
                },
            ),
            self._create_assistant_message_with_tool_use(
                "TaskUpdate",
                {
                    "taskId": "1",
                    "addBlocks": ["2"],  # Duplicate
                },
            ),
        ]
        jsonl_file.write_text("\n".join(json.dumps(m) for m in messages))

        tasks = reconstruct_tasks_from_jsonl(jsonl_file)

        assert tasks[0].blocks == ["2"]  # No duplicate

    def test_reconstruct_updates_subject_and_description(self, tmp_path: Path):
        """Test that TaskUpdate can modify subject and description."""
        jsonl_file = tmp_path / "update_fields.jsonl"

        messages = [
            self._create_assistant_message_with_tool_use(
                "TaskCreate",
                {"subject": "Original", "description": "Original desc"},
            ),
            self._create_assistant_message_with_tool_use(
                "TaskUpdate",
                {
                    "taskId": "1",
                    "subject": "Updated subject",
                    "description": "Updated description",
                    "activeForm": "Updating task",
                },
            ),
        ]
        jsonl_file.write_text("\n".join(json.dumps(m) for m in messages))

        tasks = reconstruct_tasks_from_jsonl(jsonl_file)

        assert tasks[0].subject == "Updated subject"
        assert tasks[0].description == "Updated description"
        assert tasks[0].active_form == "Updating task"

    def test_reconstruct_tasks_sorted_by_id(self, tmp_path: Path):
        """Test that reconstructed tasks are sorted by numeric ID."""
        jsonl_file = tmp_path / "many_tasks.jsonl"

        # Create 10 tasks - they'll get IDs 1-10
        messages = [
            self._create_assistant_message_with_tool_use(
                "TaskCreate",
                {"subject": f"Task {i}", "description": f"Desc {i}"},
            )
            for i in range(1, 11)
        ]
        jsonl_file.write_text("\n".join(json.dumps(m) for m in messages))

        tasks = reconstruct_tasks_from_jsonl(jsonl_file)

        assert len(tasks) == 10
        for i, task in enumerate(tasks):
            assert task.id == str(i + 1)
