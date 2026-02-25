"""
Unit tests for content block models.

Tests the TextBlock, ThinkingBlock, ToolUseBlock models and the
parse_content_block() function.
"""

from typing import Any, Dict

import pytest

from models import (
    ContentBlock,
    TextBlock,
    ThinkingBlock,
    ToolUseBlock,
    parse_content_block,
)

# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def text_block_data() -> Dict[str, Any]:
    """Sample text block data."""
    return {"type": "text", "text": "Hello, world!"}


@pytest.fixture
def thinking_block_data() -> Dict[str, Any]:
    """Sample thinking block data with signature."""
    return {
        "type": "thinking",
        "thinking": "Let me analyze this problem...",
        "signature": "sig_abc123",
    }


@pytest.fixture
def thinking_block_data_no_signature() -> Dict[str, Any]:
    """Sample thinking block data without signature."""
    return {
        "type": "thinking",
        "thinking": "Thinking without signature...",
    }


@pytest.fixture
def tool_use_block_data() -> Dict[str, Any]:
    """Sample tool_use block data."""
    return {
        "type": "tool_use",
        "id": "toolu_01XYZ123",
        "name": "Read",
        "input": {"file_path": "/path/to/file.py"},
    }


@pytest.fixture
def tool_use_block_data_empty_input() -> Dict[str, Any]:
    """Sample tool_use block data with empty input."""
    return {
        "type": "tool_use",
        "id": "toolu_02ABC456",
        "name": "Bash",
        "input": {},
    }


# =============================================================================
# TextBlock Tests
# =============================================================================


class TestTextBlock:
    """Tests for TextBlock model."""

    def test_instantiation_basic(self):
        """Test basic TextBlock instantiation."""
        block = TextBlock(text="Hello, world!")

        assert block.text == "Hello, world!"
        assert block.type == "text"

    def test_instantiation_from_dict(self, text_block_data: Dict[str, Any]):
        """Test TextBlock instantiation from dictionary."""
        block = TextBlock.model_validate(text_block_data)

        assert block.text == "Hello, world!"
        assert block.type == "text"

    def test_type_literal(self):
        """Test that type is always 'text' literal."""
        block = TextBlock(text="Test")

        assert block.type == "text"
        # Type should be enforced as literal
        assert TextBlock(type="text", text="Test").type == "text"

    def test_text_field_empty_string(self):
        """Test TextBlock with empty text."""
        block = TextBlock(text="")

        assert block.text == ""
        assert block.type == "text"

    def test_text_field_multiline(self):
        """Test TextBlock with multiline text."""
        multiline_text = "Line 1\nLine 2\nLine 3"
        block = TextBlock(text=multiline_text)

        assert block.text == multiline_text
        assert "\n" in block.text

    def test_text_field_unicode(self):
        """Test TextBlock with unicode characters."""
        unicode_text = "Hello, \u4e16\u754c! \U0001f600"
        block = TextBlock(text=unicode_text)

        assert block.text == unicode_text

    def test_immutability(self):
        """Test that TextBlock is frozen (immutable)."""
        block = TextBlock(text="Original")

        with pytest.raises(Exception):  # ValidationError for frozen model
            block.text = "Modified"

    def test_immutability_type_field(self):
        """Test that type field is also immutable."""
        block = TextBlock(text="Test")

        with pytest.raises(Exception):
            block.type = "other"


# =============================================================================
# ThinkingBlock Tests
# =============================================================================


