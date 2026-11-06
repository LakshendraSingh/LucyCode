"""
DeepSeek LLM provider with DeepSeek-R1 reasoning support.
"""

from __future__ import annotations

import os

from lucy.api.providers.base import ProviderCapabilities
from lucy.api.providers.openai_compat_provider import OpenAICompatProvider


class DeepSeekProvider(OpenAICompatProvider):
    """Provider for DeepSeek API (deepseek-chat, deepseek-reasoner)."""

    name: str = "deepseek"
    default_base_url: str = "https://api.deepseek.com"
    api_key_env_var: str = "DEEPSEEK_API_KEY"

    def get_base_url(self) -> str:
        if self._custom_base_url:
            return self._custom_base_url
        return os.environ.get("DEEPSEEK_BASE_URL", self.default_base_url)

    def get_capabilities(self, model: str) -> ProviderCapabilities:
        clean = self.clean_model_name(model).lower()
        is_reasoner = "reasoner" in clean or "r1" in clean

        return ProviderCapabilities(
            supports_streaming=True,
            supports_tool_use=not is_reasoner,  # deepseek-reasoner does not currently support function calling
            supports_vision=False,
            supports_thinking=is_reasoner,
            supports_system_prompt=True,
            supports_json_mode=True,
            max_context_window=64000,
            max_output_tokens=8192,
        )
