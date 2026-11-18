"""The Subagents tab names, colours and types each agent the way the timeline does."""

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from main import app

SESSION_UUID = "subagent-identity-session"
TEAMMATE = "achecker-00aa11bb22cc33dd"
PLAIN = "a0123456789abcdef"
FORK = "afedcba9876543210"
TS = "2026-11-18T08:{:02d}:00.000Z"


def _user(minute: int, content, **extra) -> dict:
    return {
        "type": "user",
        "uuid": f"u-{minute}-{extra.get('agentId', 'main')}",
        "timestamp": TS.format(minute),
        "sessionId": SESSION_UUID,
        "message": {"role": "user", "content": content},
        **extra,
    }


def _assistant(minute: int, blocks: list, **extra) -> dict:
    return {
        "type": "assistant",
        "uuid": f"a-{minute}-{extra.get('agentId', 'main')}",
        "timestamp": TS.format(minute),
        "sessionId": SESSION_UUID,
        "message": {"role": "assistant", "model": "claude-fable-5-2", "content": blocks},
        **extra,
    }


def _spawn(minute: int, tool_id: str, agent_id: str, **tool_input) -> list:
    use = {"type": "tool_use", "id": tool_id, "name": "Agent", "input": tool_input}
    result = {"type": "tool_result", "tool_use_id": tool_id, "content": "Spawned successfully."}
    return [
        _assistant(minute, [use]),
        _user(minute, [result], toolUseResult={"agentId": agent_id}),
    ]


def _write(path: Path, entries: list) -> None:
    path.write_text("\n".join(json.dumps(e) for e in entries) + "\n")


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def team_session(mock_claude_base):
    project = mock_claude_base / "projects" / "-Users-test-identity"
    subagents = project / SESSION_UUID / "subagents"
    subagents.mkdir(parents=True)
    main = [
        _user(0, "review the diff"),
        *_spawn(
            1,
            "toolu_team",
            TEAMMATE,
            description="Check the diff",
            prompt="Check the diff for bugs.",
            name="checker",
            subagent_type="example-plugin:reviewer",
        ),
        # No subagent_type in the call: the type has to come from the agent's meta.json
        *_spawn(2, "toolu_plain", PLAIN, description="Notes", prompt="Write the notes file."),
        *_spawn(3, "toolu_fork", FORK, description="Side task", prompt="p", subagent_type="fork"),
    ]
    _write(project / f"{SESSION_UUID}.jsonl", main)

    wrapped = (
        '<teammate-message teammate_id="team-lead" summary="Check the diff">\n'
        "Check the diff for bugs.\n</teammate-message>"
    )
    side = {"agentId": TEAMMATE, "isSidechain": True}
    _write(subagents / f"agent-{TEAMMATE}.jsonl", [_user(1, wrapped, **side)])
    (subagents / f"agent-{TEAMMATE}.meta.json").write_text(
        json.dumps(
            {
                "agentType": "checker",
                "name": "checker",
                "description": "Check the diff",
                "teamName": "example-team",
                "color": "blue",
                "model": "opus",
                "customAgentType": "example-plugin:reviewer",
                "spawnedAgentType": "example-plugin:reviewer",
            }
        )
    )

    side = {"agentId": PLAIN, "isSidechain": True}
    _write(subagents / f"agent-{PLAIN}.jsonl", [_user(2, "Write the notes file.", **side)])
    (subagents / f"agent-{PLAIN}.meta.json").write_text(
        json.dumps({"agentType": "general-purpose", "description": "Notes"})
    )

    side = {"agentId": FORK, "isSidechain": True}
    fork_first = [
        {"type": "tool_result", "tool_use_id": "toolu_fork", "content": "Fork started"},
        {
            "type": "text",
            "text": "<fork-boilerplate>\nYou are a worker fork.\n</fork-boilerplate>\n\n"
            "Your directive: do the side task.",
        },
    ]
    _write(subagents / f"agent-{FORK}.jsonl", [_user(3, fork_first, **side)])
    (subagents / f"agent-{FORK}.meta.json").write_text(
        json.dumps(
            {
                "agentType": "fork",
                "isFork": True,
                "name": "side-task",
                "description": "Side task",
                "model": "inherit",
            }
        )
    )
    return project


def _by_id(rows: list) -> dict:
    return {row["agent_id"]: row for row in rows}


