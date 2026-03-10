"""Pending folder acceptance logic for Karma sync.

Handles accepting pending Syncthing folder offers from known team members.
"""

import sys
from pathlib import Path
from typing import Optional

import click

from karma.config import KARMA_BASE

# Add API to path for sync_queries / file_validator
_API_PATH = Path(__file__).parent.parent.parent / "api"
if str(_API_PATH) not in sys.path:
    sys.path.insert(0, str(_API_PATH))

from services.file_validator import SAFE_PATH_PART  # noqa: E402
from services.folder_id import parse_karma_folder_id  # noqa: E402


def _handle_join_folder(st, folder_id: str, device_id: str, member_name: str) -> None:
    """Dismiss a karma-join-* handshake folder (signal already processed in pre-scan)."""
    try:
        st.dismiss_pending_folder(folder_id, device_id)
    except Exception:
        pass
    click.echo(
        f"  Dismissed handshake '{folder_id}' from {member_name} (signal processed)"
    )


def _handle_own_outbox(
    st,
    config,
    conn,
    folder_id: str,
    own_prefix: str,
    device_id: str,
    own_device_id: Optional[str],
    existing_folder_ids: set,
    team_name: str,
) -> int:
    """Accept our own outbox being offered back (create sendonly folder).

    Returns 1 if accepted, 0 otherwise.
    """
    from karma.project_resolution import resolve_local_project

    suffix = folder_id[len(own_prefix):]
    if not SAFE_PATH_PART.match(suffix):
        click.echo(f"  Skipped own outbox '{folder_id}' — unsafe suffix: {suffix!r}")
        return 0

    # Resolve suffix to the correct local project BEFORE creating the Syncthing
    # folder. The suffix is git-identity-based but the packager writes to the
    # Claude-encoded path. Using the suffix as the folder path would cause a
    # mismatch — Syncthing watches one dir, the packager writes to another.
    outbox_subdir = suffix  # fallback if resolution fails
    resolved_path = None
    resolved_git_id = None
    try:
        resolved = resolve_local_project(conn, team_name, suffix)
        if resolved:
            r_encoded, r_path, r_git_id = resolved
            outbox_subdir = r_encoded
            resolved_path = r_path
            resolved_git_id = r_git_id
            if r_encoded != suffix:
                click.echo(f"  Resolved project '{suffix}' -> '{r_encoded}'")
    except Exception as e:
        click.echo(f"  Warning: project resolution failed for '{suffix}': {e}")

    own_user_id = config.user_id
    outbox_path = str(KARMA_BASE / "remote-sessions" / own_user_id / outbox_subdir)
    Path(outbox_path).mkdir(parents=True, exist_ok=True)
    outbox_devices = [device_id]
    if own_device_id:
        outbox_devices.append(own_device_id)

    existing = st.find_folder_by_path(outbox_path)
    if existing:
        if existing["id"] == folder_id:
            click.echo(f"  Already have outbox '{folder_id}'")
            return 0
        st.remove_folder(existing["id"])

    st.add_folder(folder_id, outbox_path, outbox_devices, folder_type="sendonly")
    existing_folder_ids.add(folder_id)
    click.echo(f"  Created outbox '{folder_id}' -> {outbox_path} (send-only)")

    # Auto-register project if not already tracked. resolve_local_project
    # already upserts when it succeeds, but we still need a record for the
    # fallback case. Pass git_identity when available so future resolution
    # lookups (find_project_by_git_suffix) can match this record.
    try:
        from db.sync_queries import upsert_team_project

        upsert_team_project(
            conn, team_name, outbox_subdir,
            path=resolved_path,
            git_identity=resolved_git_id,
        )
    except Exception as e:
        click.echo(f"  Warning: failed to register project '{outbox_subdir}': {e}")

    return 1


