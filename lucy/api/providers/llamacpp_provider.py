"""
llama.cpp server LLM provider.
"""

from __future__ import annotations

import os

from lucy.api.providers.base import ProviderCapabilities
from lucy.api.providers.openai_compat_provider import OpenAICompatProvider


class LlamaCppProvider(OpenAICompatProvider):
    """Provider for local llama.cpp server."""

    name: str = "llamacpp"
    default_base_url: str = "http://localhost:8080/v1"
    api_key_env_var: str = ""

    def get_base_url(self) -> str:
        if self._custom_base_url:
            return self._custom_base_url
        host = os.environ.get("LLAMACPP_HOST", "http://localhost:8080")
        if not host.endswith("/v1"):
            host = f"{host.rstrip('/')}/v1"
        return host

    def get_api_key(self) -> str:
        return "not-needed"

    def is_configured(self) -> bool:
        return True

    def get_capabilities(self, model: str) -> ProviderCapabilities:
        return ProviderCapabilities(
            supports_streaming=True,
            supports_tool_use=True,
            supports_vision=False,
            supports_thinking=False,
            supports_system_prompt=True,
            supports_json_mode=True,
            max_context_window=128000,
            max_output_tokens=8192,
        )
