"""
Shared helpers for command/skill classification and parsing.

Centralizes logic that was duplicated across session.py, conversation_endpoints.py,
and sessions.py to prevent drift.

Classification categories (returned by classify_invocation):
    "builtin_command"  — Pure CLI commands compiled into Claude Code (/clear, /model)
    "bundled_skill"    — Prompt-based skills shipped with Claude Code (/simplify, /batch)
    "plugin_skill"     — Skills from installed plugins (/oh-my-claudecode:autopilot)
    "plugin_command"   — Commands from installed plugins (/superpowers:brainstorm)
    "custom_skill"     — User-authored SKILL.md files (~/.claude/skills/)
    "user_command"     — User-authored .md command files (~/.claude/commands/)
    "agent"            — Agent entries (tracked via Agent tool, not skill/command tables)
"""

import logging
import re
import shutil
import subprocess
from pathlib import Path
from typing import Literal, Optional

from cachetools import TTLCache

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Category types and helpers
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Built-in and bundled command sets
# ---------------------------------------------------------------------------

# Built-in Claude Code CLI commands — pure CLI commands with no prompt-based execution.
# Keep in sync with Claude Code CLI releases.
# Auto-extraction from cli.js supplements this list at runtime.
BUILTIN_CLI_COMMANDS = frozenset(
    {
        # Core session
        "exit",
        "clear",
        "compact",
        "resume",
        "fork",
        "rename",
        "export",
        # Configuration
        "model",
        "config",
        "memory",
        "fast",
        "vim",
        "permissions",
        "allowed-tools",
        "color",
        "theme",
        "keybindings",
        "privacy-settings",
        # Authentication
        "login",
        "logout",
        # Context
        "context",
        "add-dir",
        "files",
        # Integration
        "plugin",
        "mcp",
        "terminal",
        "ide",
        "hooks",
        "agents",
        "chrome",
        "claude-in-chrome",
        # Information
        "help",
        "cost",
        "status",
        "doctor",
        "bug",
        "usage",
        "diff",
        "copy",
        "skills",
        "plan",
        # Task management
        "tasks",
        # Other
        "init",
        "init-verifiers",
        "upgrade",
        "extra-usage",
        "btw",
        "feedback",
        "stickers",
        "stats",
        "insights",
        "voice",
        "think-back",
        "thinkback-play",
        "pr-comments",
        "install-github-app",
        "install-slack-app",
        # Legacy / aliases (not in cli.js but seen in older sessions)
        "commit",
        "commit-push-pr",
    }
)

# Prompt-based skills bundled with Claude Code itself (not user plugins).
# These have rich multi-sentence descriptions in cli.js and execute via prompts.
BUNDLED_SKILL_COMMANDS = frozenset(
    {
        "simplify",
        "batch",
        "claude-developer-platform",
        "explain_command",
        "review",
        "security-review",
        "debug",
    }
)

# Combined set for quick membership checks (is this name from Claude Code itself?)
_ALL_CLAUDE_CODE_COMMANDS: frozenset[str] = BUILTIN_CLI_COMMANDS | BUNDLED_SKILL_COMMANDS


# ---------------------------------------------------------------------------
# CLI.js auto-extraction (supplements hardcoded sets at runtime)
# ---------------------------------------------------------------------------

_cli_commands_cache: TTLCache[str, dict] = TTLCache(maxsize=1, ttl=3600)


def _find_cli_js_path() -> Path | None:
    """Locate Claude Code's cli.js via the `claude` binary.

    Resolution: which claude → resolve symlink → ../lib/node_modules/@anthropic-ai/claude-code/cli.js
    Falls back to common install paths on macOS/Linux.
    """
    # Try via `which claude`
    claude_bin = shutil.which("claude")
    if claude_bin:
        try:
            resolved = Path(claude_bin).resolve()
            # npm global: .../bin/claude → .../lib/node_modules/@anthropic-ai/claude-code/cli.js
            cli_js = resolved.parent.parent / "lib" / "node_modules" / "@anthropic-ai" / "claude-code" / "cli.js"
            if cli_js.is_file():
                return cli_js
            # Direct symlink to cli.js (e.g., Homebrew)
            if resolved.name == "cli.js" and resolved.is_file():
                return resolved
        except (OSError, ValueError):
            pass

    # Fallback paths
    for base in (
        Path("/opt/homebrew/lib/node_modules/@anthropic-ai/claude-code"),
        Path("/usr/local/lib/node_modules/@anthropic-ai/claude-code"),
        Path.home() / ".npm-global" / "lib" / "node_modules" / "@anthropic-ai" / "claude-code",
    ):
        cli_js = base / "cli.js"
        if cli_js.is_file():
            return cli_js

    return None


