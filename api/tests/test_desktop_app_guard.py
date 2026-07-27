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
