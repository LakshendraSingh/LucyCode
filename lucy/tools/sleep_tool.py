"""
Sleep tool — timed pauses for proactive agents.

Mirrors OpenCode's SleepTool.
"""

from __future__ import annotations

import asyncio
from typing import Any

from lucy.core.tool import Tool, ToolContext, ToolResult


class SleepTool(Tool):
    @property
    def name(self) -> str:
        return "Sleep"

    @property
    def aliases(self) -> list[str]:
        return ["Wait", "Pause"]

    @property
    def description(self) -> str:
        return "Pause execution for a specified duration"

    @property
    def input_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "seconds": {
                    "type": "integer",
                    "description": "Number of seconds to sleep (max 300)",
                    "minimum": 1,
                    "maximum": 300,
                },
                "reason": {
                    "type": "string",
                    "description": "Why you're waiting",
                },
            },
            "required": ["seconds"],
        }

    def get_prompt(self) -> str:
        return (
            "Pause execution for a specified number of seconds. Use this to wait "
            "for external processes, rate limits, or when polling for changes. "
            "Maximum wait time is 300 seconds (5 minutes)."
        )

    def is_read_only(self, tool_input: dict[str, Any]) -> bool:
        return True

    async def call(self, tool_input: dict[str, Any], context: ToolContext) -> ToolResult:
        seconds = min(tool_input.get("seconds", 1), 300)
        reason = tool_input.get("reason", "")

        if seconds < 1:
            return ToolResult(error="Seconds must be at least 1")

        msg = f"Sleeping for {seconds}s"
        if reason:
            msg += f" ({reason})"

        await asyncio.sleep(seconds)

        return ToolResult(data=f"{msg} — done.")
