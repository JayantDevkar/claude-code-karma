"""Agent files and types the indexer sees: named teammates, nested workflow agents, session names."""

from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from db import indexer
from db.schema import ensure_schema
from models.agent import Agent
from models.session import Session
from models.side_entries import read_session_name
from services.agent_registry import build_agent_registry
from services.session_copies import subagent_files
from services.subagent_types import get_all_subagent_types

SID = "22222222-3333-4444-5555-666666666666"
TEAMMATE = "abuilder-00aa11bb22cc33dd"
PLAIN = "a0123456789abcdef"
NESTED = "a1111111111111111"


def _ts(minute: int) -> str:
    return f"2026-11-02T09:{minute:02d}:00.000Z"


def _user(minute: int, content, **extra) -> dict:
    return {
        "type": "user",
        "uuid": f"u-{minute}-{extra.get('agentId', 'main')}",
        "timestamp": _ts(minute),
        "sessionId": SID,
        "message": {"role": "user", "content": content},
        **extra,
    }


def _assistant(minute: int, blocks: list, **extra) -> dict:
    return {
        "type": "assistant",
        "uuid": f"a-{minute}-{extra.get('agentId', 'main')}",
        "timestamp": _ts(minute),
        "sessionId": SID,
        "message": {"role": "assistant", "model": "claude-fable-5-2", "content": blocks},
        **extra,
    }


def _spawn(minute: int, tool_id: str, agent_id: str, result_text: str, **tool_input) -> list:
    use = {"type": "tool_use", "id": tool_id, "name": "Agent", "input": tool_input}
    result = {"type": "tool_result", "tool_use_id": tool_id, "content": result_text}
    return [
        _assistant(minute, [use]),
        _user(minute, [result], toolUseResult={"agentId": agent_id}),
    ]


def _write(path: Path, entries: list) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(json.dumps(e) for e in entries) + "\n")
    return path


def _agent(directory: Path, agent_id: str, first: str, meta: dict | None) -> None:
    side = {"agentId": agent_id, "isSidechain": True}
    _write(directory / f"agent-{agent_id}.jsonl", [_user(5, first, **side)])
    if meta is not None:
        (directory / f"agent-{agent_id}.meta.json").write_text(json.dumps(meta))


@pytest.fixture
def team_session(tmp_path) -> Path:
    project = tmp_path / "projects" / "-home-alice-project"
    main = [
        {"type": "agent-name", "agentName": "first-name", "sessionId": SID},
        _user(0, "start"),
        # A named teammate: the result text has no "agentId:" line
        *_spawn(
            1,
            "toolu_team",
            TEAMMATE,
            "Spawned successfully.",
            description="Build the parser",
            prompt="Build the parser.",
            name="builder",
            subagent_type="example-plugin:reviewer",
        ),
        # No subagent_type in the call
        *_spawn(2, "toolu_plain", PLAIN, "Done.", description="Notes", prompt="Write notes."),
        {"type": "agent-name", "agentName": "docs-site", "sessionId": SID},
    ]
    jsonl = _write(project / f"{SID}.jsonl", main)
    subagents = project / SID / "subagents"
    wrapped = '<teammate-message teammate_id="team-lead">\nBuild the parser.\n</teammate-message>'
    _agent(subagents, TEAMMATE, wrapped, {"agentType": "builder", "name": "builder"})
    _agent(subagents, PLAIN, "Write notes.", {"agentType": "general-purpose"})
    workflow = subagents / "workflows" / "wf_00000000-000"
    _agent(workflow, NESTED, "[Workflow harness] task", {"agentType": "workflow-subagent"})
    _write(workflow / "journal.jsonl", [{"type": "started", "agentId": NESTED}])
    return jsonl


@pytest.fixture
def mem_db():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    ensure_schema(conn)
    return conn


def _index(conn, jsonl_path: Path) -> None:
    Session.clear_all_caches()
    stat = jsonl_path.stat()
    indexer._index_session(conn, jsonl_path, jsonl_path.parent.name, stat.st_mtime, stat.st_size)
    conn.commit()


