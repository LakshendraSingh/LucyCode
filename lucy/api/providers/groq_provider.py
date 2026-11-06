"""
Groq LLM provider for ultra-fast Llama, Mixtral, and Gemma inference.
"""

from __future__ import annotations

import os

from lucy.api.providers.base import ProviderCapabilities
from lucy.api.providers.openai_compat_provider import OpenAICompatProvider


class GroqProvider(OpenAICompatProvider):
    """Provider for Groq Cloud API."""

    name: str = "groq"
    default_base_url: str = "https://api.groq.com/openai/v1"
    api_key_env_var: str = "GROQ_API_KEY"

    def get_base_url(self) -> str:
        if self._custom_base_url:
            return self._custom_base_url
        return os.environ.get("GROQ_BASE_URL", self.default_base_url)

    def get_capabilities(self, model: str) -> ProviderCapabilities:
        clean = self.clean_model_name(model).lower()
        supports_thinking = "r1" in clean or "deepseek" in clean
        supports_vision = "vision" in clean or "vl" in clean

        return ProviderCapabilities(
            supports_streaming=True,
            supports_tool_use=True,
            supports_vision=supports_vision,
            supports_thinking=supports_thinking,
            supports_system_prompt=True,
            supports_json_mode=True,
            max_context_window=128000,
            max_output_tokens=32768,
        )
