"""
Chrome Native Messaging Host for LucyCode.
"""

from __future__ import annotations

import json
import struct
import sys
import threading
from typing import Any

from lucy.core.config import get_config


class NativeHost:
    """Handles communication with the Chrome extension."""

    def __init__(self):
        self._running = False

    def read_message(self) -> dict[str, Any] | None:
        """Read a message from stdin (first 4 bytes are length)."""
        raw_length = sys.stdin.buffer.read(4)
        if len(raw_length) == 0:
            return None
        length = struct.unpack('@I', raw_length)[0]
        message = sys.stdin.buffer.read(length).decode('utf-8')
        return json.loads(message)

    def send_message(self, message: dict[str, Any]) -> None:
        """Send a message to stdout."""
        encoded = json.dumps(message).encode('utf-8')
        sys.stdout.buffer.write(struct.pack('@I', len(encoded)))
        sys.stdout.buffer.write(encoded)
        sys.stdout.buffer.flush()

    def process_message(self, message: dict[str, Any]) -> None:
        """Process an incoming message."""
        action = message.get("action")
        if action == "ping":
            self.send_message({"action": "pong", "status": "ok"})
        elif action == "evaluate_context":
            # For simplicity, returning mock data for now. Real implementation
            # would interact with LucyCode core context engine.
            self.send_message({"action": "context_result", "data": "DOM context processed."})
        else:
            self.send_message({"error": f"Unknown action: {action}"})

    def run(self):
        """Run the main IO loop."""
        self._running = True
        while self._running:
            try:
                msg = self.read_message()
                if msg is None:
                    break
                self.process_message(msg)
            except Exception as e:
                self.send_message({"error": str(e)})


def main():
    host = NativeHost()
    host.run()


if __name__ == "__main__":
    main()
