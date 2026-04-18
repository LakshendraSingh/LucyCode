"""
GrepTool — Search for patterns in files.
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any

from lucy.core.tool import Tool, ToolContext, ToolResult

MAX_RESULTS = 50
MAX_LINE_LENGTH = 500


class GrepTool(Tool):
    """Search for text patterns in files."""

    @property
    def name(self) -> str:
        return "Grep"

    @property
    def aliases(self) -> list[str]:
        return ["GrepTool", "Search"]

    @property
    def is_core(self) -> bool:
        return True

    @property
    def description(self) -> str:
        return "Search for a pattern in files"

    @property
    def input_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "pattern": {
                    "type": "string",
                    "description": "The regex pattern to search for",
                },
                "path": {
                    "type": "string",
                    "description": "Directory or file to search in (default: cwd)",
                },
                "include": {
                    "type": "string",
                    "description": "Glob pattern to filter files (e.g. '*.py')",
                },
                "case_insensitive": {
                    "type": "boolean",
                    "description": "Case-insensitive search (default: false)",
                },
            },
            "required": ["pattern"],
        }

    def get_prompt(self) -> str:
        return (
            "Search for a regex pattern across files. "
            "Returns matching lines with file paths and line numbers. "
            f"Results are capped at {MAX_RESULTS} matches. "
            "Use the 'include' parameter to filter by file glob (e.g. '*.py'). "
            "The search respects .gitignore by default."
        )

    def is_read_only(self, tool_input: dict[str, Any]) -> bool:
        return True

    def is_concurrent_safe(self, tool_input: dict[str, Any]) -> bool:
        return True

    def get_activity_description(self, tool_input: dict[str, Any] | None = None) -> str | None:
        if tool_input:
            pattern = tool_input.get("pattern", "")
            return f"Searching for '{pattern}'" if pattern else "Searching"
        return "Searching"

    async def call(self, tool_input: dict[str, Any], context: ToolContext) -> ToolResult:
        pattern = tool_input.get("pattern", "")
        search_path = tool_input.get("path", "")
        include = tool_input.get("include", "")
        case_insensitive = tool_input.get("case_insensitive", False)

        if not pattern:
            return ToolResult(error="pattern is required")

        if not search_path:
            search_path = context.cwd or os.getcwd()

        if not os.path.isabs(search_path):
            search_path = os.path.join(context.cwd or os.getcwd(), search_path)

        search = Path(search_path)
        if not search.exists():
            return ToolResult(error=f"Path not found: {search_path}")

        # Compile regex
        flags = re.IGNORECASE if case_insensitive else 0
        try:
            regex = re.compile(pattern, flags)
        except re.error as e:
            return ToolResult(error=f"Invalid regex pattern: {e}")

        # Determine files to search
        if search.is_file():
            files = [search]
        else:
            files = _collect_files(search, include)

        # Search
        matches: list[str] = []
        for fpath in files:
            if len(matches) >= MAX_RESULTS:
                break
            try:
                with open(fpath, "r", encoding="utf-8", errors="replace") as f:
                    for line_no, line in enumerate(f, 1):
                        if regex.search(line):
                            line_text = line.rstrip()
                            if len(line_text) > MAX_LINE_LENGTH:
                                line_text = line_text[:MAX_LINE_LENGTH] + "..."
                            rel = os.path.relpath(fpath, search_path) if search.is_dir() else str(fpath)
                            matches.append(f"{rel}:{line_no}: {line_text}")
                            if len(matches) >= MAX_RESULTS:
                                break
            except (OSError, UnicodeDecodeError):
                continue

        if not matches:
            return ToolResult(data=f"No matches found for pattern: {pattern}")

        header = f"Found {len(matches)} match{'es' if len(matches) != 1 else ''}"
        if len(matches) >= MAX_RESULTS:
            header += f" (capped at {MAX_RESULTS})"
        header += f" for pattern: {pattern}\n"

        return ToolResult(data=header + "\n".join(matches))


def _collect_files(
    directory: Path, include: str = "", max_files: int = 10000
) -> list[Path]:
    """Collect files from a directory, respecting .gitignore-like rules."""
    skip_dirs = {
        ".git", "node_modules", "__pycache__", ".venv", "venv",
        ".tox", ".mypy_cache", ".pytest_cache", "dist", "build",
        ".next", ".nuxt", "coverage", ".cache",
    }
    skip_extensions = {
        ".pyc", ".pyo", ".so", ".dylib", ".dll", ".exe",
        ".jpg", ".jpeg", ".png", ".gif", ".bmp", ".ico",
        ".mp3", ".mp4", ".wav", ".avi", ".mov",
        ".zip", ".tar", ".gz", ".bz2", ".xz",
        ".pdf", ".doc", ".docx", ".xls", ".xlsx",
        ".woff", ".woff2", ".ttf", ".eot",
    }

    files: list[Path] = []

    if include:
        # Use glob pattern
        for fpath in directory.rglob(include):
            if fpath.is_file() and len(files) < max_files:
                if not any(p in skip_dirs for p in fpath.parts):
                    files.append(fpath)
    else:
        for fpath in directory.rglob("*"):
            if len(files) >= max_files:
                break
            if not fpath.is_file():
                continue
            if any(p in skip_dirs for p in fpath.parts):
                continue
            if fpath.suffix.lower() in skip_extensions:
                continue
            files.append(fpath)

    return files
