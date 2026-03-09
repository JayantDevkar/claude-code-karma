"""Karma CLI entry point."""

import json
import re
import sys
from pathlib import Path
from typing import Optional

import click

from karma.config import SyncConfig, SyncthingSettings, SYNC_CONFIG_PATH, KARMA_BASE
from karma.sync import encode_project_path, detect_git_identity

# Add API to path for sync_queries
_API_PATH = Path(__file__).parent.parent.parent / "api"
if str(_API_PATH) not in sys.path:
    sys.path.insert(0, str(_API_PATH))

_SAFE_NAME = re.compile(r"^[a-zA-Z0-9_\-]+$")
SAFE_PATH_PART = re.compile(r"^[a-zA-Z0-9_\-\.]+$")


def _resolve_local_project(conn, team_name: str, project_encoded_name: str):
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
    from db.sync_queries import find_project_by_git_identity, upsert_team_project

    git_identity = None

    # ── Step A: Extract git_identity from any available manifest ──────
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
    projects_dir = Path.home() / ".claude" / "projects"
    if not projects_dir.is_dir():
        return None

    for candidate_dir in projects_dir.iterdir():
        if not candidate_dir.is_dir():
            continue
        dirname = candidate_dir.name
        if not dirname.startswith("-"):
            continue
        # Reconstruct the project path from the encoded name
        candidate_path = "/" + dirname[1:].replace("-", "/")
        if not Path(candidate_path).is_dir():
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


def _get_db():
    """Get a SQLite connection with schema applied."""
    from karma.db import get_connection

    return get_connection()


def _auto_share_folders(st, config, conn, team_name, new_device_id):
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


def _parse_folder_id(folder_id: str) -> Optional[tuple[str, str]]:
    """Parse a karma folder ID into (member_name, suffix).

    Expected format: ``karma-out-{member_name}-{suffix}``
    where *suffix* may itself contain hyphens.

    Returns ``None`` if the folder ID does not match the expected pattern.
    """
    # "karma-out-alice-acme-app" → member="alice", suffix="acme-app"
    prefix = "karma-out-"
    if not folder_id.startswith(prefix):
        return None
    rest = folder_id[len(prefix):]  # "alice-acme-app"
    # Member names are validated with _SAFE_NAME (alphanum, dash, underscore).
    # Since hyphens are allowed in member names AND suffixes, we can't split
    # on a single hyphen. Instead, we look up known member names from the DB
    # when available, or fall back to splitting on the first hyphen (which
    # works when member names don't contain hyphens — the common case).
    parts = rest.split("-")
    if len(parts) < 2:
        return None
    # Try progressively longer prefixes as the member name.
    # The first non-empty remainder wins.
    # e.g., "alice-bob-app" tries: ("alice", "bob-app"), ("alice-bob", "app")
    for i in range(1, len(parts)):
        candidate_name = "-".join(parts[:i])
        candidate_suffix = "-".join(parts[i:])
        if candidate_name and candidate_suffix:
            # Prefer the shortest member name (most common case)
            return candidate_name, candidate_suffix
    return None


def _extract_username_from_karma_folder(
    folder_id: str, prefix: str, known_names: set,
) -> Optional[tuple[str, str]]:
    """Extract (username, remainder) from a karma folder ID.

    Uses ``known_names`` (own user_id + real usernames discovered from
    handshake folders) to correctly disambiguate multi-dash usernames.
    Falls back to shortest-split when no known name matches.
    """
    rest = folder_id[len(prefix):]
    # Try known names longest-first for greedy match
    for name in sorted(known_names, key=len, reverse=True):
        if rest.startswith(name + "-"):
            remainder = rest[len(name) + 1:]
            if remainder:
                return name, remainder
    # Fallback: shortest split
    parts = rest.split("-", 1)
    if len(parts) == 2 and parts[0] and parts[1]:
        return parts[0], parts[1]
    return None


