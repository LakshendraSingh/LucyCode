"""
Parallel tool execution — run independent tools concurrently.

When the LLM requests multiple tools in a single turn, execute
read-only tools in parallel for faster response times.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from lucy.core.message import (
    ToolUseBlock,
    UserMessage,
    create_tool_result_message,
)
from lucy.core.tool import (
    PermissionBehavior,
    Tool,
    ToolContext,
    ToolRegistry,
    ToolResult,
)

logger = logging.getLogger(__name__)


class ParallelToolExecutor:
    """Execute tools in parallel when safe to do so."""

    def __init__(self, max_concurrency: int = 8) -> None:
        self.max_concurrency = max_concurrency
        self._semaphore = asyncio.Semaphore(max_concurrency)

    async def execute_tools(
        self,
        tool_use_blocks: list[ToolUseBlock],
        tools: ToolRegistry,
        context: ToolContext,
        assistant_uuid: str,
    ) -> list[UserMessage]:
        """Execute tools, parallelizing when safe.

        Strategy:
        - Read-only tools with is_concurrent_safe=True run in parallel
        - Write tools run sequentially
        - Mixed: run reads first (parallel), then writes (sequential)
        - Output list preserves the exact order of tool_use_blocks
        """
        if not tool_use_blocks:
            return []

        # If only one tool call, execute directly
        if len(tool_use_blocks) == 1:
            return [await self._execute_single_block(tool_use_blocks[0], tools, context, assistant_uuid)]

        # Pre-process tools, validate permissions, and partition into parallel reads and sequential writes
        # We pre-check permissions upfront sequentially so interactive prompts occur in predictable order.
        prepared_calls: list[dict[str, Any]] = []
        results: list[UserMessage | None] = [None] * len(tool_use_blocks)

        for idx, tool_use in enumerate(tool_use_blocks):
            tool = tools.find_by_name(tool_use.name)
            if tool is None:
                results[idx] = create_tool_result_message(
                    tool_use_id=tool_use.id,
                    result=f"Unknown tool: {tool_use.name}",
                    is_error=True,
                    source_assistant_uuid=assistant_uuid,
                )
                continue

            # Check sandbox policy if active
            if getattr(context, "sandbox", None) and getattr(context.sandbox, "is_enabled", False):
                sb_perm = context.sandbox.check_tool_permission(tool.name, tool_use.input, context)
                if sb_perm.behavior == PermissionBehavior.DENY:
                    results[idx] = create_tool_result_message(
                        tool_use_id=tool_use.id,
                        result=f"Sandbox policy violation: {sb_perm.message}",
                        is_error=True,
                        source_assistant_uuid=assistant_uuid,
                    )
                    continue

            # Check permissions
            perm = await tool.check_permissions(tool_use.input, context)
            if perm.behavior == PermissionBehavior.DENY:
                results[idx] = create_tool_result_message(
                    tool_use_id=tool_use.id,
                    result=f"Permission denied: {perm.message}",
                    is_error=True,
                    source_assistant_uuid=assistant_uuid,
                )
                continue

            if perm.behavior == PermissionBehavior.ASK:
                if not context.is_interactive:
                    results[idx] = create_tool_result_message(
                        tool_use_id=tool_use.id,
                        result="Permission denied: requires user approval (non-interactive mode)",
                        is_error=True,
                        source_assistant_uuid=assistant_uuid,
                    )
                    continue

                if context.ask_permission:
                    summary = tool.get_tool_use_summary(tool_use.input) or tool_use.name
                    approved = context.ask_permission(tool_use.name, summary)
                    if not approved:
                        results[idx] = create_tool_result_message(
                            tool_use_id=tool_use.id,
                            result="Permission denied by user",
                            is_error=True,
                            source_assistant_uuid=assistant_uuid,
                        )
                        continue

            effective_input = perm.updated_input if perm.updated_input is not None else tool_use.input
            is_parallel = tool.is_read_only(effective_input) and tool.is_concurrent_safe(effective_input)

            prepared_calls.append({
                "index": idx,
                "tool": tool,
                "tool_use": tool_use,
                "input": effective_input,
                "is_parallel": is_parallel,
            })

        # Separate into parallel (reads) and sequential (writes)
        parallel_calls = [c for c in prepared_calls if c["is_parallel"]]
        sequential_calls = [c for c in prepared_calls if not c["is_parallel"]]

        # 1. Execute parallel reads first
        if parallel_calls:
            logger.debug("Executing %d read tools concurrently", len(parallel_calls))

            async def _run_parallel(call_spec: dict[str, Any]) -> tuple[int, UserMessage]:
                async with self._semaphore:
                    msg = await self._invoke_tool(
                        tool=call_spec["tool"],
                        effective_input=call_spec["input"],
                        tool_use=call_spec["tool_use"],
                        context=context,
                        assistant_uuid=assistant_uuid,
                    )
                    return call_spec["index"], msg

            parallel_results = await asyncio.gather(*[_run_parallel(c) for c in parallel_calls], return_exceptions=True)
            for item in parallel_results:
                if isinstance(item, Exception):
                    logger.error("Parallel execution error: %s", item)
                    continue
                c_idx, msg = item
                results[c_idx] = msg

        # 2. Execute sequential writes in order
        if sequential_calls:
            logger.debug("Executing %d write/sequential tools in series", len(sequential_calls))
            for call_spec in sequential_calls:
                msg = await self._invoke_tool(
                    tool=call_spec["tool"],
                    effective_input=call_spec["input"],
                    tool_use=call_spec["tool_use"],
                    context=context,
                    assistant_uuid=assistant_uuid,
                )
                results[call_spec["index"]] = msg

        # Fallback for any slots that were unexpectedly missed
        final_messages: list[UserMessage] = []
        for idx, res in enumerate(results):
            if res is not None:
                final_messages.append(res)
            else:
                final_messages.append(create_tool_result_message(
                    tool_use_id=tool_use_blocks[idx].id,
                    result="Tool execution aborted or produced no result",
                    is_error=True,
                    source_assistant_uuid=assistant_uuid,
                ))

        return final_messages

    async def _execute_single_block(
        self,
        tool_use: ToolUseBlock,
        tools: ToolRegistry,
        context: ToolContext,
        assistant_uuid: str,
    ) -> UserMessage:
        """Execute a single tool use block sequentially."""
        tool = tools.find_by_name(tool_use.name)
        if tool is None:
            return create_tool_result_message(
                tool_use_id=tool_use.id,
                result=f"Unknown tool: {tool_use.name}",
                is_error=True,
                source_assistant_uuid=assistant_uuid,
            )

        perm = await tool.check_permissions(tool_use.input, context)
        if perm.behavior == PermissionBehavior.DENY:
            return create_tool_result_message(
                tool_use_id=tool_use.id,
                result=f"Permission denied: {perm.message}",
                is_error=True,
                source_assistant_uuid=assistant_uuid,
            )

        if perm.behavior == PermissionBehavior.ASK:
            if not context.is_interactive:
                return create_tool_result_message(
                    tool_use_id=tool_use.id,
                    result="Permission denied: requires user approval (non-interactive mode)",
                    is_error=True,
                    source_assistant_uuid=assistant_uuid,
                )
            if context.ask_permission:
                summary = tool.get_tool_use_summary(tool_use.input) or tool_use.name
                if not context.ask_permission(tool_use.name, summary):
                    return create_tool_result_message(
                        tool_use_id=tool_use.id,
                        result="Permission denied by user",
                        is_error=True,
                        source_assistant_uuid=assistant_uuid,
                    )

        effective_input = perm.updated_input if perm.updated_input is not None else tool_use.input
        return await self._invoke_tool(tool, effective_input, tool_use, context, assistant_uuid)

    async def _invoke_tool(
        self,
        tool: Tool,
        effective_input: dict[str, Any],
        tool_use: ToolUseBlock,
        context: ToolContext,
        assistant_uuid: str,
    ) -> UserMessage:
        """Call the tool and format its ToolResult into a UserMessage."""
        try:
            result = await tool.call(effective_input, context)
            content = result.to_content_string()

            # Truncate output if it exceeds context limit
            if len(content) > context.max_result_chars:
                content = (
                    content[: context.max_result_chars]
                    + f"\n\n... (truncated, {len(content)} total chars)"
                )

            return create_tool_result_message(
                tool_use_id=tool_use.id,
                result=content,
                is_error=result.is_error,
                source_assistant_uuid=assistant_uuid,
            )
        except Exception as e:
            logger.exception("Tool %s failed during execution", tool_use.name)
            return create_tool_result_message(
                tool_use_id=tool_use.id,
                result=f"Tool execution error: {e}",
                is_error=True,
                source_assistant_uuid=assistant_uuid,
            )
