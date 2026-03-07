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
        """Return the client or raise SyncthingNotRunning. Retries connection if needed."""
        if self._client is None:
            self._try_connect()
        if self._client is None:
            raise SyncthingNotRunning("Syncthing daemon is not reachable")
        return self._client

    def detect(self) -> dict:
        """Return Syncthing detection info: installed/running/version/device_id."""
        if SyncthingClient is None:
            return {"installed": False, "running": False}
        if self._client is None:
            self._try_connect()
        if self._client is None:
            return {"installed": True, "running": False}

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
            return {"installed": True, "running": False, "version": None, "device_id": None}

    def get_devices(self) -> list[dict]:
        """Return all configured devices with their connection status."""
        client = self._require_client()
        config = client._get_config()

        # Fetch raw connections response to get both per-device and total stats
        resp = requests.get(
            f"{client.api_url}/rest/system/connections",
            headers=client.headers,
            timeout=10,
        )
        resp.raise_for_status()
        conn_data = resp.json()
        connections = conn_data.get("connections", {})
        total = conn_data.get("total", {})

        # Detect self device ID
        self_id = None
        try:
            status_resp = requests.get(
                f"{client.api_url}/rest/system/status",
                headers=client.headers,
                timeout=10,
            )
            if status_resp.ok:
                self_id = status_resp.json().get("myID")
        except Exception:
            pass

        result = []
        for device in config.get("devices", []):
            device_id = device.get("deviceID", "")
            conn = connections.get(device_id, {})
            is_self = self_id and device_id == self_id
            result.append(
                {
                    "device_id": device_id,
                    "name": device.get("name", ""),
                    "connected": conn.get("connected", False) or is_self,
                    "address": conn.get("address"),
                    "type": conn.get("type"),
                    "crypto": conn.get("crypto"),
                    # Self device: show aggregate totals; remote: show per-device
                    "in_bytes_total": total.get("inBytesTotal", 0) if is_self else conn.get("inBytesTotal", 0),
                    "out_bytes_total": total.get("outBytesTotal", 0) if is_self else conn.get("outBytesTotal", 0),
                    "is_self": bool(is_self),
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

    def add_folder(
        self,
        folder_id: str,
        path: str,
        devices: list[str],
        folder_type: str = "sendonly",
    ) -> dict:
        """Create a shared folder in Syncthing."""
        client = self._require_client()
        client.add_folder(folder_id, path, devices, folder_type=folder_type)
        return {"ok": True, "folder_id": folder_id, "path": path}

    def get_folder_status(self) -> list[dict]:
        """Return all configured folders with their sync status."""
        client = self._require_client()
        folders = client.get_folders()
        result = []
        for folder in folders:
            folder_id = folder.get("id", "")
            entry = dict(folder)
            # Enrich with actual sync stats from /rest/db/status
            try:
                status_resp = requests.get(
                    f"{client.api_url}/rest/db/status",
                    headers=client.headers,
                    params={"folder": folder_id},
                    timeout=5,
                )
                if status_resp.ok:
                    status = status_resp.json()
                    entry["globalFiles"] = status.get("globalFiles", 0)
                    entry["globalBytes"] = status.get("globalBytes", 0)
                    entry["localFiles"] = status.get("localFiles", 0)
                    entry["localBytes"] = status.get("localBytes", 0)
                    entry["needFiles"] = status.get("needFiles", 0)
                    entry["needBytes"] = status.get("needBytes", 0)
                    entry["state"] = status.get("state", "unknown")
                    entry["inSyncBytes"] = status.get("inSyncBytes", 0)
                    entry["inSyncFiles"] = status.get("inSyncFiles", 0)
            except Exception:
                pass
            result.append(entry)
        return result

    def get_events(self, since: int = 0, limit: int = 100) -> list[dict]:
        """Return recent Syncthing events.

        Syncthing's /rest/events is a long-polling endpoint that blocks when
        since > 0 until new events arrive. We pass timeout=1 (seconds) to
        Syncthing so it returns quickly with an empty list if nothing new.
        """
        client = self._require_client()
        params: dict = {"since": since, "limit": limit}
        if since > 0:
            params["timeout"] = 1
        resp = requests.get(
            f"{client.api_url}/rest/events",
            headers=client.headers,
            params=params,
            timeout=5,
        )
        resp.raise_for_status()
        return resp.json()

    def rescan_folder(self, folder_id: str) -> dict:
        """Trigger an immediate rescan of a specific folder."""
        client = self._require_client()
        resp = requests.post(
            f"{client.api_url}/rest/db/scan",
            headers=client.headers,
            params={"folder": folder_id},
            timeout=10,
        )
        resp.raise_for_status()
        return {"ok": True, "folder": folder_id}

    def rescan_all(self) -> dict:
        """Trigger an immediate rescan of all folders."""
        client = self._require_client()
        folders = client.get_folders()
        scanned = []
        for folder in folders:
            folder_id = folder.get("id", "")
            if not folder_id:
                continue
            try:
                requests.post(
                    f"{client.api_url}/rest/db/scan",
                    headers=client.headers,
                    params={"folder": folder_id},
                    timeout=10,
                )
                scanned.append(folder_id)
            except Exception:
                pass
        return {"ok": True, "scanned": scanned}

    def get_pending_devices(self) -> dict:
        """Get devices trying to connect that aren't configured yet."""
        client = self._require_client()
        return client.get_pending_devices()

    def get_pending_folders_for_ui(
        self, known_devices: dict[str, tuple[str, str]]
    ) -> list[dict]:
        """Get pending folder offers filtered for known team members.

        Args:
            known_devices: {device_id: (member_name, team_name)}

        Returns:
            List of pending offers from known members with karma- prefix only.
        """
        client = self._require_client()
        pending = client.get_pending_folders()
        existing_ids = {f["id"] for f in client.get_folders()}
        result = []

        for folder_id, info in pending.items():
            if not folder_id.startswith("karma-"):
                continue
            if folder_id in existing_ids:
                continue
            for device_id, offer in info.get("offeredBy", {}).items():
                if device_id not in known_devices:
                    continue
                member_name, team_name = known_devices[device_id]
                result.append({
                    "folder_id": folder_id,
                    "from_device": device_id,
                    "from_member": member_name,
                    "from_team": team_name,
                    "offered_at": offer.get("time"),
                })
        return result

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
