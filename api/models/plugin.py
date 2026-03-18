"""
Plugin model for Claude Code installed plugins.

Plugins are stored at ~/.claude/plugins/installed_plugins.json and represent
third-party extensions installed via Claude Code's plugin system. Each plugin
can have multiple installations (user scope, project scope, etc.).

Example plugin structure:
    ~/.claude/plugins/installed_plugins.json
    {
      "version": 2,
      "plugins": {
        "github@claude-plugins-official": [{
          "scope": "user",
          "installPath": "/path/to/plugin",
          "version": "e30768372b41",
          "installedAt": "2026-01-03T01:14:29.419Z",
          "lastUpdated": "2026-01-21T09:41:35.704Z"
        }]
      }
    }
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock
from typing import Dict, List, Optional, Tuple

from pydantic import BaseModel, ConfigDict, Field

from config import settings

logger = logging.getLogger(__name__)

# Module-level cache for installed plugins
_installed_plugins_cache: Optional["InstalledPlugins"] = None
_installed_plugins_cache_time: Optional[datetime] = None
_installed_plugins_cache_lock = Lock()
_PLUGINS_CACHE_TTL_SECONDS = 60  # 1 minute cache


class PluginInstallation(BaseModel):
    """
    Represents a single installation of a plugin.

    Plugins can be installed at different scopes (user, project, etc.)
    and each installation tracks its own version and timestamps.

    Attributes:
        scope: Installation scope (e.g., "user", "project")
        install_path: File system path to the plugin installation
        version: Plugin version identifier (commit hash or semver)
        installed_at: When the plugin was first installed
        last_updated: When the plugin was last updated
    """

    model_config = ConfigDict(frozen=True, populate_by_name=True)

    scope: str = Field(..., description="Installation scope (user, project, etc.)")
    install_path: str = Field(..., alias="installPath", description="Path to plugin installation")
    version: str = Field(..., description="Plugin version (commit hash or semver)")
    installed_at: datetime = Field(
        ..., alias="installedAt", description="Initial installation time"
    )
    last_updated: datetime = Field(..., alias="lastUpdated", description="Last update time")

    @property
    def is_user_scoped(self) -> bool:
        """Check if this is a user-level installation."""
        return self.scope == "user"

    @property
    def is_project_scoped(self) -> bool:
        """Check if this is a project-level installation."""
        return self.scope == "project"

    @property
    def days_since_installed(self) -> int:
        """Calculate days since initial installation."""
        now = datetime.now(timezone.utc)
        installed = (
            self.installed_at
            if self.installed_at.tzinfo
            else self.installed_at.replace(tzinfo=timezone.utc)
        )
        return (now - installed).days

    @property
    def days_since_updated(self) -> int:
        """Calculate days since last update."""
        now = datetime.now(timezone.utc)
        updated = (
            self.last_updated
            if self.last_updated.tzinfo
            else self.last_updated.replace(tzinfo=timezone.utc)
        )
        return (now - updated).days


class InstalledPlugins(BaseModel):
    """
    Represents the installed_plugins.json file structure.

    Contains version info and a dictionary of plugin names to their
    installation records. Each plugin can have multiple installations
    at different scopes.

    Attributes:
        version: File format version
        plugins: Map of plugin names to list of installations
    """

    model_config = ConfigDict(frozen=True)

    version: int = Field(..., description="File format version")
    plugins: Dict[str, List[PluginInstallation]] = Field(
        default_factory=dict, description="Map of plugin names to installations"
    )

    @property
    def plugin_count(self) -> int:
        """
        Count unique plugin names.

        Returns:
            Number of unique plugins installed
        """
        return len(self.plugins)

    @property
    def total_installations(self) -> int:
        """
        Sum all installations across all plugins.

        Returns:
            Total number of plugin installations (can exceed plugin_count
            if plugins are installed at multiple scopes)
        """
        return sum(len(installations) for installations in self.plugins.values())

    def list_all_installations(self) -> List[Tuple[str, PluginInstallation]]:
        """
        Get all plugin installations as (plugin_name, installation) tuples.

        Returns:
            List of (plugin_name, installation) tuples sorted by plugin name

        Example:
            >>> installed = load_installed_plugins()
            >>> for name, installation in installed.list_all_installations():
            ...     print(f"{name} @ {installation.scope}: v{installation.version}")
        """
        result = []
        for plugin_name, installations in sorted(self.plugins.items()):
            for installation in installations:
                result.append((plugin_name, installation))
        return result

    def get_plugin(self, name: str) -> Optional[List[PluginInstallation]]:
        """
        Get all installations for a specific plugin.

        Args:
            name: Plugin name (e.g., "github@claude-plugins-official")

        Returns:
            List of installations, or None if plugin not found
        """
        result = self.plugins.get(name)
        if result is not None:
            return result
        # Fallback: match by short name (e.g., "feature-dev" matches "feature-dev@claude-plugins-official")
        if "@" not in name:
            for full_name, installations in self.plugins.items():
                short = full_name.split("@")[0] if "@" in full_name else full_name
                if short == name:
                    return installations
        return None

    def get_plugin_full_name(self, name: str) -> Optional[str]:
        """Resolve a short plugin name to its full name, or return as-is if already full."""
        if name in self.plugins:
            return name
        if "@" not in name:
            for full_name in self.plugins:
                short = full_name.split("@")[0] if "@" in full_name else full_name
                if short == name:
                    return full_name
        return None

    def has_plugin(self, name: str) -> bool:
        """
        Check if a plugin is installed.

        Args:
            name: Plugin name

        Returns:
            True if plugin is installed, False otherwise
        """
        return self.get_plugin(name) is not None

    @classmethod
    def from_path(cls, path: Path) -> Optional["InstalledPlugins"]:
        """
        Load installed plugins from a JSON file path.

        Reads the file content and parses it into an InstalledPlugins instance.
        Gracefully handles missing files, invalid JSON, and permission errors.

        Args:
            path: Path to the installed_plugins.json file

        Returns:
            InstalledPlugins instance, or None if file doesn't exist or cannot be read

        Example:
            >>> plugins_file = Path.home() / ".claude" / "plugins" / "installed_plugins.json"
            >>> installed = InstalledPlugins.from_path(plugins_file)
            >>> if installed:
            ...     print(f"Found {installed.plugin_count} plugins")
        """
        if not path.exists() or not path.is_file():
            logger.debug(f"Plugins file not found or not a file: {path}")
            return None

        try:
            with open(path, "r", encoding="utf-8", errors="replace") as f:
                data = json.load(f)

            # Parse datetime strings in nested structures
            if "plugins" in data:
                for _plugin_name, installations in data["plugins"].items():
                    for installation in installations:
                        # Parse installedAt
                        if isinstance(installation.get("installedAt"), str):
                            installation["installedAt"] = datetime.fromisoformat(
                                installation["installedAt"].replace("Z", "+00:00")
                            )
                        # Parse lastUpdated
                        if isinstance(installation.get("lastUpdated"), str):
                            installation["lastUpdated"] = datetime.fromisoformat(
                                installation["lastUpdated"].replace("Z", "+00:00")
                            )

            return cls.model_validate(data)

        except (json.JSONDecodeError, OSError, ValueError) as e:
            logger.warning(f"Failed to load plugins from {path}: {e}")
            return None


def get_plugins_file() -> Path:
    """
    Get the ~/.claude/plugins/installed_plugins.json file path.

    Uses settings.claude_base for the base path to support configuration.

    Returns:
        Path to the installed_plugins.json file
    """
    return settings.claude_base / "plugins" / "installed_plugins.json"


def load_installed_plugins() -> Optional[InstalledPlugins]:
    """
    Load all installed plugins from the standard location.

    Uses a module-level cache with 60-second TTL to avoid repeated file reads.

    Returns:
        InstalledPlugins instance, or None if file doesn't exist or cannot be read

    Example:
        >>> installed = load_installed_plugins()
        >>> if installed:
        ...     print(f"Version: {installed.version}")
        ...     print(f"Plugins: {installed.plugin_count}")
        ...     for name, inst in installed.list_all_installations():
        ...         print(f"  {name} @ {inst.scope}")
    """
    global _installed_plugins_cache, _installed_plugins_cache_time

    now = datetime.now(timezone.utc)

    with _installed_plugins_cache_lock:
        if (
            _installed_plugins_cache is not None
            and _installed_plugins_cache_time is not None
            and (now - _installed_plugins_cache_time).total_seconds() < _PLUGINS_CACHE_TTL_SECONDS
        ):
            return _installed_plugins_cache

        plugins_file = get_plugins_file()
        result = InstalledPlugins.from_path(plugins_file)

        _installed_plugins_cache = result
        _installed_plugins_cache_time = now

        return result


def get_plugin_cache_path(plugin_name: str) -> Optional[Path]:
    """
    Get the cache path for a plugin.

    Plugin cache is at ~/.claude/plugins/cache/{marketplace}/{plugin}/{version}/

    Args:
        plugin_name: Plugin identifier (e.g., "oh-my-claudecode")

    Returns:
        Path to plugin cache directory, or None if not found
    """
    installed = load_installed_plugins()
    if not installed:
        return None

    installations = installed.get_plugin(plugin_name)
    if not installations:
        return None

    # Use first installation's path
    install_path = Path(installations[0].install_path)
    if install_path.exists():
        return install_path

    return None


def read_plugin_manifest(cache_path: Path) -> dict:
    """
    Read a plugin's .claude-plugin/plugin.json manifest.

    The manifest can specify custom paths for skills, commands, and agents
    that supplement the default directories.

    Args:
        cache_path: Plugin install/cache directory

    Returns:
        Parsed manifest dict, or empty dict if not found
    """
    manifest_file = cache_path / ".claude-plugin" / "plugin.json"
    if not manifest_file.exists():
        return {}
    try:
        with open(manifest_file, "r") as f:
            return json.load(f)
    except Exception as e:
        logger.debug(f"Failed to read plugin manifest at {manifest_file}: {e}")
        return {}


def resolve_manifest_dirs(
    cache_path: Path, manifest: dict, key: str, defaults: list[str]
) -> list[Path]:
    """
    Resolve directory paths from manifest custom paths + defaults.

    Custom paths from plugin.json supplement (not replace) defaults.
    Returns deduplicated list of existing directories.

    Args:
        cache_path: Plugin install directory
        manifest: Parsed plugin.json manifest
        key: Manifest key ("skills", "commands", "agents")
        defaults: Default subdirectory names to check

    Returns:
        List of existing directory Paths to scan
    """
    resolved_cache = cache_path.resolve()
    dirs: list[Path] = []
    seen: set[Path] = set()

    # Add default directories first
    for default in defaults:
        d = cache_path / default
        if d.exists() and d.is_dir():
            resolved = d.resolve()
            if resolved not in seen:
                dirs.append(d)
                seen.add(resolved)

    # Add custom path from manifest (supplements defaults)
    custom = manifest.get(key)
    if custom:
        custom_paths = [custom] if isinstance(custom, str) else custom
        for cp in custom_paths:
            # Strip leading ./ prefix for path resolution
            clean = cp.removeprefix("./")
            d = cache_path / clean
            if d.exists() and d.is_dir():
                resolved = d.resolve()
                # Security: ensure path stays within plugin directory
                try:
                    resolved.relative_to(resolved_cache)
                except ValueError:
                    logger.warning(f"Custom path escapes plugin dir: {cp}")
                    continue
                if resolved not in seen:
                    dirs.append(d)
                    seen.add(resolved)

    return dirs


def scan_plugin_capabilities(plugin_name: str) -> dict:
    """
    Scan a plugin's directory for its capabilities.

    Looks for:
    - agents/*.md files
    - skills/*/SKILL.md files
    - commands/*.md files
    - hooks/*.{py,js,ts} files
    - .mcp.json for MCP tools

    Also reads .claude-plugin/plugin.json manifest for custom paths
    that supplement the default directories.

    Args:
        plugin_name: Plugin identifier

    Returns:
        Dict with agents, skills, commands, mcp_tools, hooks lists
    """
    result = {"agents": [], "skills": [], "commands": [], "mcp_tools": [], "hooks": []}

    cache_path = get_plugin_cache_path(plugin_name)
    if not cache_path or not cache_path.exists():
        return result

    # Security: Validate path is within expected plugins directory
    try:
        resolved_cache = cache_path.resolve()
        plugins_base = (settings.claude_base / "plugins").resolve()
        resolved_cache.relative_to(plugins_base)
    except ValueError:
        logger.warning(f"Plugin path outside plugins directory: {plugin_name}")
        return result

    # Read manifest for custom paths
    manifest = read_plugin_manifest(cache_path)

    # Scan agents directories (default + manifest custom paths)
    for agents_dir in resolve_manifest_dirs(cache_path, manifest, "agents", ["agents"]):
        for f in agents_dir.glob("*.md"):
            if f.stem not in result["agents"]:
                result["agents"].append(f.stem)

    # Scan skills directories first (recursive for SKILL.md)
    # Skills take priority over commands when both exist (skills have richer structure)
    for skills_dir in resolve_manifest_dirs(cache_path, manifest, "skills", ["skills"]):
        for f in skills_dir.rglob("SKILL.md"):
            skill_name = f.parent.name
            if skill_name not in result["skills"]:
                result["skills"].append(skill_name)

    # Scan commands directories — skip entries already found as skills
    skills_set = set(result["skills"])
    for commands_dir in resolve_manifest_dirs(cache_path, manifest, "commands", ["commands"]):
        for f in commands_dir.glob("*.md"):
            if f.stem not in skills_set and f.stem not in result["commands"]:
                result["commands"].append(f.stem)

    # Scan hooks directory
    hooks_dir = cache_path / "hooks"
    if hooks_dir.exists():
        hook_types = set()
        for ext in ["*.py", "*.js", "*.ts"]:
            for f in hooks_dir.glob(ext):
                # Extract hook type from filename (e.g., PreToolUse.py -> PreToolUse)
                hook_types.add(f.stem)
        result["hooks"] = list(hook_types)

    # Check for MCP tools in .mcp.json
    # Server names must match SQLite convention: plugin_{short_name}_{server_key}
    # e.g. playwright@claude-plugins-official with server "playwright" -> plugin_playwright_playwright
    plugin_short = plugin_name.split("@")[0] if "@" in plugin_name else plugin_name
    mcp_config = cache_path / ".mcp.json"
    if mcp_config.exists():
        try:
            with open(mcp_config, "r", encoding="utf-8", errors="replace") as f:
                mcp_data = json.load(f)
                server_keys = []
                if "mcpServers" in mcp_data:
                    server_keys = list(mcp_data["mcpServers"].keys())
                else:
                    # Top-level keys are server names (Claude plugin format)
                    for key, value in mcp_data.items():
                        if isinstance(value, dict) and (
                            "command" in value or "type" in value or "url" in value
                        ):
                            server_keys.append(key)
                for key in server_keys:
                    result["mcp_tools"].append(f"plugin_{plugin_short}_{key}")
        except Exception as e:
            logger.debug(f"Failed to parse MCP config for {plugin_name}: {e}")

    # Detect dist/mcp/*-server.js files (SDK in-process MCP servers)
    mcp_dist = cache_path / "dist" / "mcp"
    if mcp_dist.exists():
        for f in mcp_dist.glob("*-server.js"):
            server_key = f.stem.replace("-server", "")
            server_name = f"plugin_{plugin_short}_{server_key}"
            if server_name not in result["mcp_tools"]:
                result["mcp_tools"].append(server_name)

    return result


def read_command_contents(plugin_name: str) -> list[dict]:
    """
    Read command/skill .md file contents for a plugin.

    Reads from both default directories (commands/, skills/) and
    custom paths defined in .claude-plugin/plugin.json manifest.

    Args:
        plugin_name: Plugin identifier

    Returns:
        List of dicts with 'name' and 'content' keys
    """
    result = []
    seen_names: set[str] = set()

    cache_path = get_plugin_cache_path(plugin_name)
    if not cache_path or not cache_path.exists():
        return result

    # Security: Validate path is within expected plugins directory
    try:
        resolved_cache = cache_path.resolve()
        plugins_base = (settings.claude_base / "plugins").resolve()
        resolved_cache.relative_to(plugins_base)
    except ValueError:
        logger.warning(f"Plugin path outside plugins directory: {plugin_name}")
        return result

    manifest = read_plugin_manifest(cache_path)

    # Scan skills directories for SKILL.md files
    for skills_dir in resolve_manifest_dirs(cache_path, manifest, "skills", ["skills"]):
        for f in sorted(skills_dir.rglob("SKILL.md")):
            name = f.parent.name
            if name not in seen_names:
                seen_names.add(name)
                try:
                    content = f.read_text(encoding="utf-8")
                    result.append({"name": name, "content": content})
                except Exception as e:
                    logger.debug(f"Failed to read skill file {f}: {e}")
                    result.append({"name": name, "content": None})

    # Scan commands directories for .md files
    for commands_dir in resolve_manifest_dirs(cache_path, manifest, "commands", ["commands"]):
        for f in sorted(commands_dir.glob("*.md")):
            if f.stem not in seen_names:
                seen_names.add(f.stem)
                try:
                    content = f.read_text(encoding="utf-8")
                    result.append({"name": f.stem, "content": content})
                except Exception as e:
                    logger.debug(f"Failed to read command file {f}: {e}")
                    result.append({"name": f.stem, "content": None})

    return result


def get_plugin_description(plugin_name: str) -> Optional[str]:
    """
    Get plugin description from plugin.json metadata.

    Args:
        plugin_name: Plugin identifier

    Returns:
        Description string or None
    """
    cache_path = get_plugin_cache_path(plugin_name)
    if not cache_path:
        return None

    plugin_json = cache_path / "plugin.json"
    if plugin_json.exists():
        try:
            with open(plugin_json, "r", encoding="utf-8", errors="replace") as f:
                data = json.load(f)
                return data.get("description")
        except Exception as e:
            logger.debug(f"Failed to read plugin.json for {plugin_name}: {e}")

    return None
