"""Syncthing REST API wrapper."""

from typing import Optional

import requests


class SyncthingClient:
    """Wraps the Syncthing REST API for device/folder management."""

    def __init__(self, api_url: str = "http://127.0.0.1:8384", api_key: Optional[str] = None):
        self.api_url = api_url.rstrip("/")
        self.headers = {}
        if api_key:
            self.headers["X-API-Key"] = api_key

    def is_running(self) -> bool:
        """Check if Syncthing is running and accessible."""
        try:
            resp = requests.get(
                f"{self.api_url}/rest/system/status",
                headers=self.headers,
                timeout=5,
            )
            return resp.status_code == 200
        except requests.ConnectionError:
            return False

    def get_device_id(self) -> str:
        """Get this device's Syncthing Device ID."""
        resp = requests.get(
            f"{self.api_url}/rest/system/status",
            headers=self.headers,
            timeout=10,
        )
        resp.raise_for_status()
        return resp.json()["myID"]

    def get_connections(self) -> dict:
        """Check which devices are connected."""
        resp = requests.get(
            f"{self.api_url}/rest/system/connections",
            headers=self.headers,
            timeout=10,
        )
        resp.raise_for_status()
        return resp.json()["connections"]

    def add_device(self, device_id: str, name: str) -> None:
        """Pair with a remote device."""
        config = self._get_config()
        config["devices"].append({
            "deviceID": device_id,
            "name": name,
            "autoAcceptFolders": False,
        })
        self._set_config(config)

    def add_folder(
        self,
        folder_id: str,
        path: str,
        devices: list,
        folder_type: str = "sendonly",
    ) -> None:
        """Create a shared folder with specified devices."""
        config = self._get_config()
        config["folders"].append({
            "id": folder_id,
            "path": path,
            "devices": [{"deviceID": d} for d in devices],
            "type": folder_type,
        })
        self._set_config(config)

    def remove_device(self, device_id: str) -> None:
        """Remove a paired device."""
        config = self._get_config()
        config["devices"] = [d for d in config["devices"] if d["deviceID"] != device_id]
        self._set_config(config)

    def remove_folder(self, folder_id: str) -> None:
        """Remove a shared folder."""
        config = self._get_config()
        config["folders"] = [f for f in config["folders"] if f["id"] != folder_id]
        self._set_config(config)

    def _get_config(self) -> dict:
        resp = requests.get(f"{self.api_url}/rest/config", headers=self.headers, timeout=10)
        resp.raise_for_status()
        return resp.json()

    def _set_config(self, config: dict) -> None:
        resp = requests.put(
            f"{self.api_url}/rest/config",
            json=config,
            headers=self.headers,
            timeout=10,
        )
        resp.raise_for_status()
