"""
Git remote → canonical project identity.

`git_identity` is a machine-independent identity for a git repo, in the
form `owner/repo` (lowercase). It lets us treat all local checkouts,
worktrees, subfolders, and sync-imported variants of one repo as the
same project for cross-cutting views (e.g. "tickets touched in this
project" aggregates across encoded_names sharing a git_identity).

Two functions:
  normalize_git_url(url)  — pure parser. URL string → "owner/repo" or None.
  read_git_identity(path) — composes the subprocess + the parser. Safe
                            (timeout + swallowed errors); returns None
                            when path isn't a git checkout, the remote
                            isn't set, git is unavailable, etc.

The parser handles the URL shapes git accepts for `remote.origin.url`:
  https://github.com/Owner/Repo.git
  https://github.com/Owner/Repo
  git@github.com:Owner/Repo.git
  ssh://git@github.com/Owner/Repo.git
plus GitLab/Bitbucket variants of the same shapes. Output is always
lowercased so case-only differences in case-insensitive providers
(GitHub) don't fragment the identity.

We don't include the host (so github.com/foo/bar and gitlab.com/foo/bar
collide). This matches the sync_projects format already in use and is
acceptable for the current scope — see the v12 schema migration notes.
"""

from __future__ import annotations

import logging
import re
import subprocess
from typing import Optional

logger = logging.getLogger(__name__)

# Match either:
#   scp-style:  user@host:path        (no slashes between host and path)
#   url-style:  scheme://[user@]host/path
# In both cases we want the path portion (everything after host).
_SCP_RE = re.compile(r"^[^@]+@[^:]+:(?P<path>.+)$")
_URL_RE = re.compile(r"^[a-z]+://(?:[^@/]+@)?[^/]+/(?P<path>.+)$", re.IGNORECASE)


def normalize_git_url(url: Optional[str]) -> Optional[str]:
    """Parse a git remote URL into canonical `owner/repo` (lowercase).

    Returns None on empty input or anything we can't reduce to at least
    `owner/repo` (e.g. a local path, a URL with no path segments).
    """
    if not url:
        return None
    url = url.strip()
    if not url:
        return None

    # Try scp-style first; it's more restrictive and would otherwise
    # be misparsed as a URL-style match would fail anyway.
    m = _SCP_RE.match(url) or _URL_RE.match(url)
    if m is None:
        return None

    path = m.group("path").strip("/")
    if path.endswith(".git"):
        path = path[:-4]

    # Require at least owner/repo. Reject anything shallower.
    parts = [p for p in path.split("/") if p]
    if len(parts) < 2:
        return None

    # Take owner/repo from the LAST two segments. This handles
    # self-hosted setups where the path includes a group hierarchy
    # (gitlab.example.com/team/subgroup/owner/repo) — we keep the
    # repo's immediate parent as the owner, which matches how users
    # typically refer to the repo.
    owner, repo = parts[-2], parts[-1]
    return f"{owner}/{repo}".lower()


def read_git_identity(project_path: Optional[str]) -> Optional[str]:
    """Read `remote.origin.url` from the git config at `project_path`
    and normalize it. Returns None whenever anything goes wrong — this
    function is called from the indexer hot path and must never raise.

    The shellout uses the same defensive pattern as
    `hooks/ticket_branch_detector.py:git_current_branch`: 2-second
    timeout, `check=False`, swallowed FileNotFoundError/TimeoutExpired/
    OSError. `git config --get` returns exit code 1 (not 0) when the
    key is absent, which we treat as "no remote configured" → None.
    """
    if not project_path:
        return None
    try:
        result = subprocess.run(
            ["git", "-C", project_path, "config", "--get", "remote.origin.url"],
            capture_output=True,
            text=True,
            timeout=2,
            check=False,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError) as e:
        logger.debug("git_identity read failed for %s: %r", project_path, e)
        return None

    if result.returncode != 0:
        return None
    return normalize_git_url(result.stdout)
