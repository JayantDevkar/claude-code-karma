"""Timeline sender classification: who sent each entry, and the entries the parser used to drop."""

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from models.jsonl_utils import iter_messages_from_jsonl
from models.message import parse_message
from models.session import Session
from models.side_entries import QueuedCommandEntry, SystemEntry, iter_side_entries
from services.agent_registry import build_agent_registry
from services.conversation_endpoints import build_conversation_timeline

SID = "11111111-2222-3333-4444-555555555555"
_n = 0


def _ts(sec: int) -> str:
    return f"2026-11-01T10:{sec // 60:02d}:{sec % 60:02d}.000Z"


def _base(kind: str, sec: int, **extra) -> dict:
    global _n
    _n += 1
    return {
        "type": kind,
        "uuid": f"u-{_n}",
        "timestamp": _ts(sec),
        "sessionId": SID,
        "isSidechain": False,
        **extra,
    }


def user(sec: int, content, **extra) -> dict:
    return _base("user", sec, message={"role": "user", "content": content}, **extra)


def assistant(sec: int, blocks: list, **extra) -> dict:
    return _base(
        "assistant",
        sec,
        message={"role": "assistant", "model": "claude-fable-5-2", "content": blocks},
        **extra,
    )


def tool_use(tool_id: str, tool_name: str, /, **tool_input) -> dict:
    return {"type": "tool_use", "id": tool_id, "name": tool_name, "input": tool_input}


def tool_result(sec: int, tool_id: str, text: str, **extra) -> dict:
    block = {"type": "tool_result", "tool_use_id": tool_id, "content": text}
    if "is_error" in extra:
        block["is_error"] = extra.pop("is_error")
    return user(sec, [block], **extra)


def system(sec: int, subtype: str, **extra) -> dict:
    return _base("system", sec, subtype=subtype, **extra)


def queued(sec: int, prompt: str, origin: dict, mode: str = "prompt", **extra) -> dict:
    attachment = {
        "type": "queued_command",
        "prompt": prompt,
        "commandMode": mode,
        "origin": origin,
        "timestamp": _ts(sec),
        **extra,
    }
    return _base("attachment", sec, attachment=attachment)


def write_session(tmp_path: Path, entries: list, subagents: dict | None = None) -> Session:
    project = tmp_path / "-Users-me-repo"
    project.mkdir(parents=True, exist_ok=True)
    path = project / f"{SID}.jsonl"
    path.write_text("\n".join(json.dumps(e) for e in entries) + "\n")
    for agent_id, spec in (subagents or {}).items():
        sub_dir = project / SID / "subagents"
        sub_dir.mkdir(parents=True, exist_ok=True)
        lines = spec.get("entries") or [user(0, "task", agentId=agent_id, isSidechain=True)]
        (sub_dir / f"agent-{agent_id}.jsonl").write_text(
            "\n".join(json.dumps(e) for e in lines) + "\n"
        )
        if spec.get("meta") is not None:
            (sub_dir / f"agent-{agent_id}.meta.json").write_text(json.dumps(spec["meta"]))
    return Session.from_path(path)


def timeline(session: Session, **kwargs) -> list:
    registry = build_agent_registry(session.list_subagent_paths())
    return build_conversation_timeline(
        conversation=session, working_dirs=[], agent_registry=registry, **kwargs
    )


def of_type(events: list, event_type: str) -> list:
    return [e for e in events if e.event_type == event_type]


PEER_TEXT = (
    "Another Claude session sent a message:\n"
    '<cross-session-message from="uds:/tmp/cc-socks/10999.sock" '
    'from-name="airflow-72" from-mode="bypass">\n[ASK] Why did triage blame no-zones?\n'
    "</cross-session-message>"
)
PEER_ORIGIN = {
    "kind": "peer",
    "from": "uds:/tmp/cc-socks/10999.sock",
    "name": "airflow-72",
    "fromMode": "bypass",
    "body": "[ASK] Why did triage blame no-zones?",
}
TASK_NOTE = (
    "<task-notification>\n<task-id>a88c3f920e0d92c99</task-id>\n"
    "<tool-use-id>toolu_spawn</tool-use-id>\n<output-file>/tmp/x.output</output-file>\n"
    '<status>completed</status>\n<summary>Agent "Probe write" finished</summary>\n'
    "<result>WRITE OK</result>\n</task-notification>"
)


class TestUserSource:
    def test_typed_prompt_is_human(self):
        msg = parse_message(user(1, "fix the login bug", origin={"kind": "human"}))
        assert msg.source == "human"
        assert msg.is_internal_message is False

    def test_peer_origin_is_peer_session(self):
        msg = parse_message(user(1, PEER_TEXT, isMeta=True, origin=PEER_ORIGIN))
        assert msg.source == "peer_session"
        assert msg.origin_name == "airflow-72"
        assert msg.origin_from == "uds:/tmp/cc-socks/10999.sock"
        assert msg.is_internal_message is True

    def test_peer_with_sender_task_is_agent(self):
        origin = {"kind": "peer", "from": "research", "name": "research", "senderTaskId": "ares-1"}
        text = 'Another Claude session sent a message:\n<agent-message from="research">\ndone\n</agent-message>'
        msg = parse_message(user(1, text, isMeta=True, origin=origin))
        assert msg.source == "agent"
        assert msg.origin_sender_task_id == "ares-1"

    def test_hop_chain_marks_relayed(self):
        msg = parse_message(
            user(1, PEER_TEXT, isMeta=True, origin={**PEER_ORIGIN, "hopChain": ["a", "b"]})
        )
        assert msg.origin_relayed is True

    def test_skill_body_from_source_tool_use_id(self):
        msg = parse_message(
            user(
                1,
                [{"type": "text", "text": "Base directory for this skill: /x\n\n# Skill"}],
                isMeta=True,
                sourceToolUseID="toolu_skill",
            )
        )
        assert msg.source == "skill_body"
        assert msg.source_tool_use_id == "toolu_skill"

    def test_meta_reminder_and_other_meta(self):
        reminder = parse_message(
            user(1, "<system-reminder>\nOther agents active\n</system-reminder>", isMeta=True)
        )
        other = parse_message(user(1, '[Cross-session idle notice] "infra" is idle', isMeta=True))
        assert reminder.source == "system_reminder"
        assert other.source == "meta"

    def test_compact_summary_flag(self):
        msg = parse_message(user(1, "Summary of the earlier conversation", isCompactSummary=True))
        assert msg.source == "compact_summary"

    def test_scheduled_turn(self):
        msg = parse_message(
            user(
                1,
                "Scheduled check",
                isMeta=True,
                turnOrigin="scheduled",
                scheduledTaskId="6fdf7649",
                wakeupSource="schedule_wakeup",
            )
        )
        assert msg.source == "scheduled"
        assert msg.scheduled_task_id == "6fdf7649"

    def test_task_notification_by_origin_and_by_text(self):
        by_origin = parse_message(user(1, TASK_NOTE, origin={"kind": "task-notification"}))
        by_text = parse_message(user(1, TASK_NOTE))
        plain = parse_message(
            user(1, "[SYSTEM NOTIFICATION - NOT USER INPUT]\nautomated\n\n" + TASK_NOTE)
        )
        assert by_origin.source == by_text.source == plain.source == "task_notification"

    def test_text_fallbacks_for_old_sessions(self):
        cases = {
            '<teammate-message teammate_id="team-lead" summary="s">\nhi\n</teammate-message>': "agent",
            "The coordinator sent a message while you were working:\nverify it": "agent",
            "<bash-input> ls</bash-input>": "shell",
            "<local-command-stdout>ok</local-command-stdout>": "local_command",
            "<command-name>/clear</command-name>": "command",
            "This session is being continued from a previous conversation.": "compact_summary",
            "[Request interrupted by user]": "interrupt",
        }
        for text, expected in cases.items():
            assert parse_message(user(1, text)).source == expected, text

    def test_quoted_tag_in_a_real_prompt_is_not_hidden(self):
        msg = parse_message(user(1, "why is <task-notification> hidden in the timeline?"))
        assert msg.source == "human"
        assert msg.is_internal_message is False

    def test_tool_result_keeps_agent_id_and_error_flag_only(self):
        msg = parse_message(
            tool_result(
                1,
                "toolu_1",
                "Spawned successfully.",
                is_error=False,
                toolUseResult={"agentId": "aimpl-m9-cd8b", "prompt": "x" * 5000},
            )
        )
        assert msg.source == "tool_result"
        assert msg.spawned_agent_id == "aimpl-m9-cd8b"
        assert msg.tool_result_is_error is False
        assert "toolUseResult" not in msg.model_dump()


