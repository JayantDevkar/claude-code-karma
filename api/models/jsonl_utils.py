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


def iter_messages_from_jsonl(jsonl_path: Path) -> Iterator[Message]:
    """
    Iterate over messages in a JSONL file.

    Reads the file line by line, parsing each line as JSON and yielding
    parsed Message instances. Handles missing files, empty lines, and
    malformed JSON gracefully.

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

    with open(jsonl_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                data = json.loads(line)
                yield parse_message(data)
            except (json.JSONDecodeError, ValueError, KeyError):
                # Skip malformed lines
                continue
