"""
Direct model weight loading LLM provider (GGUF / Hugging Face safetensors).
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, AsyncGenerator

from lucy.api.providers.base import LLMProvider, ProviderCapabilities

logger = logging.getLogger(__name__)


class WeightsLLMProvider(LLMProvider):
    """Provider for directly loaded local model weights (GGUF or Hugging Face)."""

    name: str = "weights"

    def is_configured(self) -> bool:
        return True

    def get_capabilities(self, model: str) -> ProviderCapabilities:
        return ProviderCapabilities(
            supports_streaming=True,
            supports_tool_use=False,
            supports_vision=False,
            supports_thinking=False,
            supports_system_prompt=True,
            supports_json_mode=False,
            max_context_window=32768,
            max_output_tokens=4096,
        )

    def translate_tools(self, tools: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return tools

    def translate_messages(
        self,
        messages: list[dict[str, Any]],
        system_prompt: str | None = None,
    ) -> list[dict[str, Any]]:
        api_messages: list[dict[str, Any]] = []
        for msg in messages:
            role = msg.get("role", "user") if isinstance(msg, dict) else getattr(msg, "role", "user")
            content = msg.get("content", "") if isinstance(msg, dict) else getattr(msg, "content", "")
            if isinstance(content, list):
                text_parts: list[str] = []
                for b in content:
                    if isinstance(b, dict):
                        if b.get("type") == "text":
                            text_parts.append(b.get("text", ""))
                        elif b.get("type") == "tool_result":
                            res = b.get("content", "")
                            if isinstance(res, list):
                                res = "\n".join(x.get("text", "") if isinstance(x, dict) else str(x) for x in res)
                            text_parts.append(f"[Tool Result]: {res}")
                        elif "text" in b:
                            text_parts.append(str(b["text"]))
                    else:
                        text = getattr(b, "text", "") or getattr(b, "content", "")
                        if text:
                            text_parts.append(str(text))
                content_str = "\n".join(text_parts)
            else:
                content_str = str(content or "")
            api_messages.append({"role": role, "content": content_str})
        return api_messages

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
        from lucy.api.weights_provider import WeightsProvider

        path = model
        if path.startswith("weights:"):
            path = path[8:]

        provider = WeightsProvider(path)
        norm_messages = self.translate_messages(messages, system_prompt)
        async for chunk in provider.stream(
            norm_messages,
            system_prompt,
            max_tokens=max_tokens,
            abort_signal=abort_signal,
            **kwargs,
        ):
            if abort_signal and abort_signal.is_set():
                yield {"type": "error", "error": "Request cancelled by user"}
                return
            yield chunk