def _accept_pending_folders(st, config, conn):
    """Accept pending folder offers from known team members.

    Security policy:
    - Only accepts folders from device IDs registered in sync_members
    - Only accepts folder IDs prefixed with 'karma-'
    - Replaces empty pre-created inbox folders that conflict on the same path

    Handles three folder types:
    - ``karma-join-{user}-{team}`` — handshake folders (receiveonly)
    - ``karma-out-{self}-{suffix}`` — own outbox offered back (sendonly)
    - ``karma-out-{other}-{suffix}`` — other's outbox (receiveonly inbox)

    When the joiner's local DB has no ``sync_team_projects`` records (because
    they joined a team rather than creating it), folders are still accepted if
    offered by a known device.  The inbox path is derived from the folder ID
    itself, and a ``sync_team_projects`` record is auto-created so that
    subsequent operations (watcher, status) can find the project.
    """
    from db.sync_queries import get_known_devices, list_team_projects, list_teams, upsert_member

    pending = st.get_pending_folders()
    if not pending:
        return 0

    known_devices = get_known_devices(conn)
    accepted = 0
    existing_folder_ids = {f["id"] for f in st.get_folders()}
    own_device_id = config.syncthing.device_id if config.syncthing else None
    own_user_id = config.user_id

    # ── Pre-scan: extract real usernames from karma-join-* folders ────
    # Handshake folders encode the karma user_id (not the device hostname),
    # so we can use them to fix member names that were derived from hostnames.
    all_team_names = {t["name"] for t in list_teams(conn)}
    real_usernames: dict[str, str] = {}  # device_id → real karma user_id
    for folder_id, folder_info in pending.items():
        if not folder_id.startswith("karma-join-"):
            continue
        rest = folder_id[len("karma-join-"):]
        for i in range(len(rest.split("-")) - 1, 0, -1):
            parts = rest.split("-")
            candidate_team = "-".join(parts[i:])
            candidate_user = "-".join(parts[:i])
            if candidate_team in all_team_names:
                # Found a valid team — map all offering devices to this username
                for dev_id in folder_info.get("offeredBy", {}):
                    if dev_id in known_devices:
                        real_usernames[dev_id] = candidate_user
                        # Update DB member name if it was hostname-derived.
                        # upsert_member uses ON CONFLICT(team_name, device_id)
                        # so this correctly updates the name in place.
                        db_name, db_team = known_devices[dev_id]
                        if db_name != candidate_user:
                            click.echo(
                                f"  Updating member name: {db_name} → {candidate_user} "
                                f"(from handshake folder)"
                            )
                            upsert_member(conn, db_team, candidate_user, device_id=dev_id)
                break

    # Build set of known names for folder ID disambiguation
    known_names = {own_user_id}
    known_names.update(real_usernames.values())
    known_names.update(name for name, _ in known_devices.values())

    # Refresh known_devices after potential member name updates
    known_devices = get_known_devices(conn)

    for folder_id, folder_info in pending.items():
        if not folder_id.startswith("karma-"):
            click.echo(f"  Skipped non-karma folder offer '{folder_id}' (security policy)")
            continue

        if folder_id in existing_folder_ids:
            for device_id in folder_info.get("offeredBy", {}):
                try:
                    st.dismiss_pending_folder(folder_id, device_id)
                except Exception:
                    pass
            click.echo(f"  Dismissed '{folder_id}' (already configured locally)")
            continue

        offered_by = folder_info.get("offeredBy", {})
        for device_id, _offer in offered_by.items():
            if own_device_id and device_id == own_device_id:
                continue

            if device_id not in known_devices:
                short_id = device_id[:20] + "..."
                click.echo(f"  Skipped folder '{folder_id}' from unknown device {short_id}")
                continue

            member_name, team_name = known_devices[device_id]

            # ── Handle karma-join-* handshake folders ─────────────────
            # Handshake folders are just signals — parse for username
            # discovery (done in pre-scan above), then dismiss.
            if folder_id.startswith("karma-join-"):
                try:
                    st.dismiss_pending_folder(folder_id, device_id)
                except Exception:
                    pass
                click.echo(
                    f"  Dismissed handshake '{folder_id}' from {member_name} (signal processed)"
                )
                continue

            # ── Handle karma-out-* folders ────────────────────────────
            if not folder_id.startswith("karma-out-"):
                continue

            # Check if this is OUR outbox being offered back (create sendonly)
            own_prefix = f"karma-out-{own_user_id}-"
            if folder_id.startswith(own_prefix):
                suffix = folder_id[len(own_prefix):]
                if not SAFE_PATH_PART.match(suffix):
                    click.echo(f"  Skipped own outbox '{folder_id}' — unsafe suffix: {suffix!r}")
                    continue
                outbox_path = str(KARMA_BASE / "remote-sessions" / own_user_id / suffix)
                Path(outbox_path).mkdir(parents=True, exist_ok=True)
                outbox_devices = [device_id]
                if own_device_id:
                    outbox_devices.append(own_device_id)

                existing = st.find_folder_by_path(outbox_path)
                if existing:
                    if existing["id"] == folder_id:
                        click.echo(f"  Already have outbox '{folder_id}'")
                        continue
                    st.remove_folder(existing["id"])

                st.add_folder(folder_id, outbox_path, outbox_devices, folder_type="sendonly")
                existing_folder_ids.add(folder_id)
                click.echo(
                    f"  Created outbox '{folder_id}' -> {outbox_path} (send-only)"
                )
                accepted += 1

                # Auto-register project if not already tracked
                try:
                    from db.sync_queries import upsert_team_project

                    upsert_team_project(conn, team_name, suffix, path=None)
                except Exception:
                    pass

                # Try to resolve to the correct local project
                try:
                    resolved = _resolve_local_project(conn, team_name, suffix)
                    if resolved:
                        r_encoded, r_path, r_git_id = resolved
                        if r_encoded != suffix:
                            correct_outbox = str(
                                KARMA_BASE / "remote-sessions" / own_user_id / r_encoded
                            )
                            Path(correct_outbox).mkdir(parents=True, exist_ok=True)
                            click.echo(
                                f"  Resolved project '{suffix}' -> '{r_encoded}'"
                            )
                except Exception:
                    pass
                continue

            # ── Someone else's outbox → create receiveonly inbox ───────
            # Use smart disambiguation to extract sender and suffix
            parsed = _extract_username_from_karma_folder(
                folder_id, "karma-out-", known_names,
            )
            if not parsed:
                parsed = _parse_folder_id(folder_id)
            if not parsed:
                click.echo(
                    f"  Skipped folder '{folder_id}' from {member_name} "
                    f"(could not parse folder ID)"
                )
                continue

            sender_name, suffix = parsed

            # Validate path components from remote data
            if not SAFE_PATH_PART.match(sender_name) or not SAFE_PATH_PART.match(suffix):
                click.echo(
                    f"  Skipped folder '{folder_id}' — unsafe path components "
                    f"(sender={sender_name!r}, suffix={suffix!r})"
                )
                continue
            if ".." in sender_name or ".." in suffix:
                click.echo(f"  Skipped folder '{folder_id}' — path traversal attempt")
                continue

            # Try to match against a known local project
            projects = list_team_projects(conn, team_name)
            matched_project = None
            for proj in projects:
                git_id = proj.get("git_identity")
                if git_id:
                    proj_suffix = git_id.replace("/", "-")
                elif proj["path"]:
                    proj_suffix = Path(proj["path"]).name
                else:
                    proj_suffix = proj["project_encoded_name"]
                if proj_suffix == suffix:
                    matched_project = proj
                    break

            if matched_project:
                encoded = matched_project["project_encoded_name"]
                inbox_path = str(KARMA_BASE / "remote-sessions" / sender_name / encoded)
            else:
                # Auto-create a sync_team_projects record
                try:
                    from db.sync_queries import upsert_team_project

                    upsert_team_project(conn, team_name, suffix, path=None)
                    click.echo(
                        f"  Auto-registered project '{suffix}' in team '{team_name}'"
                    )
                except Exception as e:
                    click.echo(
                        f"  Warning: Could not auto-register project '{suffix}': {e}"
                    )

                # Try to resolve to the correct local project immediately
                resolved = _resolve_local_project(conn, team_name, suffix)
                if resolved:
                    r_encoded, r_path, r_git_id = resolved
                    inbox_path = str(KARMA_BASE / "remote-sessions" / sender_name / r_encoded)
                    click.echo(
                        f"  Resolved project '{suffix}' -> '{r_encoded}'"
                    )
                else:
                    inbox_path = str(KARMA_BASE / "remote-sessions" / sender_name / suffix)

            existing = st.find_folder_by_path(inbox_path)
            if existing:
                existing_id = existing["id"]
                if existing_id == folder_id:
                    click.echo(f"  Already accepted '{folder_id}' from {sender_name}")
                    continue
                click.echo(f"  Replacing empty inbox '{existing_id}' with offered '{folder_id}'")
                st.remove_folder(existing_id)

            inbox_devices = [device_id]
            if own_device_id:
                inbox_devices.append(own_device_id)
            Path(inbox_path).mkdir(parents=True, exist_ok=True)
            st.add_folder(folder_id, inbox_path, inbox_devices, folder_type="receiveonly")
            existing_folder_ids.add(folder_id)

            click.echo(
                f"  Accepted '{folder_id}' from {sender_name} "
                f"-> {inbox_path} (receive-only)"
            )
            accepted += 1

    return accepted


