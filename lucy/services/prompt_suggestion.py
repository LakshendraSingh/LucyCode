"""
Prompt suggestion service — context-aware prompt suggestions.
"""

from __future__ import annotations

import os
from typing import Any


class PromptSuggestionService:
    """Generate context-aware prompt suggestions."""

    def get_suggestions(self, cwd: str, messages: list | None = None,
                        limit: int = 5) -> list[str]:
        """Get prompt suggestions based on context."""
        suggestions = []

        # Project-type detection
        if os.path.exists(os.path.join(cwd, "package.json")):
            suggestions.extend([
                "Set up the development environment",
                "Fix failing tests",
                "Add a new API endpoint",
                "Refactor the component structure",
            ])
        elif os.path.exists(os.path.join(cwd, "pyproject.toml")) or os.path.exists(os.path.join(cwd, "setup.py")):
            suggestions.extend([
                "Add type hints to the codebase",
                "Write unit tests for the core modules",
                "Set up CI/CD pipeline",
                "Review code for security issues",
            ])
        elif os.path.exists(os.path.join(cwd, "Cargo.toml")):
            suggestions.extend([
                "Fix compiler warnings",
                "Add error handling",
                "Optimize performance-critical paths",
            ])
        elif os.path.exists(os.path.join(cwd, "go.mod")):
            suggestions.extend([
                "Add benchmarks",
                "Improve error handling",
                "Add integration tests",
            ])

        # Git-based suggestions
        if os.path.exists(os.path.join(cwd, ".git")):
            suggestions.extend([
                "Review recent changes for bugs",
                "Create a pull request description",
            ])

        # Conversation-based suggestions
        if messages and len(messages) > 0:
            suggestions.extend([
                "Continue from where we left off",
                "Summarize what we've done so far",
            ])

        # General suggestions
        if not suggestions:
            suggestions = [
                "Explain how this codebase works",
                "Find and fix any bugs",
                "Improve code quality",
                "Add documentation",
                "Set up testing",
            ]

        return suggestions[:limit]


_service: PromptSuggestionService | None = None


def get_prompt_suggestions() -> PromptSuggestionService:
    global _service
    if _service is None:
        _service = PromptSuggestionService()
    return _service