@pytest.mark.parametrize("endpoint", ["subagents", "subagents/parallel"])
def test_subagents_carry_name_colour_team_model_and_description(client, team_session, endpoint):
    rows = _by_id(client.get(f"/sessions/{SESSION_UUID}/{endpoint}").json())
    teammate = rows[TEAMMATE]
    assert teammate["name"] == "checker"
    assert teammate["color"] == "blue"
    assert teammate["team_name"] == "example-team"
    assert teammate["model"] == "opus"
    assert teammate["description"] == "Check the diff"
    plain = rows[PLAIN]
    assert (plain["name"], plain["color"], plain["team_name"]) == (None, None, None)
    assert plain["description"] == "Notes"


def test_type_is_the_real_agent_type_never_the_teammate_name(client, team_session):
    rows = _by_id(client.get(f"/sessions/{SESSION_UUID}/subagents").json())
    assert rows[TEAMMATE]["subagent_type"] == "example-plugin:reviewer"
    assert rows[PLAIN]["subagent_type"] == "general-purpose"
    assert rows[FORK]["subagent_type"] == "fork"


def test_type_agrees_with_the_timeline_spawn_event(client, team_session):
    rows = _by_id(client.get(f"/sessions/{SESSION_UUID}/subagents").json())
    timeline = client.get(f"/sessions/{SESSION_UUID}/timeline").json()
    spawns = {
        e["metadata"]["spawned_agent_id"]: e["metadata"]
        for e in timeline
        if e["event_type"] == "subagent_spawn"
    }
    assert set(spawns) == set(rows)
    for agent_id, row in rows.items():
        assert spawns[agent_id]["subagent_type"] == row["subagent_type"], agent_id
        assert spawns[agent_id]["spawned_agent_name"] == row["name"], agent_id
        assert spawns[agent_id]["spawned_agent_color"] == row["color"], agent_id


def test_initial_prompt_has_no_wrapper_or_fork_boilerplate(client, team_session):
    rows = _by_id(client.get(f"/sessions/{SESSION_UUID}/subagents").json())
    assert rows[TEAMMATE]["initial_prompt"] == "Check the diff for bugs."
    assert rows[FORK]["initial_prompt"] == "Your directive: do the side task."
    assert rows[PLAIN]["initial_prompt"] == "Write the notes file."


def test_agent_detail_reports_the_same_type(client, team_session):
    url = f"/agents/-Users-test-identity/{SESSION_UUID}/agents/{TEAMMATE}"
    assert client.get(url).json()["subagent_type"] == "example-plugin:reviewer"


def test_meta_type_that_only_repeats_the_name_is_not_a_type(tmp_path):
    from services.agent_registry import build_agent_registry

    directory = tmp_path / "subagents"
    directory.mkdir()
    (directory / "agent-aname-1.meta.json").write_text(
        json.dumps({"agentType": "checker-two", "name": "checker-two"})
    )
    (directory / "agent-acustom-2.meta.json").write_text(
        json.dumps({"agentType": "ui", "name": "ui", "customAgentType": "designer"})
    )
    registry = build_agent_registry([], extra_dirs=[directory])
    assert registry.get("aname-1").agent_type is None
    assert registry.get("acustom-2").agent_type == "designer"


def test_parallel_path_with_many_subagents_keeps_identity(client, team_session):
    subagents = team_session / SESSION_UUID / "subagents"
    for n in range(3):
        side = {"agentId": f"afiller{n}", "isSidechain": True}
        _write(subagents / f"agent-afiller{n}.jsonl", [_user(5 + n, f"filler {n}", **side)])
    rows = _by_id(client.get(f"/sessions/{SESSION_UUID}/subagents/parallel").json())
    assert len(rows) == 6
    teammate = rows[TEAMMATE]
    assert (teammate["name"], teammate["color"]) == ("checker", "blue")
    assert teammate["subagent_type"] == "example-plugin:reviewer"
    assert teammate["initial_prompt"] == "Check the diff for bugs."
    assert rows[FORK]["initial_prompt"] == "Your directive: do the side task."
    assert rows["afiller0"]["name"] is None


DETAIL_URL = "/agents/-Users-test-identity/" + SESSION_UUID + "/agents/{}"


def test_agent_detail_carries_the_same_identity_as_the_list(client, team_session):
    row = _by_id(client.get(f"/sessions/{SESSION_UUID}/subagents").json())[TEAMMATE]
    detail = client.get(DETAIL_URL.format(TEAMMATE)).json()
    for key in ("name", "color", "team_name", "model", "description", "subagent_type"):
        assert detail[key] == row[key], key
    assert detail["name"] == "checker"
    assert detail["initial_prompt"] == "Check the diff for bugs."


