"""
Context compaction — summarize older messages to free context window.

Uses the model itself to produce a summary, then replaces old messages
with a compact boundary marker + the summary.
"""

from __future__ import annotations

import logging
from typing import Any

from lucy.core.message import (
    AssistantMessage,
    CompactBoundaryMessage,
    Message,
    TextBlock,
    UserMessage,
)
from lucy.utils.tokens import estimate_tokens

logger = logging.getLogger(__name__)

COMPACT_SYSTEM_PROMPT = (
    "You are a conversation summarizer. Summarize the following conversation "
    "concisely, preserving all key technical details, decisions, code changes, "
    "file paths, and context needed to continue the work. "
    "Be thorough but brief. Use bullet points."
)

MIN_MESSAGES_TO_COMPACT = 6
KEEP_RECENT_MESSAGES = 4


async def compact_messages(
    messages: list[Message],
    model: str | None = None,
) -> tuple[list[Message], str]:
    """Compact older messages by summarizing them.

    Returns (new_messages, summary_text).
    """
    if len(messages) < MIN_MESSAGES_TO_COMPACT:
        return messages, ""

    # Split: older messages to summarize, recent messages to keep
    to_summarize = messages[:-KEEP_RECENT_MESSAGES]
    to_keep = messages[-KEEP_RECENT_MESSAGES:]

    # Build the conversation text for summarization
    conversation_text = _format_messages_for_summary(to_summarize)

    if not conversation_text.strip():
        return messages, ""

    # Ask the model to summarize
    try:
        from lucy.api.client import query as api_query

        summary_msg = await api_query(
            messages=[{"role": "user", "content": f"Summarize this conversation:\n\n{conversation_text}"}],
            system_prompt=COMPACT_SYSTEM_PROMPT,
            model=model,
            max_tokens=4096,
        )
        summary_text = summary_msg.get_text()
    except Exception as e:
        logger.warning("Failed to generate summary: %s", e)
        # Fallback: simple truncation
        summary_text = f"[Previous {len(to_summarize)} messages summarized (API error)]"

    # Build new message list
    boundary = CompactBoundaryMessage(summary=summary_text)
    new_messages: list[Message] = [boundary, *to_keep]

    return new_messages, summary_text


def _format_messages_for_summary(messages: list[Message]) -> str:
    """Format messages into text for the summarizer."""
    parts: list[str] = []
    for msg in messages:
        if isinstance(msg, UserMessage):
            text = msg.get_text()
            if text:
                parts.append(f"User: {text}")
        elif isinstance(msg, AssistantMessage):
            text = msg.get_text()
            if text:
                parts.append(f"Assistant: {text}")
            for block in msg.content:
                if hasattr(block, "name"):  # ToolUseBlock
                    parts.append(f"[Tool: {block.name}]")  # type: ignore
    return "\n\n".join(parts)