class TestSameTimestampEntries:
    def _write(self, tmp_path: Path, entries: list) -> Path:
        path = tmp_path / "s.jsonl"
        path.write_text("\n".join(json.dumps(e) for e in entries) + "\n")
        return path

    def test_string_entries_at_one_timestamp_are_both_kept(self, tmp_path):
        path = self._write(
            tmp_path,
            [
                user(1, "<local-command-caveat>caveat</local-command-caveat>", isMeta=True),
                user(1, "<command-name>/model</command-name>\n<command-args>fable</command-args>"),
            ],
        )
        sources = [m.source for m in iter_messages_from_jsonl(path)]
        assert sources == ["local_command", "command"]

    def test_tool_results_at_one_timestamp_are_both_kept(self, tmp_path):
        path = self._write(
            tmp_path, [tool_result(1, "toolu_a", "one"), tool_result(1, "toolu_b", "two")]
        )
        ids = [m.tool_result_id for m in iter_messages_from_jsonl(path)]
        assert ids == ["toolu_a", "toolu_b"]

    def test_command_and_its_meta_skill_body_stay_separate(self, tmp_path):
        path = self._write(
            tmp_path,
            [
                user(
                    1,
                    "<command-message>research</command-message>\n<command-name>/research</command-name>",
                ),
                user(
                    1, [{"type": "text", "text": "Base directory for this skill: /x"}], isMeta=True
                ),
            ],
        )
        msgs = list(iter_messages_from_jsonl(path))
        assert [m.source for m in msgs] == ["command", "meta"]
        assert "<command-name>" in msgs[0].content


class TestSideEntries:
    def test_yields_whitelisted_system_and_queued_entries_only(self, tmp_path):
        path = tmp_path / "s.jsonl"
        entries = [
            system(1, "away_summary", content="We were reviewing X."),
            system(2, "stop_hook_summary", hookCount=1),
            system(3, "turn_duration", durationMs=5),
            queued(4, "use the branch jay/x", {"kind": "human"}, humanTurn=True),
            _base("attachment", 5, attachment={"type": "skill_listing"}),
            user(6, 'quoting "type":"system" and queued_command in a prompt'),
            {"type": "api-request-blob", "message": {"content": '"type":"system"'}},
        ]
        path.write_text("\n".join(json.dumps(e, separators=(",", ":")) for e in entries) + "\n")
        side = list(iter_side_entries(path))
        assert [type(e) for e in side] == [SystemEntry, QueuedCommandEntry]
        assert side[0].subtype == "away_summary"
        assert side[1].prompt == "use the branch jay/x"
        assert side[1].origin_kind == "human"

    def test_missing_file_yields_nothing(self, tmp_path):
        assert list(iter_side_entries(tmp_path / "nope.jsonl")) == []


class TestAgentRegistry:
    def test_reads_meta_json_next_to_each_agent(self, tmp_path):
        meta = {
            "agentType": "impl-m9",
            "name": "impl-m9",
            "teamName": "session-18e9",
            "color": "purple",
            "model": "opus",
            "description": "Implement Task 9",
            "spawnedAgentType": "general-purpose",
            "toolUseId": "toolu_spawn",
        }
        session = write_session(tmp_path, [user(1, "hi")], {"aimpl-m9-cd8b": {"meta": meta}})
        registry = build_agent_registry(session.list_subagent_paths())
        info = registry.get("aimpl-m9-cd8b")
        assert (info.name, info.color, info.team_name) == ("impl-m9", "purple", "session-18e9")
        assert info.agent_type == "general-purpose"
        assert registry.by_name("impl-m9") is info
        assert registry.by_tool_use_id("toolu_spawn") is info

    def test_missing_or_broken_meta_is_ignored(self, tmp_path):
        session = write_session(tmp_path, [user(1, "hi")], {"abc123": {"meta": None}})
        (session.subagents_dir / "agent-bad.meta.json").write_text("{not json")
        registry = build_agent_registry(session.list_subagent_paths())
        assert registry.get("abc123") is None
        assert registry.get("bad") is None


