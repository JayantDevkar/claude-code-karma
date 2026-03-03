"""IPFS subprocess wrapper for Kubo CLI."""

import json
import re
import subprocess
from typing import Optional

_SAFE_KEY_RE = re.compile(r"^[a-zA-Z0-9_\-]+$")


def _validate_cid(cid: str) -> str:
    """Reject empty strings and strings starting with '-' to prevent flag injection."""
    if not cid or cid.startswith("-"):
        raise ValueError(f"Invalid CID: {cid!r}")
    return cid


class IPFSNotRunningError(Exception):
    """Raised when IPFS daemon is not running or not installed."""
    pass


class IPFSClient:
    """Wraps the `ipfs` CLI binary via subprocess calls."""

    def __init__(self, api_url: str = "http://127.0.0.1:5001"):
        self.api_url = api_url

    def _run(self, args: list[str], check: bool = True, timeout: int = 120) -> subprocess.CompletedProcess:
        """Run an ipfs command."""
        cmd = ["ipfs"] + args
        return subprocess.run(cmd, capture_output=True, text=True, check=check, timeout=timeout)

    def is_running(self) -> bool:
        """Check if IPFS daemon is running and accessible."""
        try:
            result = self._run(["id"], check=False)
            return result.returncode == 0
        except FileNotFoundError:
            return False

    def id(self) -> dict:
        """Get IPFS node identity info."""
        result = self._run(["id", "--format=json"])
        return json.loads(result.stdout)

    def add(self, path: str, recursive: bool = True) -> str:
        """Add file/directory to IPFS. Returns CID."""
        args = ["add", "-Q"]  # -Q = quiet, only final CID
        if recursive:
            args.append("-r")
        args.append("--")
        args.append(path)
        result = self._run(args)
        return result.stdout.strip()

    def get(self, cid: str, output_path: str) -> None:
        """Fetch content by CID to local path."""
        _validate_cid(cid)
        self._run(["get", "--", cid, "-o", output_path])

    def pin_add(self, cid: str) -> None:
        """Pin a CID to prevent garbage collection."""
        _validate_cid(cid)
        self._run(["pin", "add", cid])

    def pin_ls(self) -> dict:
        """List pinned CIDs."""
        result = self._run(["pin", "ls", "--type=recursive", "--enc=json"])
        data = json.loads(result.stdout)
        return data.get("Keys", {})

    def name_publish(self, cid: str, key: Optional[str] = None) -> str:
        """Publish CID to IPNS. Returns publish confirmation."""
        _validate_cid(cid)
        args = ["name", "publish", f"/ipfs/{cid}"]
        if key:
            if not _SAFE_KEY_RE.match(key):
                raise ValueError(f"Invalid key name: {key!r}")
            args.extend(["--key", key])
        result = self._run(args)
        return result.stdout.strip()

    def name_resolve(self, ipns_key: str) -> str:
        """Resolve IPNS key to CID path. Returns /ipfs/Qm..."""
        if not ipns_key or ipns_key.startswith("-"):
            raise ValueError(f"Invalid IPNS key: {ipns_key!r}")
        result = self._run(["name", "resolve", "--", ipns_key])
        return result.stdout.strip()

    def key_gen(self, name: str) -> str:
        """Generate a new IPNS keypair. Returns key ID."""
        if not _SAFE_KEY_RE.match(name):
            raise ValueError(f"Invalid key name: {name!r}")
        result = self._run(["key", "gen", name])
        return result.stdout.strip()

    def key_list(self) -> list[dict]:
        """List all IPNS keys."""
        result = self._run(["key", "list", "-l", "--enc=json"])
        return json.loads(result.stdout).get("Keys", [])

    def swarm_peers(self) -> list[str]:
        """List connected swarm peers."""
        result = self._run(["swarm", "peers", "--enc=json"])
        data = json.loads(result.stdout)
        return [p.get("Peer", "") for p in data.get("Peers", [])]
