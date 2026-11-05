"""Tests for the fallback title truncation in hooks/session_title_generator.py."""

from __future__ import annotations

import builtins
import io
import json
import subprocess
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


def _run_with_windows_locale(stdout: str):
    """Fake subprocess.run that decodes UTF-8 output the way text=True does under a cp1252 locale."""

    def run(*_args, **kwargs):
        raw = stdout.encode("utf-8")
        text = raw.decode(
            kwargs.get("encoding") or "cp1252", errors=kwargs.get("errors") or "strict"
        )
        return subprocess.CompletedProcess(_args, 0, stdout=text, stderr="")

    return run


def test_haiku_title_keeps_non_ascii(monkeypatch):
    monkeypatch.setattr(
        stg.subprocess,
        "run",
        _run_with_windows_locale("Apply the ≥80% containment rule\n"),
    )
    assert stg.generate_title("Apply the rule", None, None) == (
        "Apply the ≥80% containment rule",
        "haiku",
    )


def test_git_context_keeps_non_ascii(monkeypatch, tmp_path):
    monkeypatch.setattr(
        stg.subprocess,
        "run",
        _run_with_windows_locale("a1b2c3d fix: café menu ≥ 2 items\n"),
    )
    assert (
        stg.get_git_context(str(tmp_path), str(tmp_path / "missing.jsonl"))
        == "a1b2c3d fix: café menu ≥ 2 items"
    )


def _open_with_windows_locale(file, mode="r", *args, encoding=None, **kwargs):
    """open() that falls back to cp1252 like a Windows locale when no encoding is given."""
    if "b" not in mode:
        encoding = encoding or "cp1252"
    return builtins.open(file, mode, *args, encoding=encoding, **kwargs)


def test_transcript_prompt_keeps_non_ascii(monkeypatch, tmp_path):
    monkeypatch.setattr(stg, "open", _open_with_windows_locale, raising=False)
    transcript = tmp_path / "s.jsonl"
    entry = {
        "type": "user",
        "message": {"role": "user", "content": "Apply the ≥80% rule to the café list"},
    }
    transcript.write_text(
        json.dumps(entry, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    prompt, _ = stg.extract_session_context(str(transcript))
    assert prompt == "Apply the ≥80% rule to the café list"


def test_hook_input_with_non_ascii_path_gets_a_title(monkeypatch, tmp_path):
    project = tmp_path / "café"
    project.mkdir()
    transcript = project / "s.jsonl"
    entry = {"type": "user", "message": {"role": "user", "content": "Fix the login bug"}}
    transcript.write_text(json.dumps(entry) + "\n", encoding="utf-8")
    payload = {"session_id": "s1", "transcript_path": str(transcript), "cwd": str(project)}
    raw = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    monkeypatch.setattr(sys, "stdin", io.TextIOWrapper(io.BytesIO(raw), encoding="cp1252"))
    monkeypatch.setattr(stg, "get_git_context", lambda *_a: None)
    monkeypatch.setattr(stg, "generate_title", lambda prompt, *_a: (prompt, "haiku"))
    posted = []
    monkeypatch.setattr(stg, "post_title", lambda sid, title: posted.append((sid, title)))
    stg.main()
    assert posted == [("s1", "Fix the login bug")]


def test_generate_title_runs_given_claude_bin_with_its_dir_on_path(monkeypatch):
    seen = {}

    def run(cmd, **kwargs):
        seen["cmd"], seen["path"] = cmd, kwargs["env"]["PATH"]
        return stg.subprocess.CompletedProcess(cmd, 0, stdout="Fix login redirect\n", stderr="")

    monkeypatch.setattr(stg.subprocess, "run", run)
    monkeypatch.setenv("PATH", "/usr/bin:/bin")
    title, source = stg.generate_title("Fix the login", None, None, claude_bin="/opt/x/bin/claude")
    assert (title, source) == ("Fix login redirect", "haiku")
    assert seen["cmd"][0] == "/opt/x/bin/claude" and seen["path"] == "/opt/x/bin:/usr/bin:/bin"