def _handle_peer_outbox(
    st,
    config,
    conn,
    folder_id: str,
    device_id: str,
    own_device_id: Optional[str],
    member_name: str,
    team_name: str,
    known_names: set,
    existing_folder_ids: set,
) -> int:
    """Accept someone else's outbox as a receiveonly inbox folder.

    Returns 1 if accepted, 0 otherwise.
    """
    from karma.project_resolution import resolve_local_project

    # Use smart disambiguation to extract sender and suffix
    parsed = parse_karma_folder_id(folder_id, known_names=known_names)
    if not parsed:
        click.echo(
            f"  Skipped folder '{folder_id}' from {member_name} "
            f"(could not parse folder ID)"
        )
        return 0

    sender_name, suffix = parsed

    # Validate path components from remote data
    if not SAFE_PATH_PART.match(sender_name) or not SAFE_PATH_PART.match(suffix):
        click.echo(
            f"  Skipped folder '{folder_id}' — unsafe path components "
            f"(sender={sender_name!r}, suffix={suffix!r})"
        )
        return 0
    if ".." in sender_name or ".." in suffix:
        click.echo(f"  Skipped folder '{folder_id}' — path traversal attempt")
        return 0

    # Try to match against a known local project
    from db.sync_queries import list_team_projects

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
            click.echo(f"  Auto-registered project '{suffix}' in team '{team_name}'")
        except Exception as e:
            click.echo(f"  Warning: Could not auto-register project '{suffix}': {e}")

        # Try to resolve to the correct local project immediately
        resolved = resolve_local_project(conn, team_name, suffix)
        if resolved:
            r_encoded, r_path, r_git_id = resolved
            inbox_path = str(KARMA_BASE / "remote-sessions" / sender_name / r_encoded)
            click.echo(f"  Resolved project '{suffix}' -> '{r_encoded}'")
        else:
            inbox_path = str(KARMA_BASE / "remote-sessions" / sender_name / suffix)

    existing = st.find_folder_by_path(inbox_path)
    if existing:
        existing_id = existing["id"]
        if existing_id == folder_id:
            click.echo(f"  Already accepted '{folder_id}' from {sender_name}")
            return 0
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
    return 1


def accept_pending_folders(st, config, conn, *, auto_only=False, only_folder_id=None):
    """Accept pending folder offers from known team members.

    Security policy:
    - Only accepts folders from device IDs registered in sync_members
    - Only accepts folder IDs prefixed with 'karma-'
    - Replaces empty pre-created inbox folders that conflict on the same path

    Handles three folder types:
    - ``karma-join-{user}-{team}`` — handshake folders (dismissed after reading)
    - ``karma-out-{self}-{suffix}`` — own outbox offered back (auto-accept)
    - ``karma-out-{other}-{suffix}`` — other's outbox (requires explicit accept)

    Args:
        auto_only: When True, only process handshake folders and own outbox.
            Skip ``karma-out-{other}`` folders — those require explicit user
            acceptance via the API. Used by the watcher and background polling.
            When False (explicit user action), accept everything.
        only_folder_id: When set, only process this specific folder ID.
            Overrides auto_only (explicit user action for one folder).

    When the joiner's local DB has no ``sync_team_projects`` records (because
    they joined a team rather than creating it), folders are still accepted if
    offered by a known device.  The inbox path is derived from the folder ID
    itself, and a ``sync_team_projects`` record is auto-created so that
    subsequent operations (watcher, status) can find the project.
    """
    from db.sync_queries import get_known_devices, list_teams, upsert_member

    pending = st.get_pending_folders()
    if not pending:
        return 0

    known_devices = get_known_devices(conn)
    accepted = 0
    existing_folder_ids = {f["id"] for f in st.get_folders()}
    own_device_id = config.syncthing.device_id if config.syncthing else None
    own_user_id = config.user_id

    # ── Pre-scan: extract real usernames from karma-join-* folders ────
    # Handshake folders encode the karma user_id, so we use them to build
    # the known_names set for folder ID disambiguation below.
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
                for dev_id in folder_info.get("offeredBy", {}):
                    if dev_id in known_devices:
                        real_usernames[dev_id] = candidate_user
                        # Safety net: correct DB member name if it ever
                        # drifted (e.g. from a prior version's hostname
                        # derivation). No folder cleanup needed — device
                        # acceptance now requires folder matching which
                        # always provides the correct username upfront.
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
        # When accepting a single folder, skip everything else
        if only_folder_id and folder_id != only_folder_id:
            continue

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
            if folder_id.startswith("karma-join-"):
                _handle_join_folder(st, folder_id, device_id, member_name)
                continue

            # ── Handle karma-out-* folders ────────────────────────────
            if not folder_id.startswith("karma-out-"):
                continue

            # Check if this is OUR outbox being offered back (create sendonly).
            # The leader may have used our user_id OR machine_id when creating
            # the folder, so check both.
            own_prefixes = [f"karma-out-{own_user_id}-"]
            if config.machine_id and config.machine_id != own_user_id:
                own_prefixes.append(f"karma-out-{config.machine_id}-")
            own_prefix = next(
                (p for p in own_prefixes if folder_id.startswith(p)), None
            )
            if own_prefix is not None:
                accepted += _handle_own_outbox(
                    st, config, conn, folder_id, own_prefix, device_id,
                    own_device_id, existing_folder_ids, team_name,
                )
                continue

            # ── Someone else's outbox → create receiveonly inbox ───────
            # In auto_only mode, skip other people's outboxes — they require
            # explicit user acceptance (per-folder Accept in the UI).
            # Exception: only_folder_id overrides auto_only (explicit action).
            if auto_only and not only_folder_id:
                continue

            accepted += _handle_peer_outbox(
                st, config, conn, folder_id, device_id, own_device_id,
                member_name, team_name, known_names, existing_folder_ids,
            )

    return accepted


