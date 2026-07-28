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


def _load_core():
    """Import the installer package's core module from scripts/.

    Only the package is imported, never the ``install_karma_app`` CLI script --
    keeping the CLI's argparse/entry-point surface out of the long-lived server
    process.

    ``scripts/`` is *appended* to ``sys.path``, not inserted at the front, and
    only once. Inserting at position 0 would give ``scripts/`` higher import
    precedence than the app itself for the entire life of the server process --
    and ``scripts/`` contains an implicit namespace package ``tests`` that would
    then shadow ``api/tests`` and any like-named third-party package. Appending
    keeps ``karma_desktop`` importable without reordering everything else.
    """
    if str(SCRIPTS_DIR) not in sys.path:
        sys.path.append(str(SCRIPTS_DIR))
    try:
        from karma_desktop import core  # noqa: PLC0415

        return core
    except ImportError as exc:  # pragma: no cover - depends on checkout layout
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail=(
                "The desktop installer is not available in this checkout "
                f"(expected it at {SCRIPTS_DIR})."
            ),
        ) from exc


_LOOPBACK_PEERS = frozenset({"127.0.0.1", "::1"})
_LOOPBACK_HOSTS = frozenset({"localhost", "127.0.0.1", "::1"})
# A page from another origin carries "cross-site"; our own dashboard on another
# localhost port carries "same-site"; a user-initiated request (curl, the
# address bar) carries no such header at all. Everything but a genuine
# cross-site request is allowed.
_ALLOWED_FETCH_SITES = frozenset({"same-origin", "same-site", "none"})


