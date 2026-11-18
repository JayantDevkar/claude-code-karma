"""
Shared conversation endpoint services for Session and Agent.

Phase 3 DRY refactor: Consolidates nearly identical timeline, tools, and
file-activity endpoint logic that was duplicated across routers/sessions.py
and routers/subagent_sessions.py (~400 lines reduced).

These functions work with any ConversationEntity (Session or Agent) via
the protocol in models/conversation.py.
"""

import re
from collections import Counter
from dataclasses import dataclass, field, replace
from datetime import datetime
from typing import Optional

from collectors import resolve_subagent_type
from command_helpers import (
    classify_invocation,
    detect_slash_commands_in_text,
    expand_plugin_short_name,
    is_command_category,
    is_plugin_skill,
    is_skill_category,
    parse_command_from_content,
    strip_command_tags,
)
from models import AssistantMessage, ConversationEntity, ToolUseBlock, UserMessage
from models.api_error import ApiErrorTracker
from models.content import TextBlock, ThinkingBlock
from models.conversation import is_session
from models.message import CompactBoundaryMessage, classify_user_source
from models.side_entries import QueuedCommandEntry, SystemEntry, iter_side_entries
from schemas import FileActivity, TimelineEvent, ToolUsageSummary
from services.agent_registry import AgentInfo, AgentRegistry
from services.timeline_parsing import (
    WrappedMessage,
    parse_idle_signal,
    parse_local_command_output,
    parse_shell_input,
    parse_shell_output,
    parse_task_notification,
    parse_wrapped_messages,
    strip_prompt_wrappers,
    strip_tags,
)
from utils import (
    FileOperation,
    ToolResultData,
    collect_tool_results,
    get_tool_summary,
)

# =============================================================================
# Timeline Generation
# =============================================================================

# Bump when the event shape changes, so browsers drop timelines cached in the old shape.
TIMELINE_FORMAT_VERSION = "3"


def timeline_etag(file_etag: Optional[str]) -> Optional[str]:
    """The file-based ETag, tied to the timeline format version."""
    if not file_etag:
        return file_etag
    return f'"{file_etag.strip(chr(34))}-t{TIMELINE_FORMAT_VERSION}"'


# Names Claude Code uses for the session that leads a team of agents.
_LEAD_NAMES = frozenset({"team-lead", "coordinator", "main"})

# promptSource values that describe how a human prompt arrived.
_PROMPT_SOURCES = frozenset({"typed", "queued", "sdk", "suggestion_accepted"})

_TASK_KIND_LABELS = {
    "agent": "Agent",
    "shell": "Background command",
    "monitor": "Monitor",
    "workflow": "Workflow",
    "mcp": "MCP task",
}

_NOTICE_TITLES = {
    "away_summary": "Recap",
    "informational": "Notice",
    "model_refusal_fallback": "Model switched",
    "bridge_status": "Remote control",
}

_CONTEXT_TITLES = {
    "system_reminder": "System reminder",
    "hook_context": "Hook context",
    "skill_body": "Skill instructions",
    "meta": "Injected context",
}

# Tool results without is_error (MCP tools report failures as text) still read as errors.
_ERROR_TEXT_RE = re.compile(
    r'\s*(?:\{"result":\s*")?'
    r'(?:(?:Error|ERROR)\b|An error occurred \(|\{\s*(?:\\n\s*)?\\?"success\\?":\s*false)'
)

# A fire and the turn it starts are written within moments of each other.
_SCHEDULED_PAIR_SECONDS = 30.0

# A meta body counts as part of a typed command only when written right after it.
_FOLLOWS_SECONDS = 2.0


@dataclass
class _Inbound:
    """One piece of non-assistant input: a user entry or a queued attachment."""

    content: str
    timestamp: datetime
    source: str
    origin_kind: Optional[str] = None
    origin_name: Optional[str] = None
    origin_from: Optional[str] = None
    origin_sender_task_id: Optional[str] = None
    origin_relayed: bool = False
    prompt_source: Optional[str] = None
    is_meta: bool = False
    image_attachments: list = field(default_factory=list)
    source_tool_use_id: Optional[str] = None
    scheduled_task_id: Optional[str] = None
    wakeup_source: Optional[str] = None
    queued: bool = False

    @classmethod
    def from_user_message(cls, msg: UserMessage) -> "_Inbound":
        return cls(
            content=msg.content or "",
            timestamp=msg.timestamp,
            source=msg.source,
            origin_kind=msg.origin_kind,
            origin_name=msg.origin_name,
            origin_from=msg.origin_from,
            origin_sender_task_id=msg.origin_sender_task_id,
            origin_relayed=msg.origin_relayed,
            prompt_source=msg.prompt_source,
            is_meta=msg.is_meta,
            image_attachments=list(msg.image_attachments),
            source_tool_use_id=msg.source_tool_use_id,
            scheduled_task_id=msg.scheduled_task_id,
            wakeup_source=msg.wakeup_source,
        )

    @classmethod
    def from_queued(cls, entry: QueuedCommandEntry) -> "_Inbound":
        fields = {
            "origin_kind": entry.origin_kind,
            "origin_sender_task_id": entry.origin_sender_task_id,
            "isMeta": entry.is_meta,
        }
        if entry.command_mode == "task-notification":
            source = "task_notification"
        else:
            source = classify_user_source(fields, entry.prompt)
        return cls(
            content=entry.prompt,
            timestamp=entry.timestamp,
            source=source,
            origin_kind=entry.origin_kind,
            origin_name=entry.origin_name,
            origin_from=entry.origin_from,
            origin_sender_task_id=entry.origin_sender_task_id,
            origin_relayed=entry.origin_relayed,
            prompt_source="queued",
            is_meta=entry.is_meta,
            image_attachments=list(entry.image_attachments),
            queued=True,
        )


