"""
ANSI escape code utilities.
"""

from __future__ import annotations

import re


ANSI_RE = re.compile(r'\x1b\[[0-9;]*[a-zA-Z]')


def strip_ansi(text: str) -> str:
    """Remove all ANSI escape sequences."""
    return ANSI_RE.sub('', text)


def ansi_len(text: str) -> int:
    """Length of text excluding ANSI codes."""
    return len(strip_ansi(text))


def ansi_slice(text: str, start: int, end: int | None = None) -> str:
    """Slice text by visible character position, preserving ANSI codes."""
    result = []
    visible_pos = 0
    i = 0

    while i < len(text):
        # Check for ANSI sequence
        match = ANSI_RE.match(text, i)
        if match:
            # Always include ANSI codes
            result.append(match.group())
            i = match.end()
            continue

        # Visible character
        if end is not None and visible_pos >= end:
            break
        if visible_pos >= start:
            result.append(text[i])
        visible_pos += 1
        i += 1

    return ''.join(result)


def ansi_truncate(text: str, max_width: int, suffix: str = "…") -> str:
    """Truncate text to max visible width, preserving ANSI codes."""
    visible_len = ansi_len(text)
    if visible_len <= max_width:
        return text
    return ansi_slice(text, 0, max_width - len(suffix)) + suffix


def ansi_center(text: str, width: int) -> str:
    """Center text within width, accounting for ANSI codes."""
    visible_len = ansi_len(text)
    if visible_len >= width:
        return text
    padding = width - visible_len
    left = padding // 2
    right = padding - left
    return " " * left + text + " " * right


def ansi_ljust(text: str, width: int) -> str:
    """Left-justify text within width."""
    visible_len = ansi_len(text)
    if visible_len >= width:
        return text
    return text + " " * (width - visible_len)


def ansi_rjust(text: str, width: int) -> str:
    """Right-justify text within width."""
    visible_len = ansi_len(text)
    if visible_len >= width:
        return text
    return " " * (width - visible_len) + text
