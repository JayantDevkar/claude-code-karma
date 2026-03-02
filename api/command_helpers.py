"""
Shared helpers for command/skill classification and parsing.

Centralizes logic that was duplicated across session.py, conversation_endpoints.py,
and sessions.py to prevent drift.
"""

import re
from typing import Optional

from cachetools import TTLCache

# Built-in Claude Code CLI commands that should NOT be tracked as user-authored commands.
# These are internal to the CLI and have no corresponding user .md files.
# Keep in sync with Claude Code CLI releases.
BUILTIN_CLI_COMMANDS = frozenset(
    {
        # Core session
        "exit",
        "clear",
        "compact",
        "resume",
        # Configuration
        "model",
        "config",
        "memory",
        "fast",
        "vim",
        "permissions",
        "allowed-tools",
        # Authentication
        "login",
        "logout",
        # Context
        "context",
        "add-dir",
        # Integration
        "plugin",
        "mcp",
        "terminal",
        "ide",
        # Information
        "help",
        "cost",
        "status",
        "doctor",
        "bug",
        # Task management
        "tasks",
        # Other
        "init",
    }
)

# Regex for detecting real command prompts (starts with command tag)
_COMMAND_START_RE = re.compile(r"\s*<command-(?:name|message)>")
_COMMAND_MESSAGE_RE = re.compile(r"<command-message>(.*?)</command-message>")
_COMMAND_NAME_RE = re.compile(r"<command-name>/?(.*?)</command-name>")
_COMMAND_ARGS_RE = re.compile(r"<command-args>(.*?)</command-args>", re.DOTALL)

# Strips command/local-command XML tags from content for display
_COMMAND_TAG_RE = re.compile(
    r"<(?:command|local-command)-(?:message|name|args|caveat)>.*?</(?:command|local-command)-(?:message|name|args|caveat)>\s*",
    re.DOTALL,
)


def _is_custom_skill(name: str) -> bool:
    """Check if a name corresponds to a custom skill file on disk.

    Custom skills live at:
      ~/.claude/skills/{name}/SKILL.md  (directory-based, uppercase)
      ~/.claude/skills/{name}/skill.md  (directory-based, lowercase)
      ~/.claude/skills/{name}.md        (file-based)
    """
    from config import settings

    skills_dir = settings.skills_dir
    skill_dir = skills_dir / name
    return (
        (skill_dir / "SKILL.md").is_file()
        or (skill_dir / "skill.md").is_file()
        or (skills_dir / f"{name}.md").is_file()
    )


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
    commands_dir = version_dir / "commands"
    if commands_dir.is_dir():
        for f in commands_dir.iterdir():
            if f.is_file() and f.suffix == ".md":
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


def classify_invocation(name: str) -> str:
    """Classify a command/skill invocation name.

    Returns:
        "builtin" for built-in CLI commands (/exit, /model, etc.)
        "skill" for plugin skills (contains ':'), custom skills (SKILL.md exists),
                or plugin short names (matching a plugin directory)
        "command" for user-authored commands
    """
    if name in BUILTIN_CLI_COMMANDS:
        return "builtin"
    if ":" in name:
        entry_types = _build_entry_type_map()
        entry_type = entry_types.get(name)
        if entry_type == "command":
            return "command"
        if entry_type == "agent":
            # Agents are tracked in subagent_invocations via the Agent tool.
            # Rare edge case: Claude may invoke an agent via the Skill tool.
            # Return "agent" so callers can skip — these don't belong in
            # session_skills or session_commands.
            return "agent"
        return "skill"
    if _is_custom_skill(name):
        return "skill"
    if _is_plugin_skill(name):
        return "skill"
    return "command"