def build_conversation_timeline(
    conversation: ConversationEntity,
    working_dirs: list[str],
    actor: str = "session",
    actor_type: str = "session",
    subagent_info: Optional[dict[str, Optional[str]]] = None,
    agent_registry: Optional[AgentRegistry] = None,
    agent_types: Optional[dict[str, str]] = None,
) -> list[TimelineEvent]:
    """
    Build chronological timeline of events from a conversation.

    Shared implementation for session and subagent timeline endpoints.

    Args:
        conversation: Session or Agent to build timeline from
        working_dirs: Working directories for path relativization
        actor: Default actor identifier
        actor_type: Default actor type ("session" or "subagent")
        subagent_info: Optional dict mapping agent_id -> slug (for sessions)
        agent_registry: Names, colours and types of the session's subagents
        agent_types: Types already known by agent id (an agent's own, in its own timeline)

    Returns:
        List of TimelineEvent sorted by timestamp
    """
    builder = _TimelineBuilder(
        conversation,
        working_dirs,
        actor,
        actor_type,
        subagent_info or {},
        agent_registry or AgentRegistry(),
    )
    builder.spawn_types.update(agent_types or {})
    return builder.build()


class _TimelineBuilder:
    """Turns one conversation's entries into timeline events."""

    def __init__(
        self,
        conversation: ConversationEntity,
        working_dirs: list[str],
        actor: str,
        actor_type: str,
        subagent_info: dict[str, Optional[str]],
        registry: AgentRegistry,
    ) -> None:
        self.conversation = conversation
        self.working_dirs = working_dirs
        self.actor = actor
        self.actor_type = actor_type
        self.subagent_info = subagent_info
        self.registry = registry
        self.is_agent_view = actor_type == "subagent"

        self.events: list[TimelineEvent] = []
        # Event ids come from the entry being handled, so they survive later entries
        self._entry_key = ""
        self._entry_seq = 0
        self._used_ids: set[str] = set()
        # Spawn times per teammate name, to tell apart agents that share one
        self.spawns_by_name: dict[str, list[tuple[datetime, str]]] = {}
        # Type each spawn call asked for, by agent id
        self.spawn_types: dict[str, str] = {}
        self.tool_results: dict[str, ToolResultData] = {}
        self.task_subjects: dict[str, str] = {}
        # Events later entries attach to
        self.tool_events: dict[str, TimelineEvent] = {}
        self.command_events: list[TimelineEvent] = []
        self.scheduled_events: list[TimelineEvent] = []
        self.outgoing_messages: list[TimelineEvent] = []
        self.peer_names: dict[str, str] = {}
        self.prev_user_event: Optional[TimelineEvent] = None
        # True right after a <local-command-caveat>: the next command ran locally
        self.caveat_seen = False
        self.last_shell: Optional[TimelineEvent] = None
        self.pending_compaction: Optional[TimelineEvent] = None
        self.task_prompt: Optional[TimelineEvent] = None

    # ------------------------------------------------------------------
    # Driver
    # ------------------------------------------------------------------

    def build(self) -> list[TimelineEvent]:
        conversation = self.conversation
        # Pass 1: Collect all tool results for later merging
        self.tool_results = collect_tool_results(
            conversation, extract_spawned_agent=True, parse_xml=True
        )
        self._collect_task_subjects()

        # Pass 2: Build events with merged results
        is_first_user_message = True
        # Same sidechain policy as Session (skip) and Agent (keep) summaries.
        api_errors = ApiErrorTracker(skip_sidechain=is_session(conversation))
        api_error_events: list[tuple[TimelineEvent, str]] = []

        for msg in conversation.iter_messages():
            api_errors.feed(msg)
            self._begin_entry(getattr(msg, "uuid", None), getattr(msg, "timestamp", None))
            if isinstance(msg, UserMessage):
                # For subagents, the first UserMessage is always the Task prompt.
                is_task_prompt = is_first_user_message and self.is_agent_view
                is_first_user_message = False
                inbound = _Inbound.from_user_message(msg)
                if msg.is_tool_result:
                    if is_task_prompt and msg.prompt_text:
                        # A fork's prompt rides on the tool result that started it
                        self._add_task_prompt(replace(inbound, content=msg.prompt_text))
                    elif is_task_prompt:
                        is_first_user_message = True
                    continue
                if is_task_prompt:
                    self.prev_user_event = self._add_task_prompt(inbound)
                else:
                    self.prev_user_event = self._handle_inbound(inbound)
            elif isinstance(msg, AssistantMessage):
                self.prev_user_event = None
                self.caveat_seen = False
                api_event = self._handle_assistant(msg)
                if api_event is not None:
                    api_error_events.append((api_event, msg.uuid))
            elif isinstance(msg, CompactBoundaryMessage):
                self.pending_compaction = self._add_compaction(
                    msg.timestamp, trigger=msg.trigger, pre_tokens=msg.pre_tokens
                )

        # Pass 3: harness notices and queued input, which are not conversation messages
        self.prev_user_event = None
        jsonl_path = getattr(conversation, "jsonl_path", None)
        # An agent can span several files; a session has one
        all_paths = getattr(conversation, "all_paths", (jsonl_path,) if jsonl_path else ())
        for side_path in all_paths:
            for entry in iter_side_entries(side_path):
                self._begin_entry(entry.uuid, entry.timestamp)
                if isinstance(entry, SystemEntry):
                    self._handle_system_entry(entry)
                else:
                    self._handle_inbound(_Inbound.from_queued(entry))

        ended_turn_uuid = api_errors.summary().ended_turn_uuid
        for api_event, turn_uuid in api_error_events:
            api_event.metadata["healed"] = turn_uuid != ended_turn_uuid
        self._name_outgoing_peers()

        # Sort by timestamp
        self.events.sort(key=lambda e: e.timestamp)
        return self.events

    def _collect_task_subjects(self) -> None:
        """Map taskId -> subject so TaskUpdate events can show what the task is."""
        # TaskCreate input has no taskId; it comes back in the result as "Task #N created".
        for msg in self.conversation.iter_messages():
            if not isinstance(msg, AssistantMessage):
                continue
            for block in msg.content_blocks:
                if isinstance(block, ToolUseBlock) and block.name == "TaskCreate":
                    subject = str(block.input.get("subject", ""))
                    if not subject:
                        continue
                    result = self.tool_results.get(block.id)
                    if result:
                        m = re.search(r"Task #(\d+)", result.content)
                        if m:
                            self.task_subjects[m.group(1)] = subject

    def _add(
        self,
        event_type: str,
        timestamp: datetime,
        title: str,
        *,
        actor: str,
        actor_type: str,
        summary: Optional[str] = None,
        metadata: Optional[dict] = None,
        actor_name: Optional[str] = None,
        actor_color: Optional[str] = None,
        actor_agent_type: Optional[str] = None,
    ) -> TimelineEvent:
        event = TimelineEvent(
            id=self._next_id(),
            event_type=event_type,
            timestamp=timestamp,
            actor=actor,
            actor_type=actor_type,
            actor_name=actor_name,
            actor_color=actor_color,
            actor_agent_type=actor_agent_type,
            title=title,
            summary=summary or None,
            metadata=metadata or {},
        )
        self.events.append(event)
        return event

    def _begin_entry(self, uuid: Optional[str], timestamp: Optional[datetime]) -> None:
        """Name the JSONL entry whose events come next."""
        self._entry_key = uuid or (f"t{timestamp.isoformat()}" if timestamp else "t")
        self._entry_seq = 0

    def _next_id(self) -> str:
        """Entry uuid plus the event's position within the entry; stable across polls."""
        base = f"evt-{self._entry_key}-{self._entry_seq}"
        self._entry_seq += 1
        event_id, copy = base, 1
        while event_id in self._used_ids:
            copy += 1
            event_id = f"{base}-{copy}"
        self._used_ids.add(event_id)
        return event_id

    def _agent_type(self, agent_id: Optional[str]) -> Optional[str]:
        """An agent's type by the rule the subagents list uses; None when it is not known."""
        if not agent_id:
            return None
        return resolve_subagent_type(
            agent_id, self.spawn_types.get(agent_id), self.registry.get(agent_id)
        )

    def _is_command(self, event: TimelineEvent) -> bool:
        return any(event is command for command in self.command_events)

    def _add_system(
        self,
        event_type: str,
        timestamp: datetime,
        title: str,
        summary: Optional[str],
        metadata: dict,
    ) -> TimelineEvent:
        return self._add(
            event_type,
            timestamp,
            title,
            actor="system",
            actor_type="system",
            summary=summary,
            metadata=metadata,
        )

    # ------------------------------------------------------------------
    # Input that is not from Claude
    # ------------------------------------------------------------------

    def _handle_inbound(self, inbound: _Inbound) -> Optional[TimelineEvent]:
        """Emit the event for one inbound entry; returns the event it made or attached to."""
        source = inbound.source
        if source not in ("local_command", "command"):
            self.caveat_seen = False
        if source == "compact_summary":
            return self._attach_compact_summary(inbound)
        if source in ("peer_session", "agent"):
            return self._add_incoming_message(inbound)
        if source == "task_notification":
            return self._add_task_notification(inbound)
        if source == "scheduled":
            return self._add_scheduled_fire(inbound)
        if source == "skill_body":
            return self._attach_skill_body(inbound)
        if source == "system_reminder":
            return self._add_context(inbound, "system_reminder")
        if source == "meta":
            return self._handle_meta(inbound)
        if source == "local_command":
            return self._handle_local_command(inbound)
        if source == "command":
            return self._add_command(inbound)
        if source == "shell":
            return self._handle_shell(inbound)
        if source == "interrupt":
            return self._add(
                "system_notice",
                inbound.timestamp,
                "Interrupted by user",
                actor="user",
                actor_type="user",
                metadata={"kind": "interrupted", "level": None, "full_content": inbound.content},
            )
        return self._add_prompt(inbound)

    def _add_task_prompt(self, inbound: _Inbound) -> TimelineEvent:
        """The first message of a subagent file: the task its parent gave it."""
        parts = parse_wrapped_messages(inbound.content)
        wrapped = parts[0]
        if wrapped.wrapper:
            body = "\n\n".join(part.body for part in parts)
        else:
            body = _strip_command_tags(inbound.content)
        metadata: dict = {"full_content": body, "is_task_prompt": True}
        if wrapped.summary:
            metadata["message_summary"] = wrapped.summary
        if inbound.image_attachments:
            metadata["image_attachments"] = _images(inbound)
        self.task_prompt = self._add(
            "prompt",
            inbound.timestamp,
            "Task prompt",
            actor=wrapped.sender_name or "session",
            actor_type="session",
            actor_name=wrapped.sender_name,
            summary=wrapped.summary or _preview(body),
            metadata=metadata,
        )
        return self.task_prompt

    def _add_prompt(self, inbound: _Inbound) -> Optional[TimelineEvent]:
        """A prompt a person typed (or, inside a subagent, more input from its parent)."""
        if self.is_agent_view and inbound.origin_kind != "human":
            return self._add_parent_input(inbound)

        content = inbound.content
        # Detect command invocation from <command-message> tags
        prompt_event_type, prompt_title, cmd_summary, cmd_name, referenced_skills = (
            _detect_command_from_content(content)
        )
        if prompt_event_type != "prompt":
            return self._add_command(inbound)

        display_content = _strip_command_tags(content)
        prompt_source = inbound.prompt_source if inbound.prompt_source in _PROMPT_SOURCES else None
        prompt_metadata: dict = {
            "full_content": content,
            "prompt_source": prompt_source,
            "queued": inbound.queued or prompt_source == "queued",
        }
        if inbound.image_attachments:
            prompt_metadata["image_attachments"] = _images(inbound)
        # Skills mentioned in the prompt text are intent, not invocations.
        if referenced_skills:
            prompt_metadata["referenced_skills"] = referenced_skills
            prompt_metadata["skill_intent"] = True
        return self._add(
            "prompt",
            inbound.timestamp,
            prompt_title,
            actor="user",
            actor_type="user",
            summary=_preview(display_content),
            metadata=prompt_metadata,
        )

    def _add_parent_input(self, inbound: _Inbound) -> TimelineEvent:
        """Unwrapped text in a subagent file: more of its task, or a follow-up from its parent."""
        task_prompt = self.task_prompt
        if task_prompt is not None and inbound.timestamp == task_prompt.timestamp:
            # Workflow agents get their task as two entries written at the same moment
            task_prompt.metadata["full_content"] += "\n\n" + inbound.content
            return task_prompt
        body = inbound.content.strip()
        return self._add(
            "message",
            inbound.timestamp,
            "Message from main session",
            actor="session",
            actor_type="session",
            summary=body[:200],
            metadata={
                "direction": "in",
                "peer_kind": "agent",
                "peer_name": "main",
                "peer_address": None,
                "peer_agent_id": None,
                "peer_session_uuid": None,
                "peer_project_encoded_name": None,
                "peer_agent_type": None,
                "peer_color": None,
                "message_summary": None,
                "full_content": body,
                "queued": inbound.queued,
                "relayed": False,
            },
        )

    def _add_command(self, inbound: _Inbound, local: bool = False) -> TimelineEvent:
        """A slash command, skill or built-in the user typed (or the harness injected)."""
        content = inbound.content
        event_type, title, cmd_summary, cmd_name, _ = _detect_command_from_content(content)
        local = local or self.caveat_seen or parse_local_command_output(content) is not None
        self.caveat_seen = False
        if local and cmd_name:
            # Only built-ins run locally, whatever the installed command list says
            event_type, title = "builtin_command", f"Built-in: /{cmd_name}"
        display_content = _strip_command_tags(content)
        metadata: dict = {"full_content": content}
        if inbound.image_attachments:
            metadata["image_attachments"] = _images(inbound)
        if cmd_name:
            expanded_cmd = expand_plugin_short_name(cmd_name)
            metadata["command_name"] = cmd_name
            metadata["is_plugin"] = is_plugin_skill(expanded_cmd)
            if ":" in expanded_cmd:
                metadata["plugin"] = expanded_cmd.split(":")[0]
            elif is_plugin_skill(expanded_cmd):
                metadata["plugin"] = expanded_cmd
        output = parse_local_command_output(content)
        if output:
            metadata["result_content"] = output
        by_user = not inbound.is_meta
        event = self._add(
            event_type,
            inbound.timestamp,
            title,
            actor="user" if by_user else "system",
            actor_type="user" if by_user else "system",
            summary=cmd_summary or display_content[:200],
            metadata=metadata,
        )
        if event_type != "prompt":
            self.command_events.append(event)
        return event

    def _handle_local_command(self, inbound: _Inbound) -> Optional[TimelineEvent]:
        """Attach a slash command's output to its command; the caveat before it is boilerplate."""
        output = parse_local_command_output(inbound.content)
        if output is None:
            self.caveat_seen = True
            return None
        command = self.prev_user_event
        if command is not None and self._is_command(command):
            _mark_local(command)
            if output and "result_content" not in command.metadata:
                command.metadata["result_content"] = output
            return command
        if not output:
            return None
        return self._add_context(inbound, "meta", title="Command output", body=output)

    def _handle_shell(self, inbound: _Inbound) -> Optional[TimelineEvent]:
        """`! cmd` is two entries, the command and its output: one event."""
        command = parse_shell_input(inbound.content)
        stdout, stderr = parse_shell_output(inbound.content)
        event = None
        if command is not None:
            event = self._add(
                "shell_command",
                inbound.timestamp,
                "Shell command",
                actor="user",
                actor_type="user",
                summary=command[:100],
                metadata={"command": command, "result_content": None, "stderr": None},
            )
            self.last_shell = event
        elif self.prev_user_event is not None and self.prev_user_event is self.last_shell:
            event = self.last_shell
        if stdout is None and stderr is None:
            return event
        if event is None:
            return self._add_context(
                inbound,
                "meta",
                title="Shell output",
                body="\n".join(filter(None, (stdout, stderr))),
            )
        if stdout:
            event.metadata["result_content"] = stdout
        if stderr:
            event.metadata["stderr"] = stderr
        return event

    def _handle_meta(self, inbound: _Inbound) -> TimelineEvent:
        """Injected text: the body of a typed command when it follows one, else context."""
        command = self.prev_user_event
        if (
            command is not None
            and self._is_command(command)
            and "skill_body" not in command.metadata
            and abs((inbound.timestamp - command.timestamp).total_seconds()) <= _FOLLOWS_SECONDS
        ):
            command.metadata["skill_body"] = inbound.content
            return command
        if inbound.content.lstrip().startswith("Base directory for this skill:"):
            return self._add_context(inbound, "skill_body")
        return self._add_context(
            inbound, "hook_context" if _is_hook_text(inbound.content) else "meta"
        )

    def _attach_skill_body(self, inbound: _Inbound) -> TimelineEvent:
        """A skill body names the tool call that loaded it."""
        event = self.tool_events.get(inbound.source_tool_use_id or "")
        if event is None:
            return self._add_context(inbound, "skill_body")
        event.metadata.setdefault("skill_body", inbound.content)
        return event

    def _add_context(
        self,
        inbound: _Inbound,
        kind: str,
        *,
        title: Optional[str] = None,
        body: Optional[str] = None,
    ) -> TimelineEvent:
        content = inbound.content if body is None else body
        return self._add_system(
            "system_context",
            inbound.timestamp,
            title or _CONTEXT_TITLES[kind],
            strip_tags(content)[:150],
            {"kind": kind, "full_content": content},
        )

    def _add_compaction(
        self,
        timestamp: datetime,
        *,
        trigger: Optional[str] = None,
        pre_tokens: Optional[int] = None,
        summary_text: Optional[str] = None,
    ) -> TimelineEvent:
        parts = [{"auto": "Automatic", "manual": "Manual"}.get(trigger or "", "")]
        if pre_tokens:
            parts.append(f"{pre_tokens:,} tokens before")
        metadata: dict = {"trigger": trigger, "pre_tokens": pre_tokens}
        if summary_text:
            metadata["full_content"] = summary_text
        return self._add_system(
            "compaction",
            timestamp,
            "Context compacted",
            ", ".join(p for p in parts if p) or None,
            metadata,
        )

    def _attach_compact_summary(self, inbound: _Inbound) -> TimelineEvent:
        """The summary entry follows its compact_boundary; together they are one event."""
        pending = self.pending_compaction
        if pending is not None and "full_content" not in pending.metadata:
            pending.metadata["full_content"] = inbound.content
            self.pending_compaction = None
            return pending
        return self._add_compaction(inbound.timestamp, summary_text=inbound.content)

    def _add_scheduled_fire(self, inbound: _Inbound) -> TimelineEvent:
        event = self._add_system(
            "scheduled_fire",
            inbound.timestamp,
            "Scheduled task fired",
            inbound.content[:200],
            {
                "full_content": inbound.content,
                "cron": None,
                "task_id": inbound.scheduled_task_id,
                "wakeup_source": inbound.wakeup_source,
            },
        )
        self.scheduled_events.append(event)
        return event

    def _add_task_notification(self, inbound: _Inbound) -> TimelineEvent:
        note = parse_task_notification(inbound.content)
        info = self.registry.get(note.task_id) or self.registry.by_tool_use_id(note.tool_use_id)
        agent_id = info.agent_id if info else None
        if agent_id is None and note.tool_use_id:
            result = self.tool_results.get(note.tool_use_id)
            agent_id = result.spawned_agent_id if result else None
            info = self.registry.get(agent_id)
        kind = "agent" if agent_id else note.kind
        label = _TASK_KIND_LABELS.get(kind or "", "Background task")
        metadata: dict = {
            "task_id": note.task_id,
            "task_status": note.status,
            "task_summary": note.summary,
            "tool_use_id": note.tool_use_id,
            "task_kind": kind,
            "output_file": note.output_file,
            "queued": inbound.queued,
        }
        body = note.result or note.event
        if body:
            metadata["full_content"] = body
        if agent_id:
            metadata["agent_id"] = agent_id
            metadata["agent_name"] = info.display_name if info else None
            metadata["agent_color"] = info.color if info else None
            metadata["agent_type"] = self._agent_type(agent_id)
        return self._add_system(
            "task_notification",
            inbound.timestamp,
            f"{label} {note.status}" if note.status else f"{label} update",
            note.summary or strip_tags(inbound.content)[:200],
            metadata,
        )

    def _agent_named(self, name: Optional[str], when: datetime) -> Optional[AgentInfo]:
        """The agent a name means at a moment; None rather than a guess when several share it."""
        info = self.registry.by_name(name)
        if info is not None or not self.registry.is_ambiguous(name):
            return info
        earlier = [spawn for spawn in self.spawns_by_name.get(name or "", []) if spawn[0] <= when]
        return self.registry.get(max(earlier)[1]) if earlier else None

    def _add_incoming_message(self, inbound: _Inbound) -> Optional[TimelineEvent]:
        """Messages from another Claude session or from agents on this session's team."""
        event = None
        parts = parse_wrapped_messages(inbound.content)
        for wrapped in parts:
            # Sender fields describe the entry, so they only apply when it holds one message
            origin = inbound if len(parts) == 1 else None
            event = self._add_one_incoming_message(inbound, wrapped, origin)
        return event

    def _add_one_incoming_message(
        self, inbound: _Inbound, wrapped: WrappedMessage, origin: Optional[_Inbound]
    ) -> TimelineEvent:
        name = (origin.origin_name if origin else None) or wrapped.sender_name
        if inbound.origin_kind == "coordinator":
            name = "coordinator"
        color = wrapped.color
        peer_agent_id = None
        address = None

        if inbound.source == "peer_session" and wrapped.wrapper != "teammate-message":
            peer_kind = "session"
            address = (origin.origin_from if origin else None) or wrapped.sender_address
            actor, actor_type = name or address or "session", "peer_session"
            if address and name:
                self.peer_names[address] = name
        else:
            peer_kind = "agent"
            sender_task_id = origin.origin_sender_task_id if origin else None
            info = self.registry.get(sender_task_id) or self._agent_named(name, inbound.timestamp)
            if info is not None and info.agent_id != self.actor:
                peer_agent_id = info.agent_id
                name = info.display_name or name
                color = info.color or color
                actor, actor_type = info.agent_id, "subagent"
            elif name in _LEAD_NAMES or name is None:
                actor, actor_type = name or "session", "session"
            else:
                actor, actor_type = name, "subagent"

        idle = parse_idle_signal(wrapped.body)
        if idle is not None:
            return self._add_agent_idle(
                inbound, idle, actor, actor_type, name, color, peer_agent_id
            )

        metadata: dict = {
            "direction": "in",
            "peer_kind": peer_kind,
            "peer_name": name,
            "peer_address": address,
            "peer_agent_id": peer_agent_id,
            "peer_session_uuid": None,
            "peer_project_encoded_name": None,
            "peer_agent_type": self._agent_type(peer_agent_id),
            "peer_color": color,
            "message_summary": wrapped.summary,
            "full_content": wrapped.body,
            "queued": inbound.queued,
            "relayed": inbound.origin_relayed,
        }
        if peer_agent_id:
            metadata["agent_id"] = peer_agent_id
            metadata["agent_slug"] = self.subagent_info.get(peer_agent_id)
        return self._add(
            "message",
            inbound.timestamp,
            f"Message from {name or address or 'another session'}",
            actor=actor,
            actor_type=actor_type,
            actor_name=name,
            actor_color=color,
            actor_agent_type=self._agent_type(peer_agent_id),
            summary=wrapped.summary or wrapped.body[:200],
            metadata=metadata,
        )

    def _add_agent_idle(
        self,
        inbound: _Inbound,
        idle: dict,
        actor: str,
        actor_type: str,
        name: Optional[str],
        color: Optional[str],
        agent_id: Optional[str],
    ) -> TimelineEvent:
        """A teammate saying it has gone idle: context from that agent, not a message."""
        reason = idle.get("idleReason") if isinstance(idle.get("idleReason"), str) else None
        result = idle.get("result") if isinstance(idle.get("result"), str) else ""
        agent_type = self._agent_type(agent_id)
        metadata: dict = {
            "kind": "agent_idle",
            "full_content": result,
            "idle_reason": reason,
            "agent_type": agent_type,
        }
        if agent_id:
            metadata["agent_id"] = agent_id
            metadata["agent_slug"] = self.subagent_info.get(agent_id)
        return self._add(
            "system_context",
            inbound.timestamp,
            f"{name or 'Agent'} is idle",
            actor=actor,
            actor_type=actor_type,
            actor_name=name,
            actor_color=color,
            actor_agent_type=agent_type,
            summary=result[:150] or reason,
            metadata=metadata,
        )

    # ------------------------------------------------------------------
    # Harness notices (system entries)
    # ------------------------------------------------------------------

    def _handle_system_entry(self, entry: SystemEntry) -> None:
        if entry.subtype == "local_command":
            self._handle_system_local_command(entry)
        elif entry.subtype == "scheduled_task_fire":
            self._handle_system_scheduled_fire(entry)
        else:
            metadata: dict = {
                "kind": entry.subtype,
                "level": entry.level,
                "full_content": entry.content,
            }
            if entry.url:
                metadata["url"] = entry.url
            if entry.original_model or entry.fallback_model:
                metadata["original_model"] = entry.original_model
                metadata["fallback_model"] = entry.fallback_model
            self._add_system(
                "system_notice",
                entry.timestamp,
                _NOTICE_TITLES.get(entry.subtype, "Notice"),
                entry.content[:200],
                metadata,
            )

    def _handle_system_local_command(self, entry: SystemEntry) -> None:
        """Newer sessions record a slash command and its output as two system entries."""
        output = parse_local_command_output(entry.content)
        if output is None:
            self._add_command(
                _Inbound(content=entry.content, timestamp=entry.timestamp, source="command"),
                local=True,
            )
            return
        name = (entry.command_name or "").lstrip("/")
        candidates = [
            e
            for e in self.command_events
            if e.timestamp <= entry.timestamp
            and "result_content" not in e.metadata
            and (not name or str(e.metadata.get("command_name", "")).lstrip("/") == name)
        ]
        if candidates:
            command = max(candidates, key=lambda e: e.timestamp)
            _mark_local(command)
            if output:
                command.metadata["result_content"] = output
        elif name and output:
            event = self._add(
                "builtin_command",
                entry.timestamp,
                f"Built-in: /{name}",
                actor="user",
                actor_type="user",
                summary=entry.command_args or f"Invoked /{name}",
                metadata={"command_name": name, "is_plugin": False, "result_content": output},
            )
            self.command_events.append(event)

    def _handle_system_scheduled_fire(self, entry: SystemEntry) -> None:
        """A fire is also written as the user entry that starts its turn; keep one event."""
        for event in self.scheduled_events:
            delta = abs((event.timestamp - entry.timestamp).total_seconds())
            same_task = event.metadata.get("task_id") in (None, entry.task_id)
            if (
                event.metadata.get("cron") is None
                and same_task
                and delta <= _SCHEDULED_PAIR_SECONDS
            ):
                event.metadata["cron"] = entry.cron
                event.metadata["task_id"] = entry.task_id
                return
        prompt = entry.prompt or entry.content
        self._add_system(
            "scheduled_fire",
            entry.timestamp,
            "Scheduled task fired",
            prompt[:200],
            {
                "full_content": prompt,
                "cron": entry.cron,
                "task_id": entry.task_id,
                "wakeup_source": None,
            },
        )

    # ------------------------------------------------------------------
    # Claude's own turns
    # ------------------------------------------------------------------

    def _assistant_actor(self, msg: AssistantMessage) -> tuple[str, str, Optional[AgentInfo]]:
        if msg.is_sidechain or msg.agent_id:
            return msg.agent_id or "subagent", "subagent", self.registry.get(msg.agent_id)
        info = self.registry.get(self.actor) if self.is_agent_view else None
        return self.actor, self.actor_type, info

    def _handle_assistant(self, msg: AssistantMessage) -> Optional[TimelineEvent]:
        """Emit events for one assistant message; returns its api_error event, if it is one."""
        msg_actor, msg_actor_type, info = self._assistant_actor(msg)
        who = {
            "actor": msg_actor,
            "actor_type": msg_actor_type,
            "actor_name": info.display_name if info else None,
            "actor_color": info.color if info else None,
            "actor_agent_type": self._agent_type(msg_actor)
            if msg_actor_type == "subagent"
            else None,
        }

        # An API-error turn is one event; its synthetic text block is not a response.
        if msg.api_error is not None:
            err = msg.api_error
            return self._add(
                "api_error",
                msg.timestamp,
                err.text[:120],
                summary=err.text,
                metadata={
                    "kind": err.kind,
                    "code": err.code,
                    "status": err.status,
                    "resets_at": err.resets_at.isoformat() if err.resets_at else None,
                    "healed": True,
                },
                **who,
            )

        for index, block in enumerate(msg.content_blocks):
            # The id suffix is the block's index, whichever earlier blocks made events
            self._entry_seq = index
            if isinstance(block, ToolUseBlock):
                self._add_tool_event(msg, block, who)
            elif isinstance(block, ThinkingBlock):
                thinking_preview = block.thinking[:150] if block.thinking else ""
                self._add(
                    "thinking",
                    msg.timestamp,
                    "Thinking",
                    summary=thinking_preview,
                    metadata={"full_thinking": block.thinking},
                    **who,
                )
            elif isinstance(block, TextBlock):
                # Only include substantial text responses
                if len(block.text) > 50:
                    word_count = len(block.text.split())
                    is_big = word_count > 100
                    resp_metadata: dict = {"full_text": block.text, "word_count": word_count}
                    if is_big:
                        resp_metadata["is_big_response"] = True
                    self._add(
                        "response",
                        msg.timestamp,
                        "Big Response" if is_big else "Response",
                        summary=block.text[:150],
                        metadata=resp_metadata,
                        **who,
                    )
        return None

    def _add_tool_event(self, msg: AssistantMessage, block: ToolUseBlock, who: dict) -> None:
        result_data = self.tool_results.get(block.id)
        if block.name == "SendMessage":
            self._add_outgoing_message(msg, block, result_data, who)
            return

        title, summary, base_metadata = get_tool_summary(block, working_dirs=self.working_dirs)
        metadata = _build_tool_call_metadata(
            block, base_metadata, result_data, self.subagent_info, self.task_subjects, self.registry
        )

        # Add agent context for subagent messages
        if who["actor_type"] == "subagent":
            metadata["agent_id"] = msg.agent_id
            metadata["agent_slug"] = msg.slug

        # Determine event type based on tool
        if block.name == "TodoWrite":
            event_type = "todo_update"
        elif block.name in ("Task", "Agent"):
            event_type = "subagent_spawn"
        elif block.name == "Skill":
            skill_name = block.input.get("skill", "Unknown")
            # Expand short-form names for correct classification and metadata
            expanded_name = expand_plugin_short_name(skill_name)
            kind = classify_invocation(skill_name, source="skill_tool")
            if kind == "builtin_command":
                event_type = "builtin_command"
                title = f"Built-in: /{skill_name}"
            elif is_skill_category(kind):
                event_type = "skill_invocation"
                title = f"Skill: /{skill_name}"
            else:
                event_type = "command_invocation"
                title = f"Command: /{skill_name}"
            metadata["command_name"] = skill_name
            metadata["is_plugin"] = is_plugin_skill(expanded_name)
            if ":" in expanded_name:
                metadata["plugin"] = expanded_name.split(":")[0]
            elif is_plugin_skill(expanded_name):
                metadata["plugin"] = expanded_name
            summary = f"Invoked /{skill_name}"
        else:
            event_type = "tool_call"

        spawned_name, spawned_id = (
            metadata.get("spawned_agent_name"),
            metadata.get("spawned_agent_id"),
        )
        if event_type == "subagent_spawn" and spawned_name and spawned_id:
            self.spawns_by_name.setdefault(spawned_name, []).append((msg.timestamp, spawned_id))
        if event_type == "subagent_spawn" and spawned_id and metadata.get("subagent_type"):
            self.spawn_types[spawned_id] = metadata["subagent_type"]

        self.tool_events[block.id] = self._add(
            event_type, msg.timestamp, title, summary=summary, metadata=metadata, **who
        )

    def _add_outgoing_message(
        self,
        msg: AssistantMessage,
        block: ToolUseBlock,
        result_data: Optional[ToolResultData],
        who: dict,
    ) -> None:
        """A SendMessage call: Claude writing to another session or to an agent."""
        tool_input = block.input
        recipient = str(tool_input.get("to") or tool_input.get("recipient") or "")
        recipient_kind = tool_input.get("recipient_kind")
        info = self.registry.get(recipient) or self._agent_named(recipient, msg.timestamp)
        is_address = recipient_kind == "session" or re.match(r"[a-z]+:/", recipient) is not None
        is_agent = (
            recipient_kind in ("agent", "main")
            or recipient in _LEAD_NAMES
            or self.is_agent_view
            or self.registry.is_ambiguous(recipient)
        )

        if info is not None:
            peer_kind, name = "agent", info.display_name or recipient
        elif is_address:
            peer_kind, name = "session", None
        elif is_agent:
            peer_kind, name = "agent", recipient or None
        else:
            peer_kind, name = "session", recipient or None

        body = str(tool_input.get("message") or tool_input.get("content") or "")
        message_summary = tool_input.get("summary") or None
        metadata = _build_tool_call_metadata(block, {}, result_data, self.subagent_info)
        metadata.update(
            {
                "direction": "out",
                "peer_kind": peer_kind,
                "peer_name": name,
                "peer_address": recipient if is_address else None,
                "peer_agent_id": info.agent_id if info else None,
                "peer_session_uuid": None,
                "peer_project_encoded_name": None,
                "peer_agent_type": self._agent_type(info.agent_id) if info else None,
                "peer_color": info.color if info else None,
                "message_summary": message_summary,
                "full_content": body,
                "queued": False,
                "relayed": False,
            }
        )
        if who["actor_type"] == "subagent":
            metadata["agent_id"] = msg.agent_id
            metadata["agent_slug"] = msg.slug
        event = self._add(
            "message",
            msg.timestamp,
            f"Message to {name or recipient or 'unknown'}",
            summary=message_summary or body[:200],
            metadata=metadata,
            **who,
        )
        self.tool_events[block.id] = event
        self.outgoing_messages.append(event)

    def _name_outgoing_peers(self) -> None:
        """A reply to a socket address gets the name its sender introduced itself with."""
        for event in self.outgoing_messages:
            address = event.metadata.get("peer_address")
            name = self.peer_names.get(address) if address else None
            if name and not event.metadata.get("peer_name"):
                event.metadata["peer_name"] = name
                event.title = f"Message to {name}"