class TestThinkingBlock:
    """Tests for ThinkingBlock model."""

    def test_instantiation_with_signature(self, thinking_block_data: Dict[str, Any]):
        """Test ThinkingBlock instantiation with signature."""
        block = ThinkingBlock.model_validate(thinking_block_data)

        assert block.type == "thinking"
        assert block.thinking == "Let me analyze this problem..."
        assert block.signature == "sig_abc123"

    def test_instantiation_without_signature(
        self, thinking_block_data_no_signature: Dict[str, Any]
    ):
        """Test ThinkingBlock instantiation without signature."""
        block = ThinkingBlock.model_validate(thinking_block_data_no_signature)

        assert block.type == "thinking"
        assert block.thinking == "Thinking without signature..."
        assert block.signature is None

    def test_signature_optional(self):
        """Test that signature is optional."""
        block = ThinkingBlock(thinking="Just thinking...")

        assert block.signature is None
        assert block.thinking == "Just thinking..."

    def test_type_literal(self):
        """Test that type is always 'thinking' literal."""
        block = ThinkingBlock(thinking="Test")

        assert block.type == "thinking"

    def test_thinking_field_empty_string(self):
        """Test ThinkingBlock with empty thinking."""
        block = ThinkingBlock(thinking="")

        assert block.thinking == ""

    def test_thinking_field_long_text(self):
        """Test ThinkingBlock with long thinking text."""
        long_text = "Let me think... " * 1000
        block = ThinkingBlock(thinking=long_text)

        assert block.thinking == long_text

    def test_immutability(self):
        """Test that ThinkingBlock is frozen (immutable)."""
        block = ThinkingBlock(thinking="Original", signature="sig1")

        with pytest.raises(Exception):
            block.thinking = "Modified"

    def test_immutability_signature(self):
        """Test that signature field is also immutable."""
        block = ThinkingBlock(thinking="Test", signature="sig1")

        with pytest.raises(Exception):
            block.signature = "sig2"


# =============================================================================
# ToolUseBlock Tests
# =============================================================================


class TestToolUseBlock:
    """Tests for ToolUseBlock model."""

    def test_instantiation_basic(self, tool_use_block_data: Dict[str, Any]):
        """Test basic ToolUseBlock instantiation."""
        block = ToolUseBlock.model_validate(tool_use_block_data)

        assert block.type == "tool_use"
        assert block.id == "toolu_01XYZ123"
        assert block.name == "Read"
        assert block.input == {"file_path": "/path/to/file.py"}

    def test_instantiation_empty_input(self, tool_use_block_data_empty_input: Dict[str, Any]):
        """Test ToolUseBlock with empty input dict."""
        block = ToolUseBlock.model_validate(tool_use_block_data_empty_input)

        assert block.type == "tool_use"
        assert block.id == "toolu_02ABC456"
        assert block.name == "Bash"
        assert block.input == {}

    def test_type_literal(self):
        """Test that type is always 'tool_use' literal."""
        block = ToolUseBlock(id="toolu_test", name="Test", input={})

        assert block.type == "tool_use"

    def test_id_field(self):
        """Test tool use ID field."""
        block = ToolUseBlock(id="toolu_custom_id", name="Write", input={})

        assert block.id == "toolu_custom_id"

    def test_name_field_various_tools(self):
        """Test various tool names."""
        tools = ["Read", "Write", "Bash", "Glob", "Grep", "Edit", "WebFetch"]

        for tool_name in tools:
            block = ToolUseBlock(id="toolu_test", name=tool_name, input={})
            assert block.name == tool_name

    def test_input_field_complex(self):
        """Test ToolUseBlock with complex input."""
        complex_input = {
            "file_path": "/path/to/file.py",
            "content": "def hello():\n    print('Hello')",
            "options": {"encoding": "utf-8"},
            "nested": {"key": [1, 2, 3]},
        }
        block = ToolUseBlock(id="toolu_test", name="Write", input=complex_input)

        assert block.input == complex_input
        assert block.input["nested"]["key"] == [1, 2, 3]

    def test_input_default_factory(self):
        """Test that input defaults to empty dict."""
        block = ToolUseBlock(id="toolu_test", name="Test")

        assert block.input == {}

    def test_immutability(self):
        """Test that ToolUseBlock is frozen (immutable)."""
        block = ToolUseBlock(id="toolu_test", name="Read", input={"path": "/test"})

        with pytest.raises(Exception):
            block.id = "toolu_other"

    def test_immutability_name(self):
        """Test that name field is immutable."""
        block = ToolUseBlock(id="toolu_test", name="Read", input={})

        with pytest.raises(Exception):
            block.name = "Write"

    def test_immutability_input(self):
        """Test that input field is immutable."""
        block = ToolUseBlock(id="toolu_test", name="Read", input={"key": "value"})

        with pytest.raises(Exception):
            block.input = {"new_key": "new_value"}


# =============================================================================
# parse_content_block() Tests
# =============================================================================


