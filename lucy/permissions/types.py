"""
Permission types and data structures.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class PermissionScope(str, Enum):
    """Scope of a permission rule."""
    GLOBAL = "global"
    PROJECT = "project"
    SESSION = "session"


class PermissionAction(str, Enum):
    """Permission actions."""
    ALLOW = "allow"
    DENY = "deny"
    ASK = "ask"


class PermissionDecision(str, Enum):
    """Final permission decision."""
    ALLOWED = "allowed"
    DENIED = "denied"
    NEEDS_APPROVAL = "needs_approval"


@dataclass
class PermissionRule:
    """A single permission rule."""
    id: str = ""
    tool: str = ""               # Tool name pattern (glob)
    command: str = ""             # Command pattern (glob, for bash)
    path: str = ""               # Path pattern (glob)
    action: PermissionAction = PermissionAction.ASK
    scope: PermissionScope = PermissionScope.PROJECT
    reason: str = ""             # Human-readable reason
    priority: int = 0            # Higher = checked first
    enabled: bool = True

    def matches_tool(self, tool_name: str) -> bool:
        if not self.tool:
            return True
        import fnmatch
        return fnmatch.fnmatch(tool_name, self.tool)

    def matches_command(self, command: str) -> bool:
        if not self.command:
            return True
        import fnmatch
        return fnmatch.fnmatch(command, self.command)

    def matches_path(self, path: str) -> bool:
        if not self.path:
            return True
        import fnmatch
        return fnmatch.fnmatch(path, self.path)


@dataclass
class PermissionCheck:
    """Result of a permission check."""
    decision: PermissionDecision
    rule: PermissionRule | None = None
    explanation: str = ""
    tool_name: str = ""
    command: str = ""
    path: str = ""


@dataclass
class DenialRecord:
    """Record of a denied permission."""
    tool_name: str
    command: str = ""
    path: str = ""
    reason: str = ""
    timestamp: float = 0.0
    auto_denied: bool = False
