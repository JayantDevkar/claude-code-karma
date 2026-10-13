"""Each subagent file is parsed once per version, shared by every collector and request."""

from __future__ import annotations

import json
import os
import sys
import threading
from collections import Counter
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from collectors import collect_session_data, collect_subagent_info
from models.agent import Agent
from models.session import Session


def _line(kind: str, uuid: str, content) -> str:
    message = {"role": kind, "content": content}
    if kind == "assistant":
        message.update({"id": f"msg_{uuid}", "model": "claude-opus-4-5-20251101", "usage": {}})
    return json.dumps(
        {"type": kind, "uuid": uuid, "timestamp": "2026-10-01T09:00:00Z", "message": message}
    )


def _tool(uuid: str, name: str, **tool_input) -> str:
    return _line(
        "assistant",
        uuid,
        [{"type": "tool_use", "id": f"toolu_{uuid}", "name": name, "input": tool_input}],
    )


@pytest.fixture
def session_with_subagents(tmp_path: Path) -> Session:
    project = tmp_path / "-p"
    agents = project / "s1" / "subagents"
    agents.mkdir(parents=True)
    main = project / "s1.jsonl"
    main.write_text(
        _line("user", "u0", "do the thing") + "\n" + _tool("m1", "Bash", command="ls") + "\n"
    )
    for i in range(3):
        (agents / f"agent-a{i}.jsonl").write_text(
            "\n".join(
                [
                    _line("user", f"a{i}u", f"subtask {i}"),
                    _tool(f"a{i}r", "Read", file_path=f"/repo/file{i}.py"),
                    _tool(f"a{i}g", "Grep", pattern="x"),
                ]
            )
            + "\n"
        )
    return Session.from_path(main, claude_base_dir=tmp_path)


@pytest.fixture
def parses(monkeypatch) -> Counter:
    """Count full reads of each subagent file."""
    counts: Counter = Counter()
    real = Agent.iter_messages

    def counting(self):
        counts[self.agent_id] += 1
        return real(self)

    monkeypatch.setattr(Agent, "iter_messages", counting)
    return counts


def test_collected_data_from_subagents(session_with_subagents):
    data = collect_session_data(session_with_subagents, include_subagents=True)

    assert data.session_tool_counts == Counter({"Bash": 1})
    assert data.subagent_tool_counts == Counter({"Read": 3, "Grep": 3})
    assert sorted(
        (op.path, op.actor) for op in data.file_operations if op.actor_type == "subagent"
    ) == [
        ("/repo/file0.py", "a0"),
        ("/repo/file1.py", "a1"),
        ("/repo/file2.py", "a2"),
    ]

    infos = collect_subagent_info(
        session_with_subagents, collect_session_data(session_with_subagents), {}
    )
    assert [(i.agent_id, i.initial_prompt, i.tool_counts) for i in infos] == [
        (f"a{i}", f"subtask {i}", Counter({"Read": 1, "Grep": 1})) for i in range(3)
    ]


def test_each_subagent_file_is_parsed_once(session_with_subagents, parses):
    session = session_with_subagents
    collect_session_data(session, include_subagents=True)
    collect_session_data(session, include_subagents=True)
    collect_subagent_info(session, collect_session_data(session), {})

    assert parses == Counter({"a0": 1, "a1": 1, "a2": 1})


def test_a_changed_subagent_file_is_parsed_again(session_with_subagents, parses):
    session = session_with_subagents
    collect_session_data(session, include_subagents=True)
    changed = session.subagents_dir / "agent-a1.jsonl"
    with open(changed, "a") as fh:
        fh.write(_tool("a1w", "Write", file_path="/repo/new.py", content="x") + "\n")
    stat = changed.stat()
    os.utime(changed, ns=(stat.st_atime_ns, stat.st_mtime_ns + 1_000_000))

    data = collect_session_data(session, include_subagents=True)

    assert parses == Counter({"a0": 1, "a1": 2, "a2": 1})
    assert data.subagent_tool_counts["Write"] == 1


def test_concurrent_requests_parse_each_file_once(session_with_subagents, parses):
    session = session_with_subagents
    start = threading.Barrier(6)

    def request():
        start.wait()
        collect_session_data(session, include_subagents=True)

    threads = [threading.Thread(target=request) for _ in range(6)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert parses == Counter({"a0": 1, "a1": 1, "a2": 1})


def test_callers_cannot_corrupt_the_cache(session_with_subagents):
    session = session_with_subagents
    infos = collect_subagent_info(session, collect_session_data(session), {})
    infos[0].tool_counts["Read"] += 100
    data = collect_session_data(session, include_subagents=True)
    data.file_operations.clear()

    again = collect_session_data(session, include_subagents=True)
    assert again.subagent_tool_counts == Counter({"Read": 3, "Grep": 3})
    assert len(again.file_operations) == 3
    assert collect_subagent_info(session, collect_session_data(session), {})[
        0
    ].tool_counts == Counter({"Read": 1, "Grep": 1})
