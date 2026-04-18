"""
Agentic query loop — the heart of Lucy Code.

Implements the streaming tool-use loop:
  1. Send messages to the API
  2. Stream response
  3. If response contains tool_use blocks → execute tools → append results → loop
  4. If response has stop_reason=end_turn → return

Mirrors the query loop in the original query.ts.
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
                # Only strip tools for pure greetings. If the prompt contains action words, keep tools.
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

        # Execute tools
        tool_results = []
        for tool_use in tool_use_blocks:
            # signature = name + json_input
            sig = f"{tool_use.name}:{json.dumps(tool_use.input, sort_keys=True)}"
            tool_call_signatures[sig] = tool_call_signatures.get(sig, 0) + 1
            
            if tool_call_signatures[sig] > 3:
                # Detected a loop
                logger.warning(f"Loop detected: {sig} called {tool_call_signatures[sig]} times")
                tool_results.append(
                    create_tool_result_message(
                        tool_use_id=tool_use.id,
                        result="Error: Loop detected. You have called this exact tool with these parameters multiple times with no progress. Stop and answer the user directly.",
                        is_error=True,
                        source_assistant_uuid=assistant_msg.uuid,
                    )
                )
                continue

            # Real execution
            results = await _execute_tools(
                tool_use_blocks=[tool_use],
                tools=params.tools,
                context=params.tool_context,
                assistant_uuid=assistant_msg.uuid,
            )
            tool_results.extend(results)

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
# Tool execution
# ---------------------------------------------------------------------------

async def _execute_tools(
    tool_use_blocks: list[ToolUseBlock],
    tools: ToolRegistry,
    context: ToolContext,
    assistant_uuid: str,
) -> list[UserMessage]:
    """Execute tool_use blocks and return tool_result messages.

    Currently executes tools sequentially. Read-only tools that are
    concurrent-safe could be parallelized in the future.
    """
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
            # In non-interactive mode, deny
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
            # Ask user
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

        # Use updated input if permission modified it
        effective_input = perm.updated_input if perm.updated_input is not None else tool_use.input

        # Execute
        try:
            result = await tool.call(effective_input, context)
            content = result.to_content_string()
            # Truncate if too large
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
