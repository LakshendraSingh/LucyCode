"""
Platform detection utilities.
"""

from __future__ import annotations

import os
import platform
import shutil
import sys


def get_platform() -> str:
    """Get platform name: 'macos', 'linux', 'windows'."""
    system = platform.system().lower()
    if system == "darwin":
        return "macos"
    return system


def get_arch() -> str:
    """Get architecture: 'arm64', 'x86_64', etc."""
    return platform.machine().lower()


def is_macos() -> bool:
    return platform.system() == "Darwin"


def is_linux() -> bool:
    return platform.system() == "Linux"


def is_windows() -> bool:
    return platform.system() == "Windows"


def is_wsl() -> bool:
    """Check if running under WSL."""
    if not is_linux():
        return False
    try:
        with open("/proc/version") as f:
            return "microsoft" in f.read().lower()
    except OSError:
        return False


def is_docker() -> bool:
    """Check if running in a Docker container."""
    return os.path.exists("/.dockerenv") or os.path.exists("/run/.containerenv")


def is_ci() -> bool:
    """Check if running in CI."""
    ci_vars = ["CI", "CONTINUOUS_INTEGRATION", "GITHUB_ACTIONS",
               "GITLAB_CI", "CIRCLECI", "TRAVIS", "JENKINS_URL"]
    return any(os.environ.get(v) for v in ci_vars)


def has_gui() -> bool:
    """Check if a GUI is available."""
    if is_windows():
        return True
    if is_macos():
        return True
    return bool(os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY"))


def get_terminal() -> str:
    """Detect the terminal emulator."""
    term_program = os.environ.get("TERM_PROGRAM", "")
    if term_program:
        return term_program
    if os.environ.get("KITTY_PID"):
        return "kitty"
    if os.environ.get("WEZTERM_PANE"):
        return "wezterm"
    return os.environ.get("TERM", "unknown")


def supports_color() -> bool:
    """Check if terminal supports color."""
    if os.environ.get("NO_COLOR"):
        return False
    if os.environ.get("FORCE_COLOR"):
        return True
    return hasattr(sys.stdout, "isatty") and sys.stdout.isatty()


def supports_unicode() -> bool:
    """Check if terminal supports Unicode."""
    import locale
    encoding = locale.getpreferredencoding(False).lower()
    return "utf" in encoding


def get_terminal_size() -> tuple[int, int]:
    """Get terminal size (columns, rows)."""
    try:
        size = os.get_terminal_size()
        return size.columns, size.lines
    except OSError:
        return 80, 24
