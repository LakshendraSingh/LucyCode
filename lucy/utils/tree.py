"""
Directory tree rendering utilities.
"""

from __future__ import annotations

import os
from typing import Any


def render_tree(
    path: str,
    prefix: str = "",
    max_depth: int = 3,
    max_files: int = 200,
    show_hidden: bool = False,
    ignore_patterns: list[str] | None = None,
) -> str:
    """Render a directory tree as a string."""
    ignore = set(ignore_patterns or [
        ".git", "__pycache__", "node_modules", ".venv", "venv",
        ".tox", ".mypy_cache", ".pytest_cache", ".ruff_cache",
        "dist", "build", ".next", ".nuxt", "target",
        ".DS_Store", "*.pyc", "*.pyo",
    ])

    lines = []
    _count = [0]

    def _walk(dir_path: str, pref: str, depth: int) -> None:
        if _count[0] >= max_files or depth > max_depth:
            return

        try:
            entries = sorted(os.listdir(dir_path))
        except PermissionError:
            lines.append(f"{pref}[permission denied]")
            return

        # Filter
        entries = [e for e in entries
                   if (show_hidden or not e.startswith("."))
                   and e not in ignore]

        dirs = [e for e in entries if os.path.isdir(os.path.join(dir_path, e))]
        files = [e for e in entries if not os.path.isdir(os.path.join(dir_path, e))]

        all_entries = dirs + files

        for i, entry in enumerate(all_entries):
            _count[0] += 1
            if _count[0] > max_files:
                lines.append(f"{pref}... ({len(entries) - i} more)")
                break

            is_last = i == len(all_entries) - 1
            connector = "└── " if is_last else "├── "
            full_path = os.path.join(dir_path, entry)

            if os.path.isdir(full_path):
                lines.append(f"{pref}{connector}📁 {entry}/")
                extension = "    " if is_last else "│   "
                _walk(full_path, pref + extension, depth + 1)
            else:
                size = ""
                try:
                    s = os.path.getsize(full_path)
                    if s > 1_000_000:
                        size = f" ({s/1_000_000:.1f}MB)"
                    elif s > 1_000:
                        size = f" ({s/1_000:.1f}KB)"
                except OSError:
                    pass
                icon = _file_icon(entry)
                lines.append(f"{pref}{connector}{icon} {entry}{size}")

    basename = os.path.basename(path) or path
    lines.append(f"📁 {basename}/")
    _walk(path, "", 0)

    return "\n".join(lines)


def _file_icon(name: str) -> str:
    ext = os.path.splitext(name)[1].lower()
    icons = {
        ".py": "🐍", ".js": "📜", ".ts": "📘", ".jsx": "⚛️", ".tsx": "⚛️",
        ".rs": "🦀", ".go": "🔵", ".java": "☕", ".cpp": "⚙️", ".c": "⚙️",
        ".rb": "💎", ".php": "🐘", ".swift": "🐦", ".kt": "🟣",
        ".html": "🌐", ".css": "🎨", ".scss": "🎨",
        ".json": "📋", ".yaml": "📋", ".yml": "📋", ".toml": "📋",
        ".md": "📝", ".txt": "📄", ".rst": "📝",
        ".sh": "🔧", ".bash": "🔧", ".zsh": "🔧",
        ".sql": "🗄️", ".graphql": "🔗",
        ".png": "🖼️", ".jpg": "🖼️", ".svg": "🖼️", ".gif": "🖼️",
        ".lock": "🔒", ".env": "🔐",
    }
    return icons.get(ext, "📄")
