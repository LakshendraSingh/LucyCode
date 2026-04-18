"""
MCP tools — call MCP server tools, manage auth, list/read resources.

Mirrors OpenCode's MCPTool, McpAuthTool, ListMcpResourcesTool, ReadMcpResourceTool.
"""

from __future__ import annotations

from typing import Any

from lucy.core.tool import Tool, ToolContext, ToolResult


class MCPTool(Tool):
    """Dynamically call tools exposed by MCP servers."""

    @property
    def name(self) -> str:
        return "MCPTool"

    @property
    def aliases(self) -> list[str]:
        return ["MCP"]

    @property
    def description(self) -> str:
        return "Call a tool provided by a connected MCP server"

    @property
    def input_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "server_name": {
                    "type": "string",
                    "description": "Name of the MCP server",
                },
                "tool_name": {
                    "type": "string",
                    "description": "Name of the tool to call",
                },
                "arguments": {
                    "type": "object",
                    "description": "Arguments for the tool",
                },
            },
            "required": ["server_name", "tool_name"],
        }

    def get_prompt(self) -> str:
        return (
            "Call a tool provided by a connected MCP (Model Context Protocol) server. "
            "You must specify the server name and tool name. Use ListMcpResources to "
            "discover available servers and tools."
        )

    async def call(self, tool_input: dict[str, Any], context: ToolContext) -> ToolResult:
        from lucy.services.mcp import get_mcp_manager

        server = tool_input.get("server_name", "")
        tool_name = tool_input.get("tool_name", "")
        arguments = tool_input.get("arguments", {})

        if not server or not tool_name:
            return ToolResult(error="server_name and tool_name are required")

        mgr = get_mcp_manager()
        try:
            result = await mgr.call_tool(server, tool_name, arguments)
            return ToolResult(data=result)
        except Exception as e:
            return ToolResult(error=f"MCP tool call failed: {e}")


class McpAuthTool(Tool):
    """Authenticate with an MCP server."""

    @property
    def name(self) -> str:
        return "McpAuth"

    @property
    def description(self) -> str:
        return "Authenticate with an MCP server"

    @property
    def input_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "server_name": {
                    "type": "string",
                    "description": "Name of the MCP server to authenticate with",
                },
                "credentials": {
                    "type": "object",
                    "description": "Authentication credentials",
                },
            },
            "required": ["server_name"],
        }

    def get_prompt(self) -> str:
        return "Authenticate with an MCP server that requires credentials."

    async def call(self, tool_input: dict[str, Any], context: ToolContext) -> ToolResult:
        from lucy.services.mcp import get_mcp_manager

        server = tool_input.get("server_name", "")
        credentials = tool_input.get("credentials", {})

        mgr = get_mcp_manager()
        connections = mgr.get_connections()

        if server not in connections:
            return ToolResult(error=f"MCP server not found: {server}")

        try:
            await mgr.authenticate(server, credentials)
            return ToolResult(data=f"Authenticated with MCP server: {server}")
        except Exception as e:
            return ToolResult(error=f"Authentication failed: {e}")


class ListMcpResourcesTool(Tool):
    """List resources from MCP servers."""

    @property
    def name(self) -> str:
        return "ListMcpResources"

    @property
    def description(self) -> str:
        return "List available resources from connected MCP servers"

    @property
    def input_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "server_name": {
                    "type": "string",
                    "description": "Specific server to list resources from (optional)",
                },
            },
        }

    def get_prompt(self) -> str:
        return (
            "List resources available from connected MCP servers. "
            "Optionally filter by server name."
        )

    def is_read_only(self, tool_input: dict[str, Any]) -> bool:
        return True

    async def call(self, tool_input: dict[str, Any], context: ToolContext) -> ToolResult:
        from lucy.services.mcp import get_mcp_manager

        server_filter = tool_input.get("server_name", "")
        mgr = get_mcp_manager()
        connections = mgr.get_connections()

        if not connections:
            return ToolResult(data="No MCP servers connected.")

        lines = []
        for name, conn in connections.items():
            if server_filter and name != server_filter:
                continue

            status = "connected" if conn.is_connected else "disconnected"
            lines.append(f"\n{name} ({status}):")

            # Tools
            if conn.tools:
                lines.append("  Tools:")
                for t in conn.tools:
                    lines.append(f"    🔧 {t.name}: {t.description[:80]}")

            # Resources
            if hasattr(conn, "resources") and conn.resources:
                lines.append("  Resources:")
                for r in conn.resources:
                    lines.append(f"    📄 {r.get('name', 'unnamed')}: {r.get('uri', '')}")

        if not lines:
            return ToolResult(data=f"MCP server not found: {server_filter}")

        return ToolResult(data="MCP Servers:" + "\n".join(lines))


class ReadMcpResourceTool(Tool):
    """Read a specific MCP resource."""

    @property
    def name(self) -> str:
        return "ReadMcpResource"

    @property
    def description(self) -> str:
        return "Read a specific resource from an MCP server"

    @property
    def input_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "server_name": {
                    "type": "string",
                    "description": "Name of the MCP server",
                },
                "resource_uri": {
                    "type": "string",
                    "description": "URI of the resource to read",
                },
            },
            "required": ["server_name", "resource_uri"],
        }

    def get_prompt(self) -> str:
        return "Read a specific resource from an MCP server by its URI."

    def is_read_only(self, tool_input: dict[str, Any]) -> bool:
        return True

    async def call(self, tool_input: dict[str, Any], context: ToolContext) -> ToolResult:
        from lucy.services.mcp import get_mcp_manager

        server = tool_input.get("server_name", "")
        uri = tool_input.get("resource_uri", "")

        if not server or not uri:
            return ToolResult(error="server_name and resource_uri are required")

        mgr = get_mcp_manager()
        try:
            content = await mgr.read_resource(server, uri)
            return ToolResult(data=content)
        except Exception as e:
            return ToolResult(error=f"Failed to read resource: {e}")
