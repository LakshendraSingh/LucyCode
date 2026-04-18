"""
Shell completion — history-based and directory completion.
"""

from __future__ import annotations

import os
import readline
from typing import Any


class ShellCompletion:
    """Provide shell-like tab completion in the REPL."""

    def __init__(self):
        self._commands: list[str] = []
        self._history: list[str] = []

    def set_commands(self, commands: list[str]) -> None:
        """Set available slash commands for completion."""
        self._commands = sorted(commands)

    def add_history(self, entry: str) -> None:
        """Add an entry to conversation history for completion."""
        if entry and entry not in self._history:
            self._history.append(entry)
            if len(self._history) > 500:
                self._history = self._history[-500:]

    def complete(self, text: str, state: int) -> str | None:
        """Tab completion callback for readline."""
        if text.startswith("/"):
            matches = [c for c in self._commands if c.startswith(text)]
        elif text.startswith("~"):
            # Home directory expansion
            expanded = os.path.expanduser(text)
            matches = self._complete_path(expanded)
            # Convert back to ~ form
            home = os.path.expanduser("~")
            matches = [m.replace(home, "~") for m in matches]
        elif "/" in text or text.startswith("."):
            matches = self._complete_path(text)
        else:
            # History-based completion
            matches = [h for h in self._history if h.startswith(text)]

        if state < len(matches):
            return matches[state]
        return None

    def _complete_path(self, text: str) -> list[str]:
        """Complete filesystem paths."""
        directory = os.path.dirname(text) or "."
        prefix = os.path.basename(text)
        matches = []

        try:
            for entry in os.listdir(directory):
                if entry.startswith(prefix) or not prefix:
                    full = os.path.join(directory, entry)
                    if os.path.isdir(full):
                        matches.append(full + "/")
                    else:
                        matches.append(full)
        except OSError:
            pass

        return sorted(matches)[:20]

    def setup_readline(self) -> None:
        """Configure readline for tab completion."""
        try:
            readline.set_completer(self.complete)
            readline.parse_and_bind("tab: complete")
            readline.set_completer_delims(" \t\n;")
        except Exception:
            pass  # readline not available


def get_shell_history(history_file: str, limit: int = 100) -> list[str]:
    """Read recent shell history entries."""
    if not history_file or not os.path.exists(history_file):
        return []

    try:
        with open(history_file, errors="replace") as f:
            lines = f.readlines()

        # Clean up entries
        entries = []
        for line in lines[-limit * 2:]:
            line = line.strip()
            # Skip zsh extended history format timestamps
            if line.startswith(":"):
                parts = line.split(";", 1)
                if len(parts) > 1:
                    line = parts[1]
            if line and not line.startswith("#"):
                entries.append(line)

        return entries[-limit:]
    except OSError:
        return []
