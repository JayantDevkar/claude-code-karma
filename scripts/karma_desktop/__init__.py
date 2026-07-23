"""Desktop launcher for Claude Code Karma.

Installs a clickable desktop entry (macOS ``.app`` / Windows Desktop shortcut)
that starts the karma dev servers on demand and opens the dashboard, so the
dashboard works after a reboot without touching a terminal.

Nothing in this package hardcodes a user, home directory, or repo location:
paths are derived at runtime from ``__file__``, and interpreter locations are
discovered on the target machine at install time.
"""

from .core import API_PORT, WEB_PORT, repo_root

__all__ = ["API_PORT", "WEB_PORT", "repo_root"]
