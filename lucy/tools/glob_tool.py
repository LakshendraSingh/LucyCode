"""
GlobTool — Find files matching glob patterns.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from lucy.core.tool import Tool, ToolContext, ToolResult

MAX_RESULTS = 500

SKIP_DIRS = {
    ".git", "node_modules", "__pycache__", ".venv", "venv",
    ".tox", ".mypy_cache", ".pytest_cache", "dist", "build",
    ".next", ".nuxt", "coverage", ".cache", ".eggs",
}


class GlobTool(Tool):
    """Find files by glob pattern."""

    @property
    def name(self) -> str:
        return "Glob"

    @property
    def aliases(self) -> list[str]:
        return ["GlobTool", "FindFiles"]

    @property
    def is_core(self) -> bool:
        return True

    @property
    def description(self) -> str:
        return "Find files matching a glob pattern"

    @property
    def input_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "pattern": {
                    "type": "string",
                    "description": "Glob pattern (e.g. '**/*.py', 'src/**/*.ts')",
                },
                "path": {
                    "type": "string",
                    "description": "Base directory to search from (default: cwd)",
                },
            },
            "required": ["pattern"],
        }

    def get_prompt(self) -> str:
        return (
            "Find files matching a glob pattern. Use '**' for recursive matching. "
            f"Results are capped at {MAX_RESULTS} files. "
            "Common patterns: '**/*.py' (all Python files), 'src/**/*.ts' (TypeScript in src). "
            "Directories like node_modules, .git, __pycache__ are automatically skipped."
        )

    def is_read_only(self, tool_input: dict[str, Any]) -> bool:
        return True

    def is_concurrent_safe(self, tool_input: dict[str, Any]) -> bool:
        return True

    async def call(self, tool_input: dict[str, Any], context: ToolContext) -> ToolResult:
        pattern = tool_input.get("pattern", "")
        base_path = tool_input.get("path", "")

        if not pattern:
            return ToolResult(error="pattern is required")

        if not base_path:
            base_path = context.cwd or os.getcwd()

        if not os.path.isabs(base_path):
            base_path = os.path.join(context.cwd or os.getcwd(), base_path)

        base = Path(base_path)
        if not base.exists():
            return ToolResult(error=f"Path not found: {base_path}")

        if not base.is_dir():
            return ToolResult(error=f"Not a directory: {base_path}")

        # Collect matching files
        results: list[str] = []
        try:
            for fpath in base.glob(pattern):
                if len(results) >= MAX_RESULTS:
                    break
                # Skip hidden/ignored dirs
                if any(p in SKIP_DIRS for p in fpath.parts):
                    continue
                if fpath.is_file():
                    rel = os.path.relpath(fpath, base_path)
                    results.append(rel)
        except Exception as e:
            return ToolResult(error=f"Glob error: {e}")

        results.sort()

        if not results:
            return ToolResult(data=f"No files found matching: {pattern}")

        header = f"Found {len(results)} file{'s' if len(results) != 1 else ''}"
        if len(results) >= MAX_RESULTS:
            header += f" (capped at {MAX_RESULTS})"
        header += f" matching: {pattern}\n\n"

        return ToolResult(data=header + "\n".join(results))