def require_config() -> SyncConfig:
    """Load config or exit with helpful message."""
    try:
        config = SyncConfig.load()
    except RuntimeError as e:
        raise click.ClickException(str(e))
    if config is None:
        raise click.ClickException("Not initialized. Run: karma init")
    return config


@click.group()
@click.version_option(package_name="claude-karma-cli")
def cli():
    """Claude Karma - Syncthing session sync for distributed teams."""
    pass


# --- init ---


@cli.command()
@click.option("--user-id", prompt="Your user ID (e.g., your name)", help="Identity for syncing")
def init(user_id: str):
    """Initialize Karma sync on this machine."""
    existing = SyncConfig.load()
    if existing:
        click.echo(f"Already initialized as '{existing.user_id}' on '{existing.machine_id}'.")
        if not click.confirm("Reinitialize?"):
            return

    if not _SAFE_NAME.match(user_id):
        raise click.ClickException("User ID must be alphanumeric, dash, or underscore only.")

    from karma.syncthing import SyncthingClient, read_local_api_key

    api_key = read_local_api_key()
    if api_key:
        st = SyncthingClient(api_key=api_key)
        if st.is_running():
            device_id = st.get_device_id()
            syncthing_settings = SyncthingSettings(
                api_url="http://127.0.0.1:8384",
                api_key=api_key,
                device_id=device_id,
            )
            config = SyncConfig(user_id=user_id, syncthing=syncthing_settings)
            config.save()
            click.echo(f"Initialized as '{user_id}' on '{config.machine_id}'.")
            click.echo(f"Your Syncthing Device ID: {device_id}")
            click.echo("Share this Device ID with your team leader.")
            return

    config = SyncConfig(user_id=user_id)
    config.save()
    click.echo(f"Initialized as '{user_id}' on '{config.machine_id}'.")
    click.echo(f"Config saved to {SYNC_CONFIG_PATH}")
    click.echo("\nSyncthing not detected. Start Syncthing and re-run 'karma init' to auto-configure.")
    click.echo("\nNext steps:")
    click.echo("  1. Start Syncthing")
    click.echo("  2. Create a team: karma team create <name>")
    click.echo("  3. Add a project: karma project add <name> --path /path --team <team>")


