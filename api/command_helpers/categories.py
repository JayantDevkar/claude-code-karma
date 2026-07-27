"""
Category types and helpers for command/skill classification.

Classification categories (returned by classify_invocation):
    "builtin_command"  — Pure CLI commands compiled into Claude Code (/clear, /model)
    "bundled_skill"    — Prompt-based skills shipped with Claude Code (/simplify, /batch)
    "plugin_skill"     — Skills from installed plugins (/oh-my-claudecode:autopilot)
    "plugin_command"   — Commands from installed plugins (/superpowers:brainstorm)
    "custom_skill"     — User-authored SKILL.md files (~/.claude/skills/)
    "user_command"     — User-authored .md command files (~/.claude/commands/)
    "agent"            — Agent entries (tracked via Agent tool, not skill/command tables)
"""

from typing import Literal

InvocationCategory = Literal[
    "builtin_command",
    "bundled_skill",
    "plugin_skill",
    "plugin_command",
    "custom_skill",
    "user_command",
    "agent",
]

# Categories that go into session_skills table
_SKILL_CATEGORIES: frozenset[str] = frozenset(
    {"bundled_skill", "plugin_skill", "custom_skill"}
)
# Categories that go into session_commands table
_COMMAND_CATEGORIES: frozenset[str] = frozenset({"builtin_command", "user_command", "plugin_command"})


def is_skill_category(kind: str) -> bool:
    """Return True for any category that belongs in the skills bucket."""
    return kind in _SKILL_CATEGORIES


def is_command_category(kind: str) -> bool:
    """Return True for any category that belongs in the commands bucket."""
    return kind in _COMMAND_CATEGORIES
