"""
CLI.js auto-extraction and bundled skill prompt resolution.

Locates Claude Code's cli.js binary, extracts command names/descriptions,
and resolves full prompt templates for bundled skills.
"""

import logging
import re
import shutil
from pathlib import Path

from cachetools import TTLCache

logger = logging.getLogger(__name__)

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

# Human-readable descriptions for built-in CLI commands (no prompt content)
BUILTIN_COMMAND_DESCRIPTIONS: dict[str, str] = {
    "exit": "End the current session",
    "clear": "Clear the conversation display",
    "compact": "Compact conversation context to reduce token usage",
    "resume": "Resume a previous session",
    "fork": "Fork the current session into a new conversation",
    "rename": "Rename the current session",
    "export": "Export the session to a file",
    "model": "Switch the AI model",
    "config": "View or edit configuration settings",
    "memory": "Manage persistent memory across sessions",
    "fast": "Toggle fast mode (faster output, same model)",
    "vim": "Toggle vim keybindings",
    "permissions": "Manage tool permissions",
    "allowed-tools": "View or modify allowed tools list",
    "theme": "Switch between light and dark themes",
    "keybindings": "Customize keyboard shortcuts",
    "login": "Authenticate with Anthropic",
    "logout": "Sign out of your account",
    "context": "View current context window usage",
    "add-dir": "Add a directory to the conversation context",
    "files": "List files in context",
    "plugin": "Manage Claude Code plugins",
    "mcp": "Manage MCP (Model Context Protocol) servers",
    "terminal": "Configure terminal integration",
    "ide": "Configure IDE integration",
    "hooks": "Manage event hooks",
    "agents": "List available agents",
    "help": "Show help information",
    "cost": "View token usage and cost for this session",
    "status": "Show session status",
    "doctor": "Diagnose configuration issues",
    "bug": "Report a bug",
    "usage": "View usage statistics",
    "diff": "Show uncommitted code changes",
    "copy": "Copy last response to clipboard",
    "skills": "List available skills",
    "plan": "Enter plan mode for structured task planning",
    "tasks": "View and manage the task list",
    "init": "Initialize Claude Code in a project",
    "upgrade": "Upgrade Claude Code to the latest version",
    "pr-comments": "View pull request comments",
    "stats": "Show session statistics",
    "insights": "View usage insights and patterns",
    "voice": "Toggle voice mode",
}


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
