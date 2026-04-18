"""
Session persistence — save and resume conversations.

Sessions are stored as JSONL files in ~/.lucy/sessions/<session_id>.jsonl
Each line is a JSON object representing a message or metadata entry.
"""

from __future__ import annotations

import json
import os
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

from lucy.core.config import get_config
from lucy.core.message import (
    AssistantMessage,
    CompactBoundaryMessage,
    ContentBlock,
    Message,
    MessageUsage,
    SystemMessage,
    TextBlock,
    ThinkingBlock,
    ToolResultBlock,
    ToolUseBlock,
    UserMessage,
    RedactedThinkingBlock,
)


# ---------------------------------------------------------------------------
# Session metadata
# ---------------------------------------------------------------------------

class SessionInfo:
    """Lightweight metadata about a session (for listing)."""

    def __init__(
        self,
        session_id: str,
        title: str = "",
        first_prompt: str = "",
        last_prompt: str = "",
        created_at: str = "",
        updated_at: str = "",
        model: str = "",
        message_count: int = 0,
        total_cost: float = 0.0,
        cwd: str = "",
    ) -> None:
        self.session_id = session_id
        self.title = title
        self.first_prompt = first_prompt
        self.last_prompt = last_prompt
        self.created_at = created_at
        self.updated_at = updated_at
        self.model = model
        self.message_count = message_count
        self.total_cost = total_cost
        self.cwd = cwd


# ---------------------------------------------------------------------------
# Serialization
# ---------------------------------------------------------------------------

def _serialize_content_block(block: ContentBlock) -> dict[str, Any]:
    """Serialize a content block to a dict."""
    if isinstance(block, TextBlock):
        return {"type": "text", "text": block.text}
    if isinstance(block, ToolUseBlock):
        return {"type": "tool_use", "id": block.id, "name": block.name, "input": block.input}
    if isinstance(block, ToolResultBlock):
        content = block.content
        if isinstance(content, list):
            content = [{"type": "text", "text": b.text} for b in content]
        return {
            "type": "tool_result",
            "tool_use_id": block.tool_use_id,
            "content": content,
            "is_error": block.is_error,
        }
    if isinstance(block, ThinkingBlock):
        return {"type": "thinking", "thinking": block.thinking, "signature": block.signature}
    if isinstance(block, RedactedThinkingBlock):
        return {"type": "redacted_thinking", "data": block.data}
    return {"type": "unknown"}


def _deserialize_content_block(data: dict[str, Any]) -> ContentBlock:
    """Deserialize a content block from a dict."""
    btype = data.get("type", "")
    if btype == "text":
        return TextBlock(text=data.get("text", ""))
    if btype == "tool_use":
        return ToolUseBlock(
            id=data.get("id", ""), name=data.get("name", ""), input=data.get("input", {})
        )
    if btype == "tool_result":
        content = data.get("content", "")
        if isinstance(content, list):
            content = [TextBlock(text=b.get("text", "")) for b in content]
        return ToolResultBlock(
            tool_use_id=data.get("tool_use_id", ""),
            content=content,
            is_error=data.get("is_error", False),
        )
    if btype == "thinking":
        return ThinkingBlock(
            thinking=data.get("thinking", ""), signature=data.get("signature", "")
        )
    if btype == "redacted_thinking":
        return RedactedThinkingBlock(data=data.get("data", ""))
    return TextBlock(text="")


def serialize_message(msg: Message) -> dict[str, Any]:
    """Serialize a message to a dict for JSONL storage."""
    if isinstance(msg, UserMessage):
        content: Any
        if isinstance(msg.content, str):
            content = msg.content
        else:
            content = [_serialize_content_block(b) for b in msg.content]
        return {
            "type": "user",
            "uuid": msg.uuid,
            "content": content,
            "source_tool_assistant_uuid": msg.source_tool_assistant_uuid,
        }
    if isinstance(msg, AssistantMessage):
        data: dict[str, Any] = {
            "type": "assistant",
            "uuid": msg.uuid,
            "content": [_serialize_content_block(b) for b in msg.content],
            "model": msg.model,
            "stop_reason": msg.stop_reason,
        }
        if msg.usage:
            data["usage"] = {
                "input_tokens": msg.usage.input_tokens,
                "output_tokens": msg.usage.output_tokens,
                "cache_creation_input_tokens": msg.usage.cache_creation_input_tokens,
                "cache_read_input_tokens": msg.usage.cache_read_input_tokens,
            }
        return data
    if isinstance(msg, SystemMessage):
        return {"type": "system", "uuid": msg.uuid, "content": msg.content}
    if isinstance(msg, CompactBoundaryMessage):
        return {"type": "compact_boundary", "uuid": msg.uuid, "summary": msg.summary}
    return {"type": "unknown", "uuid": getattr(msg, "uuid", "")}