# Regex to extract name:"...",description:"..." pairs from minified cli.js.
# Matches the command registration pattern in the bundled JavaScript.
_CLI_JS_COMMAND_RE = re.compile(r'name:"([a-zA-Z][a-zA-Z0-9_-]*)",description:"([^"]*)"')

# Names to skip — these are tool definitions, pyright flags, or non-command entries
_CLI_JS_SKIP_NAMES: frozenset[str] = frozenset(
    {
        "javascript_tool", "read_page", "form_input", "navigate", "resize_window",
        "gif_creator", "upload_image", "get_page_text", "update_plan",
        "read_console_messages", "read_network_requests", "shortcuts_list",
        "shortcuts_execute", "switch_browser", "sharp", "pyright",
    }
)


def _extract_from_cli_js(cli_js_path: Path) -> dict:
    """Parse cli.js to extract command names and descriptions.

    Returns:
        {"builtin_commands": {name: description}, "bundled_skills": {name: description}}
    """
    try:
        # Read a limited portion — commands are typically in the first ~2MB
        with open(cli_js_path, "r", encoding="utf-8", errors="ignore") as f:
            content = f.read(5_000_000)
    except OSError as e:
        logger.debug("Failed to read cli.js: %s", e)
        return {"builtin_commands": {}, "bundled_skills": {}}

    # Find the command block — starts around name:"add-dir"
    start_idx = content.find('name:"add-dir"')
    if start_idx == -1:
        logger.debug("Could not find command block in cli.js")
        return {"builtin_commands": {}, "bundled_skills": {}}

    # Scan from a bit before the start to catch all commands
    search_start = max(0, start_idx - 5000)
    matches = _CLI_JS_COMMAND_RE.findall(content[search_start:])

    builtin_commands: dict[str, str] = {}
    bundled_skills: dict[str, str] = {}

    for name, description in matches:
        if name in _CLI_JS_SKIP_NAMES:
            continue
        if name.startswith("--") or name == "-":
            continue  # pyright flags

        # Bundled skills have rich multi-sentence descriptions
        if name in BUNDLED_SKILL_COMMANDS:
            bundled_skills[name] = description
        else:
            builtin_commands[name] = description

    return {"builtin_commands": builtin_commands, "bundled_skills": bundled_skills}


def get_cli_commands() -> dict:
    """Get all Claude Code commands, auto-extracted from cli.js with hardcoded fallback.

    Returns:
        {"builtin_commands": {name: description}, "bundled_skills": {name: description}}
    Cached for 1 hour.
    """
    _sentinel = "__cli_commands__"
    if _sentinel in _cli_commands_cache:
        return _cli_commands_cache[_sentinel]

    cli_js = _find_cli_js_path()
    if cli_js:
        result = _extract_from_cli_js(cli_js)
        if result["builtin_commands"] or result["bundled_skills"]:
            _cli_commands_cache[_sentinel] = result
            logger.debug(
                "Extracted %d builtin + %d bundled from cli.js",
                len(result["builtin_commands"]),
                len(result["bundled_skills"]),
            )
            return result

    # Fallback to hardcoded sets (no descriptions available)
    result = {
        "builtin_commands": {name: "" for name in BUILTIN_CLI_COMMANDS},
        "bundled_skills": {name: "" for name in BUNDLED_SKILL_COMMANDS},
    }
    _cli_commands_cache[_sentinel] = result
    return result


def get_command_description(name: str) -> str | None:
    """Get the cli.js-extracted description for a command/skill, or None."""
    cli = get_cli_commands()
    desc = cli["builtin_commands"].get(name) or cli["bundled_skills"].get(name)
    return desc if desc else None


# ---------------------------------------------------------------------------
# Bundled skill full prompt extraction
# ---------------------------------------------------------------------------

