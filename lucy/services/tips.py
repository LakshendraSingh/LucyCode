"""
Tips service — contextual tips for improving workflow.
"""

from __future__ import annotations

import random
from typing import Any


TIPS = [
    "Use /compact to save tokens when conversations get long",
    "Use /plan to analyze code before making changes",
    "Try /review to get AI code review of staged changes",
    "Set /effort high for complex architectural decisions",
    "Use /fast to switch to the fastest model for simple tasks",
    "Use /export markdown to save conversations",
    "Try /memory add to remember things across sessions",
    "Use /branch to create feature branches before making changes",
    "Use /doctor to diagnose configuration issues",
    "Try /thinkback to review the AI's thinking process",
    "Use /security-review for security-focused code analysis",
    "Set up custom agents with /agents create for specialized tasks",
    "Use /context to see how much of the context window is used",
    "Try /diff to see what changed in the session",
    "Use /copy to copy the last response to your clipboard",
    "Set up MCP servers with /mcp for extended capabilities",
    "Use /commit-push-pr for a one-step PR workflow",
    "Use /ultraplan for deep architectural analysis",
    "Try /vim on if you prefer vim keybindings",
    "You can resume sessions with /resume <id>",
]


class TipsService:
    """Provide contextual tips."""

    def __init__(self):
        self._shown: set[int] = set()

    def get_tip(self, context: dict[str, Any] | None = None) -> str | None:
        """Get a contextual tip. Returns None if all tips shown."""
        available = [i for i in range(len(TIPS)) if i not in self._shown]
        if not available:
            self._shown.clear()
            available = list(range(len(TIPS)))

        idx = random.choice(available)
        self._shown.add(idx)
        return TIPS[idx]

    def get_onboarding_tips(self) -> list[str]:
        """Get tips for new users."""
        return [
            "Type your message and press Enter to start",
            "Use / commands for special actions (type /help)",
            "Press Ctrl+C to cancel, Ctrl+D to exit",
        ]


_service: TipsService | None = None


def get_tips_service() -> TipsService:
    global _service
    if _service is None:
        _service = TipsService()
    return _service
