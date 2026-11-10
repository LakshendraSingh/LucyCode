"""
Universal LLM Provider Package for LucyCode.

Provides pluggable architecture supporting 15+ LLM providers including
Anthropic, OpenAI, Gemini, Groq, Mistral, DeepSeek, Ollama, OpenRouter,
Together, Fireworks, llama.cpp, and local model weights.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from typing import Any, AsyncGenerator

from lucy.api.providers.anthropic_provider import AnthropicProvider
from lucy.api.providers.base import LLMProvider, ProviderCapabilities
from lucy.api.providers.deepseek_provider import DeepSeekProvider
from lucy.api.providers.fireworks_provider import FireworksProvider
from lucy.api.providers.gemini_provider import GeminiProvider
from lucy.api.providers.groq_provider import GroqProvider
from lucy.api.providers.llamacpp_provider import LlamaCppProvider
from lucy.api.providers.mistral_provider import MistralProvider
from lucy.api.providers.ollama_provider import OllamaProvider
from lucy.api.providers.openai_compat_provider import OpenAICompatProvider
from lucy.api.providers.openai_provider import OpenAIProvider
from lucy.api.providers.openrouter_provider import OpenRouterProvider
from lucy.api.providers.registry import (
    ProviderInfo,
    ProviderRegistry,
    detect_from_env,
    get_provider,
    get_registry,
    list_providers,
    register_provider,
)
from lucy.api.providers.together_provider import TogetherProvider
from lucy.api.providers.weights_provider import WeightsLLMProvider

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Backward Compatibility Shim Constants and Types
# ---------------------------------------------------------------------------

class ProviderType:
    """Provider type constants for backward compatibility."""

    ANTHROPIC = "anthropic"
    OLLAMA = "ollama"
    OPENAI = "openai"
    LLAMACPP = "llamacpp"
    LOCAL = "local"
    WEIGHTS = "weights"
    GEMINI = "gemini"
    GROQ = "groq"
    MISTRAL = "mistral"
    DEEPSEEK = "deepseek"
    OPENROUTER = "openrouter"
    TOGETHER = "together"
    FIREWORKS = "fireworks"


@dataclass
class ProviderConfig:
    """Configuration for a model provider (backward compatibility)."""

    provider: str = ProviderType.ANTHROPIC
    base_url: str = ""
    api_key: str = ""
    model_name: str = ""


def detect_provider(model: str) -> tuple[str, str]:
    """Detect the provider and actual model name from a model string.

    Backward-compatible function returning (provider_type, model_name).
    """
    clean_model = model
    if ":" in model and not model.startswith("http"):
        prefix, name = model.split(":", 1)
        prefix_clean = prefix.lower()
        mapping = {
            "ollama": ProviderType.OLLAMA,
            "openai": ProviderType.OPENAI,
            "llama": ProviderType.LLAMACPP,
            "llamacpp": ProviderType.LLAMACPP,
            "local": ProviderType.LOCAL,
            "lmstudio": ProviderType.OPENAI,
            "vllm": ProviderType.OPENAI,
            "gemini": ProviderType.GEMINI,
            "google": ProviderType.GEMINI,
            "groq": ProviderType.GROQ,
            "mistral": ProviderType.MISTRAL,
            "deepseek": ProviderType.DEEPSEEK,
            "openrouter": ProviderType.OPENROUTER,
            "together": ProviderType.TOGETHER,
            "fireworks": ProviderType.FIREWORKS,
            "weights": ProviderType.WEIGHTS,
            "anthropic": ProviderType.ANTHROPIC,
            "claude": ProviderType.ANTHROPIC,
        }
        return mapping.get(prefix_clean, prefix_clean), name

    expanded = os.path.expanduser(model)
    if (
        model.startswith("weights:")
        or model.endswith(".gguf")
        or model.endswith(".safetensors")
        or model.startswith(("/", "./"))
        or (os.path.exists(expanded) and not os.path.isdir(expanded))
    ):
        return ProviderType.WEIGHTS, model
    if os.path.isdir(expanded):
        hf_markers = ["config.json", "model.safetensors", "pytorch_model.bin", "tokenizer_config.json"]
        if any(os.path.exists(os.path.join(expanded, m)) for m in hf_markers):
            return ProviderType.WEIGHTS, model
    if model.startswith("claude-"):
        return ProviderType.ANTHROPIC, model
    if model.startswith(("gpt-", "o1-", "o3-", "o4-")):
        return ProviderType.OPENAI, model
    if model.startswith("gemini-"):
        return ProviderType.GEMINI, model

    registry = get_registry()
    provider_name = registry.detect_provider_name(model)
    return provider_name, clean_model


def get_provider_config(model: str) -> ProviderConfig:
    """Build provider config from a model string (backward compatibility)."""
    provider_type, model_name = detect_provider(model)
    config = ProviderConfig(provider=provider_type, model_name=model_name)

    if provider_type == ProviderType.OLLAMA:
        config.base_url = os.environ.get("OLLAMA_HOST", "http://localhost:11434")
    elif provider_type == ProviderType.OPENAI:
        config.base_url = os.environ.get(
            "OPENAI_BASE_URL",
            os.environ.get("OPENAI_API_BASE", "https://api.openai.com/v1"),
        )
        config.api_key = os.environ.get("OPENAI_API_KEY", "")
    elif provider_type == ProviderType.LLAMACPP:
        config.base_url = os.environ.get("LLAMACPP_HOST", "http://localhost:8080")
    elif provider_type == ProviderType.GEMINI:
        config.base_url = "https://generativelanguage.googleapis.com"
        config.api_key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY", "")
    elif provider_type == ProviderType.WEIGHTS:
        config.model_name = os.path.abspath(model_name)

    return config


# ---------------------------------------------------------------------------
# Backward-Compatible Streaming Functions
# ---------------------------------------------------------------------------

async def stream_ollama(
    messages: list[dict[str, Any]],
    system_prompt: str,
    model_name: str,
    base_url: str = "http://localhost:11434",
    tools: list[dict[str, Any]] | None = None,
    **kwargs: Any,
) -> AsyncGenerator[dict[str, Any], None]:
    """Stream from Ollama API (backward compatibility)."""
    provider = OllamaProvider(base_url=base_url)
    async for chunk in provider.stream(
        messages=messages,
        system_prompt=system_prompt,
        model=model_name,
        tools=tools,
        **kwargs,
    ):
        yield chunk


async def stream_openai_compat(
    messages: list[dict[str, Any]],
    system_prompt: str,
    model_name: str,
    base_url: str = "http://localhost:1234/v1",
    api_key: str = "not-needed",
    tools: list[dict[str, Any]] | None = None,
    **kwargs: Any,
) -> AsyncGenerator[dict[str, Any], None]:
    """Stream from OpenAI-compatible API (backward compatibility)."""
    provider = OpenAICompatProvider(base_url=base_url, api_key=api_key)
    async for chunk in provider.stream(
        messages=messages,
        system_prompt=system_prompt,
        model=model_name,
        tools=tools,
        **kwargs,
    ):
        yield chunk


async def stream_llamacpp(
    messages: list[dict[str, Any]],
    system_prompt: str,
    model_name: str,
    base_url: str = "http://localhost:8080",
    **kwargs: Any,
) -> AsyncGenerator[dict[str, Any], None]:
    """Stream from llama.cpp server (backward compatibility)."""
    provider = LlamaCppProvider(base_url=base_url)
    async for chunk in provider.stream(
        messages=messages,
        system_prompt=system_prompt,
        model=model_name,
        **kwargs,
    ):
        yield chunk


async def stream_local(
    messages: list[dict[str, Any]],
    system_prompt: str,
    model: str,
    tools: list[dict[str, Any]] | None = None,
    **kwargs: Any,
) -> AsyncGenerator[dict[str, Any], None]:
    """Unified streaming interface for any local or cloud provider."""
    provider = get_provider(model)
    async for chunk in provider.stream(
        messages=messages,
        system_prompt=system_prompt,
        model=model,
        tools=tools,
        **kwargs,
    ):
        yield chunk


async def check_local_server(model: str = "ollama:llama3") -> dict[str, Any]:
    """Check if a local model server is running and available."""
    pc = get_provider_config(model)
    result: dict[str, Any] = {"provider": pc.provider, "model": pc.model_name, "available": False}

    try:
        import aiohttp

        if pc.provider == ProviderType.OLLAMA:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{pc.base_url}/api/tags",
                    timeout=aiohttp.ClientTimeout(total=3),
                ) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        models = [m.get("name", "") for m in data.get("models", [])]
                        result["available"] = True
                        result["models"] = models
                        result["model_loaded"] = pc.model_name in models or any(
                            pc.model_name in m for m in models
                        )

        elif pc.provider in (ProviderType.OPENAI, ProviderType.LLAMACPP):
            url = f"{pc.base_url}/models" if pc.provider == ProviderType.OPENAI else f"{pc.base_url}/v1/models"
            async with aiohttp.ClientSession() as session:
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=3)) as resp:
                    result["available"] = resp.status == 200
    except ImportError:
        result["error"] = "aiohttp not installed"
    except Exception as e:
        result["error"] = str(e)

    return result


__all__ = [
    # Base
    "LLMProvider",
    "ProviderCapabilities",
    # Registry
    "ProviderRegistry",
    "ProviderInfo",
    "get_registry",
    "get_provider",
    "list_providers",
    "detect_from_env",
    "register_provider",
    # Concrete Providers
    "AnthropicProvider",
    "OpenAIProvider",
    "GeminiProvider",
    "GroqProvider",
    "MistralProvider",
    "DeepSeekProvider",
    "OllamaProvider",
    "OpenAICompatProvider",
    "OpenRouterProvider",
    "TogetherProvider",
    "FireworksProvider",
    "LlamaCppProvider",
    "WeightsLLMProvider",
    # Backward Compatibility
    "ProviderType",
    "ProviderConfig",
    "detect_provider",
    "get_provider_config",
    "stream_ollama",
    "stream_openai_compat",
    "stream_llamacpp",
    "stream_local",
    "check_local_server",
]
