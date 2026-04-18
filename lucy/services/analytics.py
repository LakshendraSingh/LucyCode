"""
Analytics service — usage analytics collection and reporting.
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass, field
from typing import Any


@dataclass
class AnalyticsEvent:
    event_type: str
    timestamp: float = field(default_factory=time.time)
    data: dict[str, Any] = field(default_factory=dict)


class AnalyticsService:
    """Local-only analytics collection. No data is sent externally."""

    def __init__(self, storage_dir: str | None = None):
        self._storage_dir = storage_dir or os.path.expanduser("~/.lucycode/analytics")
        self._events: list[AnalyticsEvent] = []
        self._session_start = time.time()

    def track(self, event_type: str, data: dict[str, Any] | None = None) -> None:
        self._events.append(AnalyticsEvent(event_type=event_type, data=data or {}))

    def track_tool_use(self, tool_name: str, duration: float, success: bool) -> None:
        self.track("tool_use", {
            "tool": tool_name, "duration_ms": duration * 1000,
            "success": success,
        })

    def track_command(self, command_name: str) -> None:
        self.track("command", {"command": command_name})

    def track_query(self, model: str, input_tokens: int, output_tokens: int, cost: float) -> None:
        self.track("query", {
            "model": model, "input_tokens": input_tokens,
            "output_tokens": output_tokens, "cost": cost,
        })

    def get_summary(self) -> dict[str, Any]:
        elapsed = time.time() - self._session_start
        tool_uses = [e for e in self._events if e.event_type == "tool_use"]
        queries = [e for e in self._events if e.event_type == "query"]
        commands = [e for e in self._events if e.event_type == "command"]

        total_cost = sum(e.data.get("cost", 0) for e in queries)
        total_tokens = sum(
            e.data.get("input_tokens", 0) + e.data.get("output_tokens", 0)
            for e in queries
        )

        # Tool frequency
        tool_freq: dict[str, int] = {}
        for e in tool_uses:
            name = e.data.get("tool", "unknown")
            tool_freq[name] = tool_freq.get(name, 0) + 1

        return {
            "session_duration_s": elapsed,
            "total_events": len(self._events),
            "queries": len(queries),
            "tool_uses": len(tool_uses),
            "commands": len(commands),
            "total_cost": total_cost,
            "total_tokens": total_tokens,
            "tool_frequency": tool_freq,
            "top_tools": sorted(tool_freq.items(), key=lambda x: x[1], reverse=True)[:5],
        }

    def save_session(self, session_id: str) -> None:
        """Persist analytics to disk."""
        os.makedirs(self._storage_dir, exist_ok=True)
        path = os.path.join(self._storage_dir, f"{session_id}.json")
        data = {
            "session_id": session_id,
            "session_start": self._session_start,
            "events": [
                {"type": e.event_type, "timestamp": e.timestamp, "data": e.data}
                for e in self._events
            ],
            "summary": self.get_summary(),
        }
        with open(path, "w") as f:
            json.dump(data, f, indent=2)


_analytics: AnalyticsService | None = None


def get_analytics() -> AnalyticsService:
    global _analytics
    if _analytics is None:
        _analytics = AnalyticsService()
    return _analytics