def _mark_local(command: TimelineEvent) -> None:
    """A command with local output is a built-in, whatever the installed command list says."""
    name = command.metadata.get("command_name")
    if command.event_type == "command_invocation" and name:
        command.event_type = "builtin_command"
        command.title = f"Built-in: /{name}"


def _preview(text: str, limit: int = 200) -> str:
    """A prompt's one-line preview: paste and fork wrappers dropped, the text kept."""
    return strip_prompt_wrappers(text)[:limit]


def _images(inbound: _Inbound) -> list[dict]:
    return [
        {"media_type": img["media_type"], "data": img["data"]} for img in inbound.image_attachments
    ]


def _is_hook_text(content: str) -> bool:
    head = content.lstrip()[:80].lower()
    return head.startswith("<") and "hook" in head.split(">", 1)[0]


def _detect_command_from_content(
    content: str,
) -> tuple[str, str, str | None, str | None, list[str] | None]:
    """Parse <command-message> tags or slash-command patterns from user prompt content.

    First checks for structured <command-message> tags (Claude Code's standard format).
    Falls back to detecting /command patterns in plain text for skills invoked via hooks
    (magic keywords) where the slash command is embedded in a larger message.

    For <command-message> detected commands (explicit user invocation), returns the
    appropriate event type (skill_invocation, command_invocation, builtin_command).

    For text-detected skills (slash commands embedded in larger messages), returns
    "prompt" as the event type since the user prompt itself is not the invocation —
    the actual invocation happens when Claude calls the Skill tool ("Launching skill:").
    The referenced skill names are returned separately as intent metadata.

    Returns (event_type, title, summary, command_name, referenced_skills).
    - referenced_skills: list of skill names the user mentioned (intent, not invocation)
    """
    cmd_name, args = parse_command_from_content(content)

    # Fallback: detect /command patterns in plain text (hook-triggered skills)
    referenced_skills: list[str] | None = None
    if cmd_name is None:
        slash_cmds = detect_slash_commands_in_text(content)
        # Collect ALL skill references from the text (not just the first)
        # Expand short-form plugin names for consistency with Skill tool invocations
        skills_found = [
            expand_plugin_short_name(c)
            for c in slash_cmds
            if is_skill_category(classify_invocation(c))
        ]
        if skills_found:
            referenced_skills = skills_found

    if cmd_name is None:
        # No <command-message> tags. Return as prompt with intent metadata.
        return "prompt", "User prompt", None, None, referenced_skills

    kind = classify_invocation(cmd_name)
    summary = args[:200] if args else f"Invoked /{cmd_name}"

    if kind == "builtin_command":
        return "builtin_command", f"Built-in: /{cmd_name}", summary, cmd_name, None
    elif is_skill_category(kind):
        return "skill_invocation", f"Skill: /{cmd_name}", summary, cmd_name, None
    else:
        return "command_invocation", f"Command: /{cmd_name}", summary, cmd_name, None


