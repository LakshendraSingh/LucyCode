"""
Anthropic Claude LLM provider wrapping the official Anthropic async client.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
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
from lucy.api.models import supports_thinking
from lucy.api.providers.base import LLMProvider, ProviderCapabilities

logger = logging.getLogger(__name__)


class AnthropicProvider(LLMProvider):
    """Provider for Anthropic Claude models (Claude 3.5 Haiku, Sonnet 3.5/4, Opus 4)."""

    name: str = "anthropic"
    default_base_url: str = "https://api.anthropic.com"

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
    ) -> None:
        self._custom_api_key = api_key
        self._custom_base_url = base_url

    def get_api_key(self) -> str:
        if self._custom_api_key:
            return self._custom_api_key
        return os.environ.get("ANTHROPIC_API_KEY", "")

    def get_base_url(self) -> str:
        if self._custom_base_url:
            return self._custom_base_url
        return os.environ.get("ANTHROPIC_BASE_URL", self.default_base_url)

    def is_configured(self) -> bool:
        return bool(self.get_api_key())

    def clean_model_name(self, model: str) -> str:
        """Strip 'anthropic:' or 'claude:' prefix if present."""
        if ":" in model:
            prefix, rest = model.split(":", 1)
            if prefix.lower() in ("anthropic", "claude"):
                return rest
        return model

    def get_capabilities(self, model: str) -> ProviderCapabilities:
        clean = self.clean_model_name(model)
        thinking = supports_thinking(clean)
        is_opus = "opus" in clean.lower()

        return ProviderCapabilities(
            supports_streaming=True,
            supports_tool_use=True,
            supports_vision=True,
            supports_thinking=thinking,
            supports_system_prompt=True,
            supports_json_mode=True,
            max_context_window=200000,
            max_output_tokens=32000 if is_opus else 16000,
        )

    def translate_tools(self, tools: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Anthropic format is the native format for LucyCode tools."""
        return tools

    def translate_messages(
        self,
        messages: list[dict[str, Any]],
        system_prompt: str | None = None,
    ) -> list[dict[str, Any]]:
        """Anthropic format is the native format for LucyCode messages."""
        return messages

    async def stream(
        self,
        messages: list[dict[str, Any]],
        system_prompt: str,
        model: str,
        tools: list[dict[str, Any]] | None = None,
        max_tokens: int | None = None,
        thinking_enabled: bool | None = None,
        max_thinking_tokens: int | None = None,
        abort_signal: asyncio.Event | None = None,
        **kwargs: Any,
    ) -> AsyncGenerator[dict[str, Any], None]:
        """Stream responses from the Anthropic API."""
        try:
            import anthropic
        except ImportError:
            yield {
                "type": "error",
                "error": "Anthropic SDK not installed. Install with: pip install lucy[cloud]"
            }
            return

        api_key = self.get_api_key()
        if not api_key:
            yield {
                "type": "error",
                "error": "Anthropic API key not found. Set ANTHROPIC_API_KEY environment variable."
            }
            return

        clean_model = self.clean_model_name(model)
        client = kwargs.get("client") or anthropic.AsyncAnthropic(
            api_key=api_key,
            base_url=self.get_base_url(),
            max_retries=kwargs.get("max_retries", 3),
            timeout=kwargs.get("timeout", 120.0),
        )

        if thinking_enabled is None:
            thinking_enabled = supports_thinking(clean_model)

        params: dict[str, Any] = {
            "model": clean_model,
            "max_tokens": max_tokens or 16000,
            "messages": messages,
            "system": system_prompt,
        }

        if thinking_enabled and supports_thinking(clean_model):
            params["thinking"] = {
                "type": "enabled",
                "budget_tokens": max_thinking_tokens or 10000,
            }

        if tools:
            params["tools"] = tools

        full_text = ""
        current_tool: dict[str, Any] | None = None
        current_tool_input_json = ""
        prompt_tokens = 0
        completion_tokens = 0
        cache_creation_tokens = 0
        cache_read_tokens = 0
        stop_reason: str | None = None
        response_model = clean_model

        try:
            async with client.messages.stream(**params) as stream:
                async for event in stream:
                    if abort_signal and abort_signal.is_set():
                        yield {"type": "error", "error": "Request cancelled by user"}
                        return

                    event_type = getattr(event, "type", None)

                    if event_type == "message_start":
                        msg = getattr(event, "message", None)
                        if msg:
                            response_model = getattr(msg, "model", clean_model)
                            u = getattr(msg, "usage", None)
                            if u:
                                prompt_tokens = getattr(u, "input_tokens", 0)
                                cache_creation_tokens = getattr(u, "cache_creation_input_tokens", 0)
                                cache_read_tokens = getattr(u, "cache_read_input_tokens", 0)

                    elif event_type == "content_block_start":
                        block = getattr(event, "content_block", None)
                        block_type = getattr(block, "type", None)

                        if block_type == "tool_use":
                            current_tool = {
                                "id": getattr(block, "id", ""),
                                "name": getattr(block, "name", ""),
                            }
                            current_tool_input_json = ""

                    elif event_type == "content_block_delta":
                        delta = getattr(event, "delta", None)
                        delta_type = getattr(delta, "type", None)

                        if delta_type == "text_delta":
                            text = getattr(delta, "text", "")
                            full_text += text
                            yield {"type": "text_delta", "text": text}

                        elif delta_type == "thinking_delta":
                            thinking = getattr(delta, "thinking", "")
                            yield {"type": "thinking_delta", "thinking": thinking}

                        elif delta_type == "input_json_delta":
                            current_tool_input_json += getattr(delta, "partial_json", "")

                    elif event_type == "content_block_stop":
                        if current_tool is not None:
                            try:
                                tool_input = json.loads(current_tool_input_json) if current_tool_input_json else {}
                            except json.JSONDecodeError:
                                tool_input = {}

                            yield {
                                "type": "tool_use",
                                "id": current_tool["id"],
                                "name": current_tool["name"],
                                "input": tool_input,
                            }
                            current_tool = None
                            current_tool_input_json = ""

                    elif event_type == "message_delta":
                        delta = getattr(event, "delta", None)
                        if delta:
                            stop_reason = getattr(delta, "stop_reason", None)
                        u = getattr(event, "usage", None)
                        if u:
                            completion_tokens = getattr(u, "output_tokens", 0)

            yield {
                "type": "done",
                "text": full_text,
                "model": response_model,
                "eval_count": completion_tokens,
                "prompt_eval_count": prompt_tokens,
                "cache_creation_input_tokens": cache_creation_tokens,
                "cache_read_input_tokens": cache_read_tokens,
                "stop_reason": stop_reason,
            }

        except anthropic.AuthenticationError as e:
            yield {"type": "error", "error": f"Anthropic authentication error: {e}"}
        except anthropic.RateLimitError as e:
            yield {"type": "error", "error": f"Anthropic rate limit exceeded: {e}"}
        except anthropic.APIStatusError as e:
            yield {"type": "error", "error": f"Anthropic API status error ({e.status_code}): {e.message}"}
        except anthropic.APIConnectionError as e:
            yield {"type": "error", "error": f"Anthropic connection error: {e}"}
        except Exception as e:
            logger.exception("Anthropic streaming error")
            yield {"type": "error", "error": f"Anthropic error: {e}"}
