"""
Read-only command validation.
"""

from __future__ import annotations

from lucy.shell.commands import get_command_info
from lucy.shell.parser import parse_command


def is_read_only_command(command: str) -> bool:
    """Check if a command is read-only (no side effects)."""
    parsed = parse_command(command)

    # Check all executables in the pipeline
    for exe in parsed.get_all_executables():
        info = get_command_info(exe)
        if info is None:
            return False  # Unknown command — not safe to assume read-only
        if not info.is_read_only:
            return False

    # Check for write redirects
    for redirect in parsed.redirects:
        if redirect.get("type") in ("write", "append"):
            return False

    return True
