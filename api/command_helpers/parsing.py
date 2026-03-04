"""
Command parsing from user prompt content.

Handles detection and extraction of /command patterns from both
XML-tagged content (<command-message>) and plain text user prompts.
"""

import re
from typing import Optional

from .cli_js import _ALL_CLAUDE_CODE_COMMANDS
from .plugins import (
    _build_entry_type_map,
    _is_custom_skill,
    expand_plugin_short_name,
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
            if expanded == c and c not in _ALL_CLAUDE_CODE_COMMANDS and not _is_custom_skill(c):
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
