"""The desktop-app endpoints write an executable bundle and register a login
item, so the local/CSRF guard is security-critical. These tests exercise
``_require_local`` directly against forged request shapes.
"""

from __future__ import annotations

import sys
import types
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

# The desktop-app router pulls in FastAPI. The models-only test job installs no
# web deps and collects every tests/*.py, so skip this whole module there rather
# than failing collection with a bare ImportError.
pytest.importorskip("fastapi")

from fastapi import HTTPException  # noqa: E402

from routers.desktop_app import _require_local  # noqa: E402


def _request(headers=None, peer="127.0.0.1"):
    """Minimal stand-in for a Starlette Request (lower-cased header keys)."""
    client = types.SimpleNamespace(host=peer) if peer is not None else None
    return types.SimpleNamespace(headers=headers or {}, client=client)


def _allowed(headers=None, peer="127.0.0.1"):
    # Raises HTTPException if rejected; returns None on success.
    _require_local(_request(headers, peer))


def _rejected(headers=None, peer="127.0.0.1"):
    with pytest.raises(HTTPException) as exc:
        _require_local(_request(headers, peer))
    assert exc.value.status_code == 403


def test_plain_local_request_allowed():
    """curl / the address bar send no Origin and no Sec-Fetch-Site."""
    _allowed()


def test_same_site_dashboard_request_allowed():
    """The dashboard on :5180 calling the API on :8020 is same-site."""
    _allowed(
        {"origin": "http://localhost:5180", "sec-fetch-site": "same-site"},
    )


def test_ipv4_mapped_loopback_peer_allowed():
    """A dual-stack bind can present loopback as ::ffff:127.0.0.1."""
    _allowed(peer="::ffff:127.0.0.1")


def test_ipv6_loopback_peer_allowed():
    _allowed(peer="::1")


def test_loopback_cross_site_pairing_allowed():
    """127.0.0.1 and localhost are different *sites*, so the dashboard on one
    calling the API on the other is Sec-Fetch-Site: cross-site -- but it is
    legitimate loopback traffic (both are supported, CORS-allowed entry points),
    and a loopback Origin vouches for it. It must be allowed, not 403'd."""
    _allowed(
        {
            "host": "localhost:8020",
            "origin": "http://127.0.0.1:5180",
            "sec-fetch-site": "cross-site",
        }
    )
    _allowed(
        {
            "host": "127.0.0.1:8020",
            "origin": "http://localhost:5180",
            "sec-fetch-site": "cross-site",
        }
    )


def test_cross_site_request_rejected():
    """A random website's request carries Sec-Fetch-Site: cross-site.

    This is rejected regardless of the CORS allowlist -- the whole point, since
    CLAUDE_KARMA_CORS_ORIGINS=["*"] is a documented dev setting.
    """
    _rejected({"origin": "http://evil.com", "sec-fetch-site": "cross-site"})


def test_dns_rebinding_shape_rejected():
    """A rebound page looks same-origin to Sec-Fetch-Site but still carries a
    non-loopback Origin."""
    _rejected({"origin": "http://evil.com", "sec-fetch-site": "same-origin"})


def test_non_loopback_peer_rejected():
    _rejected(peer="10.0.0.5")


def test_no_client_rejected():
    _rejected(peer=None)


def test_proxied_public_host_rejected():
    """A non-browser client through a same-host proxy on a public domain sends
    no Sec-Fetch-Site and no Origin, and presents a loopback peer -- the Host
    header is the only thing that gives it away."""
    _rejected({"host": "karma.example.com"})


def test_loopback_host_allowed():
    _allowed({"host": "localhost:8020"})
    _allowed({"host": "127.0.0.1:8020"})
    _allowed({"host": "[::1]:8020"})


# ---------------------------------------------------------------------------
# macOS bundle-identity: status and autostart must not act on a foreign app
# ---------------------------------------------------------------------------


@pytest.mark.skipif(sys.platform != "darwin", reason="macOS bundle layout")
def test_status_ignores_a_foreign_karma_bundle(tmp_path, monkeypatch):
    """A same-named vendor Karma.app must not be reported as installed -- only a
    bundle carrying our identifier counts, matching uninstall()'s refusal to
    touch a foreign one."""
    import plistlib

    import routers.desktop_app as da

    da._load_core()
    from karma_desktop import installer_macos as mac

    foreign = tmp_path / "Karma.app" / "Contents"
    foreign.mkdir(parents=True)
    with open(foreign / "Info.plist", "wb") as fh:
        plistlib.dump({"CFBundleIdentifier": "com.someoneelse.karma"}, fh)

    monkeypatch.setattr(da, "_macos_app_paths", lambda: [tmp_path / "Karma.app"])
    monkeypatch.setattr(mac, "autostart_enabled", lambda: False)

    status = da._status_sync()
    assert status.installed is False
    assert status.install_path is None


@pytest.mark.skipif(sys.platform != "darwin", reason="Dock is macOS-only")
def test_disabling_autostart_does_not_repin_the_dock(monkeypatch):
    """Turning autostart off must not silently re-pin a launcher tile (and
    restart the Dock) the user may never have asked for."""
    import routers.desktop_app as da

    da._load_core()
    from karma_desktop import installer_macos as mac

    monkeypatch.setattr(mac, "uninstall_autostart", lambda: True)
    monkeypatch.setattr(mac, "autostart_enabled", lambda: False)
    pinned = {"called": False}
    monkeypatch.setattr(
        mac, "add_to_dock", lambda *a, **k: pinned.__setitem__("called", True) or True
    )

    result = da._set_autostart_sync(False)
    assert pinned["called"] is False
    assert result.enabled is False


def test_load_core_appends_scripts_without_shadowing():
    """scripts/ must go to the END of sys.path, so its implicit ``tests``
    namespace package can't outrank api/tests for the process's lifetime."""
    import routers.desktop_app as da

    da._load_core()
    assert str(da.SCRIPTS_DIR) in sys.path
    assert sys.path[0] != str(da.SCRIPTS_DIR)
