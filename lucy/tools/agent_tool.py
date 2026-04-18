"""
AgentTool — Sub-agent orchestration.

Spawns a nested query loop with its own context, tools, and
conversation state. Used for complex multi-step tasks that
benefit from isolated execution.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from lucy.core.tool import (
    PermissionBehavior,
    PermissionResult,
    Tool,
    ToolContext,
    ToolResult,
    get_tool_registry,
)

logger = logging.getLogger(__name__)


class AgentTool(Tool):
    """Spawn a sub-agent to handle a complex task."""

    @property
    def name(self) -> str:
        return "Agent"

    @property
    def aliases(self) -> list[str]:
        return ["SubAgent", "Dispatch"]

    @property
    def description(self) -> str:
        return "Spawn a sub-agent to work on a subtask"

    @property
    def input_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "task": {
                    "type": "string",
                    "description": (
                        "A detailed description of the task for the sub-agent. "
                        "Be specific about what needs to be done and what the "
                        "expected output should be."
                    ),
                },
                "working_directory": {
                    "type": "string",
                    "description": "Optional working directory for the sub-agent",
                },
            },
            "required": ["task"],
        }

    def get_prompt(self) -> str:
        return (
            "Launch a sub-agent to work on a subtask independently. "
            "The sub-agent has its own conversation context and can use all tools. "
            "Use this for complex, multi-step tasks that are well-defined and self-contained, "
            "such as: implementing a feature across multiple files, running a test suite "
            "and fixing failures, or researching and summarizing information. "
            "Provide a detailed task description so the sub-agent can work independently. "
            "The sub-agent's final response will be returned as the result."
        )

    async def check_permissions(
        self, tool_input: dict[str, Any], context: ToolContext
    ) -> PermissionResult:
        if context.permission_mode == "auto_accept":
            return PermissionResult(behavior=PermissionBehavior.ALLOW, updated_input=tool_input)
        task = tool_input.get("task", "")
        preview = task[:100] + ("..." if len(task) > 100 else "")
        return PermissionResult(
            behavior=PermissionBehavior.ASK,
            message=f"Launch sub-agent: {preview}",
            updated_input=tool_input,
        )

    def get_activity_description(self, tool_input: dict[str, Any] | None = None) -> str | None:
        if tool_input:
            task = tool_input.get("task", "")
            preview = task[:60] + ("..." if len(task) > 60 else "")
            return f"Sub-agent: {preview}"
        return "Running sub-agent"

    async def call(self, tool_input: dict[str, Any], context: ToolContext) -> ToolResult:
        # Deferred imports to avoid import-time dependency on anthropic SDK
        from lucy.core.context import build_system_prompt, get_lucymd_content, get_git_status
        from lucy.core.message import AssistantMessage, StreamEvent, UserMessage, create_user_message
        from lucy.core.query import QueryParams, query_loop

        task = tool_input.get("task", "")
        working_dir = tool_input.get("working_directory", "")

        if not task:
            return ToolResult(error="task is required")

        # Set up sub-agent context
        cwd = working_dir or context.cwd
        git_status = await get_git_status(cwd)
        lucymd = get_lucymd_content(cwd)
        system_prompt = build_system_prompt(
            cwd=cwd, git_status=git_status, lucymd=lucymd,
        )

        # Create sub-agent tool context (isolated from parent)
        sub_context = ToolContext(
            cwd=cwd,
            permission_mode=context.permission_mode,
            is_interactive=context.is_interactive,
            ask_permission=context.ask_permission,
            max_result_chars=context.max_result_chars,
        )

        # Start with the task as the user message
        user_msg = create_user_message(
            f"Complete this task:\n\n{task}\n\n"
            "Work step by step. Use tools as needed. "
            "When done, provide a clear summary of what you accomplished."
        )

        registry = get_tool_registry()
        abort_event = asyncio.Event()

        params = QueryParams(
            messages=[user_msg],
            system_prompt=system_prompt,
            tools=registry,
            tool_context=sub_context,
            max_turns=30,  # Sub-agents have a lower turn limit
            abort_event=abort_event,
        )

        # Run the sub-agent loop
        result_text = ""
        turn_count = 0

        try:
            async for event in query_loop(params):
                if isinstance(event, AssistantMessage):
                    text = event.get_text()
                    if text:
                        result_text = text  # Keep the last response
                    turn_count += 1
                elif isinstance(event, UserMessage):
                    pass  # Tool results
                elif isinstance(event, StreamEvent):
                    pass  # Streaming events

            if not result_text:
                result_text = "(Sub-agent produced no output)"

            return ToolResult(
                data=f"Sub-agent completed ({turn_count} turns):\n\n{result_text}"
            )

        except Exception as e:
            logger.exception("Sub-agent failed")
            return ToolResult(error=f"Sub-agent error: {e}")
