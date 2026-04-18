"""
Command registry — known commands with metadata and safety classification.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class CommandInfo:
    """Information about a known shell command."""
    name: str
    category: str  # file, network, process, package, git, system, text, dev
    is_read_only: bool = False
    is_dangerous: bool = False
    description: str = ""
    common_flags: dict[str, str] | None = None


# Registry of known commands
_COMMANDS: dict[str, CommandInfo] = {}


def _register(name: str, category: str, read_only: bool = False,
              dangerous: bool = False, description: str = "") -> None:
    _COMMANDS[name] = CommandInfo(
        name=name, category=category, is_read_only=read_only,
        is_dangerous=dangerous, description=description,
    )


# File operations
_register("ls", "file", read_only=True, description="List directory contents")
_register("cat", "file", read_only=True, description="Concatenate and print files")
_register("head", "file", read_only=True, description="Output the first part of files")
_register("tail", "file", read_only=True, description="Output the last part of files")
_register("find", "file", read_only=True, description="Search for files")
_register("tree", "file", read_only=True, description="Display directory tree")
_register("stat", "file", read_only=True, description="Display file status")
_register("file", "file", read_only=True, description="Determine file type")
_register("du", "file", read_only=True, description="Disk usage")
_register("df", "file", read_only=True, description="Disk free space")
_register("wc", "file", read_only=True, description="Word/line/byte count")
_register("cp", "file", description="Copy files")
_register("mv", "file", description="Move/rename files")
_register("rm", "file", dangerous=True, description="Remove files")
_register("rmdir", "file", description="Remove directories")
_register("mkdir", "file", description="Create directories")
_register("touch", "file", description="Create/update file timestamps")
_register("chmod", "file", dangerous=True, description="Change file permissions")
_register("chown", "file", dangerous=True, description="Change file ownership")
_register("ln", "file", description="Create links")

# Text processing
_register("grep", "text", read_only=True, description="Search text patterns")
_register("rg", "text", read_only=True, description="Ripgrep")
_register("ag", "text", read_only=True, description="The Silver Searcher")
_register("sed", "text", description="Stream editor")
_register("awk", "text", read_only=True, description="Pattern scanning")
_register("sort", "text", read_only=True, description="Sort lines")
_register("uniq", "text", read_only=True, description="Report unique lines")
_register("cut", "text", read_only=True, description="Cut columns")
_register("tr", "text", read_only=True, description="Translate characters")
_register("diff", "text", read_only=True, description="Compare files")
_register("jq", "text", read_only=True, description="JSON processor")

# Network
_register("curl", "network", description="Transfer data from URLs")
_register("wget", "network", description="Download files")
_register("ssh", "network", dangerous=True, description="Secure Shell")
_register("scp", "network", description="Secure copy")
_register("ping", "network", read_only=True, description="Send ICMP echo")
_register("nslookup", "network", read_only=True, description="DNS lookup")
_register("dig", "network", read_only=True, description="DNS lookup")

# Git
_register("git", "git", description="Version control")

# Package managers
_register("pip", "package", description="Python package installer")
_register("npm", "package", description="Node package manager")
_register("yarn", "package", description="Yarn package manager")
_register("cargo", "package", description="Rust package manager")
_register("brew", "package", description="Homebrew")
_register("apt", "package", dangerous=True, description="APT package manager")
_register("apt-get", "package", dangerous=True, description="APT-GET")

# Process management
_register("ps", "process", read_only=True, description="Process status")
_register("top", "process", read_only=True, description="Process monitor")
_register("kill", "process", dangerous=True, description="Terminate processes")
_register("killall", "process", dangerous=True, description="Kill by name")

# Development
_register("python", "dev", description="Python interpreter")
_register("python3", "dev", description="Python 3 interpreter")
_register("node", "dev", description="Node.js runtime")
_register("go", "dev", description="Go compiler")
_register("rustc", "dev", description="Rust compiler")
_register("cargo", "dev", description="Cargo (Rust)")
_register("make", "dev", description="Build tool")
_register("gcc", "dev", description="GNU C compiler")
_register("javac", "dev", description="Java compiler")

# System
_register("echo", "system", read_only=True, description="Print text")
_register("date", "system", read_only=True, description="Display date/time")
_register("whoami", "system", read_only=True, description="Current user")
_register("uname", "system", read_only=True, description="System information")
_register("env", "system", read_only=True, description="Environment variables")
_register("printenv", "system", read_only=True, description="Print environment")
_register("which", "system", read_only=True, description="Locate command")
_register("hostname", "system", read_only=True, description="System hostname")


def get_command_info(name: str) -> CommandInfo | None:
    """Get information about a command."""
    return _COMMANDS.get(name)


def is_known_command(name: str) -> bool:
    return name in _COMMANDS


def get_all_commands() -> dict[str, CommandInfo]:
    return dict(_COMMANDS)
