"""
Conversation recovery — crash recovery and persistence.
"""

from __future__ import annotations

import json
import os
import time
from typing import Any


class ConversationRecovery:
    """Auto-save conversations for crash recovery."""

    def __init__(self, recovery_dir: str | None = None):
        self._dir = recovery_dir or os.path.expanduser("~/.lucycode/recovery")
        os.makedirs(self._dir, exist_ok=True)
        self._session_id = ""
        self._last_save = 0.0
        self._save_interval = 30.0  # Save every 30 seconds

    def set_session(self, session_id: str) -> None:
        self._session_id = session_id

    def should_save(self) -> bool:
        return time.time() - self._last_save > self._save_interval

    def save(self, messages: list, metadata: dict[str, Any] | None = None) -> None:
        """Save current state for recovery."""
        if not self._session_id:
            return

        recovery_file = os.path.join(self._dir, f"{self._session_id}.recovery.json")
        data = {
            "session_id": self._session_id,
            "timestamp": time.time(),
            "message_count": len(messages),
            "metadata": metadata or {},
            "messages": [
                {"role": "user" if hasattr(m, "role") and m.role == "user" else "assistant",
                 "text": m.get_text()[:10000]}
                for m in messages[-50:]  # Keep last 50 messages
            ],
        }

        try:
            with open(recovery_file, "w") as f:
                json.dump(data, f)
            self._last_save = time.time()
        except OSError:
            pass

    def recover(self, session_id: str) -> dict[str, Any] | None:
        """Attempt to recover a crashed session."""
        recovery_file = os.path.join(self._dir, f"{session_id}.recovery.json")
        if not os.path.exists(recovery_file):
            return None

        try:
            with open(recovery_file) as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            return None

    def list_recoverable(self) -> list[dict[str, Any]]:
        """List all recoverable sessions."""
        sessions = []
        if not os.path.exists(self._dir):
            return sessions

        for fname in os.listdir(self._dir):
            if fname.endswith(".recovery.json"):
                path = os.path.join(self._dir, fname)
                try:
                    with open(path) as f:
                        data = json.load(f)
                    sessions.append({
                        "session_id": data.get("session_id", ""),
                        "timestamp": data.get("timestamp", 0),
                        "message_count": data.get("message_count", 0),
                        "path": path,
                    })
                except Exception:
                    continue

        return sorted(sessions, key=lambda s: s["timestamp"], reverse=True)

    def cleanup(self, session_id: str) -> None:
        """Remove recovery file after successful session end."""
        path = os.path.join(self._dir, f"{session_id}.recovery.json")
        try:
            os.remove(path)
        except OSError:
            pass

    def cleanup_old(self, max_age_days: int = 7) -> int:
        """Clean up old recovery files."""
        cutoff = time.time() - (max_age_days * 86400)
        removed = 0
        for fname in os.listdir(self._dir):
            path = os.path.join(self._dir, fname)
            try:
                if os.path.getmtime(path) < cutoff:
                    os.remove(path)
                    removed += 1
            except OSError:
                continue
        return removed


_recovery: ConversationRecovery | None = None


def get_recovery() -> ConversationRecovery:
    global _recovery
    if _recovery is None:
        _recovery = ConversationRecovery()
    return _recovery
