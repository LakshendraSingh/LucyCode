"""
IDE integration — VS Code and JetBrains support.

Provides:
  - Deep link handling (lucy://...)
  - File opening in the user's IDE
  - Terminal detection
  - Editor launch
"""

from __future__ import annotations

import asyncio
import logging
import os
import shutil
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


class IDE(str, Enum):
    VSCODE = "vscode"
    CURSOR = "cursor"
    JETBRAINS = "jetbrains"
    VIM = "vim"
    NEOVIM = "neovim"
    EMACS = "emacs"
    SUBLIME = "sublime"
    UNKNOWN = "unknown"


def detect_ide() -> IDE:
    """Detect the user's IDE from environment variables."""
    term_program = os.environ.get("TERM_PROGRAM", "").lower()
    if "vscode" in term_program:
        return IDE.VSCODE
    if "cursor" in term_program:
        return IDE.CURSOR

    # Check for JetBrains
    if os.environ.get("JETBRAINS_IDE"):
        return IDE.JETBRAINS
    if os.environ.get("IDEA_INITIAL_DIRECTORY"):
        return IDE.JETBRAINS

    # Check EDITOR
    editor = os.environ.get("EDITOR", "").lower()
    if "nvim" in editor or "neovim" in editor:
        return IDE.NEOVIM
    if "vim" in editor:
        return IDE.VIM
    if "emacs" in editor:
        return IDE.EMACS
    if "subl" in editor:
        return IDE.SUBLIME

    return IDE.UNKNOWN


def get_ide_name(ide: IDE) -> str:
    """Get human-readable IDE name."""
    return {
        IDE.VSCODE: "VS Code",
        IDE.CURSOR: "Cursor",
        IDE.JETBRAINS: "JetBrains",
        IDE.VIM: "Vim",
        IDE.NEOVIM: "Neovim",
        IDE.EMACS: "Emacs",
        IDE.SUBLIME: "Sublime Text",
        IDE.UNKNOWN: "Unknown",
    }.get(ide, "Unknown")


async def open_in_ide(filepath: str, line: int | None = None) -> bool:
    """Open a file in the user's IDE."""
    ide = detect_ide()

    if ide == IDE.VSCODE:
        return await _open_vscode(filepath, line)
    if ide == IDE.CURSOR:
        return await _open_cursor(filepath, line)
    if ide in (IDE.VIM, IDE.NEOVIM):
        return False  # Can't open from subprocess
    if ide == IDE.SUBLIME:
        return await _open_sublime(filepath, line)
    if ide == IDE.JETBRAINS:
        return await _open_jetbrains(filepath, line)

    # Fallback: try common editors
    for cmd in ["code", "cursor", "subl"]:
        if shutil.which(cmd):
            return await _open_with_command(cmd, filepath, line)

    return False


async def _open_vscode(filepath: str, line: int | None = None) -> bool:
    """Open in VS Code."""
    target = f"{filepath}:{line}" if line else filepath
    return await _open_with_command("code", target, line=None)


async def _open_cursor(filepath: str, line: int | None = None) -> bool:
    """Open in Cursor."""
    target = f"{filepath}:{line}" if line else filepath
    return await _open_with_command("cursor", target, line=None)


async def _open_sublime(filepath: str, line: int | None = None) -> bool:
    """Open in Sublime Text."""
    target = f"{filepath}:{line}" if line else filepath
    return await _open_with_command("subl", target, line=None)


async def _open_jetbrains(filepath: str, line: int | None = None) -> bool:
    """Open in JetBrains IDE."""
    # Try common JetBrains CLI launchers
    for cmd in ["idea", "pycharm", "webstorm", "goland", "clion", "phpstorm"]:
        if shutil.which(cmd):
            args = ["--line", str(line), filepath] if line else [filepath]
            try:
                proc = await asyncio.create_subprocess_exec(
                    cmd, *args,
                    stdout=asyncio.subprocess.DEVNULL,
                    stderr=asyncio.subprocess.DEVNULL,
                )
                return proc.returncode == 0 or proc.returncode is None
            except Exception:
                continue
    return False


async def _open_with_command(command: str, filepath: str, line: int | None = None) -> bool:
    """Open a file with a command-line editor."""
    if not shutil.which(command):
        return False

    args = [command]
    if line and command in ("code", "cursor"):
        args.extend(["--goto", f"{filepath}:{line}"])
    else:
        args.append(filepath)

    try:
        proc = await asyncio.create_subprocess_exec(
            *args,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )
        return proc.returncode == 0 or proc.returncode is None
    except Exception:
        return False


def get_terminal_info() -> dict[str, str]:
    """Get information about the current terminal."""
    return {
        "term_program": os.environ.get("TERM_PROGRAM", "unknown"),
        "term": os.environ.get("TERM", "unknown"),
        "shell": os.environ.get("SHELL", "unknown"),
        "ide": detect_ide().value,
        "ide_name": get_ide_name(detect_ide()),
        "columns": os.environ.get("COLUMNS", "80"),
        "lines": os.environ.get("LINES", "24"),
    }
