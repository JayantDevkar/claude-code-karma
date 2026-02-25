"""
Hook discovery model for Claude Code hook registrations.

Discovers hooks from three sources:
1. Global settings: ~/.claude/settings.json and settings.local.json
2. Project settings: {project}/.claude/settings.json and settings.local.json
3. Plugin hooks: {plugin_install_path}/hooks/hooks.json for each enabled plugin

Hook settings.json structure:
    {
      "hooks": {
        "PreToolUse": [
          {
            "matcher": "*",
            "hooks": [
              {"type": "command", "command": "python3 script.py", "timeout": 5000}
            ]
          }
        ]
      }
    }
"""

from __future__ import annotations

import json
import logging
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock
from typing import Any, Dict, List, Optional, Tuple

from pydantic import BaseModel, ConfigDict

from config import settings

logger = logging.getLogger(__name__)

# Add captain-hook src to path for schema introspection (done at module level
# to avoid thread-safety issues with sys.path manipulation inside functions).
_captain_hook_src = str(Path(__file__).parent.parent.parent / "captain-hook" / "src")
if _captain_hook_src not in sys.path:
    sys.path.insert(0, _captain_hook_src)

# =============================================================================
# Constants
# =============================================================================

# Event metadata: (phase, can_block, description)
HOOK_EVENT_METADATA: Dict[str, Tuple[str, bool, str]] = {
    "SessionStart": ("Session Lifecycle", False, "Fires when a session begins"),
    "SessionEnd": ("Session Lifecycle", False, "Fires when session ends"),
    "UserPromptSubmit": ("User Input", True, "Fires when user submits a message"),
    "PreToolUse": ("Tool Lifecycle", True, "Fires before tool execution"),
    "PostToolUse": ("Tool Lifecycle", False, "Fires after successful tool execution"),
    "PostToolUseFailure": ("Tool Lifecycle", False, "Fires after failed tool execution"),
    "SubagentStart": ("Agent Lifecycle", False, "Fires when a subagent is spawned"),
    "SubagentStop": ("Agent Lifecycle", False, "Fires when a subagent completes"),
    "Stop": ("Agent Lifecycle", True, "Fires when Claude finishes a response"),
    "PreCompact": ("Context & Permissions", False, "Fires before context compaction"),
    "PermissionRequest": ("Context & Permissions", True, "Fires on permission dialog"),
    "Notification": ("System", False, "Fires on system notification"),
    "Setup": ("Setup", False, "Fires on --init or --maintenance"),
}

# Lifecycle ordering for related events
LIFECYCLE_ORDER = [
    "SessionStart",
    "UserPromptSubmit",
    "PreToolUse",
    "PostToolUse",
    "PostToolUseFailure",
    "SubagentStart",
    "SubagentStop",
    "Stop",
    "PreCompact",
    "PermissionRequest",
    "Notification",
    "SessionEnd",
    "Setup",
]

# Module-level cache
_hooks_cache: Optional[List["HookRegistration"]] = None
_hooks_cache_time: Optional[datetime] = None
_hooks_cache_lock = Lock()
_HOOKS_CACHE_TTL_SECONDS = 60


# =============================================================================
# Response Models
# =============================================================================


class HookRegistration(BaseModel):
    """Single hook-to-event binding."""

    model_config = ConfigDict(frozen=True)

    event_type: str
    source_type: str  # "global" | "project" | "plugin"
    source_name: str  # "Your Hooks" | project name | plugin short name
    source_id: str  # URL-safe identifier
    plugin_id: Optional[str] = None
    description: Optional[str] = None
    matcher: str = "*"
    command: str
    script_filename: Optional[str] = None
    script_language: str = "unknown"
    timeout_ms: Optional[int] = None
    can_block: bool = False


