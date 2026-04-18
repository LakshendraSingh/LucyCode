"""
Tool base class and registry.

Every tool in Lucy Code implements the Tool protocol:
  - name, description, input_schema
  - call(input, context) -> ToolResult
  - check_permissions(input, context) -> PermissionResult
  - is_read_only, is_enabled, is_concurrent_safe
"""

from __future__ import annotations

import json
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable


# ---------------------------------------------------------------------------
# Permission result
# ---------------------------------------------------------------------------

class PermissionBehavior(str, Enum):
    ALLOW = "allow"
    DENY = "deny"
    ASK = "ask"


@dataclass
class PermissionResult:
    """Result of a permission check for a tool invocation."""
    behavior: PermissionBehavior
    message: str = ""
    updated_input: dict[str, Any] | None = None


# ---------------------------------------------------------------------------
# Tool result
# ---------------------------------------------------------------------------

@dataclass
class ToolResult:
    """Result of executing a tool."""
    data: Any = None
    error: str | None = None

    @property
    def is_error(self) -> bool:
        return self.error is not None

    def to_content_string(self) -> str:
        """Render the result as a string for the API tool_result block."""
        if self.error:
            return f"Error: {self.error}"
        if isinstance(self.data, str):
            return self.data
        return json.dumps(self.data, indent=2, default=str)


# ---------------------------------------------------------------------------
# Tool context
# ---------------------------------------------------------------------------

@dataclass
class ToolContext:
    """Context passed to tool.call() — provides access to app state and settings."""
    cwd: str = ""
    # Permission mode: 'default' | 'auto_accept' | 'plan'
    permission_mode: str = "default"
    # Whether user interaction is available (False in --print mode)
    is_interactive: bool = True
    # Abort signal
    aborted: bool = False
    # Additional working directories
    additional_dirs: list[str] = field(default_factory=list)
    # Max result size in chars before truncation
    max_result_chars: int = 100_000
    # Callback to ask user for permission
    ask_permission: Callable[[str, str], bool] | None = None


# ---------------------------------------------------------------------------
# Tool base class
# ---------------------------------------------------------------------------

class Tool(ABC):
    """Abstract base class for all tools.

    Subclasses must implement:
      - name (property)
      - description (property)
      - input_schema (property)
      - call(input, context)
      - prompt() — system prompt instructions
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Unique tool name (e.g. 'Bash', 'Read', 'Edit')."""
        ...

    @property
    def aliases(self) -> list[str]:
        """Alternative names for backwards compatibility."""
        return []

    @property
    @abstractmethod
    def description(self) -> str:
        """One-line description for the user."""
        ...

    @property
    @abstractmethod
    def input_schema(self) -> dict[str, Any]:
        """JSON Schema for the tool input (type: 'object')."""
        ...

    @abstractmethod
    async def call(
        self,
        tool_input: dict[str, Any],
        context: ToolContext,
    ) -> ToolResult:
        """Execute the tool and return a result."""
        ...

    @abstractmethod
    def get_prompt(self) -> str:
        """Return the system prompt instructions for this tool."""
        ...

    @property
    def is_core(self) -> bool:
        """Whether this is a core tool (high-priority for all models)."""
        return False

    def is_enabled(self) -> bool:
        """Whether this tool is currently available."""
        return True

    def is_read_only(self, tool_input: dict[str, Any]) -> bool:
        """Whether this invocation only reads (no writes)."""
        return False

    def is_destructive(self, tool_input: dict[str, Any]) -> bool:
        """Whether this invocation is irreversible (delete, overwrite, send)."""
        return False

    def is_concurrent_safe(self, tool_input: dict[str, Any]) -> bool:
        """Whether this tool can run concurrently with others."""
        return False

    async def check_permissions(
        self,
        tool_input: dict[str, Any],
        context: ToolContext,
    ) -> PermissionResult:
        """Check whether the user must approve this invocation.

        Default: allow everything (defer to the general permission system).
        """
        return PermissionResult(
            behavior=PermissionBehavior.ALLOW,
            updated_input=tool_input,
        )

    def user_facing_name(self, tool_input: dict[str, Any] | None = None) -> str:
        """Human-readable name for UI display."""
        return self.name

    def get_tool_use_summary(self, tool_input: dict[str, Any] | None = None) -> str | None:
        """Short summary string for compact views."""
        return None

    def get_activity_description(self, tool_input: dict[str, Any] | None = None) -> str | None:
        """Present-tense description for the spinner (e.g. 'Reading src/foo.py')."""
        return None

    def matches_name(self, name: str) -> bool:
        """Check if this tool matches the given name (primary or alias)."""
        return name == self.name or name in self.aliases

    def to_api_schema(self) -> dict[str, Any]:
        """Convert to the Anthropic API tool schema format."""
        return {
            "name": self.name,
            "description": self.get_prompt(),
            "input_schema": self.input_schema,
        }


# ---------------------------------------------------------------------------
# Tool registry
# ---------------------------------------------------------------------------

class ToolRegistry:
    """Registry of all available tools."""

    def __init__(self) -> None:
        self._tools: list[Tool] = []

    def register(self, tool: Tool) -> None:
        """Register a tool."""
        self._tools.append(tool)

    def get_all(self) -> list[Tool]:
        """Return all registered tools."""
        return list(self._tools)

    def get_enabled(self, core_only: bool = False) -> list[Tool]:
        """Return only enabled tools (optionally filtered by is_core)."""
        tools = [t for t in self._tools if t.is_enabled()]
        if core_only:
            return [t for t in tools if t.is_core]
        return tools

    def find_by_name(self, name: str) -> Tool | None:
        """Find a tool by name or alias."""
        for tool in self._tools:
            if tool.matches_name(name):
                return tool
        return None

    def get_api_schemas(self, core_only: bool = False) -> list[dict[str, Any]]:
        """Return API-formatted tool schemas for enabled tools."""
        return [t.to_api_schema() for t in self.get_enabled(core_only=core_only)]


# Global registry instance
_registry = ToolRegistry()


def register_tool(tool: Tool) -> None:
    """Register a tool in the global registry."""
    _registry.register(tool)


def get_tool_registry() -> ToolRegistry:
    """Get the global tool registry."""
    return _registry


def find_tool_by_name(name: str) -> Tool | None:
    """Find a tool by name in the global registry."""
    return _registry.find_by_name(name)
