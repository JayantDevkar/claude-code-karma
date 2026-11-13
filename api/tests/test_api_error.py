"""Classification of API-error assistant turns."""

from datetime import datetime, timezone

from models.message import parse_message

from .api_error_fixtures import (
    limit_line,
    no_response_line,
    refusal_line,
    reply_line,
    server_error_line,
)

TS = "2026-01-10T10:00:00.000Z"


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
