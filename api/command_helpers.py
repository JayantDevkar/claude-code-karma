"""
Shared helpers for command/skill classification and parsing.

Centralizes logic that was duplicated across session.py, conversation_endpoints.py,
and sessions.py to prevent drift.
"""

import re
from functools import lru_cache
from typing import Optional

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


@lru_cache(maxsize=128)
def _is_plugin_skill(name: str) -> bool:
    """Check if a name matches a plugin directory (short-form skill invocation).

    When users type /frontend-design instead of /frontend-design:frontend-design,
    the name lacks a ':' but still refers to a plugin skill. This checks if a
    plugin with that name exists in ~/.claude/plugins/cache/.
    """
    from config import settings

    plugins_cache = settings.claude_base / "plugins" / "cache"
    if not plugins_cache.is_dir():
        return False
    # Check all registries (e.g., claude-plugins-official/)
    for registry in plugins_cache.iterdir():
        if registry.is_dir() and (registry / name).is_dir():
            return True
    return False


@lru_cache(maxsize=128)
def expand_plugin_short_name(name: str) -> str:
    """Expand a short-form plugin skill name to the full plugin:skill form.

    When users type /frontend-design, Claude Code resolves it to
    frontend-design:frontend-design (plugin:skill). This function replicates
    that expansion by checking the plugin's skills directory.

    If the plugin has a single skill with the same name, returns "name:name".
    If it has exactly one skill, returns "name:that_skill".
    Otherwise returns the name unchanged.
    """
    if ":" in name:
        return name  # Already in full form

    from config import settings

    plugins_cache = settings.claude_base / "plugins" / "cache"
    if not plugins_cache.is_dir():
        return name

    for registry in plugins_cache.iterdir():
        if not registry.is_dir():
            continue
        plugin_dir = registry / name
        if not plugin_dir.is_dir():
            continue
        # Find the latest version's skills directory
        versions = sorted(plugin_dir.iterdir(), reverse=True)
        for version_dir in versions:
            skills_dir = version_dir / "skills"
            if not skills_dir.is_dir():
                continue
            skill_names = [d.name for d in skills_dir.iterdir() if d.is_dir()]
            if not skill_names:
                continue
            # If plugin has a skill matching its own name, use that
            if name in skill_names:
                return f"{name}:{name}"
            # If plugin has exactly one skill, use that
            if len(skill_names) == 1:
                return f"{name}:{skill_names[0]}"
            return name
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
    return [c for c in candidates if c not in _PATH_ROOTS]


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
