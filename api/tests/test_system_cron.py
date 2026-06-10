"""
Unit tests for the system (Linux/macOS) crontab router.

Covers the two pure, OS-independent pieces — line parsing and origin
classification — so the parser is validated on any CI host without needing
a real cron daemon installed.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest

from routers.system_cron import _classify, _human, _parse_line

# ---------------------------------------------------------------------------
# _parse_line — user crontab (5 schedule fields, no user column)
# ---------------------------------------------------------------------------


class TestParseUserCrontab:
    def test_basic_job(self):
        e = _parse_line(
            "*/30 * * * * /home/me/.claude/skills/gmail-triage/run-cron.sh",
            has_user=False,
            source="user crontab",
        )
        assert e is not None
        assert e["schedule"] == "*/30 * * * *"
        assert e["command"] == "/home/me/.claude/skills/gmail-triage/run-cron.sh"
        assert e["user"] is None
        assert e["origin"] == "claude-skill"
        assert e["skill"] == "gmail-triage"

    def test_macro(self):
        e = _parse_line("@daily /home/me/backup.sh", has_user=False, source="user crontab")
        assert e is not None
        assert e["schedule"] == "@daily"
        assert e["command"] == "/home/me/backup.sh"
        assert e["origin"] == "user"

    @pytest.mark.parametrize(
        "line",
        [
            "",
            "   ",
            "# a comment",
            "  # indented comment",
            "PATH=/usr/bin:/bin",
            "MAILTO=me@example.com",
            "*/5 * * *",  # too few fields, no command
        ],
    )
    def test_non_jobs_return_none(self, line):
        assert _parse_line(line, has_user=False, source="user crontab") is None


# ---------------------------------------------------------------------------
# _parse_line — system crontab (extra user column)
# ---------------------------------------------------------------------------


class TestParseSystemCrontab:
    def test_with_user_column(self):
        e = _parse_line(
            "17 *\t* * *\troot\tcd / && run-parts --report /etc/cron.hourly",
            has_user=True,
            source="/etc/crontab",
        )
        assert e is not None
        assert e["schedule"] == "17 * * * *"
        assert e["user"] == "root"
        assert e["command"] == "cd / && run-parts --report /etc/cron.hourly"
        assert e["origin"] == "system"

    def test_macro_with_user(self):
        e = _parse_line("@reboot root /opt/app/start.sh", has_user=True, source="/etc/cron.d/app")
        assert e is not None
        assert e["schedule"] == "@reboot"
        assert e["user"] == "root"
        assert e["command"] == "/opt/app/start.sh"


# ---------------------------------------------------------------------------
# _classify — origin buckets
# ---------------------------------------------------------------------------


class TestClassify:
    def test_skill_via_default_layout(self):
        origin, skill = _classify("/home/x/.claude/skills/foo/run.sh", "user crontab")
        assert origin == "claude-skill"
        assert skill == "foo"

    def test_claude_non_skill(self):
        origin, skill = _classify("/home/x/.claude/hooks/thing.py", "user crontab")
        assert origin == "claude"
        assert skill is None

    def test_system_source(self):
        assert _classify("run-parts /etc/cron.daily", "/etc/crontab")[0] == "system"
        assert _classify("/usr/bin/foo", "/etc/cron.d/php")[0] == "system"

    def test_plain_user(self):
        origin, skill = _classify("/home/x/scripts/backup.sh", "user crontab")
        assert origin == "user"
        assert skill is None

    def test_custom_claude_base(self, monkeypatch):
        """A non-default CLAUDE_KARMA_CLAUDE_BASE must still be recognised."""
        from config import settings

        # skills_dir is a derived property (claude_base/"skills"), so patching
        # claude_base alone is enough — and the only thing that *can* be patched.
        monkeypatch.setattr(settings, "claude_base", Path("/opt/claude"))
        origin, skill = _classify("/opt/claude/skills/bar/go.sh", "user crontab")
        assert origin == "claude-skill"
        assert skill == "bar"

    def test_command_wins_over_source(self):
        """A skill scheduled from /etc/cron.d is still a skill, not system."""
        origin, skill = _classify("/home/x/.claude/skills/foo/run.sh", "/etc/cron.d/foo")
        assert origin == "claude-skill"
        assert skill == "foo"


# ---------------------------------------------------------------------------
# _human — schedule humanisation (smoke)
# ---------------------------------------------------------------------------


class TestHuman:
    @pytest.mark.parametrize(
        "expr,expected",
        [
            ("* * * * *", "every min"),
            ("*/30 * * * *", "every 30 min"),
            ("0 */2 * * *", "every 2h"),
            ("30 9 * * *", "daily 09:30"),
            ("@daily", "daily"),
            ("@reboot", "at boot"),
        ],
    )
    def test_known_shapes(self, expr, expected):
        assert _human(expr) == expected

    def test_unknown_falls_back_to_raw(self):
        assert _human("15 14 1 * 5") == "15 14 1 * 5"
