"""
Clipboard utilities — copy/paste operations.
"""

from __future__ import annotations

import subprocess
import sys


def copy_to_clipboard(text: str) -> bool:
    """Copy text to system clipboard."""
    try:
        if sys.platform == "darwin":
            subprocess.run(["pbcopy"], input=text.encode(), check=True)
            return True
        elif sys.platform == "linux":
            # Try xclip, xsel, wl-copy
            for cmd in [
                ["xclip", "-selection", "clipboard"],
                ["xsel", "--clipboard", "--input"],
                ["wl-copy"],
            ]:
                try:
                    subprocess.run(cmd, input=text.encode(), check=True)
                    return True
                except FileNotFoundError:
                    continue
        elif sys.platform == "win32":
            subprocess.run(["clip"], input=text.encode(), check=True)
            return True
    except subprocess.SubprocessError:
        pass
    return False


def paste_from_clipboard() -> str | None:
    """Paste text from system clipboard."""
    try:
        if sys.platform == "darwin":
            r = subprocess.run(["pbpaste"], capture_output=True, text=True)
            return r.stdout
        elif sys.platform == "linux":
            for cmd in [
                ["xclip", "-selection", "clipboard", "-o"],
                ["xsel", "--clipboard", "--output"],
                ["wl-paste"],
            ]:
                try:
                    r = subprocess.run(cmd, capture_output=True, text=True)
                    if r.returncode == 0:
                        return r.stdout
                except FileNotFoundError:
                    continue
        elif sys.platform == "win32":
            import ctypes
            # Use PowerShell as fallback
            r = subprocess.run(["powershell", "-Command", "Get-Clipboard"],
                               capture_output=True, text=True)
            return r.stdout
    except Exception:
        pass
    return None
