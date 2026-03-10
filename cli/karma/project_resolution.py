"""Project resolution helpers for Karma sync.

Handles resolving team project records to correct local Claude project
directories, and auto-sharing Syncthing folders when a new member joins.
"""

import json
import sys
from pathlib import Path
from typing import Optional

import click

from karma.config import KARMA_BASE
from karma.sync import detect_git_identity

# Add API to path for sync_queries
_API_PATH = Path(__file__).parent.parent.parent / "api"
if str(_API_PATH) not in sys.path:
    sys.path.insert(0, str(_API_PATH))


def _extract_real_path_from_sessions(project_dir: Path) -> Optional[str]:
    """Extract the real project path from JSONL session files in a Claude project dir.

    Claude encodes project paths lossily (hyphens in path components become
    indistinguishable from path separators), so we cannot reliably reverse the
    encoding.  Instead, we read the ``cwd`` field from session JSONL files,
    which contains the actual filesystem path.

    Args:
        project_dir: A ``~/.claude/projects/{encoded_name}/`` directory.

    Returns:
        The real project path string, or ``None`` if no valid cwd is found.
    """
    if not project_dir.is_dir():
        return None

    session_files = sorted(
        [p for p in project_dir.glob("*.jsonl") if not p.name.startswith("agent-")]
    )
    if not session_files:
        return None

    # Try up to 5 session files (some may be empty or lack cwd)
    for session_file in session_files[:5]:
        try:
            with open(session_file, "r", encoding="utf-8") as f:
                for i, line in enumerate(f):
                    if i > 50:
                        break
                    try:
                        data = json.loads(line.strip())
                        cwd = data.get("cwd")
                        if cwd and Path(cwd).is_absolute():
                            return cwd
                    except json.JSONDecodeError:
                        continue
        except (OSError, PermissionError, UnicodeDecodeError):
            continue

    return None


def resolve_local_project(conn, team_name: str, project_encoded_name: str):
    """Resolve a team project record to the correct local Claude project.

    When a joiner accepts folder offers, the DB record may have an arbitrary
    folder suffix as ``project_encoded_name`` with ``path=None``.  This helper
    tries to find the real local Claude project directory and fix the record.

    Resolution strategy:
      A. Read manifest from any teammate's inbox to extract ``git_identity``.
      B. If git_identity found, look up the local ``projects`` table.
      C. If not in DB, scan ``~/.claude/projects/`` dirs for a matching git remote.

    Returns ``(resolved_encoded_name, resolved_path, git_identity)`` or ``None``.
    """
    from db.sync_queries import (
        find_project_by_git_identity,
        find_project_by_git_suffix,
        upsert_team_project,
    )

    git_identity = None

    # ── Step A0: Reverse-lookup git_identity from suffix via DB ───────
    # Syncthing folder suffixes use git_identity.replace("/", "-"), e.g.
    # "jayantdevkar-claude-code-karma" from "jayantdevkar/claude-code-karma".
    # Try matching against the local projects table directly — no manifest needed.
    local = find_project_by_git_suffix(conn, project_encoded_name)
    if local:
        git_identity = local["git_identity"]

    # ── Step A: Extract git_identity from any available manifest ──────
    if not git_identity:
        remote_base = KARMA_BASE / "remote-sessions"
        if remote_base.is_dir():
            for user_dir in remote_base.iterdir():
                if not user_dir.is_dir():
                    continue
                manifest_path = user_dir / project_encoded_name / "manifest.json"
                if manifest_path.exists():
                    try:
                        manifest = json.loads(manifest_path.read_text())
                        git_identity = manifest.get("git_identity")
                        if git_identity:
                            break
                    except (json.JSONDecodeError, OSError):
                        continue

    # ── Step A1: Infer git_identity by scanning local projects ──────
    # When the joiner's DB is empty (brand-new member) and no manifests
    # exist yet, we can still resolve the project by scanning local
    # ~/.claude/projects/ dirs and matching their git remotes against
    # the suffix. The suffix IS git_identity.replace("/", "-"), so if
    # a local project's git remote normalizes to the same suffix, we
    # have our match — and we now know the git_identity too.
    #
    # We extract the real project path from session JSONL files (the
    # ``cwd`` field) rather than trying to reverse Claude's lossy path
    # encoding, which mangles hyphens in path components.
    if not git_identity:
        projects_dir = Path.home() / ".claude" / "projects"
        if projects_dir.is_dir():
            for candidate_dir in projects_dir.iterdir():
                if not candidate_dir.is_dir():
                    continue
                dirname = candidate_dir.name
                if not dirname.startswith("-"):
                    continue
                # Extract real path from session cwd instead of lossy decode
                candidate_path = _extract_real_path_from_sessions(candidate_dir)
                if not candidate_path or not Path(candidate_path).is_dir():
                    continue
                candidate_git_id = detect_git_identity(candidate_path)
                if candidate_git_id and candidate_git_id.replace("/", "-") == project_encoded_name:
                    git_identity = candidate_git_id
                    # We found the match — skip ahead to Step B/C which will
                    # handle the DB upsert and return the resolved project.
                    resolved_encoded = dirname
                    resolved_path = candidate_path
                    upsert_team_project(
                        conn, team_name, resolved_encoded, resolved_path,
                        git_identity=git_identity,
                    )
                    if resolved_encoded != project_encoded_name:
                        from db.sync_queries import remove_team_project
                        try:
                            remove_team_project(conn, team_name, project_encoded_name)
                        except Exception:
                            pass
                    return resolved_encoded, resolved_path, git_identity

    if not git_identity:
        return None

    # ── Step B: Look up by git_identity in local projects table ───────
    local = find_project_by_git_identity(conn, git_identity)
    if local:
        resolved_encoded = local["encoded_name"]
        resolved_path = local.get("project_path")
        if resolved_encoded != project_encoded_name:
            upsert_team_project(
                conn, team_name, resolved_encoded, resolved_path, git_identity=git_identity,
            )
            # Remove the stale record with the old (wrong) encoded name
            from db.sync_queries import remove_team_project
            try:
                remove_team_project(conn, team_name, project_encoded_name)
            except Exception:
                pass
        return resolved_encoded, resolved_path, git_identity

    # ── Step C: Scan ~/.claude/projects/ dirs for matching git remote ─
    # Uses session JSONL cwd extraction instead of lossy path decoding,
    # so projects with hyphens in their path components can be resolved.
    projects_dir = Path.home() / ".claude" / "projects"
    if not projects_dir.is_dir():
        return None

    for candidate_dir in projects_dir.iterdir():
        if not candidate_dir.is_dir():
            continue
        dirname = candidate_dir.name
        if not dirname.startswith("-"):
            continue
        # Extract real path from session cwd instead of lossy decode
        candidate_path = _extract_real_path_from_sessions(candidate_dir)
        if not candidate_path or not Path(candidate_path).is_dir():
            continue
        candidate_git_id = detect_git_identity(candidate_path)
        if candidate_git_id and candidate_git_id == git_identity:
            resolved_encoded = dirname
            resolved_path = candidate_path
            upsert_team_project(
                conn, team_name, resolved_encoded, resolved_path, git_identity=git_identity,
            )
            if resolved_encoded != project_encoded_name:
                from db.sync_queries import remove_team_project
                try:
                    remove_team_project(conn, team_name, project_encoded_name)
                except Exception:
                    pass
            return resolved_encoded, resolved_path, git_identity

    return None