class HookScript(BaseModel):
    """Unique script file with its registrations."""

    model_config = ConfigDict(frozen=True)

    filename: str
    full_path: Optional[str] = None
    language: str
    source_name: str
    event_types: List[str]
    registrations: int
    is_symlink: bool = False
    symlink_target: Optional[str] = None


class HookSource(BaseModel):
    """All hooks from one source."""

    model_config = ConfigDict(frozen=True)

    source_type: str
    source_name: str
    source_id: str
    plugin_id: Optional[str] = None
    scripts: List[HookScript]
    total_registrations: int
    event_types_covered: List[str]
    blocking_hooks_count: int


class HookEventSummary(BaseModel):
    """Per-event-type aggregation."""

    model_config = ConfigDict(frozen=True)

    event_type: str
    phase: str
    can_block: bool
    description: str
    total_registrations: int
    sources: List[str]
    registrations: List[HookRegistration]


class HookFieldInfo(BaseModel):
    """Schema field info derived from captain-hook models."""

    model_config = ConfigDict(frozen=True)

    name: str
    type: str
    required: bool
    description: Optional[str] = None


class HookEventSchema(BaseModel):
    """Input/output schema for an event type."""

    model_config = ConfigDict(frozen=True)

    input_fields: List[HookFieldInfo]
    output_fields: List[HookFieldInfo]
    base_fields: List[HookFieldInfo]


class HookStats(BaseModel):
    """Aggregated stats for hooks overview."""

    model_config = ConfigDict(frozen=True)

    total_sources: int
    total_registrations: int
    total_scripts: int
    blocking_hooks: int
    event_types_with_hooks: int
    event_types_total: int


class HooksOverview(BaseModel):
    """Response for GET /hooks."""

    model_config = ConfigDict(frozen=True)

    sources: List[HookSource]
    event_summaries: List[HookEventSummary]
    registrations: List[HookRegistration]
    stats: HookStats


class RelatedEvent(BaseModel):
    """Adjacent event in the lifecycle timeline."""

    model_config = ConfigDict(frozen=True)

    event_type: str
    phase: str
    can_block: bool
    description: str
    position: str  # "previous" | "next"


class HookEventDetail(BaseModel):
    """Response for GET /hooks/{event_type}."""

    model_config = ConfigDict(frozen=True)

    event: HookEventSummary
    schema_info: Optional[HookEventSchema] = None
    related_events: List[RelatedEvent]


class HookSourceDetail(BaseModel):
    """Response for GET /hooks/sources/{source_id}."""

    model_config = ConfigDict(frozen=True)

    source: HookSource
    scripts: List[HookScript]
    coverage_matrix: Dict[str, bool]


# =============================================================================
# Discovery Logic
# =============================================================================


def _detect_script_language(command: str) -> str:
    """Detect language from command string."""
    cmd_lower = command.lower()
    if "python3" in cmd_lower or "python" in cmd_lower:
        return "python"
    if "node " in cmd_lower or cmd_lower.endswith(".mjs") or cmd_lower.endswith(".js"):
        return "node"
    if "bash " in cmd_lower or "sh " in cmd_lower or cmd_lower.endswith(".sh"):
        return "shell"
    # Check file extension in command
    ext_match = re.search(r"\.(py|js|mjs|ts|sh|bash)\b", cmd_lower)
    if ext_match:
        ext_map = {
            "py": "python",
            "js": "node",
            "mjs": "node",
            "ts": "node",
            "sh": "shell",
            "bash": "shell",
        }
        return ext_map.get(ext_match.group(1), "unknown")
    return "unknown"


def _extract_script_filename(command: str) -> Optional[str]:
    """Extract the script filename from a command string."""
    # Remove leading interpreter (python3, node, bash, etc.)
    parts = command.strip().split()
    if not parts:
        return None

    # Find the first part that looks like a file path
    for part in parts:
        # Strip quotes
        clean = part.strip('"').strip("'")
        # Skip interpreter commands and flags
        if clean.startswith("-") or clean in ("python3", "python", "node", "bash", "sh"):
            continue
        # Expand ${CLAUDE_PLUGIN_ROOT} for display
        clean = re.sub(r"\$\{CLAUDE_PLUGIN_ROOT\}/?", "", clean)
        if clean:
            return Path(clean).name

    return None


