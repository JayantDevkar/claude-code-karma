"""Install the Karma desktop launcher from the dashboard.

Starting the servers by hand is a one-time cost when you first clone karma;
after that the desktop icon should do it. Asking people to run a second
terminal command to get that icon defeats the point, so the dashboard exposes
the installer directly.

The installer itself lives in ``scripts/karma_desktop`` at the repository root
and is shared with the command-line entry point, so there is one implementation
of the platform logic.
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path
from typing import List, Optional

from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel, Field

from parallel import run_in_thread

router = APIRouter(prefix="/desktop-app", tags=["desktop-app"])
logger = logging.getLogger(__name__)

# <repo>/api/routers/desktop_app.py -> <repo>
REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS_DIR = REPO_ROOT / "scripts"


def _load_installer():
    """Import the shared installer package from the repo's scripts directory."""
    if str(SCRIPTS_DIR) not in sys.path:
        sys.path.insert(0, str(SCRIPTS_DIR))
    try:
        import install_karma_app  # noqa: PLC0415
        from karma_desktop import core  # noqa: PLC0415

        return install_karma_app, core
    except ImportError as exc:  # pragma: no cover - depends on checkout layout
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail=(
                "The desktop installer is not available in this checkout "
                f"(expected it at {SCRIPTS_DIR})."
            ),
        ) from exc


def _require_local(request: Request) -> None:
    """Reject anything that is not a loopback caller.

    This endpoint writes an executable application bundle and can register a
    login item, so it must never be reachable from another machine even if
    someone exposes the API beyond localhost.
    """
    host = request.client.host if request.client else None
    if host not in ("127.0.0.1", "::1", "localhost"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="The desktop installer can only be used from this machine.",
        )


class DesktopAppStatus(BaseModel):
    supported: bool = Field(description="Whether this OS has a desktop installer")
    platform: str
    installed: bool
    install_path: Optional[str] = None
    autostart_enabled: bool = False
    web_port: int
    api_port: int
    repo_root: str


class InstallRequest(BaseModel):
    dock: bool = Field(
        default=True,
        description="macOS: also pin the app to the Dock (restarts the Dock).",
    )
    autostart: bool = Field(
        default=False,
        description="Also start the servers at login.",
    )


class InstallResult(BaseModel):
    ok: bool
    messages: List[str]
    install_path: Optional[str] = None


class AutostartRequest(BaseModel):
    enabled: bool = Field(description="Whether Karma should start at login.")


class AutostartResult(BaseModel):
    ok: bool
    enabled: bool
    messages: List[str]


def _macos_app_paths() -> List[Path]:
    return [Path("/Applications/Karma.app"), Path.home() / "Applications" / "Karma.app"]


def _status_sync() -> DesktopAppStatus:
    installer, core = _load_installer()
    supported = sys.platform in ("darwin", "win32")
    installed = False
    install_path: Optional[str] = None
    autostart = False

    if sys.platform == "darwin":
        from karma_desktop import installer_macos as mac  # noqa: PLC0415

        for candidate in _macos_app_paths():
            if candidate.exists():
                installed, install_path = True, str(candidate)
                break
        autostart = mac.autostart_enabled()
    elif sys.platform == "win32":
        from karma_desktop import installer_windows as win  # noqa: PLC0415

        shortcut = win.desktop_dir() / win.SHORTCUT_NAME
        if shortcut.exists():
            installed, install_path = True, str(shortcut)
        autostart = win.autostart_enabled()

    return DesktopAppStatus(
        supported=supported,
        platform=sys.platform,
        installed=installed,
        install_path=install_path,
        autostart_enabled=autostart,
        web_port=core.WEB_PORT,
        api_port=core.API_PORT,
        repo_root=str(core.repo_root()),
    )


def _install_sync(body: InstallRequest) -> InstallResult:
    installer, core = _load_installer()
    repo = core.repo_root()
    python = installer.stable_python()
    messages: List[str] = []

    if sys.platform == "darwin":
        from karma_desktop import installer_macos as mac  # noqa: PLC0415

        # Prefer /Applications, but fall back to the user's own folder rather
        # than failing when the volume is not writable.
        app_dir = Path("/Applications")
        try:
            app = mac.install_app(repo, python, app_dir, core.WEB_PORT, core.API_PORT)
        except (PermissionError, OSError):
            app_dir = Path.home() / "Applications"
            app_dir.mkdir(parents=True, exist_ok=True)
            app = mac.install_app(repo, python, app_dir, core.WEB_PORT, core.API_PORT)
            messages.append(
                "No permission to write to /Applications; installed to ~/Applications instead."
            )
        messages.append(f"Installed {app}")

        if body.dock:
            if mac.add_to_dock(app):
                messages.append("Pinned to the Dock.")
            else:
                messages.append("Could not update the Dock; drag the app there manually.")
        if body.autostart:
            mac.install_autostart(repo, python, core.WEB_PORT, core.API_PORT)
            messages.append("Karma will now start at login.")
        return InstallResult(ok=True, messages=messages, install_path=str(app))

    if sys.platform == "win32":
        from karma_desktop import installer_windows as win  # noqa: PLC0415

        lnk = win.install_app(repo, python, core.WEB_PORT, core.API_PORT)
        messages.append(f"Added {lnk.name} to your Desktop.")
        if body.autostart:
            win.install_autostart(repo, python, core.WEB_PORT, core.API_PORT)
            messages.append("Karma will now start at login.")
        return InstallResult(ok=True, messages=messages, install_path=str(lnk))

    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail=f"No desktop installer for {sys.platform} yet.",
    )


