"""
Text parsers for the wrappers Claude Code puts around non-human input.

The sender of an entry comes from its structured fields (see models/message.py).
These helpers only pull the body and attributes out of the wrapper text.
"""

from __future__ import annotations

import html
import json
import re
from dataclasses import dataclass
from typing import Optional

_WRAPPER_RE = re.compile(
    r"<(cross-session-message|agent-message|teammate-message)\b([^>]*)>\n?(.*?)\n?(?:</\1>|\Z)",
    re.DOTALL,
)
_ATTR_RE = re.compile(r'([\w-]+)="([^"]*)"')
_PREAMBLE_RE = re.compile(r"\s*(?:Another Claude session sent a message[^\n]*\n)?\s*")
_SPACE_RE = re.compile(r"\s*")
_COORDINATOR_RE = re.compile(r"\s*The coordinator sent a message[^\n]*\n?")
_TAG_STRIP_RE = re.compile(r"</?[\w-]+(?:\s[^>]*)?>")


@dataclass(frozen=True)
class WrappedMessage:
    """A message from another session or agent, without its wrapper."""

    body: str
    wrapper: Optional[str] = None  # tag name, "coordinator", or None when unwrapped
    sender_name: Optional[str] = None
    sender_address: Optional[str] = None
    summary: Optional[str] = None
    color: Optional[str] = None


def _wrapped(tag: str, attr_text: str, body: str) -> WrappedMessage:
    attrs = dict(_ATTR_RE.findall(attr_text))
    if tag == "cross-session-message":
        return WrappedMessage(
            body=body.strip(),
            wrapper=tag,
            sender_name=attrs.get("from-name") or None,
            sender_address=attrs.get("from") or None,
        )
    return WrappedMessage(
        body=body.strip(),
        wrapper=tag,
        sender_name=attrs.get("from") or attrs.get("teammate_id") or None,
        summary=attrs.get("summary") or None,
        color=attrs.get("color") or None,
    )


def parse_wrapped_messages(content: str) -> list[WrappedMessage]:
    """Split an entry into the messages it carries; one entry can hold several teammates' messages."""
    # A wrapper counts only where the entry starts with it: prose may mention these tags too
    position = _PREAMBLE_RE.match(content).end()
    messages: list[WrappedMessage] = []
    last = None
    while True:
        match = _WRAPPER_RE.match(content, position)
        if match is None:
            break
        messages.append(_wrapped(match.group(1), match.group(2), match.group(3)))
        last = match
        position = _SPACE_RE.match(content, match.end()).end()
    if last is not None and position < len(content):
        # Text is left over: the body itself mentions a closing tag, so take it up to the last one
        tag, start = last.group(1), last.start(3)
        end = content.rfind(f"</{tag}>")
        body = content[start:end] if end > start else content[start:]
        messages[-1] = _wrapped(tag, last.group(2), body)
    if messages:
        return messages
    coordinator = _COORDINATOR_RE.match(content)
    if coordinator:
        body = content[coordinator.end() :].strip()
        return [WrappedMessage(body=body, wrapper="coordinator", sender_name="coordinator")]
    return [WrappedMessage(body=content.strip())]


def parse_idle_signal(body: str) -> Optional[dict]:
    """A teammate's idle_notification, or None for anything else (other JSON stays a message)."""
    if not body.startswith("{"):
        return None
    try:
        data = json.loads(body)
    except ValueError:
        return None
    if isinstance(data, dict) and data.get("type") == "idle_notification":
        return data
    return None


@dataclass(frozen=True)
class TaskNotification:
    """Fields of a <task-notification> block."""

    task_id: Optional[str] = None
    tool_use_id: Optional[str] = None
    output_file: Optional[str] = None
    status: Optional[str] = None
    summary: Optional[str] = None
    result: Optional[str] = None
    event: Optional[str] = None

    @property
    def kind(self) -> Optional[str]:
        """What kind of background task reported: from the summary, else the task id prefix."""
        summary = self.summary or ""
        for prefix, kind in _SUMMARY_KINDS:
            if summary.startswith(prefix):
                return kind
        return _ID_PREFIX_KINDS.get((self.task_id or "")[:1])


_SUMMARY_KINDS = (
    ("Agent ", "agent"),
    ("Background ", "shell"),
    ("Monitor ", "monitor"),
    ("Dynamic workflow", "workflow"),
    ("MCP task", "mcp"),
)
_ID_PREFIX_KINDS = {"a": "agent", "b": "shell", "w": "workflow", "k": "mcp"}


def _tag(content: str, name: str, greedy: bool = False) -> Optional[str]:
    body = ".*" if greedy else ".*?"
    match = re.search(rf"<{name}>({body})</{name}>", content, re.DOTALL)
    return match.group(1).strip() if match else None


def parse_task_notification(content: str) -> TaskNotification:
    """Read the fields of a <task-notification> block (also the plain-text preamble form)."""
    return TaskNotification(
        task_id=_tag(content, "task-id"),
        tool_use_id=_tag(content, "tool-use-id"),
        output_file=_tag(content, "output-file"),
        status=_tag(content, "status"),
        summary=_tag(content, "summary"),
        result=_tag(content, "result", greedy=True),
        event=_tag(content, "event", greedy=True),
    )


def parse_shell_input(content: str) -> Optional[str]:
    """The command of a `! cmd` entry, or None when the entry holds no <bash-input>."""
    command = _tag(content, "bash-input")
    return html.unescape(command) if command is not None else None


def parse_shell_output(content: str) -> tuple[Optional[str], Optional[str]]:
    """(stdout, stderr) of a `! cmd` entry; None for a stream the entry does not hold."""
    stdout, stderr = _tag(content, "bash-stdout", True), _tag(content, "bash-stderr", True)
    return (
        html.unescape(stdout) if stdout is not None else None,
        html.unescape(stderr) if stderr is not None else None,
    )


def parse_local_command_output(content: str) -> Optional[str]:
    """Combined stdout/stderr of a slash command, or None when the text holds neither."""
    parts = [
        _tag(content, "local-command-stdout", True),
        _tag(content, "local-command-stderr", True),
    ]
    if all(part is None for part in parts):
        return None
    return "\n".join(part for part in parts if part)


# Wrappers that carry no meaning when a prompt is shown as plain text.
_FORK_BOILERPLATE_RE = re.compile(r"<fork-boilerplate>.*?</fork-boilerplate>", re.DOTALL)
_PASTED_TAG_RE = re.compile(r"</?pasted_content\b[^>]*>")


def strip_prompt_wrappers(text: str) -> str:
    """Drop paste tags and a fork's boilerplate block; the prompt text itself is kept."""
    return _PASTED_TAG_RE.sub("", _FORK_BOILERPLATE_RE.sub("", text)).strip()


def clean_task_prompt(text: str) -> str:
    """A subagent's task as plain text: no teammate-message wrapper, no fork boilerplate."""
    parts = parse_wrapped_messages(text)
    if parts[0].wrapper:
        text = "\n\n".join(part.body for part in parts)
    return strip_prompt_wrappers(text)


def strip_tags(content: str) -> str:
    """Drop XML-like tags for a one-line preview."""
    return _TAG_STRIP_RE.sub("", content).strip()