# --- project ---


@cli.group()
def project():
    """Manage projects for syncing."""
    pass


@project.command("add")
@click.argument("name")
@click.option("--path", required=True, help="Absolute path to the project directory")
@click.option("--team", "team_name", required=True, help="Team to add project to")
def project_add(name: str, path: str, team_name: str):
    """Add a project for syncing."""
    if not _SAFE_NAME.match(name):
        raise click.ClickException("Project name must be alphanumeric, dash, or underscore only.")

    if not Path(path).is_absolute():
        raise click.ClickException("Project path must be absolute (e.g., /Users/alice/my-project).")

    config = require_config()
    conn = _get_db()

    from db.sync_queries import get_team, add_team_project, list_members, log_event

    team = get_team(conn, team_name)
    if not team:
        raise click.ClickException(f"Team '{team_name}' not found.")

    encoded = encode_project_path(path)
    git_identity = detect_git_identity(path)

    # Ensure project exists in projects table (FK requirement), include git_identity
    conn.execute(
        "INSERT OR IGNORE INTO projects (encoded_name, project_path, git_identity) VALUES (?, ?, ?)",
        (encoded, path, git_identity),
    )
    if git_identity:
        conn.execute(
            "UPDATE projects SET git_identity = ? WHERE encoded_name = ? AND git_identity IS NULL",
            (git_identity, encoded),
        )
    conn.commit()

    if git_identity:
        click.echo(f"Detected git identity: {git_identity}")

    try:
        add_team_project(conn, team_name, encoded, path, git_identity=git_identity)
    except Exception as e:
        if "UNIQUE constraint" in str(e):
            raise click.ClickException(f"Project already exists in team '{team_name}'.")
        raise

    log_event(conn, "project_added", team_name=team_name, project_encoded_name=encoded)

    # Compute folder suffix: prefer git_identity, fall back to CLI name
    proj_suffix = git_identity.replace("/", "-") if git_identity else name

    # Auto-create shared folders if team has Syncthing members
    members = list_members(conn, team_name)
    if members:
        try:
            from karma.syncthing import SyncthingClient, read_local_api_key

            api_key = config.syncthing.api_key or read_local_api_key()
            st = SyncthingClient(api_key=api_key)
            if st.is_running():
                outbox_path = str(KARMA_BASE / "remote-sessions" / config.user_id / encoded)
                outbox_id = f"karma-out-{config.user_id}-{proj_suffix}"
                device_ids = []
                if config.syncthing.device_id:
                    device_ids.append(config.syncthing.device_id)
                for m in members:
                    if m["device_id"]:
                        device_ids.append(m["device_id"])
                Path(outbox_path).mkdir(parents=True, exist_ok=True)
                st.add_folder(outbox_id, outbox_path, device_ids, folder_type="sendonly")
                click.echo(f"Outbox '{outbox_id}' -> {outbox_path} (send-only)")

                for m in members:
                    if m["device_id"]:
                        inbox_path = str(KARMA_BASE / "remote-sessions" / m["name"] / encoded)
                        inbox_id = f"karma-out-{m['name']}-{proj_suffix}"
                        inbox_devices = [m["device_id"]]
                        if config.syncthing.device_id:
                            inbox_devices.append(config.syncthing.device_id)
                        Path(inbox_path).mkdir(parents=True, exist_ok=True)
                        st.add_folder(inbox_id, inbox_path, inbox_devices, folder_type="receiveonly")
                        click.echo(f"Inbox '{inbox_id}' -> {inbox_path} (receive-only)")
        except Exception as e:
            click.echo(f"Warning: Could not auto-share folder: {e}")

    click.echo(f"Added project '{name}' ({path})")
    click.echo(f"Encoded as: {encoded}")