class TestTimelineSenders:
    def test_cross_session_message_is_a_message_not_a_prompt(self, tmp_path):
        session = write_session(
            tmp_path, [user(1, PEER_TEXT, isMeta=True, origin={**PEER_ORIGIN, "hopChain": ["a"]})]
        )
        events = timeline(session)
        assert of_type(events, "prompt") == []
        (ev,) = of_type(events, "message")
        assert (ev.actor, ev.actor_type, ev.actor_name) == (
            "airflow-72",
            "peer_session",
            "airflow-72",
        )
        assert ev.metadata["direction"] == "in"
        assert ev.metadata["peer_kind"] == "session"
        assert ev.metadata["peer_address"] == "uds:/tmp/cc-socks/10999.sock"
        assert ev.metadata["full_content"] == "[ASK] Why did triage blame no-zones?"
        assert ev.metadata["relayed"] is True

    def test_agent_message_resolves_to_the_subagent(self, tmp_path):
        origin = {"kind": "peer", "from": "research", "name": "research", "senderTaskId": "ares-1"}
        text = 'Another Claude session sent a message:\n<agent-message from="research">\nmap is done\n</agent-message>'
        session = write_session(
            tmp_path,
            [user(1, text, isMeta=True, origin=origin)],
            {"ares-1": {"meta": {"name": "research", "color": "cyan", "agentType": "research"}}},
        )
        (ev,) = of_type(timeline(session), "message")
        assert (ev.actor, ev.actor_type, ev.actor_name, ev.actor_color) == (
            "ares-1",
            "subagent",
            "research",
            "cyan",
        )
        assert ev.metadata["peer_kind"] == "agent"
        assert ev.metadata["peer_agent_id"] == "ares-1"
        assert ev.metadata["full_content"] == "map is done"

    def test_send_message_is_an_outgoing_message(self, tmp_path):
        block = tool_use(
            "toolu_sm",
            "SendMessage",
            to="uds:/tmp/cc-socks/10999.sock",
            recipient="uds:/tmp/cc-socks/10999.sock",
            recipient_kind="session",
            type="message",
            summary="Reply to triage ASK",
            message="ANSWER: nothing in WT picks fiber lines",
            content="ANSWER: nothing…",
        )
        session = write_session(
            tmp_path,
            [assistant(1, [block]), tool_result(2, "toolu_sm", '{"success":true}')],
        )
        events = timeline(session)
        assert of_type(events, "tool_call") == []
        (ev,) = of_type(events, "message")
        assert (ev.actor, ev.actor_type) == ("session", "session")
        meta = ev.metadata
        assert (meta["direction"], meta["peer_kind"]) == ("out", "session")
        assert meta["peer_address"] == "uds:/tmp/cc-socks/10999.sock"
        assert meta["message_summary"] == "Reply to triage ASK"
        assert meta["full_content"] == "ANSWER: nothing in WT picks fiber lines"
        assert (meta["tool_name"], meta["tool_id"], meta["has_result"]) == (
            "SendMessage",
            "toolu_sm",
            True,
        )

    def test_send_message_to_a_teammate_by_name(self, tmp_path):
        block = tool_use(
            "toolu_sm",
            "SendMessage",
            to="impl-m9",
            recipient="impl-m9",
            recipient_kind="name",
            message="go",
        )
        session = write_session(
            tmp_path,
            [assistant(1, [block])],
            {"aimpl-m9-cd8b": {"meta": {"name": "impl-m9", "color": "purple"}}},
        )
        (ev,) = of_type(timeline(session), "message")
        assert ev.metadata["peer_kind"] == "agent"
        assert ev.metadata["peer_agent_id"] == "aimpl-m9-cd8b"
        assert (ev.metadata["peer_name"], ev.metadata["peer_color"]) == ("impl-m9", "purple")

    def test_skill_body_attaches_to_its_skill_event(self, tmp_path):
        body = [{"type": "text", "text": "Base directory for this skill: /x\n\n# Debugging"}]
        session = write_session(
            tmp_path,
            [
                assistant(
                    1, [tool_use("toolu_skill", "Skill", skill="superpowers:systematic-debugging")]
                ),
                tool_result(2, "toolu_skill", "Launching skill"),
                user(2, body, isMeta=True, sourceToolUseID="toolu_skill"),
            ],
        )
        events = timeline(session)
        assert of_type(events, "prompt") == [] and of_type(events, "system_context") == []
        (ev,) = of_type(events, "skill_invocation")
        assert ev.metadata["skill_body"].startswith("Base directory for this skill")

    def test_meta_body_after_a_typed_command_attaches_to_the_command(self, tmp_path):
        session = write_session(
            tmp_path,
            [
                user(
                    1,
                    "<command-message>commit</command-message>\n<command-name>/commit</command-name>",
                    origin={"kind": "human"},
                ),
                user(1, [{"type": "text", "text": "# Commit\n\nStage and commit."}], isMeta=True),
            ],
        )
        events = timeline(session)
        assert len(events) == 1
        assert events[0].actor_type == "user"
        assert events[0].metadata["skill_body"].startswith("# Commit")

    def test_other_meta_becomes_system_context(self, tmp_path):
        session = write_session(
            tmp_path,
            [
                user(1, "real question", origin={"kind": "human"}, promptSource="typed"),
                user(2, "<system-reminder>\nOther agents active\n</system-reminder>", isMeta=True),
                user(3, '[Cross-session idle notice] "infra" is idle now', isMeta=True),
            ],
        )
        events = timeline(session)
        (prompt,) = of_type(events, "prompt")
        assert prompt.metadata["prompt_source"] == "typed"
        ctx = of_type(events, "system_context")
        assert [e.metadata["kind"] for e in ctx] == ["system_reminder", "meta"]
        assert all((e.actor, e.actor_type) == ("system", "system") for e in ctx)

    def test_task_notification_links_to_the_agent(self, tmp_path):
        session = write_session(
            tmp_path,
            [
                assistant(
                    1,
                    [
                        tool_use(
                            "toolu_spawn",
                            "Agent",
                            description="Probe write",
                            prompt="p",
                            subagent_type="general-purpose",
                            run_in_background=True,
                        )
                    ],
                ),
                tool_result(
                    2,
                    "toolu_spawn",
                    "Async agent launched successfully.",
                    toolUseResult={"agentId": "a88c3f920e0d92c99", "status": "async_launched"},
                ),
                user(9, TASK_NOTE, origin={"kind": "task-notification"}),
            ],
            {
                "a88c3f920e0d92c99": {
                    "meta": {
                        "agentType": "general-purpose",
                        "description": "Probe write",
                        "toolUseId": "toolu_spawn",
                    }
                }
            },
        )
        events = timeline(session)
        (spawn,) = of_type(events, "subagent_spawn")
        assert spawn.metadata["spawned_agent_id"] == "a88c3f920e0d92c99"
        assert spawn.metadata["run_in_background"] is True
        (note,) = of_type(events, "task_notification")
        assert (note.actor, note.actor_type) == ("system", "system")
        meta = note.metadata
        assert (meta["task_id"], meta["task_status"], meta["task_kind"]) == (
            "a88c3f920e0d92c99",
            "completed",
            "agent",
        )
        assert meta["task_summary"] == 'Agent "Probe write" finished'
        assert meta["tool_use_id"] == "toolu_spawn"
        assert meta["agent_id"] == "a88c3f920e0d92c99"
        assert meta["output_file"] == "/tmp/x.output"
        assert meta["full_content"] == "WRITE OK"

    def test_named_teammate_spawn_links_without_agent_id_text(self, tmp_path):
        result = tool_result(
            2,
            "toolu_spawn",
            "Spawned successfully.\nname: impl-m9",
            toolUseResult={
                "agentId": "aimpl-m9-cd8b",
                "status": "teammate_spawned",
                "name": "impl-m9",
            },
        )
        meta = {
            "name": "impl-m9",
            "color": "purple",
            "teamName": "session-18e9",
            "model": "opus",
            "spawnedAgentType": "general-purpose",
        }
        session = write_session(
            tmp_path,
            [
                assistant(
                    1,
                    [
                        tool_use(
                            "toolu_spawn",
                            "Agent",
                            description="Task 9",
                            prompt="p",
                            name="impl-m9",
                            subagent_type="general-purpose",
                        )
                    ],
                ),
                result,
            ],
            {"aimpl-m9-cd8b": {"meta": meta}},
        )
        (spawn,) = of_type(timeline(session), "subagent_spawn")
        m = spawn.metadata
        assert m["spawned_agent_id"] == "aimpl-m9-cd8b"
        assert (m["spawned_agent_name"], m["spawned_agent_color"]) == ("impl-m9", "purple")
        assert (m["team_name"], m["agent_model"], m["run_in_background"]) == (
            "session-18e9",
            "opus",
            False,
        )

    def test_scheduled_fire_is_one_event(self, tmp_path):
        session = write_session(
            tmp_path,
            [
                system(
                    1,
                    "scheduled_task_fire",
                    content="Running scheduled task",
                    taskId="6fdf7649",
                    cron="9,29,49 * * * *",
                    prompt="Scheduled check: read the DM",
                ),
                user(
                    1,
                    "Scheduled check: read the DM",
                    isMeta=True,
                    turnOrigin="scheduled",
                    scheduledTaskId="6fdf7649",
                    wakeupSource="schedule_wakeup",
                    promptSource="system",
                ),
            ],
        )
        events = timeline(session)
        (ev,) = of_type(events, "scheduled_fire")
        assert len(events) == 1
        assert ev.actor_type == "system"
        assert ev.metadata["cron"] == "9,29,49 * * * *"
        assert ev.metadata["task_id"] == "6fdf7649"
        assert ev.metadata["wakeup_source"] == "schedule_wakeup"
        assert ev.metadata["full_content"] == "Scheduled check: read the DM"

    def test_compaction_boundary_and_summary_are_one_event(self, tmp_path):
        session = write_session(
            tmp_path,
            [
                system(
                    1,
                    "compact_boundary",
                    content="Conversation compacted",
                    compactMetadata={"trigger": "auto", "preTokens": 155206},
                ),
                user(
                    2,
                    "This session is being continued from a previous conversation.\nSummary: did X",
                    isCompactSummary=True,
                ),
            ],
        )
        events = timeline(session)
        (ev,) = events
        assert ev.event_type == "compaction"
        assert (ev.metadata["trigger"], ev.metadata["pre_tokens"]) == ("auto", 155206)
        assert "did X" in ev.metadata["full_content"]

    def test_shell_command_pairs_input_with_output(self, tmp_path):
        session = write_session(
            tmp_path,
            [
                user(1, "<bash-input> gh auth status</bash-input>"),
                user(
                    2, "<bash-stdout>ok &lt;done&gt;</bash-stdout><bash-stderr>warn</bash-stderr>"
                ),
            ],
        )
        (ev,) = timeline(session)
        assert ev.event_type == "shell_command"
        assert (ev.actor, ev.actor_type) == ("user", "user")
        assert ev.metadata["command"] == "gh auth status"
        assert ev.metadata["result_content"] == "ok <done>"
        assert ev.metadata["stderr"] == "warn"

    def test_builtin_command_gets_its_output_and_no_caveat_event(self, tmp_path):
        session = write_session(
            tmp_path,
            [
                user(1, "<local-command-caveat>Caveat: ...</local-command-caveat>", isMeta=True),
                user(
                    1,
                    "<command-name>/model</command-name>\n<command-message>model</command-message>\n<command-args>fable</command-args>",
                ),
                user(1, "<local-command-stdout>Set model to Fable</local-command-stdout>"),
            ],
        )
        (ev,) = timeline(session)
        assert ev.event_type == "builtin_command"
        assert ev.metadata["result_content"] == "Set model to Fable"

    def test_system_local_command_entries_become_one_command_event(self, tmp_path):
        session = write_session(
            tmp_path,
            [
                system(
                    1,
                    "local_command",
                    content="<command-name>/remote-control</command-name>\n<command-message>remote-control</command-message>\n<command-args>wt</command-args>",
                    level="info",
                ),
                system(
                    1,
                    "local_command",
                    content="<local-command-stdout>Connected</local-command-stdout>",
                    level="info",
                    commandRun={"command": "remote-control", "args": "wt"},
                ),
            ],
        )
        (ev,) = timeline(session)
        assert ev.event_type == "builtin_command"
        assert ev.metadata["command_name"] == "remote-control"
        assert ev.metadata["result_content"] == "Connected"

    def test_system_notices(self, tmp_path):
        session = write_session(
            tmp_path,
            [
                system(1, "away_summary", content="We were reviewing the bot work."),
                system(
                    2, "informational", content="Safeguards stopped the response", level="notice"
                ),
                system(
                    3,
                    "model_refusal_fallback",
                    content="Switched to Opus 4.8.",
                    level="warning",
                    originalModel="fable",
                    fallbackModel="opus",
                ),
                system(
                    4,
                    "bridge_status",
                    content="/remote-control is active",
                    url="https://claude.ai/code/session_01",
                ),
                system(5, "stop_hook_summary", hookCount=2),
            ],
        )
        events = timeline(session)
        assert [e.event_type for e in events] == ["system_notice"] * 4
        assert [e.metadata["kind"] for e in events] == [
            "away_summary",
            "informational",
            "model_refusal_fallback",
            "bridge_status",
        ]
        assert events[1].metadata["level"] == "notice"
        assert events[3].metadata["url"] == "https://claude.ai/code/session_01"
        assert all(e.actor_type == "system" for e in events)

    def test_queued_attachments_surface_as_their_real_kind(self, tmp_path):
        session = write_session(
            tmp_path,
            [
                queued(1, "use the branch jay/x", {"kind": "human"}, humanTurn=True),
                queued(2, PEER_TEXT.split("\n", 1)[1], PEER_ORIGIN, isMeta=True),
                queued(3, TASK_NOTE, {"kind": "task-notification"}, mode="task-notification"),
            ],
        )
        events = timeline(session)
        assert [e.event_type for e in events] == ["prompt", "message", "task_notification"]
        assert all(e.metadata["queued"] is True for e in events)
        assert (events[0].actor, events[0].metadata["prompt_source"]) == ("user", "queued")
        assert events[0].metadata["full_content"] == "use the branch jay/x"
        assert events[1].actor_name == "airflow-72"

    def test_reply_to_an_address_is_named_after_its_sender(self, tmp_path):
        reply = tool_use(
            "toolu_sm",
            "SendMessage",
            to="uds:/tmp/cc-socks/10999.sock",
            recipient_kind="session",
            message="ANSWER: yes",
        )
        session = write_session(
            tmp_path,
            [user(1, PEER_TEXT, isMeta=True, origin=PEER_ORIGIN), assistant(2, [reply])],
        )
        incoming, outgoing = of_type(timeline(session), "message")
        assert outgoing.metadata["peer_name"] == "airflow-72"
        assert outgoing.title == "Message to airflow-72"

    def test_teammate_messages_to_the_lead_are_one_event_each(self, tmp_path):
        text = (
            "Another Claude session sent a message:\n"
            '<teammate-message teammate_id="spec-reader" color="purple" summary="Human test plan">\nPlan is ready.\n</teammate-message>\n\n'
            '<teammate-message teammate_id="impl-m9" color="orange">\nTask 9 done.\n</teammate-message>'
        )
        session = write_session(
            tmp_path,
            [user(1, text)],
            {"aimpl-m9-cd8b": {"meta": {"name": "impl-m9", "color": "orange"}}},
        )
        events = timeline(session)
        assert [e.event_type for e in events] == ["message", "message"]
        first, second = events
        assert (first.actor, first.actor_type, first.actor_color) == (
            "spec-reader",
            "subagent",
            "purple",
        )
        assert first.metadata["message_summary"] == "Human test plan"
        assert first.metadata["full_content"] == "Plan is ready."
        assert (second.actor, second.actor_name) == ("aimpl-m9-cd8b", "impl-m9")
        assert second.metadata["peer_agent_id"] == "aimpl-m9-cd8b"

    def test_teammate_idle_signal_is_quiet_context_from_the_agent(self, tmp_path):
        body = json.dumps(
            {
                "type": "idle_notification",
                "from": "impl-m9",
                "idleReason": "available",
                "result": "VERDICT: ready",
            }
        )
        text = (
            "Another Claude session sent a message:\n"
            f'<teammate-message teammate_id="impl-m9" color="purple">\n{body}\n</teammate-message>'
        )
        session = write_session(
            tmp_path,
            [user(1, text)],
            {"aimpl-m9-cd8b": {"meta": {"name": "impl-m9", "color": "purple"}}},
        )
        (ev,) = timeline(session)
        assert ev.event_type == "system_context"
        assert ev.metadata["kind"] == "agent_idle"
        assert (ev.actor, ev.actor_type) == ("aimpl-m9-cd8b", "subagent")
        assert (ev.actor_name, ev.actor_color) == ("impl-m9", "purple")
        assert ev.metadata["full_content"] == "VERDICT: ready"

    def test_other_teammate_json_stays_a_message_with_its_body(self, tmp_path):
        body = json.dumps({"type": "shutdown_request", "reason": "done"})
        text = (
            "Another Claude session sent a message:\n"
            f'<teammate-message teammate_id="impl-m9">\n{body}\n</teammate-message>'
        )
        (ev,) = timeline(write_session(tmp_path, [user(1, text)]))
        assert ev.event_type == "message"
        assert ev.metadata["full_content"] == body

    def test_command_after_a_caveat_is_a_builtin_even_if_unlisted(self, tmp_path):
        session = write_session(
            tmp_path,
            [
                user(1, "<local-command-caveat>Caveat: ...</local-command-caveat>", isMeta=True),
                user(
                    2,
                    "<command-name>/not-in-any-list</command-name>\n<command-message>not-in-any-list</command-message>",
                ),
                user(3, "plain question", origin={"kind": "human"}),
                user(
                    4,
                    "<command-name>/my-custom-thing</command-name>\n<command-message>my-custom-thing</command-message>",
                ),
            ],
        )
        local, prompt, custom = timeline(session)
        assert (local.event_type, local.title) == ("builtin_command", "Built-in: /not-in-any-list")
        assert prompt.event_type == "prompt"
        assert custom.event_type != "builtin_command"

    def test_meta_flag_does_not_hide_a_human_origin(self, tmp_path):
        session = write_session(
            tmp_path, [queued(1, "leave the simulator alone", {"kind": "human"}, isMeta=True)]
        )
        (ev,) = timeline(session)
        assert (ev.event_type, ev.actor) == ("prompt", "user")

    def test_interrupt_marker_is_not_a_prompt(self, tmp_path):
        session = write_session(
            tmp_path, [user(1, [{"type": "text", "text": "[Request interrupted by user]"}])]
        )
        (ev,) = timeline(session)
        assert ev.event_type == "system_notice"
        assert ev.metadata["kind"] == "interrupted"

    def test_tool_error_uses_is_error(self, tmp_path):
        session = write_session(
            tmp_path,
            [
                assistant(
                    1,
                    [
                        tool_use("t_ok", "Read", file_path="/x/error.log"),
                        tool_use("t_bad", "Bash", command="false"),
                    ],
                ),
                tool_result(
                    2, "t_ok", "error: this is file content, not a failure", is_error=False
                ),
                tool_result(3, "t_bad", "exit code 1", is_error=True),
            ],
        )
        by_id = {e.metadata["tool_id"]: e for e in of_type(timeline(session), "tool_call")}
        assert by_id["t_ok"].metadata["result_status"] == "success"
        assert by_id["t_bad"].metadata["result_status"] == "error"


