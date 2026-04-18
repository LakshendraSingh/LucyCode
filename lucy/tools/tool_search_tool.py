"""
ToolSearch tool — search for available tools.

Mirrors OpenCode's ToolSearchTool.
"""

from __future__ import annotations

from typing import Any

from lucy.core.tool import Tool, ToolContext, ToolResult


class ToolSearchTool(Tool):
    @property
    def name(self) -> str:
        return "ToolSearch"

    @property
    def description(self) -> str:
        return "Search for available tools by name or description"

    @property
    def input_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Search query to find tools",
                },
            },
            "required": ["query"],
        }

    def get_prompt(self) -> str:
        return (
            "Search for available tools by name, alias, or description keyword. "
            "Use this when you're not sure which tool to use for a task."
        )

    def is_read_only(self, tool_input: dict[str, Any]) -> bool:
        return True

    async def call(self, tool_input: dict[str, Any], context: ToolContext) -> ToolResult:
        from lucy.core.tool import get_tool_registry

        query = tool_input.get("query", "").lower()
        if not query:
            return ToolResult(error="Query is required")

        registry = get_tool_registry()
        matches = []

        for tool in registry.get_all():
            score = 0
            name_lower = tool.name.lower()
            desc_lower = tool.description.lower()

            if query == name_lower:
                score = 100
            elif query in name_lower:
                score = 80
            elif any(query == a.lower() for a in tool.aliases):
                score = 90
            elif any(query in a.lower() for a in tool.aliases):
                score = 70
            elif query in desc_lower:
                score = 50
            else:
                # Fuzzy: check if all query words are in name+desc
                words = query.split()
                combined = f"{name_lower} {desc_lower}"
                if all(w in combined for w in words):
                    score = 30

            if score > 0:
                matches.append((score, tool))

        matches.sort(key=lambda x: x[0], reverse=True)

        if not matches:
            return ToolResult(data=f"No tools found matching '{query}'")

        lines = [f"Tools matching '{query}':\n"]
        for score, tool in matches[:15]:
            enabled = "✓" if tool.is_enabled() else "✗"
            aliases = f" (aliases: {', '.join(tool.aliases)})" if tool.aliases else ""
            lines.append(f"  {enabled} {tool.name}{aliases}")
            lines.append(f"    {tool.description}")

        return ToolResult(data="\n".join(lines))
