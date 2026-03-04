"""Tests for invocation source tracking: dedup logic, aggregate helpers, and plugin name normalization."""

from collections import Counter
from pathlib import Path

import pytest

from command_helpers import (
    _build_entry_to_plugin_map,
    _build_entry_type_map,
    _entry_map_cache,
    _entry_type_cache,
    _expand_name_cache,
    _is_plugin_skill,
    _plugin_skill_cache,
    aggregate_by_name,
    classify_invocation,
    detect_slash_commands_in_text,
    expand_plugin_short_name,
    is_command_category,
    is_skill_category,
    parse_command_from_content,
)
from models.session import _apply_command_triggered, _dedup_invocation_sources


class TestDedupInvocationSources:
    """Tests for _dedup_invocation_sources() which prevents double-counting
    when the same skill invocation fires multiple detection sources."""

    def test_slash_command_absorbs_skill_tool(self):
        """User types /commit → fires slash_command + skill_tool. Should keep 1 slash_command."""
        counter = Counter(
            {
                ("commit", "slash_command"): 1,
                ("commit", "skill_tool"): 1,
            }
        )
        _dedup_invocation_sources(counter)
        assert counter[("commit", "slash_command")] == 1
        assert ("commit", "skill_tool") not in counter

    def test_slash_command_absorbs_text_detection(self):
        """User types /commit → fires slash_command + text_detection. Should keep 1 slash_command."""
        counter = Counter(
            {
                ("commit", "slash_command"): 1,
                ("commit", "text_detection"): 1,
            }
        )
        _dedup_invocation_sources(counter)
        assert counter[("commit", "slash_command")] == 1
        assert ("commit", "text_detection") not in counter

    def test_all_three_sources_deduped(self):
        """User types /skill → fires all three sources. Should keep only slash_command."""
        counter = Counter(
            {
                ("autopilot", "slash_command"): 1,
                ("autopilot", "skill_tool"): 1,
                ("autopilot", "text_detection"): 1,
            }
        )
        _dedup_invocation_sources(counter)
        assert counter[("autopilot", "slash_command")] == 1
        assert ("autopilot", "skill_tool") not in counter
        assert ("autopilot", "text_detection") not in counter

    def test_extra_auto_calls_preserved(self):
        """3 manual + 5 auto → 3 manual + 2 auto (absorbs 3 from auto)."""
        counter = Counter(
            {
                ("review", "slash_command"): 3,
                ("review", "skill_tool"): 5,
            }
        )
        _dedup_invocation_sources(counter)
        assert counter[("review", "slash_command")] == 3
        assert counter[("review", "skill_tool")] == 2

    def test_only_auto_calls_untouched(self):
        """Pure auto invocations (no slash_command) should not be absorbed."""
        counter = Counter(
            {
                ("autopilot", "skill_tool"): 3,
            }
        )
        _dedup_invocation_sources(counter)
        assert counter[("autopilot", "skill_tool")] == 3

    def test_only_text_detection_untouched(self):
        """Pure text_detection invocations should not be absorbed."""
        counter = Counter(
            {
                ("commit", "text_detection"): 2,
            }
        )
        _dedup_invocation_sources(counter)
        assert counter[("commit", "text_detection")] == 2

    def test_multiple_skills_independent(self):
        """Different skills are deduped independently."""
        counter = Counter(
            {
                ("commit", "slash_command"): 1,
                ("commit", "skill_tool"): 1,
                ("review", "skill_tool"): 3,
            }
        )
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
        counter = Counter(
            {
                ("commit", "slash_command"): 5,
            }
        )
        _dedup_invocation_sources(counter)
        assert counter[("commit", "slash_command")] == 5

    def test_command_triggered_not_absorbed(self):
        """command_triggered is independent — not absorbed by slash_command or skill_tool."""
        counter = Counter(
            {
                ("brainstorming", "command_triggered"): 1,
                ("brainstorming", "skill_tool"): 2,
            }
        )
        _dedup_invocation_sources(counter)
        assert counter[("brainstorming", "command_triggered")] == 1
        assert counter[("brainstorming", "skill_tool")] == 2

    def test_command_triggered_alone_untouched(self):
        """Pure command_triggered entries should not be modified."""
        counter = Counter(
            {
                ("brainstorming", "command_triggered"): 3,
            }
        )
        _dedup_invocation_sources(counter)
        assert counter[("brainstorming", "command_triggered")] == 3

    def test_text_detection_plus_skill_tool_upgrades_to_slash_command(self):
        """text_detection + skill_tool (no slash_command) → upgrade to slash_command.

        User typed /command in text AND Claude invoked Skill tool = manual invocation.
        """
        counter = Counter(
            {
                ("autopilot", "skill_tool"): 2,
                ("autopilot", "text_detection"): 2,
            }
        )
        _dedup_invocation_sources(counter)
        assert counter[("autopilot", "slash_command")] == 2
        assert ("autopilot", "skill_tool") not in counter
        assert ("autopilot", "text_detection") not in counter

    def test_text_detection_plus_skill_tool_partial_upgrade(self):
        """More skill_tool than text_detection → partial upgrade, rest stays auto."""
        counter = Counter(
            {
                ("autopilot", "skill_tool"): 3,
                ("autopilot", "text_detection"): 1,
            }
        )
        _dedup_invocation_sources(counter)
        # 1 upgraded to slash_command, 2 remain as skill_tool
        assert counter[("autopilot", "slash_command")] == 1
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
    _entry_type_cache.clear()


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