class TestSubagentTimeline:
    def _agent_timeline(self, tmp_path, entries, meta=None, others=None):
        agent_id = "aimpl-m9-cd8b"
        for e in entries:
            e["agentId"] = agent_id
            e["isSidechain"] = True
        subs = {agent_id: {"entries": entries, "meta": meta}, **(others or {})}
        session = write_session(tmp_path, [user(0, "go")], subs)
        agent = next(a for a in session.list_subagents() if a.agent_id == agent_id)
        registry = build_agent_registry(session.list_subagent_paths())
        return build_conversation_timeline(
            conversation=agent,
            working_dirs=[],
            actor=agent_id,
            actor_type="subagent",
            agent_registry=registry,
        )

    def test_first_teammate_message_is_the_task_prompt(self, tmp_path):
        first = '<teammate-message teammate_id="team-lead" summary="Implement Task 9">\nYou are implementing Task 9.\n</teammate-message>'
        later = '<teammate-message teammate_id="team-lead" summary="Fix round 1">\nFix the review items.\n</teammate-message>'
        events = self._agent_timeline(
            tmp_path,
            [user(1, first), assistant(2, [{"type": "text", "text": "x" * 80}]), user(3, later)],
            meta={"name": "impl-m9", "color": "purple"},
        )
        prompt, response, message = events
        assert prompt.event_type == "prompt" and prompt.title == "Task prompt"
        assert prompt.metadata["is_task_prompt"] is True
        assert (prompt.actor_type, prompt.actor_name) == ("session", "team-lead")
        assert prompt.metadata["full_content"] == "You are implementing Task 9."
        assert (response.actor, response.actor_name, response.actor_color) == (
            "aimpl-m9-cd8b",
            "impl-m9",
            "purple",
        )
        assert message.event_type == "message"
        assert message.metadata["direction"] == "in"
        assert message.metadata["message_summary"] == "Fix round 1"
        assert message.metadata["full_content"] == "Fix the review items."
        assert (message.actor, message.actor_type) == ("team-lead", "session")

    def test_coordinator_message_and_reminder(self, tmp_path):
        events = self._agent_timeline(
            tmp_path,
            [
                user(1, "Review the diff"),
                user(
                    2,
                    "The coordinator sent a message while you were working:\nVerify 3161b7d.",
                    isMeta=True,
                    origin={"kind": "coordinator"},
                ),
                user(
                    3,
                    "<system-reminder>\nOther agents active in this session\n</system-reminder>",
                    isMeta=True,
                ),
            ],
        )
        assert [e.event_type for e in events] == ["prompt", "message", "system_context"]
        assert events[0].metadata["is_task_prompt"] is True
        assert events[1].metadata["full_content"] == "Verify 3161b7d."
        assert (events[1].actor, events[1].actor_type) == ("coordinator", "session")

    def test_workflow_task_at_the_same_timestamp_joins_the_task_prompt(self, tmp_path):
        events = self._agent_timeline(
            tmp_path,
            [
                user(1, "[Workflow harness — user request] The user asked for a review."),
                user(1, "[Workflow harness — computed task] Review file a.py."),
            ],
        )
        (ev,) = events
        assert ev.metadata["is_task_prompt"] is True
        assert "user request" in ev.metadata["full_content"]
        assert "computed task" in ev.metadata["full_content"]


