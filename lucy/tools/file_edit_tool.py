"""
FileEditTool — Surgical search-and-replace edits.
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


class FileEditTool(Tool):
    """Apply targeted edits to existing files."""

    @property
    def name(self) -> str:
        return "Edit"

    @property
    def aliases(self) -> list[str]:
        return ["FileEdit"]

    @property
    def is_core(self) -> bool:
        return True

    @property
    def description(self) -> str:
        return "Edit a file by replacing specific text"

    @property
    def input_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "file_path": {
                    "type": "string",
                    "description": "Absolute path to the file to edit",
                },
                "old_text": {
                    "type": "string",
                    "description": "The exact text to find and replace (must match exactly)",
                },
                "new_text": {
                    "type": "string",
                    "description": "The replacement text",
                },
            },
            "required": ["file_path", "old_text", "new_text"],
        }

    def get_prompt(self) -> str:
        return (
            "Make targeted edits to a file by specifying the exact text to replace. "
            "The old_text must match EXACTLY (including whitespace and indentation). "
            "The old_text must be unique within the file to avoid ambiguous edits. "
            "For creating new files, use the Write tool instead. "
            "For multiple non-adjacent edits, make multiple Edit calls."
        )

    async def check_permissions(
        self, tool_input: dict[str, Any], context: ToolContext
    ) -> PermissionResult:
        if getattr(context, "autonomous", False) or context.permission_mode in ("auto_accept", "autonomous"):
            return PermissionResult(
                behavior=PermissionBehavior.ALLOW, updated_input=tool_input
            )
        file_path = tool_input.get("file_path", "")
        return PermissionResult(
            behavior=PermissionBehavior.ASK,
            message=f"Edit file: {file_path}",
            updated_input=tool_input,
        )

    def get_activity_description(self, tool_input: dict[str, Any] | None = None) -> str | None:
        if tool_input:
            fp = tool_input.get("file_path", "")
            basename = Path(fp).name if fp else ""
            return f"Editing {basename}" if basename else "Editing file"
        return "Editing file"

    async def call(self, tool_input: dict[str, Any], context: ToolContext) -> ToolResult:
        file_path = tool_input.get("file_path", "")
        old_text = tool_input.get("old_text", "")
        new_text = tool_input.get("new_text", "")

        if not file_path:
            return ToolResult(error="file_path is required")
        if not old_text:
            return ToolResult(error="old_text is required")

        if not os.path.isabs(file_path):
            file_path = os.path.join(context.cwd or os.getcwd(), file_path)

        path = Path(file_path)

        if not path.exists():
            return ToolResult(error=f"File not found: {file_path}")

        if not path.is_file():
            return ToolResult(error=f"Not a file: {file_path}")

        try:
            content = path.read_text(encoding="utf-8")
        except OSError as e:
            return ToolResult(error=f"Cannot read file: {e}")

        # Apply the edit with multi-stage fuzzy patching
        from lucy.core.fuzzy_patcher import FuzzyPatcher

        patch_res = FuzzyPatcher.apply_patch(content, old_text, new_text)

        if not patch_res.success:
            return ToolResult(
                error=(
                    f"old_text could not be applied to {file_path}: {patch_res.error}\n"
                    "Make sure the target lines exist in the file and sufficient context is provided."
                )
            )

        new_content = patch_res.new_content

        # Record change for undo/revert
        try:
            from lucy.utils.diff_preview import get_undo_manager
            get_undo_manager().record_change(
                filepath=str(path),
                original_content=content,
                new_content=new_content,
                change_type="edit",
            )
        except Exception:
            pass

        try:
            path.write_text(new_content, encoding="utf-8")
        except OSError as e:
            return ToolResult(error=f"Failed to write file: {e}")

        # Compute a simple diff summary
        old_lines = old_text.count("\n") + 1
        new_lines = new_text.count("\n") + 1
        delta = new_lines - old_lines
        stage_info = f" via {patch_res.stage_used}" if patch_res.stage_used != "exact" else ""

        return ToolResult(
            data=(
                f"Edited {file_path}: replaced {old_lines} lines with {new_lines} lines "
                f"({'+' if delta >= 0 else ''}{delta} net){stage_info}"
            )
        )