def test_agent_detail_never_returns_an_index_marker_as_the_type(client, team_session, monkeypatch):
    from contextlib import contextmanager

    import db.connection

    class _Conn:
        def execute(self, *_args):
            return self

        def fetchone(self):
            return ("_teammate",)

    @contextmanager
    def fake_sqlite_read():
        yield _Conn()

    monkeypatch.setattr(db.connection, "sqlite_read", fake_sqlite_read)
    detail = client.get(DETAIL_URL.format(TEAMMATE)).json()
    assert detail["subagent_type"] == "example-plugin:reviewer"


def test_inherit_is_not_a_model(client, team_session):
    row = _by_id(client.get(f"/sessions/{SESSION_UUID}/subagents").json())[FORK]
    assert row["model"] is None
    assert client.get(DETAIL_URL.format(FORK)).json()["model"] is None
    timeline = client.get(f"/sessions/{SESSION_UUID}/timeline").json()
    spawn = next(e for e in timeline if e["metadata"].get("spawned_agent_id") == FORK)
    assert spawn["metadata"]["agent_model"] is None
    teammate = next(e for e in timeline if e["metadata"].get("spawned_agent_id") == TEAMMATE)
    assert teammate["metadata"]["agent_model"] == "opus"


def test_agent_timeline_events_carry_the_agents_type(client, team_session):
    subagents = team_session / SESSION_UUID / "subagents"
    side = {"agentId": TEAMMATE, "isSidechain": True}
    wrapped = (
        '<teammate-message teammate_id="team-lead" summary="s">\nCheck the diff for bugs.\n'
        "</teammate-message>"
    )
    entries = [
        _user(1, wrapped, **side),
        _assistant(2, [{"type": "text", "text": "x" * 80}], **side),
    ]
    _write(subagents / f"agent-{TEAMMATE}.jsonl", entries)
    events = client.get(DETAIL_URL.format(TEAMMATE) + "/timeline").json()
    response = next(e for e in events if e["event_type"] == "response")
    assert response["actor_agent_type"] == "example-plugin:reviewer"
    prompt = next(e for e in events if e["event_type"] == "prompt")
    assert prompt["actor_agent_type"] is None


NESTED = "a1111111111111111"


@pytest.fixture
def workflow_agent(team_session):
    run_dir = team_session / SESSION_UUID / "subagents" / "workflows" / "wf_00000000-000"
    run_dir.mkdir(parents=True)
    side = {"agentId": NESTED, "isSidechain": True}
    _write(run_dir / f"agent-{NESTED}.jsonl", [_user(4, "[Workflow harness] do it", **side)])
    (run_dir / f"agent-{NESTED}.meta.json").write_text(
        json.dumps({"agentType": "workflow-subagent", "description": "research:notes"})
    )
    _write(run_dir / "journal.jsonl", [{"type": "started", "agentId": NESTED}])


def test_workflow_agents_below_subagents_are_listed(client, team_session, workflow_agent):
    rows = _by_id(client.get(f"/sessions/{SESSION_UUID}/subagents").json())
    assert rows[NESTED]["subagent_type"] == "workflow-subagent"
    assert rows[NESTED]["description"] == "research:notes"
    assert "journal" not in " ".join(rows)


def test_workflow_agent_pages_load(client, team_session, workflow_agent):
    assert client.get(DETAIL_URL.format(NESTED)).status_code == 200
    events = client.get(DETAIL_URL.format(NESTED) + "/timeline").json()
    assert [e["event_type"] for e in events] == ["prompt"]


SENDER = "abababab-0000-4000-8000-000000000001"


PEER_TEXT = (
    "Another Claude session sent a message:\n"
    '<cross-session-message from="uds:/tmp/example/peer.sock" from-name="docs-site">\n'
    "[ASK] Which port?\n</cross-session-message>"
)
PEER_ORIGIN = {"kind": "peer", "from": "uds:/tmp/example/peer.sock", "name": "docs-site"}


def _receive_peer_message(team_session) -> None:
    with open(team_session / f"{SESSION_UUID}.jsonl", "a") as f:
        f.write(json.dumps(_user(30, PEER_TEXT, isMeta=True, origin=PEER_ORIGIN)) + "\n")


def test_timeline_links_a_message_to_the_named_session_that_sent_it(
    client, team_session, monkeypatch
):
    from db import indexer
    from db.connection import get_writer_db

    _receive_peer_message(team_session)

    conn = get_writer_db()
    conn.execute(
        "INSERT INTO projects (encoded_name, display_name, slug) VALUES ('-Users-test-docs', 'd', 'd')"
    )
    conn.execute(
        "INSERT INTO sessions (uuid, project_encoded_name, session_name, start_time, end_time, "
        "jsonl_mtime) VALUES (?, '-Users-test-docs', 'docs-site', ?, ?, 1.0)",
        (SENDER, TS.format(0).replace("Z", "+00:00"), TS.format(59).replace("Z", "+00:00")),
    )
    conn.commit()
    monkeypatch.setattr(indexer, "is_db_ready", lambda: True)

    events = client.get(f"/sessions/{SESSION_UUID}/timeline").json()
    message = next(e for e in events if e["event_type"] == "message")
    assert message["metadata"]["peer_session_uuid"] == SENDER
    assert message["metadata"]["peer_project_encoded_name"] == "-Users-test-docs"


