"""
Brief tool — generate concise summaries.

Mirrors OpenCode's BriefTool.
"""

from __future__ import annotations

from typing import Any

from lucy.core.tool import Tool, ToolContext, ToolResult


class BriefTool(Tool):
    @property
    def name(self) -> str:
        return "Brief"

    @property
    def description(self) -> str:
        return "Generate a brief, concise summary of content"

    @property
    def input_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "content": {
                    "type": "string",
                    "description": "The content to summarize",
                },
                "max_length": {
                    "type": "integer",
                    "description": "Maximum length of the summary in characters",
                    "default": 500,
                },
                "style": {
                    "type": "string",
                    "enum": ["bullet", "paragraph", "oneliner"],
                    "description": "Summary style",
                    "default": "paragraph",
                },
            },
            "required": ["content"],
        }

    def get_prompt(self) -> str:
        return (
            "Generate a brief summary of content. Use this to condense long outputs, "
            "file contents, or tool results into a shorter form. "
            "Styles: 'bullet' for bullet points, 'paragraph' for prose, "
            "'oneliner' for a single line."
        )

    def is_read_only(self, tool_input: dict[str, Any]) -> bool:
        return True

    async def call(self, tool_input: dict[str, Any], context: ToolContext) -> ToolResult:
        content = tool_input.get("content", "")
        max_length = tool_input.get("max_length", 500)
        style = tool_input.get("style", "paragraph")

        if not content:
            return ToolResult(error="Content is required")

        # Simple extractive summarization
        lines = content.strip().split("\n")
        lines = [l.strip() for l in lines if l.strip()]

        if style == "oneliner":
            summary = lines[0][:max_length] if lines else content[:max_length]
        elif style == "bullet":
            # Take key lines
            key_lines = []
            for line in lines:
                if len(" ".join(key_lines)) + len(line) > max_length:
                    break
                key_lines.append(f"• {line}")
            summary = "\n".join(key_lines) if key_lines else f"• {content[:max_length]}"
        else:
            # Paragraph — take first N chars intelligently
            text = " ".join(lines)
            if len(text) <= max_length:
                summary = text
            else:
                # Cut at sentence boundary
                cut = text[:max_length]
                last_period = cut.rfind(".")
                if last_period > max_length // 2:
                    summary = cut[: last_period + 1]
                else:
                    last_space = cut.rfind(" ")
                    summary = cut[:last_space] + "..." if last_space > 0 else cut + "..."

        return ToolResult(data=summary)
