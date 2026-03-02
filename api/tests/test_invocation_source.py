"""Tests for invocation source tracking: dedup logic and aggregate helpers."""

from collections import Counter

import pytest

from command_helpers import aggregate_by_name
from models.session import _dedup_invocation_sources


class TestDedupInvocationSources:
    """Tests for _dedup_invocation_sources() which prevents double-counting
    when the same skill invocation fires multiple detection sources."""

    def test_slash_command_absorbs_skill_tool(self):
        """User types /commit → fires slash_command + skill_tool. Should keep 1 slash_command."""
        counter = Counter({
            ("commit", "slash_command"): 1,
            ("commit", "skill_tool"): 1,
        })
        _dedup_invocation_sources(counter)
        assert counter[("commit", "slash_command")] == 1
        assert ("commit", "skill_tool") not in counter

    def test_slash_command_absorbs_text_detection(self):
        """User types /commit → fires slash_command + text_detection. Should keep 1 slash_command."""
        counter = Counter({
            ("commit", "slash_command"): 1,
            ("commit", "text_detection"): 1,
        })
        _dedup_invocation_sources(counter)
        assert counter[("commit", "slash_command")] == 1
        assert ("commit", "text_detection") not in counter

    def test_all_three_sources_deduped(self):
        """User types /skill → fires all three sources. Should keep only slash_command."""
        counter = Counter({
            ("autopilot", "slash_command"): 1,
            ("autopilot", "skill_tool"): 1,
            ("autopilot", "text_detection"): 1,
        })
        _dedup_invocation_sources(counter)
        assert counter[("autopilot", "slash_command")] == 1
        assert ("autopilot", "skill_tool") not in counter
        assert ("autopilot", "text_detection") not in counter

    def test_extra_auto_calls_preserved(self):
        """3 manual + 5 auto → 3 manual + 2 auto (absorbs 3 from auto)."""
        counter = Counter({
            ("review", "slash_command"): 3,
            ("review", "skill_tool"): 5,
        })
        _dedup_invocation_sources(counter)
        assert counter[("review", "slash_command")] == 3
        assert counter[("review", "skill_tool")] == 2

    def test_only_auto_calls_untouched(self):
        """Pure auto invocations (no slash_command) should not be absorbed."""
        counter = Counter({
            ("autopilot", "skill_tool"): 3,
        })
        _dedup_invocation_sources(counter)
        assert counter[("autopilot", "skill_tool")] == 3

    def test_only_text_detection_untouched(self):
        """Pure text_detection invocations should not be absorbed."""
        counter = Counter({
            ("commit", "text_detection"): 2,
        })
        _dedup_invocation_sources(counter)
        assert counter[("commit", "text_detection")] == 2

    def test_multiple_skills_independent(self):
        """Different skills are deduped independently."""
        counter = Counter({
            ("commit", "slash_command"): 1,
            ("commit", "skill_tool"): 1,
            ("review", "skill_tool"): 3,
        })
        _dedup_invocation_sources(counter)
        # commit: slash absorbs skill_tool
        assert counter[("commit", "slash_command")] == 1
        assert ("commit", "skill_tool") not in counter
        # review: no slash_command, so skill_tool untouched
        assert counter[("review", "skill_tool")] == 3

    def test_empty_counter(self):
        """Empty counter should be a no-op."""
        counter = Counter()
        _dedup_invocation_sources(counter)
        assert len(counter) == 0

    def test_single_source_no_change(self):
        """Single source per skill should not be modified."""
        counter = Counter({
            ("commit", "slash_command"): 5,
        })
        _dedup_invocation_sources(counter)
        assert counter[("commit", "slash_command")] == 5

    def test_skill_tool_absorbs_text_detection(self):
        """skill_tool (higher priority) absorbs text_detection when no slash_command."""
        counter = Counter({
            ("autopilot", "skill_tool"): 2,
            ("autopilot", "text_detection"): 2,
        })
        _dedup_invocation_sources(counter)
        assert counter[("autopilot", "skill_tool")] == 2
        assert ("autopilot", "text_detection") not in counter


class TestAggregateByName:
    """Tests for aggregate_by_name() which collapses (name, source) keys to name-only."""

    def test_tuple_keys_aggregated(self):
        items = {
            ("commit", "slash_command"): 3,
            ("commit", "skill_tool"): 2,
            ("review", "skill_tool"): 1,
        }
        result = aggregate_by_name(items)
        assert result == {"commit": 5, "review": 1}

    def test_plain_string_keys_passthrough(self):
        items = {"commit": 3, "review": 1}
        result = aggregate_by_name(items)
        assert result == {"commit": 3, "review": 1}

    def test_empty_dict(self):
        assert aggregate_by_name({}) == {}

    def test_mixed_keys(self):
        """Mix of tuple and string keys (shouldn't happen but handles gracefully)."""
        items = {
            ("commit", "slash_command"): 2,
            "review": 1,
        }
        result = aggregate_by_name(items)
        assert result == {"commit": 2, "review": 1}