@project.command("list")
def project_list():
    """List configured projects."""
    require_config()
    conn = _get_db()

    from db.sync_queries import list_teams, list_team_projects

    teams = list_teams(conn)
    if not teams:
        click.echo("No projects configured. Run: karma project add <name> --path /path --team <team>")
        return

    for t in teams:
        projects = list_team_projects(conn, t["name"])
        for proj in projects:
            proj_path = proj["path"] or proj["project_encoded_name"]
            proj_short = Path(proj_path).name if proj["path"] else proj["project_encoded_name"]
            click.echo(f"  {proj_short}: {proj_path} [team: {t['name']}]")


@project.command("remove")
@click.argument("name")
@click.option("--team", "team_name", required=True, help="Team to remove project from")
def project_remove(name: str, team_name: str):
    """Remove a project from syncing."""
    require_config()
    conn = _get_db()

    from db.sync_queries import get_team, list_team_projects, remove_team_project, log_event

    team = get_team(conn, team_name)
    if not team:
        raise click.ClickException(f"Team '{team_name}' not found.")

    # Find the project by short name (derived from path) or encoded name
    projects = list_team_projects(conn, team_name)
    target = None
    for proj in projects:
        proj_short = Path(proj["path"]).name if proj["path"] else proj["project_encoded_name"]
        if proj_short == name or proj["project_encoded_name"] == name:
            target = proj
            break

    if not target:
        raise click.ClickException(f"Project '{name}' not found in team '{team_name}'.")

    log_event(conn, "project_removed", team_name=team_name, project_encoded_name=target["project_encoded_name"])
    remove_team_project(conn, team_name, target["project_encoded_name"])
    click.echo(f"Removed project '{name}'.")


# --- ls ---


@cli.command("ls")
def list_remote():
    """List available remote sessions."""
    remote_dir = KARMA_BASE / "remote-sessions"
    if not remote_dir.is_dir():
        click.echo("No remote sessions. Run: karma pull")
        return

    for user_dir in sorted(remote_dir.iterdir()):
        if not user_dir.is_dir():
            continue
        click.echo(f"\n{user_dir.name}:")
        for project_dir in sorted(user_dir.iterdir()):
            if not project_dir.is_dir():
                continue
            manifest_path = project_dir / "manifest.json"
            if manifest_path.exists():
                try:
                    manifest = json.loads(manifest_path.read_text())
                    click.echo(
                        f"  {project_dir.name}: "
                        f"{manifest.get('session_count', '?')} sessions "
                        f"(synced {manifest.get('synced_at', '?')})"
                    )
                except (json.JSONDecodeError, OSError):
                    click.echo(f"  {project_dir.name}: (corrupt manifest)")
            else:
                click.echo(f"  {project_dir.name}: (no manifest)")


# --- accept ---


@cli.command()
def accept():
    """Accept pending Syncthing folder offers from known team members.

    Only accepts folders from devices registered in your team config,
    and only folders with a 'karma-' prefix. Unknown devices and
    non-karma folders are logged and skipped.
    """
    from karma.syncthing import SyncthingClient, read_local_api_key

    config = require_config()
    conn = _get_db()
    api_key = config.syncthing.api_key if config.syncthing else read_local_api_key()
    if not api_key:
        raise click.ClickException(
            "No Syncthing API key found. Run: karma init"
        )

    st = SyncthingClient(api_key=api_key)
    if not st.is_running():
        raise click.ClickException("Syncthing is not running. Start Syncthing first.")

    click.echo("Checking for pending folder offers...")
    n = _accept_pending_folders(st, config, conn)
    if n == 0:
        click.echo("No pending folders to accept.")
    else:
        click.echo(f"\nDone. Accepted {n} folder(s).")


# --- watch ---


