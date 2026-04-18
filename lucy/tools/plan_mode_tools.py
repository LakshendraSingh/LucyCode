"""
Plan mode tools — enter/exit plan-only mode.

Mirrors OpenCode's EnterPlanModeTool and ExitPlanModeTool.
"""

from __future__ import annotations

from typing import Any

from lucy.core.tool import Tool, ToolContext, ToolResult


class EnterPlanModeTool(Tool):
    @property
    def name(self) -> str:
        return "EnterPlanMode"

    @property
    def description(self) -> str:
        return "Switch to plan-only mode — no file writes allowed, only reading and planning"

    @property
    def input_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "reason": {
                    "type": "string",
                    "description": "Why you're entering plan mode",
                },
            },
        }

    def get_prompt(self) -> str:
        return (
            "Switch to plan mode. In plan mode, you can only read files, search, "
            "and create plans — no file writes or bash commands that modify state. "
            "Use this when you want to analyze and plan before making changes."
        )

    async def call(self, tool_input: dict[str, Any], context: ToolContext) -> ToolResult:
        reason = tool_input.get("reason", "User requested plan mode")
        context.permission_mode = "plan"
        return ToolResult(data=f"Entered plan mode. Reason: {reason}\nOnly read-only operations are allowed.")


class ExitPlanModeTool(Tool):
    @property
    def name(self) -> str:
        return "ExitPlanMode"

    @property
    def description(self) -> str:
        return "Exit plan mode and return to normal execution"

    @property
    def input_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "plan_summary": {
                    "type": "string",
                    "description": "Summary of the plan created during plan mode",
                },
            },
        }

    def get_prompt(self) -> str:
        return (
            "Exit plan mode and return to normal execution mode where file writes "
            "and bash commands are allowed. Provide a summary of the plan."
        )

    async def call(self, tool_input: dict[str, Any], context: ToolContext) -> ToolResult:
        summary = tool_input.get("plan_summary", "")
        context.permission_mode = "default"
        msg = "Exited plan mode. Normal execution resumed."
        if summary:
            msg += f"\nPlan summary: {summary}"
        return ToolResult(data=msg)