# Unique content markers to locate each bundled skill's prompt template literal
# in cli.js.  We search for these strings, scan backwards to find the opening
# backtick, then extract the full template literal.
_PROMPT_MARKERS: dict[str, str] = {
    "simplify": "# Simplify: Code Review and Cleanup",
    "batch": "# Batch: Parallel Work Orchestration",
    "review": "You are an expert code reviewer",
    "security-review": "You are a senior security engineer",
    "debug": "# Debug Skill",
    "claude-developer-platform": "# Building LLM-Powered Applications",
}

# Secondary markers for template-literal variables referenced inside prompts.
# These are extracted separately and spliced in during resolution.
_TEMPLATE_LITERAL_VAR_MARKERS: dict[str, str] = {
    "uGz": "After you finish implementing the change:",  # batch worker instructions
}

# Cache: {cli_js_path: {"mtime": float, "size": int, "prompts": {name: text}}}
_prompt_cache: dict[str, dict] = {}


def _extract_template_literal(content: str, backtick_pos: int) -> str | None:
    """Extract a JS template literal starting at *backtick_pos*.

    Handles escaped characters (``\\```, ``\\n``), ``${...}`` expressions
    (preserved verbatim for later resolution), and nested braces.
    Returns the decoded string content, or ``None`` on failure.
    """
    if backtick_pos >= len(content) or content[backtick_pos] != "`":
        return None

    pos = backtick_pos + 1
    chars: list[str] = []

    while pos < len(content):
        ch = content[pos]

        if ch == "\\":
            # Escaped character
            pos += 1
            if pos >= len(content):
                break
            nch = content[pos]
            if nch == "`":
                chars.append("`")
            elif nch == "n":
                chars.append("\n")
            elif nch == "t":
                chars.append("\t")
            elif nch == "\\":
                chars.append("\\")
            elif nch == "$":
                chars.append("$")
            else:
                chars.append(nch)
            pos += 1

        elif ch == "`":
            # End of template literal
            return "".join(chars)

        elif ch == "$" and pos + 1 < len(content) and content[pos + 1] == "{":
            # Template expression ${...} — preserve for later resolution
            depth = 1
            expr_start = pos + 2
            pos = expr_start
            while pos < len(content) and depth > 0:
                if content[pos] == "{":
                    depth += 1
                elif content[pos] == "}":
                    depth -= 1
                elif content[pos] == "`":
                    # Skip nested template literal inside expression
                    pos += 1
                    while pos < len(content):
                        if content[pos] == "\\":
                            pos += 1
                        elif content[pos] == "`":
                            break
                        pos += 1
                elif content[pos] == "\\":
                    pos += 1  # skip escaped char in expression
                pos += 1
            expr = content[expr_start : pos - 1]
            chars.append(f"${{{expr}}}")

        else:
            chars.append(ch)
            pos += 1

    return None  # Unclosed template literal


# Regex for simple var assignments:  var X="VALUE"  or  X="VALUE"
_VAR_ASSIGN_STR_RE = re.compile(
    r"(?:var\s+)?([a-zA-Z_$][a-zA-Z0-9_$]*)=\"([^\"]*)\""
)
# Regex for numeric var assignments:  var X=NUMBER
_VAR_ASSIGN_NUM_RE = re.compile(
    r"(?:var\s+)?([a-zA-Z_$][a-zA-Z0-9_$]*)=(\d+)(?=[,;\s})])"
)
# Regex for ${VARNAME} references (simple identifiers only, not function calls)
_TEMPLATE_VAR_RE = re.compile(r"\$\{([a-zA-Z_$][a-zA-Z0-9_$]*)\}")
# Regex for ${func(...)} patterns (function calls in template expressions)
_FUNC_CALL_IN_TEMPLATE_RE = re.compile(r"\$\{[^}]*\([^)]*\)[^}]*\}")


