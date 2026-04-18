"""
Model definitions — names, context windows, pricing, capabilities.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ModelInfo:
    """Static information about a model."""
    id: str
    name: str
    context_window: int
    max_output_tokens: int
    input_price_per_mtok: float   # USD per million input tokens
    output_price_per_mtok: float  # USD per million output tokens
    supports_thinking: bool = True
    supports_tool_use: bool = True
    supports_vision: bool = True
    supports_pdf: bool = True


# ---------------------------------------------------------------------------
# Model catalog
# ---------------------------------------------------------------------------

MODELS: dict[str, ModelInfo] = {
    # Opus 4
    "claude-opus-4-20250514": ModelInfo(
        id="claude-opus-4-20250514",
        name="Claude Opus 4",
        context_window=200_000,
        max_output_tokens=32_000,
        input_price_per_mtok=15.0,
        output_price_per_mtok=75.0,
    ),
    # Sonnet 4
    "claude-sonnet-4-20250514": ModelInfo(
        id="claude-sonnet-4-20250514",
        name="Claude Sonnet 4",
        context_window=200_000,
        max_output_tokens=16_000,
        input_price_per_mtok=3.0,
        output_price_per_mtok=15.0,
    ),
    # Haiku 3.5
    "claude-3-5-haiku-20241022": ModelInfo(
        id="claude-3-5-haiku-20241022",
        name="Claude 3.5 Haiku",
        context_window=200_000,
        max_output_tokens=8_192,
        input_price_per_mtok=0.80,
        output_price_per_mtok=4.0,
        supports_thinking=False,
    ),
    # Sonnet 3.5 v2
    "claude-3-5-sonnet-20241022": ModelInfo(
        id="claude-3-5-sonnet-20241022",
        name="Claude 3.5 Sonnet v2",
        context_window=200_000,
        max_output_tokens=8_192,
        input_price_per_mtok=3.0,
        output_price_per_mtok=15.0,
        supports_thinking=False,
    ),
}

# ---------------------------------------------------------------------------
# Offline / Local model catalog
# ---------------------------------------------------------------------------

OFFLINE_MODELS: dict[str, ModelInfo] = {
    # Ollama models
    "ollama:llama3.1": ModelInfo(
        id="ollama:llama3.1", name="Llama 3.1 (Ollama)",
        context_window=128_000, max_output_tokens=8_192,
        input_price_per_mtok=0.0, output_price_per_mtok=0.0,
        supports_thinking=False, supports_vision=False, supports_pdf=False,
    ),
    "ollama:llama3.1:70b": ModelInfo(
        id="ollama:llama3.1:70b", name="Llama 3.1 70B (Ollama)",
        context_window=128_000, max_output_tokens=8_192,
        input_price_per_mtok=0.0, output_price_per_mtok=0.0,
        supports_thinking=False, supports_vision=False, supports_pdf=False,
    ),
    "ollama:deepseek-coder-v2": ModelInfo(
        id="ollama:deepseek-coder-v2", name="DeepSeek Coder V2 (Ollama)",
        context_window=128_000, max_output_tokens=8_192,
        input_price_per_mtok=0.0, output_price_per_mtok=0.0,
        supports_thinking=False, supports_vision=False, supports_pdf=False,
    ),
    "ollama:codellama": ModelInfo(
        id="ollama:codellama", name="CodeLlama (Ollama)",
        context_window=16_000, max_output_tokens=4_096,
        input_price_per_mtok=0.0, output_price_per_mtok=0.0,
        supports_thinking=False, supports_vision=False, supports_pdf=False,
    ),
    "ollama:qwen2.5-coder": ModelInfo(
        id="ollama:qwen2.5-coder", name="Qwen2.5 Coder (Ollama)",
        context_window=32_000, max_output_tokens=8_192,
        input_price_per_mtok=0.0, output_price_per_mtok=0.0,
        supports_thinking=False, supports_vision=False, supports_pdf=False,
    ),
    "ollama:mistral": ModelInfo(
        id="ollama:mistral", name="Mistral (Ollama)",
        context_window=32_000, max_output_tokens=8_192,
        input_price_per_mtok=0.0, output_price_per_mtok=0.0,
        supports_thinking=False, supports_vision=False, supports_pdf=False,
    ),
    "ollama:gemma2": ModelInfo(
        id="ollama:gemma2", name="Gemma 2 (Ollama)",
        context_window=8_000, max_output_tokens=4_096,
        input_price_per_mtok=0.0, output_price_per_mtok=0.0,
        supports_thinking=False, supports_vision=False, supports_pdf=False,
    ),
    # OpenAI-compatible (LM Studio, vLLM)
    "openai:gpt-4": ModelInfo(
        id="openai:gpt-4", name="GPT-4 (OpenAI-compat)",
        context_window=128_000, max_output_tokens=16_384,
        input_price_per_mtok=0.0, output_price_per_mtok=0.0,
        supports_thinking=False, supports_pdf=False,
    ),
    "openai:local-model": ModelInfo(
        id="openai:local-model", name="Local Model (OpenAI-compat)",
        context_window=32_000, max_output_tokens=4_096,
        input_price_per_mtok=0.0, output_price_per_mtok=0.0,
        supports_thinking=False, supports_vision=False, supports_pdf=False,
    ),
}

# Merge into main catalog
MODELS.update(OFFLINE_MODELS)

# Aliases → canonical model IDs
MODEL_ALIASES: dict[str, str] = {
    "opus": "claude-opus-4-20250514",
    "opus-4": "claude-opus-4-20250514",
    "sonnet": "claude-sonnet-4-20250514",
    "sonnet-4": "claude-sonnet-4-20250514",
    "haiku": "claude-3-5-haiku-20241022",
    "haiku-3.5": "claude-3-5-haiku-20241022",
    "sonnet-3.5": "claude-3-5-sonnet-20241022",
    # Offline aliases
    "llama3": "ollama:llama3.1",
    "llama": "ollama:llama3.1",
    "deepseek": "ollama:deepseek-coder-v2",
    "codellama": "ollama:codellama",
    "qwen": "ollama:qwen2.5-coder",
    "mistral": "ollama:mistral",
    "gemma": "ollama:gemma2",
}

DEFAULT_MODEL = "claude-sonnet-4-20250514"
SMALL_FAST_MODEL = "claude-3-5-haiku-20241022"
DEFAULT_OFFLINE_MODEL = "ollama:llama3.1"


def resolve_model(model_str: str) -> str:
    """Resolve a model string (alias or ID) to a canonical model ID."""
    if model_str in MODELS:
        return model_str
    if model_str in MODEL_ALIASES:
        return MODEL_ALIASES[model_str]
    # Unknown model — pass through (supports custom/3P models)
    return model_str


def get_model_info(model: str) -> ModelInfo | None:
    """Get model info for a given model ID."""
    resolved = resolve_model(model)
    return MODELS.get(resolved)


def get_context_window(model: str) -> int:
    """Get the context window size for a model."""
    info = get_model_info(model)
    return info.context_window if info else 200_000


def get_max_output_tokens(model: str) -> int:
    """Get the max output tokens for a model."""
    info = get_model_info(model)
    return info.max_output_tokens if info else 16_000


def supports_thinking(model: str) -> bool:
    """Check if a model supports extended thinking."""
    info = get_model_info(model)
    return info.supports_thinking if info else False


def is_offline_model(model: str) -> bool:
    """Check if a model is an offline/local model."""
    resolved = resolve_model(model)
    # Match prefixes or local file paths (ends with .gguf, .safetensors, or starts with /)
    return (
        any(resolved.startswith(p) for p in ["ollama:", "openai:", "llama:", "local:", "weights:"]) or
        resolved.endswith(".gguf") or
        resolved.endswith(".safetensors") or
        resolved.startswith("/") or
        resolved.startswith("./")
    )


def is_free_model(model: str) -> bool:
    """Check if a model is free (no API cost)."""
    info = get_model_info(model)
    if not info:
        return is_offline_model(model)
    return info.input_price_per_mtok == 0.0 and info.output_price_per_mtok == 0.0


def calculate_cost(
    model: str,
    input_tokens: int,
    output_tokens: int,
    cache_creation_tokens: int = 0,
    cache_read_tokens: int = 0,
) -> float:
    """Calculate the USD cost for a given usage."""
    info = get_model_info(model)
    if not info:
        return 0.0
    # Offline models are free
    if info.input_price_per_mtok == 0.0 and info.output_price_per_mtok == 0.0:
        return 0.0
    input_cost = (input_tokens / 1_000_000) * info.input_price_per_mtok
    output_cost = (output_tokens / 1_000_000) * info.output_price_per_mtok
    # Cache creation charged at 1.25x input; cache read at 0.1x input
    cache_create_cost = (cache_creation_tokens / 1_000_000) * info.input_price_per_mtok * 1.25
    cache_read_cost = (cache_read_tokens / 1_000_000) * info.input_price_per_mtok * 0.1
    return input_cost + output_cost + cache_create_cost + cache_read_cost