class TestTimelineCacheVersion:
    def test_etag_carries_the_format_version(self):
        from services.conversation_endpoints import TIMELINE_FORMAT_VERSION, timeline_etag

        assert timeline_etag('"abc"') == f'"abc-t{TIMELINE_FORMAT_VERSION}"'
        assert timeline_etag(None) is None

    def test_stale_etag_is_not_rescued_by_if_modified_since(self):
        pytest.importorskip("starlette")  # the models-only CI job has no web deps
        from datetime import datetime, timezone

        from starlette.requests import Request

        from http_caching import check_conditional_request, format_http_date

        modified = datetime(2026, 11, 1, tzinfo=timezone.utc)
        headers = [
            (b"if-none-match", b'"old-shape"'),
            (b"if-modified-since", format_http_date(modified).encode()),
        ]
        request = Request({"type": "http", "headers": headers})
        assert check_conditional_request(request, '"new-shape"', modified) is None
        fresh = Request({"type": "http", "headers": [(b"if-none-match", b'"new-shape"')]})
        assert check_conditional_request(fresh, '"new-shape"', modified).status_code == 304


class TestStableEventIds:
    def _entries(self) -> list:
        return [
            user(1, "hello", origin={"kind": "human"}),
            assistant(
                2,
                [
                    {"type": "thinking", "thinking": "hmm"},
                    {"type": "text", "text": "x" * 80},
                    tool_use("toolu_1", "Read", file_path="/x"),
                ],
            ),
            system(3, "away_summary", content="We were reviewing the bot work."),
            queued(4, "use the branch jay/x", {"kind": "human"}),
            user(5, "next", origin={"kind": "human"}),
        ]

    def test_ids_are_unique(self, tmp_path):
        ids = [e.id for e in timeline(write_session(tmp_path, self._entries()))]
        assert len(ids) == len(set(ids)) == 7

    def test_appending_entries_keeps_every_earlier_id(self, tmp_path):
        entries = self._entries()
        before = {e.id: (e.event_type, e.title) for e in timeline(write_session(tmp_path, entries))}
        more = entries + [
            assistant(6, [tool_use("toolu_2", "Bash", command="ls")]),
            system(7, "informational", content="note", level="notice"),
            user(8, "third", origin={"kind": "human"}),
        ]
        after = {e.id: (e.event_type, e.title) for e in timeline(write_session(tmp_path, more))}
        assert len(after) == len(before) + 3
        assert {k: after.get(k) for k in before} == before

    def test_ids_come_from_the_entry_uuid(self, tmp_path):
        entry = user(1, "hello", origin={"kind": "human"})
        (ev,) = timeline(write_session(tmp_path, [entry]))
        assert entry["uuid"] in ev.id

    def test_messages_in_one_entry_get_distinct_ids(self, tmp_path):
        text = (
            "Another Claude session sent a message:\n"
            '<teammate-message teammate_id="a">\none\n</teammate-message>\n\n'
            '<teammate-message teammate_id="b">\ntwo\n</teammate-message>'
        )
        first, second = timeline(write_session(tmp_path, [user(1, text)]))
        assert first.id != second.id

    def test_repeated_uuid_still_yields_unique_ids(self, tmp_path):
        entry = user(1, "hello", origin={"kind": "human"})
        twin = {**entry, "timestamp": _ts(2)}
        ids = [e.id for e in timeline(write_session(tmp_path, [entry, twin]))]
        assert len(set(ids)) == 2


