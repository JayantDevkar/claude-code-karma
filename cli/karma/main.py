"""Karma CLI entry point."""

import json
import re
from pathlib import Path
from typing import Optional

import click

from karma.config import (
    SyncConfig, ProjectConfig, TeamMember, TeamConfig,
    TeamMemberSyncthing, SYNC_CONFIG_PATH, KARMA_BASE,
)
from karma.sync import sync_project, pull_remote_sessions, encode_project_path

_SAFE_NAME = re.compile(r"^[a-zA-Z0-9_\-]+$")


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
        from karma.syncthing import SyncthingClient
        st = SyncthingClient()
        if not st.is_running():
            raise click.ClickException("Syncthing is not running. Start Syncthing first.")
        device_id = st.get_device_id()
        config = SyncConfig(user_id=user_id)
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
    remote_dir = Path.home() / ".claude_karma" / "remote-sessions"
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

    click.echo(f"Watching {len(team_cfg.projects)} project(s) for team '{team_name}'...")
    click.echo("Press Ctrl+C to stop.\n")

    watchers = []
    for proj_name, proj in team_cfg.projects.items():
        claude_dir = Path.home() / ".claude" / "projects" / proj.encoded_name
        if not claude_dir.is_dir():
            click.echo(f"  Skipping '{proj_name}': Claude dir not found ({claude_dir})")
            continue

        outbox = KARMA_BASE / "sync-outbox" / team_name / config.user_id / proj.encoded_name

        def make_package_fn(cd=claude_dir, ob=outbox, pn=proj_name):
            def package():
                packager = SessionPackager(
                    project_dir=cd,
                    user_id=config.user_id,
                    machine_id=config.machine_id,
                    project_path=proj.path,
                )
                ob.mkdir(parents=True, exist_ok=True)
                packager.package(staging_dir=ob)
                click.echo(f"  Packaged '{pn}' -> {ob}")
            return package

        watcher = SessionWatcher(
            watch_dir=claude_dir,
            package_fn=make_package_fn(),
        )
        watcher.start()
        watchers.append(watcher)
        click.echo(f"  Watching: {proj_name} ({claude_dir})")

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

    # Per-team
    for team_name, team_cfg in config.teams.items():
        click.echo(f"\n{team_name} ({team_cfg.backend}):")
        if not team_cfg.projects:
            click.echo("  No projects")
        for proj_name, proj in team_cfg.projects.items():
            last = proj.last_sync_at or "never"
            click.echo(f"  {proj_name}: {proj.path} (last: {last})")
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
