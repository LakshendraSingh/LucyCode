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
    # ── Anthropic Claude ──
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

    # ── OpenAI ──
    "openai:gpt-4o": ModelInfo(
        id="openai:gpt-4o",
        name="OpenAI GPT-4o",
        context_window=128_000,
        max_output_tokens=16_384,
        input_price_per_mtok=2.50,
        output_price_per_mtok=10.00,
        supports_thinking=False,
        supports_vision=True,
    ),
    "openai:gpt-4o-mini": ModelInfo(
        id="openai:gpt-4o-mini",
        name="OpenAI GPT-4o-mini",
        context_window=128_000,
        max_output_tokens=16_384,
        input_price_per_mtok=0.15,
        output_price_per_mtok=0.60,
        supports_thinking=False,
        supports_vision=True,
    ),
    "openai:gpt-4.1": ModelInfo(
        id="openai:gpt-4.1",
        name="OpenAI GPT-4.1",
        context_window=128_000,
        max_output_tokens=16_384,
        input_price_per_mtok=2.00,
        output_price_per_mtok=8.00,
        supports_thinking=False,
        supports_vision=True,
    ),
    "openai:o1": ModelInfo(
        id="openai:o1",
        name="OpenAI o1 Reasoning Model",
        context_window=200_000,
        max_output_tokens=100_000,
        input_price_per_mtok=15.00,
        output_price_per_mtok=60.00,
        supports_thinking=True,
        supports_vision=True,
    ),
    "openai:o3": ModelInfo(
        id="openai:o3",
        name="OpenAI o3 Reasoning Model",
        context_window=200_000,
        max_output_tokens=100_000,
        input_price_per_mtok=15.00,
        output_price_per_mtok=60.00,
        supports_thinking=True,
        supports_vision=True,
    ),
    "openai:o3-mini": ModelInfo(
        id="openai:o3-mini",
        name="OpenAI o3-mini Reasoning Model",
        context_window=200_000,
        max_output_tokens=100_000,
        input_price_per_mtok=1.10,
        output_price_per_mtok=4.40,
        supports_thinking=True,
        supports_vision=False,
    ),
    "openai:o4-mini": ModelInfo(
        id="openai:o4-mini",
        name="OpenAI o4-mini Reasoning Model",
        context_window=200_000,
        max_output_tokens=100_000,
        input_price_per_mtok=1.10,
        output_price_per_mtok=4.40,
        supports_thinking=True,
        supports_vision=True,
    ),

    # ── Google Gemini ──
    "gemini:gemini-3.1-flash-lite": ModelInfo(
        id="gemini:gemini-3.1-flash-lite",
        name="Google Gemini 3.1 Flash Lite",
        context_window=1_000_000,
        max_output_tokens=65_536,
        input_price_per_mtok=0.075,
        output_price_per_mtok=0.30,
        supports_thinking=True,
        supports_vision=True,
    ),
    "gemini:gemini-3.5-flash": ModelInfo(
        id="gemini:gemini-3.5-flash",
        name="Google Gemini 3.5 Flash",
        context_window=1_000_000,
        max_output_tokens=65_536,
        input_price_per_mtok=0.15,
        output_price_per_mtok=0.60,
        supports_thinking=True,
        supports_vision=True,
    ),
    "gemini:gemini-3.5-flash-lite": ModelInfo(
        id="gemini:gemini-3.5-flash-lite",
        name="Google Gemini 3.5 Flash Lite",
        context_window=1_000_000,
        max_output_tokens=65_536,
        input_price_per_mtok=0.075,
        output_price_per_mtok=0.30,
        supports_thinking=True,
        supports_vision=True,
    ),
    "gemini:gemini-flash-latest": ModelInfo(
        id="gemini:gemini-flash-latest",
        name="Google Gemini Flash (Latest)",
        context_window=1_000_000,
        max_output_tokens=65_536,
        input_price_per_mtok=0.15,
        output_price_per_mtok=0.60,
        supports_thinking=True,
        supports_vision=True,
    ),
    "gemini:gemini-pro-latest": ModelInfo(
        id="gemini:gemini-pro-latest",
        name="Google Gemini Pro (Latest)",
        context_window=2_000_000,
        max_output_tokens=65_536,
        input_price_per_mtok=1.25,
        output_price_per_mtok=5.00,
        supports_thinking=True,
        supports_vision=True,
    ),
    "gemini:gemini-3.8-pro": ModelInfo(
        id="gemini:gemini-3.8-pro",
        name="Google Gemini 3.8 Pro",
        context_window=2_000_000,
        max_output_tokens=65_536,
        input_price_per_mtok=1.25,
        output_price_per_mtok=5.00,
        supports_thinking=True,
        supports_vision=True,
    ),
    "gemini:gemini-3.8-flash": ModelInfo(
        id="gemini:gemini-3.8-flash",
        name="Google Gemini 3.8 Flash",
        context_window=1_000_000,
        max_output_tokens=65_536,
        input_price_per_mtok=0.15,
        output_price_per_mtok=0.60,
        supports_thinking=True,
        supports_vision=True,
    ),
    "gemini:gemini-2.5-pro": ModelInfo(
        id="gemini:gemini-2.5-pro",
        name="Google Gemini 2.5 Pro",
        context_window=2_000_000,
        max_output_tokens=65_536,
        input_price_per_mtok=1.25,
        output_price_per_mtok=5.00,
        supports_thinking=True,
        supports_vision=True,
    ),
    "gemini:gemini-2.5-flash": ModelInfo(
        id="gemini:gemini-2.5-flash",
        name="Google Gemini 2.5 Flash",
        context_window=1_000_000,
        max_output_tokens=65_536,
        input_price_per_mtok=0.15,
        output_price_per_mtok=0.60,
        supports_thinking=True,
        supports_vision=True,
    ),
    "gemini:gemini-2.0-flash": ModelInfo(
        id="gemini:gemini-2.0-flash",
        name="Google Gemini 2.0 Flash",
        context_window=1_000_000,
        max_output_tokens=8_192,
        input_price_per_mtok=0.10,
        output_price_per_mtok=0.40,
        supports_thinking=False,
        supports_vision=True,
    ),

    # ── Groq ──
    "groq:llama-3.3-70b-versatile": ModelInfo(
        id="groq:llama-3.3-70b-versatile",
        name="Llama 3.3 70B (Groq)",
        context_window=128_000,
        max_output_tokens=32_768,
        input_price_per_mtok=0.59,
        output_price_per_mtok=0.79,
        supports_thinking=False,
        supports_vision=False,
    ),
    "groq:llama-3.1-8b-instant": ModelInfo(
        id="groq:llama-3.1-8b-instant",
        name="Llama 3.1 8B Instant (Groq)",
        context_window=128_000,
        max_output_tokens=8_192,
        input_price_per_mtok=0.05,
        output_price_per_mtok=0.08,
        supports_thinking=False,
        supports_vision=False,
    ),
    "groq:mixtral-8x7b-32768": ModelInfo(
        id="groq:mixtral-8x7b-32768",
        name="Mixtral 8x7B (Groq)",
        context_window=32_768,
        max_output_tokens=32_768,
        input_price_per_mtok=0.24,
        output_price_per_mtok=0.24,
        supports_thinking=False,
        supports_vision=False,
    ),
    "groq:deepseek-r1-distill-llama-70b": ModelInfo(
        id="groq:deepseek-r1-distill-llama-70b",
        name="DeepSeek R1 Distill Llama 70B (Groq)",
        context_window=128_000,
        max_output_tokens=32_768,
        input_price_per_mtok=0.75,
        output_price_per_mtok=0.99,
        supports_thinking=True,
        supports_vision=False,
    ),

    # ── Mistral AI ──
    "mistral:mistral-large-latest": ModelInfo(
        id="mistral:mistral-large-latest",
        name="Mistral Large",
        context_window=128_000,
        max_output_tokens=32_768,
        input_price_per_mtok=2.00,
        output_price_per_mtok=6.00,
        supports_thinking=False,
        supports_vision=False,
    ),
    "mistral:codestral-latest": ModelInfo(
        id="mistral:codestral-latest",
        name="Codestral",
        context_window=256_000,
        max_output_tokens=32_768,
        input_price_per_mtok=0.30,
        output_price_per_mtok=0.90,
        supports_thinking=False,
        supports_vision=False,
    ),
    "mistral:mistral-small-latest": ModelInfo(
        id="mistral:mistral-small-latest",
        name="Mistral Small",
        context_window=128_000,
        max_output_tokens=32_768,
        input_price_per_mtok=0.20,
        output_price_per_mtok=0.60,
        supports_thinking=False,
        supports_vision=False,
    ),

    # ── DeepSeek ──
    "deepseek:deepseek-chat": ModelInfo(
        id="deepseek:deepseek-chat",
        name="DeepSeek-V3 Chat",
        context_window=64_000,
        max_output_tokens=8_192,
        input_price_per_mtok=0.14,
        output_price_per_mtok=0.28,
        supports_thinking=False,
        supports_vision=False,
    ),
    "deepseek:deepseek-reasoner": ModelInfo(
        id="deepseek:deepseek-reasoner",
        name="DeepSeek-R1 Reasoner",
        context_window=64_000,
        max_output_tokens=8_192,
        input_price_per_mtok=0.55,
        output_price_per_mtok=2.19,
        supports_thinking=True,
        supports_vision=False,
    ),

    # ── OpenRouter ──
    "openrouter:auto": ModelInfo(
        id="openrouter:auto",
        name="OpenRouter Auto",
        context_window=128_000,
        max_output_tokens=16_384,
        input_price_per_mtok=1.00,
        output_price_per_mtok=2.00,
        supports_thinking=False,
        supports_vision=True,
    ),

    # ── Together AI ──
    "together:meta-llama/Llama-3.3-70B-Instruct-Turbo": ModelInfo(
        id="together:meta-llama/Llama-3.3-70B-Instruct-Turbo",
        name="Llama 3.3 70B Instruct Turbo (Together)",
        context_window=128_000,
        max_output_tokens=8_192,
        input_price_per_mtok=0.88,
        output_price_per_mtok=0.88,
        supports_thinking=False,
        supports_vision=False,
    ),
    "together:Qwen/Qwen2.5-Coder-32B-Instruct": ModelInfo(
        id="together:Qwen/Qwen2.5-Coder-32B-Instruct",
        name="Qwen 2.5 Coder 32B Instruct (Together)",
        context_window=32_768,
        max_output_tokens=8_192,
        input_price_per_mtok=0.80,
        output_price_per_mtok=0.80,
        supports_thinking=False,
        supports_vision=False,
    ),

    # ── Fireworks AI ──
    "fireworks:accounts/fireworks/models/llama-v3p3-70b-instruct": ModelInfo(
        id="fireworks:accounts/fireworks/models/llama-v3p3-70b-instruct",
        name="Llama 3.3 70B Instruct (Fireworks)",
        context_window=128_000,
        max_output_tokens=8_192,
        input_price_per_mtok=0.90,
        output_price_per_mtok=0.90,
        supports_thinking=False,
        supports_vision=False,
    ),
    "fireworks:accounts/fireworks/models/deepseek-r1": ModelInfo(
        id="fireworks:accounts/fireworks/models/deepseek-r1",
        name="DeepSeek R1 (Fireworks)",
        context_window=128_000,
        max_output_tokens=16_384,
        input_price_per_mtok=0.90,
        output_price_per_mtok=0.90,
        supports_thinking=True,
        supports_vision=False,
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
    # OpenAI-compatible local models (LM Studio, vLLM)
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
    # Anthropic Claude
    "opus": "claude-opus-4-20250514",
    "opus-4": "claude-opus-4-20250514",
    "sonnet": "claude-sonnet-4-20250514",
    "sonnet-4": "claude-sonnet-4-20250514",
    "haiku": "claude-3-5-haiku-20241022",
    "haiku-3.5": "claude-3-5-haiku-20241022",
    "sonnet-3.5": "claude-3-5-sonnet-20241022",
    # OpenAI
    "gpt4": "openai:gpt-4o",
    "gpt4o": "openai:gpt-4o",
    "gpt-4o": "openai:gpt-4o",
    "gpt4o-mini": "openai:gpt-4o-mini",
    "gpt-4o-mini": "openai:gpt-4o-mini",
    "gpt-4.1": "openai:gpt-4.1",
    "gpt4.1": "openai:gpt-4.1",
    "o1": "openai:o1",
    "o3": "openai:o3",
    "o3-mini": "openai:o3-mini",
    "o4-mini": "openai:o4-mini",
    # Google Gemini
    "gemini": "gemini:gemini-3.1-flash-lite",
    "gemini-flash": "gemini:gemini-3.1-flash-lite",
    "gemini-pro": "gemini:gemini-pro-latest",
    "gemini-lite": "gemini:gemini-3.1-flash-lite",
    "gemini-3.1": "gemini:gemini-3.1-flash-lite",
    "gemini-3.5": "gemini:gemini-3.5-flash",
    "gemini-3.8": "gemini:gemini-3.8-flash",
    "gemini-3.8-flash": "gemini:gemini-3.8-flash",
    "gemini-3.8-pro": "gemini:gemini-3.8-pro",
    "gemini-3.5-flash": "gemini:gemini-3.5-flash",
    "gemini-3.5-flash-lite": "gemini:gemini-3.5-flash-lite",
    "gemini-3.1-flash-lite": "gemini:gemini-3.1-flash-lite",
    "gemini-2.5-flash": "gemini:gemini-2.5-flash",
    "gemini-2.5-pro": "gemini:gemini-2.5-pro",
    "gemini-2.0-flash": "gemini:gemini-2.0-flash",
    # Groq
    "groq": "groq:llama-3.3-70b-versatile",
    "groq-llama": "groq:llama-3.3-70b-versatile",
    # Mistral
    "mistral-large": "mistral:mistral-large-latest",
    "codestral": "mistral:codestral-latest",
    # DeepSeek
    "deepseek-r1": "deepseek:deepseek-reasoner",
    "deepseek-v3": "deepseek:deepseek-chat",
    # OpenRouter / Together / Fireworks
    "openrouter": "openrouter:auto",
    "together": "together:meta-llama/Llama-3.3-70B-Instruct-Turbo",
    "fireworks": "fireworks:accounts/fireworks/models/llama-v3p3-70b-instruct",
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
    if info:
        return info.supports_thinking
    clean = model.lower()
    return "r1" in clean or "reasoner" in clean or clean.startswith(("o1", "o3", "o4"))


def is_offline_model(model: str) -> bool:
    """Check if a model is an offline/local model."""
    resolved = resolve_model(model)
    # Match prefixes or local file paths (ends with .gguf, .safetensors, or starts with /)
    return (
        any(resolved.startswith(p) for p in ["ollama:", "llama:", "llamacpp:", "local:", "weights:"]) or
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
    # Offline or zero-cost models are free
    if info.input_price_per_mtok == 0.0 and info.output_price_per_mtok == 0.0:
        return 0.0
    input_cost = (input_tokens / 1_000_000) * info.input_price_per_mtok
    output_cost = (output_tokens / 1_000_000) * info.output_price_per_mtok
    # Cache creation charged at 1.25x input; cache read at 0.1x input
    cache_create_cost = (cache_creation_tokens / 1_000_000) * info.input_price_per_mtok * 1.25
    cache_read_cost = (cache_read_tokens / 1_000_000) * info.input_price_per_mtok * 0.1
    return input_cost + output_cost + cache_create_cost + cache_read_cost