class TestReviewFixes:
    def test_forked_agent_task_prompt_rides_on_a_tool_result(self, tmp_path):
        first = user(
            1,
            [
                {"type": "tool_result", "tool_use_id": "toolu_fork", "content": "Fork started"},
                {
                    "type": "text",
                    "text": "<fork-boilerplate>\nYou are a worker fork.\n</fork-boilerplate>\n\nRecord the inventory.",
                },
            ],
        )
        entries = [
            assistant(0, [tool_use("toolu_fork", "Agent", description="d", prompt="p")]),
            first,
            assistant(2, [{"type": "text", "text": "y" * 80}]),
        ]
        for e in entries:
            e["agentId"], e["isSidechain"] = "afork1", True
        session = write_session(tmp_path, [user(0, "go")], {"afork1": {"entries": entries}})
        agent = session.list_subagents()[0]
        events = build_conversation_timeline(
            conversation=agent, working_dirs=[], actor="afork1", actor_type="subagent"
        )
        prompts = of_type(events, "prompt")
        assert len(prompts) == 1
        assert prompts[0].metadata["is_task_prompt"] is True
        assert "Record the inventory." in prompts[0].metadata["full_content"]
        assert "Fork started" not in prompts[0].metadata["full_content"]

    def test_raw_source_key_does_not_break_parsing(self):
        msg = parse_message(user(1, "hello", source="cli", origin={"kind": "human"}))
        assert msg.source == "human"
        peer = parse_message(user(1, PEER_TEXT, isMeta=True, origin=PEER_ORIGIN, source="human"))
        assert peer.source == "peer_session"

    def test_initial_prompt_skips_messages_from_agents_and_sessions(self, tmp_path):
        from utils import get_initial_prompt

        teammate = (
            "Another Claude session sent a message:\n"
            '<teammate-message teammate_id="spec-reader">\nPlan is ready.\n</teammate-message>'
        )
        session = write_session(
            tmp_path,
            [
                user(1, teammate),
                user(2, PEER_TEXT, isMeta=True, origin=PEER_ORIGIN),
                user(3, TASK_NOTE),
                user(4, "the real first prompt", origin={"kind": "human"}),
            ],
        )
        assert get_initial_prompt(session) == "the real first prompt"

    def test_bad_queued_attachment_does_not_fail_the_timeline(self, tmp_path):
        bad_image = queued(1, "x", {"kind": "human"})
        bad_image["attachment"]["prompt"] = [
            {"type": "image", "source": "not-a-dict"},
            {"type": "text", "text": "look"},
        ]
        bad_origin = queued(2, "y", {"kind": "human"})
        bad_origin["attachment"]["origin"] = "human"
        no_time = queued(3, "z", {"kind": "human"})
        no_time["timestamp"] = None
        no_time["attachment"]["timestamp"] = {"bad": 1}
        session = write_session(
            tmp_path, [bad_image, bad_origin, no_time, user(4, "ok", origin={"kind": "human"})]
        )
        events = timeline(session)
        assert [e.metadata["full_content"] for e in of_type(events, "prompt")] == [
            "look",
            "y",
            "ok",
        ]

    def test_duplicate_teammate_names_resolve_by_spawn_time(self, tmp_path):
        def spawn(sec, tool_id, agent_id):
            return [
                assistant(
                    sec,
                    [
                        tool_use(
                            tool_id, "Agent", description="review", prompt="p", name="code-review"
                        )
                    ],
                ),
                tool_result(sec + 1, tool_id, "Spawned.", toolUseResult={"agentId": agent_id}),
            ]

        def says(sec, text):
            wrapped = f'<teammate-message teammate_id="code-review">\n{text}\n</teammate-message>'
            return user(sec, "Another Claude session sent a message:\n" + wrapped)

        meta = {"name": "code-review", "color": "blue"}
        session = write_session(
            tmp_path,
            [
                *spawn(1, "t1", "acr-1"),
                says(5, "first review"),
                *spawn(10, "t2", "acr-2"),
                says(15, "second review"),
            ],
            {"acr-1": {"meta": meta}, "acr-2": {"meta": {**meta, "color": "green"}}},
        )
        first, second = of_type(timeline(session), "message")
        assert first.metadata["peer_agent_id"] == "acr-1"
        assert second.metadata["peer_agent_id"] == "acr-2"

    def test_ambiguous_name_without_spawn_events_is_left_unlinked(self, tmp_path):
        wrapped = '<teammate-message teammate_id="code-review">\nhi\n</teammate-message>'
        meta = {"name": "code-review"}
        session = write_session(
            tmp_path,
            [user(1, "Another Claude session sent a message:\n" + wrapped)],
            {"acr-1": {"meta": meta}, "acr-2": {"meta": meta}},
        )
        (ev,) = timeline(session)
        assert ev.metadata["peer_agent_id"] is None
        assert (ev.actor, ev.actor_type) == ("code-review", "subagent")

    def test_mcp_error_text_without_is_error(self, tmp_path):
        session = write_session(
            tmp_path,
            [
                assistant(
                    1, [tool_use("t1", "mcp__dev-tools__x"), tool_use("t2", "mcp__dev-tools__y")]
                ),
                tool_result(
                    2,
                    "t1",
                    '{"result":"An error occurred (code: GEN-ERR-12). Check mcp_errors.log"}',
                ),
                tool_result(3, "t2", '{"result":"Found 2 results: An error occurred earlier"}'),
            ],
        )
        by_id = {
            e.metadata["tool_id"]: e.metadata["result_status"]
            for e in of_type(timeline(session), "tool_call")
        }
        assert by_id == {"t1": "error", "t2": "success"}

    def test_agent_initial_prompt_when_first_message_is_from_a_teammate(self, tmp_path):
        from collectors import collect_agent_data

        first = '<teammate-message teammate_id="team-lead" summary="Task 9">\nImplement Task 9.\n</teammate-message>'
        entries = [
            user(1, first),
            assistant(2, [{"type": "text", "text": "y" * 80}]),
            user(3, "later", origin={"kind": "human"}),
        ]
        for e in entries:
            e["agentId"], e["isSidechain"] = "aimpl-1", True
        session = write_session(tmp_path, [user(0, "go")], {"aimpl-1": {"entries": entries}})
        data = collect_agent_data(session.list_subagents()[0])
        assert "Implement Task 9." in data.initial_prompt
        assert "later" not in data.initial_prompt

    def test_prompt_summary_drops_pasted_content_wrappers(self, tmp_path):
        text = '\n\n<pasted_content id="5d34">\nContinue the rework.\n</pasted_content>'
        (ev,) = timeline(write_session(tmp_path, [user(1, text, origin={"kind": "human"})]))
        assert ev.summary == "Continue the rework."
        assert ev.metadata["full_content"] == text


