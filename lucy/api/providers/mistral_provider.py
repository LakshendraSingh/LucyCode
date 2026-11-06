"""
Mistral AI LLM provider.
"""

from __future__ import annotations

import os

from lucy.api.providers.base import ProviderCapabilities
from lucy.api.providers.openai_compat_provider import OpenAICompatProvider


class MistralProvider(OpenAICompatProvider):
    """Provider for Mistral AI models (Mistral Large, Codestral, Pixtral, etc.)."""

    name: str = "mistral"
    default_base_url: str = "https://api.mistral.ai/v1"
    api_key_env_var: str = "MISTRAL_API_KEY"

    def get_base_url(self) -> str:
        if self._custom_base_url:
            return self._custom_base_url
        return os.environ.get("MISTRAL_BASE_URL", self.default_base_url)

    def get_capabilities(self, model: str) -> ProviderCapabilities:
        clean = self.clean_model_name(model).lower()
        is_codestral = "codestral" in clean
        is_pixtral = "pixtral" in clean

        return ProviderCapabilities(
            supports_streaming=True,
            supports_tool_use=True,
            supports_vision=is_pixtral,
            supports_thinking=False,
            supports_system_prompt=True,
            supports_json_mode=True,
            max_context_window=256000 if is_codestral else 128000,
            max_output_tokens=32768,
        )
