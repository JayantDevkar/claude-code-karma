"""Worktree directory discovery for CLI packager.

Detects worktree project directories that belong to a given main project.
This is a lightweight port of the logic in api/services/desktop_sessions.py,
without any API dependencies.

Worktree patterns (all encoded by Claude Code):
  1. CLI worktrees:    {project}/.claude/worktrees/{name}
     Encoded:          {project_encoded}--claude-worktrees-{name}
  2. Superpowers:      {project}/.worktrees/{name}
     Encoded:          {project_encoded}--worktrees-{name}
  3. Desktop worktrees: ~/.claude-worktrees/{project}/{name}
     Encoded:          -Users-{user}--claude-worktrees-{project}-{name}
     (These DON'T share a prefix with the main project -- handled separately)
"""

from pathlib import Path

_WORKTREE_MARKERS = [
    "--claude-worktrees-",
    "-.claude-worktrees-",
    "--worktrees-",
    "-.worktrees-",
]


def is_worktree_dir(encoded_name: str) -> bool:
    """Check if an encoded project directory name is a worktree."""
    if not encoded_name:
        return False
    if "-claude-worktrees-" in encoded_name:
        return True
    if "--worktrees-" in encoded_name or "-.worktrees-" in encoded_name:
        return True
    return False


def _get_worktree_prefix(encoded_name: str) -> str | None:
    """Extract the main project prefix from a worktree encoded name.

    Returns the prefix before the worktree marker, or None if not a
    prefix-style worktree (e.g., Desktop worktrees don't share a prefix).
    """
    for marker in _WORKTREE_MARKERS:
        idx = encoded_name.find(marker)
        if idx > 0:
            prefix = encoded_name[:idx]
            if prefix.startswith("-") and len(prefix) > 1:
                return prefix
    return None


def find_worktree_dirs(
    main_encoded_name: str, projects_dir: Path
) -> list[Path]:
    """Find all worktree directories that belong to a main project.

    Scans projects_dir for directories whose encoded name starts with
    the main project's encoded name followed by a worktree marker.

    Args:
        main_encoded_name: The main project's encoded directory name
            (e.g., "-Users-jay-GitHub-karma").
        projects_dir: Path to ~/.claude/projects/

    Returns:
        List of Path objects for matching worktree directories.
    """
    if not projects_dir.is_dir():
        return []

    matches = []
    for entry in projects_dir.iterdir():
        if not entry.is_dir():
            continue
        if entry.name == main_encoded_name:
            continue  # skip the main project itself
        if not is_worktree_dir(entry.name):
            continue
        # Check if this worktree's prefix matches the main project
        prefix = _get_worktree_prefix(entry.name)
        if prefix == main_encoded_name:
            matches.append(entry)

    return sorted(matches)


def project_name_from_path(project_path: str) -> str:
    """Extract the directory name from a full project path.

    Examples:
        /Users/jay/GitHub/claude-karma -> claude-karma
        C:\\Users\\jay\\repos\\karma     -> karma
        /Users/jay/repo/               -> repo  (trailing slash)
        myproject                      -> myproject
    """
    p = project_path.replace("\\", "/").rstrip("/")
    return p.rsplit("/", 1)[-1] if "/" in p else p


def find_desktop_worktree_dirs(
    project_name: str,
    projects_dir: Path,
    worktree_base: Path | None = None,
) -> list[Path]:
    """Find Desktop worktree directories for a project.

    Desktop worktrees (created by Claude Desktop) live in
    ~/.claude-worktrees/{project_name}/{random_name}/ and get encoded as:
      -Users-{user}--claude-worktrees-{project}-{name}

    These DON'T share a prefix with the main project, so we scan for
    the marker pattern instead.
    """
    if worktree_base is None:
        worktree_base = Path.home() / ".claude-worktrees"

    if not projects_dir.is_dir():
        return []

    marker = f"-claude-worktrees-{project_name}-"

    matches = []
    for entry in projects_dir.iterdir():
        if not entry.is_dir():
            continue
        if marker not in entry.name:
            continue
        matches.append(entry)

    return sorted(matches)


def find_all_worktree_dirs(
    main_encoded_name: str,
    project_path: str,
    projects_dir: Path,
    worktree_base: Path | None = None,
) -> list[Path]:
    """Find ALL worktree directories for a project (CLI + Desktop).

    Combines find_worktree_dirs() (prefix match) and
    find_desktop_worktree_dirs() (project name match), deduplicating results.
    """
    cli_dirs = find_worktree_dirs(main_encoded_name, projects_dir)
    proj_name = project_name_from_path(project_path)
    desktop_dirs = find_desktop_worktree_dirs(proj_name, projects_dir, worktree_base)

    seen: set[Path] = set()
    result: list[Path] = []
    for d in cli_dirs + desktop_dirs:
        resolved = d.resolve()
        if resolved not in seen:
            seen.add(resolved)
            result.append(d)

    return sorted(result)
