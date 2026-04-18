"""
Shell quoting utilities.
"""

from __future__ import annotations

import shlex


def shell_quote(s: str) -> str:
    """Quote a string for safe shell usage."""
    return shlex.quote(s)


def shell_unquote(s: str) -> str:
    """Remove shell quotes from a string."""
    s = s.strip()
    if (s.startswith("'") and s.endswith("'")) or (s.startswith('"') and s.endswith('"')):
        return s[1:-1]
    return s


def shell_join(args: list[str]) -> str:
    """Join arguments into a shell command string."""
    return " ".join(shlex.quote(a) for a in args)


def escape_for_bash(s: str) -> str:
    """Escape special characters for bash."""
    special = set('\\`$"!#&|;(){}[]<>*?~')
    return "".join(f"\\{c}" if c in special else c for c in s)
