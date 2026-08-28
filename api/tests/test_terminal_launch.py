"""Unit tests for services.terminal_launch (osascript calls mocked)."""

from __future__ import annotations

import sys
from pathlib import Path

_api_dir = Path(__file__).resolve().parent.parent
if str(_api_dir) not in sys.path:
    sys.path.insert(0, str(_api_dir))

import services.terminal_launch as tl

UUID = "aaaaaaaa-1111-2222-3333-444444444444"


def test_build_command_quotes_path():
    cmd = tl._build_command("/Users/me/my repo", UUID)
    assert cmd == f"cd '/Users/me/my repo' && claude --resume {UUID}"


def test_build_command_quotes_hostile_path():
    cmd = tl._build_command("/tmp/a'; rm -rf ~", UUID)
    # shlex.quote must neutralize the embedded quote — no bare `; rm` remains.
    assert "; rm" not in cmd.replace("'; rm", "")
    assert cmd.startswith("cd ")


def test_non_darwin_is_honest(monkeypatch):
    monkeypatch.setattr(sys, "platform", "linux")
    result = tl.launch_resume_in_terminal("/tmp", UUID)
    assert result["launched"] is False
    assert "macOS" in result["detail"]


def test_iterm_hint_uses_iterm_when_running(monkeypatch):
    monkeypatch.setattr(sys, "platform", "darwin")
    monkeypatch.setattr(tl, "_app_is_running", lambda target: True)
    scripts = []
    monkeypatch.setattr(tl, "_osascript", lambda script: scripts.append(script) or None)

    result = tl.launch_resume_in_terminal("/tmp/repo", UUID, term_program="iTerm.app")
    assert result["launched"] is True
    assert result["method"] == "iterm-tab"
    assert 'tell application "iTerm2"' in scripts[0]
    assert f"claude --resume {UUID}" in scripts[0]


def test_iterm_hint_falls_back_when_not_running(monkeypatch):
    monkeypatch.setattr(sys, "platform", "darwin")
    monkeypatch.setattr(tl, "_app_is_running", lambda target: False)
    scripts = []
    monkeypatch.setattr(tl, "_osascript", lambda script: scripts.append(script) or None)

    result = tl.launch_resume_in_terminal("/tmp/repo", UUID, term_program="iTerm.app")
    assert result["launched"] is True
    assert result["method"] == "terminal-window"
    assert 'tell application "Terminal"' in scripts[0]


def test_default_is_terminal_app(monkeypatch):
    monkeypatch.setattr(sys, "platform", "darwin")
    scripts = []
    monkeypatch.setattr(tl, "_osascript", lambda script: scripts.append(script) or None)

    result = tl.launch_resume_in_terminal("/tmp/repo", UUID, term_program="Apple_Terminal")
    assert result["launched"] is True
    assert result["method"] == "terminal-window"


def test_osascript_failure_is_honest(monkeypatch):
    monkeypatch.setattr(sys, "platform", "darwin")
    monkeypatch.setattr(tl, "_osascript", lambda script: "execution error: not allowed (-1743)")

    result = tl.launch_resume_in_terminal("/tmp/repo", UUID)
    assert result["launched"] is False
    assert "-1743" in result["detail"]
