"""
PairingService — permanent, deterministic pairing codes using base64url.

Codes encode "{member_tag}:{device_id}" via base64url, strip padding, and
group the result into 6-character blocks separated by dashes.

Example output: amF5LW-1hY2Jv-b2suam-...

Backwards-compatible: validate_code() auto-detects old base32 codes (all
uppercase + digits) vs new base64url codes (mixed case).
"""

import base64

from pydantic import BaseModel


class PairingInfo(BaseModel):
    """Decoded pairing information extracted from a pairing code."""

    model_config = {"frozen": True}

    member_tag: str
    device_id: str


class PairingService:
    """Generates and validates permanent, deterministic pairing codes."""

    BLOCK_SIZE = 6

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def generate_code(self, member_tag: str, device_id: str) -> str:
        """Return a deterministic pairing code for (member_tag, device_id).

        The code is a sequence of 6-character blocks separated by dashes,
        using base64url encoding for ~22% shorter codes than base32.
        """
        payload = f"{member_tag}:{device_id}"
        encoded = base64.urlsafe_b64encode(payload.encode()).decode()
        encoded = encoded.rstrip("=")
        blocks = [encoded[i : i + self.BLOCK_SIZE] for i in range(0, len(encoded), self.BLOCK_SIZE)]
        return "-".join(blocks)

    def validate_code(self, code: str) -> PairingInfo:
        """Decode a pairing code and return PairingInfo.

        Auto-detects encoding format:
        - base64url (v2): contains lowercase letters
        - base32 (v1, legacy): all uppercase + digits

        Raises ValueError if the code is invalid or cannot be decoded.
        """
        if not code:
            raise ValueError("Pairing code must not be empty")

        normalized = code.replace("-", "").replace(" ", "").replace("\n", "").replace("\r", "").strip()
        if not normalized:
            raise ValueError("Pairing code contains no data")

        # Auto-detect: base64url uses lowercase; base32 is all uppercase + digits
        is_base64 = any(c.islower() or c in ("_",) for c in normalized)

        if is_base64:
            decoded = self._decode_base64url(normalized)
        else:
            decoded = self._decode_base32(normalized)

        if ":" not in decoded:
            raise ValueError("Pairing code does not contain expected separator")

        member_tag, device_id = decoded.split(":", 1)
        return PairingInfo(member_tag=member_tag, device_id=device_id)

    # ------------------------------------------------------------------
    # Private decoders
    # ------------------------------------------------------------------

    @staticmethod
    def _decode_base64url(normalized: str) -> str:
        """Decode a base64url-encoded pairing code (v2)."""
        pad = (4 - len(normalized) % 4) % 4
        padded = normalized + "=" * pad
        try:
            return base64.urlsafe_b64decode(padded).decode()
        except Exception as exc:
            raise ValueError(f"Invalid pairing code (base64url): {exc}") from exc

    @staticmethod
    def _decode_base32(normalized: str) -> str:
        """Decode a legacy base32-encoded pairing code (v1)."""
        normalized = normalized.upper()
        remainder = len(normalized) % 8
        if remainder:
            normalized += "=" * (8 - remainder)
        try:
            return base64.b32decode(normalized).decode()
        except Exception as exc:
            raise ValueError(f"Invalid pairing code (base32): {exc}") from exc
