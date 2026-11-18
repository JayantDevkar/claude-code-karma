"""Peer-session links come from the index, so a timeline built without it must not be cached as final."""

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from main import app

SESSION_UUID = "cdcdcdcd-0000-4000-8000-000000000001"
SENDER = "abababab-0000-4000-8000-000000000002"
AGENT = "a3333333333333333"
PROJECT = "-Users-test-peercache"
TS = "2026-11-18T08:{:02d}:00.000Z"
PEER_TEXT = (
    "Another Claude session sent a message:\n"
    '<cross-session-message from="uds:/tmp/example/peer.sock" from-name="docs-site">\n'
    "[ASK] Which port?\n</cross-session-message>"
)
ORIGIN = {"kind": "peer", "from": "uds:/tmp/example/peer.sock", "name": "docs-site"}
URLS = [
    f"/sessions/{SESSION_UUID}/timeline",
    f"/agents/{PROJECT}/{SESSION_UUID}/agents/{AGENT}/timeline",
]


def _user(minute: int, content, **extra) -> dict:
    return {
        "type": "user",
        "uuid": f"u-{minute}-{extra.get('agentId', 'main')}",
        "timestamp": TS.format(minute),
        "sessionId": SESSION_UUID,
        "message": {"role": "user", "content": content},
        **extra,
    }


def _write(path: Path, entries: list) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(json.dumps(e) for e in entries) + "\n")


@pytest.fixture
def client(mock_claude_base):
    """A lead session and one of its agents; each received a message from the session "docs-site"."""
    project = mock_claude_base / "projects" / PROJECT
    _write(
        project / f"{SESSION_UUID}.jsonl",
        [_user(0, "start"), _user(30, PEER_TEXT, isMeta=True, origin=ORIGIN)],
    )
    side = {"agentId": AGENT, "isSidechain": True}
    _write(
        project / SESSION_UUID / "subagents" / f"agent-{AGENT}.jsonl",
        [_user(5, "do the task", **side), _user(31, PEER_TEXT, isMeta=True, origin=ORIGIN, **side)],
    )
    return TestClient(app)


@pytest.fixture
def index(monkeypatch):
    """The index, with the named sender in it; `index.ready` flips whether routes may use it."""
    from db import indexer
    from db.connection import get_writer_db

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

    class Index:
        ready = True

        def rename_sender(self, name: str) -> None:
            conn.execute("UPDATE sessions SET session_name = ? WHERE uuid = ?", (name, SENDER))
            conn.commit()

    state = Index()
    monkeypatch.setattr(indexer, "is_db_ready", lambda: state.ready)
    return state


def _message(response) -> dict:
    return next(e for e in response.json() if e["event_type"] == "message")


@pytest.mark.parametrize("url", URLS)
def test_timeline_built_without_the_index_is_not_stored(client, index, url):
    index.ready = False
    response = client.get(url)
    assert response.status_code == 200
    assert _message(response)["metadata"]["peer_session_uuid"] is None
    assert "no-store" in response.headers["cache-control"]
    assert "etag" not in response.headers


@pytest.mark.parametrize("url", URLS)
def test_links_appear_once_the_index_is_ready(client, index, url):
    index.ready = False
    client.get(url)
    index.ready = True
    response = client.get(url)
    assert _message(response)["metadata"]["peer_session_uuid"] == SENDER
    assert "no-store" not in response.headers["cache-control"]
    assert response.headers["etag"]


@pytest.mark.parametrize("url", URLS)
def test_unchanged_links_revalidate_with_304(client, index, url):
    etag = client.get(url).headers["etag"]
    assert client.get(url, headers={"If-None-Match": etag}).status_code == 304


@pytest.mark.parametrize("url", URLS)
def test_etag_changes_when_the_index_resolves_the_link_differently(client, index, url):
    linked = client.get(url)
    etag = linked.headers["etag"]
    index.rename_sender("something-else")
    again = client.get(url, headers={"If-None-Match": etag})
    assert again.status_code == 200
    assert again.headers["etag"] != etag
    assert _message(again)["metadata"]["peer_session_uuid"] is None


@pytest.mark.parametrize("url", URLS)
def test_a_cached_link_is_not_served_once_the_index_stops_being_ready(client, index, url):
    etag = client.get(url).headers["etag"]
    index.ready = False
    again = client.get(url, headers={"If-None-Match": etag})
    assert again.status_code == 200
    assert "no-store" in again.headers["cache-control"]


def test_timeline_without_peer_messages_is_cached_even_without_the_index(client, index):
    index.ready = False
    project = client.app  # noqa: F841 - the fixture already wrote the files
    plain = "efefefef-0000-4000-8000-000000000003"
    from config import settings

    _write(settings.projects_dir / PROJECT / f"{plain}.jsonl", [_user(0, "just a prompt")])
    response = client.get(f"/sessions/{plain}/timeline")
    etag = response.headers["etag"]
    assert "no-store" not in response.headers["cache-control"]
    assert (
        client.get(f"/sessions/{plain}/timeline", headers={"If-None-Match": etag}).status_code
        == 304
    )
