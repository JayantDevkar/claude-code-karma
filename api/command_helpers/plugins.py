"""
Plugin filesystem scanning, classification, and name expansion.

Handles detection of plugin skills/commands via the ~/.claude/plugins/cache/
directory structure and classification of invocation names into categories.
"""

import logging
from pathlib import Path
from typing import Optional

from cachetools import TTLCache

from .categories import InvocationCategory
from .cli_js import (
    _ALL_CLAUDE_CODE_COMMANDS,
    BUILTIN_CLI_COMMANDS,
    BUNDLED_SKILL_COMMANDS,
    get_cli_commands,
)

logger = logging.getLogger(__name__)

_custom_skill_cache: TTLCache[str, bool] = TTLCache(maxsize=128, ttl=60)


def _is_custom_skill(name: str) -> bool:
    """Check if a name corresponds to a custom skill file on disk.

    Custom skills live at:
      ~/.claude/skills/{name}/SKILL.md  (directory-based, uppercase)
      ~/.claude/skills/{name}/skill.md  (directory-based, lowercase)
      ~/.claude/skills/{name}.md        (file-based)
    """
    if name in _custom_skill_cache:
        return _custom_skill_cache[name]

    from config import settings

    skills_dir = settings.skills_dir
    skill_dir = skills_dir / name
    result = (
        (skill_dir / "SKILL.md").is_file()
        or (skill_dir / "skill.md").is_file()
        or (skills_dir / f"{name}.md").is_file()
    )
    _custom_skill_cache[name] = result
    return result


# TTL caches for filesystem-dependent lookups (auto-expire after 60s so
# plugin installs/removals are picked up without restarting the server).
_plugin_skill_cache: TTLCache[str, bool] = TTLCache(maxsize=128, ttl=60)
_expand_name_cache: TTLCache[str, str] = TTLCache(maxsize=128, ttl=60)
_entry_map_cache: TTLCache[str, dict[str, str]] = TTLCache(maxsize=1, ttl=60)
_entry_type_cache: TTLCache[str, dict[str, str]] = TTLCache(maxsize=1, ttl=60)


def _is_plugin_skill(name: str) -> bool:
    """Check if a name matches a plugin directory (short-form skill invocation).

    When users type /frontend-design instead of /frontend-design:frontend-design,
    the name lacks a ':' but still refers to a plugin skill. This checks if a
    plugin with that name exists in ~/.claude/plugins/cache/.
    """
    if name in _plugin_skill_cache:
        return _plugin_skill_cache[name]

    from config import settings

    plugins_cache = settings.claude_base / "plugins" / "cache"
    if not plugins_cache.is_dir():
        _plugin_skill_cache[name] = False
        return False
    # Check all registries (e.g., claude-plugins-official/)
    for registry in plugins_cache.iterdir():
        if registry.is_dir() and (registry / name).is_dir():
            _plugin_skill_cache[name] = True
            return True
    _plugin_skill_cache[name] = False
    return False


def _build_entry_type_map() -> dict[str, str]:
    """Map 'plugin:entry' → 'command'|'skill'|'agent' by checking filesystem.

    Scans all plugins' commands/, skills/, agents/ directories.
    Returns mapping like {'superpowers:brainstorm': 'command', 'superpowers:brainstorming': 'skill'}.
    """
    _sentinel = "__entry_type__"
    if _sentinel in _entry_type_cache:
        return _entry_type_cache[_sentinel]

    from config import settings

    plugins_cache = settings.claude_base / "plugins" / "cache"
    if not plugins_cache.is_dir():
        _entry_type_cache[_sentinel] = {}
        return {}

    result: dict[str, str] = {}
    for registry in plugins_cache.iterdir():
        if not registry.is_dir():
            continue
        for plugin_dir in registry.iterdir():
            if not plugin_dir.is_dir():
                continue
            plugin_name = plugin_dir.name
            versions = sorted(plugin_dir.iterdir(), reverse=True)
            for version_dir in versions:
                entries = _collect_plugin_entries(version_dir)
                for entry_name, kind in entries.items():
                    result[f"{plugin_name}:{entry_name}"] = kind
                break  # Only check latest version

    _entry_type_cache[_sentinel] = result
    return result