def deserialize_message(data: dict[str, Any]) -> Message | None:
    """Deserialize a message from a dict."""
    mtype = data.get("type", "")

    if mtype == "user":
        content = data.get("content", "")
        if isinstance(content, list):
            content = [_deserialize_content_block(b) for b in content]
        return UserMessage(
            uuid=data.get("uuid", str(uuid.uuid4())),
            content=content,
            source_tool_assistant_uuid=data.get("source_tool_assistant_uuid"),
        )
    if mtype == "assistant":
        blocks = [_deserialize_content_block(b) for b in data.get("content", [])]
        usage = None
        if "usage" in data and data["usage"]:
            u = data["usage"]
            usage = MessageUsage(
                input_tokens=u.get("input_tokens", 0),
                output_tokens=u.get("output_tokens", 0),
                cache_creation_input_tokens=u.get("cache_creation_input_tokens", 0),
                cache_read_input_tokens=u.get("cache_read_input_tokens", 0),
            )
        return AssistantMessage(
            uuid=data.get("uuid", str(uuid.uuid4())),
            content=blocks,
            model=data.get("model", ""),
            stop_reason=data.get("stop_reason"),
            usage=usage,
        )
    if mtype == "system":
        return SystemMessage(
            uuid=data.get("uuid", str(uuid.uuid4())),
            content=data.get("content", ""),
        )
    if mtype == "compact_boundary":
        return CompactBoundaryMessage(
            uuid=data.get("uuid", str(uuid.uuid4())),
            summary=data.get("summary", ""),
        )

    return None


# ---------------------------------------------------------------------------
# Session file operations
# ---------------------------------------------------------------------------

def _get_session_dir() -> Path:
    """Get the sessions directory."""
    return get_config().sessions_dir


def _get_session_file(session_id: str) -> Path:
    """Get the file path for a session."""
    return _get_session_dir() / f"{session_id}.jsonl"


def save_message(session_id: str, message: Message) -> None:
    """Append a single message to a session file."""
    session_dir = _get_session_dir()
    session_dir.mkdir(parents=True, exist_ok=True)

    filepath = _get_session_file(session_id)
    entry = serialize_message(message)
    with open(filepath, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, default=str) + "\n")


def save_metadata(
    session_id: str,
    title: str = "",
    model: str = "",
    cwd: str = "",
    total_cost: float = 0.0,
) -> None:
    """Save/update session metadata."""
    filepath = _get_session_file(session_id)
    entry = {
        "type": "metadata",
        "session_id": session_id,
        "title": title,
        "model": model,
        "cwd": cwd,
        "total_cost": total_cost,
        "updated_at": datetime.now().isoformat(),
    }
    with open(filepath, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, default=str) + "\n")


def save_session(
    session_id: str,
    messages: list[Message],
    title: str = "",
    model: str = "",
    cwd: str = "",
    total_cost: float = 0.0,
) -> None:
    """Save an entire session (overwriting any existing file)."""
    session_dir = _get_session_dir()
    session_dir.mkdir(parents=True, exist_ok=True)

    filepath = _get_session_file(session_id)

    with open(filepath, "w", encoding="utf-8") as f:
        # Metadata header
        header = {
            "type": "metadata",
            "session_id": session_id,
            "title": title,
            "model": model,
            "cwd": cwd,
            "total_cost": total_cost,
            "created_at": datetime.now().isoformat(),
            "updated_at": datetime.now().isoformat(),
        }
        f.write(json.dumps(header, default=str) + "\n")

        # Messages
        for msg in messages:
            entry = serialize_message(msg)
            f.write(json.dumps(entry, default=str) + "\n")


def load_session(session_id: str) -> tuple[list[Message], SessionInfo | None]:
    """Load a session from disk.

    Returns (messages, session_info).
    """
    filepath = _get_session_file(session_id)
    if not filepath.exists():
        return [], None

    messages: list[Message] = []
    info = SessionInfo(session_id=session_id)

    with open(filepath, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                data = json.loads(line)
            except json.JSONDecodeError:
                continue

            if data.get("type") == "metadata":
                info.title = data.get("title", "")
                info.model = data.get("model", "")
                info.cwd = data.get("cwd", "")
                info.total_cost = data.get("total_cost", 0.0)
                info.created_at = data.get("created_at", "")
                info.updated_at = data.get("updated_at", "")
                continue

            msg = deserialize_message(data)
            if msg is not None:
                messages.append(msg)

    info.message_count = len(messages)

    # Extract first/last prompt
    for m in messages:
        if isinstance(m, UserMessage):
            text = m.get_text().strip()
            if text and not info.first_prompt:
                info.first_prompt = text[:100]
            if text:
                info.last_prompt = text[:100]

    return messages, info


def list_sessions(limit: int = 20) -> list[SessionInfo]:
    """List available sessions, most recent first."""
    session_dir = _get_session_dir()
    if not session_dir.exists():
        return []

    sessions: list[SessionInfo] = []

    for filepath in sorted(session_dir.glob("*.jsonl"), key=lambda p: p.stat().st_mtime, reverse=True):
        if len(sessions) >= limit:
            break

        session_id = filepath.stem
        info = SessionInfo(session_id=session_id)

        # Quick metadata scan (read first and last few lines)
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        data = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    if data.get("type") == "metadata":
                        info.title = data.get("title", "")
                        info.model = data.get("model", "")
                        info.cwd = data.get("cwd", "")
                        info.total_cost = data.get("total_cost", 0.0)
                        info.created_at = data.get("created_at", "")
                        info.updated_at = data.get("updated_at", "")
                    elif data.get("type") == "user":
                        content = data.get("content", "")
                        text = content if isinstance(content, str) else ""
                        if text and not info.first_prompt:
                            info.first_prompt = text[:100]
                        info.message_count += 1
                    else:
                        info.message_count += 1
        except OSError:
            continue

        if not info.title and info.first_prompt:
            info.title = info.first_prompt

        sessions.append(info)

    return sessions


def delete_session(session_id: str) -> bool:
    """Delete a session file."""
    filepath = _get_session_file(session_id)
    if filepath.exists():
        filepath.unlink()
        return True
    return False
