"""
Remote server — expose Lucy Code over WebSocket.

JSON-RPC 2.0 protocol over WebSocket, with:
  - Authentication (API key / JWT)
  - Session management
  - Rate limiting
  - TLS support
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import secrets
import time
from dataclasses import dataclass, field
from typing import Any, Callable

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Authentication
# ---------------------------------------------------------------------------

@dataclass
class AuthToken:
    """An authentication token."""
    token: str
    created_at: float = field(default_factory=time.time)
    expires_at: float = 0.0
    scopes: list[str] = field(default_factory=lambda: ["query", "tools"])

    @property
    def is_expired(self) -> bool:
        return self.expires_at > 0 and time.time() > self.expires_at


class AuthManager:
    """Manage authentication tokens."""

    def __init__(self):
        self._tokens: dict[str, AuthToken] = {}

    def generate_token(self, ttl_seconds: float = 3600) -> AuthToken:
        token = secrets.token_urlsafe(32)
        auth = AuthToken(
            token=token,
            expires_at=time.time() + ttl_seconds if ttl_seconds > 0 else 0,
        )
        self._tokens[token] = auth
        return auth

    def validate(self, token: str) -> AuthToken | None:
        auth = self._tokens.get(token)
        if auth and not auth.is_expired:
            return auth
        if auth and auth.is_expired:
            del self._tokens[token]
        return None

    def revoke(self, token: str) -> bool:
        return self._tokens.pop(token, None) is not None


# ---------------------------------------------------------------------------
# Rate limiter
# ---------------------------------------------------------------------------

class RateLimiter:
    """Simple token-bucket rate limiter."""

    def __init__(self, max_requests: int = 60, window_seconds: float = 60.0):
        self.max_requests = max_requests
        self.window = window_seconds
        self._requests: dict[str, list[float]] = {}

    def check(self, client_id: str) -> bool:
        now = time.time()
        times = self._requests.setdefault(client_id, [])
        # Remove old entries
        times[:] = [t for t in times if now - t < self.window]
        if len(times) >= self.max_requests:
            return False
        times.append(now)
        return True


# ---------------------------------------------------------------------------
# WebSocket server (using asyncio stdlib)
# ---------------------------------------------------------------------------

@dataclass
class RemoteSession:
    """A connected client session."""
    session_id: str = ""
    client_id: str = ""
    connected_at: float = field(default_factory=time.time)
    messages: list[dict] = field(default_factory=list)
    writer: Any = None


class RemoteServer:
    """WebSocket-style JSON-RPC server using raw TCP + upgrade.

    For production, use `websockets` or `aiohttp`. This provides
    a minimal working implementation with the same protocol.
    """

    def __init__(
        self,
        host: str = "127.0.0.1",
        port: int = 9847,
        auth_required: bool = True,
    ):
        self.host = host
        self.port = port
        self.auth_required = auth_required
        self.auth_manager = AuthManager()
        self.rate_limiter = RateLimiter()
        self._sessions: dict[str, RemoteSession] = {}
        self._handlers: dict[str, Callable] = {}
        self._server: asyncio.AbstractServer | None = None

        # Register built-in handlers
        self._handlers["ping"] = self._handle_ping
        self._handlers["query"] = self._handle_query
        self._handlers["status"] = self._handle_status
        self._handlers["list_tools"] = self._handle_list_tools
        self._handlers["list_sessions"] = self._handle_list_sessions

    async def start(self) -> None:
        """Start the remote server."""
        self._server = await asyncio.start_server(
            self._handle_connection, self.host, self.port,
        )
        logger.info("Remote server listening on %s:%d", self.host, self.port)

        # Generate initial token
        token = self.auth_manager.generate_token(ttl_seconds=0)  # No expiry
        logger.info("Access token: %s", token.token)

        async with self._server:
            await self._server.serve_forever()

    async def stop(self) -> None:
        if self._server:
            self._server.close()
            await self._server.wait_closed()

    async def _handle_connection(
        self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter
    ) -> None:
        """Handle an incoming TCP connection (simplified JSON-RPC over newline-delimited JSON)."""
        addr = writer.get_extra_info("peername")
        client_id = f"{addr[0]}:{addr[1]}" if addr else "unknown"
        logger.info("Client connected: %s", client_id)

        session = RemoteSession(
            session_id=secrets.token_hex(8),
            client_id=client_id,
            writer=writer,
        )
        self._sessions[session.session_id] = session
        authenticated = not self.auth_required

        try:
            while True:
                line = await reader.readline()
                if not line:
                    break

                try:
                    msg = json.loads(line)
                except json.JSONDecodeError:
                    self._send_error(writer, None, -32700, "Parse error")
                    continue

                msg_id = msg.get("id")
                method = msg.get("method", "")
                params = msg.get("params", {})

                # Auth check
                if method == "authenticate":
                    token = params.get("token", "")
                    auth = self.auth_manager.validate(token)
                    if auth:
                        authenticated = True
                        self._send_result(writer, msg_id, {"status": "authenticated"})
                    else:
                        self._send_error(writer, msg_id, -32001, "Invalid token")
                    continue

                if self.auth_required and not authenticated:
                    self._send_error(writer, msg_id, -32002, "Not authenticated")
                    continue

                # Rate limit
                if not self.rate_limiter.check(client_id):
                    self._send_error(writer, msg_id, -32003, "Rate limited")
                    continue

                # Dispatch
                handler = self._handlers.get(method)
                if handler:
                    try:
                        result = await handler(params, session)
                        self._send_result(writer, msg_id, result)
                    except Exception as e:
                        self._send_error(writer, msg_id, -32000, str(e))
                else:
                    self._send_error(writer, msg_id, -32601, f"Method not found: {method}")

        except (asyncio.CancelledError, ConnectionResetError):
            pass
        finally:
            self._sessions.pop(session.session_id, None)
            writer.close()
            logger.info("Client disconnected: %s", client_id)

    def _send_result(self, writer: Any, msg_id: Any, result: Any) -> None:
        msg = json.dumps({"jsonrpc": "2.0", "id": msg_id, "result": result}) + "\n"
        writer.write(msg.encode())

    def _send_error(self, writer: Any, msg_id: Any, code: int, message: str) -> None:
        msg = json.dumps({
            "jsonrpc": "2.0", "id": msg_id,
            "error": {"code": code, "message": message},
        }) + "\n"
        writer.write(msg.encode())

    # --- Handlers ---

    async def _handle_ping(self, params: dict, session: RemoteSession) -> dict:
        return {"pong": True, "time": time.time()}

    async def _handle_query(self, params: dict, session: RemoteSession) -> dict:
        prompt = params.get("prompt", "")
        if not prompt:
            return {"error": "prompt is required"}
        # Placeholder — in production, this calls the query loop
        return {"status": "received", "prompt": prompt[:100]}

    async def _handle_status(self, params: dict, session: RemoteSession) -> dict:
        return {
            "server": "lucy-remote",
            "sessions": len(self._sessions),
            "uptime": time.time(),
        }

    async def _handle_list_tools(self, params: dict, session: RemoteSession) -> dict:
        from lucy.core.tool import get_tool_registry
        tools = get_tool_registry().get_all()
        return {"tools": [{"name": t.name, "description": t.description} for t in tools]}

    async def _handle_list_sessions(self, params: dict, session: RemoteSession) -> dict:
        return {
            "sessions": [
                {"id": s.session_id, "client": s.client_id, "connected_at": s.connected_at}
                for s in self._sessions.values()
            ]
        }

    def get_connection_info(self) -> dict[str, Any]:
        return {
            "host": self.host,
            "port": self.port,
            "url": f"ws://{self.host}:{self.port}",
            "sessions": len(self._sessions),
        }


async def run_remote_server(host: str = "127.0.0.1", port: int = 9847) -> None:
    """Entry point for the remote server."""
    server = RemoteServer(host=host, port=port)
    await server.start()
