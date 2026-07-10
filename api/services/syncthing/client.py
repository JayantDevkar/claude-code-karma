"""
SyncthingClient — pure HTTP wrapper for the Syncthing REST API.

No business logic lives here. Each method maps 1-to-1 to a Syncthing
REST endpoint. Callers (DeviceManager, FolderManager, etc.) add logic.
"""

from typing import Any, Dict, List, Optional

import httpx


class SyncthingClient:
    """Thin async HTTP client for the Syncthing REST API."""

    def __init__(self, api_url: str, api_key: str, timeout: float = 30.0) -> None:
        self.api_url = api_url.rstrip("/")
        self.api_key = api_key
        self.timeout = timeout

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _headers(self) -> Dict[str, str]:
        return {
            "X-API-Key": self.api_key,
            "Content-Type": "application/json",
        }

    async def _get(self, path: str, params: Optional[Dict[str, str]] = None) -> Any:
        async with httpx.AsyncClient(timeout=self.timeout) as http:
            resp = await http.get(
                self.api_url + path,
                headers=self._headers(),
                params=params,
            )
            resp.raise_for_status()
            return resp.json()

    async def _post(
        self,
        path: str,
        json: Optional[Any] = None,
        params: Optional[Dict[str, str]] = None,
    ) -> None:
        async with httpx.AsyncClient(timeout=self.timeout) as http:
            resp = await http.post(
                self.api_url + path,
                headers=self._headers(),
                json=json,
                params=params,
            )
            resp.raise_for_status()

    async def _put(self, path: str, json: Optional[Any] = None) -> None:
        async with httpx.AsyncClient(timeout=self.timeout) as http:
            resp = await http.put(
                self.api_url + path,
                headers=self._headers(),
                json=json,
            )
            resp.raise_for_status()

    async def _delete(
        self, path: str, params: Optional[Dict[str, str]] = None
    ) -> None:
        async with httpx.AsyncClient(timeout=self.timeout) as http:
            resp = await http.delete(
                self.api_url + path,
                headers=self._headers(),
                params=params,
            )
            resp.raise_for_status()

    # ------------------------------------------------------------------
    # System
    # ------------------------------------------------------------------

    async def get_system_status(self) -> Dict[str, Any]:
        """GET /rest/system/status — returns myID, uptime, etc."""
        return await self._get("/rest/system/status")

    async def get_connections(self) -> Dict[str, Any]:
        """GET /rest/system/connections — returns connected device map."""
        return await self._get("/rest/system/connections")

    # ------------------------------------------------------------------
    # Config (whole config)
    # ------------------------------------------------------------------

    async def get_config(self) -> Dict[str, Any]:
        """GET /rest/config — full Syncthing config."""
        return await self._get("/rest/config")

    async def post_config(self, config: Dict[str, Any]) -> None:
        """POST /rest/config — replace full config."""
        await self._post("/rest/config", json=config)

    # ------------------------------------------------------------------
    # Config — devices
    # ------------------------------------------------------------------

    async def get_config_devices(self) -> List[Dict[str, Any]]:
        """GET /rest/config/devices — list of configured devices."""
        return await self._get("/rest/config/devices")

    async def put_config_device(self, device: Dict[str, Any]) -> None:
        """PUT /rest/config/devices/{id} — add or update a single device."""
        device_id = device["deviceID"]
        await self._put(f"/rest/config/devices/{device_id}", json=device)

    async def delete_config_device(self, device_id: str) -> None:
        """DELETE /rest/config/devices/{device_id} — remove a device."""
        await self._delete(f"/rest/config/devices/{device_id}")

    # ------------------------------------------------------------------
    # Config — folders
    # ------------------------------------------------------------------

    async def get_config_folders(self) -> List[Dict[str, Any]]:
        """GET /rest/config/folders — list of configured folders."""
        return await self._get("/rest/config/folders")

    async def put_config_folder(self, folder: Dict[str, Any]) -> None:
        """PUT /rest/config/folders/{id} — add or update a single folder."""
        folder_id = folder["id"]
        await self._put(f"/rest/config/folders/{folder_id}", json=folder)

    async def delete_config_folder(self, folder_id: str) -> None:
        """DELETE /rest/config/folders/{folder_id} — remove a folder."""
        await self._delete(f"/rest/config/folders/{folder_id}")

    # ------------------------------------------------------------------
    # Pending (cluster)
    # ------------------------------------------------------------------

    async def get_pending_devices(self) -> Dict[str, Any]:
        """GET /rest/cluster/pending/devices — devices requesting connection."""
        return await self._get("/rest/cluster/pending/devices")

    async def dismiss_pending_device(self, device_id: str) -> None:
        """DELETE /rest/cluster/pending/devices?device={device_id} — dismiss a pending device."""
        await self._delete("/rest/cluster/pending/devices", params={"device": device_id})

    async def get_pending_folders(self) -> Dict[str, Any]:
        """GET /rest/cluster/pending/folders — folders offered by peers."""
        return await self._get("/rest/cluster/pending/folders")

    async def dismiss_pending_folder(self, folder_id: str, device_id: str) -> None:
        """DELETE /rest/cluster/pending/folders?folder={id}&device={id} — dismiss a pending folder."""
        await self._delete(
            "/rest/cluster/pending/folders",
            params={"folder": folder_id, "device": device_id},
        )

    # ------------------------------------------------------------------
    # Database / folder ops
    # ------------------------------------------------------------------

    async def get_folder_status(self, folder_id: str) -> Dict[str, Any]:
        """GET /rest/db/status?folder={folder_id} — folder sync status."""
        return await self._get("/rest/db/status", params={"folder": folder_id})

    async def post_folder_rescan(self, folder_id: str) -> None:
        """POST /rest/db/scan?folder={folder_id} — trigger rescan."""
        await self._post("/rest/db/scan", params={"folder": folder_id})