def _collect_plugin_entries(version_dir) -> dict[str, str]:
    """Collect all invocable entry names from a plugin version directory.

    Plugins define invocables in three locations:
      - skills/{name}/    (directory-based, e.g. frontend-design)
      - commands/{name}.md (file-based, e.g. feature-dev)
      - agents/{name}.md   (file-based, e.g. code-simplifier)

    Returns:
        Dict mapping entry_name → kind ("skill", "command", or "agent").
    """
    entries: dict[str, str] = {}

    # skills/ — directory-based entries
    skills_dir = version_dir / "skills"
    if skills_dir.is_dir():
        for d in skills_dir.iterdir():
            if d.is_dir():
                entries[d.name] = "skill"

    # commands/ — file-based entries (.md files)
    # Skills take priority when both exist (skills have richer structure)
    commands_dir = version_dir / "commands"
    if commands_dir.is_dir():
        for f in commands_dir.iterdir():
            if f.is_file() and f.suffix == ".md":
                if f.stem not in entries:  # Don't overwrite existing skill
                    entries[f.stem] = "command"

    # agents/ — file-based entries (.md files)
    agents_dir = version_dir / "agents"
    if agents_dir.is_dir():
        for f in agents_dir.iterdir():
            if f.is_file() and f.suffix == ".md" and f.stem != "AGENTS":
                entries[f.stem] = "agent"

    return entries


def _build_entry_to_plugin_map() -> dict[str, str]:
    """Build a reverse lookup: entry_name → 'plugin:entry_name'.

    Handles cases where the Skill tool is called with just the entry name
    (e.g., 'commit') instead of the full form ('commit-commands:commit').
    Only maps unambiguous entries (skip if multiple plugins define the same name).
    """
    _sentinel = "__entry_map__"
    if _sentinel in _entry_map_cache:
        return _entry_map_cache[_sentinel]

    from config import settings

    plugins_cache = settings.claude_base / "plugins" / "cache"
    if not plugins_cache.is_dir():
        _entry_map_cache[_sentinel] = {}
        return {}

    # entry_name → list of plugin names that define it
    candidates: dict[str, list[str]] = {}

    for registry in plugins_cache.iterdir():
        if not registry.is_dir():
            continue
        for plugin_dir in registry.iterdir():
            if not plugin_dir.is_dir():
                continue
            plugin_name = plugin_dir.name
            versions = sorted(plugin_dir.iterdir(), reverse=True)
            for version_dir in versions:
                entries = _collect_plugin_entries(version_dir)
                for entry in entries.keys():
                    candidates.setdefault(entry, []).append(plugin_name)
                break  # Only check latest version

    # Only include unambiguous mappings (one plugin owns the name)
    result: dict[str, str] = {}
    for entry, plugins in candidates.items():
        if len(plugins) == 1:
            plugin = plugins[0]
            # Skip if entry == plugin (handled by expand_plugin_short_name)
            if entry != plugin:
                result[entry] = f"{plugin}:{entry}"

    _entry_map_cache[_sentinel] = result
    return result


def expand_plugin_short_name(name: str) -> str:
    """Expand a short-form plugin skill name to the full plugin:skill form.

    Handles two cases:
    1. Plugin name used as short form: "feature-dev" → "feature-dev:feature-dev"
       (user typed /feature-dev, plugin has an entry matching its own name)
    2. Entry name used without plugin prefix: "commit" → "commit-commands:commit"
       (Skill tool called with just the entry name)

    Returns the name unchanged if expansion is ambiguous or no match found.
    """
    if ":" in name:
        return name  # Already in full form

    if name in _expand_name_cache:
        return _expand_name_cache[name]

    from config import settings

    plugins_cache = settings.claude_base / "plugins" / "cache"
    if not plugins_cache.is_dir():
        _expand_name_cache[name] = name
        return name

    # Case 1: name matches a plugin directory
    for registry in plugins_cache.iterdir():
        if not registry.is_dir():
            continue
        plugin_dir = registry / name
        if not plugin_dir.is_dir():
            continue
        # Find the latest version
        versions = sorted(plugin_dir.iterdir(), reverse=True)
        for version_dir in versions:
            entry_names = _collect_plugin_entries(version_dir)
            if not entry_names:
                continue
            # If plugin has an entry matching its own name, use that
            if name in entry_names:
                result = f"{name}:{name}"
                _expand_name_cache[name] = result
                return result
            # If plugin has exactly one entry, use that
            if len(entry_names) == 1:
                result = f"{name}:{next(iter(entry_names))}"
                _expand_name_cache[name] = result
                return result
            _expand_name_cache[name] = name
            return name

    # Case 2: name is an entry name without plugin prefix (reverse lookup)
    entry_map = _build_entry_to_plugin_map()
    if name in entry_map:
        result = entry_map[name]
        _expand_name_cache[name] = result
        return result

    _expand_name_cache[name] = name
    return name


