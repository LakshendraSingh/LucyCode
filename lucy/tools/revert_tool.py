"""
Revert & Undo Tool for LucyCode.

Empowers the agent to undo or revert file modifications made during the session:
- revert the most recent change
- revert changes to a specific file
- revert all modifications made during the session
- list modified files and preview diffs
- seamlessly fall back to git checkout / restore if git modifications exist
"""

from __future__ import annotations

import os
import subprocess
import time
from pathlib import Path
from typing import Any

from lucy.core.tool import Tool, ToolContext, ToolResult
from lucy.utils.diff_preview import get_undo_manager


class RevertTool(Tool):
    """Tool to revert or undo file modifications made during execution."""

    @property
    def name(self) -> str:
        return "revert_change"

    @property
    def aliases(self) -> list[str]:
        return ["undo", "revert", "rollback"]

    @property
    def description(self) -> str:
        return (
            "Revert or undo file changes made during the session. "
            "Use this when a change caused a regression, a test failed, or the user requested to undo changes. "
            "Supports reverting the last change, a specific file, or all session changes."
        )

    @property
    def input_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["last", "file", "all", "list", "diff"],
                    "description": "Revert action: 'last' (undo last change), 'file' (revert specific file), 'all' (revert all session changes), 'list' (view change history), 'diff' (preview last diff).",
                    "default": "last",
                },
                "file_path": {
                    "type": "string",
                    "description": "Optional file path to revert (required when action is 'file').",
                },
            },
        }

    def is_read_only(self, tool_input: dict[str, Any]) -> bool:
        action = tool_input.get("action", "last")
        return action in ("list", "diff")

    def get_prompt(self) -> str:
        return "Revert or rollback file modifications when tests fail or when the user requests an undo."

    async def call(self, tool_input: dict[str, Any], context: ToolContext) -> ToolResult:
        action = tool_input.get("action", "last").lower()
        file_path = tool_input.get("file_path", "")
        mgr = get_undo_manager()

        # ── 1. List History ──
        if action == "list":
            history = mgr.get_history()
            if not history:
                return ToolResult(data="No recorded file changes in current session.")
            lines = ["Recent session file changes:\n"]
            for ch in history:
                ts = time.strftime("%H:%M:%S", time.localtime(ch.timestamp))
                lines.append(f"  [{ts}] {ch.change_type.upper()}: {ch.filepath}")
            return ToolResult(data="\n".join(lines))

        # ── 2. Preview Diff ──
        if action == "diff":
            diff = mgr.preview_last()
            if not diff:
                return ToolResult(data="No changes to preview in current session.")
            return ToolResult(data=diff)

        # ── 3. Revert All ──
        if action == "all":
            undone = mgr.undo_all()
            if undone:
                files_str = ", ".join(os.path.basename(ch.filepath) for ch in undone)
                return ToolResult(
                    data=f"Successfully reverted all {len(undone)} session change(s): {files_str}"
                )
            # Git fallback
            try:
                proc = subprocess.run(
                    ["git", "checkout", "."],
                    capture_output=True,
                    text=True,
                    cwd=context.cwd or os.getcwd(),
                    timeout=5,
                )
                if proc.returncode == 0:
                    return ToolResult(data="Reverted all uncommitted working tree changes via git.")
            except Exception:
                pass
            return ToolResult(data="No changes to revert.")

        # ── 4. Revert Specific File ──
        if action == "file" or (file_path and action == "last"):
            target_path = file_path
            if not os.path.isabs(target_path):
                target_path = str((Path(context.cwd or os.getcwd()) / target_path).resolve())

            change = mgr.undo_file(target_path)
            if change:
                return ToolResult(
                    data=f"Successfully reverted {change.change_type} on {os.path.basename(change.filepath)}"
                )

            # Git fallback for specific file
            try:
                proc = subprocess.run(
                    ["git", "checkout", "--", target_path],
                    capture_output=True,
                    text=True,
                    cwd=context.cwd or os.getcwd(),
                    timeout=5,
                )
                if proc.returncode == 0:
                    return ToolResult(
                        data=f"Reverted uncommitted changes on {os.path.basename(target_path)} via git."
                    )
            except Exception:
                pass

            return ToolResult(
                error=f"No recorded changes or git modifications found for {file_path} to revert."
            )

        # ── 5. Revert Last ──
        change = mgr.undo_last()
        if change:
            return ToolResult(
                data=f"Successfully reverted {change.change_type} on {os.path.basename(change.filepath)}"
            )

        # Git fallback for last change
        try:
            # Check git status for modified files
            proc = subprocess.run(
                ["git", "status", "--porcelain"],
                capture_output=True,
                text=True,
                cwd=context.cwd or os.getcwd(),
                timeout=5,
            )
            lines = [l.strip() for l in proc.stdout.splitlines() if l.strip()]
            if lines:
                last_file = lines[-1].split()[-1]
                subprocess.run(
                    ["git", "checkout", "--", last_file],
                    capture_output=True,
                    cwd=context.cwd or os.getcwd(),
                    timeout=5,
                )
                return ToolResult(
                    data=f"Reverted git modifications on {os.path.basename(last_file)}."
                )
        except Exception:
            pass

        return ToolResult(data="No changes to revert.")