class TestWrapperParsing:
    PROSE = (
        "Your directive: handle incoming messages: cross-session "
        "(`<cross-session-message from= from-name=>`), `<agent-message from=>`, "
        "`<teammate-message teammate_id= summary=>`, and the coordinator form."
    )

    def test_tags_mentioned_in_prose_are_not_wrappers(self):
        from services.timeline_parsing import clean_task_prompt, parse_wrapped_messages

        (only,) = parse_wrapped_messages(self.PROSE)
        assert only.wrapper is None
        assert only.body == self.PROSE
        fork = "<fork-boilerplate>\nYou are a worker fork.\n</fork-boilerplate>\n\n" + self.PROSE
        assert clean_task_prompt(fork) == self.PROSE

    def test_wrapped_body_that_mentions_tags_is_kept_whole(self):
        from services.timeline_parsing import parse_wrapped_messages

        body = "Close it with </teammate-message> and open with <teammate-message teammate_id= >."
        text = (
            f'<teammate-message teammate_id="team-lead" summary="s">\n{body}\n</teammate-message>'
        )
        (only,) = parse_wrapped_messages("Another Claude session sent a message:\n" + text)
        assert (only.wrapper, only.sender_name) == ("teammate-message", "team-lead")
        assert only.body == body

    def test_several_wrapped_messages_in_a_row_are_split(self):
        from services.timeline_parsing import parse_wrapped_messages

        text = (
            '<teammate-message teammate_id="a">\none\n</teammate-message>\n\n'
            '<teammate-message teammate_id="b">\ntwo\n</teammate-message>'
        )
        assert [(m.sender_name, m.body) for m in parse_wrapped_messages(text)] == [
            ("a", "one"),
            ("b", "two"),
        ]

    def test_fork_task_prompt_in_the_timeline_keeps_its_prose(self, tmp_path):
        first = user(
            1,
            [
                {"type": "tool_result", "tool_use_id": "toolu_fork", "content": "Fork started"},
                {"type": "text", "text": self.PROSE},
            ],
        )
        first["agentId"], first["isSidechain"] = "afork2", True
        session = write_session(tmp_path, [user(0, "go")], {"afork2": {"entries": [first]}})
        (ev,) = build_conversation_timeline(
            conversation=session.list_subagents()[0],
            working_dirs=[],
            actor="afork2",
            actor_type="subagent",
        )
        assert ev.metadata["full_content"] == self.PROSE


