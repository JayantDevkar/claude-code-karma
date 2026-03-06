"""Syncthing proxy service for the Karma API."""
from __future__ import annotations

import asyncio
import logging
import sys
from functools import partial
from pathlib import Path
from typing import Any, Optional

import requests

# Add CLI to path for SyncthingClient import
CLI_PATH = Path(__file__).parent.parent.parent / "cli"
if str(CLI_PATH) not in sys.path:
    sys.path.insert(0, str(CLI_PATH))

try:
    from karma.syncthing import SyncthingClient, read_local_api_key
except ImportError:
    SyncthingClient = None  # type: ignore[assignment,misc]
    read_local_api_key = None  # type: ignore[assignment]

logger = logging.getLogger(__name__)


class SyncthingNotRunning(Exception):
    """Raised when Syncthing daemon is not reachable."""


async def run_sync(func: Any, *args: Any, **kwargs: Any) -> Any:
    """Run a synchronous function in an executor to avoid blocking the event loop."""
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, partial(func, *args, **kwargs))


class SyncthingProxy:
    """Service layer wrapping SyncthingClient for use by the FastAPI API."""

    def __init__(self) -> None:
        self._client: Optional[Any] = None
        self._try_connect()

    def _try_connect(self) -> None:
        """Attempt to create and validate a SyncthingClient."""
        if SyncthingClient is None:
            logger.warning("SyncthingClient not available (import failed)")
            return

        # Try to read API key from sync-config.json first, then local config
        api_key: Optional[str] = None
        try:
            from config import settings

            config_path = settings.karma_base / "sync-config.json"
            if config_path.exists():
                import json

                with open(config_path) as f:
                    data = json.load(f)
                syncthing_cfg = data.get("syncthing", {})
                api_key = syncthing_cfg.get("api_key") if isinstance(syncthing_cfg, dict) else None
        except Exception as e:
            logger.debug("Could not read sync-config.json: %s", e)

        if api_key is None and read_local_api_key is not None:
            try:
                api_key = read_local_api_key()
            except Exception as e:
                logger.debug("read_local_api_key() failed: %s", e)

        try:
            client = SyncthingClient(api_key=api_key)
            if client.is_running():
                self._client = client
            else:
                logger.debug("Syncthing is not running")
        except Exception as e:
            logger.debug("Failed to connect to Syncthing: %s", e)

    def _require_client(self) -> Any:
        """Return the client or raise SyncthingNotRunning."""
        if self._client is None:
            raise SyncthingNotRunning("Syncthing daemon is not reachable")
        return self._client

    def detect(self) -> dict:
        """Return Syncthing detection info: installed/running/version/device_id."""
        if SyncthingClient is None or self._client is None:
            installed = SyncthingClient is not None
            return {"installed": installed, "running": False}

        client = self._client
        if not client.is_running():
            return {"installed": True, "running": False}

        try:
            resp = requests.get(
                f"{client.api_url}/rest/system/status",
                headers=client.headers,
                timeout=10,
            )
            resp.raise_for_status()
            data = resp.json()
            return {
                "installed": True,
                "running": True,
                "version": data.get("version"),
                "device_id": data.get("myID"),
            }
        except Exception as e:
            logger.warning("Failed to get Syncthing system status: %s", e)
            return {"installed": True, "running": True, "version": None, "device_id": None}

    def get_devices(self) -> list[dict]:
        """Return all configured devices with their connection status."""
        client = self._require_client()
        config = client._get_config()
        connections = client.get_connections()

        result = []
        for device in config.get("devices", []):
            device_id = device.get("deviceID", "")
            conn = connections.get(device_id, {})
            result.append(
                {
                    "device_id": device_id,
                    "name": device.get("name", ""),
                    "connected": conn.get("connected", False),
                    "address": conn.get("address"),
                    **{k: v for k, v in device.items() if k not in ("deviceID", "name")},
                }
            )
        return result

    def add_device(self, device_id: str, name: str) -> dict:
        """Pair with a remote device."""
        client = self._require_client()
        client.add_device(device_id, name)
        return {"ok": True, "device_id": device_id, "name": name}

    def remove_device(self, device_id: str) -> dict:
        """Remove a paired device."""
        client = self._require_client()
        client.remove_device(device_id)
        return {"ok": True, "device_id": device_id}

    def get_folder_status(self) -> list[dict]:
        """Return all configured folders."""
        client = self._require_client()
        return client.get_folders()

    def get_events(self, since: int = 0, limit: int = 100) -> list[dict]:
        """Return recent Syncthing events."""
        client = self._require_client()
        resp = requests.get(
            f"{client.api_url}/rest/events",
            headers=client.headers,
            params={"since": since, "limit": limit},
            timeout=10,
        )
        resp.raise_for_status()
        return resp.json()

    def get_bandwidth(self) -> dict:
        """Return current bandwidth totals from connections endpoint."""
        client = self._require_client()
        resp = requests.get(
            f"{client.api_url}/rest/system/connections",
            headers=client.headers,
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()
        total = data.get("total", {})
        return {
            "upload_total": total.get("outBytesTotal", 0),
            "download_total": total.get("inBytesTotal", 0),
            "upload_rate": total.get("rateSendBps", 0),
            "download_rate": total.get("rateRecvBps", 0),
        }
