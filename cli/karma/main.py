"""Karma CLI entry point."""

import json
import re
from pathlib import Path
from typing import Optional

import click

from karma.config import (
    SyncConfig, ProjectConfig, TeamMember, TeamConfig,
    TeamMemberSyncthing, SyncthingSettings, SYNC_CONFIG_PATH, KARMA_BASE,
)
from karma.sync import sync_project, pull_remote_sessions, encode_project_path

_SAFE_NAME = re.compile(r"^[a-zA-Z0-9_\-]+$")


def _auto_share_folders(st, config, team_cfg, teams, team_name, new_device_id):
    """Auto-create Syncthing shared folders for all projects in a team.

    Each user gets their own outbox folder with a unique ID:
      - karma-out-{my_user_id}-{project} (send-only: my sessions → teammates)
      - karma-in-{their_user_id}-{project} (receive-only: their sessions → my machine)

    This prevents Syncthing from merging sessions from different users.
    """
    for proj_name, proj_cfg in team_cfg.projects.items():
        # 1. My outbox: send my sessions to teammates
        outbox_path = str(KARMA_BASE / "remote-sessions" / config.user_id / proj_cfg.encoded_name)
        outbox_id = f"karma-out-{config.user_id}-{proj_name}"
        all_device_ids = [new_device_id]
        if config.syncthing.device_id:
            all_device_ids.append(config.syncthing.device_id)
        for member in team_cfg.syncthing_members.values():
            if member.syncthing_device_id not in all_device_ids:
                all_device_ids.append(member.syncthing_device_id)
        try:
            Path(outbox_path).mkdir(parents=True, exist_ok=True)
            st.add_folder(outbox_id, outbox_path, all_device_ids, folder_type="sendonly")
            click.echo(f"Outbox '{outbox_id}' -> {outbox_path} (send-only)")
        except Exception as e:
            click.echo(f"Warning: Could not create outbox for '{proj_name}': {e}")

        # 2. Inbox for each teammate: receive their sessions
        # Find the member name for the new device ID
        for member_name, member_cfg in team_cfg.syncthing_members.items():
            if member_cfg.syncthing_device_id == new_device_id:
                inbox_path = str(KARMA_BASE / "remote-sessions" / member_name / proj_cfg.encoded_name)
                inbox_id = f"karma-out-{member_name}-{proj_name}"
                inbox_devices = [new_device_id]
                if config.syncthing.device_id:
                    inbox_devices.append(config.syncthing.device_id)
                try:
                    Path(inbox_path).mkdir(parents=True, exist_ok=True)
                    st.add_folder(inbox_id, inbox_path, inbox_devices, folder_type="receiveonly")
                    click.echo(f"Inbox '{inbox_id}' -> {inbox_path} (receive-only)")
                except Exception as e:
                    click.echo(f"Warning: Could not create inbox for '{member_name}/{proj_name}': {e}")


