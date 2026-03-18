"""
PairingService — permanent, deterministic pairing codes using base32.

Codes encode "{member_tag}:{device_id}" via base32, strip padding, and
group the result into 4-character blocks separated by dashes.

Example output: KXRM-4HPQ-ANVY-...
"""

import base64
from typing import Optional

from pydantic import BaseModel


class PairingInfo(BaseModel):
    """Decoded pairing information extracted from a pairing code."""

    model_config = {"frozen": True}

    member_tag: str
    device_id: str


class PairingService:
    """Generates and validates permanent, deterministic pairing codes."""

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def generate_code(self, member_tag: str, device_id: str) -> str:
        """Return a deterministic pairing code for (member_tag, device_id).

        The code is a sequence of 4-character uppercase alphanumeric blocks
        separated by dashes, e.g. "KXRM-4HPQ-ANVY".
        """
        payload = f"{member_tag}:{device_id}"
        encoded = base64.b32encode(payload.encode()).decode()
        # Strip base32 padding characters
        encoded = encoded.rstrip("=")
        # Group into 4-char blocks
        blocks = [encoded[i : i + 4] for i in range(0, len(encoded), 4)]
        return "-".join(blocks)

    def validate_code(self, code: str) -> PairingInfo:
        """Decode a pairing code and return PairingInfo.

        Raises ValueError if the code is invalid or cannot be decoded.
        """
        if not code:
            raise ValueError("Pairing code must not be empty")

        # Normalize: remove dashes, uppercase
        normalized = code.replace("-", "").upper()
        if not normalized:
            raise ValueError("Pairing code contains no data")

        # Re-add base32 padding
        remainder = len(normalized) % 8
        if remainder:
            normalized += "=" * (8 - remainder)

        try:
            decoded = base64.b32decode(normalized).decode()
        except Exception as exc:
            raise ValueError(f"Invalid pairing code: {exc}") from exc

        # Split on first colon to allow colons in device_id
        if ":" not in decoded:
            raise ValueError("Pairing code does not contain expected separator")

        member_tag, device_id = decoded.split(":", 1)
        return PairingInfo(member_tag=member_tag, device_id=device_id)
