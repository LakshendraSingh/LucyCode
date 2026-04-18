"""
Message types for the Lucy Code conversation system.

Mirrors the Anthropic API message schema with internal extensions
for tool use tracking, system messages, and UI state.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Literal, Union


# ---------------------------------------------------------------------------
# Content Blocks
# ---------------------------------------------------------------------------

@dataclass
class TextBlock:
    """A block of text content."""
    type: Literal["text"] = "text"
    text: str = ""


@dataclass
class ToolUseBlock:
    """A tool_use block emitted by the assistant."""
    type: Literal["tool_use"] = "tool_use"
    id: str = ""
    name: str = ""
    input: dict[str, Any] = field(default_factory=dict)


@dataclass
class ToolResultBlock:
    """A tool_result block supplied by the user (system)."""
    type: Literal["tool_result"] = "tool_result"
    tool_use_id: str = ""
    content: str | list[TextBlock] = ""
    is_error: bool = False


@dataclass
class ThinkingBlock:
    """An extended-thinking block (internal reasoning)."""
    type: Literal["thinking"] = "thinking"
    thinking: str = ""
    signature: str = ""


@dataclass
class RedactedThinkingBlock:
    """A redacted thinking block."""
    type: Literal["redacted_thinking"] = "redacted_thinking"
    data: str = ""


ContentBlock = Union[TextBlock, ToolUseBlock, ToolResultBlock, ThinkingBlock, RedactedThinkingBlock]


# ---------------------------------------------------------------------------
# Messages
# ---------------------------------------------------------------------------

class MessageRole(str, Enum):
    USER = "user"
    ASSISTANT = "assistant"


@dataclass
class UserMessage:
    """A message from the user."""
    type: Literal["user"] = "user"
    uuid: str = field(default_factory=lambda: str(uuid.uuid4()))
    content: str | list[ContentBlock] = ""
    # When this message is a tool_result, link back to the assistant message
    source_tool_assistant_uuid: str | None = None

    @property
    def role(self) -> str:
        return "user"

    def get_text(self) -> str:
        """Extract plain text from content."""
        if isinstance(self.content, str):
            return self.content
        return "\n".join(
            block.text for block in self.content
            if isinstance(block, TextBlock)
        )


@dataclass
class AssistantMessage:
    """A message from the assistant (model response)."""
    type: Literal["assistant"] = "assistant"
    uuid: str = field(default_factory=lambda: str(uuid.uuid4()))
    content: list[ContentBlock] = field(default_factory=list)
    model: str = ""
    stop_reason: str | None = None
    # API usage from this response
    usage: MessageUsage | None = None
    # Error from API (if stop_reason indicates an error)
    api_error: str | None = None

    @property
    def role(self) -> str:
        return "assistant"

    def get_text(self) -> str:
        """Extract plain text from content blocks."""
        return "\n".join(
            block.text for block in self.content
            if isinstance(block, TextBlock)
        )

    def get_tool_use_blocks(self) -> list[ToolUseBlock]:
        """Extract all tool_use blocks."""
        return [b for b in self.content if isinstance(b, ToolUseBlock)]

    def get_thinking_text(self) -> str:
        """Extract thinking text."""
        return "\n".join(
            block.thinking for block in self.content
            if isinstance(block, ThinkingBlock)
        )

    @property
    def has_tool_use(self) -> bool:
        return any(isinstance(b, ToolUseBlock) for b in self.content)


@dataclass
class SystemMessage:
    """A system message (not sent to API, UI-only)."""
    type: Literal["system"] = "system"
    uuid: str = field(default_factory=lambda: str(uuid.uuid4()))
    content: str = ""


@dataclass
class CompactBoundaryMessage:
    """Marks a compaction boundary in the conversation."""
    type: Literal["compact_boundary"] = "compact_boundary"
    uuid: str = field(default_factory=lambda: str(uuid.uuid4()))
    summary: str = ""


Message = Union[UserMessage, AssistantMessage, SystemMessage, CompactBoundaryMessage]


# ---------------------------------------------------------------------------
# Token Usage
# ---------------------------------------------------------------------------

@dataclass
class MessageUsage:
    """Token usage from a single API response."""
    input_tokens: int = 0
    output_tokens: int = 0
    cache_creation_input_tokens: int = 0
    cache_read_input_tokens: int = 0

    @property
    def total_tokens(self) -> int:
        return (
            self.input_tokens
            + self.output_tokens
            + self.cache_creation_input_tokens
            + self.cache_read_input_tokens
        )


# ---------------------------------------------------------------------------
# Stream Events
# ---------------------------------------------------------------------------

@dataclass
class StreamEvent:
    """An event from the streaming API."""
    type: str  # text_delta, tool_use_start, tool_use_delta, thinking_delta, etc.
    data: dict[str, Any] = field(default_factory=dict)


@dataclass
class RequestStartEvent:
    """Emitted when a new API request is about to be sent."""
    type: Literal["stream_request_start"] = "stream_request_start"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def create_user_message(
    content: str | list[ContentBlock],
    source_tool_assistant_uuid: str | None = None,
) -> UserMessage:
    """Create a UserMessage with a fresh UUID."""
    return UserMessage(
        content=content,
        source_tool_assistant_uuid=source_tool_assistant_uuid,
    )


def create_tool_result_message(
    tool_use_id: str,
    result: str,
    is_error: bool = False,
    source_assistant_uuid: str | None = None,
) -> UserMessage:
    """Create a UserMessage containing a tool_result block."""
    return UserMessage(
        content=[
            ToolResultBlock(
                tool_use_id=tool_use_id,
                content=result,
                is_error=is_error,
            )
        ],
        source_tool_assistant_uuid=source_assistant_uuid,
    )


def create_assistant_error_message(error: str, api_error: str | None = None) -> AssistantMessage:
    """Create an AssistantMessage representing an API error."""
    return AssistantMessage(
        content=[TextBlock(text=error)],
        api_error=api_error,
    )


def messages_to_api_params(messages: list[Message]) -> list[dict[str, Any]]:
    """Convert internal messages to Anthropic API message params.

    Filters out system/boundary messages and normalizes content.
    """
    api_messages: list[dict[str, Any]] = []
    for msg in messages:
        if isinstance(msg, UserMessage):
            if isinstance(msg.content, str):
                api_messages.append({"role": "user", "content": msg.content})
            else:
                blocks = []
                for block in msg.content:
                    if isinstance(block, TextBlock):
                        blocks.append({"type": "text", "text": block.text})
                    elif isinstance(block, ToolResultBlock):
                        result_content = block.content
                        if isinstance(result_content, list):
                            result_content = [{"type": "text", "text": b.text} for b in result_content]
                        blocks.append({
                            "type": "tool_result",
                            "tool_use_id": block.tool_use_id,
                            "content": result_content,
                            "is_error": block.is_error,
                        })
                if blocks:
                    api_messages.append({"role": "user", "content": blocks})

        elif isinstance(msg, AssistantMessage):
            blocks = []
            for block in msg.content:
                if isinstance(block, TextBlock):
                    blocks.append({"type": "text", "text": block.text})
                elif isinstance(block, ToolUseBlock):
                    blocks.append({
                        "type": "tool_use",
                        "id": block.id,
                        "name": block.name,
                        "input": block.input,
                    })
                elif isinstance(block, ThinkingBlock):
                    blocks.append({
                        "type": "thinking",
                        "thinking": block.thinking,
                        "signature": block.signature,
                    })
                elif isinstance(block, RedactedThinkingBlock):
                    blocks.append({
                        "type": "redacted_thinking",
                        "data": block.data,
                    })
            if blocks:
                api_messages.append({"role": "assistant", "content": blocks})

    return api_messages