class TestBuildEntryTypeMap:
    """Tests for _build_entry_type_map() which maps plugin:entry → type."""

    def test_command_entries_mapped(self, mock_claude_base):
        _make_plugin(mock_claude_base, "superpowers", ["brainstorm"], kind="commands")
        result = _build_entry_type_map()
        assert result["superpowers:brainstorm"] == "command"

    def test_skill_entries_mapped(self, mock_claude_base):
        _make_plugin(mock_claude_base, "superpowers", ["brainstorming"], kind="skills")
        result = _build_entry_type_map()
        assert result["superpowers:brainstorming"] == "skill"

    def test_mixed_entries(self, mock_claude_base):
        """Plugin with commands + skills all mapped correctly."""
        _make_plugin(mock_claude_base, "superpowers", ["brainstorm"], kind="commands")
        _make_plugin(mock_claude_base, "superpowers", ["brainstorming"], kind="skills")
        result = _build_entry_type_map()
        assert result["superpowers:brainstorm"] == "command"
        assert result["superpowers:brainstorming"] == "skill"

    def test_agent_entries_mapped(self, mock_claude_base):
        _make_plugin(mock_claude_base, "my-plugin", ["code-reviewer"], kind="agents")
        result = _build_entry_type_map()
        assert result["my-plugin:code-reviewer"] == "agent"

    def test_skill_takes_priority_over_command_when_both_exist(self, mock_claude_base):
        """When skills/X/ and commands/X.md both exist, classify as 'skill'."""
        _make_plugin(mock_claude_base, "my-plugin", ["autopilot"], kind="skills")
        _make_plugin(mock_claude_base, "my-plugin", ["autopilot"], kind="commands")
        result = _build_entry_type_map()
        assert result["my-plugin:autopilot"] == "skill"

    def test_empty_plugins_dir(self, mock_claude_base):
        result = _build_entry_type_map()
        assert result == {}


class TestClassifyInvocation:
    """Tests for classify_invocation() with entry type awareness."""

    def test_plugin_command_classified_as_plugin_command(self, mock_claude_base):
        """superpowers:brainstorm (in commands/) → 'plugin_command'."""
        _make_plugin(mock_claude_base, "superpowers", ["brainstorm"], kind="commands")
        assert classify_invocation("superpowers:brainstorm") == "plugin_command"

    def test_plugin_command_is_command_category(self):
        assert is_command_category("plugin_command") is True

    def test_plugin_command_is_not_skill_category(self):
        assert is_skill_category("plugin_command") is False

    def test_plugin_skill_classified_as_plugin_skill(self, mock_claude_base):
        """superpowers:brainstorming (in skills/) → 'plugin_skill'."""
        _make_plugin(mock_claude_base, "superpowers", ["brainstorming"], kind="skills")
        assert classify_invocation("superpowers:brainstorming") == "plugin_skill"

    def test_unknown_plugin_entry_defaults_to_plugin_skill(self, mock_claude_base):
        """Backward compat: unknown plugin:entry defaults to 'plugin_skill'."""
        assert classify_invocation("unknown-plugin:unknown-entry") == "plugin_skill"

    def test_builtin_classified_as_builtin_command(self, mock_claude_base):
        """/exit → 'builtin_command' regardless of entry type map."""
        assert classify_invocation("exit") == "builtin_command"

    def test_custom_skill_classified_as_custom_skill(self, mock_claude_base):
        """Custom skills (no ':') classified as 'custom_skill' when SKILL.md exists."""
        skills_dir = mock_claude_base / "skills" / "my-custom-skill"
        skills_dir.mkdir(parents=True)
        (skills_dir / "SKILL.md").write_text("# My Skill")
        assert classify_invocation("my-custom-skill") == "custom_skill"

    def test_plugin_agent_classified_as_agent(self, mock_claude_base):
        """feature-dev:code-explorer (in agents/) → 'agent'."""
        _make_plugin(mock_claude_base, "feature-dev", ["code-explorer"], kind="agents")
        assert classify_invocation("feature-dev:code-explorer") == "agent"

    def test_overlapping_skill_and_command_prefers_plugin_skill(self, mock_claude_base):
        """oh-my-claudecode:autopilot in both skills/ and commands/ → 'plugin_skill'."""
        _make_plugin(mock_claude_base, "oh-my-claudecode", ["autopilot"], kind="skills")
        _make_plugin(mock_claude_base, "oh-my-claudecode", ["autopilot"], kind="commands")
        assert classify_invocation("oh-my-claudecode:autopilot") == "plugin_skill"

    def test_bundled_skill_classified_as_bundled_skill(self, mock_claude_base):
        """Bundled Claude Code skills (e.g. /simplify) → 'bundled_skill'."""
        assert classify_invocation("simplify") == "bundled_skill"


