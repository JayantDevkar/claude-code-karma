"""While the SQLite index is being built or rebuilt, no route may answer 500."""

import json
import re

import pytest
from fastapi.testclient import TestClient

from main import app

PROJECT = "-Users-test-sweep"
SESSION = "5e5e5e5e-0000-4000-8000-000000000001"
AGENT = "a4444444444444444"
MESSAGE = "u-sweep-1"
TS = "2026-11-18T08:{:02d}:00.000Z"

# Path parameters point at the fixture below, so each route runs its own code, not just a 404.
_PARAMS = {
    "uuid": SESSION,
    "session_uuid": SESSION,
    "session_id": SESSION,
    "short_id": SESSION[:8],
    "encoded_name": PROJECT,
    "project_encoded_name": PROJECT,
    "agent_id": AGENT,
    "message_uuid": MESSAGE,
    "subagent_type": "general-purpose",
    "skill_name": "example-plugin:debugging",
    "command_name": "commit",
    "provider": "github",
    "external_key": "example/repo#1",
}


def _fill(path: str) -> str:
    return re.sub(r"\{(\w+)(?::\w+)?\}", lambda m: _PARAMS.get(m.group(1), "missing"), path)


def _get_paths() -> list[str]:
    paths = app.openapi()["paths"]
    return sorted({_fill(path) for path, methods in paths.items() if "get" in methods})


def _entry(kind: str, minute: int, uuid: str, content, **extra) -> dict:
    message = {"role": kind, "content": content}
    if kind == "assistant":
        message["model"] = "claude-fable-5-2"
        message["usage"] = {"input_tokens": 10, "output_tokens": 5}
    return {
        "type": kind,
        "uuid": uuid,
        "timestamp": TS.format(minute),
        "sessionId": SESSION,
        "cwd": "/Users/test/sweep",
        "message": message,
        **extra,
    }


def _tool(tool_id: str, name: str, **tool_input) -> dict:
    return {"type": "tool_use", "id": tool_id, "name": name, "input": tool_input}


def _result(tool_id: str, text: str) -> list:
    return [{"type": "tool_result", "tool_use_id": tool_id, "content": text}]


def _write(path, entries: list) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(json.dumps(e) for e in entries) + "\n")


@pytest.fixture
def populated(mock_claude_base):
    """A project with one session that used tools, a skill, a task, a subagent and a peer message."""
    project = mock_claude_base / "projects" / PROJECT
    peer = (
        "Another Claude session sent a message:\n"
        '<cross-session-message from="uds:/tmp/example/peer.sock" from-name="docs-site">\n'
        "[ASK] Which port?\n</cross-session-message>"
    )
    origin = {"kind": "peer", "from": "uds:/tmp/example/peer.sock", "name": "docs-site"}
    main = [
        _entry("user", 0, MESSAGE, "read the README and commit"),
        _entry(
            "assistant",
            1,
            "a-sweep-1",
            [
                _tool("t_read", "Read", file_path="/Users/test/sweep/README.md"),
                _tool("t_skill", "Skill", skill="example-plugin:debugging"),
                _tool("t_task", "TaskCreate", subject="Commit", description="d"),
                _tool("t_agent", "Agent", description="Notes", prompt="Write notes."),
            ],
        ),
        _entry("user", 2, "u-sweep-2", _result("t_read", "# README")),
        _entry("user", 2, "u-sweep-3", _result("t_task", "Task #1 created successfully")),
        _entry(
            "user", 3, "u-sweep-4", _result("t_agent", "Done."), toolUseResult={"agentId": AGENT}
        ),
        _entry("user", 4, "u-sweep-5", peer, isMeta=True, origin=origin),
        _entry("assistant", 5, "a-sweep-2", [{"type": "text", "text": "x" * 80}]),
    ]
    _write(project / f"{SESSION}.jsonl", main)
    side = {"agentId": AGENT, "isSidechain": True}
    subagents = project / SESSION / "subagents"
    _write(
        subagents / f"agent-{AGENT}.jsonl",
        [
            _entry("user", 3, "u-agent-1", "Write notes.", **side),
            _entry(
                "assistant",
                4,
                "a-agent-1",
                [_tool("t_w", "Write", file_path="/x", content="n")],
                **side,
            ),
        ],
    )
    (subagents / f"agent-{AGENT}.meta.json").write_text(
        json.dumps({"agentType": "general-purpose"})
    )
    return project


@pytest.fixture
def client(populated):
    from db import indexer

    was_ready = indexer._ready.is_set()
    yield TestClient(app, raise_server_exceptions=False)
    # /shells runs a real sync, which marks the index ready for every later test
    if not was_ready:
        indexer._ready.clear()


@pytest.fixture
def index_not_ready(monkeypatch):
    """The state during a re-index: the database file exists, the index is not marked ready."""
    from db import indexer
    from db.connection import get_writer_db

    get_writer_db()
    monkeypatch.setattr(indexer, "is_db_ready", lambda: False)


REBUILDING = {"detail": "The index is rebuilding. Try again in a moment."}


def _is_rebuilding_answer(response) -> bool:
    return (
        response.status_code == 503
        and response.json() == REBUILDING
        and response.headers.get("retry-after") == "5"
    )


