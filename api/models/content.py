"""
Content block models for Claude Code assistant message content.

Assistant messages contain a list of content blocks which can be:
- TextBlock: Plain text responses
- ThinkingBlock: Extended thinking content (with signature)
- ToolUseBlock: Tool invocation requests
"""

from __future__ import annotations

from typing import Any, Dict, Literal, Optional, Union

from pydantic import BaseModel, ConfigDict, Field


class TextBlock(BaseModel):
    """Plain text content block."""

    model_config = ConfigDict(frozen=True)

    type: Literal["text"] = "text"
    text: str


class ThinkingBlock(BaseModel):
    """Extended thinking content block."""

    model_config = ConfigDict(frozen=True)

    type: Literal["thinking"] = "thinking"
    thinking: str
    signature: Optional[str] = None


class ToolUseBlock(BaseModel):
    """Tool invocation request block."""

    model_config = ConfigDict(frozen=True)

    type: Literal["tool_use"] = "tool_use"
    id: str = Field(..., description="Tool use ID (e.g., toolu_xxx)")
    name: str = Field(..., description="Tool name (Read, Write, Shell, etc.)")
    input: Dict[str, Any] = Field(default_factory=dict)


# Discriminated union for parsing content blocks
ContentBlock = Union[TextBlock, ThinkingBlock, ToolUseBlock]


def parse_content_block(data: Dict[str, Any]) -> ContentBlock:
    """
    Parse a raw content block dict into the appropriate typed model.

    Args:
        data: Raw dict from JSONL content array

    Returns:
        Typed ContentBlock instance

    Raises:
        ValueError: If block type is unknown
    """
    block_type = data.get("type")
    if block_type == "text":
        return TextBlock.model_validate(data)
    if block_type == "thinking":
        return ThinkingBlock.model_validate(data)
    if block_type == "tool_use":
        return ToolUseBlock.model_validate(data)
    raise ValueError(f"Unknown content block type: {block_type}")
