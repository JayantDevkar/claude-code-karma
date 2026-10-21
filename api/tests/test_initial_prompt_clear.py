"""Initial prompt extraction for sessions started with /clear.

Claude Code opens such sessions with an isMeta <local-command-caveat> message
and the /clear command itself before the first real user prompt.
"""

import json
from pathlib import Path

from collectors import collect_session_data
from models import Session
from utils import get_initial_prompt

CAVEAT = (
    "<local-command-caveat>The command below was run directly in Claude Code, "
    "not sent to you as a request, and its output goes straight to the user. "
    "It's recorded here as context for later messages.</local-command-caveat>"
)
CLEAR = (
    "<command-name>/clear</command-name>\n"
    "            <command-message>clear</command-message>\n"
    "            <command-args></command-args>"
)
PROMPT = "Fix the login bug"


def _user(uuid: str, content, ts: str, **extra) -> dict:
    return {
        "type": "user",
        "uuid": uuid,
        "timestamp": ts,
        "sessionId": "clear-session",
        "message": {"role": "user", "content": content},
        **extra,
    }


def _make_session(tmp_path: Path) -> Session:
    lines = [
        _user("u1", CAVEAT, "2026-10-21T10:00:00.000Z", isMeta=True),
        _user("u2", CLEAR, "2026-10-21T10:00:00.100Z"),
        _user("u3", [{"type": "text", "text": PROMPT}], "2026-10-21T10:00:05.000Z"),
    ]
    jsonl = tmp_path / "clear-session.jsonl"
    jsonl.write_text("\n".join(json.dumps(line) for line in lines) + "\n", encoding="utf-8")
    return Session(uuid="clear-session", jsonl_path=jsonl, claude_base_dir=tmp_path)


def test_get_initial_prompt_skips_clear_preamble(tmp_path: Path):
    session = _make_session(tmp_path)
    assert get_initial_prompt(session) == PROMPT


def test_collect_session_data_skips_clear_preamble(tmp_path: Path):
    session = _make_session(tmp_path)
    assert collect_session_data(session).initial_prompt == PROMPT


def _session_from(tmp_path: Path, name: str, lines: list) -> Session:
    jsonl = tmp_path / f"{name}.jsonl"
    jsonl.write_text("\n".join(json.dumps(line) for line in lines) + "\n", encoding="utf-8")
    return Session(uuid=name, jsonl_path=jsonl, claude_base_dir=tmp_path)


def test_skips_local_command_with_args_after_clear(tmp_path: Path):
    """/clear then /model fable: the model name is not the prompt."""
    model = (
        "<command-name>/model</command-name>\n"
        "            <command-message>model</command-message>\n"
        "            <command-args>fable</command-args>"
    )
    stdout = "<local-command-stdout>Set model to Fable</local-command-stdout>"
    session = _session_from(
        tmp_path,
        "clear-model",
        [
            _user("u1", CAVEAT, "2026-10-21T10:00:00.000Z", isMeta=True),
            _user("u2", CLEAR, "2026-10-21T10:00:00.100Z"),
            _user("u3", CAVEAT, "2026-10-21T10:00:01.000Z", isMeta=True),
            _user("u4", model, "2026-10-21T10:00:01.100Z"),
            _user("u5", stdout, "2026-10-21T10:00:01.200Z"),
            _user("u6", [{"type": "text", "text": PROMPT}], "2026-10-21T10:00:05.000Z"),
        ],
    )

    assert get_initial_prompt(session) == PROMPT
    assert collect_session_data(session).initial_prompt == PROMPT


def test_preamble_only_session_has_no_prompt(tmp_path: Path):
    session = _session_from(
        tmp_path,
        "preamble-only",
        [
            _user("u1", CAVEAT, "2026-10-21T10:00:00.000Z", isMeta=True),
            _user("u2", CLEAR, "2026-10-21T10:00:00.100Z"),
        ],
    )

    assert get_initial_prompt(session) is None
    assert collect_session_data(session).initial_prompt is None


def test_skips_tool_results_and_extracts_command_args(tmp_path: Path):
    tool_result = [{"type": "tool_result", "tool_use_id": "toolu_1", "content": "ok"}]
    skill = (
        "<command-message>review</command-message>\n"
        "<command-name>/review</command-name>\n"
        f"<command-args>{PROMPT}</command-args>"
    )
    lines = [
        _user("u1", tool_result, "2026-10-21T10:00:00.000Z"),
        _user("u2", skill, "2026-10-21T10:00:01.000Z"),
    ]
    jsonl = tmp_path / "skill.jsonl"
    jsonl.write_text("\n".join(json.dumps(line) for line in lines) + "\n", encoding="utf-8")
    session = Session(uuid="skill", jsonl_path=jsonl, claude_base_dir=tmp_path)

    assert get_initial_prompt(session) == PROMPT
    assert collect_session_data(session).initial_prompt == PROMPT


def test_prompt_quoting_caveat_is_kept(tmp_path: Path):
    """A typed prompt that mentions the caveat tag is still the initial prompt."""
    quoted = f"Why does Karma show {CAVEAT} as the prompt?"
    jsonl = tmp_path / "quoted.jsonl"
    line = _user("u1", [{"type": "text", "text": quoted}], "2026-10-21T10:00:00.000Z")
    jsonl.write_text(json.dumps(line) + "\n", encoding="utf-8")
    session = Session(uuid="quoted", jsonl_path=jsonl, claude_base_dir=tmp_path)

    assert get_initial_prompt(session) == quoted
    assert collect_session_data(session).initial_prompt == quoted
