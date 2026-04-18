"""
Diff preview — show unified diffs before applying changes.

Provides:
  - Pre-apply diff preview with colored output
  - Undo support (track file changes)
  - File change history per session
"""

from __future__ import annotations

import difflib
import os
import shutil
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

UNDO_DIR = Path.home() / ".lucy" / "undo"
MAX_UNDO_HISTORY = 50


@dataclass
class FileChange:
    """A tracked file change."""
    filepath: str
    original_content: str
    new_content: str
    timestamp: float = field(default_factory=time.time)
    change_type: str = "edit"  # edit, create, delete
    backup_path: str = ""

    @property
    def diff(self) -> str:
        """Generate a unified diff."""
        return generate_diff(
            self.original_content, self.new_content,
            f"a/{os.path.basename(self.filepath)}",
            f"b/{os.path.basename(self.filepath)}",
        )


class UndoManager:
    """Track and undo file changes."""

    def __init__(self):
        self._history: list[FileChange] = []
        UNDO_DIR.mkdir(parents=True, exist_ok=True)

    def record_change(
        self,
        filepath: str,
        original_content: str,
        new_content: str,
        change_type: str = "edit",
    ) -> FileChange:
        """Record a file change for potential undo."""
        # Save backup
        backup_name = f"{int(time.time())}_{os.path.basename(filepath)}"
        backup_path = UNDO_DIR / backup_name
        try:
            backup_path.write_text(original_content)
        except OSError:
            pass

        change = FileChange(
            filepath=filepath,
            original_content=original_content,
            new_content=new_content,
            change_type=change_type,
            backup_path=str(backup_path),
        )
        self._history.append(change)

        # Trim history
        if len(self._history) > MAX_UNDO_HISTORY:
            old = self._history.pop(0)
            try:
                os.unlink(old.backup_path)
            except OSError:
                pass

        return change

    def undo_last(self) -> FileChange | None:
        """Undo the most recent change."""
        if not self._history:
            return None

        change = self._history.pop()
        try:
            if change.change_type == "delete":
                Path(change.filepath).write_text(change.original_content)
            elif change.change_type == "create":
                os.unlink(change.filepath)
            else:
                Path(change.filepath).write_text(change.original_content)
        except OSError:
            pass

        return change

    def undo_file(self, filepath: str) -> FileChange | None:
        """Undo the most recent change to a specific file."""
        for i in range(len(self._history) - 1, -1, -1):
            if self._history[i].filepath == filepath:
                change = self._history.pop(i)
                try:
                    Path(change.filepath).write_text(change.original_content)
                except OSError:
                    pass
                return change
        return None

    def get_history(self, limit: int = 20) -> list[FileChange]:
        return list(reversed(self._history[:limit]))

    def preview_last(self) -> str | None:
        """Preview the diff of the last change."""
        if not self._history:
            return None
        return self._history[-1].diff

    def clear(self) -> int:
        count = len(self._history)
        self._history.clear()
        return count


def generate_diff(
    old_text: str,
    new_text: str,
    old_name: str = "original",
    new_name: str = "modified",
    context_lines: int = 3,
) -> str:
    """Generate a unified diff between two strings."""
    old_lines = old_text.splitlines(keepends=True)
    new_lines = new_text.splitlines(keepends=True)

    diff = difflib.unified_diff(
        old_lines, new_lines,
        fromfile=old_name, tofile=new_name,
        n=context_lines,
    )
    return "".join(diff)


def colorize_diff(diff_text: str) -> str:
    """Add ANSI colors to a unified diff."""
    lines = []
    for line in diff_text.split("\n"):
        if line.startswith("+++") or line.startswith("---"):
            lines.append(f"\033[1m{line}\033[0m")  # Bold
        elif line.startswith("@@"):
            lines.append(f"\033[36m{line}\033[0m")  # Cyan
        elif line.startswith("+"):
            lines.append(f"\033[32m{line}\033[0m")  # Green
        elif line.startswith("-"):
            lines.append(f"\033[31m{line}\033[0m")  # Red
        else:
            lines.append(line)
    return "\n".join(lines)


def preview_file_change(filepath: str, new_content: str) -> str:
    """Preview what a file change would look like."""
    try:
        old_content = Path(filepath).read_text()
    except (OSError, FileNotFoundError):
        old_content = ""

    if not old_content:
        line_count = new_content.count("\n") + 1
        return f"[NEW FILE] {filepath} ({line_count} lines)"

    diff = generate_diff(old_content, new_content, filepath, filepath)
    if not diff:
        return f"[NO CHANGES] {filepath}"

    return colorize_diff(diff)


# Global singleton
_undo_manager: UndoManager | None = None


def get_undo_manager() -> UndoManager:
    global _undo_manager
    if _undo_manager is None:
        _undo_manager = UndoManager()
    return _undo_manager
