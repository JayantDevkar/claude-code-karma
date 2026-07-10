"""Read Syncthing API key from local config file."""

import subprocess
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Optional


def read_local_api_key() -> Optional[str]:
    """Auto-detect the Syncthing API key from the local config file."""
    # Ask Syncthing itself where its config lives
    try:
        result = subprocess.run(
            ["syncthing", "paths"],
            capture_output=True, text=True, timeout=5,
        )
        for line in result.stdout.splitlines():
            line = line.strip()
            if line.endswith("config.xml"):
                config_path = Path(line)
                if config_path.exists():
                    tree = ET.parse(config_path)
                    key = tree.getroot().findtext(".//apikey")
                    return key or None
    except (subprocess.SubprocessError, FileNotFoundError, ET.ParseError):
        pass

    # Fallback: try known platform locations
    candidates = [
        Path.home() / "Library" / "Application Support" / "Syncthing" / "config.xml",
        Path.home() / ".local" / "share" / "syncthing" / "config.xml",
        Path.home() / ".config" / "syncthing" / "config.xml",
    ]
    for path in candidates:
        if path.exists():
            try:
                tree = ET.parse(path)
                key = tree.getroot().findtext(".//apikey")
                return key or None
            except ET.ParseError:
                continue
    return None
