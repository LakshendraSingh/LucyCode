"""
FileWriteTool — Create or overwrite files.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from lucy.core.tool import (
    PermissionBehavior,
    PermissionResult,
    Tool,
    ToolContext,
    ToolResult,
)


class FileWriteTool(Tool):
    """Create new files or overwrite existing ones."""

    @property
    def name(self) -> str:
        return "Write"

    @property
    def aliases(self) -> list[str]:
        return ["FileWrite", "WriteFile"]

    @property
    def is_core(self) -> bool:
        return True

    @property
    def description(self) -> str:
        return "Create or overwrite a file"

    @property
    def input_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "file_path": {
                    "type": "string",
                    "description": "Absolute path for the file to create/overwrite",
                },
                "content": {
                    "type": "string",
                    "description": "The full content to write to the file",
                },
            },
            "required": ["file_path", "content"],
        }

    def get_prompt(self) -> str:
        return (
            "Create a new file or overwrite an existing file with the provided content. "
            "Parent directories will be created automatically. "
            "Use this for creating new files. For modifying existing files, prefer the Edit tool. "
            "Always provide the COMPLETE file content — this tool overwrites the entire file."
        )

    def is_destructive(self, tool_input: dict[str, Any]) -> bool:
        file_path = tool_input.get("file_path", "")
        return Path(file_path).exists()

    async def check_permissions(
        self, tool_input: dict[str, Any], context: ToolContext
    ) -> PermissionResult:
        file_path = tool_input.get("file_path", "")
        exists = Path(file_path).exists() if file_path else False
        action = "Overwrite" if exists else "Create"
        if context.permission_mode == "auto_accept":
            return PermissionResult(
                behavior=PermissionBehavior.ALLOW, updated_input=tool_input
            )
        return PermissionResult(
            behavior=PermissionBehavior.ASK,
            message=f"{action} file: {file_path}",
            updated_input=tool_input,
        )

    def get_activity_description(self, tool_input: dict[str, Any] | None = None) -> str | None:
        if tool_input:
            fp = tool_input.get("file_path", "")
            basename = Path(fp).name if fp else ""
            return f"Writing {basename}" if basename else "Writing file"
        return "Writing file"

    async def call(self, tool_input: dict[str, Any], context: ToolContext) -> ToolResult:
        file_path = tool_input.get("file_path", "")
        content = tool_input.get("content", "")

        if not file_path:
            return ToolResult(error="file_path is required")

        if not os.path.isabs(file_path):
            file_path = os.path.join(context.cwd or os.getcwd(), file_path)

        path = Path(file_path)

        try:
            # Create parent directories
            path.parent.mkdir(parents=True, exist_ok=True)

            existed = path.exists()
            old_size = path.stat().st_size if existed else 0

            with open(path, "w", encoding="utf-8") as f:
                f.write(content)

            new_size = len(content.encode("utf-8"))
            action = "Updated" if existed else "Created"
            lines = content.count("\n") + (1 if content and not content.endswith("\n") else 0)

            return ToolResult(
                data=f"{action} {file_path} ({lines} lines, {new_size:,} bytes)"
            )

        except OSError as e:
            return ToolResult(error=f"Failed to write file: {e}")
