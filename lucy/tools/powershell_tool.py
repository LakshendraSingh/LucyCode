"""
PowerShell tool — execute PowerShell commands cross-platform.

Mirrors OpenCode's PowerShellTool.
"""

from __future__ import annotations

import asyncio
import os
import shutil
import subprocess
from typing import Any

from lucy.core.tool import Tool, ToolContext, ToolResult, PermissionBehavior, PermissionResult


class PowerShellTool(Tool):
    @property
    def name(self) -> str:
        return "PowerShell"

    @property
    def aliases(self) -> list[str]:
        return ["pwsh"]

    @property
    def description(self) -> str:
        return "Execute PowerShell commands (requires pwsh or powershell)"

    @property
    def input_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "command": {
                    "type": "string",
                    "description": "PowerShell command to execute",
                },
                "timeout": {
                    "type": "integer",
                    "description": "Timeout in seconds",
                    "default": 120,
                },
            },
            "required": ["command"],
        }

    def get_prompt(self) -> str:
        return (
            "Execute PowerShell commands. Use this on Windows systems or when "
            "PowerShell-specific cmdlets are needed. Requires 'pwsh' (PowerShell Core) "
            "or 'powershell' to be installed."
        )

    def is_enabled(self) -> bool:
        return shutil.which("pwsh") is not None or shutil.which("powershell") is not None

    async def check_permissions(self, tool_input: dict[str, Any], context: ToolContext) -> PermissionResult:
        if context.permission_mode == "auto_accept":
            return PermissionResult(behavior=PermissionBehavior.ALLOW, updated_input=tool_input)
        if context.permission_mode == "plan":
            return PermissionResult(behavior=PermissionBehavior.DENY,
                                    message="PowerShell commands not allowed in plan mode")
        return PermissionResult(behavior=PermissionBehavior.ASK,
                                message=f"Run PowerShell: {tool_input.get('command', '')[:100]}",
                                updated_input=tool_input)

    async def call(self, tool_input: dict[str, Any], context: ToolContext) -> ToolResult:
        command = tool_input.get("command", "")
        timeout = tool_input.get("timeout", 120)

        if not command:
            return ToolResult(error="Command is required")

        # Find PowerShell
        ps = shutil.which("pwsh") or shutil.which("powershell")
        if not ps:
            return ToolResult(error="PowerShell not found. Install PowerShell Core (pwsh).")

        try:
            result = subprocess.run(
                [ps, "-NoProfile", "-NonInteractive", "-Command", command],
                capture_output=True, text=True,
                cwd=context.cwd, timeout=timeout,
                env={**os.environ, "TERM": "dumb"},
            )

            output_parts = []
            if result.stdout:
                output_parts.append(result.stdout)
            if result.stderr:
                output_parts.append(f"STDERR:\n{result.stderr}")

            output = "\n".join(output_parts) or "(no output)"

            if result.returncode != 0:
                return ToolResult(data=f"Exit code: {result.returncode}\n{output}")

            return ToolResult(data=output)

        except subprocess.TimeoutExpired:
            return ToolResult(error=f"Command timed out after {timeout}s")
        except OSError as e:
            return ToolResult(error=f"Failed to run PowerShell: {e}")

    def get_activity_description(self, tool_input: dict[str, Any] | None = None) -> str | None:
        if tool_input:
            return f"Running PS: {tool_input.get('command', '')[:60]}"
        return "Running PowerShell"
