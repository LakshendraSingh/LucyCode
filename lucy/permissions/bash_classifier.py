"""
Bash command classifier — determine risk level of shell commands.
"""

from __future__ import annotations

import re
from enum import Enum
from typing import Any

from lucy.permissions.dangerous_patterns import DANGEROUS_PATTERNS, SAFE_COMMANDS


class BashRiskLevel(str, Enum):
    SAFE = "safe"           # Read-only, no side effects
    LOW = "low"             # Minor side effects
    MEDIUM = "medium"       # Moderate side effects, reversible
    HIGH = "high"           # Significant side effects
    CRITICAL = "critical"   # Potentially destructive/irreversible


def classify_bash_command(command: str) -> tuple[BashRiskLevel, str]:
    """Classify a bash command's risk level.

    Returns (risk_level, reason).
    """
    command = command.strip()
    if not command:
        return BashRiskLevel.SAFE, "Empty command"

    # Extract the base command (first word, ignore env vars and redirects)
    base_cmd = _extract_base_command(command)

    # Check dangerous patterns first
    for pattern, reason in DANGEROUS_PATTERNS:
        if re.search(pattern, command, re.IGNORECASE):
            return BashRiskLevel.CRITICAL, reason

    # Check for piped commands — classify each
    if "|" in command:
        parts = command.split("|")
        max_risk = BashRiskLevel.SAFE
        for part in parts:
            risk, reason = classify_bash_command(part.strip())
            if _risk_order(risk) > _risk_order(max_risk):
                max_risk = risk
        return max_risk, "Piped command"

    # Check for command chaining
    for sep in ["&&", "||", ";"]:
        if sep in command:
            parts = command.split(sep)
            max_risk = BashRiskLevel.SAFE
            for part in parts:
                risk, reason = classify_bash_command(part.strip())
                if _risk_order(risk) > _risk_order(max_risk):
                    max_risk = risk
            return max_risk, "Chained command"

    # Safe read-only commands
    if base_cmd in SAFE_COMMANDS:
        return BashRiskLevel.SAFE, f"'{base_cmd}' is read-only"

    # Package managers
    if base_cmd in ("pip", "npm", "yarn", "cargo", "gem", "brew", "apt", "apt-get", "yum", "dnf"):
        if any(w in command for w in ("install", "add", "update", "upgrade", "remove", "uninstall")):
            return BashRiskLevel.HIGH, f"Package manager operation: {base_cmd}"
        return BashRiskLevel.LOW, f"Package manager query: {base_cmd}"

    # Git
    if base_cmd == "git":
        if any(w in command for w in ("push", "reset --hard", "clean -fd", "force")):
            return BashRiskLevel.HIGH, "Destructive git operation"
        if any(w in command for w in ("commit", "merge", "rebase", "checkout", "branch -d")):
            return BashRiskLevel.MEDIUM, "Git state change"
        return BashRiskLevel.SAFE, "Git read operation"

    # File operations
    if base_cmd in ("rm", "rmdir"):
        if "-r" in command or "-f" in command or "--recursive" in command:
            return BashRiskLevel.CRITICAL, "Recursive/force delete"
        return BashRiskLevel.HIGH, "File deletion"

    if base_cmd in ("mv", "rename"):
        return BashRiskLevel.MEDIUM, "File move/rename"

    if base_cmd in ("cp", "rsync"):
        return BashRiskLevel.LOW, "File copy"

    if base_cmd in ("mkdir", "touch"):
        return BashRiskLevel.LOW, "Create file/directory"

    if base_cmd in ("chmod", "chown", "chgrp"):
        return BashRiskLevel.HIGH, "Permission change"

    # Network
    if base_cmd in ("curl", "wget"):
        if any(w in command for w in ("-X POST", "-X PUT", "-X DELETE", "--data", "-d ")):
            return BashRiskLevel.MEDIUM, "HTTP write request"
        return BashRiskLevel.LOW, "HTTP read request"

    if base_cmd in ("ssh", "scp", "sftp"):
        return BashRiskLevel.HIGH, "Remote access"

    # Process management
    if base_cmd in ("kill", "killall", "pkill"):
        return BashRiskLevel.HIGH, "Process termination"

    # Editors/compilers (generally safe to run)
    if base_cmd in ("python", "python3", "node", "ruby", "go", "rustc", "gcc", "make"):
        if any(w in command for w in ("-c ", "-e ")):
            return BashRiskLevel.MEDIUM, "Code execution"
        return BashRiskLevel.MEDIUM, f"Run {base_cmd}"

    # Default: medium (unknown commands need review)
    return BashRiskLevel.MEDIUM, f"Unknown command: {base_cmd}"


def _extract_base_command(command: str) -> str:
    """Extract the actual command from a shell line."""
    cmd = command.strip()

    # Skip env variable assignments
    while "=" in cmd.split()[0] if cmd.split() else False:
        parts = cmd.split(None, 1)
        if len(parts) > 1:
            cmd = parts[1]
        else:
            break

    # Skip sudo, env, nice, etc.
    prefixes = ("sudo", "env", "nice", "nohup", "time", "timeout", "strace", "exec")
    parts = cmd.split()
    while parts and parts[0] in prefixes:
        parts = parts[1:]
        # Skip flags of the prefix
        while parts and parts[0].startswith("-"):
            parts = parts[1:]

    return parts[0] if parts else cmd.split()[0] if cmd.split() else ""


def _risk_order(level: BashRiskLevel) -> int:
    return {"safe": 0, "low": 1, "medium": 2, "high": 3, "critical": 4}.get(level.value, 2)
