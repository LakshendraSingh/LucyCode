"""
FileReadTool — Read file contents with optional line ranges.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from lucy.core.tool import Tool, ToolContext, ToolResult

MAX_LINES_FIRST_READ = 800
MAX_LINES_PER_READ = 800
MAX_FILE_SIZE_BYTES = 10 * 1024 * 1024  # 10 MB


class FileReadTool(Tool):
    """Read file contents."""

    @property
    def name(self) -> str:
        return "Read"

    @property
    def aliases(self) -> list[str]:
        return ["FileRead", "ReadFile"]

    @property
    def is_core(self) -> bool:
        return True

    @property
    def description(self) -> str:
        return "Read file contents"

    @property
    def input_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "file_path": {
                    "type": "string",
                    "description": "Absolute path to the file to read",
                },
                "start_line": {
                    "type": "integer",
                    "description": "Start line (1-indexed, inclusive). Omit to start from beginning.",
                },
                "end_line": {
                    "type": "integer",
                    "description": "End line (1-indexed, inclusive). Omit to read to end.",
                },
            },
            "required": ["file_path"],
        }

    def get_prompt(self) -> str:
        return (
            "Read the contents of a file. Provide the absolute path. "
            "You can optionally specify start_line and end_line to read a range. "
            "Lines are 1-indexed. Each line in the output is prefixed with its line number. "
            f"The first read of a file shows up to {MAX_LINES_FIRST_READ} lines. "
            f"Subsequent reads can show up to {MAX_LINES_PER_READ} lines at a time."
        )

    def is_read_only(self, tool_input: dict[str, Any]) -> bool:
        return True

    def is_concurrent_safe(self, tool_input: dict[str, Any]) -> bool:
        return True

    def get_activity_description(self, tool_input: dict[str, Any] | None = None) -> str | None:
        if tool_input:
            fp = tool_input.get("file_path", "")
            basename = Path(fp).name if fp else ""
            return f"Reading {basename}" if basename else "Reading file"
        return "Reading file"

    async def call(self, tool_input: dict[str, Any], context: ToolContext) -> ToolResult:
        file_path = tool_input.get("file_path", "")
        start_line = tool_input.get("start_line")
        end_line = tool_input.get("end_line")

        if not file_path:
            return ToolResult(error="file_path is required")

        # Resolve relative paths
        if not os.path.isabs(file_path):
            file_path = os.path.join(context.cwd or os.getcwd(), file_path)

        path = Path(file_path)

        if not path.is_file():
            if path.is_dir():
                return ToolResult(error=f"Path is a directory, not a file: {file_path}")
            return ToolResult(error=f"Path is not a regular file (it may be a device, socket, or missing): {file_path}")

        # Check file size
        try:
            size = path.stat().st_size
        except OSError as e:
            return ToolResult(error=f"Cannot stat file: {e}")

        if size > MAX_FILE_SIZE_BYTES:
            return ToolResult(
                error=f"File is too large ({size:,} bytes, max {MAX_FILE_SIZE_BYTES:,}). "
                "Use line ranges or the Bash tool (head/tail) to read portions."
            )

        # Check if binary
        try:
            with open(path, "rb") as f:
                chunk = f.read(8192)
            if b"\x00" in chunk:
                return ToolResult(
                    data=f"Binary file: {file_path} ({size:,} bytes)"
                )
        except OSError as e:
            return ToolResult(error=f"Cannot read file: {e}")

        # Read the file
        try:
            with open(path, "r", encoding="utf-8", errors="replace") as f:
                all_lines = f.readlines()
        except OSError as e:
            return ToolResult(error=f"Cannot read file: {e}")

        total_lines = len(all_lines)

        # Apply line range
        if start_line is not None or end_line is not None:
            s = (start_line or 1) - 1  # Convert to 0-indexed
            e = end_line or total_lines
            s = max(0, s)
            e = min(total_lines, e)

            if s >= total_lines:
                return ToolResult(
                    error=f"start_line {start_line} is beyond the file ({total_lines} lines)"
                )

            # Limit lines per read
            if e - s > MAX_LINES_PER_READ:
                e = s + MAX_LINES_PER_READ

            selected = all_lines[s:e]
            line_offset = s
        else:
            # First read — limit to MAX_LINES_FIRST_READ
            if total_lines > MAX_LINES_FIRST_READ:
                selected = all_lines[:MAX_LINES_FIRST_READ]
                line_offset = 0
            else:
                selected = all_lines
                line_offset = 0

        # Format with line numbers
        numbered_lines = []
        for i, line in enumerate(selected):
            line_num = line_offset + i + 1
            numbered_lines.append(f"{line_num}: {line.rstrip()}")

        output = "\n".join(numbered_lines)

        # Add metadata header
        shown = len(selected)
        if shown < total_lines:
            header = (
                f"File: {file_path}\n"
                f"Total lines: {total_lines} | Showing lines {line_offset + 1}-{line_offset + shown}\n"
                f"{'─' * 40}\n"
            )
        else:
            header = (
                f"File: {file_path}\n"
                f"Total lines: {total_lines}\n"
                f"{'─' * 40}\n"
            )

        return ToolResult(data=header + output)