@cli.command()
@click.option("--team", "team_name", required=True, help="Team to watch for")
def watch(team_name: str):
    """Watch project sessions and auto-package for Syncthing sync."""
    from karma.watcher import SessionWatcher
    from karma.packager import SessionPackager

    config = require_config()
    conn = _get_db()

    from db.sync_queries import get_team, list_team_projects, log_event

    team = get_team(conn, team_name)
    if not team:
        raise click.ClickException(
            f"Team '{team_name}' not found. Run: karma team create {team_name}"
        )

    projects = list_team_projects(conn, team_name)
    if not projects:
        raise click.ClickException(
            f"No projects in team '{team_name}'. Run: karma project add <name> --path /path --team {team_name}"
        )

    # Auto-accept pending folder offers from known teammates before starting
    try:
        from karma.syncthing import SyncthingClient, read_local_api_key

        api_key = config.syncthing.api_key if config.syncthing else read_local_api_key()
        if api_key:
            st = SyncthingClient(api_key=api_key)
            if st.is_running():
                n = _accept_pending_folders(st, config, conn)
                if n:
                    click.echo(f"Accepted {n} pending folder(s) from known teammates.\n")
    except Exception as e:
        click.echo(f"Warning: Could not check pending folders: {e}\n")

    click.echo(f"Watching {len(projects)} project(s) for team '{team_name}'...")
    click.echo("Press Ctrl+C to stop.\n")

    from karma.worktree_discovery import find_all_worktree_dirs

    watchers = []
    projects_dir = Path.home() / ".claude" / "projects"

    # Re-read projects after accept (records may have been updated by resolution)
    projects = list_team_projects(conn, team_name)

    for proj in projects:
        encoded = proj["project_encoded_name"]
        proj_path = proj["path"] or ""
        proj_short = Path(proj_path).name if proj_path else encoded

        claude_dir = projects_dir / encoded
        if not claude_dir.is_dir():
            # Try to resolve the DB record to the correct local project
            try:
                resolved = _resolve_local_project(conn, team_name, encoded)
                if resolved:
                    encoded, proj_path, _ = resolved
                    proj_short = Path(proj_path).name if proj_path else encoded
                    claude_dir = projects_dir / encoded
                    click.echo(f"  Resolved project -> '{encoded}'")
            except Exception:
                pass

            if not claude_dir.is_dir():
                click.echo(f"  Skipping '{proj_short}': Claude dir not found ({claude_dir})")
                continue

        # Discover worktree dirs for this project
        wt_dirs = find_all_worktree_dirs(encoded, proj_path, projects_dir)
        if wt_dirs:
            click.echo(f"  Found {len(wt_dirs)} worktree dir(s) for '{proj_short}'")

        outbox = KARMA_BASE / "remote-sessions" / config.user_id / encoded

        def make_package_fn(cd=claude_dir, ob=outbox, pn=proj_short, en=encoded, pp=proj_path):
            def package():
                current_wt_dirs = find_all_worktree_dirs(en, pp, projects_dir)
                packager = SessionPackager(
                    project_dir=cd,
                    user_id=config.user_id,
                    machine_id=config.machine_id,
                    project_path=pp,
                    extra_dirs=current_wt_dirs,
                )
                ob.mkdir(parents=True, exist_ok=True)
                packager.package(staging_dir=ob)
                click.echo(f"  Packaged '{pn}' -> {ob} ({len(current_wt_dirs)} worktrees)")

            return package

        package_fn = make_package_fn()

        watcher = SessionWatcher(
            watch_dir=claude_dir,
            package_fn=package_fn,
        )
        watcher.start()
        watchers.append(watcher)
        click.echo(f"  Watching: {proj_short} ({claude_dir})")

        # Also watch each worktree dir
        for wt_dir in wt_dirs:
            wt_watcher = SessionWatcher(
                watch_dir=wt_dir,
                package_fn=package_fn,
            )
            wt_watcher.start()
            watchers.append(wt_watcher)
            if "--claude-worktrees-" in wt_dir.name:
                wt_name = wt_dir.name.split("--claude-worktrees-")[-1]
            elif "-claude-worktrees-" in wt_dir.name:
                parts = wt_dir.name.split("-claude-worktrees-")
                wt_name = parts[-1] if parts else wt_dir.name
            else:
                wt_name = wt_dir.name
            click.echo(f"  Watching worktree: {wt_name} ({wt_dir})")

    log_event(conn, "watcher_started", team_name=team_name)

    try:
        import time

        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        click.echo("\nStopping watchers...")
    finally:
        for w in watchers:
            w.stop()
        log_event(conn, "watcher_stopped", team_name=team_name)
        click.echo("Done.")


# --- status ---


