"""
Unit tests for TodoItem model and load_todos_from_file function.

Tests cover:
- TodoItem instantiation with all status values
- Field alias "activeForm" -> active_form
- Optional active_form field
- Immutability (frozen=True)
- load_todos_from_file() functionality and edge cases
"""

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from models import TodoItem, load_todos_from_file


class TestTodoItemInstantiation:
    """Tests for TodoItem instantiation with various status values."""

    def test_instantiation_with_pending_status(self):
        """Test TodoItem with pending status."""
        todo = TodoItem(content="Write documentation", status="pending")
        assert todo.content == "Write documentation"
        assert todo.status == "pending"

    def test_instantiation_with_in_progress_status(self):
        """Test TodoItem with in_progress status."""
        todo = TodoItem(content="Implement feature", status="in_progress")
        assert todo.content == "Implement feature"
        assert todo.status == "in_progress"

    def test_instantiation_with_completed_status(self):
        """Test TodoItem with completed status."""
        todo = TodoItem(content="Fix bug", status="completed")
        assert todo.content == "Fix bug"
        assert todo.status == "completed"

    def test_default_status_is_pending(self):
        """Test that status defaults to pending when not provided."""
        todo = TodoItem(content="New task")
        assert todo.status == "pending"

    def test_invalid_status_raises_validation_error(self):
        """Test that invalid status value raises ValidationError."""
        with pytest.raises(ValidationError):
            TodoItem(content="Invalid task", status="invalid_status")


class TestTodoItemFieldAlias:
    """Tests for the activeForm -> active_form field alias."""

    def test_active_form_alias_on_instantiation(self):
        """Test that activeForm alias works during instantiation."""
        todo = TodoItem(content="Test task", status="in_progress", activeForm="Testing task")
        assert todo.active_form == "Testing task"

    def test_active_form_direct_field_name(self):
        """Test that active_form field name also works."""
        todo = TodoItem(content="Test task", status="completed", active_form="Testing task")
        assert todo.active_form == "Testing task"

    def test_model_validate_with_alias(self):
        """Test model_validate with activeForm alias in dict."""
        data = {"content": "Validate task", "status": "pending", "activeForm": "Validating task"}
        todo = TodoItem.model_validate(data)
        assert todo.active_form == "Validating task"

    def test_model_dump_with_alias(self):
        """Test that model_dump can output with alias."""
        todo = TodoItem(content="Dump task", status="completed", active_form="Dumping task")
        # by_alias=True should use activeForm in output
        dumped = todo.model_dump(by_alias=True)
        assert "activeForm" in dumped
        assert dumped["activeForm"] == "Dumping task"


class TestTodoItemOptionalActiveForm:
    """Tests for optional active_form field."""

    def test_active_form_defaults_to_none(self):
        """Test that active_form defaults to None when not provided."""
        todo = TodoItem(content="Simple task", status="pending")
        assert todo.active_form is None

    def test_active_form_can_be_none_explicitly(self):
        """Test that active_form can be explicitly set to None."""
        todo = TodoItem(content="Task", status="pending", active_form=None)
        assert todo.active_form is None

    def test_active_form_with_value(self):
        """Test that active_form accepts string value."""
        todo = TodoItem(content="Write tests", status="in_progress", active_form="Writing tests")
        assert todo.active_form == "Writing tests"


class TestTodoItemImmutability:
    """Tests for TodoItem immutability (frozen=True)."""

    def test_cannot_modify_content(self):
        """Test that content field cannot be modified after creation."""
        todo = TodoItem(content="Original content", status="pending")
        with pytest.raises(ValidationError):
            todo.content = "Modified content"

    def test_cannot_modify_status(self):
        """Test that status field cannot be modified after creation."""
        todo = TodoItem(content="Task", status="pending")
        with pytest.raises(ValidationError):
            todo.status = "completed"

    def test_cannot_modify_active_form(self):
        """Test that active_form field cannot be modified after creation."""
        todo = TodoItem(content="Task", status="in_progress", active_form="Working on task")
        with pytest.raises(ValidationError):
            todo.active_form = "Different form"

    def test_todo_is_hashable(self):
        """Test that frozen TodoItem can be used in sets/dicts."""
        todo1 = TodoItem(content="Task 1", status="pending")
        todo2 = TodoItem(content="Task 2", status="completed")
        # Frozen models should be hashable
        todo_set = {todo1, todo2}
        assert len(todo_set) == 2


