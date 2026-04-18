"""
String utilities — common text manipulation functions.
"""

from __future__ import annotations

import re
import textwrap


def truncate(text: str, max_length: int = 100, suffix: str = "...") -> str:
    """Truncate text to max_length."""
    if len(text) <= max_length:
        return text
    return text[:max_length - len(suffix)] + suffix


def indent(text: str, prefix: str = "  ") -> str:
    """Indent each line of text."""
    return textwrap.indent(text, prefix)


def dedent(text: str) -> str:
    """Remove common leading whitespace."""
    return textwrap.dedent(text)


def word_wrap(text: str, width: int = 80) -> str:
    """Wrap text at word boundaries."""
    return textwrap.fill(text, width=width)


def pluralize(count: int, singular: str, plural: str | None = None) -> str:
    """Pluralize a word based on count."""
    if count == 1:
        return f"{count} {singular}"
    return f"{count} {plural or singular + 's'}"


def human_size(size_bytes: int) -> str:
    """Format bytes as human-readable size."""
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if abs(size_bytes) < 1024:
            if unit == "B":
                return f"{size_bytes} {unit}"
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024
    return f"{size_bytes:.1f} PB"


def human_duration(seconds: float) -> str:
    """Format seconds as human-readable duration."""
    if seconds < 1:
        return f"{seconds*1000:.0f}ms"
    if seconds < 60:
        return f"{seconds:.1f}s"
    if seconds < 3600:
        mins = int(seconds // 60)
        secs = int(seconds % 60)
        return f"{mins}m {secs}s"
    hours = int(seconds // 3600)
    mins = int((seconds % 3600) // 60)
    return f"{hours}h {mins}m"


def slugify(text: str) -> str:
    """Convert text to a URL-friendly slug."""
    text = text.lower().strip()
    text = re.sub(r'[^\w\s-]', '', text)
    text = re.sub(r'[-\s]+', '-', text)
    return text.strip('-')


def extract_urls(text: str) -> list[str]:
    """Extract URLs from text."""
    pattern = r'https?://[^\s<>"{}|\\^`\[\]]+'
    return re.findall(pattern, text)


def mask_sensitive(value: str, visible_chars: int = 4) -> str:
    """Mask a sensitive string, showing only last N characters."""
    if len(value) <= visible_chars:
        return "***"
    return "•" * min(8, len(value) - visible_chars) + value[-visible_chars:]


def snake_to_camel(s: str) -> str:
    """Convert snake_case to CamelCase."""
    return "".join(w.capitalize() for w in s.split("_"))


def camel_to_snake(s: str) -> str:
    """Convert CamelCase to snake_case."""
    return re.sub(r'(?<!^)(?=[A-Z])', '_', s).lower()