def auto_share_folders(st, config, conn, team_name: str, new_device_id: str) -> None:
    """Auto-create Syncthing shared folders for all projects in a team.

    Each user gets their own outbox folder with a unique ID:
      - karma-out-{my_user_id}-{project} (send-only: my sessions → teammates)
      - karma-in-{their_user_id}-{project} (receive-only: their sessions → my machine)
    """
    from db.sync_queries import list_team_projects, list_members

    projects = list_team_projects(conn, team_name)
    members = list_members(conn, team_name)

    for proj in projects:
        encoded = proj["project_encoded_name"]
        git_id = proj.get("git_identity")
        if git_id:
            proj_short = git_id.replace("/", "-")
        elif proj["path"]:
            proj_short = Path(proj["path"]).name
        else:
            proj_short = encoded

        # 1. My outbox: send my sessions to teammates
        outbox_path = str(KARMA_BASE / "remote-sessions" / config.user_id / encoded)
        outbox_id = f"karma-out-{config.user_id}-{proj_short}"
        all_device_ids = [new_device_id]
        if config.syncthing.device_id:
            all_device_ids.append(config.syncthing.device_id)
        for m in members:
            if m["device_id"] and m["device_id"] not in all_device_ids:
                all_device_ids.append(m["device_id"])
        try:
            Path(outbox_path).mkdir(parents=True, exist_ok=True)
            st.add_folder(outbox_id, outbox_path, all_device_ids, folder_type="sendonly")
            click.echo(f"Outbox '{outbox_id}' -> {outbox_path} (send-only)")
        except Exception as e:
            click.echo(f"Warning: Could not create outbox for '{proj_short}': {e}")

        # 2. Inbox for the new member
        for m in members:
            if m["device_id"] == new_device_id:
                inbox_path = str(KARMA_BASE / "remote-sessions" / m["name"] / encoded)
                inbox_id = f"karma-out-{m['name']}-{proj_short}"
                inbox_devices = [new_device_id]
                if config.syncthing.device_id:
                    inbox_devices.append(config.syncthing.device_id)
                try:
                    Path(inbox_path).mkdir(parents=True, exist_ok=True)
                    st.add_folder(inbox_id, inbox_path, inbox_devices, folder_type="receiveonly")
                    click.echo(f"Inbox '{inbox_id}' -> {inbox_path} (receive-only)")
                except Exception as e:
                    click.echo(f"Warning: Could not create inbox for '{m['name']}/{proj_short}': {e}")