def _strip_command_tags(content: str) -> str:
    """Remove command XML tags from content for display."""
    return strip_command_tags(content)


def _build_tool_call_metadata(
    block: ToolUseBlock,
    base_metadata: dict,
    result_data: Optional[ToolResultData],
    subagent_info: dict[str, Optional[str]],
    task_subjects: Optional[dict[str, str]] = None,
    registry: Optional[AgentRegistry] = None,
) -> dict:
    """Build complete metadata for a tool call, merging in result if available."""
    metadata = {"tool_name": block.name, "tool_id": block.id, **base_metadata}

    # For Task tool, add spawning context
    if block.name in ("Task", "Agent"):
        metadata["is_spawn_task"] = True
        _add_spawn_identity(
            metadata, block, result_data, subagent_info, registry or AgentRegistry()
        )

    # Annotate TaskUpdate with the subject from the matching TaskCreate
    if block.name == "TaskUpdate" and task_subjects:
        task_id = str(block.input.get("taskId", ""))
        if task_id and task_id in task_subjects:
            metadata["task_subject"] = task_subjects[task_id]

    if result_data is None:
        return metadata

    # Merge result data
    metadata["has_result"] = True
    metadata["result_timestamp"] = result_data.timestamp.isoformat()
    metadata["result_content"] = result_data.content

    if result_data.parsed:
        metadata["result_parsed"] = result_data.parsed

    metadata["result_status"] = _result_status(result_data)

    return metadata


