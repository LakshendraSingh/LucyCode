"""
Abstract base class and capability definitions for LLM providers.
"""

from __future__ import annotations

import asyncio
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, AsyncGenerator


@dataclass
class ProviderCapabilities:
    """Capabilities supported by a specific provider or model."""

    supports_streaming: bool = True
    supports_tool_use: bool = True
    supports_vision: bool = False
    supports_thinking: bool = False
    supports_system_prompt: bool = True
    supports_json_mode: bool = False
    max_context_window: int = 128000
    max_output_tokens: int = 16384


class LLMProvider(ABC):
    """Abstract base for all LLM providers."""

    name: str = "base"

    @abstractmethod
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
        """Stream responses from the LLM provider.

        Yields dictionaries with one of the following event types:
          - {"type": "text_delta", "text": "..."}
          - {"type": "tool_use", "id": "...", "name": "...", "input": {...}}
          - {"type": "thinking_delta", "thinking": "..."}
          - {"type": "done", "text": "...", "model": "...", "eval_count": 0, "prompt_eval_count": 0}
          - {"type": "error", "error": "..."}
        """

    @abstractmethod
    def get_capabilities(self, model: str) -> ProviderCapabilities:
        """Return the capabilities supported by this provider for the specified model."""

    @abstractmethod
    def translate_tools(self, tools: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Translate from Lucy's Anthropic-style tool format to provider's format."""

    @abstractmethod
    def translate_messages(
        self,
        messages: list[dict[str, Any]],
        system_prompt: str | None = None,
    ) -> list[dict[str, Any]]:
        """Translate message format for this provider."""

    def is_configured(self) -> bool:
        """Check if provider has the required credentials or endpoints configured."""
        return True
