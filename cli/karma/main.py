"""Karma CLI entry point."""

import re
from pathlib import Path

import click

from karma.config import SyncConfig, SyncthingSettings, SYNC_CONFIG_PATH, KARMA_BASE

_SAFE_NAME = re.compile(r"^[a-zA-Z0-9_\-]+$")


@click.group()
@click.version_option(package_name="claude-karma-cli")
def cli():
    """Claude Karma - Syncthing session sync for distributed teams.

    Sync operations (teams, projects, members, pending folders) have moved
    to the API layer.  Use the web dashboard or API endpoints instead.
    """
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


# --- ls ---


@cli.command("ls")
def list_remote():
    """List available remote sessions."""
    import json

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


if __name__ == "__main__":
    cli()
