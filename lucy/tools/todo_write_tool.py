"""
TodoWrite tool — structured TODO management.

Mirrors OpenCode's TodoWriteTool.
"""

from __future__ import annotations

import json
import os
from typing import Any

from lucy.core.tool import Tool, ToolContext, ToolResult


class TodoWriteTool(Tool):
    @property
    def name(self) -> str:
        return "TodoWrite"

    @property
    def aliases(self) -> list[str]:
        return ["Todo"]

    @property
    def description(self) -> str:
        return "Create or update a structured TODO list"

    @property
    def input_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "todos": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "id": {"type": "string"},
                            "content": {"type": "string"},
                            "status": {"type": "string", "enum": ["pending", "in_progress", "done", "cancelled"]},
                            "priority": {"type": "string", "enum": ["low", "medium", "high", "critical"]},
                        },
                        "required": ["content", "status"],
                    },
                    "description": "List of TODO items",
                },
                "file_path": {
                    "type": "string",
                    "description": "Path to save the TODO file (default: .lucy-todos.json)",
                },
            },
            "required": ["todos"],
        }

    def get_prompt(self) -> str:
        return (
            "Create or update a TODO list. Each item has content, status "
            "(pending/in_progress/done/cancelled), and optional priority. "
            "The TODO list is persisted to a JSON file. Use this to track "
            "multi-step plans and progress."
        )

    async def call(self, tool_input: dict[str, Any], context: ToolContext) -> ToolResult:
        todos = tool_input.get("todos", [])
        file_path = tool_input.get("file_path", ".lucy-todos.json")

        if not os.path.isabs(file_path):
            file_path = os.path.join(context.cwd, file_path)

        # Load existing
        existing = {}
        if os.path.exists(file_path):
            try:
                with open(file_path) as f:
                    data = json.load(f)
                    for item in data.get("todos", []):
                        existing[item.get("id", "")] = item
            except (json.JSONDecodeError, OSError):
                pass

        # Merge
        import uuid
        for todo in todos:
            tid = todo.get("id", uuid.uuid4().hex[:8])
            todo["id"] = tid
            existing[tid] = todo

        # Save
        all_todos = list(existing.values())
        try:
            with open(file_path, "w") as f:
                json.dump({"todos": all_todos}, f, indent=2)
        except OSError as e:
            return ToolResult(error=f"Failed to save TODOs: {e}")

        # Format output
        icons = {"pending": "⬜", "in_progress": "🔄", "done": "✅", "cancelled": "⏹️"}
        priority_icons = {"critical": "🔴", "high": "🟠", "medium": "🟡", "low": "🟢"}
        lines = ["TODO List:\n"]
        for t in all_todos:
            icon = icons.get(t.get("status", "pending"), "?")
            pri = priority_icons.get(t.get("priority", ""), "")
            lines.append(f"  {icon} {pri} [{t['id']}] {t['content']}")

        done = sum(1 for t in all_todos if t.get("status") == "done")
        lines.append(f"\nProgress: {done}/{len(all_todos)}")

        return ToolResult(data="\n".join(lines))

    def get_activity_description(self, tool_input: dict[str, Any] | None = None) -> str | None:
        return "Updating TODO list"