def parse_command_from_content(content: str) -> tuple[Optional[str], Optional[str]]:
    """Parse command name and args from user prompt content with <command-message> tags.

    Real command prompts from Claude Code start with either:
      <command-name>/foo</command-name><command-message>foo</command-message>...
    or:
      <command-message>foo</command-message><command-name>/foo</command-name>...

    Returns:
        (command_name, args) or (None, None) if not a command prompt.
    """
    if "<command-message>" not in content:
        return None, None

    # Real commands start with <command-name> or <command-message> tag;
    # code snippets have these tags mid-content
    if not _COMMAND_START_RE.match(content):
        return None, None

    # Prefer <command-name> (clean name like "brainstorm") over
    # <command-message> (may contain descriptive text like "The skill is running").
    name_match = _COMMAND_NAME_RE.search(content)
    if name_match:
        cmd_name = name_match.group(1)
    else:
        cmd_match = _COMMAND_MESSAGE_RE.search(content)
        if not cmd_match:
            return None, None
        cmd_name = cmd_match.group(1)

    args_match = _COMMAND_ARGS_RE.search(content)
    args = args_match.group(1).strip() if args_match and args_match.group(1).strip() else None

    return cmd_name, args


# Regex for detecting /command or /plugin:command patterns in plain text.
# Uses negative lookahead (?!/) to reject file paths like /Users/foo, /private/tmp.
# Also rejects matches preceded by common path/URL characters.
_SLASH_COMMAND_RE = re.compile(r"(?:^|(?<=\s))/([a-zA-Z][\w:.-]*)(?!/)")

# Common false-positive roots from file paths, URLs, and system dirs
_PATH_ROOTS = frozenset(
    {
        "bin",
        "dev",
        "etc",
        "home",
        "lib",
        "nix",
        "opt",
        "private",
        "proc",
        "root",
        "run",
        "sbin",
        "snap",
        "srv",
        "sys",
        "tmp",
        "usr",
        "var",
        "Applications",
        "Library",
        "System",
        "Users",
        "Volumes",
    }
)


def detect_slash_commands_in_text(content: str) -> list[str]:
    """Detect /command patterns in plain-text user prompts (no XML tags).

    This catches skills invoked via hooks (magic keywords) where Claude Code
    does not wrap the command in <command-message> tags because the slash
    command was not the primary content of the message.

    Only scans the user's actual text — strips system-injected content
    (``<system-reminder>`` blocks, ``<local-command-*>`` tags, tool output)
    to avoid false positives from code diffs and file contents.

    Returns a list of command/skill names found (without leading /).
    """
    # Strip system-injected content that may contain code/diffs/paths.
    # User text is always BEFORE the first injection marker.
    # Markers: XML tags from Claude Code, and ⏺ from compaction summaries.
    for marker in (
        "<system-reminder>",
        "<local-command-",
        "<command-name>",
        "<command-message>",
        "\u23fa",
    ):
        idx = content.find(marker)
        if idx != -1:
            content = content[:idx]

    candidates = _SLASH_COMMAND_RE.findall(content)
    results: list[str] = []
    entry_types = _build_entry_type_map()
    for c in candidates:
        if c in _PATH_ROOTS:
            continue
        if ":" in c:
            # Validate plugin:entry names exist in filesystem.
            # Rejects "feature:dev-feature-dev" (malformed), "omc:plan" (not real).
            if c not in entry_types:
                continue
        else:
            # Bare names (no ':') must resolve to something concrete.
            # Reject bare plugin names that don't expand to a specific entry
            # (e.g., "oh-my-claudecode" has 71 entries, can't pick one).
            expanded = expand_plugin_short_name(c)
            if expanded == c and c not in BUILTIN_CLI_COMMANDS and not _is_custom_skill(c):
                continue
        results.append(c)
    return results


def aggregate_by_name(items: dict) -> dict[str, int]:
    """Aggregate (name, source) keyed counts to name-only counts.

    Converts the tuple-keyed dicts from get_skills_used()/get_commands_used()
    back to simple {name: total_count} format for backward compatibility.
    """
    result: dict[str, int] = {}
    for key, count in items.items():
        name = key[0] if isinstance(key, tuple) else key
        result[name] = result.get(name, 0) + count
    return result


def strip_command_tags(content: str) -> str:
    """Remove command and local-command XML tags from content for display.

    Handles both <command-*> and <local-command-*> tags (e.g., <local-command-caveat>).
    """
    if "<command-" not in content and "<local-command-" not in content:
        return content
    return _COMMAND_TAG_RE.sub("", content).strip()