def _add_spawn_identity(
    metadata: dict,
    block: ToolUseBlock,
    result_data: Optional[ToolResultData],
    subagent_info: dict[str, Optional[str]],
    registry: AgentRegistry,
) -> None:
    """Link a spawn to its subagent and name it from the agent's meta.json."""
    agent_id = result_data.spawned_agent_id if result_data else None
    info = registry.get(agent_id) or registry.by_tool_use_id(block.id)
    if agent_id is None and info is not None and result_data is not None:
        agent_id = info.agent_id
    if agent_id:
        metadata["spawned_agent_id"] = agent_id
        metadata["spawned_agent_slug"] = subagent_info.get(agent_id)
    tool_input = block.input
    metadata["spawned_agent_name"] = (info.name if info else None) or tool_input.get("name")
    metadata["spawned_agent_color"] = info.color if info else None
    metadata["team_name"] = (info.team_name if info else None) or tool_input.get("team_name")
    model = (info.model if info else None) or tool_input.get("model")
    metadata["agent_model"] = None if model == "inherit" else model
    metadata["run_in_background"] = bool(tool_input.get("run_in_background"))
    metadata["subagent_type"] = resolve_subagent_type(agent_id, metadata.get("subagent_type"), info)


def _result_status(result_data: ToolResultData) -> str:
    """success/error from the tool_result's is_error; a text check only when it has none."""
    if result_data.is_error is not None:
        return "error" if result_data.is_error else "success"
    return "error" if _ERROR_TEXT_RE.match(result_data.content) else "success"


