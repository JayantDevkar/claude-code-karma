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
    "inherited_skill",
    "user_command",
    "agent",
]

# Categories that go into session_skills table
_SKILL_CATEGORIES: frozenset[str] = frozenset(
    {"bundled_skill", "plugin_skill", "custom_skill", "inherited_skill"}
)
# Categories that go into session_commands table
_COMMAND_CATEGORIES: frozenset[str] = frozenset({"builtin_command", "user_command", "plugin_command"})


def is_skill_category(kind: str) -> bool:
    """Return True for any category that belongs in the skills bucket."""
    return kind in _SKILL_CATEGORIES


def is_command_category(kind: str) -> bool:
    """Return True for any category that belongs in the commands bucket."""
    return kind in _COMMAND_CATEGORIES


def category_from_base_directory(base_dir: str) -> str | None:
    """Infer skill category from a 'Base directory for this skill:' path.

    Claude Code injects this line into the UserMessage that follows a Skill
    tool invocation.  The path segment reliably identifies the category:
      ~/.claude/plugins/cache/.../commands/ → plugin_command
      ~/.claude/plugins/cache/...          → plugin_skill
      ~/.claude/skills/...                 → custom_skill
      ~/.claude/commands/...               → user_command
    """
    # Check plugin paths first — they also contain /skills/ or /commands/
    if "/plugins/cache/" in base_dir:
        if "/commands/" in base_dir:
            return "plugin_command"
        return "plugin_skill"
    if "/skills/" in base_dir:
        return "custom_skill"
    if "/commands/" in base_dir:
        return "user_command"
    return None
