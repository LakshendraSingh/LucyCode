"""
Token estimation utilities.
"""

from __future__ import annotations


def estimate_tokens(text: str) -> int:
    """Estimate the number of tokens in a string.

    Uses the chars/4 heuristic (reasonably accurate for English text).
    For precise counts, use tiktoken.
    """
    return max(1, len(text) // 4)


def estimate_message_tokens(messages: list[dict]) -> int:
    """Estimate total tokens across a list of API messages."""
    total = 0
    for msg in messages:
        content = msg.get("content", "")
        if isinstance(content, str):
            total += estimate_tokens(content)
        elif isinstance(content, list):
            for block in content:
                if isinstance(block, dict):
                    text = block.get("text", "") or block.get("content", "")
                    if isinstance(text, str):
                        total += estimate_tokens(text)
    # Add overhead per message (role tokens, etc.)
    total += len(messages) * 4
    return total
