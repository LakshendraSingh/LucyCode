"""
Shell provider — abstraction over bash/zsh/powershell.
"""

from __future__ import annotations

import os
import platform
import shutil
from dataclasses import dataclass
from enum import Enum


class ShellType(str, Enum):
    BASH = "bash"
    ZSH = "zsh"
    FISH = "fish"
    POWERSHELL = "powershell"
    CMD = "cmd"
    SH = "sh"


@dataclass
class ShellProvider:
    """Information about the current shell."""
    shell_type: ShellType
    path: str
    version: str = ""
    supports_unicode: bool = True
    supports_256_colors: bool = True
    history_file: str = ""

    @property
    def name(self) -> str:
        return self.shell_type.value

    def get_exec_command(self, command: str) -> list[str]:
        """Get the command to execute a shell command."""
        if self.shell_type == ShellType.POWERSHELL:
            return [self.path, "-NoProfile", "-NonInteractive", "-Command", command]
        elif self.shell_type == ShellType.CMD:
            return [self.path, "/c", command]
        else:
            return [self.path, "-c", command]

    def get_env_prefix(self) -> dict[str, str]:
        """Get environment variables to set for this shell."""
        env = {"TERM": "xterm-256color"}
        if self.shell_type != ShellType.POWERSHELL:
            env["PAGER"] = "cat"
            env["GIT_PAGER"] = "cat"
        return env


def detect_shell() -> ShellType:
    """Detect the current shell."""
    shell_env = os.environ.get("SHELL", "")
    if "zsh" in shell_env:
        return ShellType.ZSH
    if "fish" in shell_env:
        return ShellType.FISH
    if "bash" in shell_env:
        return ShellType.BASH

    if platform.system() == "Windows":
        if shutil.which("pwsh"):
            return ShellType.POWERSHELL
        return ShellType.CMD

    return ShellType.BASH


def get_shell_provider() -> ShellProvider:
    """Get the shell provider for the current environment."""
    shell_type = detect_shell()

    # Find shell path
    paths = {
        ShellType.BASH: shutil.which("bash") or "/bin/bash",
        ShellType.ZSH: shutil.which("zsh") or "/bin/zsh",
        ShellType.FISH: shutil.which("fish") or "/usr/bin/fish",
        ShellType.POWERSHELL: shutil.which("pwsh") or shutil.which("powershell") or "pwsh",
        ShellType.CMD: os.environ.get("COMSPEC", "cmd.exe"),
        ShellType.SH: "/bin/sh",
    }

    path = paths.get(shell_type, "/bin/sh")

    # History file
    home = os.path.expanduser("~")
    history_files = {
        ShellType.BASH: os.path.join(home, ".bash_history"),
        ShellType.ZSH: os.path.join(home, ".zsh_history"),
        ShellType.FISH: os.path.join(home, ".local/share/fish/fish_history"),
    }

    return ShellProvider(
        shell_type=shell_type,
        path=path,
        history_file=history_files.get(shell_type, ""),
    )
