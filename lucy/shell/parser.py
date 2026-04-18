"""
Shell command parser — parse bash commands into structured representations.
"""

from __future__ import annotations

import re
import shlex
from dataclasses import dataclass, field
from typing import Any


@dataclass
class ParsedCommand:
    """A parsed shell command."""
    raw: str
    executable: str = ""
    args: list[str] = field(default_factory=list)
    redirects: list[dict[str, str]] = field(default_factory=list)
    pipes: list["ParsedCommand"] = field(default_factory=list)
    background: bool = False
    env_vars: dict[str, str] = field(default_factory=dict)
    is_compound: bool = False          # && || ;
    compound_operator: str = ""
    compound_parts: list["ParsedCommand"] = field(default_factory=list)
    subshells: list[str] = field(default_factory=list)

    @property
    def is_piped(self) -> bool:
        return len(self.pipes) > 0

    @property
    def full_command(self) -> str:
        parts = [self.executable] + self.args
        return " ".join(parts)

    def get_all_executables(self) -> list[str]:
        """Get all executables in the command chain."""
        execs = [self.executable] if self.executable else []
        for p in self.pipes:
            execs.extend(p.get_all_executables())
        for p in self.compound_parts:
            execs.extend(p.get_all_executables())
        return execs


def parse_command(command: str) -> ParsedCommand:
    """Parse a shell command string into a ParsedCommand."""
    command = command.strip()
    result = ParsedCommand(raw=command)

    if not command:
        return result

    # Check for compound commands (&&, ||, ;)
    for op in ["&&", "||", ";"]:
        parts = _split_preserving_quotes(command, op)
        if len(parts) > 1:
            result.is_compound = True
            result.compound_operator = op
            result.compound_parts = [parse_command(p.strip()) for p in parts]
            result.executable = result.compound_parts[0].executable if result.compound_parts else ""
            return result

    # Check for pipes
    pipe_parts = _split_preserving_quotes(command, "|")
    if len(pipe_parts) > 1:
        first = pipe_parts[0].strip()
        result = _parse_simple_command(first)
        result.raw = command
        result.pipes = [_parse_simple_command(p.strip()) for p in pipe_parts[1:]]
        return result

    return _parse_simple_command(command)


def _parse_simple_command(command: str) -> ParsedCommand:
    """Parse a simple (non-compound, non-piped) command."""
    result = ParsedCommand(raw=command)

    # Check for background
    if command.rstrip().endswith("&"):
        result.background = True
        command = command.rstrip()[:-1].rstrip()

    # Check for redirects
    command, redirects = _extract_redirects(command)
    result.redirects = redirects

    # Extract env vars (VAR=val at start)
    while True:
        m = re.match(r'^([A-Za-z_][A-Za-z0-9_]*)=(\S+)\s+', command)
        if m:
            result.env_vars[m.group(1)] = m.group(2)
            command = command[m.end():]
        else:
            break

    # Tokenize
    try:
        tokens = shlex.split(command)
    except ValueError:
        # Fallback for unclosed quotes
        tokens = command.split()

    if tokens:
        # Skip common prefixes
        idx = 0
        prefixes = {"sudo", "env", "nice", "nohup", "time", "timeout", "exec"}
        while idx < len(tokens) and tokens[idx] in prefixes:
            idx += 1
            # Skip flags
            while idx < len(tokens) and tokens[idx].startswith("-"):
                idx += 1

        if idx < len(tokens):
            result.executable = tokens[idx]
            result.args = tokens[idx + 1:]
        elif tokens:
            result.executable = tokens[0]
            result.args = tokens[1:]

    return result


def _split_preserving_quotes(s: str, sep: str) -> list[str]:
    """Split string by separator, preserving quoted sections."""
    parts = []
    current = []
    in_single = False
    in_double = False
    i = 0

    while i < len(s):
        if s[i] == "'" and not in_double:
            in_single = not in_single
            current.append(s[i])
        elif s[i] == '"' and not in_single:
            in_double = not in_double
            current.append(s[i])
        elif s[i:i + len(sep)] == sep and not in_single and not in_double:
            parts.append("".join(current))
            current = []
            i += len(sep)
            continue
        else:
            current.append(s[i])
        i += 1

    parts.append("".join(current))
    return parts


def _extract_redirects(command: str) -> tuple[str, list[dict[str, str]]]:
    """Extract redirect operators from a command."""
    redirects = []
    # Patterns: 2>&1, >file, >>file, <file, 2>file
    patterns = [
        (r'(\d?)>>(\S+)', 'append'),
        (r'(\d?)>(\S+)', 'write'),
        (r'(\d?)<(\S+)', 'read'),
        (r'(\d?)>&(\d+)', 'dup'),
    ]

    clean = command
    for pattern, rtype in patterns:
        for m in re.finditer(pattern, clean):
            redirects.append({
                "type": rtype,
                "fd": m.group(1) or ("1" if rtype != "read" else "0"),
                "target": m.group(2),
            })
        clean = re.sub(pattern, "", clean)

    return clean.strip(), redirects