def _set_autostart_sync(enabled: bool) -> AutostartResult:
    """Enable or disable start-at-login.

    Deliberately independent of installing the desktop icon: someone using the
    browser-installed app wants the servers up at login but has no use for a
    second icon.
    """
    installer, core = _load_installer()
    repo = core.repo_root()
    python = installer.stable_python()
    messages: List[str] = []

    if sys.platform == "darwin":
        from karma_desktop import installer_macos as backend  # noqa: PLC0415

        login_items_hint = (
            "macOS will notify you that a background item was added. You can "
            "also switch it off under System Settings > General > Login Items."
        )
    elif sys.platform == "win32":
        from karma_desktop import installer_windows as backend  # noqa: PLC0415

        login_items_hint = (
            "Windows lists this under Task Manager > Startup, where it can also be disabled."
        )
    else:
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail=f"No autostart support for {sys.platform} yet.",
        )

    if enabled:
        backend.install_autostart(repo, python, core.WEB_PORT, core.API_PORT)
        messages.append("Karma will now start at login.")
        messages.append(login_items_hint)
        # With the servers up at login, the launcher never needs clicking, so a
        # pinned launcher tile only competes with the PWA icon the user pins.
        if sys.platform == "darwin" and backend.unpin_from_dock():
            messages.append(
                "Unpinned the launcher from the Dock — install Karma from your "
                "browser's address bar (Install app) and pin that instead."
            )
    else:
        removed = backend.uninstall_autostart()
        messages.append(
            "Karma will no longer start at login."
            if removed
            else "Karma was not set to start at login."
        )
        messages.append(
            "Servers already running were left alone; close them if you want them stopped now."
        )

    # Report what is actually on disk rather than what was requested, so a
    # partial failure can never be reported as success.
    return AutostartResult(ok=True, enabled=backend.autostart_enabled(), messages=messages)


def _uninstall_sync() -> InstallResult:
    _load_installer()
    if sys.platform == "darwin":
        from karma_desktop import installer_macos as mac  # noqa: PLC0415

        removed = mac.uninstall([Path("/Applications"), Path.home() / "Applications"])
    elif sys.platform == "win32":
        from karma_desktop import installer_windows as win  # noqa: PLC0415

        removed = win.uninstall()
    else:
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail=f"No desktop installer for {sys.platform} yet.",
        )
    return InstallResult(
        ok=True,
        messages=[f"Removed {item}" for item in removed] or ["Nothing was installed."],
    )


@router.get("/status", response_model=DesktopAppStatus)
async def get_status(request: Request) -> DesktopAppStatus:
    """Whether the desktop launcher is installed on this machine."""
    _require_local(request)
    return await run_in_thread(_status_sync)


@router.post("/install", response_model=InstallResult)
async def install(request: Request, body: InstallRequest) -> InstallResult:
    """Install the desktop launcher (and optionally pin it / enable autostart)."""
    _require_local(request)
    try:
        return await run_in_thread(_install_sync, body)
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Desktop app install failed")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Install failed: {exc}",
        ) from exc


@router.put("/autostart", response_model=AutostartResult)
async def set_autostart(request: Request, body: AutostartRequest) -> AutostartResult:
    """Turn start-at-login on or off."""
    _require_local(request)
    try:
        return await run_in_thread(_set_autostart_sync, body.enabled)
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Setting autostart failed")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Could not change the autostart setting: {exc}",
        ) from exc


@router.delete("/install", response_model=InstallResult)
async def uninstall(request: Request) -> InstallResult:
    """Remove the desktop launcher, its Dock tile and any login item."""
    _require_local(request)
    try:
        return await run_in_thread(_uninstall_sync)
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Desktop app uninstall failed")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Uninstall failed: {exc}",
        ) from exc
