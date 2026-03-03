"""Sync and pull operations for IPFS session sharing."""

import re
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Optional

import click

from karma.config import SyncConfig
from karma.ipfs import IPFSClient
from karma.packager import SessionPackager

_SAFE_NAME = re.compile(r"^[a-zA-Z0-9_\-]+$")
_SAFE_FILENAME = re.compile(r"^[a-zA-Z0-9_.\-]+$")


def encode_project_path(path: str) -> str:
    """Encode a project path the same way Claude Code does.

    Unix:    /Users/alice/repo  → -Users-alice-repo
    Windows: C:\\Users\\alice\\repo → -C-Users-alice-repo
    """
    p = path.replace("\\", "/")
    # Strip leading slash (Unix) or drive letter colon (Windows: C:/)
    if p.startswith("/"):
        p = p[1:]
    p = p.replace(":", "")
    return "-" + p.replace("/", "-")


def find_claude_project_dir(project_path: str) -> Optional[Path]:
    """Find the Claude project directory for a given project path."""
    encoded = encode_project_path(project_path)
    claude_dir = Path.home() / ".claude" / "projects" / encoded
    if claude_dir.is_dir():
        return claude_dir
    return None


def sync_project(
    project_name: str,
    config: SyncConfig,
    ipfs: IPFSClient,
) -> tuple[str, int]:
    """Sync a project's sessions to IPFS. Returns (cid, session_count)."""
    if project_name not in config.projects:
        raise click.ClickException(
            f"Project '{project_name}' not configured. Run: karma project add {project_name}"
        )

    project = config.projects[project_name]
    claude_dir = Path.home() / ".claude" / "projects" / project.encoded_name

    if not claude_dir.is_dir():
        raise click.ClickException(f"Claude project directory not found: {claude_dir}")

    packager = SessionPackager(
        project_dir=claude_dir,
        user_id=config.user_id,
        machine_id=config.machine_id,
        project_path=project.path,
        last_sync_cid=project.last_sync_cid,
    )

    with tempfile.TemporaryDirectory(prefix="karma-sync-") as staging:
        staging_path = Path(staging)
        manifest = packager.package(staging_dir=staging_path)

        if manifest.session_count == 0:
            return ("", 0)

        # Add to IPFS
        try:
            cid = ipfs.add(str(staging_path), recursive=True)
            ipfs.pin_add(cid)
            ipfs.name_publish(cid)
        except subprocess.CalledProcessError as e:
            raise click.ClickException(f"IPFS error: {e.stderr or str(e)}")

        return (cid, manifest.session_count)


def pull_remote_sessions(
    config: SyncConfig,
    ipfs: IPFSClient,
    output_dir: Optional[Path] = None,
) -> list[dict]:
    """Pull remote sessions from IPFS for all team members."""
    if output_dir is None:
        output_dir = Path.home() / ".claude_karma" / "remote-sessions"

    results = []
    for member_name, member in config.team.items():
        # Re-validate member name before using in filesystem paths
        if not _SAFE_NAME.match(member_name):
            results.append({
                "member": member_name, "cid": None,
                "status": "error: invalid member name",
            })
            continue

        try:
            # Resolve IPNS to CID
            cid_path = ipfs.name_resolve(member.ipns_key)
            cid = cid_path.split("/")[-1] if "/" in cid_path else cid_path

            member_dir = output_dir / member_name
            # Safety check: ensure resolved path stays inside output_dir
            if not member_dir.resolve().is_relative_to(output_dir.resolve()):
                results.append({
                    "member": member_name, "cid": None,
                    "status": "error: path escape detected",
                })
                continue

            # ipfs get writes content into a CID-named subdirectory.
            # Fetch to a temp dir, then move contents into member_dir.
            with tempfile.TemporaryDirectory(prefix="karma-pull-") as tmp:
                tmp_path = Path(tmp)
                ipfs.get(cid, str(tmp_path))

                # ipfs get creates tmp_path/CID/ — move its contents to member_dir
                cid_subdir = tmp_path / cid
                if cid_subdir.is_dir():
                    src = cid_subdir
                else:
                    # Fallback: content placed directly in tmp_path
                    src = tmp_path

                member_dir.mkdir(parents=True, exist_ok=True)
                for item in src.iterdir():
                    # Skip symlinks (could point outside output dir)
                    if item.is_symlink():
                        continue
                    # Validate filename
                    if not _SAFE_FILENAME.match(item.name):
                        continue
                    dest = member_dir / item.name
                    # Final safety: ensure dest resolves inside member_dir
                    if not dest.resolve().is_relative_to(member_dir.resolve()):
                        continue
                    if dest.exists():
                        if dest.is_dir():
                            shutil.rmtree(dest)
                        else:
                            dest.unlink()
                    shutil.move(str(item), str(dest))

            results.append({"member": member_name, "cid": cid, "status": "ok"})
        except Exception as e:
            results.append({"member": member_name, "cid": None, "status": f"error: {e}"})

    return results
