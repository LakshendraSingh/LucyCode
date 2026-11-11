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
        clean_model = model[9:].strip() if model.startswith("llamacpp:") else model
        expanded = os.path.abspath(os.path.expanduser(clean_model))
        if os.path.isfile(expanded) or clean_model.endswith(".gguf"):
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

    async def stream(
        self,
        messages: list[dict[str, Any]],
        system_prompt: str,
        model: str,
        tools: list[dict[str, Any]] | None = None,
        max_tokens: int | None = None,
        thinking_enabled: bool | None = None,
        max_thinking_tokens: int | None = None,
        abort_signal: Any = None,
        **kwargs: Any,
    ):
        clean_model = model[9:].strip() if model.startswith("llamacpp:") else model
        expanded = os.path.abspath(os.path.expanduser(clean_model))
        if os.path.isfile(expanded) or clean_model.endswith(".gguf"):
            from lucy.api.providers.weights_provider import WeightsLLMProvider
            prov = WeightsLLMProvider()
            async for chunk in prov.stream(
                messages=messages,
                system_prompt=system_prompt,
                model=f"weights:{expanded}",
                tools=tools,
                max_tokens=max_tokens,
                thinking_enabled=thinking_enabled,
                max_thinking_tokens=max_thinking_tokens,
                abort_signal=abort_signal,
                **kwargs,
            ):
                yield chunk
            return

        async for chunk in super().stream(
            messages=messages,
            system_prompt=system_prompt,
            model=model,
            tools=tools,
            max_tokens=max_tokens,
            thinking_enabled=thinking_enabled,
            max_thinking_tokens=max_thinking_tokens,
            abort_signal=abort_signal,
            **kwargs,
        ):
            yield chunk