class TestAgentTypeOnEvents:
    META = {"name": "impl-m9", "spawnedAgentType": "feature-dev:code-reviewer"}

    def _session(self, tmp_path, entries):
        return write_session(tmp_path, entries, {"aimpl-m9-cd8b": {"meta": self.META}})

    def test_messages_name_the_peer_agents_type(self, tmp_path):
        incoming = (
            "Another Claude session sent a message:\n"
            '<teammate-message teammate_id="impl-m9">\nTask 9 done.\n</teammate-message>'
        )
        outgoing = tool_use(
            "t_sm", "SendMessage", to="impl-m9", recipient_kind="name", message="go"
        )
        stranger = tool_use(
            "t_sm2", "SendMessage", to="uds:/tmp/x.sock", recipient_kind="session", message="hi"
        )
        events = timeline(
            self._session(tmp_path, [user(1, incoming), assistant(2, [outgoing, stranger])])
        )
        came, went, other = of_type(events, "message")
        assert came.actor_agent_type == "feature-dev:code-reviewer"
        assert came.metadata["peer_agent_type"] == "feature-dev:code-reviewer"
        assert went.metadata["peer_agent_type"] == "feature-dev:code-reviewer"
        assert went.actor_agent_type is None
        assert other.metadata["peer_agent_type"] is None

    def test_idle_row_and_task_notification_name_the_agents_type(self, tmp_path):
        idle = json.dumps(
            {"type": "idle_notification", "from": "impl-m9", "idleReason": "available"}
        )
        idle_text = (
            "Another Claude session sent a message:\n"
            f'<teammate-message teammate_id="impl-m9">\n{idle}\n</teammate-message>'
        )
        note = TASK_NOTE.replace("a88c3f920e0d92c99", "aimpl-m9-cd8b").replace(
            "toolu_spawn", "t_none"
        )
        shell = TASK_NOTE.replace("a88c3f920e0d92c99", "bsh123456").replace(
            'Agent "Probe write" finished', 'Background command "x" completed (exit code 0)'
        )
        events = timeline(
            self._session(tmp_path, [user(1, idle_text), user(2, note), user(3, shell)])
        )
        (idle_row,) = of_type(events, "system_context")
        assert idle_row.actor_agent_type == "feature-dev:code-reviewer"
        assert idle_row.metadata["agent_type"] == "feature-dev:code-reviewer"
        agent_note, shell_note = of_type(events, "task_notification")
        assert agent_note.metadata["agent_type"] == "feature-dev:code-reviewer"
        assert shell_note.metadata.get("agent_type") is None

    def test_type_from_the_spawn_call_when_the_agent_has_no_meta(self, tmp_path):
        spawn = assistant(
            1, [tool_use("t_spawn", "Agent", description="d", prompt="p", subagent_type="Explore")]
        )
        result = tool_result(
            2, "t_spawn", "done\nagentId: a1b2c3d4e5", toolUseResult={"agentId": "a1b2c3d4e5"}
        )
        note = TASK_NOTE.replace("a88c3f920e0d92c99", "a1b2c3d4e5").replace(
            "toolu_spawn", "t_spawn"
        )
        events = timeline(write_session(tmp_path, [spawn, result, user(3, note)]))
        (agent_note,) = of_type(events, "task_notification")
        assert agent_note.metadata["agent_type"] == "Explore"

    def test_unlinked_sender_has_no_type(self, tmp_path):
        text = (
            "Another Claude session sent a message:\n"
            '<teammate-message teammate_id="stranger">\nhello\n</teammate-message>'
        )
        (ev,) = timeline(write_session(tmp_path, [user(1, text)]))
        assert (ev.actor_type, ev.actor_agent_type) == ("subagent", None)
        assert ev.metadata["peer_agent_type"] is None
