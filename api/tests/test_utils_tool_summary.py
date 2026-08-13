"""Tests for get_tool_summary()'s text-capping contract (_cap_text)."""

import pytest

from models.content import ToolUseBlock
from utils import _METADATA_TEXT_LIMIT, _cap_text, get_tool_summary


def make_tool_use(name: str, **input_kwargs) -> ToolUseBlock:
    return ToolUseBlock(type="tool_use", id="toolu_test", name=name, input=input_kwargs)


class TestCapText:
    def test_exactly_at_limit_passes_untouched(self):
        value = "x" * _METADATA_TEXT_LIMIT
        assert _cap_text(value) == value

    def test_over_limit_is_capped_with_marker(self):
        value = "x" * 9000
        result = _cap_text(value)
        assert result.startswith("x" * _METADATA_TEXT_LIMIT)
        assert result.endswith("[truncated, 9000 chars total]")
        assert len(result) > _METADATA_TEXT_LIMIT

    def test_under_limit_passes_untouched(self):
        assert _cap_text("short") == "short"


class TestGetToolSummaryEdit:
    def test_edit_carries_path_and_capped_strings(self):
        block = make_tool_use(
            "Edit",
            path="/repo/file.py",
            old_string="a" * 5000,
            new_string="b" * 10,
        )
        _, _, metadata = get_tool_summary(block)
        assert metadata["path"] == "/repo/file.py"
        assert metadata["old_string"].endswith("[truncated, 5000 chars total]")
        assert metadata["new_string"] == "b" * 10

    def test_edit_short_strings_uncapped(self):
        block = make_tool_use("Edit", path="/repo/file.py", old_string="foo", new_string="bar")
        _, _, metadata = get_tool_summary(block)
        assert metadata["old_string"] == "foo"
        assert metadata["new_string"] == "bar"


class TestGetToolSummaryWrite:
    def test_write_content_capped_over_limit(self):
        block = make_tool_use("Write", path="/repo/big.txt", content="c" * 9000)
        _, _, metadata = get_tool_summary(block)
        assert metadata["content"].endswith("[truncated, 9000 chars total]")

    def test_write_content_under_limit_uncapped(self):
        block = make_tool_use("Write", path="/repo/small.txt", content="hello")
        _, _, metadata = get_tool_summary(block)
        assert metadata["content"] == "hello"


class TestGetToolSummaryTask:
    @pytest.mark.parametrize("tool_name", ["Task", "Agent"])
    def test_task_carries_capped_prompt(self, tool_name):
        block = make_tool_use(
            tool_name,
            description="Investigate the bug",
            subagent_type="explore",
            prompt="p" * 9000,
        )
        _, _, metadata = get_tool_summary(block)
        assert metadata["subagent_type"] == "explore"
        assert metadata["prompt"].endswith("[truncated, 9000 chars total]")

    def test_task_short_prompt_uncapped(self):
        block = make_tool_use("Task", description="desc", subagent_type="explore", prompt="find x")
        _, _, metadata = get_tool_summary(block)
        assert metadata["prompt"] == "find x"
