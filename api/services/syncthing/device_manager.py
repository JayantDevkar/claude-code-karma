"""
DeviceManager — high-level operations on Syncthing device configuration.

Wraps SyncthingClient to provide idempotent pair/unpair operations and
connection status queries.
"""

from typing import List

from services.syncthing.client import SyncthingClient


class DeviceManager:
    """Manages Syncthing device pairing and connection status."""

    def __init__(self, client: SyncthingClient) -> None:
        self._client = client

    # ------------------------------------------------------------------
    # Pairing
    # ------------------------------------------------------------------

    async def pair(self, device_id: str) -> None:
        """Add device to Syncthing config. Overwrites if already present."""
        device = {
            "deviceID": device_id,
            "name": device_id[:8],
            "addresses": ["dynamic"],
            "compression": "metadata",
            "certName": "",
            "introducer": False,
            "skipIntroductionRemovals": False,
            "introducedBy": "",
            "paused": False,
            "allowedNetworks": [],
            "autoAcceptFolders": False,
            "maxSendKbps": 0,
            "maxRecvKbps": 0,
            "ignoredFolders": [],
            "encryptionPassword": "",
        }
        await self._client.put_config_device(device)

    async def unpair(self, device_id: str) -> None:
        """Remove device from Syncthing config."""
        await self._client.delete_config_device(device_id)

    async def ensure_paired(self, device_id: str) -> None:
        """Pair the device only if it is not already in the config (idempotent)."""
        existing = await self._client.get_config_devices()
        existing_ids = {d["deviceID"] for d in existing}
        if device_id not in existing_ids:
            await self.pair(device_id)

    # ------------------------------------------------------------------
    # Connection status
    # ------------------------------------------------------------------

    async def is_connected(self, device_id: str) -> bool:
        """Return True if the device is currently connected."""
        data = await self._client.get_connections()
        connections = data.get("connections", {})
        entry = connections.get(device_id)
        if entry is None:
            return False
        return bool(entry.get("connected", False))

    async def list_connected(self) -> List[str]:
        """Return list of device IDs that are currently connected."""
        data = await self._client.get_connections()
        connections = data.get("connections", {})
        return [
            device_id
            for device_id, info in connections.items()
            if info.get("connected", False)
        ]
