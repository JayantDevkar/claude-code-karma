"""The Subagents tab names, colours and types each agent the way the timeline does."""

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from main import app

SESSION_UUID = "subagent-identity-session"
TEAMMATE = "areview-backend-dfe067fd7904abc2"
PLAIN = "a73440259afc2602f"
FORK = "af7566f9b9c587651"
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
            description="Review backend timeline diff",
            prompt="Review the backend diff.",
            name="review-backend",
            subagent_type="oh-my-claudecode:code-reviewer",
        ),
        # No subagent_type in the call: the type has to come from the agent's meta.json
        *_spawn(2, "toolu_plain", PLAIN, description="Probe", prompt="Write the probe file."),
        *_spawn(
            3, "toolu_fork", FORK, description="Backend half", prompt="p", subagent_type="fork"
        ),
    ]
    _write(project / f"{SESSION_UUID}.jsonl", main)

    wrapped = (
        '<teammate-message teammate_id="team-lead" summary="Review backend timeline diff">\n'
        "Review the backend diff.\n</teammate-message>"
    )
    side = {"agentId": TEAMMATE, "isSidechain": True}
    _write(subagents / f"agent-{TEAMMATE}.jsonl", [_user(1, wrapped, **side)])
    (subagents / f"agent-{TEAMMATE}.meta.json").write_text(
        json.dumps(
            {
                "agentType": "review-backend",
                "name": "review-backend",
                "description": "Review backend timeline diff",
                "teamName": "session-c7905cf6",
                "color": "blue",
                "model": "opus",
                "customAgentType": "oh-my-claudecode:code-reviewer",
                "spawnedAgentType": "oh-my-claudecode:code-reviewer",
            }
        )
    )

    side = {"agentId": PLAIN, "isSidechain": True}
    _write(subagents / f"agent-{PLAIN}.jsonl", [_user(2, "Write the probe file.", **side)])
    (subagents / f"agent-{PLAIN}.meta.json").write_text(
        json.dumps({"agentType": "general-purpose", "description": "Probe"})
    )

    side = {"agentId": FORK, "isSidechain": True}
    fork_first = [
        {"type": "tool_result", "tool_use_id": "toolu_fork", "content": "Fork started"},
        {
            "type": "text",
            "text": "<fork-boilerplate>\nYou are a worker fork.\n</fork-boilerplate>\n\n"
            "Your directive: do the backend half.",
        },
    ]
    _write(subagents / f"agent-{FORK}.jsonl", [_user(3, fork_first, **side)])
    (subagents / f"agent-{FORK}.meta.json").write_text(
        json.dumps(
            {
                "agentType": "fork",
                "isFork": True,
                "name": "timeline-backend",
                "description": "Backend half",
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
    assert teammate["name"] == "review-backend"
    assert teammate["color"] == "blue"
    assert teammate["team_name"] == "session-c7905cf6"
    assert teammate["model"] == "opus"
    assert teammate["description"] == "Review backend timeline diff"
    plain = rows[PLAIN]
    assert (plain["name"], plain["color"], plain["team_name"]) == (None, None, None)
    assert plain["description"] == "Probe"


def test_type_is_the_real_agent_type_never_the_teammate_name(client, team_session):
    rows = _by_id(client.get(f"/sessions/{SESSION_UUID}/subagents").json())
    assert rows[TEAMMATE]["subagent_type"] == "oh-my-claudecode:code-reviewer"
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
    assert rows[TEAMMATE]["initial_prompt"] == "Review the backend diff."
    assert rows[FORK]["initial_prompt"] == "Your directive: do the backend half."
    assert rows[PLAIN]["initial_prompt"] == "Write the probe file."


def test_agent_detail_reports_the_same_type(client, team_session):
    url = f"/agents/-Users-test-identity/{SESSION_UUID}/agents/{TEAMMATE}"
    assert client.get(url).json()["subagent_type"] == "oh-my-claudecode:code-reviewer"


def test_meta_type_that_only_repeats_the_name_is_not_a_type(tmp_path):
    from services.agent_registry import build_agent_registry

    directory = tmp_path / "subagents"
    directory.mkdir()
    (directory / "agent-aname-1.meta.json").write_text(
        json.dumps({"agentType": "review-frontend", "name": "review-frontend"})
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
    assert (teammate["name"], teammate["color"]) == ("review-backend", "blue")
    assert teammate["subagent_type"] == "oh-my-claudecode:code-reviewer"
    assert teammate["initial_prompt"] == "Review the backend diff."
    assert rows[FORK]["initial_prompt"] == "Your directive: do the backend half."
    assert rows["afiller0"]["name"] is None


DETAIL_URL = "/agents/-Users-test-identity/" + SESSION_UUID + "/agents/{}"


def test_agent_detail_carries_the_same_identity_as_the_list(client, team_session):
    row = _by_id(client.get(f"/sessions/{SESSION_UUID}/subagents").json())[TEAMMATE]
    detail = client.get(DETAIL_URL.format(TEAMMATE)).json()
    for key in ("name", "color", "team_name", "model", "description", "subagent_type"):
        assert detail[key] == row[key], key
    assert detail["name"] == "review-backend"
    assert detail["initial_prompt"] == "Review the backend diff."


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
    assert detail["subagent_type"] == "oh-my-claudecode:code-reviewer"


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
        '<teammate-message teammate_id="team-lead" summary="s">\nReview the backend diff.\n'
        "</teammate-message>"
    )
    entries = [
        _user(1, wrapped, **side),
        _assistant(2, [{"type": "text", "text": "x" * 80}], **side),
    ]
    _write(subagents / f"agent-{TEAMMATE}.jsonl", entries)
    events = client.get(DETAIL_URL.format(TEAMMATE) + "/timeline").json()
    response = next(e for e in events if e["event_type"] == "response")
    assert response["actor_agent_type"] == "oh-my-claudecode:code-reviewer"
    prompt = next(e for e in events if e["event_type"] == "prompt")
    assert prompt["actor_agent_type"] is None
