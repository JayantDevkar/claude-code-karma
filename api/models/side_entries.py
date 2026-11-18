"""
Entries a session JSONL holds beside the conversation: harness notices and queued input.

These are kept out of the Message union and iter_messages so message counts
and every other consumer stay unchanged. The timeline reads them separately.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Iterator, List, Optional, Union

from pydantic import BaseModel, ConfigDict, Field, model_validator

logger = logging.getLogger(__name__)

# System subtypes the timeline shows; stop_hook_summary and turn_duration are noise.
SYSTEM_SUBTYPES = frozenset(
    {
        "away_summary",
        "informational",
        "local_command",
        "scheduled_task_fire",
        "model_refusal_fallback",
        "bridge_status",
    }
)

# Substrings a line must hold to be worth parsing (compact and spaced JSON).
_MARKERS = ('"type":"system"', '"type": "system"', '"queued_command"')


class SystemEntry(BaseModel):
    """A `type: system` entry: something the harness told the user."""

    model_config = ConfigDict(frozen=True, populate_by_name=True)

    uuid: str = ""
    timestamp: datetime
    subtype: str
    content: str = ""
    level: Optional[str] = None
    url: Optional[str] = None
    command_name: Optional[str] = Field(default=None, description="commandRun.command")
    command_args: Optional[str] = Field(default=None, description="commandRun.args")
    task_id: Optional[str] = Field(default=None, alias="taskId")
    cron: Optional[str] = None
    prompt: Optional[str] = None
    original_model: Optional[str] = Field(default=None, alias="originalModel")
    fallback_model: Optional[str] = Field(default=None, alias="fallbackModel")

    @model_validator(mode="before")
    @classmethod
    def _flatten(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data
        result = dict(data)
        if not isinstance(result.get("content"), str):
            result["content"] = ""
        run = data.get("commandRun")
        if isinstance(run, dict):
            result.setdefault("command_name", run.get("command"))
            result.setdefault("command_args", run.get("args"))
        return result


class QueuedCommandEntry(BaseModel):
    """A `queued_command` attachment: input delivered while Claude was working."""

    model_config = ConfigDict(frozen=True, populate_by_name=True)

    uuid: str = ""
    timestamp: datetime
    prompt: str = ""
    command_mode: Optional[str] = None
    origin_kind: Optional[str] = None
    origin_name: Optional[str] = None
    origin_from: Optional[str] = None
    origin_sender_task_id: Optional[str] = None
    origin_relayed: bool = False
    is_meta: bool = False
    image_attachments: List[dict] = Field(default_factory=list)

    @model_validator(mode="before")
    @classmethod
    def _flatten(cls, data: Any) -> Any:
        if not isinstance(data, dict) or "attachment" not in data:
            return data
        attachment = data.get("attachment")
        if not isinstance(attachment, dict):
            attachment = {}
        origin = attachment.get("origin") if isinstance(attachment.get("origin"), dict) else {}
        prompt = attachment.get("prompt")
        images: list[dict] = []
        if isinstance(prompt, list):
            texts = []
            for part in prompt:
                if not isinstance(part, dict):
                    continue
                source = part.get("source") if isinstance(part.get("source"), dict) else {}
                if part.get("type") == "image" and source.get("type") == "base64":
                    images.append(
                        {
                            "media_type": source.get("media_type", "image/png"),
                            "data": source.get("data", ""),
                        }
                    )
                elif isinstance(part.get("text"), str):
                    texts.append(part["text"])
            prompt = "\n".join(texts)
        return {
            "uuid": data.get("uuid") or "",
            "timestamp": _first_str(data.get("timestamp"), attachment.get("timestamp")),
            "prompt": prompt if isinstance(prompt, str) else "",
            "command_mode": _first_str(attachment.get("commandMode")),
            "origin_kind": _first_str(origin.get("kind")),
            "origin_name": _first_str(origin.get("name")),
            "origin_from": _first_str(origin.get("from")),
            "origin_sender_task_id": _first_str(origin.get("senderTaskId")),
            "origin_relayed": bool(origin.get("hopChain")),
            "is_meta": bool(attachment.get("isMeta")),
            "image_attachments": images,
        }


def _first_str(*values: Any) -> Optional[str]:
    """The first non-empty string among the values; other types are ignored."""
    return next((v for v in values if isinstance(v, str) and v), None)


SideEntry = Union[SystemEntry, QueuedCommandEntry]


def parse_side_entry(data: dict) -> Optional[SideEntry]:
    """Parse one raw JSONL dict into a side entry, or None if it is not one or is malformed."""
    entry_type = data.get("type")
    try:
        if entry_type == "system" and data.get("subtype") in SYSTEM_SUBTYPES:
            return SystemEntry.model_validate(data)
        if entry_type == "attachment":
            attachment = data.get("attachment")
            if isinstance(attachment, dict) and attachment.get("type") == "queued_command":
                return QueuedCommandEntry.model_validate(data)
    except Exception:  # noqa: BLE001 - one malformed entry must not fail the whole timeline
        logger.debug("Skipping malformed %s entry", entry_type, exc_info=True)
    return None


def read_session_name(jsonl_path: Path) -> Optional[str]:
    """The name a session was given (its latest `agent-name` entry), or None if it has none."""
    name = None
    try:
        with open(jsonl_path, "r", encoding="utf-8", errors="replace") as f:
            for line in f:
                if '"agent-name"' not in line:
                    continue
                try:
                    data = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if isinstance(data, dict) and data.get("type") == "agent-name":
                    name = _first_str(data.get("agentName")) or name
    except OSError:
        return None
    return name


def iter_side_entries(jsonl_path: Path) -> Iterator[SideEntry]:
    """Yield the system notices and queued commands of a session or agent JSONL, in file order."""
    if not jsonl_path.exists():
        return
    with open(jsonl_path, "r", encoding="utf-8", errors="replace") as f:
        for line in f:
            # Cheap prefilter; the top-level type is checked after parsing.
            if not any(marker in line for marker in _MARKERS):
                continue
            try:
                data = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not isinstance(data, dict):
                continue
            entry = parse_side_entry(data)
            if entry is not None:
                yield entry
