"""
Session memory service — cross-session memory persistence and retrieval.
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass, field
from typing import Any


@dataclass
class Memory:
    content: str
    category: str = "general"  # general, preference, fact, learned
    timestamp: float = field(default_factory=time.time)
    source_session: str = ""
    relevance_score: float = 1.0
    tags: list[str] = field(default_factory=list)


class SessionMemoryService:
    """Persistent memory across sessions."""

    def __init__(self, storage_path: str | None = None):
        self._path = storage_path or os.path.expanduser("~/.lucycode/memories.json")
        self._memories: list[Memory] = []
        self._load()

    def _load(self) -> None:
        if os.path.exists(self._path):
            try:
                with open(self._path) as f:
                    data = json.load(f)
                self._memories = [
                    Memory(
                        content=m["content"],
                        category=m.get("category", "general"),
                        timestamp=m.get("timestamp", 0),
                        source_session=m.get("source_session", ""),
                        relevance_score=m.get("relevance_score", 1.0),
                        tags=m.get("tags", []),
                    )
                    for m in data
                ]
            except (json.JSONDecodeError, OSError, KeyError):
                self._memories = []

    def _save(self) -> None:
        os.makedirs(os.path.dirname(self._path), exist_ok=True)
        with open(self._path, "w") as f:
            json.dump([
                {
                    "content": m.content,
                    "category": m.category,
                    "timestamp": m.timestamp,
                    "source_session": m.source_session,
                    "relevance_score": m.relevance_score,
                    "tags": m.tags,
                }
                for m in self._memories
            ], f, indent=2)

    def add(self, content: str, category: str = "general",
            session_id: str = "", tags: list[str] | None = None) -> None:
        # Deduplicate
        for m in self._memories:
            if m.content == content:
                m.relevance_score += 0.1  # Boost relevance
                self._save()
                return

        self._memories.append(Memory(
            content=content, category=category,
            source_session=session_id, tags=tags or [],
        ))

        # Keep max 500 memories
        if len(self._memories) > 500:
            self._memories.sort(key=lambda m: m.relevance_score * (m.timestamp / time.time()))
            self._memories = self._memories[-500:]

        self._save()

    def search(self, query: str, limit: int = 10) -> list[Memory]:
        query_lower = query.lower()
        scored = []
        for m in self._memories:
            score = 0
            if query_lower in m.content.lower():
                score = 1.0
            else:
                words = query_lower.split()
                matching = sum(1 for w in words if w in m.content.lower())
                score = matching / max(len(words), 1)
            if score > 0:
                scored.append((score * m.relevance_score, m))

        scored.sort(key=lambda x: x[0], reverse=True)
        return [m for _, m in scored[:limit]]

    def get_context_memories(self, context: str = "", limit: int = 5) -> list[Memory]:
        """Get relevant memories for the current context."""
        if context:
            return self.search(context, limit)
        # Return most recent
        recent = sorted(self._memories, key=lambda m: m.timestamp, reverse=True)
        return recent[:limit]

    def get_all(self) -> list[Memory]:
        return list(self._memories)

    def clear(self) -> None:
        self._memories.clear()
        self._save()

    def count(self) -> int:
        return len(self._memories)


_service: SessionMemoryService | None = None


def get_session_memory() -> SessionMemoryService:
    global _service
    if _service is None:
        _service = SessionMemoryService()
    return _service
