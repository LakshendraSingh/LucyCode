"""
MCP (Model Context Protocol) server support and hosting.

Provides:
  - Client connections: Stdio, SSE (HTTP Server-Sent Events), and Streamable HTTP transports
  - Server hosting: Host Lucy's tools as an MCP server (MCPServerHost)
  - OAuth2 authentication with automatic token refresh (MCPOAuth2)
  - Reconnection resilience and comprehensive resource management
  - Compatibility with MCP specification: https://spec.modelcontextprotocol.io/
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import sys
import time
import urllib.parse
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

try:
    import aiohttp
except ImportError:
    aiohttp = None  # type: ignore[assignment]

from lucy.core.tool import Tool, ToolContext, ToolRegistry, ToolResult, get_tool_registry

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# MCP Server config & Transports
# ---------------------------------------------------------------------------

class MCPTransport(str, Enum):
    """Supported MCP transports."""
    STDIO = "stdio"
    SSE = "sse"
    STREAMABLE_HTTP = "streamable-http"

    @classmethod
    def from_string(cls, val: str) -> MCPTransport:
        """Parse transport string flexibly."""
        val_lower = val.lower().replace("_", "-")
        if val_lower in ("streamable-http", "streamablehttp", "http"):
            return cls.STREAMABLE_HTTP
        if val_lower == "sse":
            return cls.SSE
        return cls.STDIO


@dataclass
class MCPAuthConfig:
    """Configuration for MCP authentication (OAuth2 / Bearer / API Key)."""
    type: str = "oauth2"  # "oauth2", "bearer", "api_key"
    client_id: str = ""
    client_secret: str = ""
    auth_url: str = ""
    token_url: str = ""
    refresh_token: str = ""
    access_token: str = ""
    expires_at: float = 0.0
    scopes: list[str] = field(default_factory=list)
    token_file: str = ""


@dataclass
class MCPServerConfig:
    """Configuration for an MCP server."""
    name: str
    command: str = ""             # For stdio transport
    args: list[str] = field(default_factory=list)
    env: dict[str, str] = field(default_factory=dict)
    url: str = ""                  # For SSE or Streamable HTTP transport
    transport: MCPTransport = MCPTransport.STDIO
    auth: MCPAuthConfig | None = None
    enabled: bool = True
    timeout: int = 30             # Request/connection timeout in seconds
    max_reconnect_attempts: int = 3
    reconnect_delay: float = 1.0


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
# OAuth2 Authentication Flow
# ---------------------------------------------------------------------------

class MCPOAuth2:
    """OAuth2 flow for MCP server authentication with automatic token refresh."""

    def __init__(self, token_storage_path: Path | None = None) -> None:
        self._token_file = token_storage_path or (Path.home() / ".lucy" / "mcp_tokens.json")
        self._tokens: dict[str, dict[str, Any]] = {}
        self._load_tokens()

    def _load_tokens(self) -> None:
        """Load stored tokens from disk."""
        if not self._token_file.exists():
            return
        try:
            with open(self._token_file, "r", encoding="utf-8") as f:
                self._tokens = json.load(f)
        except Exception as e:
            logger.warning("Failed to load MCP tokens from %s: %s", self._token_file, e)

    def _save_tokens(self) -> None:
        """Persist tokens to disk."""
        try:
            self._token_file.parent.mkdir(parents=True, exist_ok=True)
            with open(self._token_file, "w", encoding="utf-8") as f:
                json.dump(self._tokens, f, indent=2)
        except Exception as e:
            logger.warning("Failed to save MCP tokens to %s: %s", self._token_file, e)

    async def authenticate(self, config: MCPAuthConfig, server_name: str = "") -> str:
        """Run OAuth2 authentication or retrieve cached valid access token."""
        server_key = server_name or config.client_id or "default"
        now = time.time()

        # 1. Check in-memory / persisted token cache
        cached = self._tokens.get(server_key, {})
        access_token = cached.get("access_token") or config.access_token
        refresh_token = cached.get("refresh_token") or config.refresh_token
        expires_at = cached.get("expires_at") or config.expires_at

        # 2. Check if token is still valid (with 60-second safety window)
        if access_token and (expires_at == 0.0 or expires_at > now + 60):
            return access_token

        # 3. Attempt token refresh if refresh_token and token_url exist
        if refresh_token and config.token_url:
            try:
                new_token = await self.refresh_token(config, refresh_token, server_key)
                return new_token
            except Exception as e:
                logger.warning("Token refresh failed for MCP server '%s': %s", server_key, e)

        # 4. Attempt Client Credentials grant if client_secret is provided
        if config.client_id and config.client_secret and config.token_url:
            try:
                new_token = await self._client_credentials_flow(config, server_key)
                return new_token
            except Exception as e:
                logger.warning("Client credentials grant failed for MCP server '%s': %s", server_key, e)

        # If static access token is present, return it as fallback
        if access_token:
            return access_token

        raise PermissionError(
            f"No valid OAuth2 token available for MCP server '{server_key}'. "
            "Configure client_id, client_secret, or refresh_token."
        )

    async def refresh_token(self, config: MCPAuthConfig, refresh_token: str, server_key: str) -> str:
        """Refresh an expired access token using the refresh token."""
        data = {
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
        }
        if config.client_id:
            data["client_id"] = config.client_id
        if config.client_secret:
            data["client_secret"] = config.client_secret

        if aiohttp is None:
            raise ImportError("aiohttp is required for OAuth2 token requests. Install with: pip install aiohttp")

        async with aiohttp.ClientSession() as session:
            async with session.post(config.token_url, data=data, timeout=aiohttp.ClientTimeout(total=15)) as resp:
                if resp.status != 200:
                    text = await resp.text()
                    raise RuntimeError(f"Token refresh error HTTP {resp.status}: {text}")
                payload = await resp.json()

        access_token = payload["access_token"]
        expires_in = payload.get("expires_in", 3600)
        new_refresh = payload.get("refresh_token", refresh_token)
        expires_at = time.time() + float(expires_in)

        # Update cache & config
        self._tokens[server_key] = {
            "access_token": access_token,
            "refresh_token": new_refresh,
            "expires_at": expires_at,
        }
        config.access_token = access_token
        config.refresh_token = new_refresh
        config.expires_at = expires_at
        self._save_tokens()
        return access_token

    async def _client_credentials_flow(self, config: MCPAuthConfig, server_key: str) -> str:
        """Obtain a token using the Client Credentials grant."""
        data = {
            "grant_type": "client_credentials",
            "client_id": config.client_id,
            "client_secret": config.client_secret,
        }
        if config.scopes:
            data["scope"] = " ".join(config.scopes)

        if aiohttp is None:
            raise ImportError("aiohttp is required for OAuth2 token requests. Install with: pip install aiohttp")

        async with aiohttp.ClientSession() as session:
            async with session.post(config.token_url, data=data, timeout=aiohttp.ClientTimeout(total=15)) as resp:
                if resp.status != 200:
                    text = await resp.text()
                    raise RuntimeError(f"Client credentials error HTTP {resp.status}: {text}")
                payload = await resp.json()

        access_token = payload["access_token"]
        expires_in = payload.get("expires_in", 3600)
        expires_at = time.time() + float(expires_in)

        self._tokens[server_key] = {
            "access_token": access_token,
            "refresh_token": payload.get("refresh_token", ""),
            "expires_at": expires_at,
        }
        config.access_token = access_token
        config.expires_at = expires_at
        self._save_tokens()
        return access_token


# ---------------------------------------------------------------------------
# MCP Connection: Stdio Transport
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
                "clientInfo": {"name": "lucy", "version": "0.3.0"},
            })

            if result is None:
                logger.warning("MCP server %s: initialization failed", self.config.name)
                await self.disconnect()
                return False

            # Send initialized notification
            await self._send_notification("notifications/initialized", {})

            # Discover tools
            self._tools.clear()
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
            self._resources.clear()
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
                "MCP server %s connected via stdio (%d tools, %d resources)",
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
        if not self._connected:
            raise ConnectionError(f"Server {self.config.name} not connected")
        result = await self._send_request("tools/call", {
            "name": name,
            "arguments": arguments,
        })
        return result

    async def read_resource(self, uri: str) -> Any:
        """Read a resource from the MCP server."""
        if not self._connected:
            raise ConnectionError(f"Server {self.config.name} not connected")
        result = await self._send_request("resources/read", {"uri": uri})
        return result

    async def authenticate(self, credentials: dict[str, Any]) -> bool:
        """Authenticate with stdio server (if server implements custom auth method)."""
        res = await self._send_request("auth/login", credentials)
        return bool(res)

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
        loop = asyncio.get_running_loop()
        future: asyncio.Future = loop.create_future()
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
# MCP Connection: SSE Transport (Server-Sent Events)
# ---------------------------------------------------------------------------

class MCPSSEConnection:
    """MCP connection via Server-Sent Events (HTTP)."""

    def __init__(self, config: MCPServerConfig) -> None:
        self.config = config
        self._session: aiohttp.ClientSession | None = None
        self._post_url: str = ""
        self._connected = False
        self._tools: list[MCPTool] = []
        self._resources: list[MCPResource] = []
        self._request_id = 0
        self._pending: dict[int, asyncio.Future] = {}
        self._sse_task: asyncio.Task | None = None
        self._auth_manager = MCPOAuth2()
        self._access_token: str = ""
        self._endpoint_event_received = asyncio.Event()

    @property
    def is_connected(self) -> bool:
        return self._connected

    @property
    def tools(self) -> list[MCPTool]:
        return list(self._tools)

    @property
    def resources(self) -> list[MCPResource]:
        return list(self._resources)

    def _get_headers(self) -> dict[str, str]:
        """Prepare HTTP headers, injecting OAuth2 token if configured."""
        headers = {
            "Accept": "text/event-stream, application/json",
            "User-Agent": "lucy-code/0.3.0",
        }
        if self._access_token:
            headers["Authorization"] = f"Bearer {self._access_token}"
        return headers

    async def connect(self) -> bool:
        """Connect to SSE endpoint, send initialize, discover tools."""
        if self._connected:
            return True

        if aiohttp is None:
            raise ImportError("aiohttp is required for MCP SSE transport. Install with: pip install aiohttp")

        try:
            # Handle authentication if configured
            if self.config.auth:
                try:
                    self._access_token = await self._auth_manager.authenticate(
                        self.config.auth, self.config.name
                    )
                except Exception as e:
                    logger.warning("MCP SSE auth failed for %s: %s", self.config.name, e)

            # Create persistent aiohttp session
            timeout = aiohttp.ClientTimeout(total=None, sock_connect=10, sock_read=None)
            self._session = aiohttp.ClientSession(timeout=timeout)

            # Start SSE listener task
            self._endpoint_event_received.clear()
            self._sse_task = asyncio.create_task(self._listen_sse())

            # Wait for endpoint discovery event from the SSE stream
            try:
                await asyncio.wait_for(
                    self._endpoint_event_received.wait(),
                    timeout=min(float(self.config.timeout), 10.0),
                )
            except asyncio.TimeoutError:
                # If server doesn't emit 'endpoint' event, default POST endpoint to url
                if not self._post_url:
                    self._post_url = self.config.url

            # Handshake: initialize
            init_res = await self._send_request("initialize", {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "lucy", "version": "0.3.0"},
            })

            if init_res is None:
                logger.warning("MCP SSE server %s: initialization rejected", self.config.name)
                await self.disconnect()
                return False

            # Send initialized notification
            await self._send_notification("notifications/initialized", {})

            # Discover tools
            self._tools.clear()
            tools_res = await self._send_request("tools/list", {})
            if tools_res and "tools" in tools_res:
                for t in tools_res["tools"]:
                    self._tools.append(MCPTool(
                        name=t.get("name", ""),
                        description=t.get("description", ""),
                        input_schema=t.get("inputSchema", {}),
                        server_name=self.config.name,
                    ))

            # Discover resources
            self._resources.clear()
            try:
                res_res = await self._send_request("resources/list", {})
                if res_res and "resources" in res_res:
                    for r in res_res["resources"]:
                        self._resources.append(MCPResource(
                            uri=r.get("uri", ""),
                            name=r.get("name", ""),
                            description=r.get("description", ""),
                            mime_type=r.get("mimeType", ""),
                            server_name=self.config.name,
                        ))
            except Exception:
                pass

            self._connected = True
            logger.info(
                "MCP server %s connected via SSE (%d tools, %d resources)",
                self.config.name, len(self._tools), len(self._resources),
            )
            return True

        except Exception as e:
            logger.warning("Failed to connect to MCP SSE server %s: %s", self.config.name, e)
            await self.disconnect()
            return False

    async def disconnect(self) -> None:
        """Disconnect and cleanup session."""
        self._connected = False
        if self._sse_task and not self._sse_task.done():
            self._sse_task.cancel()
            try:
                await self._sse_task
            except asyncio.CancelledError:
                pass
        if self._session and not self._session.closed:
            await self._session.close()
            self._session = None
        for fut in self._pending.values():
            if not fut.done():
                fut.set_exception(ConnectionError("Server disconnected"))
        self._pending.clear()

    async def call_tool(self, name: str, arguments: dict[str, Any]) -> Any:
        """Call tool via HTTP POST."""
        if not self._connected:
            raise ConnectionError(f"Server {self.config.name} is not connected")
        return await self._send_request("tools/call", {
            "name": name,
            "arguments": arguments,
        })

    async def read_resource(self, uri: str) -> Any:
        """Read resource via HTTP POST."""
        if not self._connected:
            raise ConnectionError(f"Server {self.config.name} is not connected")
        return await self._send_request("resources/read", {"uri": uri})

    async def authenticate(self, credentials: dict[str, Any]) -> bool:
        """Authenticate or update credentials."""
        if self.config.auth:
            self._access_token = await self._auth_manager.authenticate(
                self.config.auth, self.config.name
            )
            return True
        return False

    async def _send_request(self, method: str, params: dict[str, Any]) -> Any:
        """Send JSON-RPC request to the POST endpoint."""
        if not self._session or self._session.closed:
            raise ConnectionError("No active HTTP session")

        target_url = self._post_url or self.config.url
        self._request_id += 1
        req_id = self._request_id

        payload = {
            "jsonrpc": "2.0",
            "id": req_id,
            "method": method,
            "params": params,
        }

        loop = asyncio.get_running_loop()
        future: asyncio.Future = loop.create_future()
        self._pending[req_id] = future

        headers = self._get_headers()
        headers["Content-Type"] = "application/json"

        try:
            async with self._session.post(
                target_url,
                json=payload,
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=self.config.timeout),
            ) as resp:
                # Handle 401 Unauthorized by refreshing token and retrying once
                if resp.status == 401 and self.config.auth:
                    self._access_token = await self._auth_manager.refresh_token(
                        self.config.auth, self.config.auth.refresh_token, self.config.name
                    )
                    headers["Authorization"] = f"Bearer {self._access_token}"
                    async with self._session.post(
                        target_url,
                        json=payload,
                        headers=headers,
                        timeout=aiohttp.ClientTimeout(total=self.config.timeout),
                    ) as retry_resp:
                        resp = retry_resp

                if resp.status not in (200, 202):
                    err_text = await resp.text()
                    self._pending.pop(req_id, None)
                    raise RuntimeError(f"HTTP {resp.status} from MCP server: {err_text}")

                # If server returns the response directly in POST body instead of SSE stream
                content_type = resp.headers.get("Content-Type", "")
                if "application/json" in content_type:
                    body = await resp.json()
                    if isinstance(body, dict) and "id" in body:
                        self._pending.pop(req_id, None)
                        if "error" in body:
                            raise RuntimeError(f"MCP error: {body['error'].get('message', 'Unknown')}")
                        return body.get("result")

            # Otherwise, wait for SSE event stream to resolve future
            result = await asyncio.wait_for(future, timeout=self.config.timeout)
            return result

        except asyncio.TimeoutError:
            self._pending.pop(req_id, None)
            raise TimeoutError(f"MCP SSE request timed out: {method}")
        except Exception:
            self._pending.pop(req_id, None)
            raise

    async def _send_notification(self, method: str, params: dict[str, Any]) -> None:
        """Send JSON-RPC notification."""
        if not self._session or self._session.closed:
            return
        target_url = self._post_url or self.config.url
        headers = self._get_headers()
        headers["Content-Type"] = "application/json"
        payload = {
            "jsonrpc": "2.0",
            "method": method,
            "params": params,
        }
        try:
            await self._session.post(
                target_url,
                json=payload,
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=10),
            )
        except Exception as e:
            logger.debug("Failed to send notification %s: %s", method, e)

    async def _listen_sse(self) -> None:
        """Listen for SSE events from the server."""
        if not self._session or self._session.closed:
            return

        headers = self._get_headers()
        try:
            async with self._session.get(self.config.url, headers=headers) as resp:
                if resp.status != 200:
                    logger.warning("SSE connection to %s failed: HTTP %s", self.config.url, resp.status)
                    return

                event_name = "message"
                data_lines: list[str] = []

                async for raw_line in resp.content:
                    line = raw_line.decode("utf-8", errors="replace").rstrip("\r\n")

                    if not line:
                        # Empty line denotes end of an SSE message
                        if data_lines:
                            full_data = "\n".join(data_lines)
                            await self._handle_sse_event(event_name, full_data)
                            data_lines = []
                            event_name = "message"
                        continue

                    if line.startswith(":"):
                        continue  # SSE comment / keepalive

                    if ":" in line:
                        field_name, field_value = line.split(":", 1)
                        field_value = field_value.lstrip(" ")

                        if field_name == "event":
                            event_name = field_value
                        elif field_name == "data":
                            data_lines.append(field_value)

        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.warning("MCP SSE connection dropped for %s: %s", self.config.name, e)
            self._connected = False

    async def _handle_sse_event(self, event_name: str, data: str) -> None:
        """Process a parsed SSE event."""
        # 1. Endpoint discovery event: contains the relative or absolute POST URL
        if event_name == "endpoint":
            endpoint = data.strip()
            self._post_url = urllib.parse.urljoin(self.config.url, endpoint)
            logger.debug("MCP SSE endpoint discovered: %s", self._post_url)
            self._endpoint_event_received.set()
            return

        # 2. JSON-RPC message event
        try:
            msg = json.loads(data)
        except json.JSONDecodeError:
            return

        if isinstance(msg, dict):
            req_id = msg.get("id")
            if req_id is not None and req_id in self._pending:
                fut = self._pending.pop(req_id)
                if not fut.done():
                    if "error" in msg:
                        fut.set_exception(
                            RuntimeError(f"MCP error: {msg['error'].get('message', 'Unknown')}")
                        )
                    else:
                        fut.set_result(msg.get("result"))


# ---------------------------------------------------------------------------
# MCP Connection: Streamable HTTP Transport
# ---------------------------------------------------------------------------

class MCPStreamableHTTPConnection:
    """MCP connection via Streamable HTTP (latest MCP spec)."""

    def __init__(self, config: MCPServerConfig) -> None:
        self.config = config
        self._session: aiohttp.ClientSession | None = None
        self._connected = False
        self._session_id: str | None = None
        self._tools: list[MCPTool] = []
        self._resources: list[MCPResource] = []
        self._request_id = 0
        self._auth_manager = MCPOAuth2()
        self._access_token: str = ""

    @property
    def is_connected(self) -> bool:
        return self._connected

    @property
    def tools(self) -> list[MCPTool]:
        return list(self._tools)

    @property
    def resources(self) -> list[MCPResource]:
        return list(self._resources)

    def _get_headers(self) -> dict[str, str]:
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
            "User-Agent": "lucy-code/0.3.0",
        }
        if self._session_id:
            headers["Mcp-Session-Id"] = self._session_id
        if self._access_token:
            headers["Authorization"] = f"Bearer {self._access_token}"
        return headers

    async def connect(self) -> bool:
        """Connect to Streamable HTTP endpoint, initialize, discover tools."""
        if self._connected:
            return True

        if aiohttp is None:
            raise ImportError("aiohttp is required for MCP Streamable HTTP transport. Install with: pip install aiohttp")

        try:
            if self.config.auth:
                try:
                    self._access_token = await self._auth_manager.authenticate(
                        self.config.auth, self.config.name
                    )
                except Exception as e:
                    logger.warning("Streamable HTTP auth error for %s: %s", self.config.name, e)

            timeout = aiohttp.ClientTimeout(total=self.config.timeout)
            self._session = aiohttp.ClientSession(timeout=timeout)

            # Handshake: initialize
            init_res = await self._send_request("initialize", {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "lucy", "version": "0.3.0"},
            })

            if init_res is None:
                logger.warning("Streamable HTTP server %s: handshake failed", self.config.name)
                await self.disconnect()
                return False

            # Initialized notification
            await self._send_notification("notifications/initialized", {})

            # Discover tools
            self._tools.clear()
            tools_res = await self._send_request("tools/list", {})
            if tools_res and "tools" in tools_res:
                for t in tools_res["tools"]:
                    self._tools.append(MCPTool(
                        name=t.get("name", ""),
                        description=t.get("description", ""),
                        input_schema=t.get("inputSchema", {}),
                        server_name=self.config.name,
                    ))

            # Discover resources
            self._resources.clear()
            try:
                res_res = await self._send_request("resources/list", {})
                if res_res and "resources" in res_res:
                    for r in res_res["resources"]:
                        self._resources.append(MCPResource(
                            uri=r.get("uri", ""),
                            name=r.get("name", ""),
                            description=r.get("description", ""),
                            mime_type=r.get("mimeType", ""),
                            server_name=self.config.name,
                        ))
            except Exception:
                pass

            self._connected = True
            logger.info(
                "MCP server %s connected via Streamable HTTP (%d tools, %d resources)",
                self.config.name, len(self._tools), len(self._resources),
            )
            return True

        except Exception as e:
            logger.warning("Streamable HTTP connection failed for %s: %s", self.config.name, e)
            await self.disconnect()
            return False

    async def disconnect(self) -> None:
        """Disconnect session."""
        self._connected = False
        if self._session and not self._session.closed:
            await self._session.close()
            self._session = None

    async def call_tool(self, name: str, arguments: dict[str, Any]) -> Any:
        """Call tool via Streamable HTTP."""
        if not self._connected:
            raise ConnectionError(f"Server {self.config.name} not connected")
        return await self._send_request("tools/call", {
            "name": name,
            "arguments": arguments,
        })

    async def read_resource(self, uri: str) -> Any:
        """Read resource via Streamable HTTP."""
        if not self._connected:
            raise ConnectionError(f"Server {self.config.name} not connected")
        return await self._send_request("resources/read", {"uri": uri})

    async def authenticate(self, credentials: dict[str, Any]) -> bool:
        """Run or update authentication."""
        if self.config.auth:
            self._access_token = await self._auth_manager.authenticate(
                self.config.auth, self.config.name
            )
            return True
        return False

    async def _send_request(self, method: str, params: dict[str, Any]) -> Any:
        """Send JSON-RPC request and handle response (JSON or SSE stream)."""
        if not self._session or self._session.closed:
            raise ConnectionError("No active HTTP session")

        self._request_id += 1
        req_id = self._request_id
        payload = {
            "jsonrpc": "2.0",
            "id": req_id,
            "method": method,
            "params": params,
        }
        headers = self._get_headers()

        async with self._session.post(self.config.url, json=payload, headers=headers) as resp:
            # Handle token refresh on 401
            if resp.status == 401 and self.config.auth:
                self._access_token = await self._auth_manager.refresh_token(
                    self.config.auth, self.config.auth.refresh_token, self.config.name
                )
                headers["Authorization"] = f"Bearer {self._access_token}"
                async with self._session.post(self.config.url, json=payload, headers=headers) as retry_resp:
                    resp = retry_resp

            # Track session header
            session_hdr = resp.headers.get("Mcp-Session-Id")
            if session_hdr:
                self._session_id = session_hdr

            if resp.status not in (200, 202):
                err = await resp.text()
                raise RuntimeError(f"Streamable HTTP error {resp.status}: {err}")

            content_type = resp.headers.get("Content-Type", "")
            # If standard JSON response
            if "application/json" in content_type:
                data = await resp.json()
                if "error" in data:
                    raise RuntimeError(f"MCP error: {data['error'].get('message', 'Unknown')}")
                return data.get("result")

            # If chunked / streaming SSE response
            data_str = ""
            async for chunk in resp.content:
                text = chunk.decode("utf-8", errors="replace")
                for line in text.splitlines():
                    if line.startswith("data:"):
                        data_str = line[5:].strip()
                        try:
                            parsed = json.loads(data_str)
                            if parsed.get("id") == req_id:
                                if "error" in parsed:
                                    raise RuntimeError(f"MCP error: {parsed['error'].get('message', 'Unknown')}")
                                return parsed.get("result")
                        except json.JSONDecodeError:
                            continue

            if data_str:
                try:
                    parsed = json.loads(data_str)
                    return parsed.get("result")
                except json.JSONDecodeError:
                    pass

            return None

    async def _send_notification(self, method: str, params: dict[str, Any]) -> None:
        """Send notification."""
        if not self._session or self._session.closed:
            return
        payload = {
            "jsonrpc": "2.0",
            "method": method,
            "params": params,
        }
        try:
            await self._session.post(self.config.url, json=payload, headers=self._get_headers())
        except Exception as e:
            logger.debug("Failed to send notification %s: %s", method, e)


# ---------------------------------------------------------------------------
# MCP Server Hosting (Lucy acting AS an MCP Server)
# ---------------------------------------------------------------------------

class MCPServerHost:
    """Host Lucy's tools as an MCP server for other clients."""

    def __init__(
        self,
        registry: ToolRegistry | None = None,
        tool_context: ToolContext | None = None,
    ) -> None:
        self.registry = registry or get_tool_registry()
        self.context = tool_context or ToolContext(
            cwd=os.getcwd(),
            permission_mode="auto_accept",
            is_interactive=False,
        )
        self._server_info = {"name": "lucy-code", "version": "0.3.0"}
        self._protocol_version = "2024-11-05"
        self._running = False

    def _register_lucy_tools(self) -> list[dict[str, Any]]:
        """Expose Lucy's tools as MCP tools."""
        tools = self.registry.get_enabled()
        mcp_tools = []
        for t in tools:
            mcp_tools.append({
                "name": t.name,
                "description": t.description or (t.get_prompt()[:200] if hasattr(t, "get_prompt") else ""),
                "inputSchema": t.input_schema,
            })
        return mcp_tools

    async def handle_request(self, request: dict[str, Any]) -> dict[str, Any]:
        """Handle incoming JSON-RPC request and return JSON-RPC response."""
        req_id = request.get("id")
        method = request.get("method", "")
        params = request.get("params", {})

        # Handle notifications (no id)
        if req_id is None:
            if method == "notifications/initialized":
                logger.info("MCP client sent notifications/initialized")
            return {}

        # 1. Initialize
        if method == "initialize":
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {
                    "protocolVersion": self._protocol_version,
                    "capabilities": {
                        "tools": {"listChanged": True},
                        "resources": {"listChanged": True},
                    },
                    "serverInfo": self._server_info,
                },
            }

        # 2. Ping
        if method == "ping":
            return {"jsonrpc": "2.0", "id": req_id, "result": {}}

        # 3. List tools
        if method == "tools/list":
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {"tools": self._register_lucy_tools()},
            }

        # 4. Call tool
        if method == "tools/call":
            tool_name = params.get("name", "")
            tool_args = params.get("arguments", {})
            tool = self.registry.find_by_name(tool_name)

            if tool is None:
                return {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "error": {"code": -32601, "message": f"Tool not found: {tool_name}"},
                }

            try:
                result = await tool.call(tool_args, self.context)
                content_str = result.to_content_string()
                return {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "result": {
                        "content": [{"type": "text", "text": content_str}],
                        "isError": result.is_error,
                    },
                }
            except Exception as e:
                logger.exception("Error executing MCP tool %s", tool_name)
                return {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "result": {
                        "content": [{"type": "text", "text": f"Error: {e}"}],
                        "isError": True,
                    },
                }

        # 5. List resources
        if method == "resources/list":
            resources = []
            lucy_md = Path(self.context.cwd) / "LUCY.md"
            if lucy_md.exists():
                resources.append({
                    "uri": f"file://{lucy_md.resolve()}",
                    "name": "LUCY.md",
                    "description": "Project instructions and architecture",
                    "mimeType": "text/markdown",
                })
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {"resources": resources},
            }

        # 6. Read resource
        if method == "resources/read":
            uri = params.get("uri", "")
            if uri.startswith("file://"):
                file_path = Path(uri[7:])
                if file_path.exists() and file_path.is_file():
                    try:
                        content = file_path.read_text(encoding="utf-8")
                        return {
                            "jsonrpc": "2.0",
                            "id": req_id,
                            "result": {
                                "contents": [
                                    {"uri": uri, "mimeType": "text/plain", "text": content}
                                ]
                            },
                        }
                    except Exception as e:
                        return {
                            "jsonrpc": "2.0",
                            "id": req_id,
                            "error": {"code": -32000, "message": f"Failed to read resource: {e}"},
                        }

            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "error": {"code": -32602, "message": f"Resource not found: {uri}"},
            }

        # Unknown method
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "error": {"code": -32601, "message": f"Method not found: {method}"},
        }

    async def start(self, transport: str = "stdio", host: str = "127.0.0.1", port: int = 8765) -> None:
        """Start serving Lucy's tools via MCP protocol."""
        self._running = True
        logger.info("Starting Lucy MCP server host via %s", transport)

        if transport == "stdio":
            await self._run_stdio()
        elif transport in ("sse", "streamable-http", "http"):
            await self._run_http(host=host, port=port)
        else:
            raise ValueError(f"Unsupported server host transport: {transport}")

    async def _run_stdio(self) -> None:
        """Run stdio event loop processing JSON-RPC messages."""
        loop = asyncio.get_running_loop()
        reader = asyncio.StreamReader()
        protocol = asyncio.StreamReaderProtocol(reader)
        await loop.connect_read_pipe(lambda: protocol, sys.stdin)

        while self._running:
            line_bytes = await reader.readline()
            if not line_bytes:
                break

            line = line_bytes.decode("utf-8").strip()
            if not line:
                continue

            try:
                request = json.loads(line)
            except json.JSONDecodeError:
                err_resp = {
                    "jsonrpc": "2.0",
                    "id": None,
                    "error": {"code": -32700, "message": "Parse error"},
                }
                sys.stdout.write(json.dumps(err_resp) + "\n")
                sys.stdout.flush()
                continue

            response = await self.handle_request(request)
            if response:
                sys.stdout.write(json.dumps(response) + "\n")
                sys.stdout.flush()

    async def _run_http(self, host: str, port: int) -> None:
        """Run aiohttp server supporting Streamable HTTP and SSE."""
        from aiohttp import web

        app = web.Application()

        async def mcp_handler(req: web.Request) -> web.Response:
            try:
                data = await req.json()
            except Exception:
                return web.json_response(
                    {"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": "Parse error"}},
                    status=400,
                )
            res = await self.handle_request(data)
            return web.json_response(res)

        app.router.add_post("/mcp", mcp_handler)
        app.router.add_post("/messages", mcp_handler)

        runner = web.AppRunner(app)
        await runner.setup()
        site = web.TCPSite(runner, host, port)
        await site.start()
        logger.info("Lucy MCP HTTP server listening on http://%s:%d/mcp", host, port)

        try:
            while self._running:
                await asyncio.sleep(1)
        finally:
            await runner.cleanup()