def _resolve_script_path(
    command: str,
    source_type: str,
    install_path: Optional[Path] = None,
) -> Tuple[Optional[str], bool, Optional[str]]:
    """Resolve script to absolute path, detect symlinks.

    Returns:
        (full_path, is_symlink, symlink_target)
    """
    parts = command.strip().split()
    script_path_str = None

    for part in parts:
        clean = part.strip('"').strip("'")
        if clean.startswith("-") or clean in ("python3", "python", "node", "bash", "sh"):
            continue
        # Expand ${CLAUDE_PLUGIN_ROOT}
        if "${CLAUDE_PLUGIN_ROOT}" in clean and install_path:
            clean = clean.replace("${CLAUDE_PLUGIN_ROOT}", str(install_path))
        # Expand ~
        clean = os.path.expanduser(clean)
        script_path_str = clean
        break

    if not script_path_str:
        return None, False, None

    script_path = Path(script_path_str)
    if not script_path.exists():
        return None, False, None

    full_path = str(script_path.resolve())
    is_symlink = script_path.is_symlink()
    symlink_target = str(script_path.resolve()) if is_symlink else None

    return full_path, is_symlink, symlink_target


def _parse_hook_groups(
    hooks_config: dict,
    source_type: str,
    source_name: str,
    source_id: str,
    plugin_id: Optional[str] = None,
    description_fallback: Optional[str] = None,
    install_path: Optional[Path] = None,
) -> List[HookRegistration]:
    """Shared iteration over event_type -> groups -> hooks in a hooks config dict.

    Args:
        hooks_config: The ``"hooks": { ... }`` dict from settings or plugin JSON.
        source_type: "global", "project", or "plugin".
        source_name: Human-readable source label.
        source_id: URL-safe identifier for the source.
        plugin_id: Full plugin name (only for plugin sources).
        description_fallback: Fallback description when group has none (e.g. plugin description).
        install_path: Plugin install path for ``${CLAUDE_PLUGIN_ROOT}`` expansion.
    """
    registrations: List[HookRegistration] = []

    for event_type, groups in hooks_config.items():
        if not isinstance(groups, list):
            continue

        meta = HOOK_EVENT_METADATA.get(event_type, ("Unknown", False, ""))
        can_block = meta[1]

        for group in groups:
            if not isinstance(group, dict):
                continue

            matcher = group.get("matcher", "*")
            description = group.get("description") or description_fallback
            hook_list = group.get("hooks", [])

            if not isinstance(hook_list, list):
                continue

            for hook_entry in hook_list:
                if not isinstance(hook_entry, dict):
                    continue
                command = hook_entry.get("command", "")
                if not command:
                    continue

                timeout_ms = hook_entry.get("timeout")

                # For plugins, expand ${CLAUDE_PLUGIN_ROOT} in the display command
                display_command = command
                if install_path and "${CLAUDE_PLUGIN_ROOT}" in command:
                    display_command = command.replace("${CLAUDE_PLUGIN_ROOT}", str(install_path))

                registrations.append(
                    HookRegistration(
                        event_type=event_type,
                        source_type=source_type,
                        source_name=source_name,
                        source_id=source_id,
                        plugin_id=plugin_id,
                        matcher=str(matcher) if matcher else "*",
                        command=display_command,
                        script_filename=_extract_script_filename(command),
                        script_language=_detect_script_language(command),
                        timeout_ms=timeout_ms,
                        can_block=can_block,
                        description=description,
                    )
                )

    return registrations


