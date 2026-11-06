"""
OpenAI LLM provider using pure aiohttp REST API calls (no external SDK dependency).
"""

from __future__ import annotations

import os
from typing import Any

from lucy.api.providers.base import ProviderCapabilities
from lucy.api.providers.openai_compat_provider import OpenAICompatProvider


class OpenAIProvider(OpenAICompatProvider):
    """Provider for OpenAI models (GPT-4o, GPT-4.1, o1, o3, o4-mini, etc.)."""

    name: str = "openai"
    default_base_url: str = "https://api.openai.com/v1"
    api_key_env_var: str = "OPENAI_API_KEY"

    def get_base_url(self) -> str:
        if self._custom_base_url:
            return self._custom_base_url
        env_url = os.environ.get("OPENAI_BASE_URL", os.environ.get("OPENAI_API_BASE", ""))
        return env_url or self.default_base_url

    def get_capabilities(self, model: str) -> ProviderCapabilities:
        clean = self.clean_model_name(model).lower()
        is_reasoning = clean.startswith(("o1", "o3", "o4"))

        if is_reasoning:
            return ProviderCapabilities(
                supports_streaming=True,
                supports_tool_use=True,
                supports_vision=True,
                supports_thinking=True,
                supports_system_prompt=True,
                supports_json_mode=True,
                max_context_window=200000,
                max_output_tokens=100000,
            )

        return ProviderCapabilities(
            supports_streaming=True,
            supports_tool_use=True,
            supports_vision=True,
            supports_thinking=False,
            supports_system_prompt=True,
            supports_json_mode=True,
            max_context_window=128000,
            max_output_tokens=16384,
        )