@cli.command()
def status():
    """Show sync status for all teams."""
    from karma.worktree_discovery import find_all_worktree_dirs

    config = require_config()
    conn = _get_db()

    from db.sync_queries import list_teams, list_team_projects, list_members, query_events

    click.echo(f"User: {config.user_id} ({config.machine_id})")

    teams = list_teams(conn)
    if not teams:
        click.echo("No teams configured.")
        return

    projects_dir = Path.home() / ".claude" / "projects"

    for t in teams:
        team_name = t["name"]
        click.echo(f"\n{team_name}:")

        projects = list_team_projects(conn, team_name)
        if not projects:
            click.echo("  No projects")

        for proj in projects:
            encoded = proj["project_encoded_name"]
            proj_path = proj["path"] or encoded
            proj_short = Path(proj_path).name if proj["path"] else encoded

            claude_dir = projects_dir / encoded

            # Count local sessions
            local_count = 0
            if claude_dir.is_dir():
                local_count = sum(
                    1 for f in claude_dir.glob("*.jsonl")
                    if not f.name.startswith("agent-") and f.stat().st_size > 0
                )

            # Count worktree sessions
            wt_dirs = find_all_worktree_dirs(encoded, proj_path, projects_dir)
            wt_count = 0
            for wd in wt_dirs:
                wt_count += sum(
                    1 for f in wd.glob("*.jsonl")
                    if not f.name.startswith("agent-") and f.stat().st_size > 0
                )

            # Count packaged sessions
            outbox = KARMA_BASE / "remote-sessions" / config.user_id / encoded / "sessions"
            packaged_count = 0
            if outbox.is_dir():
                packaged_count = sum(1 for f in outbox.glob("*.jsonl") if not f.name.startswith("agent-"))

            total_local = local_count + wt_count
            gap = total_local - packaged_count

            click.echo(f"  {proj_short}: {proj_path}")
            click.echo(f"    Local: {local_count} sessions + {wt_count} worktree ({len(wt_dirs)} dirs) = {total_local}")
            click.echo(f"    Packaged: {packaged_count}  {'(up to date)' if gap <= 0 else f'({gap} behind)'}")

        members = list_members(conn, team_name)
        if members:
            member_names = [m["name"] for m in members]
            click.echo(f"  Members: {', '.join(member_names)}")

    # Show recent events
    events = query_events(conn, limit=5)
    if events:
        click.echo("\nRecent activity:")
        for ev in events:
            line = f"  [{ev['created_at']}] {ev['event_type']}"
            if ev["team_name"]:
                line += f" ({ev['team_name']})"
            click.echo(line)


# --- team ---


@cli.group()
def team():
    """Manage teams and team members for syncing."""
    pass


@team.command("create")
@click.argument("name")
def team_create(name: str):
    """Create a new team for Syncthing-based session sharing."""
    if not _SAFE_NAME.match(name):
        raise click.ClickException("Team name must be alphanumeric, dash, or underscore only.")

    require_config()
    conn = _get_db()

    from db.sync_queries import create_team, log_event

    try:
        create_team(conn, name)
    except Exception as e:
        if "UNIQUE constraint" in str(e):
            raise click.ClickException(f"Team '{name}' already exists.")
        raise

    log_event(conn, "team_created", team_name=name)
    click.echo(f"Created team '{name}'")


@team.command("leave")
@click.argument("name")
def team_leave(name: str):
    """Leave a team — cleans up Syncthing folders/devices and removes local data."""
    config = require_config()
    conn = _get_db()

    from db.sync_queries import get_team, list_members, list_team_projects, delete_team, log_event

    team_data = get_team(conn, name)
    if not team_data:
        raise click.ClickException(f"Team '{name}' not found.")

    # Clean up Syncthing state before deleting DB records
    folders_removed = 0
    devices_removed = 0
    try:
        from karma.syncthing import SyncthingClient, read_local_api_key

        api_key = config.syncthing.api_key or read_local_api_key()
        st = SyncthingClient(api_key=api_key)
        if st.is_running():
            members = list_members(conn, name)
            projects = list_team_projects(conn, name)

            # Compute project suffixes
            from karma.sync import detect_git_identity
            proj_suffixes = set()
            for proj in projects:
                git_id = proj.get("git_identity")
                suffix = git_id.replace("/", "-") if git_id else proj["project_encoded_name"]
                proj_suffixes.add(suffix)

            # Collect all relevant member names (including self)
            member_names = {m["name"] for m in members}
            member_names.add(config.user_id)

            # Remove matching karma folders
            for folder in st.get_folders():
                folder_id = folder.get("id", "")
                if folder_id.startswith("karma-out-"):
                    parts = folder_id[len("karma-out-"):].split("-", 1)
                    if len(parts) == 2:
                        # Check all possible name lengths against known members
                        rest = folder_id[len("karma-out-"):]
                        matched = False
                        for mname in sorted(member_names, key=len, reverse=True):
                            if rest.startswith(mname + "-"):
                                remainder = rest[len(mname) + 1:]
                                if remainder in proj_suffixes:
                                    st.remove_folder(folder_id)
                                    folders_removed += 1
                                    matched = True
                                    break
                        if not matched and parts[1] in proj_suffixes:
                            st.remove_folder(folder_id)
                            folders_removed += 1
                elif folder_id.startswith("karma-join-") and folder_id.endswith(f"-{name}"):
                    st.remove_folder(folder_id)
                    folders_removed += 1

            # Remove team member devices (if not used by other teams)
            my_device_id = config.syncthing.device_id
            for m in members:
                did = m["device_id"]
                if did == my_device_id:
                    continue
                other = conn.execute(
                    "SELECT COUNT(*) FROM sync_members WHERE device_id = ? AND team_name != ?",
                    (did, name),
                ).fetchone()[0]
                if other == 0:
                    try:
                        st.remove_device(did)
                        devices_removed += 1
                    except Exception:
                        pass
    except Exception as e:
        click.echo(f"Warning: Syncthing cleanup failed: {e}", err=True)

    log_event(conn, "team_left", team_name=name)
    delete_team(conn, name)
    click.echo(f"Left team '{name}'. Removed {folders_removed} folders, {devices_removed} devices.")


