"""Tests for the fallback title truncation in hooks/session_title_generator.py."""

from __future__ import annotations

import sys
from pathlib import Path

_hooks_dir = Path(__file__).resolve().parent.parent
if str(_hooks_dir) not in sys.path:
    sys.path.insert(0, str(_hooks_dir))

import session_title_generator as stg  # noqa: E402


def test_short_prompt_is_kept_whole():
    assert stg.truncate_title("Fix the login bug") == "Fix the login bug"


def test_exactly_at_limit_has_no_ellipsis():
    text = "a" * 60
    assert stg.truncate_title(text) == text


def test_long_prompt_cuts_at_word_boundary_with_one_ellipsis():
    text = "Refactor the session title generator so fallback titles stop cutting words in half"
    title = stg.truncate_title(text)
    assert title == "Refactor the session title generator so fallback titles…"
    assert len(title) <= stg.FALLBACK_TITLE_MAX_CHARS
    assert title.count("…") == 1 and "..." not in title


def test_word_ending_exactly_at_cut_is_kept():
    text = "word " * 11 + "1234 trailing words"
    title = stg.truncate_title(text)
    assert title == ("word " * 11).strip() + " 1234…"
    assert len(title) == stg.FALLBACK_TITLE_MAX_CHARS


def test_whitespace_and_newlines_collapse():
    text = "Another Claude session sent a message:\n<cross-session-message from='x'>  hello there friend</cross>"
    title = stg.truncate_title(text)
    assert "\n" not in title and "  " not in title
    assert title == "Another Claude session sent a message…"


def test_trailing_punctuation_is_dropped_before_ellipsis():
    text = "Investigate the flaky test, then fix it; also update the docs and the changelog"
    title = stg.truncate_title(text)
    assert title.endswith("…")
    assert not title[:-1].endswith((",", ";", ":", "."))


def test_single_long_token_is_cut_mid_word():
    text = "/Users/someone/Documents/GitHub/a-very-long-repository-name/with/a/deep/path/file.py"
    title = stg.truncate_title(text)
    assert title == text[:59] + "…"
    assert len(title) == stg.FALLBACK_TITLE_MAX_CHARS


def test_generate_title_fallback_uses_truncation(monkeypatch):
    def fail(*_args, **_kwargs):
        raise FileNotFoundError("claude")

    monkeypatch.setattr(stg.subprocess, "run", fail)
    prompt = "Please review the onboarding flow and list every place where copy is unclear to new users"
    title, source = stg.generate_title(prompt, None, None)
    assert source == "fallback"
    assert title == stg.truncate_title(prompt)
    assert title.endswith("…") and len(title) <= stg.FALLBACK_TITLE_MAX_CHARS
