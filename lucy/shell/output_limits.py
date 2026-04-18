"""
Output limits — truncation and size management for shell output.
"""

from __future__ import annotations

import re


DEFAULT_MAX_OUTPUT = 100_000  # chars
DEFAULT_MAX_LINES = 2000


def truncate_output(
    output: str,
    max_chars: int = DEFAULT_MAX_OUTPUT,
    max_lines: int = DEFAULT_MAX_LINES,
) -> str:
    """Truncate shell output to stay within limits."""
    lines = output.split("\n")

    # Line limit
    if len(lines) > max_lines:
        kept_top = max_lines // 3
        kept_bottom = max_lines - kept_top
        omitted = len(lines) - max_lines
        lines = (
            lines[:kept_top]
            + [f"\n... ({omitted} lines omitted) ...\n"]
            + lines[-kept_bottom:]
        )
        output = "\n".join(lines)

    # Character limit
    if len(output) > max_chars:
        # Keep beginning and end
        keep_start = max_chars * 2 // 3
        keep_end = max_chars - keep_start - 100  # Leave room for message
        omitted = len(output) - max_chars
        output = (
            output[:keep_start]
            + f"\n\n... ({omitted} characters omitted) ...\n\n"
            + output[-keep_end:]
        )

    return output


def strip_ansi(text: str) -> str:
    """Remove ANSI escape sequences from text."""
    return re.sub(r'\x1b\[[0-9;]*[a-zA-Z]', '', text)


def count_visible_chars(text: str) -> int:
    """Count visible characters (excluding ANSI codes)."""
    return len(strip_ansi(text))