@team.command("add")
@click.argument("name")
@click.argument("identifier")
@click.option("--team", "team_name", required=True, help="Team to add member to")
def team_add(name: str, identifier: str, team_name: str):
    """Add a team member by their Syncthing device ID."""
    if not _SAFE_NAME.match(name):
        raise click.ClickException("Team member name must be alphanumeric, dash, or underscore only.")

    config = require_config()
    conn = _get_db()

    from db.sync_queries import get_team, add_member, log_event

    team_data = get_team(conn, team_name)
    if not team_data:
        raise click.ClickException(f"Team '{team_name}' not found.")

    try:
        add_member(conn, team_name, name, device_id=identifier)
    except Exception as e:
        if "UNIQUE constraint" in str(e):
            raise click.ClickException(f"Member '{name}' already exists in team '{team_name}'.")
        raise

    log_event(conn, "member_added", team_name=team_name, member_name=name)

    # Auto-pair device in Syncthing
    try:
        from karma.syncthing import SyncthingClient, read_local_api_key

        api_key = config.syncthing.api_key or read_local_api_key()
        st = SyncthingClient(api_key=api_key)
        if st.is_running():
            st.add_device(identifier, name)
            click.echo(f"Paired Syncthing device '{name}' ({identifier[:7]}...)")

            _auto_share_folders(st, config, conn, team_name, identifier)

            n = _accept_pending_folders(st, config, conn)
            if n:
                click.echo(f"Accepted {n} pending folder(s) from known teammates.")
        else:
            click.echo("Warning: Syncthing not running — device saved but not paired yet.")
    except Exception as e:
        click.echo(f"Warning: Could not auto-pair device: {e}")
        click.echo("You can pair manually in Syncthing UI (http://127.0.0.1:8384)")

    click.echo(f"Added team member '{name}' to team '{team_name}'")


@team.command("list")
def team_list():
    """List teams and their members."""
    require_config()
    conn = _get_db()

    from db.sync_queries import list_teams, list_members

    teams = list_teams(conn)
    if not teams:
        click.echo("No teams. Run: karma team create <name>")
        return

    for t in teams:
        click.echo(f"\n  {t['name']}:")
        members = list_members(conn, t["name"])
        if members:
            for m in members:
                id_info = m["device_id"] or "no-id"
                click.echo(f"    {m['name']}: {id_info}")
        else:
            click.echo("    (no members)")


@team.command("remove")
@click.argument("name")
@click.option("--team", "team_name", required=True, help="Team to remove member from")
def team_remove(name: str, team_name: str):
    """Remove a team member."""
    require_config()
    conn = _get_db()

    from db.sync_queries import get_team, list_members, remove_member, log_event

    team_data = get_team(conn, team_name)
    if not team_data:
        raise click.ClickException(f"Team '{team_name}' not found.")

    members = list_members(conn, team_name)
    member = next((m for m in members if m["name"] == name), None)
    if member is None:
        raise click.ClickException(f"Member '{name}' not found in team '{team_name}'.")

    log_event(conn, "member_removed", team_name=team_name, member_name=name)
    remove_member(conn, team_name, member["device_id"])
    click.echo(f"Removed team member '{name}'.")


if __name__ == "__main__":
    cli()
