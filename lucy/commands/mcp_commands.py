"""
MCP commands — /mcp.
"""

from __future__ import annotations

from typing import Any

from lucy.core.commands import Command, CommandResult


class McpCommand(Command):
    @property
    def name(self) -> str: return "mcp"
    @property
    def description(self) -> str: return "Manage MCP server connections"
    @property
    def usage(self) -> str: return "/mcp [list|connect|disconnect|status] [server]"

    async def execute(self, args: str, state: Any) -> CommandResult:
        from lucy.services.mcp import get_mcp_manager
        mgr = get_mcp_manager()

        parts = args.strip().split(None, 1)
        action = parts[0] if parts else "list"
        target = parts[1].strip() if len(parts) > 1 else ""

        if action == "list" or action == "status":
            connections = mgr.get_connections()
            if not connections:
                return CommandResult(output="No MCP servers configured.\n"
                                           "Add servers in ~/.lucycode/config.json under 'mcp_servers'")
            lines = ["MCP Servers:\n"]
            for name, conn in connections.items():
                status = "🟢 connected" if conn.is_connected else "🔴 disconnected"
                lines.append(f"  {name}: {status}")
                if conn.tools:
                    lines.append(f"    Tools: {', '.join(t.name for t in conn.tools)}")
            return CommandResult(output="\n".join(lines))

        if action == "connect":
            if not target:
                return CommandResult(error="Usage: /mcp connect <server>")
            try:
                await mgr.connect(target)
                return CommandResult(output=f"Connected to: {target}")
            except Exception as e:
                return CommandResult(error=f"Connection failed: {e}")

        if action == "disconnect":
            if not target:
                return CommandResult(error="Usage: /mcp disconnect <server>")
            try:
                await mgr.disconnect(target)
                return CommandResult(output=f"Disconnected: {target}")
            except Exception as e:
                return CommandResult(error=f"Disconnect failed: {e}")

        return CommandResult(error=f"Unknown action: {action}")


def get_commands() -> list[Command]:
    return [McpCommand()]
