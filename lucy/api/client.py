"""
Multi-provider API client with streaming support.

Routes queries to the correct backend:
  - Anthropic API (claude-*) — requires `anthropic` package
  - Ollama / OpenAI-compatible / llama.cpp — requires `aiohttp` package

All providers produce the same output types (StreamEvent, AssistantMessage).
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, AsyncGenerator

from lucy.api.errors import (
    AuthenticationError,
    ConnectionError_,
    MaxOutputTokensError,
    LucyCodeAPIError,
    OverloadedError,
    PromptTooLongError,
    RateLimitError,
    UserAbortError,
)
from lucy.api.models import (
    calculate_cost,
    get_max_output_tokens,
    is_offline_model,
    resolve_model,
    supports_thinking,
)
from lucy.core.config import get_config
from lucy.core.message import (
    AssistantMessage,
    ContentBlock,
    MessageUsage,
    RedactedThinkingBlock,
    StreamEvent,
    TextBlock,
    ThinkingBlock,
    ToolUseBlock,
    messages_to_api_params,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Client creation (Anthropic)
# ---------------------------------------------------------------------------

def create_client(
    api_key: str | None = None,
    base_url: str | None = None,
    max_retries: int | None = None,
    timeout: float | None = None,
):
    """Create an Anthropic async client. Returns None if anthropic is not installed."""
    try:
        import anthropic
    except ImportError:
        return None

    config = get_config()
    return anthropic.AsyncAnthropic(
        api_key=api_key or config.api_key,
        base_url=base_url or config.base_url,
        max_retries=max_retries if max_retries is not None else config.max_retries,
        timeout=timeout or config.timeout,
    )


# ---------------------------------------------------------------------------
# Streaming query — unified entry point
# ---------------------------------------------------------------------------

async def stream_query(
    messages: list[Any],
    system_prompt: str | list[dict[str, Any]],
    model: str | None = None,
    tools: list[dict[str, Any]] | None = None,
    max_tokens: int | None = None,
    thinking_enabled: bool | None = None,
    max_thinking_tokens: int | None = None,
    client: Any | None = None,
    abort_signal: asyncio.Event | None = None,
) -> AsyncGenerator[StreamEvent | AssistantMessage, None]:
    """Stream a query to the appropriate backend.

    Automatically routes to Anthropic API or local provider based on the model name.
    Yields StreamEvents during streaming and a final AssistantMessage.
    """
    config = get_config()
    model = resolve_model(model or config.model)
    max_tokens = max_tokens or get_max_output_tokens(model)

    # Route to local provider for offline models or local weights
    from lucy.api.providers import ProviderType, detect_provider
    provider_type, _ = detect_provider(model)

    if is_offline_model(model) or provider_type == ProviderType.WEIGHTS:
        async for event in _stream_local_model(
            messages=messages,
            system_prompt=system_prompt if isinstance(system_prompt, str) else "\n".join(
                b.get("text", "") for b in system_prompt if isinstance(b, dict)
            ),
            model=model,
            tools=tools,
            max_tokens=max_tokens,
            abort_signal=abort_signal,
        ):
            yield event
        return

    # Anthropic API path
    async for event in _stream_anthropic(
        messages=messages,
        system_prompt=system_prompt,
        model=model,
        tools=tools,
        max_tokens=max_tokens,
        thinking_enabled=thinking_enabled,
        max_thinking_tokens=max_thinking_tokens,
        client=client,
        abort_signal=abort_signal,
    ):
        yield event


# ---------------------------------------------------------------------------
# Local model streaming
# ---------------------------------------------------------------------------

async def _stream_local_model(
    messages: list[Any],
    system_prompt: str,
    model: str,
    tools: list[dict[str, Any]] | None = None,
    max_tokens: int = 4096,
    abort_signal: asyncio.Event | None = None,
) -> AsyncGenerator[StreamEvent | AssistantMessage, None]:
    """Stream from a local model provider (Ollama, OpenAI-compat, llama.cpp)."""
    from lucy.api.providers import stream_local

    # Convert API messages to simple format for local providers
    simple_messages = []
    for msg in messages:
        if isinstance(msg, dict):
            role = msg.get("role", "user")
            content = msg.get("content", "")
            if isinstance(content, list):
                # Extract text from content blocks
                text_parts = []
                for block in content:
                    if isinstance(block, dict):
                        if block.get("type") == "text":
                            text_parts.append(block.get("text", ""))
                        elif block.get("type") == "tool_result":
                            text_parts.append(str(block.get("content", "")))
                content = "\n".join(text_parts)
            simple_messages.append({"role": role, "content": content})

    content_blocks: list[ContentBlock] = []
    full_text = ""
    usage = MessageUsage()

    async for chunk in stream_local(
        messages=simple_messages,
        system_prompt=system_prompt,
        model=model,
        tools=tools,
        max_tokens=max_tokens,
    ):
        # Check abort
        if abort_signal and abort_signal.is_set():
            raise UserAbortError()

        chunk_type = chunk.get("type", "")

        if chunk_type == "text_delta":
            text = chunk.get("text", "")
            full_text += text
            yield StreamEvent(type="text_delta", data={"text": text})

        elif chunk_type == "tool_use":
            tool_block = ToolUseBlock(
                id=chunk.get("id", ""),
                name=chunk.get("name", ""),
                input=chunk.get("input", {}),
            )
            content_blocks.append(tool_block)
            yield StreamEvent(
                type="tool_use_start",
                data={"id": tool_block.id, "name": tool_block.name},
            )
            yield StreamEvent(
                type="tool_use_complete",
                data={"id": tool_block.id, "name": tool_block.name, "input": tool_block.input},
            )

        elif chunk_type == "done":
            usage.input_tokens = chunk.get("prompt_eval_count", 0)
            usage.output_tokens = chunk.get("eval_count", 0)

        elif chunk_type == "error":
            raise LucyCodeAPIError(chunk.get("error", "Unknown local model error"))

    # Add accumulated text as a content block
    if full_text:
        content_blocks.insert(0, TextBlock(text=full_text))

    # Build final message
    assistant_msg = AssistantMessage(
        content=content_blocks,
        model=model,
        stop_reason="end_turn",
        usage=usage,
    )

    from lucy.utils.cost import get_session_tracker
    get_session_tracker().add_usage(model, usage)

    logger.debug(
        "Local model response: model=%s, output=%d chars",
        model, len(full_text),
    )

    yield assistant_msg


# ---------------------------------------------------------------------------
# Anthropic API streaming
# ---------------------------------------------------------------------------

async def _stream_anthropic(
    messages: list[Any],
    system_prompt: str | list[dict[str, Any]],
    model: str,
    tools: list[dict[str, Any]] | None = None,
    max_tokens: int | None = None,
    thinking_enabled: bool | None = None,
    max_thinking_tokens: int | None = None,
    client: Any | None = None,
    abort_signal: asyncio.Event | None = None,
) -> AsyncGenerator[StreamEvent | AssistantMessage, None]:
    """Stream from the Anthropic API."""
    try:
        import anthropic
    except ImportError:
        raise LucyCodeAPIError(
            "Anthropic SDK not installed. Install with: pip install lucy[cloud]\n"
            "Or use an offline model: lucy --model ollama:llama3.1"
        )

    config = get_config()
    client = client or create_client()

    if thinking_enabled is None:
        thinking_enabled = config.thinking_enabled and supports_thinking(model)

    # Build system prompt
    if isinstance(system_prompt, str):
        system_param: str | list[dict[str, Any]] = system_prompt
    else:
        system_param = system_prompt

    # Build request params
    params: dict[str, Any] = {
        "model": model,
        "max_tokens": max_tokens,
        "messages": messages,
        "system": system_param,
    }

    # Add thinking
    if thinking_enabled:
        thinking_budget = max_thinking_tokens or config.max_thinking_tokens
        params["thinking"] = {
            "type": "enabled",
            "budget_tokens": thinking_budget,
        }

    # Add tools
    if tools:
        params["tools"] = tools

    # Stream the response
    content_blocks: list[ContentBlock] = []
    current_text = ""
    current_thinking = ""
    current_tool: dict[str, Any] | None = None
    current_tool_input_json = ""
    usage = MessageUsage()
    stop_reason: str | None = None
    response_model = model

    try:
        async with client.messages.stream(**params) as stream:
            async for event in stream:
                # Check abort
                if abort_signal and abort_signal.is_set():
                    raise UserAbortError()

                event_type = getattr(event, "type", None)

                if event_type == "message_start":
                    msg = getattr(event, "message", None)
                    if msg:
                        response_model = getattr(msg, "model", model)
                        u = getattr(msg, "usage", None)
                        if u:
                            usage.input_tokens = getattr(u, "input_tokens", 0)
                            usage.cache_creation_input_tokens = getattr(
                                u, "cache_creation_input_tokens", 0
                            )
                            usage.cache_read_input_tokens = getattr(
                                u, "cache_read_input_tokens", 0
                            )

                elif event_type == "content_block_start":
                    block = getattr(event, "content_block", None)
                    block_type = getattr(block, "type", None)

                    if block_type == "text":
                        current_text = ""
                    elif block_type == "thinking":
                        current_thinking = ""
                    elif block_type == "tool_use":
                        current_tool = {
                            "id": getattr(block, "id", ""),
                            "name": getattr(block, "name", ""),
                        }
                        current_tool_input_json = ""
                        yield StreamEvent(
                            type="tool_use_start",
                            data={"id": current_tool["id"], "name": current_tool["name"]},
                        )

                elif event_type == "content_block_delta":
                    delta = getattr(event, "delta", None)
                    delta_type = getattr(delta, "type", None)

                    if delta_type == "text_delta":
                        text = getattr(delta, "text", "")
                        current_text += text
                        yield StreamEvent(type="text_delta", data={"text": text})

                    elif delta_type == "thinking_delta":
                        thinking = getattr(delta, "thinking", "")
                        current_thinking += thinking
                        yield StreamEvent(type="thinking_delta", data={"thinking": thinking})

                    elif delta_type == "input_json_delta":
                        json_str = getattr(delta, "partial_json", "")
                        current_tool_input_json += json_str

                elif event_type == "content_block_stop":
                    idx = getattr(event, "index", 0)
                    # Determine what type of block just ended
                    if current_tool is not None:
                        # Parse accumulated JSON for tool input
                        import json

                        try:
                            tool_input = json.loads(current_tool_input_json) if current_tool_input_json else {}
                        except json.JSONDecodeError:
                            tool_input = {}

                        content_blocks.append(
                            ToolUseBlock(
                                id=current_tool["id"],
                                name=current_tool["name"],
                                input=tool_input,
                            )
                        )
                        yield StreamEvent(
                            type="tool_use_complete",
                            data={
                                "id": current_tool["id"],
                                "name": current_tool["name"],
                                "input": tool_input,
                            },
                        )
                        current_tool = None
                        current_tool_input_json = ""
                    elif current_thinking:
                        content_blocks.append(
                            ThinkingBlock(thinking=current_thinking)
                        )
                        current_thinking = ""
                    elif current_text:
                        content_blocks.append(TextBlock(text=current_text))
                        current_text = ""

                elif event_type == "message_delta":
                    delta = getattr(event, "delta", None)
                    if delta:
                        stop_reason = getattr(delta, "stop_reason", None)
                    u = getattr(event, "usage", None)
                    if u:
                        usage.output_tokens = getattr(u, "output_tokens", 0)

                elif event_type == "message_stop":
                    pass  # Handled below

        # Finalize any remaining text/thinking that wasn't followed by content_block_stop
        if current_text:
            content_blocks.append(TextBlock(text=current_text))
        if current_thinking:
            content_blocks.append(ThinkingBlock(thinking=current_thinking))

    except anthropic.AuthenticationError as e:
        raise AuthenticationError(str(e)) from e
    except anthropic.RateLimitError as e:
        raise RateLimitError(str(e)) from e
    except anthropic.APIStatusError as e:
        if e.status_code == 529:
            raise OverloadedError(str(e)) from e
        if e.status_code == 400 and "prompt is too long" in str(e).lower():
            raise PromptTooLongError(str(e)) from e
        raise LucyCodeAPIError(str(e), status_code=e.status_code) from e
    except anthropic.APIConnectionError as e:
        raise ConnectionError_(str(e)) from e

    # Build the final AssistantMessage
    assistant_msg = AssistantMessage(
        content=content_blocks,
        model=response_model,
        stop_reason=stop_reason,
        usage=usage,
    )

    # Calculate cost
    from lucy.utils.cost import get_session_tracker
    cost = get_session_tracker().add_usage(response_model, usage)
    logger.debug(
        "API response: model=%s, input=%d, output=%d, cost=$%.4f, stop=%s",
        response_model,
        usage.input_tokens,
        usage.output_tokens,
        cost,
        stop_reason,
    )

    yield assistant_msg


# ---------------------------------------------------------------------------
# Non-streaming query (convenience)
# ---------------------------------------------------------------------------

async def query(
    messages: list[Any],
    system_prompt: str | list[dict[str, Any]],
    **kwargs: Any,
) -> AssistantMessage:
    """Non-streaming query — returns a single AssistantMessage."""
    assistant_msg: AssistantMessage | None = None
    async for event in stream_query(messages, system_prompt, **kwargs):
        if isinstance(event, AssistantMessage):
            assistant_msg = event
    if assistant_msg is None:
        raise LucyCodeAPIError("No assistant message received")
    return assistant_msg


# ---------------------------------------------------------------------------
# API key verification
# ---------------------------------------------------------------------------

async def verify_api_key(api_key: str) -> bool:
    """Quick check that an API key is valid."""
    try:
        import anthropic
    except ImportError:
        return False

    try:
        client = create_client(api_key=api_key, max_retries=1, timeout=15)
        await client.messages.create(
            model="claude-3-5-haiku-20241022",
            max_tokens=1,
            messages=[{"role": "user", "content": "test"}],
        )
        return True
    except anthropic.AuthenticationError:
        return False
    except Exception:
        # Network errors, etc. — key might be valid
        raise
