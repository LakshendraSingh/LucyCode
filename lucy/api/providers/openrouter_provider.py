"""
OpenRouter LLM provider offering access to 200+ models via a unified API.
"""

from __future__ import annotations

import os

from lucy.api.providers.base import ProviderCapabilities
from lucy.api.providers.openai_compat_provider import OpenAICompatProvider


class OpenRouterProvider(OpenAICompatProvider):
    """Provider for OpenRouter unified API."""

    name: str = "openrouter"
    default_base_url: str = "https://openrouter.ai/api/v1"
    api_key_env_var: str = "OPENROUTER_API_KEY"

    def __init__(
        self,
        base_url: str | None = None,
        api_key: str | None = None,
    ) -> None:
        super().__init__(
            base_url=base_url,
            api_key=api_key,
            extra_headers={
                "HTTP-Referer": "https://github.com/lucycode/lucy",
                "X-Title": "LucyCode",
            },
        )

    def get_base_url(self) -> str:
        if self._custom_base_url:
            return self._custom_base_url
        return os.environ.get("OPENROUTER_BASE_URL", self.default_base_url)

    def get_capabilities(self, model: str) -> ProviderCapabilities:
        clean = self.clean_model_name(model).lower()
        supports_thinking = "r1" in clean or "reasoning" in clean or "o1" in clean or "o3" in clean
        supports_vision = any(v in clean for v in ["vision", "vl", "pixtral", "4o", "gemini"])

        return ProviderCapabilities(
            supports_streaming=True,
            supports_tool_use=True,
            supports_vision=supports_vision,
            supports_thinking=supports_thinking,
            supports_system_prompt=True,
            supports_json_mode=True,
            max_context_window=200000,
            max_output_tokens=32768,
        )