def _accept_pending_folders(st, config):
    """Accept pending folder offers from known team members.

    Security policy:
    - Only accepts folders from device IDs registered in syncthing_members
    - Only accepts folder IDs prefixed with 'karma-'
    - Logs all decisions (accepted, ignored unknown, ignored non-karma)
    - Replaces empty pre-created inbox folders that conflict on the same path

    Returns the number of folders accepted.
    """
    pending = st.get_pending_folders()
    if not pending:
        return 0

    # Build device_id -> (member_name, team_name) lookup
    known_devices: dict[str, tuple[str, str]] = {}
    for team_name, team_cfg in config.teams.items():
        for member_name, member_cfg in team_cfg.syncthing_members.items():
            known_devices[member_cfg.syncthing_device_id] = (member_name, team_name)

    accepted = 0

    # Get existing folder IDs to avoid duplicates
    existing_folder_ids = {f["id"] for f in st.get_folders()}
    own_device_id = config.syncthing.device_id if config.syncthing else None

    for folder_id, folder_info in pending.items():
        # Security: only accept karma-prefixed folders
        if not folder_id.startswith("karma-"):
            click.echo(f"  Skipped non-karma folder offer '{folder_id}' (security policy)")
            continue

        # Skip folders we already have configured (e.g. our own outbox)
        if folder_id in existing_folder_ids:
            # Dismiss the pending offer so it doesn't reappear
            for device_id in folder_info.get("offeredBy", {}):
                try:
                    st.dismiss_pending_folder(folder_id, device_id)
                except Exception:
                    pass
            click.echo(f"  Dismissed '{folder_id}' (already configured locally)")
            continue

        offered_by = folder_info.get("offeredBy", {})
        for device_id, _offer in offered_by.items():
            # Skip offers from our own device
            if own_device_id and device_id == own_device_id:
                continue

            if device_id not in known_devices:
                short_id = device_id[:20] + "..."
                click.echo(f"  Skipped folder '{folder_id}' from unknown device {short_id}")
                continue

            member_name, team_name = known_devices[device_id]
            team_cfg = config.teams[team_name]

            # Find matching project by checking if project name appears in folder ID
            matched_project = None
            for proj_name, proj_cfg in team_cfg.projects.items():
                if proj_name in folder_id:
                    matched_project = (proj_name, proj_cfg)
                    break

            if not matched_project:
                click.echo(
                    f"  Skipped folder '{folder_id}' from {member_name} "
                    f"(no matching project in team '{team_name}')"
                )
                continue

            proj_name, proj_cfg = matched_project
            inbox_path = str(KARMA_BASE / "remote-sessions" / member_name / proj_cfg.encoded_name)

            # Check if we already have a folder at this path (pre-created inbox)
            existing = st.find_folder_by_path(inbox_path)
            if existing:
                existing_id = existing["id"]
                if existing_id == folder_id:
                    click.echo(f"  Already accepted '{folder_id}' from {member_name}")
                    continue
                # Remove the pre-created empty folder to accept the real one
                click.echo(f"  Replacing empty inbox '{existing_id}' with offered '{folder_id}'")
                st.remove_folder(existing_id)

            # Accept: create the folder as receiveonly
            inbox_devices = [device_id]
            if own_device_id:
                inbox_devices.append(own_device_id)
            Path(inbox_path).mkdir(parents=True, exist_ok=True)
            st.add_folder(folder_id, inbox_path, inbox_devices, folder_type="receiveonly")
            existing_folder_ids.add(folder_id)

            click.echo(
                f"  Accepted '{folder_id}' from {member_name} "
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
    """Claude Karma - IPFS/Syncthing session sync for distributed teams."""
    pass


# --- init ---

@cli.command()
@click.option("--user-id", prompt="Your user ID (e.g., your name)", help="Identity for syncing")
@click.option("--backend", type=click.Choice(["ipfs", "syncthing"]), default=None, help="Sync backend")
def init(user_id: str, backend: Optional[str]):
    """Initialize Karma sync on this machine."""
    existing = SyncConfig.load()
    if existing:
        click.echo(f"Already initialized as '{existing.user_id}' on '{existing.machine_id}'.")
        if not click.confirm("Reinitialize?"):
            return

    if not _SAFE_NAME.match(user_id):
        raise click.ClickException("User ID must be alphanumeric, dash, or underscore only.")

    if backend == "syncthing":
        from karma.syncthing import SyncthingClient, read_local_api_key
        api_key = read_local_api_key()
        st = SyncthingClient(api_key=api_key)
        if not st.is_running():
            raise click.ClickException("Syncthing is not running. Start Syncthing first.")
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
        click.echo("Share this Device ID with your project owner.")
    else:
        config = SyncConfig(user_id=user_id)
        config.save()
        click.echo(f"Initialized as '{user_id}' on '{config.machine_id}'.")
        click.echo(f"Config saved to {SYNC_CONFIG_PATH}")
        click.echo("\nNext steps:")
        click.echo("  1. Install Kubo: https://docs.ipfs.tech/install/command-line/")
        click.echo("  2. Start IPFS daemon: ipfs daemon &")
        click.echo("  3. Add a project: karma project add <name> --path /path/to/project")


# --- project ---

@cli.group()
def project():
    """Manage projects for syncing."""
    pass


@project.command("add")
@click.argument("name")
@click.option("--path", required=True, help="Absolute path to the project directory")
@click.option("--team", "team_name", default=None, help="Team to add project to")
def project_add(name: str, path: str, team_name: Optional[str]):
    """Add a project for syncing."""
    if not _SAFE_NAME.match(name):
        raise click.ClickException("Project name must be alphanumeric, dash, or underscore only.")

    if not Path(path).is_absolute():
        raise click.ClickException("Project path must be absolute (e.g., /Users/alice/my-project).")

    config = require_config()

    encoded = encode_project_path(path)
    project_config = ProjectConfig(path=path, encoded_name=encoded)

    if team_name:
        if team_name not in config.teams:
            raise click.ClickException(f"Team '{team_name}' not found.")
        team_cfg = config.teams[team_name]
        projects = dict(team_cfg.projects)
        projects[name] = project_config
        teams = dict(config.teams)
        teams[team_name] = team_cfg.model_copy(update={"projects": projects})
        updated = config.model_copy(update={"teams": teams})

        # Auto-create shared folders if team has Syncthing members
        if team_cfg.backend == "syncthing" and team_cfg.syncthing_members:
            try:
                from karma.syncthing import SyncthingClient, read_local_api_key
                api_key = config.syncthing.api_key or read_local_api_key()
                st = SyncthingClient(api_key=api_key)
                if st.is_running():
                    # My outbox (send-only)
                    outbox_path = str(KARMA_BASE / "remote-sessions" / config.user_id / encoded)
                    outbox_id = f"karma-out-{config.user_id}-{name}"
                    device_ids = []
                    if config.syncthing.device_id:
                        device_ids.append(config.syncthing.device_id)
                    for member in team_cfg.syncthing_members.values():
                        device_ids.append(member.syncthing_device_id)
                    Path(outbox_path).mkdir(parents=True, exist_ok=True)
                    st.add_folder(outbox_id, outbox_path, device_ids, folder_type="sendonly")
                    click.echo(f"Outbox '{outbox_id}' -> {outbox_path} (send-only)")

                    # Inbox per teammate (receive-only)
                    for member_name, member_cfg in team_cfg.syncthing_members.items():
                        inbox_path = str(KARMA_BASE / "remote-sessions" / member_name / encoded)
                        inbox_id = f"karma-out-{member_name}-{name}"
                        inbox_devices = [member_cfg.syncthing_device_id]
                        if config.syncthing.device_id:
                            inbox_devices.append(config.syncthing.device_id)
                        Path(inbox_path).mkdir(parents=True, exist_ok=True)
                        st.add_folder(inbox_id, inbox_path, inbox_devices, folder_type="receiveonly")
                        click.echo(f"Inbox '{inbox_id}' -> {inbox_path} (receive-only)")
            except Exception as e:
                click.echo(f"Warning: Could not auto-share folder: {e}")
    else:
        # Legacy flat projects
        projects = dict(config.projects)
        projects[name] = project_config
        updated = config.model_copy(update={"projects": projects})

    updated.save()
    click.echo(f"Added project '{name}' ({path})")
    click.echo(f"Encoded as: {encoded}")


@project.command("list")
def project_list():
    """List configured projects."""
    config = require_config()

    if not config.projects and not config.teams:
        click.echo("No projects configured. Run: karma project add <name> --path /path")
        return

    for name, proj in config.projects.items():
        sync_info = f" (last sync: {proj.last_sync_at})" if proj.last_sync_at else " (never synced)"
        click.echo(f"  {name}: {proj.path}{sync_info}")

    for team_name, team_cfg in config.teams.items():
        for name, proj in team_cfg.projects.items():
            last = proj.last_sync_at or "never"
            click.echo(f"  {name}: {proj.path} [team: {team_name}] (last: {last})")


@project.command("remove")
@click.argument("name")
@click.option("--team", "team_name", default=None, help="Team to remove project from")
def project_remove(name: str, team_name: Optional[str]):
    """Remove a project from syncing."""
    config = require_config()

    if team_name:
        if team_name not in config.teams:
            raise click.ClickException(f"Team '{team_name}' not found.")
        team_cfg = config.teams[team_name]
        if name not in team_cfg.projects:
            raise click.ClickException(f"Project '{name}' not found in team '{team_name}'.")
        projects = dict(team_cfg.projects)
        del projects[name]
        teams = dict(config.teams)
        teams[team_name] = team_cfg.model_copy(update={"projects": projects})
        updated = config.model_copy(update={"teams": teams})
    else:
        if name not in config.projects:
            raise click.ClickException(f"Project '{name}' not found.")
        projects = dict(config.projects)
        del projects[name]
        updated = config.model_copy(update={"projects": projects})

    updated.save()
    click.echo(f"Removed project '{name}'.")


# --- sync ---

@cli.command()
@click.argument("name", required=False)
@click.option("--all", "sync_all", is_flag=True, help="Sync all configured projects")
def sync(name: str, sync_all: bool):
    """Sync project sessions to IPFS."""
    from karma.ipfs import IPFSClient

    config = require_config()
    ipfs = IPFSClient(api_url=config.ipfs_api)

    if not ipfs.is_running():
        raise click.ClickException("IPFS daemon not running. Start with: ipfs daemon &")

    targets = list(config.projects.keys()) if sync_all else ([name] if name else [])
    if not targets:
        raise click.ClickException("Specify a project name or use --all")

    for project_name in targets:
        try:
            click.echo(f"Syncing '{project_name}'...")
            cid, count = sync_project(project_name, config, ipfs)
            if count == 0:
                click.echo("  No sessions found.")
            else:
                click.echo(f"  Synced {count} sessions -> {cid}")
                projects = dict(config.projects)
                old = projects[project_name]
                from datetime import datetime, timezone
                projects[project_name] = old.model_copy(update={
                    "last_sync_cid": cid,
                    "last_sync_at": datetime.now(timezone.utc).isoformat(),
                })
                config = config.model_copy(update={"projects": projects})
                config.save()
        except click.ClickException as e:
            click.echo(f"  Error syncing '{project_name}': {e.message}", err=True)


# --- pull ---

@cli.command()
def pull():
    """Pull remote sessions from IPFS for all team members."""
    from karma.ipfs import IPFSClient

    config = require_config()
    ipfs = IPFSClient(api_url=config.ipfs_api)

    if not ipfs.is_running():
        raise click.ClickException("IPFS daemon not running. Start with: ipfs daemon &")

    if not config.team:
        click.echo("No team members configured. Run: karma team add <name> <ipns-key>")
        return

    click.echo(f"Pulling sessions from {len(config.team)} team members...")
    results = pull_remote_sessions(config, ipfs)

    for r in results:
        status = r["status"]
        if status == "ok":
            click.echo(f"  {r['member']}: pulled ({r['cid'][:12]}...)")
        else:
            click.echo(f"  {r['member']}: {status}")


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
    api_key = config.syncthing.api_key if config.syncthing else read_local_api_key()
    if not api_key:
        raise click.ClickException(
            "No Syncthing API key found. Run: karma init --backend syncthing"
        )

    st = SyncthingClient(api_key=api_key)
    if not st.is_running():
        raise click.ClickException("Syncthing is not running. Start Syncthing first.")

    click.echo("Checking for pending folder offers...")
    n = _accept_pending_folders(st, config)
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

    if team_name not in config.teams:
        raise click.ClickException(
            f"Team '{team_name}' not found. Run: karma team create {team_name} --backend syncthing"
        )

    team_cfg = config.teams[team_name]
    if team_cfg.backend != "syncthing":
        raise click.ClickException(
            f"Team '{team_name}' uses {team_cfg.backend}, not syncthing. Watch is only for Syncthing."
        )

    if not team_cfg.projects:
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
                n = _accept_pending_folders(st, config)
                if n:
                    click.echo(f"Accepted {n} pending folder(s) from known teammates.\n")
    except Exception as e:
        click.echo(f"Warning: Could not check pending folders: {e}\n")

    click.echo(f"Watching {len(team_cfg.projects)} project(s) for team '{team_name}'...")
    click.echo("Press Ctrl+C to stop.\n")

    from karma.worktree_discovery import find_all_worktree_dirs

    watchers = []
    projects_dir = Path.home() / ".claude" / "projects"

    for proj_name, proj in team_cfg.projects.items():
        claude_dir = Path.home() / ".claude" / "projects" / proj.encoded_name
        if not claude_dir.is_dir():
            click.echo(f"  Skipping '{proj_name}': Claude dir not found ({claude_dir})")
            continue

        # Discover worktree dirs for this project
        wt_dirs = find_all_worktree_dirs(proj.encoded_name, proj.path, projects_dir)
        if wt_dirs:
            click.echo(f"  Found {len(wt_dirs)} worktree dir(s) for '{proj_name}'")

        # team_name intentionally excluded — user_id provides namespace isolation.
        # Both IPFS pull and Syncthing watch converge on this same path.
        outbox = KARMA_BASE / "remote-sessions" / config.user_id / proj.encoded_name

        def make_package_fn(cd=claude_dir, ob=outbox, pn=proj_name, en=proj.encoded_name, pp=proj.path):
            def package():
                # Re-discover worktrees each time (new ones may appear)
                current_wt_dirs = find_all_worktree_dirs(en, pp, projects_dir)
                packager = SessionPackager(
                    project_dir=cd,
                    user_id=config.user_id,
                    machine_id=config.machine_id,
                    project_path=proj.path,
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
        click.echo(f"  Watching: {proj_name} ({claude_dir})")

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

    try:
        import time
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        click.echo("\nStopping watchers...")
    finally:
        for w in watchers:
            w.stop()
        click.echo("Done.")


# --- status ---

@cli.command()
def status():
    """Show sync status for all teams."""
    from karma.worktree_discovery import find_all_worktree_dirs

    config = require_config()

    click.echo(f"User: {config.user_id} ({config.machine_id})")

    if not config.teams and not config.projects:
        click.echo("No teams or projects configured.")
        return

    # Legacy flat projects
    if config.projects:
        click.echo(f"\nLegacy projects (IPFS):")
        for name, proj in config.projects.items():
            sync_info = f"last sync: {proj.last_sync_at}" if proj.last_sync_at else "never synced"
            click.echo(f"  {name}: {proj.path} ({sync_info})")

    projects_dir = Path.home() / ".claude" / "projects"

    # Per-team
    for team_name, team_cfg in config.teams.items():
        click.echo(f"\n{team_name} ({team_cfg.backend}):")
        if not team_cfg.projects:
            click.echo("  No projects")
        for proj_name, proj in team_cfg.projects.items():
            last = proj.last_sync_at or "never"
            claude_dir = projects_dir / proj.encoded_name

            # Count local sessions
            local_count = 0
            if claude_dir.is_dir():
                local_count = sum(
                    1 for f in claude_dir.glob("*.jsonl")
                    if not f.name.startswith("agent-") and f.stat().st_size > 0
                )

            # Count worktree sessions
            wt_dirs = find_all_worktree_dirs(proj.encoded_name, proj.path, projects_dir)
            wt_count = 0
            for wd in wt_dirs:
                wt_count += sum(
                    1 for f in wd.glob("*.jsonl")
                    if not f.name.startswith("agent-") and f.stat().st_size > 0
                )

            # Count packaged sessions
            outbox = KARMA_BASE / "remote-sessions" / config.user_id / proj.encoded_name / "sessions"
            packaged_count = 0
            if outbox.is_dir():
                packaged_count = sum(1 for f in outbox.glob("*.jsonl") if not f.name.startswith("agent-"))

            total_local = local_count + wt_count
            gap = total_local - packaged_count

            click.echo(f"  {proj_name}: {proj.path} (last: {last})")
            click.echo(f"    Local: {local_count} sessions + {wt_count} worktree ({len(wt_dirs)} dirs) = {total_local}")
            click.echo(f"    Packaged: {packaged_count}  {'(up to date)' if gap <= 0 else f'({gap} behind)'}")

        if team_cfg.members:
            click.echo(f"  Members: {', '.join(team_cfg.members.keys())}")


# --- team ---

@cli.group()
def team():
    """Manage team members for pulling remote sessions."""
    pass


@team.command("create")
@click.argument("name")
@click.option("--backend", type=click.Choice(["ipfs", "syncthing"]), required=True, help="Sync backend")
def team_create(name: str, backend: str):
    """Create a new team with a specific sync backend."""
    if not _SAFE_NAME.match(name):
        raise click.ClickException("Team name must be alphanumeric, dash, or underscore only.")

    config = require_config()

    team_config = TeamConfig(backend=backend, projects={})

    teams = dict(config.teams)
    teams[name] = team_config
    updated = config.model_copy(update={"teams": teams})
    updated.save()

    click.echo(f"Created team '{name}' (backend: {backend})")


@team.command("add")
@click.argument("name")
@click.argument("identifier")
@click.option("--team", "team_name", default=None, help="Team to add member to (for per-team config)")
def team_add(name: str, identifier: str, team_name: Optional[str]):
    """Add a team member by their IPNS key or Syncthing device ID."""
    if not _SAFE_NAME.match(name):
        raise click.ClickException("Team member name must be alphanumeric, dash, or underscore only.")

    config = require_config()

    if team_name and team_name in config.teams:
        # Per-team member add
        team_cfg = config.teams[team_name]
        if team_cfg.backend == "syncthing":
            syncthing_members = dict(team_cfg.syncthing_members)
            syncthing_members[name] = TeamMemberSyncthing(syncthing_device_id=identifier)
            teams = dict(config.teams)
            teams[team_name] = team_cfg.model_copy(update={"syncthing_members": syncthing_members})

            # Auto-pair device in Syncthing
            try:
                from karma.syncthing import SyncthingClient, read_local_api_key
                api_key = config.syncthing.api_key or read_local_api_key()
                st = SyncthingClient(api_key=api_key)
                if st.is_running():
                    st.add_device(identifier, name)
                    click.echo(f"Paired Syncthing device '{name}' ({identifier[:7]}...)")

                    # Auto-create shared folder if team has projects
                    _auto_share_folders(st, config, team_cfg, teams, team_name, identifier)

                    # Auto-accept any pending folder offers from this member
                    updated_config = config.model_copy(update={"teams": teams})
                    n = _accept_pending_folders(st, updated_config)
                    if n:
                        click.echo(f"Accepted {n} pending folder(s) from known teammates.")
                else:
                    click.echo("Warning: Syncthing not running — device saved but not paired yet.")
            except Exception as e:
                click.echo(f"Warning: Could not auto-pair device: {e}")
                click.echo("You can pair manually in Syncthing UI (http://127.0.0.1:8384)")
        else:
            ipfs_members = dict(team_cfg.ipfs_members)
            ipfs_members[name] = TeamMember(ipns_key=identifier)
            teams = dict(config.teams)
            teams[team_name] = team_cfg.model_copy(update={"ipfs_members": ipfs_members})
        updated = config.model_copy(update={"teams": teams})
        updated.save()
        click.echo(f"Added team member '{name}' to team '{team_name}'")
    else:
        # Legacy flat team dict (IPFS-only backward compat)
        if not identifier or identifier.startswith("-") or len(identifier) > 128:
            raise click.ClickException("Invalid IPNS key: must be non-empty, not start with dash, max 128 chars.")
        if not re.match(r"^[a-zA-Z0-9]+$", identifier):
            raise click.ClickException("Invalid IPNS key: must be alphanumeric only.")
        members = dict(config.team)
        members[name] = TeamMember(ipns_key=identifier)
        updated = config.model_copy(update={"team": members})
        updated.save()
        click.echo(f"Added team member '{name}' ({identifier})")


@team.command("list")
def team_list():
    """List team members."""
    config = require_config()

    if not config.team and not config.teams:
        click.echo("No team members. Run: karma team add <name> <ipns-key>")
        return

    # Legacy flat team
    for name, member in config.team.items():
        click.echo(f"  {name}: {member.ipns_key}")

    # Per-team members
    for team_name, team_cfg in config.teams.items():
        if team_cfg.members:
            click.echo(f"\n  {team_name} ({team_cfg.backend}):")
            for member_name in team_cfg.members:
                click.echo(f"    {member_name}")


@team.command("remove")
@click.argument("name")
@click.option("--team", "team_name", default=None, help="Team to remove member from")
def team_remove(name: str, team_name: Optional[str]):
    """Remove a team member."""
    config = require_config()

    if team_name:
        if team_name not in config.teams:
            raise click.ClickException(f"Team '{team_name}' not found.")
        team_cfg = config.teams[team_name]
        if team_cfg.backend == "syncthing":
            if name not in team_cfg.syncthing_members:
                raise click.ClickException(f"Member '{name}' not found in team '{team_name}'.")
            members = dict(team_cfg.syncthing_members)
            del members[name]
            teams = dict(config.teams)
            teams[team_name] = team_cfg.model_copy(update={"syncthing_members": members})
        else:
            if name not in team_cfg.ipfs_members:
                raise click.ClickException(f"Member '{name}' not found in team '{team_name}'.")
            members = dict(team_cfg.ipfs_members)
            del members[name]
            teams = dict(config.teams)
            teams[team_name] = team_cfg.model_copy(update={"ipfs_members": members})
        updated = config.model_copy(update={"teams": teams})
    else:
        if name not in config.team:
            raise click.ClickException(f"Team member '{name}' not found.")
        members = dict(config.team)
        del members[name]
        updated = config.model_copy(update={"team": members})

    updated.save()
    click.echo(f"Removed team member '{name}'.")


if __name__ == "__main__":
    cli()