class TestIsSkillCategory:
    """Tests for is_skill_category() helper."""

    def test_bundled_skill_is_skill_category(self):
        assert is_skill_category("bundled_skill") is True

    def test_plugin_skill_is_skill_category(self):
        assert is_skill_category("plugin_skill") is True

    def test_custom_skill_is_skill_category(self):
        assert is_skill_category("custom_skill") is True

    def test_agent_is_not_skill_category(self):
        assert is_skill_category("agent") is False

    def test_builtin_command_is_not_skill_category(self):
        assert is_skill_category("builtin_command") is False

    def test_user_command_is_not_skill_category(self):
        assert is_skill_category("user_command") is False


class TestIsCommandCategory:
    """Tests for is_command_category() helper."""

    def test_builtin_command_is_command_category(self):
        assert is_command_category("builtin_command") is True

    def test_user_command_is_command_category(self):
        assert is_command_category("user_command") is True

    def test_plugin_skill_is_not_command_category(self):
        assert is_command_category("plugin_skill") is False

    def test_bundled_skill_is_not_command_category(self):
        assert is_command_category("bundled_skill") is False

    def test_agent_is_not_command_category(self):
        assert is_command_category("agent") is False

    def test_custom_skill_is_not_command_category(self):
        assert is_command_category("custom_skill") is False


class TestCommandTriggeredLinkage:
    """Tests for turn-based command→skill linkage via pending_commands state."""

    def test_same_plugin_command_triggers_skill(self):
        """Command from plugin X + Skill tool from plugin X → command_triggered."""
        pending_commands: set[str] = {"superpowers"}
        skills: Counter[tuple] = Counter({("superpowers:brainstorming", "skill_tool"): 1})
        _apply_command_triggered(pending_commands, skills)
        assert ("superpowers:brainstorming", "skill_tool") not in skills
        assert skills[("superpowers:brainstorming", "command_triggered")] == 1

    def test_different_plugin_no_linkage(self):
        """Command from plugin A doesn't affect skill from plugin B."""
        pending_commands: set[str] = {"plugin-a"}
        skills: Counter[tuple] = Counter({("plugin-b:skill", "skill_tool"): 1})
        _apply_command_triggered(pending_commands, skills)
        assert skills[("plugin-b:skill", "skill_tool")] == 1

    def test_no_pending_commands_no_change(self):
        """No pending commands → skills unchanged."""
        pending_commands: set[str] = set()
        skills: Counter[tuple] = Counter({("superpowers:brainstorming", "skill_tool"): 2})
        _apply_command_triggered(pending_commands, skills)
        assert skills[("superpowers:brainstorming", "skill_tool")] == 2

    def test_non_plugin_skill_unaffected(self):
        """Skills without ':' (bundled) are never command_triggered."""
        pending_commands: set[str] = {"superpowers"}
        skills: Counter[tuple] = Counter({("simplify", "skill_tool"): 1})
        _apply_command_triggered(pending_commands, skills)
        assert skills[("simplify", "skill_tool")] == 1

    def test_multiple_skills_first_matches(self):
        """Only same-plugin skills get command_triggered, others stay skill_tool."""
        pending_commands: set[str] = {"superpowers"}
        skills: Counter[tuple] = Counter(
            {
                ("superpowers:brainstorming", "skill_tool"): 1,
                ("oh-my-claudecode:autopilot", "skill_tool"): 1,
            }
        )
        _apply_command_triggered(pending_commands, skills)
        assert skills[("superpowers:brainstorming", "command_triggered")] == 1
        assert skills[("oh-my-claudecode:autopilot", "skill_tool")] == 1