class TestAgentFiles:
    def test_nested_workflow_agents_are_listed_and_journals_are_not(self, team_session):
        names = sorted(p.name for p in subagent_files(team_session))
        assert names == sorted(f"agent-{a}.jsonl" for a in (TEAMMATE, PLAIN, NESTED))

    def test_session_lists_the_nested_agent(self, team_session):
        session = Session.from_path(team_session)
        agents = {a.agent_id: a for a in session.list_subagents()}
        assert set(agents) == {TEAMMATE, PLAIN, NESTED}
        assert agents[NESTED].parent_session_uuid == SID

    def test_agent_id_comes_from_the_whole_file_name(self, tmp_path):
        path = tmp_path / SID / "subagents" / f"agent-{TEAMMATE}.jsonl"
        path.parent.mkdir(parents=True)
        path.write_text("")
        assert Agent.from_path(path).agent_id == TEAMMATE

    def test_a_meta_file_reached_twice_does_not_make_a_name_ambiguous(self, team_session):
        subagents = team_session.parent / SID / "subagents"
        (subagents / "workflows" / "wf_00000000-000" / f"agent-{NESTED}.meta.json").write_text(
            json.dumps({"agentType": "workflow-subagent", "name": "nested-one"})
        )
        registry = build_agent_registry(subagent_files(team_session), extra_dirs=[subagents])
        assert registry.by_name("nested-one").agent_id == NESTED
        assert registry.by_name("builder").agent_id == TEAMMATE


class TestIndexedTypes:
    def test_named_teammate_gets_the_spawn_calls_type(self, team_session):
        types = get_all_subagent_types(team_session, subagent_files(team_session))
        assert types[TEAMMATE] == "example-plugin:reviewer"

    def test_spawn_without_a_type_uses_the_meta_type(self, team_session):
        types = get_all_subagent_types(team_session, subagent_files(team_session))
        assert types[PLAIN] == "general-purpose"
        assert types[NESTED] == "workflow-subagent"

    def test_meta_type_that_repeats_the_name_is_not_used(self, team_session):
        # Drop the spawn call's type: only the meta is left, and its agentType is just the name
        entries = [json.loads(line) for line in team_session.read_text().splitlines()]
        for entry in entries:
            for block in (entry.get("message") or {}).get("content") or []:
                if isinstance(block, dict) and block.get("id") == "toolu_team":
                    del block["input"]["subagent_type"]
        _write(team_session, entries)
        types = get_all_subagent_types(team_session, subagent_files(team_session))
        assert types[TEAMMATE] == "_teammate"

    def test_system_agents_keep_their_marker(self, team_session):
        subagents = team_session.parent / SID / "subagents"
        _agent(subagents, "acompact-0a1b2c", "Summarise.", {"agentType": "compact"})
        types = get_all_subagent_types(team_session, subagent_files(team_session))
        assert types["acompact-0a1b2c"] == "_compact"

    def test_indexer_stores_real_types_for_every_agent(self, mem_db, team_session):
        _index(mem_db, team_session)
        rows = dict(
            mem_db.execute("SELECT agent_id, subagent_type FROM subagent_invocations").fetchall()
        )
        assert rows == {
            TEAMMATE: "example-plugin:reviewer",
            PLAIN: "general-purpose",
            NESTED: "workflow-subagent",
        }
        count = mem_db.execute("SELECT subagent_count FROM sessions").fetchone()[0]
        assert count == 3


class TestSessionName:
    def test_latest_agent_name_entry_is_the_session_name(self, team_session):
        assert read_session_name(team_session) == "docs-site"

    def test_no_agent_name_entry_means_no_name(self, tmp_path):
        path = _write(tmp_path / "s.jsonl", [_user(0, 'I mention "agent-name" in a prompt')])
        assert read_session_name(path) is None
        assert read_session_name(tmp_path / "missing.jsonl") is None

    def test_indexer_stores_the_session_name(self, mem_db, team_session):
        _index(mem_db, team_session)
        assert mem_db.execute("SELECT session_name FROM sessions").fetchone()[0] == "docs-site"


SPLIT = "a2222222222222222"


def _reply(minute: int, text: str, tokens: int, request_id: str, **extra) -> dict:
    entry = _assistant(minute, [{"type": "text", "text": text}], **extra)
    entry["uuid"] = f"a-{request_id}"
    entry["requestId"] = request_id
    entry["message"]["id"] = f"msg_{request_id}"
    entry["message"]["usage"] = {"input_tokens": tokens, "output_tokens": tokens}
    return entry