def is_plugin_skill(name: str) -> bool:
    """Check if a skill name refers to a plugin skill (full or short form).

    Returns True for:
      - Full form: 'oh-my-claudecode:cancel' (contains ':')
      - Short form: 'frontend-design' (matches a plugin directory)
    """
    if ":" in name:
        return True
    return _is_plugin_skill(name)


def classify_invocation(name: str, *, source: str = "") -> str:
    """Classify a command/skill invocation name into one of 6 categories.

    Args:
        name: The invocation name (e.g. "commit", "superpowers:brainstorming").
        source: Where the invocation came from. Use "skill_tool" when the name
            was extracted from a Skill tool call — this lets plugin entries win
            over builtin/bundled names that shadow them (e.g. "commit" is both a
            builtin CLI alias and a plugin skill "commit-commands:commit"; when
            invoked via the Skill tool it's always the plugin skill).

    Returns one of:
        "builtin_command"  — Pure CLI commands (/exit, /model, /clear)
        "bundled_skill"    — Prompt-based skills shipped with Claude Code (/simplify, /batch)
        "plugin_skill"     — Plugin skills (/oh-my-claudecode:autopilot, /frontend-design)
        "custom_skill"     — User SKILL.md files (~/.claude/skills/)
        "user_command"     — User .md command files (~/.claude/commands/)
        "agent"            — Agent entries (skip from skill/command tables)
    """
    # When invoked via the Skill tool, plugin entries take priority over
    # builtin/bundled names that shadow them.  The Skill tool never runs
    # builtin CLI commands — those are handled by Claude Code internally.
    if source == "skill_tool":
        expanded = expand_plugin_short_name(name)
        if expanded != name and ":" in expanded:
            return _classify_colon_name(expanded)
        if ":" in name:
            return _classify_colon_name(name)

    # Check bundled skills first (before builtin, since these are tracked as skills)
    if name in BUNDLED_SKILL_COMMANDS:
        return "bundled_skill"
    # Also check cli.js-extracted bundled skills (may include newly added ones)
    cli = get_cli_commands()
    if name in cli["bundled_skills"]:
        return "bundled_skill"
    if name in BUILTIN_CLI_COMMANDS:
        return "builtin_command"
    if name in cli["builtin_commands"]:
        return "builtin_command"
    if ":" in name:
        return _classify_colon_name(name)
    if _is_custom_skill(name):
        return "custom_skill"
    if _is_plugin_skill(name):
        return "plugin_skill"
    # Last resort: try expanding short-form plugin entry names.
    # e.g. "brainstorming" → "superpowers:brainstorming" (a plugin skill entry)
    expanded = expand_plugin_short_name(name)
    if expanded != name and ":" in expanded:
        return _classify_colon_name(expanded)
    return "user_command"


def _classify_colon_name(name: str) -> str:
    """Classify a fully-qualified 'plugin:entry' name via filesystem lookup."""
    entry_types = _build_entry_type_map()
    entry_type = entry_types.get(name)
    if entry_type == "agent":
        # Agents are tracked in subagent_invocations via the Agent tool.
        # Rare edge case: Claude may invoke an agent via the Skill tool.
        # Return "agent" so callers can skip — these don't belong in
        # session_skills or session_commands.
        return "agent"
    if entry_type == "command":
        return "plugin_command"
    return "plugin_skill"
