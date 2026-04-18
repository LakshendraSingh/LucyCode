"""
MCP (Model Context Protocol) server support.

Manages MCP server connections that provide additional tools and resources
to the model. MCP servers communicate via stdio or SSE transport.

Based on the Model Context Protocol specification:
  https://spec.modelcontextprotocol.io/
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import uuid
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

from lucy.core.config import get_config
from lucy.core.tool import Tool, ToolContext, ToolResult

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# MCP Server config
# ---------------------------------------------------------------------------

class MCPTransport(str, Enum):
    STDIO = "stdio"
    SSE = "sse"


@dataclass
class MCPServerConfig:
    """Configuration for an MCP server."""
    name: str
    command: str = ""             # For stdio transport
    args: list[str] = field(default_factory=list)
    env: dict[str, str] = field(default_factory=dict)
    url: str = ""                  # For SSE transport
    transport: MCPTransport = MCPTransport.STDIO
    enabled: bool = True
    timeout: int = 30             # Connection timeout in seconds


@dataclass
class MCPTool:
    """A tool provided by an MCP server."""
    name: str
    description: str = ""
    input_schema: dict[str, Any] = field(default_factory=dict)
    server_name: str = ""


@dataclass
class MCPResource:
    """A resource provided by an MCP server."""
    uri: str
    name: str = ""
    description: str = ""
    mime_type: str = ""
    server_name: str = ""


# ---------------------------------------------------------------------------
# MCP Connection
# ---------------------------------------------------------------------------

class MCPConnection:
    """A connection to an MCP server via stdio transport."""

    def __init__(self, config: MCPServerConfig) -> None:
        self.config = config
        self._process: asyncio.subprocess.Process | None = None
        self._request_id = 0
        self._pending: dict[int, asyncio.Future] = {}
        self._tools: list[MCPTool] = []
        self._resources: list[MCPResource] = []
        self._connected = False
        self._read_task: asyncio.Task | None = None

    @property
    def is_connected(self) -> bool:
        return self._connected

    async def connect(self) -> bool:
        """Start the MCP server process and initialize the connection."""
        if self._connected:
            return True

        try:
            env = {**os.environ, **self.config.env}
            self._process = await asyncio.create_subprocess_exec(
                self.config.command,
                *self.config.args,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=env,
            )

            # Start reading responses
            self._read_task = asyncio.create_task(self._read_loop())

            # Initialize
            result = await self._send_request("initialize", {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "lucy", "version": "0.1.0"},
            })

            if result is None:
                logger.warning("MCP server %s: initialization failed", self.config.name)
                await self.disconnect()
                return False

            # Send initialized notification
            await self._send_notification("notifications/initialized", {})

            # Discover tools
            tools_result = await self._send_request("tools/list", {})
            if tools_result and "tools" in tools_result:
                for t in tools_result["tools"]:
                    self._tools.append(MCPTool(
                        name=t.get("name", ""),
                        description=t.get("description", ""),
                        input_schema=t.get("inputSchema", {}),
                        server_name=self.config.name,
                    ))

            # Discover resources
            try:
                res_result = await self._send_request("resources/list", {})
                if res_result and "resources" in res_result:
                    for r in res_result["resources"]:
                        self._resources.append(MCPResource(
                            uri=r.get("uri", ""),
                            name=r.get("name", ""),
                            description=r.get("description", ""),
                            mime_type=r.get("mimeType", ""),
                            server_name=self.config.name,
                        ))
            except Exception:
                pass  # Resources are optional

            self._connected = True
            logger.info(
                "MCP server %s connected (%d tools, %d resources)",
                self.config.name, len(self._tools), len(self._resources),
            )
            return True

        except Exception as e:
            logger.warning("Failed to connect MCP server %s: %s", self.config.name, e)
            await self.disconnect()
            return False

    async def disconnect(self) -> None:
        """Disconnect from the MCP server."""
        self._connected = False
        if self._read_task and not self._read_task.done():
            self._read_task.cancel()
            try:
                await self._read_task
            except asyncio.CancelledError:
                pass
        if self._process:
            try:
                self._process.terminate()
                await asyncio.wait_for(self._process.wait(), timeout=5)
            except (asyncio.TimeoutError, ProcessLookupError):
                self._process.kill()
            self._process = None
        # Clear pending futures
        for fut in self._pending.values():
            if not fut.done():
                fut.set_exception(ConnectionError("Server disconnected"))
        self._pending.clear()

    async def call_tool(self, name: str, arguments: dict[str, Any]) -> Any:
        """Call a tool on the MCP server."""
        result = await self._send_request("tools/call", {
            "name": name,
            "arguments": arguments,
        })
        return result

    @property
    def tools(self) -> list[MCPTool]:
        return list(self._tools)

    @property
    def resources(self) -> list[MCPResource]:
        return list(self._resources)

    async def _send_request(self, method: str, params: dict[str, Any]) -> Any:
        """Send a JSON-RPC request and wait for the response."""
        if not self._process or not self._process.stdin:
            raise ConnectionError("Not connected")

        self._request_id += 1
        req_id = self._request_id

        message = {
            "jsonrpc": "2.0",
            "id": req_id,
            "method": method,
            "params": params,
        }

        line = json.dumps(message) + "\n"
        self._process.stdin.write(line.encode("utf-8"))
        await self._process.stdin.drain()

        # Wait for response
        future: asyncio.Future = asyncio.get_event_loop().create_future()
        self._pending[req_id] = future

        try:
            result = await asyncio.wait_for(future, timeout=self.config.timeout)
            return result
        except asyncio.TimeoutError:
            self._pending.pop(req_id, None)
            raise TimeoutError(f"MCP request timed out: {method}")

    async def _send_notification(self, method: str, params: dict[str, Any]) -> None:
        """Send a JSON-RPC notification (no response expected)."""
        if not self._process or not self._process.stdin:
            return

        message = {
            "jsonrpc": "2.0",
            "method": method,
            "params": params,
        }

        line = json.dumps(message) + "\n"
        self._process.stdin.write(line.encode("utf-8"))
        await self._process.stdin.drain()

    async def _read_loop(self) -> None:
        """Read JSON-RPC responses from the server."""
        if not self._process or not self._process.stdout:
            return

        try:
            while True:
                line = await self._process.stdout.readline()
                if not line:
                    break

                try:
                    msg = json.loads(line)
                except json.JSONDecodeError:
                    continue

                # Handle response
                if "id" in msg and msg["id"] in self._pending:
                    future = self._pending.pop(msg["id"])
                    if "error" in msg:
                        future.set_exception(
                            Exception(f"MCP error: {msg['error'].get('message', 'Unknown')}")
                        )
                    else:
                        future.set_result(msg.get("result"))

                # Handle notification (from server)
                elif "method" in msg and "id" not in msg:
                    logger.debug("MCP notification: %s", msg.get("method"))

        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.warning("MCP read loop error: %s", e)


# ---------------------------------------------------------------------------
# MCP Tool adapter
# ---------------------------------------------------------------------------

class MCPToolAdapter(Tool):
    """Wraps an MCP tool as an Lucy Code Tool."""

    def __init__(self, mcp_tool: MCPTool, connection: MCPConnection) -> None:
        self._mcp_tool = mcp_tool
        self._connection = connection

    @property
    def name(self) -> str:
        return f"mcp__{self._mcp_tool.server_name}__{self._mcp_tool.name}"

    @property
    def description(self) -> str:
        return self._mcp_tool.description or f"MCP tool: {self._mcp_tool.name}"

    @property
    def input_schema(self) -> dict[str, Any]:
        return self._mcp_tool.input_schema or {"type": "object", "properties": {}}

    def get_prompt(self) -> str:
        return self._mcp_tool.description or f"Tool from MCP server {self._mcp_tool.server_name}"

    def user_facing_name(self, tool_input: dict[str, Any] | None = None) -> str:
        return f"{self._mcp_tool.server_name}:{self._mcp_tool.name}"

    async def call(self, tool_input: dict[str, Any], context: ToolContext) -> ToolResult:
        try:
            result = await self._connection.call_tool(self._mcp_tool.name, tool_input)
            if result is None:
                return ToolResult(data="(no output)")

            # MCP tool results contain a "content" array
            if isinstance(result, dict) and "content" in result:
                parts = []
                for block in result["content"]:
                    if block.get("type") == "text":
                        parts.append(block.get("text", ""))
                    elif block.get("type") == "image":
                        parts.append(f"[image: {block.get('mimeType', 'unknown')}]")
                return ToolResult(data="\n".join(parts) if parts else "(no output)")

            return ToolResult(data=json.dumps(result, indent=2, default=str))

        except Exception as e:
            return ToolResult(error=f"MCP tool error: {e}")


# ---------------------------------------------------------------------------
# MCP Manager
# ---------------------------------------------------------------------------

class MCPManager:
    """Manages MCP server connections and their tools."""

    def __init__(self) -> None:
        self._connections: dict[str, MCPConnection] = {}
        self._tool_adapters: list[MCPToolAdapter] = []

    async def connect_server(self, config: MCPServerConfig) -> bool:
        """Connect to an MCP server."""
        if config.name in self._connections:
            if self._connections[config.name].is_connected:
                return True

        conn = MCPConnection(config)
        success = await conn.connect()
        if success:
            self._connections[config.name] = conn
            # Create tool adapters
            for mcp_tool in conn.tools:
                adapter = MCPToolAdapter(mcp_tool, conn)
                self._tool_adapters.append(adapter)
        return success

    async def disconnect_server(self, name: str) -> None:
        """Disconnect from an MCP server."""
        if name in self._connections:
            await self._connections[name].disconnect()
            # Remove adapters
            self._tool_adapters = [
                a for a in self._tool_adapters
                if a._mcp_tool.server_name != name
            ]
            del self._connections[name]

    async def disconnect_all(self) -> None:
        """Disconnect from all MCP servers."""
        for name in list(self._connections.keys()):
            await self.disconnect_server(name)

    def get_tools(self) -> list[MCPToolAdapter]:
        """Get all tools from connected MCP servers."""
        return list(self._tool_adapters)

    def get_connections(self) -> dict[str, MCPConnection]:
        return dict(self._connections)

    async def connect_from_config(self) -> None:
        """Connect to all MCP servers defined in the config."""
        config_path = Path.home() / ".lucy" / "mcp.json"
        if not config_path.exists():
            return

        try:
            with open(config_path) as f:
                config_data = json.load(f)
        except (json.JSONDecodeError, OSError) as e:
            logger.warning("Failed to load MCP config: %s", e)
            return

        servers = config_data.get("mcpServers", config_data.get("servers", {}))
        for name, server_config in servers.items():
            mcp_config = MCPServerConfig(
                name=name,
                command=server_config.get("command", ""),
                args=server_config.get("args", []),
                env=server_config.get("env", {}),
                url=server_config.get("url", ""),
                transport=MCPTransport(server_config.get("transport", "stdio")),
                timeout=server_config.get("timeout", 30),
            )
            if mcp_config.command or mcp_config.url:
                success = await self.connect_server(mcp_config)
                if success:
                    logger.info("Connected to MCP server: %s", name)
                else:
                    logger.warning("Failed to connect MCP server: %s", name)


# Global singleton
_mcp_manager: MCPManager | None = None


def get_mcp_manager() -> MCPManager:
    global _mcp_manager
    if _mcp_manager is None:
        _mcp_manager = MCPManager()
    return _mcp_manager
