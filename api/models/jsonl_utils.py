"""
Utility functions for parsing JSONL message files.

This module provides shared functionality for reading and parsing
JSONL files containing Claude Code messages. Used by both Session
and Agent models to avoid code duplication.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Iterator

from .message import Message, parse_message


def _is_image_marker_text(text: str) -> bool:
    """
    Detect a text block that is an image-attachment marker Claude Code emits
    alongside the real image content block.

    Two formats are observed across Claude Code versions:

    - Pre-v2.1.83: ``[Image: source: /var/folders/...]``
    - v2.1.83+:    ``[Image #N]`` (may have a trailing space in v2.1.85+)

    Both are redundant because the actual image data is already present in a
    sibling ``image`` content block and should be dropped during merge.
    """
    if not isinstance(text, str):
        return False
    return text.startswith("[Image: source:") or text.startswith("[Image #")


def _merge_user_message_dicts(base: dict, extra: dict) -> dict:
    """
    Merge two raw user message dicts that share the same timestamp.

    Claude Code emits a pair of user messages at the same timestamp when
    an image is attached: the first contains the real text + base64 image
    block, and the second is a text-only fallback with a marker reference
    like ``[Image: source: /var/folders/...]`` (pre-v2.1.83) or
    ``[Image #N]`` (v2.1.83+).  We merge both into one dict so the
    downstream parser sees a single message with the correct content
    and image attachment.

    The marker reference parts are dropped because the image data is
    already present in the base message's image content block.  Any other
    real text in the extra message is preserved.
    """
    merged = {**base}

    def _get_content(d: dict) -> list:
        c = d.get("message", {}).get("content") or d.get("content", [])
        return c if isinstance(c, list) else []

    base_content = _get_content(merged)
    extra_content = _get_content(extra)

    # Keep extra parts that are not redundant image-marker text references
    real_extra = [
        part
        for part in extra_content
        if not (
            isinstance(part, dict)
            and part.get("type") == "text"
            and _is_image_marker_text(part.get("text", ""))
        )
    ]

    if real_extra:
        combined = base_content + real_extra
        if "message" in merged:
            merged["message"] = {**merged["message"], "content": combined}
        else:
            merged["content"] = combined

    return merged


def iter_messages_from_jsonl(jsonl_path: Path) -> Iterator[Message]:
    """
    Iterate over messages in a JSONL file.

    Reads the file line by line, parsing each line as JSON and yielding
    parsed Message instances. Handles missing files, empty lines, and
    malformed JSON gracefully.

    Consecutive user messages that share an identical timestamp are merged
    into a single message before parsing.  Claude Code writes such pairs
    when the user attaches an image: one entry with the real text + base64
    image block and a second text-only entry with a file-path reference.

    Args:
        jsonl_path: Path to the JSONL file containing messages.

    Yields:
        Message instances (UserMessage, AssistantMessage, FileHistorySnapshot, etc.)

    Note:
        - Returns an empty iterator if the file doesn't exist
        - Skips empty lines and whitespace-only lines
        - Skips malformed JSON lines (logs no errors)
        - Skips lines that fail message parsing (invalid structure)
    """
    if not jsonl_path.exists():
        return

    pending: dict | None = None

    with open(jsonl_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                data = json.loads(line)
            except json.JSONDecodeError:
                continue

            # Merge consecutive user messages with the same timestamp into one
            if (
                pending is not None
                and pending.get("type") == "user"
                and data.get("type") == "user"
                and pending.get("timestamp") == data.get("timestamp")
            ):
                pending = _merge_user_message_dicts(pending, data)
                continue

            # Yield the previously buffered message
            if pending is not None:
                try:
                    yield parse_message(pending)
                except (ValueError, KeyError):
                    pass

            pending = data

    # Yield the final buffered message
    if pending is not None:
        try:
            yield parse_message(pending)
        except (ValueError, KeyError):
            pass
