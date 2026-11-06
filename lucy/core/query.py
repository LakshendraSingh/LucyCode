"""
Agentic query loop — the heart of Lucy Code.

Implements the streaming tool-use loop:
  1. Send messages to the API
  2. Stream response
  3. If response contains tool_use blocks → execute tools (parallel where safe) → append results → loop
  4. Pre-fetch speculative context (imports, test/source code)
  5. If response has stop_reason=end_turn → return
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, AsyncGenerator

from lucy.api.client import stream_query
from lucy.api.errors import (
    MaxOutputTokensError,
    LucyCodeAPIError,
    PromptTooLongError,
    UserAbortError,
)
from lucy.core.config import get_config
from lucy.core.message import (
    AssistantMessage,
    CompactBoundaryMessage,
    Message,
    MessageUsage,
    RequestStartEvent,
    StreamEvent,
    TextBlock,
    ToolResultBlock,
    ToolUseBlock,
    UserMessage,
    create_assistant_error_message,
    create_tool_result_message,
    messages_to_api_params,
)
from lucy.core.parallel_tools import ParallelToolExecutor
from lucy.core.speculative import get_speculative_engine
from lucy.core.tool import ToolContext, ToolRegistry, ToolResult, find_tool_by_name

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Types
# ---------------------------------------------------------------------------

QueryEvent = StreamEvent | RequestStartEvent | Message


# ---------------------------------------------------------------------------
# Query parameters
# ---------------------------------------------------------------------------

class QueryParams:
    """Parameters for the query loop."""

    def __init__(
        self,
        messages: list[Message],
        system_prompt: str,
        tools: ToolRegistry,
        tool_context: ToolContext,
        model: str | None = None,
        max_tokens: int | None = None,
        max_turns: int = 50,
        thinking_enabled: bool | None = None,
        abort_event: asyncio.Event | None = None,
        parallel_tools: bool = True,
        speculative_execution: bool = True,
    ) -> None:
        self.messages = messages
        self.system_prompt = system_prompt
        self.tools = tools
        self.tool_context = tool_context
        self.model = model
        self.max_tokens = max_tokens
        self.max_turns = max_turns
        self.thinking_enabled = thinking_enabled
        self.abort_event = abort_event or asyncio.Event()
        self.parallel_tools = parallel_tools
        self.speculative_execution = speculative_execution


# ---------------------------------------------------------------------------
# Main query loop
# ---------------------------------------------------------------------------

async def query_loop(
    params: QueryParams,
) -> AsyncGenerator[QueryEvent, None]:
    """The main agentic query loop.

    Yields:
      - RequestStartEvent when a new API request begins
      - StreamEvent during streaming (text_delta, thinking_delta, tool_use_*)
      - UserMessage for tool results
      - AssistantMessage for the final response

    The loop continues as long as the model emits tool_use blocks.
    """
    messages = list(params.messages)
    turn_count = 0
    sequential_tool_turns = 0
    total_usage = MessageUsage()

    # Track tool calls to prevent repeating identical calls (looping)
    tool_call_signatures: dict[str, int] = {}
    parallel_executor = ParallelToolExecutor()
    speculative_engine = get_speculative_engine()

    while turn_count < params.max_turns:
        turn_count += 1

        # Check abort
        if params.abort_event.is_set():
            yield create_assistant_error_message("Request cancelled by user")
            return

        # Signal: new API request
        yield RequestStartEvent()

        # Prepare messages for API
        api_messages = messages_to_api_params(messages)

        # Get tool schemas — filter for local models to prevent loops
        import os
        use_core_only = False
        if params.model and (params.model.startswith("ollama:") or "localhost" in params.model):
            if os.environ.get("LUCY_ALL_TOOLS") != "1":
                use_core_only = True

        tool_schemas = params.tools.get_api_schemas(core_only=use_core_only)

        # Nuclear Loop Suppression:
        # 1. Greeting Hijack: If the user just said "hi", don't give tools to the model.
        if turn_count == 1 and len(messages) > 0:
            last_user_msg = next((m for m in reversed(messages) if isinstance(m, UserMessage)), None)
            if last_user_msg:
                text = last_user_msg.get_text().lower().strip("!. ")
                action_keywords = ["create", "make", "find", "read", "run", "search", "write", "ls", "pwd"]
                is_pure_greeting = text in ["hi", "hello", "hey", "who are you", "what are you"]
                has_action = any(kw in text for kw in action_keywords)

                if is_pure_greeting and not has_action:
                    logger.info("Pure greeting detected. Stripping tools to prevent loops.")
                    tool_schemas = []

        # 2. Sequential Tool Cap: If we've done 3 turns of ONLY tools, force the next turn to be text.
        if sequential_tool_turns >= 3:
            logger.info("Sequential tool limit reached. Forcing text response.")
            tool_schemas = []

        # Stream the API call
        assistant_msg: AssistantMessage | None = None
        try:
            async for event in stream_query(
                messages=api_messages,
                system_prompt=params.system_prompt,
                model=params.model,
                tools=tool_schemas if tool_schemas else None,
                max_tokens=params.max_tokens,
                thinking_enabled=params.thinking_enabled,
                abort_signal=params.abort_event,
            ):
                if isinstance(event, AssistantMessage):
                    assistant_msg = event
                    # Accumulate usage
                    if event.usage:
                        total_usage.input_tokens += event.usage.input_tokens
                        total_usage.output_tokens += event.usage.output_tokens
                        total_usage.cache_creation_input_tokens += event.usage.cache_creation_input_tokens
                        total_usage.cache_read_input_tokens += event.usage.cache_read_input_tokens
                else:
                    yield event

        except UserAbortError:
            yield create_assistant_error_message("Request cancelled by user")
            return
        except PromptTooLongError:
            yield create_assistant_error_message(
                "The conversation has exceeded the model's context window. "
                "Please use /compact to summarize, or /clear to start fresh."
            )
            return
        except LucyCodeAPIError as e:
            yield create_assistant_error_message(f"API error: {e}", api_error=str(e))
            return

        if assistant_msg is None:
            yield create_assistant_error_message("No response received from the API")
            return

        # Yield and record the assistant message
        yield assistant_msg
        messages.append(assistant_msg)

        # Check for tool use
        tool_use_blocks = assistant_msg.get_tool_use_blocks()
        text_content = assistant_msg.get_text()

        if text_content.strip():
            # Model said something to the user, reset the loop counter
            sequential_tool_turns = 0
        elif tool_use_blocks:
            # Model only used tools, increment the loop counter
            sequential_tool_turns += 1

        if not tool_use_blocks:
            # No tool use — we're done
            return

        # Check loop suppression per tool block
        valid_blocks: list[ToolUseBlock] = []
        loop_results: dict[int, UserMessage] = {}

        for idx, tool_use in enumerate(tool_use_blocks):
            sig = f"{tool_use.name}:{json.dumps(tool_use.input, sort_keys=True)}"
            tool_call_signatures[sig] = tool_call_signatures.get(sig, 0) + 1

            if tool_call_signatures[sig] > 3:
                logger.warning("Loop detected: %s called %d times", sig, tool_call_signatures[sig])
                loop_results[idx] = create_tool_result_message(
                    tool_use_id=tool_use.id,
                    result="Error: Loop detected. You have called this exact tool with these parameters multiple times with no progress. Stop and answer the user directly.",
                    is_error=True,
                    source_assistant_uuid=assistant_msg.uuid,
                )
            else:
                valid_blocks.append(tool_use)

        # Execute valid tool blocks (parallel or sequential)
        executed_results: list[UserMessage] = []
        if valid_blocks:
            if params.parallel_tools:
                executed_results = await parallel_executor.execute_tools(
                    tool_use_blocks=valid_blocks,
                    tools=params.tools,
                    context=params.tool_context,
                    assistant_uuid=assistant_msg.uuid,
                )
            else:
                executed_results = await _execute_tools(
                    tool_use_blocks=valid_blocks,
                    tools=params.tools,
                    context=params.tool_context,
                    assistant_uuid=assistant_msg.uuid,
                )

        # Assemble full list of results matching original blocks order
        tool_results: list[UserMessage] = []
        exec_iter = iter(executed_results)
        for idx in range(len(tool_use_blocks)):
            if idx in loop_results:
                tool_results.append(loop_results[idx])
            else:
                try:
                    tool_results.append(next(exec_iter))
                except StopIteration:
                    pass

        # Speculative execution: pre-compute / pre-fetch related context
        if params.speculative_execution and valid_blocks:
            all_speculative_data: dict[str, str] = {}
            for tu in valid_blocks:
                spec_res = await speculative_engine.speculate(tu.name, tu.input, params.tool_context)
                all_speculative_data.update(spec_res)

            if all_speculative_data and tool_results:
                # Append speculative insights to the last tool result message
                spec_formatted = "\n\n".join(
                    f"[{key}]\n{val}" for key, val in all_speculative_data.items()
                )
                last_msg = tool_results[-1]
                if isinstance(last_msg.content, list):
                    for b in last_msg.content:
                        if isinstance(b, ToolResultBlock):
                            b.content = (
                                f"{b.content}\n\n"
                                f"=== Speculative Pre-Fetched Context ===\n"
                                f"{spec_formatted}"
                            )
                            break

        # Yield and record tool results
        for result_msg in tool_results:
            yield result_msg
            messages.append(result_msg)

    # Hit max turns
    yield create_assistant_error_message(
        f"Reached maximum number of turns ({params.max_turns}). "
        "The assistant may continue if you send another message."
    )


# ---------------------------------------------------------------------------
# Tool execution (Sequential fallback)
# ---------------------------------------------------------------------------

async def _execute_tools(
    tool_use_blocks: list[ToolUseBlock],
    tools: ToolRegistry,
    context: ToolContext,
    assistant_uuid: str,
) -> list[UserMessage]:
    """Execute tool_use blocks sequentially and return tool_result messages."""
    result_messages: list[UserMessage] = []

    for tool_use in tool_use_blocks:
        tool = tools.find_by_name(tool_use.name)
        if tool is None:
            result_messages.append(
                create_tool_result_message(
                    tool_use_id=tool_use.id,
                    result=f"Unknown tool: {tool_use.name}",
                    is_error=True,
                    source_assistant_uuid=assistant_uuid,
                )
            )
            continue

        # Check sandbox policy if active
        if getattr(context, "sandbox", None) and getattr(context.sandbox, "is_enabled", False):
            sb_perm = context.sandbox.check_tool_permission(tool.name, tool_use.input, context)
            if sb_perm.behavior.value == "deny":
                result_messages.append(
                    create_tool_result_message(
                        tool_use_id=tool_use.id,
                        result=f"Sandbox policy violation: {sb_perm.message}",
                        is_error=True,
                        source_assistant_uuid=assistant_uuid,
                    )
                )
                continue

        # Permission check
        perm = await tool.check_permissions(tool_use.input, context)
        if perm.behavior.value == "deny":
            result_messages.append(
                create_tool_result_message(
                    tool_use_id=tool_use.id,
                    result=f"Permission denied: {perm.message}",
                    is_error=True,
                    source_assistant_uuid=assistant_uuid,
                )
            )
            continue

        if perm.behavior.value == "ask":
            if not context.is_interactive:
                result_messages.append(
                    create_tool_result_message(
                        tool_use_id=tool_use.id,
                        result="Permission denied: requires user approval (non-interactive mode)",
                        is_error=True,
                        source_assistant_uuid=assistant_uuid,
                    )
                )
                continue
            if context.ask_permission:
                summary = tool.get_tool_use_summary(tool_use.input) or tool_use.name
                approved = context.ask_permission(tool_use.name, summary)
                if not approved:
                    result_messages.append(
                        create_tool_result_message(
                            tool_use_id=tool_use.id,
                            result="Permission denied by user",
                            is_error=True,
                            source_assistant_uuid=assistant_uuid,
                        )
                    )
                    continue

        effective_input = perm.updated_input if perm.updated_input is not None else tool_use.input

        try:
            result = await tool.call(effective_input, context)
            content = result.to_content_string()
            if len(content) > context.max_result_chars:
                content = (
                    content[: context.max_result_chars]
                    + f"\n\n... (truncated, {len(content)} total chars)"
                )
            result_messages.append(
                create_tool_result_message(
                    tool_use_id=tool_use.id,
                    result=content,
                    is_error=result.is_error,
                    source_assistant_uuid=assistant_uuid,
                )
            )
        except Exception as e:
            logger.exception("Tool %s failed", tool_use.name)
            result_messages.append(
                create_tool_result_message(
                    tool_use_id=tool_use.id,
                    result=f"Tool execution error: {e}",
                    is_error=True,
                    source_assistant_uuid=assistant_uuid,
                )
            )

    return result_messages