@pytest.mark.parametrize("path", _get_paths())
def test_no_get_route_answers_500_while_the_index_is_not_ready(client, index_not_ready, path):
    response = client.get(path)
    # The only 5xx allowed is the explicit "index is rebuilding, retry" answer
    assert response.status_code < 500 or _is_rebuilding_answer(response), path


# Routes that must run their own code against the fixture, not stop at a 404.
_MUST_ANSWER_200 = [
    f"/sessions/{SESSION}",
    f"/sessions/{SESSION}/timeline",
    f"/sessions/{SESSION}/subagents",
    f"/sessions/{SESSION}/subagents/parallel",
    f"/sessions/{SESSION}/tools",
    f"/sessions/{SESSION}/file-activity",
    f"/sessions/{SESSION}/tasks",
    f"/sessions/{SESSION}/initial-prompt",
    f"/agents/{PROJECT}/{SESSION}/agents/{AGENT}",
    f"/agents/{PROJECT}/{SESSION}/agents/{AGENT}/timeline",
    f"/agents/{PROJECT}/{SESSION}/agents/{AGENT}/tools",
    f"/agents/{PROJECT}/{SESSION}/agents/{AGENT}/file-activity",
    f"/projects/{PROJECT}",
    f"/analytics/projects/{PROJECT}",
    "/skills/example-plugin:debugging/sessions",
]


@pytest.mark.parametrize("path", _MUST_ANSWER_200)
def test_session_and_agent_routes_work_from_files_while_the_index_is_not_ready(
    client, index_not_ready, path
):
    assert path in _get_paths()
    assert client.get(path).status_code == 200, path


def test_timeline_has_its_events_but_no_links_while_the_index_is_not_ready(client, index_not_ready):
    response = client.get(f"/sessions/{SESSION}/timeline")
    kinds = {e["event_type"] for e in response.json()}
    assert {"prompt", "tool_call", "subagent_spawn", "skill_invocation", "message"} <= kinds
    message = next(e for e in response.json() if e["event_type"] == "message")
    assert message["metadata"]["peer_session_uuid"] is None
    assert "no-store" in response.headers["cache-control"]


def test_the_sweep_reaches_handler_code_for_most_paths(client, index_not_ready):
    statuses = [client.get(path).status_code for path in _get_paths()]
    reached = sum(1 for status in statuses if status not in (404, 422))
    # 79 of 108 when written; the others need a plugin, plan, hook, ticket or live session to exist
    assert reached >= 75, (reached, len(statuses))


@pytest.mark.parametrize(
    "path",
    [
        "/shells",
        "/shells/project-rollup",
        f"/sessions/{SESSION}/shells",
        "/cron",
        "/cron/project-rollup",
        f"/sessions/{SESSION}/cron",
    ],
)
def test_shell_and_cron_lists_ask_to_retry_while_the_index_is_not_ready(
    client, index_not_ready, path
):
    assert _is_rebuilding_answer(client.get(path))


def test_shell_and_cron_lists_answer_normally_when_the_index_is_ready(client, monkeypatch):
    from db import indexer
    from db.connection import get_writer_db

    get_writer_db()
    monkeypatch.setattr(indexer, "is_db_ready", lambda: True)
    assert client.get("/shells/project-rollup").json() == {"projects": [], "count": 0}
    assert client.get("/cron/project-rollup").json() == {"projects": [], "count": 0}
    assert client.get(f"/sessions/{SESSION}/shells").status_code == 404


def test_kill_asks_to_retry_while_the_index_is_not_ready(client, index_not_ready):
    assert _is_rebuilding_answer(client.post("/shells/toolu_missing/kill"))


def test_a_cross_origin_page_can_read_retry_after(client, index_not_ready):
    from config import settings

    origin = settings.cors_origins[0]
    response = client.get("/shells", headers={"Origin": origin})
    assert _is_rebuilding_answer(response)
    exposed = response.headers.get("access-control-expose-headers", "")
    assert "retry-after" in exposed.lower()


def test_skill_sessions_fallback_runs_without_the_index(client, index_not_ready):
    response = client.get("/skills/missing/sessions")
    assert response.status_code == 200
    assert response.json()["sessions"] == []


DISABLED = {
    "detail": "This view needs the SQLite index, which is turned off (CLAUDE_KARMA_USE_SQLITE=false)."
}


@pytest.fixture
def sqlite_disabled(monkeypatch):
    from config import settings

    monkeypatch.setattr(settings, "use_sqlite", False)


@pytest.mark.parametrize(
    "method, path",
    [
        ("get", "/shells"),
        ("get", "/shells/project-rollup"),
        ("get", f"/sessions/{SESSION}/shells"),
        ("get", "/cron"),
        ("get", "/cron/project-rollup"),
        ("get", f"/sessions/{SESSION}/cron"),
        ("post", "/shells/toolu_missing/kill"),
    ],
)
def test_with_sqlite_turned_off_the_answer_is_final_not_a_retry(
    client, sqlite_disabled, method, path
):
    response = getattr(client, method)(path)
    assert response.status_code == 501
    assert response.json() == DISABLED
    assert "retry-after" not in response.headers
