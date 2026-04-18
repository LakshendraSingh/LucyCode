"""
Application state management.

Central mutable state for the session: messages, model, cost, etc.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any

from lucy.core.config import get_config
from lucy.core.message import Message, MessageUsage


@dataclass
class CostTracker:
    """Track cumulative token usage and cost."""
    total_input_tokens: int = 0
    total_output_tokens: int = 0
    total_cache_creation_tokens: int = 0
    total_cache_read_tokens: int = 0
    total_cost_usd: float = 0.0
    turn_count: int = 0

    @property
    def total_cost(self) -> float:
        """Alias for total_cost_usd."""
        return self.total_cost_usd

    def add_usage(self, usage: MessageUsage, cost: float) -> None:
        self.total_input_tokens += usage.input_tokens
        self.total_output_tokens += usage.output_tokens
        self.total_cache_creation_tokens += usage.cache_creation_input_tokens
        self.total_cache_read_tokens += usage.cache_read_input_tokens
        self.total_cost_usd += cost
        self.turn_count += 1

    def format_cost(self) -> str:
        return f"${self.total_cost_usd:.4f}"

    def format_tokens(self) -> str:
        total = (
            self.total_input_tokens
            + self.total_output_tokens
            + self.total_cache_creation_tokens
            + self.total_cache_read_tokens
        )
        return f"{total:,} tokens"


@dataclass
class AppState:
    """Mutable application state for a session."""

    # Conversation
    messages: list[Message] = field(default_factory=list)
    conversation_id: str = ""

    # Model
    model: str = ""

    # Cost
    cost: CostTracker = field(default_factory=CostTracker)

    # Working directory
    cwd: str = field(default_factory=os.getcwd)

    # Permission mode
    permission_mode: str = "default"

    # Session metadata
    session_title: str = ""

    # Whether this is a --print (non-interactive) session
    is_non_interactive: bool = False

    def __post_init__(self) -> None:
        if not self.model:
            self.model = get_config().model