def _build_var_map(content: str) -> dict[str, str]:
    """Build a combined map of variable name → resolved value from cli.js.

    Captures:
    - Simple string assignments: ``var X="Agent"``
    - Numeric assignments: ``var X=30``
    - Known template-literal variables (via ``_TEMPLATE_LITERAL_VAR_MARKERS``)
    """
    var_map: dict[str, str] = {}

    # String vars (tool names, etc.)
    for m in _VAR_ASSIGN_STR_RE.finditer(content):
        name, value = m.group(1), m.group(2)
        if len(value) <= 60 and not name.isdigit():
            var_map[name] = value

    # Numeric vars (counts like gVq=5, FVq=30)
    for m in _VAR_ASSIGN_NUM_RE.finditer(content):
        name, value = m.group(1), m.group(2)
        if not name.isdigit():
            var_map[name] = value

    # Template-literal vars (e.g., uGz for batch worker instructions)
    for var_name, marker in _TEMPLATE_LITERAL_VAR_MARKERS.items():
        idx = content.find(marker)
        if idx == -1:
            continue
        bt = content.rfind("`", max(0, idx - 200), idx)
        if bt == -1:
            continue
        extracted = _extract_template_literal(content, bt)
        if extracted:
            var_map[var_name] = extracted

    return var_map


def _resolve_template_variables(prompt: str, var_map: dict[str, str]) -> str:
    """Replace ``${VARNAME}`` references with resolved values.

    - Known function arguments (``A``, ``q``, ``K``) → descriptive placeholders
    - Resolved variables → their value
    - ``${func(...)}`` calls → ``[dynamic]``
    - Remaining unresolved → ``[VARNAME]``
    """
    # Replace function-call expressions first (before simple var resolution)
    prompt = _FUNC_CALL_IN_TEMPLATE_RE.sub("[dynamic]", prompt)

    # Single-letter vars that are function arguments, not global constants
    _arg_names = frozenset("AqKYzw_$")

    def _replace(m: re.Match) -> str:
        name = m.group(1)
        if name in _arg_names:
            return "[argument]"
        if name in var_map:
            return var_map[name]
        return f"[{name}]"

    return _TEMPLATE_VAR_RE.sub(_replace, prompt)


def _extract_bundled_skill_prompts(cli_js_path: Path) -> dict[str, str]:
    """Extract full prompt templates for all bundled skills from cli.js.

    Returns ``{skill_name: resolved_prompt_markdown}``.
    """
    try:
        with open(cli_js_path, "r", encoding="utf-8", errors="ignore") as f:
            content = f.read()
    except OSError as e:
        logger.debug("Failed to read cli.js for prompt extraction: %s", e)
        return {}

    var_map = _build_var_map(content)
    prompts: dict[str, str] = {}

    for skill_name, marker in _PROMPT_MARKERS.items():
        marker_idx = content.find(marker)
        if marker_idx == -1:
            logger.debug("Could not find prompt marker for %s", skill_name)
            continue

        # Scan backwards from marker to find the opening backtick
        search_start = max(0, marker_idx - 500)
        bt = content.rfind("`", search_start, marker_idx)
        if bt == -1:
            logger.debug("Could not find opening backtick for %s", skill_name)
            continue

        raw = _extract_template_literal(content, bt)
        if not raw:
            logger.debug("Failed to extract template literal for %s", skill_name)
            continue

        resolved = _resolve_template_variables(raw, var_map)

        # Post-processing: strip YAML frontmatter for security-review
        if skill_name == "security-review" and resolved.lstrip().startswith("---"):
            text = resolved.lstrip()
            end = text.find("---", 3)
            if end != -1:
                resolved = text[end + 3:].lstrip("\n")

        prompts[skill_name] = resolved.strip()

    return prompts


def get_bundled_skill_prompt(name: str) -> str | None:
    """Get the full prompt markdown for a bundled skill, or ``None``.

    Extracts from cli.js with mtime+size caching — only re-parses when the
    file changes on disk.
    """
    cli_js = _find_cli_js_path()
    if not cli_js:
        return None

    try:
        stat = cli_js.stat()
        mtime = stat.st_mtime
        size = stat.st_size
    except OSError:
        return None

    cache_key = str(cli_js)
    cached = _prompt_cache.get(cache_key)
    if cached and cached["mtime"] == mtime and cached["size"] == size:
        return cached["prompts"].get(name)

    # Re-extract
    prompts = _extract_bundled_skill_prompts(cli_js)
    _prompt_cache[cache_key] = {"mtime": mtime, "size": size, "prompts": prompts}
    logger.debug("Extracted %d bundled skill prompts from cli.js", len(prompts))

    return prompts.get(name)


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