# ---------------------------------------------------------------------------
# MCP Tool adapter
# ---------------------------------------------------------------------------

class MCPToolAdapter(Tool):
    """Wraps an MCP tool as a Lucy Code Tool."""

    def __init__(
        self,
        mcp_tool: MCPTool,
        connection: MCPConnection | MCPSSEConnection | MCPStreamableHTTPConnection,
    ) -> None:
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

    def is_read_only(self, tool_input: dict[str, Any]) -> bool:
        """Inspect schema or name for read-only heuristics."""
        name_lower = self._mcp_tool.name.lower()
        if any(prefix in name_lower for prefix in ("get", "read", "list", "search", "fetch", "check", "view")):
            return True
        return False

    def is_concurrent_safe(self, tool_input: dict[str, Any]) -> bool:
        return self.is_read_only(tool_input)

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
    """Manages MCP server connections, tools, and auto-reconnection."""

    def __init__(self) -> None:
        self._connections: dict[str, MCPConnection | MCPSSEConnection | MCPStreamableHTTPConnection] = {}
        self._configs: dict[str, MCPServerConfig] = {}
        self._tool_adapters: list[MCPToolAdapter] = []
        self._oauth = MCPOAuth2()

    async def connect_server(self, config: MCPServerConfig) -> bool:
        """Connect to an MCP server using its configured transport."""
        self._configs[config.name] = config

        if config.name in self._connections:
            if self._connections[config.name].is_connected:
                return True

        # Factory based on transport
        conn: MCPConnection | MCPSSEConnection | MCPStreamableHTTPConnection
        if config.transport == MCPTransport.SSE:
            conn = MCPSSEConnection(config)
        elif config.transport == MCPTransport.STREAMABLE_HTTP:
            conn = MCPStreamableHTTPConnection(config)
        else:
            conn = MCPConnection(config)

        success = await conn.connect()
        if success:
            self._connections[config.name] = conn
            # Create tool adapters
            for mcp_tool in conn.tools:
                adapter = MCPToolAdapter(mcp_tool, conn)
                self._tool_adapters.append(adapter)
            return True
        return False

    async def ensure_connected(self, server_name: str) -> bool:
        """Ensure server is connected, reconnecting if needed."""
        conn = self._connections.get(server_name)
        if conn and conn.is_connected:
            return True
        config = self._configs.get(server_name)
        if config:
            logger.info("Auto-reconnecting MCP server '%s'...", server_name)
            return await self.connect_server(config)
        return False

    async def disconnect_server(self, name: str) -> None:
        """Disconnect from an MCP server."""
        if name in self._connections:
            await self._connections[name].disconnect()
            self._tool_adapters = [
                a for a in self._tool_adapters
                if a._mcp_tool.server_name != name
            ]
            del self._connections[name]

    async def disconnect_all(self) -> None:
        """Disconnect from all MCP servers."""
        for name in list(self._connections.keys()):
            await self.disconnect_server(name)

    async def call_tool(self, server_name: str, tool_name: str, arguments: dict[str, Any]) -> Any:
        """Call a tool on an MCP server with auto-reconnection."""
        if not await self.ensure_connected(server_name):
            raise ConnectionError(f"Server '{server_name}' is not connected")
        conn = self._connections[server_name]
        try:
            return await conn.call_tool(tool_name, arguments)
        except Exception as e:
            # Reconnect and retry once if dropped
            logger.warning("MCP call failed (%s), attempting auto-reconnect: %s", server_name, e)
            if await self.ensure_connected(server_name):
                return await self._connections[server_name].call_tool(tool_name, arguments)
            raise

    async def read_resource(self, server_name: str, uri: str) -> Any:
        """Read a resource from an MCP server with auto-reconnection."""
        if not await self.ensure_connected(server_name):
            raise ConnectionError(f"Server '{server_name}' is not connected")
        conn = self._connections[server_name]
        try:
            return await conn.read_resource(uri)
        except Exception as e:
            logger.warning("MCP read_resource failed (%s), attempting auto-reconnect: %s", server_name, e)
            if await self.ensure_connected(server_name):
                return await self._connections[server_name].read_resource(uri)
            raise

    async def authenticate(self, server_name: str, credentials: dict[str, Any]) -> str:
        """Run authentication for an MCP server."""
        config = self._configs.get(server_name)
        if config and config.auth:
            token = await self._oauth.authenticate(config.auth, server_name)
            return token
        conn = self._connections.get(server_name)
        if conn and hasattr(conn, "authenticate"):
            await conn.authenticate(credentials)
            return "Authenticated"
        return "No authentication required or supported"

    def get_tools(self) -> list[MCPToolAdapter]:
        """Get all tools from connected MCP servers."""
        return list(self._tool_adapters)

    def get_connections(self) -> dict[str, MCPConnection | MCPSSEConnection | MCPStreamableHTTPConnection]:
        return dict(self._connections)

    async def connect_from_config(self, custom_path: Path | None = None) -> None:
        """Connect to all MCP servers defined in global and project configuration files."""
        config_paths = []
        if custom_path:
            config_paths.append(custom_path)
        else:
            # 1. Project local config (.lucy/mcp.json)
            local_cfg = Path.cwd() / ".lucy" / "mcp.json"
            if local_cfg.exists():
                config_paths.append(local_cfg)
            # 2. Global user config (~/.lucy/mcp.json)
            global_cfg = Path.home() / ".lucy" / "mcp.json"
            if global_cfg.exists():
                config_paths.append(global_cfg)

        for cfg_path in config_paths:
            try:
                with open(cfg_path, "r", encoding="utf-8") as f:
                    config_data = json.load(f)
            except (json.JSONDecodeError, OSError) as e:
                logger.warning("Failed to load MCP config from %s: %s", cfg_path, e)
                continue

            servers = config_data.get("mcpServers", config_data.get("servers", {}))
            for name, server_dict in servers.items():
                transport_str = server_dict.get("transport", "stdio")
                transport = MCPTransport.from_string(transport_str)

                # Parse auth if present
                auth_cfg = None
                auth_dict = server_dict.get("auth")
                if isinstance(auth_dict, dict):
                    auth_cfg = MCPAuthConfig(
                        type=auth_dict.get("type", "oauth2"),
                        client_id=auth_dict.get("client_id", ""),
                        client_secret=auth_dict.get("client_secret", ""),
                        auth_url=auth_dict.get("auth_url", ""),
                        token_url=auth_dict.get("token_url", ""),
                        refresh_token=auth_dict.get("refresh_token", ""),
                        access_token=auth_dict.get("access_token", ""),
                        scopes=auth_dict.get("scopes", []),
                    )

                mcp_config = MCPServerConfig(
                    name=name,
                    command=server_dict.get("command", ""),
                    args=server_dict.get("args", []),
                    env=server_dict.get("env", {}),
                    url=server_dict.get("url", ""),
                    transport=transport,
                    auth=auth_cfg,
                    enabled=server_dict.get("enabled", True),
                    timeout=server_dict.get("timeout", 30),
                )

                if mcp_config.enabled and (mcp_config.command or mcp_config.url):
                    success = await self.connect_server(mcp_config)
                    if success:
                        logger.info("Connected to MCP server: %s (%s)", name, transport.value)
                    else:
                        logger.warning("Failed to connect MCP server: %s", name)


# Global singleton
_mcp_manager: MCPManager | None = None


def get_mcp_manager() -> MCPManager:
    global _mcp_manager
    if _mcp_manager is None:
        _mcp_manager = MCPManager()
    return _mcp_manager
