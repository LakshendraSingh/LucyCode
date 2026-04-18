"""
Cost tracking utilities.
"""

from __future__ import annotations

from lucy.api.models import calculate_cost
from lucy.core.message import MessageUsage


def format_cost(cost_usd: float) -> str:
    """Format a cost value as a dollar string."""
    if cost_usd < 0.01:
        return f"${cost_usd:.4f}"
    return f"${cost_usd:.2f}"


def format_tokens(count: int) -> str:
    """Format a token count with commas."""
    return f"{count:,}"


def estimate_cost_from_usage(model: str, usage: MessageUsage) -> float:
    """Calculate cost from a usage object."""
    return calculate_cost(
        model=model,
        input_tokens=usage.input_tokens,
        output_tokens=usage.output_tokens,
        cache_creation_tokens=usage.cache_creation_input_tokens,
        cache_read_tokens=usage.cache_read_input_tokens,
    )

class SessionCostTracker:
    def __init__(self):
        self.total_cost: float = 0.0
        self.input_tokens: int = 0
        self.output_tokens: int = 0
        self.cache_write_tokens: int = 0
        self.cache_read_tokens: int = 0
        self.model_usage: dict[str, dict] = {}

    def add_usage(self, model: str, usage: MessageUsage) -> float:
        cost = estimate_cost_from_usage(model, usage)
        self.total_cost += cost
        self.input_tokens += usage.input_tokens
        self.output_tokens += usage.output_tokens
        self.cache_write_tokens += usage.cache_creation_input_tokens
        self.cache_read_tokens += usage.cache_read_input_tokens

        if model not in self.model_usage:
            self.model_usage[model] = {
                "input": 0, "output": 0, "cache_write": 0, "cache_read": 0, "cost": 0.0
            }
        
        m = self.model_usage[model]
        m["input"] += usage.input_tokens
        m["output"] += usage.output_tokens
        m["cache_write"] += usage.cache_creation_input_tokens
        m["cache_read"] += usage.cache_read_input_tokens
        m["cost"] += cost
        return cost
        
    def format_total(self) -> str:
        s = []
        s.append(f"Total Session Cost: {format_cost(self.total_cost)}")
        s.append(f"Tokens: {format_tokens(self.input_tokens)} input, {format_tokens(self.output_tokens)} output")
        if self.cache_write_tokens or self.cache_read_tokens:
            s.append(f"Cache: {format_tokens(self.cache_write_tokens)} written, {format_tokens(self.cache_read_tokens)} read")
        return "\n".join(s)

_global_tracker = SessionCostTracker()

def get_session_tracker() -> SessionCostTracker:
    return _global_tracker
