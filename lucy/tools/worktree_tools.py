"""
Worktree tools — enter/exit git worktrees for isolated work.

Mirrors OpenCode's EnterWorktreeTool and ExitWorktreeTool.
"""

from __future__ import annotations

import os
import subprocess
import uuid
from typing import Any

from lucy.core.tool import Tool, ToolContext, ToolResult


class EnterWorktreeTool(Tool):
    @property
    def name(self) -> str:
        return "EnterWorktree"

    @property
    def description(self) -> str:
        return "Create and enter a git worktree for isolated work"

    @property
    def input_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "branch_name": {
                    "type": "string",
                    "description": "Name for the new worktree branch",
                },
                "base_branch": {
                    "type": "string",
                    "description": "Branch to base the worktree on (default: current branch)",
                },
            },
        }

    def get_prompt(self) -> str:
        return (
            "Create a git worktree to work in isolation. This creates a separate "
            "working directory with its own branch, allowing you to make changes "
            "without affecting the main working directory. Use this for risky "
            "changes or when you want to try something without commitment."
        )

    async def call(self, tool_input: dict[str, Any], context: ToolContext) -> ToolResult:
        branch = tool_input.get("branch_name", f"lucy-worktree-{uuid.uuid4().hex[:8]}")
        base = tool_input.get("base_branch", "")

        # Check if we're in a git repo
        try:
            subprocess.run(
                ["git", "rev-parse", "--git-dir"],
                cwd=context.cwd, capture_output=True, check=True,
            )
        except (subprocess.CalledProcessError, FileNotFoundError):
            return ToolResult(error="Not in a git repository")

        # Create worktree path
        worktree_dir = os.path.join(context.cwd, ".lucy-worktrees", branch)
        os.makedirs(os.path.dirname(worktree_dir), exist_ok=True)

        # Build command
        cmd = ["git", "worktree", "add", "-b", branch, worktree_dir]
        if base:
            cmd.append(base)

        try:
            result = subprocess.run(
                cmd, cwd=context.cwd, capture_output=True, text=True, timeout=30,
            )
            if result.returncode != 0:
                return ToolResult(error=f"Failed to create worktree: {result.stderr.strip()}")
        except subprocess.TimeoutExpired:
            return ToolResult(error="Worktree creation timed out")

        # Switch context to worktree
        context.cwd = worktree_dir
        return ToolResult(
            data=f"Created worktree at: {worktree_dir}\nBranch: {branch}\n"
                 f"Working directory switched to worktree."
        )


class ExitWorktreeTool(Tool):
    @property
    def name(self) -> str:
        return "ExitWorktree"

    @property
    def description(self) -> str:
        return "Exit the current git worktree and optionally merge changes"

    @property
    def input_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "merge": {
                    "type": "boolean",
                    "description": "Whether to merge worktree changes back",
                    "default": False,
                },
                "delete": {
                    "type": "boolean",
                    "description": "Whether to delete the worktree after exiting",
                    "default": True,
                },
            },
        }

    def get_prompt(self) -> str:
        return (
            "Exit the current git worktree and return to the main working directory. "
            "Set merge=true to merge the worktree branch back into the original branch. "
            "Set delete=true to remove the worktree directory."
        )

    async def call(self, tool_input: dict[str, Any], context: ToolContext) -> ToolResult:
        merge = tool_input.get("merge", False)
        delete = tool_input.get("delete", True)

        worktree_dir = context.cwd
        if ".lucy-worktrees" not in worktree_dir:
            return ToolResult(error="Not currently in a Lucy worktree")

        # Find main repo
        main_dir = worktree_dir.split(".lucy-worktrees")[0].rstrip(os.sep)

        # Get current branch name
        try:
            branch_result = subprocess.run(
                ["git", "branch", "--show-current"],
                cwd=worktree_dir, capture_output=True, text=True,
            )
            branch = branch_result.stdout.strip()
        except Exception:
            branch = ""

        messages = []

        if merge and branch:
            # Merge into main
            try:
                subprocess.run(
                    ["git", "merge", branch],
                    cwd=main_dir, capture_output=True, text=True, check=True,
                )
                messages.append(f"Merged branch '{branch}' into main")
            except subprocess.CalledProcessError as e:
                messages.append(f"Merge failed: {e.stderr.strip()}")

        # Switch back
        context.cwd = main_dir
        messages.append(f"Returned to: {main_dir}")

        if delete:
            try:
                subprocess.run(
                    ["git", "worktree", "remove", worktree_dir, "--force"],
                    cwd=main_dir, capture_output=True, text=True,
                )
                messages.append(f"Removed worktree: {worktree_dir}")
                if branch:
                    subprocess.run(
                        ["git", "branch", "-d", branch],
                        cwd=main_dir, capture_output=True, text=True,
                    )
            except Exception:
                messages.append("Warning: could not clean up worktree")

        return ToolResult(data="\n".join(messages))