# =============================================================================
# Tool Usage Summary
# =============================================================================


def build_tool_usage_summaries(
    session_tool_counts: Counter,
    subagent_tool_counts: Optional[Counter] = None,
) -> list[ToolUsageSummary]:
    """
    Build tool usage summaries from tool count data.

    Args:
        session_tool_counts: Tool counts from main session/agent
        subagent_tool_counts: Tool counts from subagents (sessions only)

    Returns:
        List of ToolUsageSummary sorted by count descending
    """
    subagent_tool_counts = subagent_tool_counts or Counter()

    # Combine into summaries
    all_tools = set(session_tool_counts.keys()) | set(subagent_tool_counts.keys())
    summaries = []

    for tool_name in sorted(all_tools):
        by_session = session_tool_counts.get(tool_name, 0)
        by_subagents = subagent_tool_counts.get(tool_name, 0)
        summaries.append(
            ToolUsageSummary(
                tool_name=tool_name,
                count=by_session + by_subagents,
                by_session=by_session,
                by_subagents=by_subagents,
            )
        )

    # Sort by total count descending
    summaries.sort(key=lambda s: s.count, reverse=True)
    return summaries


def build_agent_tool_summaries(tool_counts: Counter) -> list[ToolUsageSummary]:
    """
    Build tool usage summaries for an agent (subagent or standalone).

    For agents, all usage is attributed to the agent itself (by_subagents field).

    Args:
        tool_counts: Tool counts from the agent

    Returns:
        List of ToolUsageSummary sorted by count descending
    """
    summaries = [
        ToolUsageSummary(
            tool_name=tool_name,
            count=count,
            by_session=0,  # Agents don't have subagents themselves
            by_subagents=count,  # All usage is from this agent
        )
        for tool_name, count in tool_counts.items()
    ]

    # Sort by count descending
    summaries.sort(key=lambda s: s.count, reverse=True)
    return summaries


# =============================================================================
# File Activity
# =============================================================================


def build_file_activities(file_operations: list[FileOperation]) -> list[FileActivity]:
    """
    Convert FileOperation dataclasses to FileActivity schemas.

    Args:
        file_operations: List of FileOperation objects from data collection

    Returns:
        List of FileActivity sorted by timestamp
    """
    activities = [
        FileActivity(
            path=op.path,
            operation=op.operation,
            actor=op.actor,
            actor_type=op.actor_type,
            timestamp=op.timestamp,
            tool_name=op.tool_name,
        )
        for op in file_operations
    ]

    # Sort by timestamp
    activities.sort(key=lambda a: a.timestamp)
    return activities