def _parse_settings_hooks(
    settings_path: Path,
    source_type: str,
    source_name: str,
    source_id: str,
) -> List[HookRegistration]:
    """Parse hooks from a single settings.json file."""
    if not settings_path.exists():
        return []

    try:
        with open(settings_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        logger.warning("Failed to parse hooks from %s: %s", settings_path, e)
        return []

    hooks_config = data.get("hooks", {})
    if not isinstance(hooks_config, dict):
        return []

    return _parse_hook_groups(hooks_config, source_type, source_name, source_id)


def _parse_plugin_hooks(
    plugin_name: str,
    install_path: Path,
) -> List[HookRegistration]:
    """Parse hooks from a plugin's hooks/hooks.json."""
    hooks_json = install_path / "hooks" / "hooks.json"
    if not hooks_json.exists():
        return []

    try:
        with open(hooks_json, "r", encoding="utf-8") as f:
            raw = f.read()
        # Plugin hooks.json files often have trailing commas (invalid JSON).
        # Strip them before parsing: ",\s*]" → "]" and ",\s*}" → "}"
        raw = re.sub(r",\s*([}\]])", r"\1", raw)
        data = json.loads(raw)
    except (json.JSONDecodeError, OSError) as e:
        logger.warning("Failed to parse plugin hooks from %s: %s", hooks_json, e)
        return []

    # Plugin hooks.json has { "description": "...", "hooks": { ... } }
    plugin_description = data.get("description")
    hooks_config = data.get("hooks", {})
    if not isinstance(hooks_config, dict):
        return []

    short_name = plugin_name.split("@")[0] if "@" in plugin_name else plugin_name
    source_id = re.sub(r"[^a-zA-Z0-9_-]", "-", short_name)

    return _parse_hook_groups(
        hooks_config,
        source_type="plugin",
        source_name=short_name,
        source_id=source_id,
        plugin_id=plugin_name,
        description_fallback=plugin_description,
        install_path=install_path,
    )


def discover_hooks(project_path: Optional[str] = None) -> List[HookRegistration]:
    """
    Parse and merge hooks from all sources.

    Sources checked:
    1. ~/.claude/settings.json -> global hooks
    2. ~/.claude/settings.local.json -> global local hooks
    3. For each enabledPlugin -> {installPath}/hooks/hooks.json
    4. If project_path: {project}/.claude/settings.json + settings.local.json
    """
    all_registrations: List[HookRegistration] = []

    claude_base = settings.claude_base

    # 1. Global settings
    global_settings = claude_base / "settings.json"
    all_registrations.extend(
        _parse_settings_hooks(global_settings, "global", "Your Hooks", "global")
    )

    # 2. Global local settings
    global_local = claude_base / "settings.local.json"
    all_registrations.extend(
        _parse_settings_hooks(global_local, "global", "Your Hooks (local)", "global-local")
    )

    # 3. Plugin hooks - check enabledPlugins in settings
    enabled_plugins = _get_enabled_plugins(global_settings, global_local)

    for plugin_name, install_path in enabled_plugins.items():
        if install_path:
            all_registrations.extend(_parse_plugin_hooks(plugin_name, install_path))

    # 4. Project-level hooks
    if project_path:
        project_dir = Path(project_path)
        project_name = project_dir.name

        project_settings = project_dir / ".claude" / "settings.json"
        all_registrations.extend(
            _parse_settings_hooks(project_settings, "project", project_name, "project")
        )

        project_local = project_dir / ".claude" / "settings.local.json"
        all_registrations.extend(
            _parse_settings_hooks(
                project_local, "project", f"{project_name} (local)", "project-local"
            )
        )

    return all_registrations


def _get_enabled_plugins(
    settings_path: Path,
    local_settings_path: Path,
) -> Dict[str, Optional[Path]]:
    """Get enabled plugins and their install paths."""
    from models.plugin import load_installed_plugins

    # Merge enabledPlugins from both settings files
    enabled: Dict[str, bool] = {}

    for path in (settings_path, local_settings_path):
        if not path.exists():
            continue
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            ep = data.get("enabledPlugins", {})
            if isinstance(ep, dict):
                enabled.update(ep)
        except (json.JSONDecodeError, OSError):
            pass

    if not enabled:
        return {}

    # Get install paths from installed_plugins.json
    installed = load_installed_plugins()
    result: Dict[str, Optional[Path]] = {}

    for plugin_name, is_enabled in enabled.items():
        if not is_enabled:
            continue
        install_path = None
        if installed:
            installations = installed.get_plugin(plugin_name)
            if installations:
                install_path = Path(installations[0].install_path)
                if not install_path.exists():
                    install_path = None
        result[plugin_name] = install_path

    return result


def discover_hooks_cached(project_path: Optional[str] = None) -> List[HookRegistration]:
    """Cached version of discover_hooks. Only caches when project_path is None."""
    global _hooks_cache, _hooks_cache_time

    # Don't cache project-specific queries
    if project_path:
        return discover_hooks(project_path)

    now = datetime.now(timezone.utc)

    with _hooks_cache_lock:
        if (
            _hooks_cache is not None
            and _hooks_cache_time is not None
            and (now - _hooks_cache_time).total_seconds() < _HOOKS_CACHE_TTL_SECONDS
        ):
            return _hooks_cache

        result = discover_hooks(project_path)
        _hooks_cache = result
        _hooks_cache_time = datetime.now(timezone.utc)
        return result


# =============================================================================
# Schema Introspection
# =============================================================================


def _get_captain_hook_type_map() -> Optional[Dict[str, Any]]:
    """Import captain_hook's HOOK_TYPE_MAP if available."""
    try:
        from captain_hook import HOOK_TYPE_MAP

        return HOOK_TYPE_MAP
    except ImportError:
        logger.debug("captain_hook not available for schema introspection")
        return None


def _get_output_model_for_event(event_type: str) -> Optional[Any]:
    """Get the output model class for an event type."""
    try:
        from captain_hook import PermissionRequestOutput, PreToolUseOutput, StopOutput

        output_map = {
            "PreToolUse": PreToolUseOutput,
            "Stop": StopOutput,
            "SubagentStop": StopOutput,
            "PermissionRequest": PermissionRequestOutput,
            # TODO: Add UserPromptSubmitOutput when captain-hook exports it.
            # Currently captain_hook.outputs does not define an output model
            # for UserPromptSubmit hooks.
        }
        return output_map.get(event_type)
    except ImportError:
        return None


def _extract_fields(model_class: Any, exclude_base: bool = False) -> List[HookFieldInfo]:
    """Extract field info from a Pydantic model class."""
    fields = []
    base_field_names = {
        "session_id",
        "transcript_path",
        "cwd",
        "permission_mode",
        "hook_event_name",
    }

    for name, field_info in model_class.model_fields.items():
        if exclude_base and name in base_field_names:
            continue

        # Determine type string
        annotation = field_info.annotation
        type_str = str(annotation) if annotation else "Any"
        # Clean up type display
        type_str = type_str.replace("typing.", "").replace("<class '", "").replace("'>", "")

        required = field_info.is_required()
        description = field_info.description

        fields.append(
            HookFieldInfo(
                name=name,
                type=type_str,
                required=required,
                description=description,
            )
        )

    return fields


def get_event_schema(event_type: str) -> Optional[HookEventSchema]:
    """Introspect captain-hook Pydantic models to extract field info."""
    hook_type_map = _get_captain_hook_type_map()
    if not hook_type_map:
        return None

    model_class = hook_type_map.get(event_type)
    if not model_class:
        return None

    # Get base fields from BaseHook
    base_field_names = {
        "session_id",
        "transcript_path",
        "cwd",
        "permission_mode",
        "hook_event_name",
    }
    base_fields = [f for f in _extract_fields(model_class) if f.name in base_field_names]

    # Get event-specific input fields
    input_fields = _extract_fields(model_class, exclude_base=True)

    # Get output fields if applicable
    output_fields = []
    output_model = _get_output_model_for_event(event_type)
    if output_model:
        output_fields = _extract_fields(output_model)

    return HookEventSchema(
        input_fields=input_fields,
        output_fields=output_fields,
        base_fields=base_fields,
    )


# =============================================================================
# Aggregation
# =============================================================================


def build_hooks_overview(registrations: List[HookRegistration]) -> HooksOverview:
    """Aggregate registrations into sources, events, and stats."""
    # Group by source_id
    source_map: Dict[str, List[HookRegistration]] = {}
    for reg in registrations:
        source_map.setdefault(reg.source_id, []).append(reg)

    # Build sources
    sources = []
    for source_id, regs in source_map.items():
        first = regs[0]

        # Build scripts
        script_map: Dict[str, List[HookRegistration]] = {}
        for r in regs:
            key = r.script_filename or r.command
            script_map.setdefault(key, []).append(r)

        scripts = []
        for script_key, script_regs in script_map.items():
            sr = script_regs[0]
            full_path, is_symlink, symlink_target = _resolve_script_path(
                sr.command, sr.source_type, None
            )

            scripts.append(
                HookScript(
                    filename=sr.script_filename or script_key,
                    full_path=full_path,
                    language=sr.script_language,
                    source_name=sr.source_name,
                    event_types=sorted(set(r.event_type for r in script_regs)),
                    registrations=len(script_regs),
                    is_symlink=is_symlink,
                    symlink_target=symlink_target,
                )
            )

        event_types_covered = sorted(set(r.event_type for r in regs))
        blocking = sum(1 for r in regs if r.can_block)

        sources.append(
            HookSource(
                source_type=first.source_type,
                source_name=first.source_name,
                source_id=source_id,
                plugin_id=first.plugin_id,
                scripts=scripts,
                total_registrations=len(regs),
                event_types_covered=event_types_covered,
                blocking_hooks_count=blocking,
            )
        )

    # Group by event_type
    event_map: Dict[str, List[HookRegistration]] = {}
    for reg in registrations:
        event_map.setdefault(reg.event_type, []).append(reg)

    event_summaries = []
    for event_type in LIFECYCLE_ORDER:
        regs = event_map.get(event_type, [])
        meta = HOOK_EVENT_METADATA.get(event_type, ("Unknown", False, ""))

        event_summaries.append(
            HookEventSummary(
                event_type=event_type,
                phase=meta[0],
                can_block=meta[1],
                description=meta[2],
                total_registrations=len(regs),
                sources=sorted(set(r.source_name for r in regs)),
                registrations=regs,
            )
        )

    # Add any event types not in LIFECYCLE_ORDER
    for event_type, regs in event_map.items():
        if event_type not in LIFECYCLE_ORDER:
            meta = HOOK_EVENT_METADATA.get(event_type, ("Unknown", False, ""))
            event_summaries.append(
                HookEventSummary(
                    event_type=event_type,
                    phase=meta[0],
                    can_block=meta[1],
                    description=meta[2],
                    total_registrations=len(regs),
                    sources=sorted(set(r.source_name for r in regs)),
                    registrations=regs,
                )
            )

    # Stats
    blocking_hooks = sum(1 for r in registrations if r.can_block)

    stats = HookStats(
        total_sources=len(sources),
        total_registrations=len(registrations),
        total_scripts=sum(len(s.scripts) for s in sources),
        blocking_hooks=blocking_hooks,
        event_types_with_hooks=sum(1 for es in event_summaries if es.total_registrations > 0),
        event_types_total=len(HOOK_EVENT_METADATA),
    )

    return HooksOverview(
        sources=sources,
        event_summaries=event_summaries,
        registrations=registrations,
        stats=stats,
    )
