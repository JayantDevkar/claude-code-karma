"""
Unit tests for the JSONL utility functions.

Tests the shared iter_messages_from_jsonl function used by both
Session and Agent models for parsing JSONL message files.
"""

import json
from pathlib import Path
from typing import Any, Dict

from models import AssistantMessage, UserMessage, iter_messages_from_jsonl


class TestIterMessagesFromJsonl:
    """Tests for iter_messages_from_jsonl utility function."""

    def test_yields_messages_from_valid_jsonl(
        self, temp_project_dir: Path, sample_user_message_data: Dict[str, Any]
    ) -> None:
        """Test that valid JSONL lines yield Message instances."""
        jsonl_path = temp_project_dir / "test.jsonl"
        with open(jsonl_path, "w") as f:
            f.write(json.dumps(sample_user_message_data) + "\n")

        messages = list(iter_messages_from_jsonl(jsonl_path))

        assert len(messages) == 1
        assert isinstance(messages[0], UserMessage)
        assert messages[0].content == "Help me understand this code"

    def test_handles_multiple_messages(
        self,
        temp_project_dir: Path,
        sample_user_message_data: Dict[str, Any],
        sample_assistant_message_data: Dict[str, Any],
    ) -> None:
        """Test parsing multiple messages from a JSONL file."""
        jsonl_path = temp_project_dir / "test.jsonl"
        with open(jsonl_path, "w") as f:
            f.write(json.dumps(sample_user_message_data) + "\n")
            f.write(json.dumps(sample_assistant_message_data) + "\n")

        messages = list(iter_messages_from_jsonl(jsonl_path))

        assert len(messages) == 2
        assert isinstance(messages[0], UserMessage)
        assert isinstance(messages[1], AssistantMessage)

    def test_returns_empty_iterator_for_nonexistent_file(self, temp_project_dir: Path) -> None:
        """Test that non-existent file returns empty iterator."""
        nonexistent_path = temp_project_dir / "nonexistent.jsonl"

        messages = list(iter_messages_from_jsonl(nonexistent_path))

        assert messages == []

    def test_skips_empty_lines(
        self, temp_project_dir: Path, sample_user_message_data: Dict[str, Any]
    ) -> None:
        """Test that empty lines are skipped."""
        jsonl_path = temp_project_dir / "test.jsonl"
        with open(jsonl_path, "w") as f:
            f.write("\n")
            f.write(json.dumps(sample_user_message_data) + "\n")
            f.write("   \n")  # Whitespace-only line
            f.write("\n")

        messages = list(iter_messages_from_jsonl(jsonl_path))

        assert len(messages) == 1

    def test_skips_malformed_json(
        self, temp_project_dir: Path, sample_user_message_data: Dict[str, Any]
    ) -> None:
        """Test that malformed JSON lines are skipped."""
        jsonl_path = temp_project_dir / "test.jsonl"
        with open(jsonl_path, "w") as f:
            f.write("not valid json\n")
            f.write(json.dumps(sample_user_message_data) + "\n")
            f.write('{"incomplete": }\n')

        messages = list(iter_messages_from_jsonl(jsonl_path))

        assert len(messages) == 1
        assert isinstance(messages[0], UserMessage)

    def test_skips_invalid_message_structure(
        self, temp_project_dir: Path, sample_user_message_data: Dict[str, Any]
    ) -> None:
        """Test that lines with valid JSON but invalid message structure are skipped."""
        jsonl_path = temp_project_dir / "test.jsonl"
        with open(jsonl_path, "w") as f:
            f.write('{"some": "data"}\n')  # Valid JSON, invalid message
            f.write(json.dumps(sample_user_message_data) + "\n")

        messages = list(iter_messages_from_jsonl(jsonl_path))

        assert len(messages) == 1
        assert isinstance(messages[0], UserMessage)

    def test_preserves_message_order(
        self, temp_project_dir: Path, sample_user_message_data: Dict[str, Any]
    ) -> None:
        """Test that messages are yielded in file order."""
        jsonl_path = temp_project_dir / "test.jsonl"
        with open(jsonl_path, "w") as f:
            for i in range(5):
                msg = sample_user_message_data.copy()
                msg["uuid"] = f"uuid-{i}"
                msg["message"]["content"] = f"message {i}"
                f.write(json.dumps(msg) + "\n")

        messages = list(iter_messages_from_jsonl(jsonl_path))

        assert len(messages) == 5
        for i, msg in enumerate(messages):
            assert msg.content == f"message {i}"

    def test_handles_empty_file(self, temp_project_dir: Path) -> None:
        """Test that empty file returns empty iterator."""
        jsonl_path = temp_project_dir / "empty.jsonl"
        jsonl_path.touch()

        messages = list(iter_messages_from_jsonl(jsonl_path))

        assert messages == []

    def test_is_a_generator(
        self, temp_project_dir: Path, sample_user_message_data: Dict[str, Any]
    ) -> None:
        """Test that the function returns a generator (lazy iteration)."""
        jsonl_path = temp_project_dir / "test.jsonl"
        with open(jsonl_path, "w") as f:
            f.write(json.dumps(sample_user_message_data) + "\n")

        result = iter_messages_from_jsonl(jsonl_path)

        # Should be a generator, not a list
        import types

        assert isinstance(result, types.GeneratorType)
