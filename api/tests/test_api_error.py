"""Classification of API-error assistant turns."""

from datetime import datetime, timezone

from models.agent import Agent
from models.message import parse_message
from models.session import Session

from .api_error_fixtures import (
    SESSION_ID,
    bookkeeping_line,
    limit_line,
    no_response_line,
    refusal_line,
    reply_line,
    server_error_line,
    user_line,
    write_jsonl,
)

TS = "2026-01-10T10:00:00.000Z"
RESET = datetime(2026, 1, 10, 12, tzinfo=timezone.utc)


def _ts(n):
    return f"2026-01-10T10:{n:02d}:00.000Z"


def _session(tmp_path, lines):
    path = tmp_path / "projects" / "-home-alice-project" / f"{SESSION_ID}.jsonl"
    write_jsonl(path, lines)
    Session.clear_all_caches()
    return Session.from_path(path)


def _u(n):
    return user_line(f"u{n}", None, _ts(n), "go")


def _sidechain(line):
    line["isSidechain"] = True
    return line


def test_limit_turn_classified_with_reset():
    m = parse_message(limit_line("a1", "u1", TS, resets_at=1768046400))
    assert m.api_error.kind == "limit"
    assert m.api_error.code == "usage_limit_reached"
    assert m.api_error.status == 429
    assert m.api_error.resets_at == datetime(2026, 1, 10, 12, 0, tzinfo=timezone.utc)
    assert m.api_error.text.startswith("You've hit your session limit")
    assert m.is_synthetic


def test_refusal_wins_over_category():
    m = parse_message(refusal_line("a1", "u1", TS))
    assert m.api_error.kind == "refusal"
    assert m.api_error.code == "invalid_request"


def test_refusal_wins_over_rate_limit_error():
    line = refusal_line("a1", "u1", TS)
    line["error"] = "rate_limit"
    assert parse_message(line).api_error.kind == "refusal"


def test_other_error_is_api_error():
    m = parse_message(server_error_line("a1", "u1", TS))
    assert m.api_error.kind == "api_error"
    assert m.api_error.code == "connection_failed"
    assert m.api_error.resets_at is None


def test_error_key_without_marker_is_not_error():
    line = reply_line("a1", "u1", TS, "hi")
    line["error"] = "rate_limit"
    assert parse_message(line).api_error is None


def test_limit_without_quota_has_no_reset():
    line = limit_line("a1", "u1", TS)
    line.pop("quotaLimits")
    m = parse_message(line)
    assert m.api_error.kind == "limit"
    assert m.api_error.resets_at is None


def test_limit_with_string_reset_has_no_reset():
    m = parse_message(limit_line("a1", "u1", TS, resets_at="soon"))
    assert m.api_error.kind == "limit"
    assert m.api_error.resets_at is None


def test_limit_with_absurd_reset_does_not_raise():
    m = parse_message(limit_line("a1", "u1", TS, resets_at=1e30))
    assert m.api_error.kind == "limit"
    assert m.api_error.resets_at is None


def test_no_response_turn_is_synthetic_not_error():
    m = parse_message(no_response_line("a1", "u1", TS))
    assert m.api_error is None
    assert m.is_synthetic


def test_normal_reply_untouched():
    m = parse_message(reply_line("a1", "u1", TS, "hi"))
    assert m.api_error is None
    assert not m.is_synthetic


def test_session_ends_on_limit_after_healed_hit(tmp_path):
    s = _session(
        tmp_path,
        [
            _u(1),
            limit_line("a1", "u1", _ts(2)),
            _u(3),
            reply_line("a2", "u3", _ts(4), "ok"),
            _u(5),
            limit_line("a3", "u5", _ts(6)),
        ],
    )
    sm = s.api_error_summary
    assert (sm.ended_by, sm.limit_hit_count) == ("limit", 2)
    assert sm.ended_resets_at == RESET
    assert sm.ended_turn_uuid == "a3"
    assert "<synthetic>" not in s.get_models_used()
    assert s.message_count == 6
    assert s._get_cache().assistant_message_count == 1


def test_healed_limit_is_not_ended(tmp_path):
    s = _session(
        tmp_path,
        [_u(1), limit_line("a1", "u1", _ts(2)), _u(3), reply_line("a2", "u3", _ts(4), "ok")],
    )
    sm = s.api_error_summary
    assert (sm.ended_by, sm.limit_hit_count) == (None, 1)
    assert sm.ended_turn_uuid is None
    assert sm.ended_resets_at is None


def test_trailing_bookkeeping_keeps_ended(tmp_path):
    s = _session(
        tmp_path,
        [
            _u(1),
            limit_line("a1", "u1", _ts(2)),
            bookkeeping_line("queue-operation"),
            bookkeeping_line("queue-operation"),
        ],
    )
    assert s.api_error_summary.ended_by == "limit"


def test_user_prompt_without_reply_keeps_ended(tmp_path):
    s = _session(tmp_path, [_u(1), limit_line("a1", "u1", _ts(2)), _u(3)])
    assert s.api_error_summary.ended_by == "limit"


def test_no_response_turn_does_not_heal(tmp_path):
    s = _session(
        tmp_path, [_u(1), limit_line("a1", "u1", _ts(2)), no_response_line("a2", "u1", _ts(3))]
    )
    sm = s.api_error_summary
    assert sm.ended_by == "limit"
    assert sm.ended_turn_uuid == "a1"


def test_final_refusal(tmp_path):
    s = _session(tmp_path, [_u(1), refusal_line("a1", "u1", _ts(2))])
    assert s.api_error_summary.ended_by == "refusal"


def test_final_server_error(tmp_path):
    s = _session(tmp_path, [_u(1), server_error_line("a1", "u1", _ts(2))])
    sm = s.api_error_summary
    assert (sm.ended_by, sm.limit_hit_count) == ("api_error", 0)


def test_sidechain_turn_ignored_for_session(tmp_path):
    s = _session(
        tmp_path,
        [
            _u(1),
            limit_line("a1", "u1", _ts(2)),
            _sidechain(reply_line("a2", "u1", _ts(3), "side")),
        ],
    )
    assert s.api_error_summary.ended_by == "limit"


def test_agent_ends_on_limit(tmp_path):
    path = tmp_path / "projects" / "-home-alice-project" / "agent-abc123.jsonl"
    write_jsonl(
        path,
        [
            _sidechain(_u(1)),
            _sidechain(reply_line("a1", "u1", _ts(2), "ok")),
            _sidechain(limit_line("a2", "a1", _ts(3))),
        ],
    )
    Agent.clear_all_caches()
    agent = Agent.from_path(path)
    sm = agent.api_error_summary
    assert (sm.ended_by, sm.limit_hit_count) == ("limit", 1)
    assert "<synthetic>" not in agent.get_models_used()
