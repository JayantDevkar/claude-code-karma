"""
Shared helpers for command/skill classification and parsing.

This package centralizes logic for classifying invocation names into categories,
extracting command metadata from CLI.js, scanning plugin filesystems, and
parsing commands from user prompt content.

Submodules:
    categories — Category types and skill/command bucket helpers
    cli_js     — CLI.js auto-extraction, built-in/bundled sets, prompt resolution
    plugins    — Plugin filesystem scanning, name expansion, classification
    parsing    — Command parsing from XML tags and plain text
"""

# Re-export everything for backward compatibility.
# All existing `from command_helpers import X` imports continue to work.

from .categories import (
    InvocationCategory,
    is_command_category,
    is_skill_category,
)
from .cli_js import (
    BUILTIN_CLI_COMMANDS,
    BUILTIN_COMMAND_DESCRIPTIONS,
    BUNDLED_SKILL_COMMANDS,
    get_bundled_skill_prompt,
    get_cli_commands,
    get_command_description,
)
from .parsing import (
    aggregate_by_name,
    detect_slash_commands_in_text,
    parse_command_from_content,
    strip_command_tags,
)

# Also re-export private symbols used by tests
from .plugins import (
    _build_entry_to_plugin_map,
    _build_entry_type_map,
    _entry_map_cache,
    _entry_type_cache,
    _expand_name_cache,
    _is_plugin_skill,
    _plugin_skill_cache,
    classify_invocation,
    expand_plugin_short_name,
    is_plugin_skill,
)

__all__ = [
    # categories
    "InvocationCategory",
    "is_skill_category",
    "is_command_category",
    # cli_js
    "BUILTIN_CLI_COMMANDS",
    "BUILTIN_COMMAND_DESCRIPTIONS",
    "BUNDLED_SKILL_COMMANDS",
    "get_cli_commands",
    "get_command_description",
    "get_bundled_skill_prompt",
    # plugins
    "classify_invocation",
    "expand_plugin_short_name",
    "is_plugin_skill",
    # parsing
    "parse_command_from_content",
    "detect_slash_commands_in_text",
    "aggregate_by_name",
    "strip_command_tags",
]
