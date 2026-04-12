"""
Unit tests for the JSONL utility functions.

Tests the shared iter_messages_from_jsonl function used by both
Session and Agent models for parsing JSONL message files.
"""

import json
from pathlib import Path
from typing import Any, Dict

from models import AssistantMessage, UserMessage, iter_messages_from_jsonl
from models.jsonl_utils import _merge_user_message_dicts


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
                msg["timestamp"] = f"2026-01-08T13:0{i}:00.000Z"
                msg["message"] = {"role": "user", "content": f"message {i}"}
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


class TestMessageMerging:
    """Tests for _merge_user_message_dicts and the merge logic in iter_messages_from_jsonl."""

    # -------------------------------------------------------------------------
    # Direct unit tests of _merge_user_message_dicts
    # -------------------------------------------------------------------------

    def test_merge_drops_image_source_text_part(self) -> None:
        """Merged result contains the image block and real text, but NOT [Image: source:...] text."""
        base = {
            "type": "user",
            "uuid": "u1",
            "timestamp": "2026-01-08T13:00:00.000Z",
            "message": {
                "role": "user",
                "content": [
                    {"type": "text", "text": "look at this"},
                    {
                        "type": "image",
                        "source": {"type": "base64", "media_type": "image/png", "data": "abc"},
                    },
                ],
            },
        }
        extra = {
            "type": "user",
            "uuid": "u2",
            "timestamp": "2026-01-08T13:00:00.000Z",
            "message": {
                "role": "user",
                "content": [
                    {"type": "text", "text": "[Image: source: /var/folders/abc.png]"},
                ],
            },
        }

        result = _merge_user_message_dicts(base, extra)
        content = result["message"]["content"]

        types_in_result = [p.get("type") for p in content]
        texts_in_result = [p.get("text", "") for p in content if p.get("type") == "text"]

        assert "image" in types_in_result
        assert "look at this" in texts_in_result
        # The [Image: source:...] fallback text must be absent
        assert not any("[Image: source:" in t for t in texts_in_result)

    def test_merge_drops_image_hash_number_marker(self) -> None:
        """
        Merged result drops the v2.1.83+ ``[Image #N]`` marker (including the
        v2.1.85+ trailing-space variant).  Regression guard for the format
        change Claude Code introduced after our initial merge logic shipped.
        """
        base = {
            "type": "user",
            "uuid": "u1",
            "timestamp": "2026-01-08T13:00:00.000Z",
            "message": {
                "role": "user",
                "content": [
                    {"type": "text", "text": "explain this screenshot"},
                    {
                        "type": "image",
                        "source": {"type": "base64", "media_type": "image/png", "data": "abc"},
                    },
                    {
                        "type": "image",
                        "source": {"type": "base64", "media_type": "image/png", "data": "def"},
                    },
                ],
            },
        }
        extra = {
            "type": "user",
            "uuid": "u2",
            "timestamp": "2026-01-08T13:00:00.000Z",
            "message": {
                "role": "user",
                "content": [
                    {"type": "text", "text": "[Image #1]"},
                    {"type": "text", "text": "[Image #2] "},  # v2.1.85+ trailing-space variant
                ],
            },
        }

        result = _merge_user_message_dicts(base, extra)
        content = result["message"]["content"]

        types_in_result = [p.get("type") for p in content]
        texts_in_result = [p.get("text", "") for p in content if p.get("type") == "text"]

        # Both image blocks preserved from base
        assert types_in_result.count("image") == 2
        # Real text from base preserved
        assert "explain this screenshot" in texts_in_result
        # Both [Image #N] markers dropped (with and without trailing space)
        assert not any(t.startswith("[Image #") for t in texts_in_result)

    def test_merge_preserves_real_extra_text(self) -> None:
        """Real text in the extra message is preserved alongside base content."""
        base = {
            "type": "user",
            "uuid": "u1",
            "timestamp": "2026-01-08T13:00:00.000Z",
            "message": {"role": "user", "content": [{"type": "text", "text": "first"}]},
        }
        extra = {
            "type": "user",
            "uuid": "u2",
            "timestamp": "2026-01-08T13:00:00.000Z",
            "message": {"role": "user", "content": [{"type": "text", "text": "second"}]},
        }

        result = _merge_user_message_dicts(base, extra)
        content = result["message"]["content"]
        texts = [p["text"] for p in content if p.get("type") == "text"]

        assert "first" in texts
        assert "second" in texts

    def test_merge_with_empty_extra_returns_base_content(self) -> None:
        """When extra has no content, merged result preserves base content unchanged."""
        base = {
            "type": "user",
            "uuid": "u1",
            "timestamp": "2026-01-08T13:00:00.000Z",
            "message": {"role": "user", "content": [{"type": "text", "text": "only this"}]},
        }
        extra = {
            "type": "user",
            "uuid": "u2",
            "timestamp": "2026-01-08T13:00:00.000Z",
            "message": {"role": "user", "content": []},
        }

        result = _merge_user_message_dicts(base, extra)
        content = result["message"]["content"]

        assert len(content) == 1
        assert content[0]["text"] == "only this"

    def test_merge_handles_legacy_content_key(self) -> None:
        """Merge works for legacy dicts that use top-level 'content' instead of 'message.content'."""
        base = {
            "type": "user",
            "uuid": "u1",
            "timestamp": "2026-01-08T13:00:00.000Z",
            "content": [{"type": "text", "text": "base text"}],
        }
        extra = {
            "type": "user",
            "uuid": "u2",
            "timestamp": "2026-01-08T13:00:00.000Z",
            "content": [{"type": "text", "text": "extra text"}],
        }

        result = _merge_user_message_dicts(base, extra)
        # No nested 'message' key — should fall back to top-level 'content'
        content = result.get("content", [])

        texts = [p["text"] for p in content if p.get("type") == "text"]
        assert "base text" in texts
        assert "extra text" in texts

    # -------------------------------------------------------------------------
    # Integration tests via iter_messages_from_jsonl
    # -------------------------------------------------------------------------

    def _make_user_msg(self, uuid: str, timestamp: str, content_blocks: list) -> Dict[str, Any]:
        return {
            "type": "user",
            "uuid": uuid,
            "timestamp": timestamp,
            "sessionId": "test-session",
            "isSidechain": False,
            "userType": "external",
            "cwd": "/tmp/test",
            "version": "2.1.1",
            "message": {"role": "user", "content": content_blocks},
        }

    def _make_assistant_msg(self, uuid: str, timestamp: str) -> Dict[str, Any]:
        return {
            "type": "assistant",
            "uuid": uuid,
            "timestamp": timestamp,
            "sessionId": "test-session",
            "isSidechain": False,
            "cwd": "/tmp/test",
            "version": "2.1.1",
            "message": {
                "role": "assistant",
                "model": "claude-opus-4-5-20251101",
                "id": "msg_test",
                "type": "message",
                "content": [{"type": "text", "text": "reply"}],
                "stop_reason": "end_turn",
                "usage": {"input_tokens": 10, "output_tokens": 5},
            },
        }

    def test_iter_merges_same_timestamp_user_messages(self, temp_project_dir: Path) -> None:
        """Two user messages at the same timestamp are merged into one UserMessage."""
        ts = "2026-01-08T13:00:00.000Z"
        msg1 = self._make_user_msg(
            "u1",
            ts,
            [
                {"type": "text", "text": "look at this"},
                {
                    "type": "image",
                    "source": {"type": "base64", "media_type": "image/png", "data": "abc"},
                },
            ],
        )
        msg2 = self._make_user_msg(
            "u2",
            ts,
            [
                {"type": "text", "text": "[Image: source: /var/folders/abc.png]"},
            ],
        )

        jsonl_path = temp_project_dir / "merge_test.jsonl"
        with open(jsonl_path, "w") as f:
            f.write(json.dumps(msg1) + "\n")
            f.write(json.dumps(msg2) + "\n")

        messages = list(iter_messages_from_jsonl(jsonl_path))

        assert len(messages) == 1
        assert isinstance(messages[0], UserMessage)
        # Image data should be captured as attachment, and text should not include the [Image: source:] fallback
        assert "[Image: source:" not in messages[0].content

    def test_iter_does_not_merge_different_timestamps(self, temp_project_dir: Path) -> None:
        """User messages with different timestamps yield two separate messages."""
        msg1 = self._make_user_msg(
            "u1",
            "2026-01-08T13:00:00.000Z",
            [
                {"type": "text", "text": "first message"},
            ],
        )
        msg2 = self._make_user_msg(
            "u2",
            "2026-01-08T13:00:01.000Z",
            [
                {"type": "text", "text": "second message"},
            ],
        )

        jsonl_path = temp_project_dir / "no_merge_test.jsonl"
        with open(jsonl_path, "w") as f:
            f.write(json.dumps(msg1) + "\n")
            f.write(json.dumps(msg2) + "\n")

        messages = list(iter_messages_from_jsonl(jsonl_path))

        assert len(messages) == 2
        assert all(isinstance(m, UserMessage) for m in messages)

    def test_iter_does_not_merge_user_and_assistant_with_same_timestamp(
        self, temp_project_dir: Path
    ) -> None:
        """A user and an assistant message sharing the same timestamp are NOT merged."""
        ts = "2026-01-08T13:00:00.000Z"
        user_msg = self._make_user_msg("u1", ts, [{"type": "text", "text": "user text"}])
        asst_msg = self._make_assistant_msg("a1", ts)

        jsonl_path = temp_project_dir / "cross_type_test.jsonl"
        with open(jsonl_path, "w") as f:
            f.write(json.dumps(user_msg) + "\n")
            f.write(json.dumps(asst_msg) + "\n")

        messages = list(iter_messages_from_jsonl(jsonl_path))

        assert len(messages) == 2
        assert isinstance(messages[0], UserMessage)
        assert isinstance(messages[1], AssistantMessage)

    def test_iter_handles_three_consecutive_same_timestamp_user_messages(
        self, temp_project_dir: Path
    ) -> None:
        """Three user messages at the same timestamp are all merged into one."""
        ts = "2026-01-08T13:00:00.000Z"
        msg1 = self._make_user_msg("u1", ts, [{"type": "text", "text": "part one"}])
        msg2 = self._make_user_msg("u2", ts, [{"type": "text", "text": "part two"}])
        msg3 = self._make_user_msg("u3", ts, [{"type": "text", "text": "part three"}])

        jsonl_path = temp_project_dir / "triple_merge_test.jsonl"
        with open(jsonl_path, "w") as f:
            f.write(json.dumps(msg1) + "\n")
            f.write(json.dumps(msg2) + "\n")
            f.write(json.dumps(msg3) + "\n")

        messages = list(iter_messages_from_jsonl(jsonl_path))

        assert len(messages) == 1
        assert isinstance(messages[0], UserMessage)
        # All three text parts should be present in the merged content
        assert "part one" in messages[0].content
        assert "part two" in messages[0].content
        assert "part three" in messages[0].content
