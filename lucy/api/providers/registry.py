"""
Universal LLM Provider Registry for LucyCode.

Handles provider registration, hot-swapping, model-to-provider routing,
and environment-based provider detection.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from typing import Any

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
from lucy.api.providers.together_provider import TogetherProvider
from lucy.api.providers.weights_provider import WeightsLLMProvider

logger = logging.getLogger(__name__)


@dataclass
class ProviderInfo:
    """Information and capability summary for a registered provider."""

    name: str
    display_name: str
    description: str
    default_model: str
    env_vars: list[str]
    is_configured: bool
    capabilities: ProviderCapabilities


class ProviderRegistry:
    """Registry managing available LLM providers and dynamic routing."""

    def __init__(self) -> None:
        self._providers: dict[str, LLMProvider] = {}
        self._metadata: dict[str, dict[str, Any]] = {}
        self._prefix_map: dict[str, str] = {}
        self._default_provider_name: str = "anthropic"

    def register_provider(
        self,
        name: str,
        provider: LLMProvider,
        display_name: str | None = None,
        description: str | None = None,
        default_model: str | None = None,
        env_vars: list[str] | None = None,
        prefixes: list[str] | None = None,
        is_default: bool = False,
    ) -> None:
        """Register or replace a provider implementation (hot-swap support)."""
        clean_name = name.lower()
        self._providers[clean_name] = provider
        self._metadata[clean_name] = {
            "display_name": display_name or clean_name.capitalize(),
            "description": description or f"{display_name or clean_name} LLM Provider",
            "default_model": default_model or "",
            "env_vars": env_vars or [],
        }

        # Map name itself as prefix
        self._prefix_map[clean_name] = clean_name
        if prefixes:
            for p in prefixes:
                self._prefix_map[p.lower()] = clean_name

        if is_default:
            self._default_provider_name = clean_name

        logger.debug("Registered LLM provider: %s (%s)", clean_name, display_name)

    def unregister_provider(self, name: str) -> None:
        """Remove a provider from the registry."""
        clean_name = name.lower()
        self._providers.pop(clean_name, None)
        self._metadata.pop(clean_name, None)
        # Clean prefix map
        to_del = [k for k, v in self._prefix_map.items() if v == clean_name]
        for k in to_del:
            self._prefix_map.pop(k, None)

    def detect_from_env(self) -> list[str]:
        """Detect which providers have valid API keys or active configuration in the environment."""
        active: list[str] = []
        for name, meta in self._metadata.items():
            env_vars = meta.get("env_vars", [])
            provider = self._providers.get(name)

            # Check if any associated environment variable is populated
            has_env_key = any(bool(os.environ.get(var)) for var in env_vars)
            if has_env_key or (provider and provider.is_configured()):
                active.append(name)
        return active

    def detect_provider_name(self, model: str) -> str:
        """Detect the provider name from a model string or active environment credentials."""
        # 1. Direct local file check (GGUF, safetensors, weights)
        if (
            model.endswith(".gguf")
            or model.endswith(".safetensors")
            or model.startswith("/")
            or model.startswith("./")
            or (os.path.exists(model) and not os.path.isdir(model))
        ):
            return "weights"

        # 2. Explicit prefix (e.g. "openai:gpt-4o", "gemini:gemini-2.5-flash")
        if ":" in model and not model.startswith("http"):
            prefix, _ = model.split(":", 1)
            clean_prefix = prefix.lower()
            if clean_prefix in self._prefix_map:
                return self._prefix_map[clean_prefix]

        clean_lower = model.lower()

        # 3. Model name heuristic prefixes
        if clean_lower.startswith("claude-"):
            return "anthropic"
        if clean_lower.startswith(("gpt-", "o1", "o3", "o4", "chatgpt-")):
            return "openai"
        if clean_lower.startswith("gemini-"):
            return "gemini"
        if clean_lower.startswith(("mistral-", "codestral-", "pixtral-", "open-mistral-")):
            return "mistral"
        if clean_lower.startswith("deepseek-"):
            return "deepseek"
        if clean_lower.startswith("groq/"):
            return "groq"
        if clean_lower.startswith(("meta-llama/", "togethercomputer/")):
            return "together"
        if clean_lower.startswith("accounts/fireworks/"):
            return "fireworks"

        # 4. Check available API keys in environment
        available = self.detect_from_env()
        if "anthropic" in available and any(x in clean_lower for x in ["claude", "haiku", "sonnet", "opus"]):
            return "anthropic"
        if "openai" in available and "gpt" in clean_lower:
            return "openai"
        if "gemini" in available and "gemini" in clean_lower:
            return "gemini"

        # 5. If only one provider is configured with an API key, use it
        cloud_providers = [p for p in available if p not in ("ollama", "llamacpp", "weights", "openai_compat")]
        if len(cloud_providers) == 1:
            return cloud_providers[0]

        # 6. Fallback to default provider
        return self._default_provider_name

    def get_provider(self, model: str) -> LLMProvider:
        """Resolve model string to a provider instance."""
        provider_name = self.detect_provider_name(model)
        provider = self._providers.get(provider_name)

        if not provider:
            # Fallback to default provider or first available
            provider = self._providers.get(self._default_provider_name)
            if not provider and self._providers:
                provider = next(iter(self._providers.values()))

        if not provider:
            raise RuntimeError(
                f"No LLM provider available for model '{model}'. "
                f"Registered providers: {list(self._providers.keys())}"
            )

        return provider

    def list_providers(self) -> list[ProviderInfo]:
        """List all registered providers and their capability matrix."""
        infos: list[ProviderInfo] = []
        for name, provider in self._providers.items():
            meta = self._metadata.get(name, {})
            caps = provider.get_capabilities(meta.get("default_model", ""))
            infos.append(
                ProviderInfo(
                    name=name,
                    display_name=meta.get("display_name", name),
                    description=meta.get("description", ""),
                    default_model=meta.get("default_model", ""),
                    env_vars=meta.get("env_vars", []),
                    is_configured=provider.is_configured(),
                    capabilities=caps,
                )
            )
        return infos


# ---------------------------------------------------------------------------
# Global Registry Singleton and Initialization
# ---------------------------------------------------------------------------

_REGISTRY: ProviderRegistry | None = None


def get_registry() -> ProviderRegistry:
    """Get or initialize the global provider registry singleton."""
    global _REGISTRY
    if _REGISTRY is not None:
        return _REGISTRY

    registry = ProviderRegistry()

    # 1. Anthropic
    registry.register_provider(
        name="anthropic",
        provider=AnthropicProvider(),
        display_name="Anthropic Claude",
        description="Anthropic Claude 3.5 and Claude 4 models",
        default_model="claude-sonnet-4-20250514",
        env_vars=["ANTHROPIC_API_KEY"],
        prefixes=["anthropic", "claude"],
        is_default=True,
    )

    # 2. OpenAI
    registry.register_provider(
        name="openai",
        provider=OpenAIProvider(),
        display_name="OpenAI",
        description="OpenAI GPT-4o, GPT-4.1, o1, o3, o4 models",
        default_model="gpt-4o",
        env_vars=["OPENAI_API_KEY"],
        prefixes=["openai", "gpt", "o1", "o3", "o4"],
    )

    # 3. Google Gemini
    registry.register_provider(
        name="gemini",
        provider=GeminiProvider(),
        display_name="Google Gemini",
        description="Google Gemini 2.5 Pro, Flash, and 2.0 models",
        default_model="gemini-2.5-flash",
        env_vars=["GEMINI_API_KEY", "GOOGLE_API_KEY"],
        prefixes=["gemini", "google"],
    )

    # 4. Groq
    registry.register_provider(
        name="groq",
        provider=GroqProvider(),
        display_name="Groq Cloud",
        description="Ultra-fast Llama, Mixtral, and Gemma inference on LPUs",
        default_model="llama-3.3-70b-versatile",
        env_vars=["GROQ_API_KEY"],
        prefixes=["groq"],
    )

    # 5. Mistral AI
    registry.register_provider(
        name="mistral",
        provider=MistralProvider(),
        display_name="Mistral AI",
        description="Mistral Large, Codestral, and Pixtral models",
        default_model="mistral-large-latest",
        env_vars=["MISTRAL_API_KEY"],
        prefixes=["mistral", "codestral"],
    )

    # 6. DeepSeek
    registry.register_provider(
        name="deepseek",
        provider=DeepSeekProvider(),
        display_name="DeepSeek",
        description="DeepSeek-Chat (V3) and DeepSeek-Reasoner (R1)",
        default_model="deepseek-chat",
        env_vars=["DEEPSEEK_API_KEY"],
        prefixes=["deepseek"],
    )

    # 7. OpenRouter
    registry.register_provider(
        name="openrouter",
        provider=OpenRouterProvider(),
        display_name="OpenRouter",
        description="Unified gateway to 200+ commercial and open models",
        default_model="anthropic/claude-3.5-sonnet",
        env_vars=["OPENROUTER_API_KEY"],
        prefixes=["openrouter"],
    )

    # 8. Together AI
    registry.register_provider(
        name="together",
        provider=TogetherProvider(),
        display_name="Together AI",
        description="Serverless inference for open source models",
        default_model="meta-llama/Llama-3.3-70B-Instruct-Turbo",
        env_vars=["TOGETHER_API_KEY"],
        prefixes=["together"],
    )

    # 9. Fireworks AI
    registry.register_provider(
        name="fireworks",
        provider=FireworksProvider(),
        display_name="Fireworks AI",
        description="Fast serverless inference for fine-tuned and open models",
        default_model="accounts/fireworks/models/llama-v3p3-70b-instruct",
        env_vars=["FIREWORKS_API_KEY"],
        prefixes=["fireworks"],
    )

    # 10. Ollama
    registry.register_provider(
        name="ollama",
        provider=OllamaProvider(),
        display_name="Ollama (Local)",
        description="Locally running Ollama server",
        default_model="llama3.1",
        env_vars=["OLLAMA_HOST"],
        prefixes=["ollama"],
    )

    # 11. Generic OpenAI Compatible (LM Studio, vLLM, text-gen-webui)
    registry.register_provider(
        name="openai_compat",
        provider=OpenAICompatProvider(),
        display_name="OpenAI Compatible",
        description="Local or remote OpenAI-compatible server (LM Studio, vLLM)",
        default_model="default",
        env_vars=["OPENAI_BASE_URL"],
        prefixes=["openai-compat", "compat", "lmstudio", "vllm", "local"],
    )

    # 12. llama.cpp Server
    registry.register_provider(
        name="llamacpp",
        provider=LlamaCppProvider(),
        display_name="llama.cpp (Local)",
        description="Locally running llama.cpp server",
        default_model="default",
        env_vars=["LLAMACPP_HOST"],
        prefixes=["llama", "llamacpp"],
    )

    # 13. Weights (Direct GGUF / Hugging Face loading)
    registry.register_provider(
        name="weights",
        provider=WeightsLLMProvider(),
        display_name="Direct Model Weights",
        description="Direct in-process GGUF or Safetensors weight execution",
        default_model="",
        env_vars=[],
        prefixes=["weights"],
    )

    _REGISTRY = registry
    return registry


def get_provider(model: str) -> LLMProvider:
    """Convenience function to get the provider for a model from the global registry."""
    return get_registry().get_provider(model)


def list_providers() -> list[ProviderInfo]:
    """Convenience function to list all registered providers."""
    return get_registry().list_providers()


def detect_from_env() -> list[str]:
    """Convenience function to detect available providers from environment API keys."""
    return get_registry().detect_from_env()


def register_provider(
    name: str,
    provider: LLMProvider,
    **kwargs: Any,
) -> None:
    """Convenience function to register a provider in the global registry."""
    get_registry().register_provider(name, provider, **kwargs)
