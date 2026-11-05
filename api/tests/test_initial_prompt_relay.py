"""Initial prompt extraction for sessions a coordinator spawned in a project.

Claude Code opens such sessions with an isMeta <relay reason="spawn"> message
holding the coordinator's brief, then the <wake> message whose human line
("yes") triggered the spawn. The brief is the prompt.
"""

import json
from pathlib import Path

from collectors import collect_session_data
from models import Session
from utils import get_initial_prompt

NOTE = (
    "The user said yes to starting the login fix. Run the plan "
    "docs/plans/login-fix.md, then report back here and stop."
)
RELAY = (
    '<relay from="coordinator" session="session_coordinator" '
    'current-time="2026-11-01T20:27:28Z" reason="spawn">\n'
    "  The note below was written by the coordinator session, a Claude session, "
    "not by your user.\n"
    f"  <note>\n      {NOTE}\n  </note>\n</relay>"
)
WAKE = (
    '<wake reason="mention" current-time="2026-11-01T20:27:28Z">\n'
    '  <project id="chan_project" type="project">\n'
    '    <message trigger="true" from="human" trust="principal" mention="true">yes</message>\n'
    "  </project>\n</wake>\n"
)


def _user(uuid: str, content, ts: str, **extra) -> dict:
    return {
        "type": "user",
        "uuid": uuid,
        "timestamp": ts,
        "sessionId": "spawned",
        "message": {"role": "user", "content": content},
        **extra,
    }


def _session_from(tmp_path: Path, lines: list) -> Session:
    jsonl = tmp_path / "spawned.jsonl"
    jsonl.write_text("\n".join(json.dumps(line) for line in lines) + "\n", encoding="utf-8")
    return Session(uuid="spawned", jsonl_path=jsonl, claude_base_dir=tmp_path)


def test_spawn_relay_note_is_the_initial_prompt(tmp_path: Path):
    session = _session_from(
        tmp_path,
        [
            {
                "type": "queue-operation",
                "operation": "enqueue",
                "timestamp": "2026-11-01T20:27:44.498Z",
                "sessionId": "spawned",
                "content": RELAY,
            },
            _user("u1", RELAY, "2026-11-01T20:27:46.949Z", isMeta=True),
            _user("u2", WAKE, "2026-11-01T20:27:47.100Z"),
        ],
    )

    assert get_initial_prompt(session) == NOTE
    assert collect_session_data(session).initial_prompt == NOTE


def test_non_spawn_meta_relay_is_skipped(tmp_path: Path):
    """Only the spawn brief starts a session; other meta relays stay hidden."""
    relay = RELAY.replace('reason="spawn"', 'reason="update"')
    session = _session_from(
        tmp_path,
        [
            _user("u1", relay, "2026-11-01T20:27:46.949Z", isMeta=True),
            _user("u2", [{"type": "text", "text": "Fix the login bug"}], "2026-11-01T20:28:00Z"),
        ],
    )

    assert get_initial_prompt(session) == "Fix the login bug"
    assert collect_session_data(session).initial_prompt == "Fix the login bug"
