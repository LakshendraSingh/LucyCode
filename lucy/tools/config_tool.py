"""
Config tool — programmatically modify settings.

Mirrors OpenCode's ConfigTool.
"""

from __future__ import annotations

from typing import Any

from lucy.core.tool import Tool, ToolContext, ToolResult


class ConfigTool(Tool):
    @property
    def name(self) -> str:
        return "Config"

    @property
    def aliases(self) -> list[str]:
        return ["Settings"]

    @property
    def description(self) -> str:
        return "Read or modify Lucy Code configuration settings"

    @property
    def input_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["get", "set", "list"],
                    "description": "Action to perform",
                },
                "key": {
                    "type": "string",
                    "description": "Config key to get/set",
                },
                "value": {
                    "type": "string",
                    "description": "Value to set",
                },
            },
            "required": ["action"],
        }

    def get_prompt(self) -> str:
        return (
            "Read or modify Lucy Code configuration. Actions:\n"
            "- 'list': Show all current settings\n"
            "- 'get': Get a specific setting value\n"
            "- 'set': Change a setting value\n"
            "Available keys: model, theme, permission_mode, thinking_enabled, "
            "show_cost, verbose, max_tokens, max_thinking_tokens."
        )

    def is_read_only(self, tool_input: dict[str, Any]) -> bool:
        return tool_input.get("action") != "set"

    async def call(self, tool_input: dict[str, Any], context: ToolContext) -> ToolResult:
        from lucy.core.config import get_config, save_config

        action = tool_input.get("action", "list")
        key = tool_input.get("key", "")
        value = tool_input.get("value", "")

        config = get_config()

        if action == "list":
            settings = {
                "model": config.model,
                "theme": config.theme,
                "permission_mode": config.permission_mode,
                "thinking_enabled": config.thinking_enabled,
                "show_cost": config.show_cost,
                "verbose": config.verbose,
                "max_tokens": config.max_tokens,
                "max_thinking_tokens": config.max_thinking_tokens,
                "timeout": config.timeout,
                "base_url": config.base_url,
            }
            lines = ["Current settings:"]
            for k, v in settings.items():
                lines.append(f"  {k}: {v}")
            return ToolResult(data="\n".join(lines))

        if action == "get":
            if not key:
                return ToolResult(error="Key is required for 'get' action")
            if hasattr(config, key):
                return ToolResult(data=f"{key} = {getattr(config, key)}")
            return ToolResult(error=f"Unknown config key: {key}")

        if action == "set":
            if not key or not value:
                return ToolResult(error="Key and value are required for 'set' action")

            allowed = {
                "model", "theme", "permission_mode", "verbose",
                "thinking_enabled", "show_cost", "max_tokens",
                "max_thinking_tokens", "timeout",
            }
            if key not in allowed:
                return ToolResult(error=f"Cannot set '{key}'. Allowed: {', '.join(sorted(allowed))}")

            # Type coercion
            current = getattr(config, key, None)
            if isinstance(current, bool):
                value = value.lower() in ("true", "1", "yes", "on")
            elif isinstance(current, int):
                try:
                    value = int(value)
                except ValueError:
                    return ToolResult(error=f"Invalid integer value: {value}")

            setattr(config, key, value)
            save_config(config)
            return ToolResult(data=f"Set {key} = {value}")

        return ToolResult(error=f"Unknown action: {action}")