class TestParseContentBlock:
    """Tests for parse_content_block() function."""

    def test_parse_text_block(self, text_block_data: Dict[str, Any]):
        """Test parsing a text block."""
        result = parse_content_block(text_block_data)

        assert isinstance(result, TextBlock)
        assert result.type == "text"
        assert result.text == "Hello, world!"

    def test_parse_thinking_block_with_signature(self, thinking_block_data: Dict[str, Any]):
        """Test parsing a thinking block with signature."""
        result = parse_content_block(thinking_block_data)

        assert isinstance(result, ThinkingBlock)
        assert result.type == "thinking"
        assert result.thinking == "Let me analyze this problem..."
        assert result.signature == "sig_abc123"

    def test_parse_thinking_block_without_signature(
        self, thinking_block_data_no_signature: Dict[str, Any]
    ):
        """Test parsing a thinking block without signature."""
        result = parse_content_block(thinking_block_data_no_signature)

        assert isinstance(result, ThinkingBlock)
        assert result.signature is None

    def test_parse_tool_use_block(self, tool_use_block_data: Dict[str, Any]):
        """Test parsing a tool_use block."""
        result = parse_content_block(tool_use_block_data)

        assert isinstance(result, ToolUseBlock)
        assert result.type == "tool_use"
        assert result.id == "toolu_01XYZ123"
        assert result.name == "Read"
        assert result.input == {"file_path": "/path/to/file.py"}

    def test_parse_unknown_type_raises_valueerror(self):
        """Test that unknown block type raises ValueError."""
        unknown_data = {"type": "unknown_type", "data": "some_data"}

        with pytest.raises(ValueError) as exc_info:
            parse_content_block(unknown_data)

        assert "Unknown content block type: unknown_type" in str(exc_info.value)

    def test_parse_missing_type_raises_valueerror(self):
        """Test that missing type raises ValueError."""
        no_type_data = {"text": "Hello"}

        with pytest.raises(ValueError) as exc_info:
            parse_content_block(no_type_data)

        assert "Unknown content block type: None" in str(exc_info.value)

    def test_parse_none_type_raises_valueerror(self):
        """Test that explicit None type raises ValueError."""
        none_type_data = {"type": None, "text": "Hello"}

        with pytest.raises(ValueError) as exc_info:
            parse_content_block(none_type_data)

        assert "Unknown content block type: None" in str(exc_info.value)

    def test_parse_empty_dict_raises_valueerror(self):
        """Test that empty dict raises ValueError."""
        with pytest.raises(ValueError) as exc_info:
            parse_content_block({})

        assert "Unknown content block type: None" in str(exc_info.value)


# =============================================================================
# ContentBlock Union Type Tests
# =============================================================================


class TestContentBlockUnion:
    """Tests for ContentBlock union type validation."""

    def test_text_block_is_content_block(self):
        """Test that TextBlock is a valid ContentBlock."""
        block: ContentBlock = TextBlock(text="Test")

        assert isinstance(block, TextBlock)

    def test_thinking_block_is_content_block(self):
        """Test that ThinkingBlock is a valid ContentBlock."""
        block: ContentBlock = ThinkingBlock(thinking="Test")

        assert isinstance(block, ThinkingBlock)

    def test_tool_use_block_is_content_block(self):
        """Test that ToolUseBlock is a valid ContentBlock."""
        block: ContentBlock = ToolUseBlock(id="test", name="Test", input={})

        assert isinstance(block, ToolUseBlock)

    def test_parse_returns_content_block_type(
        self,
        text_block_data: Dict[str, Any],
        thinking_block_data: Dict[str, Any],
        tool_use_block_data: Dict[str, Any],
    ):
        """Test that parse_content_block returns valid ContentBlock types."""
        text_block = parse_content_block(text_block_data)
        thinking_block = parse_content_block(thinking_block_data)
        tool_use_block = parse_content_block(tool_use_block_data)

        # All should be instances of their respective types
        assert isinstance(text_block, TextBlock)
        assert isinstance(thinking_block, ThinkingBlock)
        assert isinstance(tool_use_block, ToolUseBlock)

        # All should satisfy ContentBlock union (they all have type field)
        assert hasattr(text_block, "type")
        assert hasattr(thinking_block, "type")
        assert hasattr(tool_use_block, "type")

    def test_content_block_list_mixed_types(
        self,
        text_block_data: Dict[str, Any],
        thinking_block_data: Dict[str, Any],
        tool_use_block_data: Dict[str, Any],
    ):
        """Test parsing a list of mixed content blocks."""
        raw_blocks = [text_block_data, thinking_block_data, tool_use_block_data]

        parsed_blocks = [parse_content_block(b) for b in raw_blocks]

        assert len(parsed_blocks) == 3
        assert isinstance(parsed_blocks[0], TextBlock)
        assert isinstance(parsed_blocks[1], ThinkingBlock)
        assert isinstance(parsed_blocks[2], ToolUseBlock)