@pytest.fixture
def split_agent_session(tmp_path) -> Path:
    """One workflow agent whose transcript continues in a second file at the top level."""
    project = tmp_path / "projects" / "-home-alice-project"
    jsonl = _write(project / f"{SID}.jsonl", [_user(0, "start")])
    subagents = project / SID / "subagents"
    side = {"agentId": SPLIT, "isSidechain": True}
    run_dir = subagents / "workflows" / "wf_00000000-000"
    _write(
        run_dir / f"agent-{SPLIT}.jsonl",
        [
            _user(10, "[Workflow harness] review a.py", **side),
            _reply(11, "first", 100, "r1", **side),
        ],
    )
    (run_dir / f"agent-{SPLIT}.meta.json").write_text(
        json.dumps({"agentType": "workflow-subagent"})
    )
    # The continuation: starts with an assistant entry, has no meta.json
    _write(
        subagents / f"agent-{SPLIT}.jsonl",
        [_reply(20, "second", 40, "r2", **side), _user(21, "one more thing", **side)],
    )
    return jsonl


class TestAgentWithTwoSegments:
    def test_both_files_are_listed_not_merged_as_copies(self, split_agent_session):
        files = subagent_files(split_agent_session)
        assert len(files) == 2
        assert {p.name for p in files} == {f"agent-{SPLIT}.jsonl"}

    def test_session_sees_one_agent_made_of_both_files(self, split_agent_session):
        session = Session.from_path(split_agent_session)
        (agent,) = session.list_subagents()
        assert agent.agent_id == SPLIT
        assert session.count_subagents() == 1
        # The workflow run comes first, the top-level file continues it
        assert "workflows" in agent.jsonl_path.parts
        assert len(agent.segment_paths) == 1
        texts = [getattr(m, "content", None) or m.text_content for m in agent.iter_messages()]
        assert texts == ["[Workflow harness] review a.py", "first", "second", "one more thing"]

    def test_usage_of_both_segments_is_summed(self, split_agent_session):
        (agent,) = Session.from_path(split_agent_session).list_subagents()
        usage = agent.get_usage_summary()
        assert (usage.input_tokens, usage.output_tokens) == (140, 140)
        assert agent.message_count == 4

    def test_a_change_in_the_second_file_refreshes_the_agent(self, split_agent_session):
        import os

        (agent,) = Session.from_path(split_agent_session).list_subagents()
        assert agent.message_count == 4
        second = agent.segment_paths[0]
        side = {"agentId": SPLIT, "isSidechain": True}
        with open(second, "a") as f:
            f.write(json.dumps(_reply(22, "third", 5, "r3", **side)) + "\n")
        stat = second.stat()
        os.utime(second, ns=(stat.st_atime_ns, stat.st_mtime_ns + 2_000_000_000))
        (again,) = Session.from_path(split_agent_session).list_subagents()
        assert again.message_count == 5

    def test_indexer_stores_one_row_with_the_summed_usage(self, mem_db, split_agent_session):
        _index(mem_db, split_agent_session)
        rows = mem_db.execute(
            "SELECT agent_id, subagent_type, input_tokens, output_tokens FROM subagent_invocations"
        ).fetchall()
        assert [tuple(r) for r in rows] == [(SPLIT, "workflow-subagent", 140, 140)]
        session = mem_db.execute(
            "SELECT subagent_count, subagent_output_tokens FROM sessions"
        ).fetchone()
        assert tuple(session) == (1, 140)

    def test_timeline_of_the_agent_covers_both_segments(self, split_agent_session):
        from services.conversation_endpoints import build_conversation_timeline

        (agent,) = Session.from_path(split_agent_session).list_subagents()
        events = build_conversation_timeline(
            conversation=agent, working_dirs=[], actor=SPLIT, actor_type="subagent"
        )
        assert [e.event_type for e in events] == ["prompt", "message"]
        assert events[0].metadata["is_task_prompt"] is True
        assert events[1].metadata["full_content"] == "one more thing"
        assert len({e.id for e in events}) == 2


def test_each_meta_file_is_read_once(team_session, monkeypatch):
    import services.agent_registry as agent_registry

    read = []
    real = agent_registry._read_meta
    monkeypatch.setattr(agent_registry, "_read_meta", lambda p: read.append(p) or real(p))
    subagents = team_session.parent / SID / "subagents"
    build_agent_registry(subagent_files(team_session), extra_dirs=[subagents])
    assert len(read) == len(set(read)) == 3