def _require_local(request: Request) -> None:
    """Guard this code-execution endpoint against remote and cross-site callers.

    Honest scope: this is a **localhost-only** endpoint, not an authenticated
    one. It writes an executable bundle and can register a login item, so it
    must only ever be reachable from this machine. The checks below defend that
    boundary against the realistic browser attacks and the ordinary
    reverse-proxy setup -- but a non-browser client reaching a proxy that
    rewrites the Host to a loopback value cannot be told apart from a genuine
    local caller. Do not expose this API beyond localhost; that is the actual
    guarantee, and no header check can substitute for it.

    Also explicit, because ``same-site`` is deliberately allowed (the real
    dashboard on :5180 calling the API on :8020 is same-site, not same-origin):
    *any* page served from *any* loopback port -- including another local dev
    server you happen to be running -- is same-site to this API and passes this
    guard. On a single-user machine that is an accepted trade-off, but it does
    mean the boundary is "anything local", not "only the Karma dashboard".

    Four checks, none relying on the user-tunable CORS allowlist:

    1. ``Host`` -- when present it must be a loopback host. A request through a
       proxy on a public domain (``curl https://karma.example.com/...``) carries
       ``Host: karma.example.com`` and is rejected. This is the check that
       covers non-browser callers the Sec-Fetch/Origin checks miss.
    2. ``Sec-Fetch-Site`` -- browser-set, not forgeable from page script. A
       genuine cross-site request (a random website) is rejected; CORS merely
       happened to block it before.
    3. ``Origin`` -- when present it must be a loopback origin. Stops DNS
       rebinding, where a rebound page looks same-origin to Sec-Fetch-Site but
       still carries its real, non-local Origin.
    4. The TCP peer must be loopback. Defence in depth; not relied on alone,
       since behind a same-host proxy every request presents as 127.0.0.1.
    """
    from urllib.parse import urlsplit  # noqa: PLC0415

    host = request.headers.get("host")
    if host:
        # urlsplit needs a scheme to populate .hostname; strips the port and
        # unwraps [::1] for us.
        hostname = urlsplit(f"//{host}").hostname
        if hostname not in _LOOPBACK_HOSTS:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="The desktop installer can only be used from this machine.",
            )

    fetch_site = request.headers.get("sec-fetch-site")
    if fetch_site is not None and fetch_site not in _ALLOWED_FETCH_SITES:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This action must originate from the Karma dashboard on this machine.",
        )

    origin = request.headers.get("origin")
    if origin and urlsplit(origin).hostname not in _LOOPBACK_HOSTS:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This action must originate from the Karma dashboard on this machine.",
        )

    peer = request.client.host if request.client else None
    if peer and peer.startswith("::ffff:"):  # IPv4-mapped IPv6 on a dual-stack bind
        peer = peer[len("::ffff:") :]
    if peer not in _LOOPBACK_PEERS:
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
    core = _load_core()
    supported = sys.platform in ("darwin", "win32")
    installed = False
    install_path: Optional[str] = None
    autostart = False

    if sys.platform == "darwin":
        from karma_desktop import installer_macos as mac  # noqa: PLC0415

        # Only *our* bundle counts as installed. "Karma" is not a rare product
        # name; reporting an unrelated vendor's Karma.app as installed would let
        # Reinstall/Remove act on it, and uninstall() already refuses to touch a
        # foreign bundle -- so status must apply the same bundle-id check.
        for candidate in _macos_app_paths():
            if candidate.exists() and mac._is_our_bundle(candidate):
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
    core = _load_core()
    repo = core.repo_root()
    python = core.stable_python()
    messages: List[str] = []

    if sys.platform == "darwin":
        from karma_desktop import installer_macos as mac  # noqa: PLC0415

        # Prefer /Applications, but fall back to the user's own folder rather
        # than failing when the volume is not writable. A FileExistsError
        # (a foreign Karma.app is in the way) is a real conflict, not a
        # permissions problem, so it must not trigger the fallback.
        app_dir = Path("/Applications")
        try:
            app = mac.install_app(repo, python, app_dir, core.WEB_PORT, core.API_PORT)
        except FileExistsError as exc:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
        except (PermissionError, OSError):
            app_dir = Path.home() / "Applications"
            app_dir.mkdir(parents=True, exist_ok=True)
            try:
                app = mac.install_app(repo, python, app_dir, core.WEB_PORT, core.API_PORT)
            except FileExistsError as exc:
                raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
            messages.append(
                "No permission to write to /Applications; installed to ~/Applications instead."
            )
        messages.append(f"Installed {app}")

        # Pinning the launcher only makes sense when autostart is off. With
        # autostart on the servers are already up at login, so the launcher is
        # never clicked and its tile would just fight the PWA icon -- so skip
        # the pin (and unpin any stale launcher tile) in that state, regardless
        # of what the request asked for.
        if body.dock and not mac.autostart_enabled():
            if mac.add_to_dock(app):
                messages.append("Pinned to the Dock.")
            else:
                messages.append("Could not update the Dock; drag the app there manually.")
        elif body.dock and mac.autostart_enabled():
            mac.unpin_from_dock()
            messages.append(
                "Autostart is on, so the launcher was not pinned; pin the "
                "browser-installed Karma instead."
            )
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
    core = _load_core()
    repo = core.repo_root()
    python = core.stable_python()
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
        # Autostart-on had unpinned the launcher (the PWA was the icon). Turning
        # it off means the PWA can no longer start the servers -- but do NOT
        # silently re-pin: there is no stored record that the user ever wanted a
        # launcher tile (install offers pinning as its own opt-in switch), and
        # forcing one back would both surprise them and restart the Dock for a
        # setting they didn't touch. Point them at the pin control instead; it
        # reappears in the UI as soon as autostart is off.
        if sys.platform == "darwin":
            messages.append(
                "The PWA can no longer start the servers on its own. To get a "
                "click-to-start icon back, turn on “Pin the launcher to the "
                "Dock” and reinstall."
            )
        messages.append(
            "Servers already running were left alone; close them if you want them stopped now."
        )

    # ``enabled`` reflects whether the login item is installed on disk -- which
    # is what determines login behaviour. It does not assert that launchctl
    # accepted it this session, nor whether the OS has since disabled it in
    # Login Items (see autostart_enabled()); those are not readable here.
    return AutostartResult(ok=True, enabled=backend.autostart_enabled(), messages=messages)


def _uninstall_sync() -> InstallResult:
    _load_core()
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
    """Whether the desktop launcher is installed on this machine.

    Read-only, but note it returns local paths (``repo_root``, ``install_path``)
    that include the username, and it is a GET -- which browsers send with no
    ``Origin`` header. Any local page that is same-site to this API (see
    ``_require_local``) can therefore read this status. That is the same
    "anything local" surface the mutating verbs sit behind, minus the Origin
    check they get for free; the leak is low-value on a single-user machine but
    is real, so this endpoint carries nothing more sensitive than paths.
    """
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
            detail="Install failed. See the server logs for details.",
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
            detail="Could not change the autostart setting. See the server logs for details.",
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
            detail="Uninstall failed. See the server logs for details.",
        ) from exc