def test_timeline_still_loads_when_the_index_is_not_ready(client, team_session, monkeypatch):
    from db import indexer

    _receive_peer_message(team_session)
    monkeypatch.setattr(indexer, "is_db_ready", lambda: False)

    response = client.get(f"/sessions/{SESSION_UUID}/timeline")
    assert response.status_code == 200
    messages = [e for e in response.json() if e["event_type"] == "message"]
    assert len(messages) == 1
    assert messages[0]["metadata"]["peer_name"] == "docs-site"
    assert messages[0]["metadata"]["peer_session_uuid"] is None


@pytest.fixture
def name_only_meta(team_session):
    """The teammate's meta.json only repeats its name, so its type is known from the spawn call alone."""
    meta = team_session / SESSION_UUID / "subagents" / f"agent-{TEAMMATE}.meta.json"
    meta.write_text(json.dumps({"agentType": "checker", "name": "checker", "color": "blue"}))


def test_teammates_own_timeline_has_the_type_the_list_shows(client, team_session, name_only_meta):
    side = {"agentId": TEAMMATE, "isSidechain": True}
    entries = [
        _user(1, "Check the diff for bugs.", **side),
        _assistant(2, [{"type": "text", "text": "x" * 80}], **side),
    ]
    _write(team_session / SESSION_UUID / "subagents" / f"agent-{TEAMMATE}.jsonl", entries)
    row = _by_id(client.get(f"/sessions/{SESSION_UUID}/subagents").json())[TEAMMATE]
    assert row["subagent_type"] == "example-plugin:reviewer"
    events = client.get(DETAIL_URL.format(TEAMMATE) + "/timeline").json()
    response = next(e for e in events if e["event_type"] == "response")
    assert response["actor_agent_type"] == "example-plugin:reviewer"
    assert client.get(DETAIL_URL.format(TEAMMATE)).json()["subagent_type"] == row["subagent_type"]


def test_parallel_path_uses_the_spawn_calls_type(client, team_session, name_only_meta):
    subagents = team_session / SESSION_UUID / "subagents"
    for n in range(3):
        side = {"agentId": f"afiller{n}", "isSidechain": True}
        _write(subagents / f"agent-afiller{n}.jsonl", [_user(5 + n, f"filler {n}", **side)])
    rows = _by_id(client.get(f"/sessions/{SESSION_UUID}/subagents/parallel").json())
    assert len(rows) == 6
    assert rows[TEAMMATE]["subagent_type"] == "example-plugin:reviewer"
    assert rows[FORK]["subagent_type"] == "fork"
    assert rows[PLAIN]["subagent_type"] == "general-purpose"


SPLIT = "a2222222222222222"


def test_agent_split_over_two_files_is_one_row_and_one_page(client, team_session):
    subagents = team_session / SESSION_UUID / "subagents"
    side = {"agentId": SPLIT, "isSidechain": True}
    run_dir = subagents / "workflows" / "wf_00000000-000"
    run_dir.mkdir(parents=True)
    _write(
        run_dir / f"agent-{SPLIT}.jsonl",
        [_user(10, "[Workflow harness] review a.py", **side), _assistant(11, [], **side)],
    )
    (run_dir / f"agent-{SPLIT}.meta.json").write_text(
        json.dumps({"agentType": "workflow-subagent"})
    )
    _write(
        subagents / f"agent-{SPLIT}.jsonl",
        [_assistant(20, [], **side), _user(21, "one more thing", **side)],
    )
    rows = client.get(f"/sessions/{SESSION_UUID}/subagents").json()
    split = [r for r in rows if r["agent_id"] == SPLIT]
    assert len(split) == 1
    assert split[0]["message_count"] == 4
    assert split[0]["subagent_type"] == "workflow-subagent"
    assert split[0]["initial_prompt"] == "[Workflow harness] review a.py"
    assert client.get(DETAIL_URL.format(SPLIT)).json()["message_count"] == 4
    events = client.get(DETAIL_URL.format(SPLIT) + "/timeline").json()
    assert [e["event_type"] for e in events] == ["prompt", "message"]
