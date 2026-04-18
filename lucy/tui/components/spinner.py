"""
Animated spinner with multiple states.
"""

from __future__ import annotations

import time
from typing import Any

from rich.spinner import Spinner
from rich.text import Text


class AnimatedSpinner:
    """Rich spinner with different animation states."""

    STATES = {
        "thinking": {"name": "dots", "style": "cyan", "text": "Thinking"},
        "working": {"name": "dots2", "style": "green", "text": "Working"},
        "searching": {"name": "line", "style": "yellow", "text": "Searching"},
        "writing": {"name": "dots3", "style": "magenta", "text": "Writing"},
        "stalled": {"name": "simpleDots", "style": "red", "text": "Waiting"},
        "connecting": {"name": "dots4", "style": "blue", "text": "Connecting"},
    }

    def __init__(self, state: str = "thinking"):
        self._state = state
        self._start_time = time.time()
        self._spinner = self._create_spinner(state)

    def _create_spinner(self, state: str) -> Spinner:
        cfg = self.STATES.get(state, self.STATES["thinking"])
        return Spinner(cfg["name"], text=cfg["text"], style=cfg["style"])

    def set_state(self, state: str) -> None:
        if state != self._state and state in self.STATES:
            self._state = state
            self._spinner = self._create_spinner(state)
            self._start_time = time.time()

    @property
    def elapsed(self) -> float:
        return time.time() - self._start_time

    @property
    def spinner(self) -> Spinner:
        # Auto-switch to stalled if too long
        if self.elapsed > 30 and self._state != "stalled":
            self.set_state("stalled")
        return self._spinner

    def __rich__(self) -> Spinner:
        return self.spinner


class ToolSpinner(AnimatedSpinner):
    """Spinner specialized for tool execution."""

    def __init__(self, tool_name: str):
        super().__init__("working")
        self._tool_name = tool_name
        self._spinner = self._create_spinner("working")
        self._spinner.text = f"Running {tool_name}..."

    def set_progress(self, message: str) -> None:
        self._spinner.text = f"{self._tool_name}: {message}"
