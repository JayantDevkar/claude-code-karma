"""Karma CLI entry point."""

import re
import sys
from pathlib import Path

import click

from karma.config import SyncConfig, SyncthingSettings, SYNC_CONFIG_PATH, KARMA_BASE
from karma.folder_ids import (
    build_handshake_id,
    build_outbox_id,
    compute_proj_suffix,
    is_outbox_folder,
    parse_outbox_id,
    OUTBOX_PREFIX,
)
from karma.pending import accept_pending_folders
from karma.project_resolution import resolve_local_project, auto_share_folders
from karma.sync import encode_project_path, detect_git_identity

# Add API to path for sync_queries
_API_PATH = Path(__file__).parent.parent.parent / "api"
if str(_API_PATH) not in sys.path:
    sys.path.insert(0, str(_API_PATH))

_SAFE_NAME = re.compile(r"^[a-zA-Z0-9_\-]+$")


def _get_db():
    """Get a SQLite connection with schema applied."""
    from karma.db import get_connection

    return get_connection()


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
                outbox_path = str(KARMA_BASE / "remote-sessions" / config.member_tag / encoded)
                outbox_id = build_outbox_id(config.member_tag, proj_suffix)
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
                        member_tag = m.get("member_tag") or m["name"]
                        inbox_path = str(KARMA_BASE / "remote-sessions" / member_tag / encoded)
                        inbox_id = build_outbox_id(member_tag, proj_suffix)
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
    n = accept_pending_folders(st, config, conn)
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
                # auto_only=True: only handshake + own outbox at startup.
                # Other people's project shares require explicit acceptance.
                n = accept_pending_folders(st, config, conn, auto_only=True)
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
                resolved = resolve_local_project(conn, team_name, encoded)
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
                    device_id=config.syncthing.device_id if config.syncthing else None,
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
                parsed_out = parse_outbox_id(folder_id)
                if parsed_out:
                    uname, suffix = parsed_out
                    if uname in member_names and suffix in proj_suffixes:
                        st.remove_folder(folder_id)
                        folders_removed += 1
                elif is_outbox_folder(folder_id):
                    pass  # Unparseable outbox — skip
                else:
                    from karma.folder_ids import parse_handshake_id
                    parsed_hs = parse_handshake_id(folder_id)
                    if parsed_hs and parsed_hs[1] == name:
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

            auto_share_folders(st, config, conn, team_name, identifier)

            # auto_only=True: during join, only process handshake + own outbox.
            # Project shares from the new member require explicit acceptance.
            n = accept_pending_folders(st, config, conn, auto_only=True)
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
@click.option("--keep-data", is_flag=True, default=False,
              help="Keep synced session files and DB rows (only remove from team)")
def team_remove(name: str, team_name: str, keep_data: bool):
    """Remove a team member — cleans up Syncthing folders, devices, and session data."""
    config = require_config()
    conn = _get_db()

    from db.sync_queries import (
        get_team, list_members, list_team_projects, remove_member, log_event,
        cleanup_data_for_member,
    )

    team_data = get_team(conn, team_name)
    if not team_data:
        raise click.ClickException(f"Team '{team_name}' not found.")

    members = list_members(conn, team_name)
    member = next((m for m in members if m["name"] == name), None)
    if member is None:
        raise click.ClickException(f"Member '{name}' not found in team '{team_name}'.")

    device_id = member["device_id"]

    # Syncthing cleanup: remove member's folders, un-share our outbox, remove device
    folders_removed = 0
    devices_removed = 0
    devices_unshared = 0
    try:
        from karma.syncthing import SyncthingClient, read_local_api_key
        from pathlib import Path as _Path

        api_key = config.syncthing.api_key or read_local_api_key()
        st = SyncthingClient(api_key=api_key)
        if st.is_running():
            projects = list_team_projects(conn, team_name)
            proj_suffixes = set()
            for proj in projects:
                git_id = proj.get("git_identity")
                path = proj.get("path")
                encoded = proj["project_encoded_name"]
                if git_id:
                    suffix = git_id.replace("/", "-")
                elif path:
                    suffix = _Path(path).name
                else:
                    suffix = encoded
                proj_suffixes.add(suffix)

            my_user_id = config.user_id

            for folder in st.get_folders():
                folder_id = folder.get("id", "")
                parsed_out = parse_outbox_id(folder_id)
                if parsed_out:
                    uname, suffix = parsed_out
                    if suffix in proj_suffixes:
                        if uname == my_user_id:
                            # Our outbox — un-share from kicked member's device
                            if st.remove_device_from_folder(folder_id, device_id):
                                devices_unshared += 1
                        elif uname == name:
                            # Member's inbox on our disk — remove entirely
                            st.remove_folder(folder_id)
                            folders_removed += 1
                elif folder_id == build_handshake_id(name, team_name):
                    st.remove_folder(folder_id)
                    folders_removed += 1

            # Remove device if not in other teams
            my_device_id = config.syncthing.device_id
            if device_id and device_id != my_device_id:
                other = conn.execute(
                    "SELECT COUNT(*) FROM sync_members WHERE device_id = ? AND team_name != ?",
                    (device_id, team_name),
                ).fetchone()[0]
                if other == 0:
                    try:
                        st.remove_device(device_id)
                        devices_removed += 1
                    except Exception:
                        pass
        else:
            click.echo("Warning: Syncthing not running — skipping Syncthing cleanup.", err=True)
    except Exception as e:
        click.echo(f"Warning: Syncthing cleanup failed: {e}", err=True)

    # Filesystem + DB session cleanup
    dirs_removed = 0
    sessions_deleted = 0
    if not keep_data:
        try:
            from karma.config import KARMA_BASE

            result = cleanup_data_for_member(conn, team_name, name, KARMA_BASE)
            dirs_removed = result["dirs_removed"]
            sessions_deleted = result["sessions_deleted"]
        except Exception as e:
            click.echo(f"Warning: Data cleanup failed: {e}", err=True)

    remove_member(conn, team_name, device_id)
    log_event(conn, "member_removed", team_name=team_name, member_name=name,
              detail={"folders_removed": folders_removed, "devices_removed": devices_removed,
                      "devices_unshared": devices_unshared,
                      "dirs_removed": dirs_removed, "sessions_deleted": sessions_deleted})
    click.echo(
        f"Removed '{name}' from team '{team_name}'. "
        f"Syncthing: {folders_removed} folders, {devices_removed} devices, "
        f"{devices_unshared} outboxes unshared. "
        f"Data: {dirs_removed} dirs, {sessions_deleted} sessions cleaned."
    )


if __name__ == "__main__":
    cli()
