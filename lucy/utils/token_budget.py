"""
Token budget management for context window.
"""

from __future__ import annotations

from typing import Any


# Known model context windows
MODEL_CONTEXT_WINDOWS = {
    "claude-sonnet-4-20250514": 200_000,
    "claude-3-5-sonnet-20241022": 200_000,
    "claude-3-opus-20240229": 200_000,
    "claude-3-5-haiku-20241022": 200_000,
    "claude-3-haiku-20240307": 200_000,
    # Local models
    "llama3.1": 128_000,
    "llama3.1:70b": 128_000,
    "mistral": 32_000,
    "codellama": 16_000,
    "deepseek-coder": 16_000,
    "qwen2.5-coder": 32_000,
}


def get_context_window(model: str) -> int:
    """Get the context window size for a model."""
    for key, window in MODEL_CONTEXT_WINDOWS.items():
        if key in model:
            return window
    return 128_000  # Default


def estimate_tokens(text: str) -> int:
    """Estimate token count from text (rough: ~4 chars per token)."""
    return len(text) // 4


def estimate_message_tokens(messages: list) -> int:
    """Estimate total tokens in a message list."""
    total = 0
    for msg in messages:
        text = msg.get_text() if hasattr(msg, "get_text") else str(msg)
        total += estimate_tokens(text) + 4  # Per-message overhead
    return total


class TokenBudget:
    """Manage token budget for context window."""

    def __init__(self, model: str, reserved_output: int = 16384):
        self.model = model
        self.context_window = get_context_window(model)
        self.reserved_output = reserved_output
        self.system_tokens = 0
        self.tool_schema_tokens = 0

    @property
    def available(self) -> int:
        """Tokens available for conversation."""
        return max(0, self.context_window - self.reserved_output -
                   self.system_tokens - self.tool_schema_tokens)

    def set_system_prompt(self, prompt: str) -> None:
        self.system_tokens = estimate_tokens(prompt)

    def set_tool_schemas(self, schemas: list[dict[str, Any]]) -> None:
        import json
        self.tool_schema_tokens = estimate_tokens(json.dumps(schemas))

    def check(self, messages: list) -> dict[str, Any]:
        """Check if messages fit in the context window."""
        used = estimate_message_tokens(messages)
        available = self.available

        return {
            "fits": used < available,
            "used": used,
            "available": available,
            "context_window": self.context_window,
            "utilization": used / max(available, 1),
            "remaining": max(0, available - used),
        }

    def needs_compaction(self, messages: list, threshold: float = 0.85) -> bool:
        """Check if messages need compaction."""
        check = self.check(messages)
        return check["utilization"] > threshold
