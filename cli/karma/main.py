"""Karma CLI entry point."""

import json
import re

import click

from karma.config import SyncConfig, ProjectConfig, TeamMember, SYNC_CONFIG_PATH
from karma.sync import sync_project, pull_remote_sessions, encode_project_path

_SAFE_NAME = re.compile(r"^[a-zA-Z0-9_\-]+$")


def require_config() -> SyncConfig:
    """Load config or exit with helpful message."""
    config = SyncConfig.load()
    if config is None:
        raise click.ClickException("Not initialized. Run: karma init")
    return config


@click.group()
@click.version_option()
def cli():
    """Claude Karma - IPFS session sync for distributed teams."""
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
def project_add(name: str, path: str):
    """Add a project for IPFS syncing."""
    if not _SAFE_NAME.match(name):
        raise click.ClickException("Project name must be alphanumeric, dash, or underscore only.")

    from pathlib import Path as _Path
    if not _Path(path).is_absolute():
        raise click.ClickException("Project path must be absolute (e.g., /Users/alice/my-project).")

    config = require_config()

    encoded = encode_project_path(path)
    project_config = ProjectConfig(path=path, encoded_name=encoded)

    # Update config (create mutable copy)
    projects = dict(config.projects)
    projects[name] = project_config
    updated = config.model_copy(update={"projects": projects})
    updated.save()

    click.echo(f"Added project '{name}' ({path})")
    click.echo(f"Encoded as: {encoded}")
    click.echo(f"\nSync with: karma sync {name}")


@project.command("list")
def project_list():
    """List configured projects."""
    config = require_config()

    if not config.projects:
        click.echo("No projects configured. Run: karma project add <name> --path /path")
        return

    for name, proj in config.projects.items():
        sync_info = f" (last sync: {proj.last_sync_at})" if proj.last_sync_at else " (never synced)"
        click.echo(f"  {name}: {proj.path}{sync_info}")


@project.command("remove")
@click.argument("name")
def project_remove(name: str):
    """Remove a project from syncing."""
    config = require_config()

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
        click.echo(f"Syncing '{project_name}'...")
        cid, count = sync_project(project_name, config, ipfs)
        if count == 0:
            click.echo("  No sessions found.")
        else:
            click.echo(f"  Synced {count} sessions -> {cid}")

            # Update last sync in config
            projects = dict(config.projects)
            old = projects[project_name]
            from datetime import datetime, timezone
            projects[project_name] = old.model_copy(update={
                "last_sync_cid": cid,
                "last_sync_at": datetime.now(timezone.utc).isoformat(),
            })
            config = config.model_copy(update={"projects": projects})
            config.save()


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
    from pathlib import Path

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
                manifest = json.loads(manifest_path.read_text())
                click.echo(
                    f"  {project_dir.name}: "
                    f"{manifest.get('session_count', '?')} sessions "
                    f"(synced {manifest.get('synced_at', '?')})"
                )
            else:
                click.echo(f"  {project_dir.name}: (no manifest)")


# --- team ---

@cli.group()
def team():
    """Manage team members for pulling remote sessions."""
    pass


@team.command("add")
@click.argument("name")
@click.argument("ipns_key")
def team_add(name: str, ipns_key: str):
    """Add a team member by their IPNS key."""
    if not _SAFE_NAME.match(name):
        raise click.ClickException("Team member name must be alphanumeric, dash, or underscore only.")
    config = require_config()

    members = dict(config.team)
    members[name] = TeamMember(ipns_key=ipns_key)
    updated = config.model_copy(update={"team": members})
    updated.save()

    click.echo(f"Added team member '{name}' ({ipns_key})")


@team.command("list")
def team_list():
    """List team members."""
    config = require_config()

    if not config.team:
        click.echo("No team members. Run: karma team add <name> <ipns-key>")
        return

    for name, member in config.team.items():
        click.echo(f"  {name}: {member.ipns_key}")


@team.command("remove")
@click.argument("name")
def team_remove(name: str):
    """Remove a team member."""
    config = require_config()

    if name not in config.team:
        raise click.ClickException(f"Team member '{name}' not found.")

    members = dict(config.team)
    del members[name]
    updated = config.model_copy(update={"team": members})
    updated.save()

    click.echo(f"Removed team member '{name}'.")


if __name__ == "__main__":
    cli()
