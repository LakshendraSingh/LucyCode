"""
Setup script to register the Chrome Native Messaging host.
"""

from __future__ import annotations

import json
import os
import platform
import sys
from pathlib import Path


def get_registration_dir() -> Path:
    """Get the target directory for Chrome native messaging host manifest based on OS."""
    system = platform.system()
    if system == "Darwin":
        return Path("~/Library/Application Support/Google/Chrome/NativeMessagingHosts").expanduser()
    elif system == "Linux":
        return Path("~/.config/google-chrome/NativeMessagingHosts").expanduser()
    elif system == "Windows":
        # Usually requires a registry key, but local AppData sometimes works:
        # For full implementation on Windows, registry HKLM or HKCU is preferred.
        # Fallback to AppData for now.
        return Path(os.getenv("LOCALAPPDATA", "~")) / "Google" / "Chrome" / "User Data" / "NativeMessagingHosts"
    return Path(".")


def install_host():
    """Install the native messaging host manifest."""
    host_name = "com.lucycode.cli"
    
    # Path to the executable script (must be an absolute path)
    script_path = Path(__file__).parent / "native_host.py"
    
    manifest = {
        "name": host_name,
        "description": "LucyCode Chrome Integration",
        "path": sys.executable + f" {script_path.resolve()}",
        "type": "stdio",
        "allowed_origins": [
            "chrome-extension://knldjmfmopnpolkbohjnmigbcfknohoh/" # Dummy extension ID
        ]
    }
    
    target_dir = get_registration_dir()
    target_dir.mkdir(parents=True, exist_ok=True)
    
    manifest_path = target_dir / f"{host_name}.json"
    
    if platform.system() == "Windows":
        # Simple JSON write for Windows file, but needs registry.
        pass

    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2)
        
    print(f"Native messaging host installed to {manifest_path}")


if __name__ == "__main__":
    install_host()