# =============================================================================
# Integration with conftest fixtures
# =============================================================================


class TestContentBlockWithConftest:
    """Tests using fixtures from conftest.py."""

    def test_parse_assistant_message_content(self, sample_assistant_message_data: Dict[str, Any]):
        """Test parsing content blocks from sample assistant message."""
        content_list = sample_assistant_message_data["message"]["content"]

        parsed_blocks = [parse_content_block(block) for block in content_list]

        assert len(parsed_blocks) == 3

        # First block is thinking
        assert isinstance(parsed_blocks[0], ThinkingBlock)
        assert parsed_blocks[0].thinking == "Let me analyze this..."
        assert parsed_blocks[0].signature == "sig123"

        # Second block is text
        assert isinstance(parsed_blocks[1], TextBlock)
        assert parsed_blocks[1].text == "I can help you with that."

        # Third block is tool_use
        assert isinstance(parsed_blocks[2], ToolUseBlock)
        assert parsed_blocks[2].id == "toolu_01ABC"
        assert parsed_blocks[2].name == "Read"
        assert parsed_blocks[2].input == {"file_path": "/test/file.py"}


# =============================================================================
# Edge Cases and Error Handling
# =============================================================================


class TestEdgeCases:
    """Edge case tests for content blocks."""

    def test_text_block_with_special_characters(self):
        """Test TextBlock with various special characters."""
        special_text = 'Tab:\tNewline:\nQuote:"Backslash:\\'
        block = TextBlock(text=special_text)

        assert block.text == special_text

    def test_tool_use_with_nested_input(self):
        """Test ToolUseBlock with deeply nested input."""
        deep_input = {"level1": {"level2": {"level3": {"level4": ["a", "b", "c"]}}}}
        block = ToolUseBlock(id="toolu_deep", name="Test", input=deep_input)

        assert block.input["level1"]["level2"]["level3"]["level4"] == ["a", "b", "c"]

    def test_parse_extra_fields_ignored(self):
        """Test that extra fields in input data are handled."""
        data_with_extras = {
            "type": "text",
            "text": "Hello",
            "extra_field": "should be ignored by frozen model",
        }

        # Pydantic by default ignores extra fields unless configured otherwise
        block = parse_content_block(data_with_extras)

        assert isinstance(block, TextBlock)
        assert block.text == "Hello"
        assert not hasattr(block, "extra_field")

    def test_text_block_model_dump(self):
        """Test model serialization for TextBlock."""
        block = TextBlock(text="Hello")
        dumped = block.model_dump()

        assert dumped == {"type": "text", "text": "Hello"}

    def test_thinking_block_model_dump(self):
        """Test model serialization for ThinkingBlock."""
        block = ThinkingBlock(thinking="Thinking...", signature="sig")
        dumped = block.model_dump()

        assert dumped == {
            "type": "thinking",
            "thinking": "Thinking...",
            "signature": "sig",
        }

    def test_tool_use_block_model_dump(self):
        """Test model serialization for ToolUseBlock."""
        block = ToolUseBlock(id="toolu_test", name="Read", input={"path": "/test"})
        dumped = block.model_dump()

        assert dumped == {
            "type": "tool_use",
            "id": "toolu_test",
            "name": "Read",
            "input": {"path": "/test"},
        }

    def test_thinking_block_model_dump_excludes_none(self):
        """Test that ThinkingBlock without signature serializes properly."""
        block = ThinkingBlock(thinking="No sig")
        dumped = block.model_dump()

        # signature should be None in dump
        assert dumped["signature"] is None

        # Can exclude None values
        dumped_no_none = block.model_dump(exclude_none=True)
        assert "signature" not in dumped_no_none