class TestParseCommandFromContent:
    """Tests for parse_command_from_content() XML tag parsing."""

    def test_prefers_command_name_over_message(self):
        """When both tags exist, <command-name> has the clean name."""
        content = (
            '<command-message>The "agent-selection" skill is running</command-message>'
            "<command-name>agent-selection</command-name>"
        )
        name, args = parse_command_from_content(content)
        assert name == "agent-selection"

    def test_command_name_strips_leading_slash(self):
        """<command-name>/foo</command-name> → 'foo' (no leading /)."""
        content = (
            "<command-message>brainstorm</command-message><command-name>/brainstorm</command-name>"
        )
        name, args = parse_command_from_content(content)
        assert name == "brainstorm"

    def test_falls_back_to_command_message(self):
        """When no <command-name>, use <command-message>."""
        content = "<command-message>analyze-ui-project</command-message>"
        name, args = parse_command_from_content(content)
        assert name == "analyze-ui-project"

    def test_no_tags_returns_none(self):
        content = "just some regular text"
        name, args = parse_command_from_content(content)
        assert name is None

    def test_tags_mid_content_rejected(self):
        """Tags appearing mid-content (code snippets) are rejected."""
        content = "Here is some code: <command-message>foo</command-message>"
        name, args = parse_command_from_content(content)
        assert name is None


class TestDetectSlashCommandsValidation:
    """Tests for text detection validation in detect_slash_commands_in_text()."""

    @pytest.fixture(autouse=True)
    def _clear_caches(self):
        _plugin_skill_cache.clear()
        _expand_name_cache.clear()
        _entry_map_cache.clear()
        _entry_type_cache.clear()

    def test_rejects_malformed_plugin_entry(self, tmp_path, monkeypatch):
        """'feature:dev-feature-dev' (colon in wrong place) rejected."""
        # Set up plugin with no matching entry
        plugins_cache = tmp_path / "plugins" / "cache"
        (plugins_cache / "registry" / "feature" / "v1" / "skills").mkdir(parents=True)
        monkeypatch.setattr("config.settings.claude_base", tmp_path)

        result = detect_slash_commands_in_text("try /feature:dev-feature-dev please")
        assert "feature:dev-feature-dev" not in result

    def test_rejects_unknown_plugin_colon_entry(self, tmp_path, monkeypatch):
        """'omc:plan' where 'omc' isn't a real plugin is rejected."""
        plugins_cache = tmp_path / "plugins" / "cache"
        plugins_cache.mkdir(parents=True)
        monkeypatch.setattr("config.settings.claude_base", tmp_path)

        result = detect_slash_commands_in_text("use /omc:plan for this")
        assert "omc:plan" not in result

    def test_accepts_valid_plugin_entry(self, tmp_path, monkeypatch):
        """'superpowers:brainstorming' (real plugin:entry) accepted."""
        plugins_cache = tmp_path / "plugins" / "cache"
        skill_dir = plugins_cache / "reg" / "superpowers" / "v1" / "skills" / "brainstorming"
        skill_dir.mkdir(parents=True)
        (skill_dir / "SKILL.md").touch()
        monkeypatch.setattr("config.settings.claude_base", tmp_path)

        result = detect_slash_commands_in_text("use /superpowers:brainstorming")
        assert "superpowers:brainstorming" in result

    def test_rejects_bare_plugin_name_no_expansion(self, tmp_path, monkeypatch):
        """'oh-my-claudecode' (bare plugin, many entries, can't expand) rejected."""
        plugins_cache = tmp_path / "plugins" / "cache"
        omc_dir = plugins_cache / "reg" / "oh-my-claudecode" / "v1"
        # Create multiple entries so it can't auto-expand
        (omc_dir / "skills" / "cancel").mkdir(parents=True)
        (omc_dir / "skills" / "cancel" / "SKILL.md").touch()
        (omc_dir / "skills" / "plan").mkdir(parents=True)
        (omc_dir / "skills" / "plan" / "SKILL.md").touch()
        monkeypatch.setattr("config.settings.claude_base", tmp_path)

        result = detect_slash_commands_in_text("install /oh-my-claudecode plugin")
        assert "oh-my-claudecode" not in result

    def test_accepts_expandable_bare_name(self, tmp_path, monkeypatch):
        """'brainstorming' (expands to superpowers:brainstorming) accepted."""
        plugins_cache = tmp_path / "plugins" / "cache"
        skill_dir = plugins_cache / "reg" / "superpowers" / "v1" / "skills" / "brainstorming"
        skill_dir.mkdir(parents=True)
        (skill_dir / "SKILL.md").touch()
        monkeypatch.setattr("config.settings.claude_base", tmp_path)

        result = detect_slash_commands_in_text("run /brainstorming on this")
        assert "brainstorming" in result
