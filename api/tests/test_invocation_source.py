"""Tests for invocation source tracking: dedup logic, aggregate helpers, and plugin name normalization."""

from collections import Counter
from pathlib import Path

import pytest

from command_helpers import (
    _build_entry_to_plugin_map,
    _entry_map_cache,
    _expand_name_cache,
    _is_plugin_skill,
    _plugin_skill_cache,
    aggregate_by_name,
    expand_plugin_short_name,
)
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


def _clear_caches():
    """Clear all TTL caches between tests."""
    _plugin_skill_cache.clear()
    _expand_name_cache.clear()
    _entry_map_cache.clear()


def _make_plugin(base: Path, plugin_name: str, entries: list[str], *, kind: str = "skills"):
    """Create a mock plugin directory structure under base/plugins/cache/.

    Args:
        base: The claude_base directory (e.g., tmp_path / ".claude")
        plugin_name: Plugin directory name (e.g., "frontend-design")
        entries: List of entry names to create
        kind: "skills" (directory-based), "commands" (file-based), or "agents" (file-based)
    """
    version_dir = base / "plugins" / "cache" / "registry" / plugin_name / "1.0.0"
    target_dir = version_dir / kind
    target_dir.mkdir(parents=True, exist_ok=True)

    for entry in entries:
        if kind == "skills":
            (target_dir / entry).mkdir(exist_ok=True)
        else:
            (target_dir / f"{entry}.md").write_text(f"# {entry}")


@pytest.fixture(autouse=False)
def mock_claude_base(tmp_path, monkeypatch):
    """Provide a temp claude_base and clear caches before/after each test."""
    _clear_caches()
    claude_base = tmp_path / ".claude"
    claude_base.mkdir()
    monkeypatch.setattr("config.settings.claude_base", claude_base)
    yield claude_base
    _clear_caches()


class TestIsPluginSkill:
    """Tests for _is_plugin_skill() filesystem-based plugin detection."""

    def test_known_plugin_returns_true(self, mock_claude_base):
        _make_plugin(mock_claude_base, "frontend-design", ["frontend-design"])
        assert _is_plugin_skill("frontend-design") is True

    def test_unknown_name_returns_false(self, mock_claude_base):
        assert _is_plugin_skill("nonexistent-plugin") is False

    def test_no_plugins_cache_dir(self, mock_claude_base):
        # Don't create any plugins dir
        assert _is_plugin_skill("anything") is False

    def test_cache_invalidates_after_ttl(self, mock_claude_base):
        """Verify cache is used (same call returns cached result)."""
        assert _is_plugin_skill("my-plugin") is False
        # Now create the plugin
        _make_plugin(mock_claude_base, "my-plugin", ["my-plugin"])
        # Still returns False due to TTL cache
        assert _is_plugin_skill("my-plugin") is False
        # But after clearing cache, picks up the new plugin
        _clear_caches()
        assert _is_plugin_skill("my-plugin") is True


class TestExpandPluginShortName:
    """Tests for expand_plugin_short_name() name normalization."""

    def test_already_full_form_unchanged(self, mock_claude_base):
        assert expand_plugin_short_name("oh-my-claudecode:cancel") == "oh-my-claudecode:cancel"

    def test_plugin_name_with_matching_entry(self, mock_claude_base):
        """Plugin name == entry name → 'name:name'."""
        _make_plugin(mock_claude_base, "frontend-design", ["frontend-design"])
        assert expand_plugin_short_name("frontend-design") == "frontend-design:frontend-design"

    def test_plugin_with_single_entry(self, mock_claude_base):
        """Plugin has one entry different from its name → 'plugin:entry'."""
        _make_plugin(mock_claude_base, "my-plugin", ["the-skill"])
        assert expand_plugin_short_name("my-plugin") == "my-plugin:the-skill"

    def test_plugin_with_multiple_entries_no_match(self, mock_claude_base):
        """Plugin has multiple entries, none matching name → unchanged."""
        _make_plugin(mock_claude_base, "multi", ["skill-a", "skill-b"])
        assert expand_plugin_short_name("multi") == "multi"

    def test_reverse_lookup_entry_name(self, mock_claude_base):
        """Entry name without plugin prefix → 'plugin:entry' via reverse map."""
        _make_plugin(mock_claude_base, "commit-commands", ["commit", "clean_gone"])
        assert expand_plugin_short_name("commit") == "commit-commands:commit"

    def test_unknown_name_unchanged(self, mock_claude_base):
        assert expand_plugin_short_name("totally-unknown") == "totally-unknown"

    def test_no_plugins_dir_unchanged(self, mock_claude_base):
        assert expand_plugin_short_name("anything") == "anything"

    def test_agents_dir_entries(self, mock_claude_base):
        """Entries in agents/ dir are discovered."""
        _make_plugin(mock_claude_base, "my-plugin", ["code-reviewer"], kind="agents")
        assert expand_plugin_short_name("code-reviewer") == "my-plugin:code-reviewer"

    def test_commands_dir_entries(self, mock_claude_base):
        """Entries in commands/ dir are discovered."""
        _make_plugin(mock_claude_base, "my-plugin", ["feature-dev"], kind="commands")
        assert expand_plugin_short_name("feature-dev") == "my-plugin:feature-dev"


class TestBuildEntryToPluginMap:
    """Tests for _build_entry_to_plugin_map() reverse lookup building."""

    def test_single_plugin_entries_mapped(self, mock_claude_base):
        _make_plugin(mock_claude_base, "commit-commands", ["commit", "clean_gone"])
        result = _build_entry_to_plugin_map()
        assert result["commit"] == "commit-commands:commit"
        assert result["clean_gone"] == "commit-commands:clean_gone"

    def test_ambiguous_entries_excluded(self, mock_claude_base):
        """If two plugins define the same entry, it's excluded."""
        _make_plugin(mock_claude_base, "plugin-a", ["shared-skill"])
        # Create second plugin in same registry
        version_dir = mock_claude_base / "plugins" / "cache" / "registry" / "plugin-b" / "1.0.0"
        skills_dir = version_dir / "skills"
        skills_dir.mkdir(parents=True)
        (skills_dir / "shared-skill").mkdir()
        result = _build_entry_to_plugin_map()
        assert "shared-skill" not in result

    def test_entry_same_as_plugin_name_excluded(self, mock_claude_base):
        """Entry == plugin name is skipped (handled by expand_plugin_short_name case 1)."""
        _make_plugin(mock_claude_base, "my-plugin", ["my-plugin"])
        result = _build_entry_to_plugin_map()
        assert "my-plugin" not in result

    def test_empty_plugins_dir(self, mock_claude_base):
        result = _build_entry_to_plugin_map()
        assert result == {}
