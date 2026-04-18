"""
Shell subsystem — parsing, quoting, completion, provider abstraction.
"""

from lucy.shell.parser import parse_command, ParsedCommand
from lucy.shell.quoting import shell_quote, shell_unquote
from lucy.shell.provider import ShellProvider, get_shell_provider
from lucy.shell.commands import get_command_info, CommandInfo

__all__ = [
    "parse_command", "ParsedCommand",
    "shell_quote", "shell_unquote",
    "ShellProvider", "get_shell_provider",
    "get_command_info", "CommandInfo",
]