class TestLoadTodosFromFileValid:
    """Tests for load_todos_from_file with valid JSON files."""

    def test_load_valid_todos_file(self, sample_todos_file: Path, sample_todo_data: list):
        """Test loading a valid todos JSON file."""
        todos = load_todos_from_file(sample_todos_file)

        assert len(todos) == 3
        assert all(isinstance(todo, TodoItem) for todo in todos)

        # Check first todo (completed)
        assert todos[0].content == "Explore codebase structure"
        assert todos[0].status == "completed"
        assert todos[0].active_form == "Exploring codebase"

        # Check second todo (in_progress)
        assert todos[1].content == "Initialize feature"
        assert todos[1].status == "in_progress"
        assert todos[1].active_form == "Initializing feature"

        # Check third todo (pending)
        assert todos[2].content == "Write tests"
        assert todos[2].status == "pending"
        assert todos[2].active_form == "Writing tests"

    def test_load_todos_with_minimal_data(self, tmp_path: Path):
        """Test loading todos with only required fields."""
        todo_file = tmp_path / "minimal_todos.json"
        minimal_data = [{"content": "Task 1"}, {"content": "Task 2", "status": "completed"}]
        todo_file.write_text(json.dumps(minimal_data))

        todos = load_todos_from_file(todo_file)

        assert len(todos) == 2
        assert todos[0].content == "Task 1"
        assert todos[0].status == "pending"  # default
        assert todos[0].active_form is None  # default
        assert todos[1].status == "completed"


class TestLoadTodosFromFileEmpty:
    """Tests for load_todos_from_file with empty array."""

    def test_load_empty_array(self, tmp_path: Path):
        """Test loading a JSON file with empty array."""
        empty_file = tmp_path / "empty_todos.json"
        empty_file.write_text("[]")

        todos = load_todos_from_file(empty_file)

        assert todos == []
        assert isinstance(todos, list)


class TestLoadTodosFromFileNotFound:
    """Tests for load_todos_from_file with FileNotFoundError."""

    def test_file_not_found_raises_error(self, tmp_path: Path):
        """Test that FileNotFoundError is raised for missing file."""
        nonexistent_path = tmp_path / "nonexistent_todos.json"

        with pytest.raises(FileNotFoundError):
            load_todos_from_file(nonexistent_path)

    def test_file_not_found_error_message(self, tmp_path: Path):
        """Test FileNotFoundError contains useful information."""
        nonexistent_path = tmp_path / "missing.json"

        with pytest.raises(FileNotFoundError) as exc_info:
            load_todos_from_file(nonexistent_path)

        # Error should reference the file path
        assert "missing.json" in str(exc_info.value) or str(nonexistent_path) in str(exc_info.value)


class TestLoadTodosFromFileNonList:
    """Tests for load_todos_from_file with non-list JSON."""

    def test_non_list_json_returns_empty_list(self, tmp_path: Path):
        """Test that non-list JSON returns empty list."""
        non_list_file = tmp_path / "non_list.json"
        non_list_file.write_text('{"key": "value"}')

        todos = load_todos_from_file(non_list_file)

        assert todos == []

    def test_string_json_returns_empty_list(self, tmp_path: Path):
        """Test that string JSON returns empty list."""
        string_file = tmp_path / "string.json"
        string_file.write_text('"just a string"')

        todos = load_todos_from_file(string_file)

        assert todos == []

    def test_number_json_returns_empty_list(self, tmp_path: Path):
        """Test that number JSON returns empty list."""
        number_file = tmp_path / "number.json"
        number_file.write_text("42")

        todos = load_todos_from_file(number_file)

        assert todos == []

    def test_null_json_returns_empty_list(self, tmp_path: Path):
        """Test that null JSON returns empty list."""
        null_file = tmp_path / "null.json"
        null_file.write_text("null")

        todos = load_todos_from_file(null_file)

        assert todos == []

    def test_boolean_json_returns_empty_list(self, tmp_path: Path):
        """Test that boolean JSON returns empty list."""
        bool_file = tmp_path / "bool.json"
        bool_file.write_text("true")

        todos = load_todos_from_file(bool_file)

        assert todos == []


class TestLoadTodosFromFileInvalidJson:
    """Tests for load_todos_from_file with invalid JSON."""

    def test_invalid_json_raises_decode_error(self, tmp_path: Path):
        """Test that invalid JSON raises JSONDecodeError."""
        invalid_file = tmp_path / "invalid.json"
        invalid_file.write_text("not valid json {")

        with pytest.raises(json.JSONDecodeError):
            load_todos_from_file(invalid_file)

    def test_empty_file_raises_decode_error(self, tmp_path: Path):
        """Test that empty file raises JSONDecodeError."""
        empty_file = tmp_path / "empty.json"
        empty_file.write_text("")

        with pytest.raises(json.JSONDecodeError):
            load_todos_from_file(empty_file)
