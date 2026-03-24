"""
Configuration management using Pydantic Settings.

Environment variables can be prefixed with CLAUDE_KARMA_ to override defaults.
Example: CLAUDE_KARMA_MAX_AGENT_SIZE=200000
"""

from pathlib import Path
from typing import List

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application configuration with environment variable support."""

    model_config = SettingsConfigDict(
        env_prefix="CLAUDE_KARMA_",
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    # Base directories
    claude_base: Path = Field(
        default_factory=lambda: Path.home() / ".claude",
        description="Base directory for Claude Code data",
    )

    # File size limits (in bytes)
    max_agent_size: int = Field(
        default=100_000,  # 100KB
        description="Maximum size for agent markdown files",
    )
    max_skill_size: int = Field(
        default=1_000_000,  # 1MB
        description="Maximum size for skill files",
    )

    # Cache durations (in seconds)
    cache_projects_list: int = Field(default=30, description="Cache duration for projects list")
    cache_project_detail: int = Field(default=60, description="Cache duration for project details")
    cache_session_detail: int = Field(default=60, description="Cache duration for session details")
    cache_file_activity: int = Field(default=300, description="Cache duration for file activity")
    cache_analytics: int = Field(default=120, description="Cache duration for analytics")
    cache_agents_list: int = Field(default=30, description="Cache duration for agents list")
    cache_agents_detail: int = Field(default=60, description="Cache duration for agent details")
    cache_skills_list: int = Field(default=30, description="Cache duration for skills list")
    cache_skills_detail: int = Field(default=60, description="Cache duration for skill details")
    cache_live_sessions: int = Field(
        default=5, description="Cache duration for live sessions (short for near-real-time)"
    )
    cache_agent_usage: int = Field(
        default=300,  # 5 minutes - historical data, doesn't change often
        description="Cache duration for agent usage analytics",
    )
    cache_agent_usage_revalidate: int = Field(
        default=600,  # 10 minutes stale-while-revalidate
        description="Stale-while-revalidate duration for agent usage",
    )

    # SQLite metadata index
    use_sqlite: bool = Field(
        default=True,
        description="Enable SQLite metadata index for fast queries. "
        "When disabled, falls back to JSONL-based loading.",
    )
    reindex_interval_seconds: int = Field(
        default=300,
        description="Interval in seconds between periodic SQLite re-index runs. "
        "Set to 0 to disable periodic reindexing.",
    )

    # Live session reconciler
    reconciler_enabled: bool = Field(
        default=True, description="Enable live session reconciler background task"
    )
    reconciler_check_interval: int = Field(
        default=60, description="Seconds between reconciler checks"
    )
    reconciler_idle_threshold: int = Field(
        default=120, description="Seconds of idle before considering reconciliation"
    )

    # CORS settings
    cors_origins: List[str] = Field(
        default=[
            "http://localhost:3000",
            "http://127.0.0.1:3000",
            "http://localhost:5173",
            "http://127.0.0.1:5173",
            "http://localhost:3001",
            "http://127.0.0.1:3001",
        ],
        description="Allowed CORS origins",
    )
    cors_allow_credentials: bool = Field(default=True, description="Allow credentials in CORS")
    cors_allow_methods: List[str] = Field(
        default=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        description="Allowed HTTP methods for CORS",
    )
    cors_allow_headers: List[str] = Field(
        default=["Content-Type", "Authorization"],
        description="Allowed headers for CORS",
    )

    # Logging
    log_level: str = Field(
        default="INFO", description="Logging level (DEBUG, INFO, WARNING, ERROR)"
    )

    # API metadata
    api_title: str = Field(default="Claude Code Karma API", description="API title")
    api_version: str = Field(default="0.1.0", description="API version")
    api_description: str = Field(
        default="API for monitoring Claude Code session activity",
        description="API description",
    )

    @property
    def agents_dir(self) -> Path:
        """Get the agents directory path."""
        return self.claude_base / "agents"

    @property
    def skills_dir(self) -> Path:
        """Get the skills directory path."""
        return self.claude_base / "skills"

    @property
    def commands_dir(self) -> Path:
        """Get the commands directory path."""
        return self.claude_base / "commands"

    @property
    def projects_dir(self) -> Path:
        """Get the projects directory path."""
        return self.claude_base / "projects"

    @property
    def todos_dir(self) -> Path:
        """Get the todos directory path."""
        return self.claude_base / "todos"

    @property
    def debug_dir(self) -> Path:
        """Get the debug logs directory path."""
        return self.claude_base / "debug"

    @property
    def live_sessions_dir(self) -> Path:
        """Get the live sessions state directory path."""
        return Path.home() / ".claude_karma" / "live-sessions"

    @property
    def karma_base(self) -> Path:
        """Get the base directory for Claude Code Karma data."""
        return Path.home() / ".claude_karma"

    @property
    def sqlite_db_path(self) -> Path:
        """Get the SQLite metadata database path."""
        return self.karma_base / "metadata.db"


# Global settings instance
settings = Settings()


# =============================================================================
# Constants (from services/constants.py)
# =============================================================================

# File operation tool mappings: tool_name -> (operation_type, path_field)
# Used by sessions.py, subagent_sessions.py, and collectors.py
FILE_TOOL_MAPPINGS: dict[str, tuple[str, str]] = {
    "Read": ("read", "file_path"),
    "Write": ("write", "file_path"),
    "Edit": ("edit", "file_path"),
    "StrReplace": ("edit", "file_path"),
    "Delete": ("delete", "file_path"),
    "Glob": ("search", "glob_pattern"),
    "LS": ("read", "target_directory"),
    "Grep": ("search", "path"),
    "SemanticSearch": ("search", "target_directories"),
}
