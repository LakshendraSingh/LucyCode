"""
Compact service — smart conversation compaction with summarization.
"""

from __future__ import annotations

import logging
from typing import Any

from lucy.core.message import (
    AssistantMessage,
    CompactBoundaryMessage,
    Message,
    UserMessage,
)

logger = logging.getLogger(__name__)


async def compact_conversation(
    messages: list[Message],
    model: str | None = None,
    keep_last: int = 2,
    max_summary_tokens: int = 2000,
) -> tuple[list[Message], int]:
    """Compact a conversation by summarizing old messages.

    Returns (compacted_messages, tokens_saved_estimate).
    """
    if len(messages) <= keep_last + 1:
        return messages, 0

    # Split into sections
    first_msg = messages[0]
    middle = messages[1:-keep_last]
    recent = messages[-keep_last:]

    if not middle:
        return messages, 0

    # Build summary of middle section
    summary_parts = []
    tool_calls = []
    key_decisions = []

    for msg in middle:
        if isinstance(msg, UserMessage):
            text = msg.get_text()
            if text:
                summary_parts.append(f"User: {text[:300]}")
        elif isinstance(msg, AssistantMessage):
            text = msg.get_text()
            if text:
                summary_parts.append(f"Assistant: {text[:300]}")
            # Track tool calls
            for tu in msg.get_tool_use_blocks():
                tool_calls.append(f"{tu.name}({_summarize_input(tu.input)})")

    # Build structured summary
    summary_lines = ["=== Conversation Summary ==="]
    summary_lines.append(f"Messages summarized: {len(middle)}")

    if tool_calls:
        summary_lines.append(f"\nTools used: {', '.join(set(tool_calls[:20]))}")

    summary_lines.append("\nKey exchanges:")
    for part in summary_parts[:20]:  # Keep top 20
        summary_lines.append(f"  • {part[:200]}")

    summary = "\n".join(summary_lines)

    # Estimate savings
    old_chars = sum(len(m.get_text()) for m in middle)
    new_chars = len(summary)
    saved = max(0, (old_chars - new_chars) // 4)

    # Build compacted list
    boundary = CompactBoundaryMessage(summary=summary)
    compacted = [first_msg, boundary] + list(recent)

    return compacted, saved


def _summarize_input(inp: dict[str, Any]) -> str:
    """One-line summary of tool input."""
    if not inp:
        return ""
    # Try common keys
    for key in ("command", "file_path", "query", "pattern", "task", "url"):
        if key in inp:
            val = str(inp[key])
            return val[:80]
    return str(list(inp.keys()))[:60]


async def auto_compact_if_needed(
    messages: list[Message],
    max_messages: int = 100,
    max_chars: int = 500_000,
) -> tuple[list[Message], bool]:
    """Auto-compact if conversation exceeds thresholds."""
    total_chars = sum(len(m.get_text()) for m in messages)

    if len(messages) > max_messages or total_chars > max_chars:
        compacted, saved = await compact_conversation(messages)
        logger.info("Auto-compacted: %d -> %d messages, ~%d tokens saved",
                     len(messages), len(compacted), saved)
        return compacted, True

    return messages, False
