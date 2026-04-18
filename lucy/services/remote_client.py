"""
Remote client — connect to a remote Lucy Code server.

Features:
  - WebSocket client (JSON-RPC over TCP)
  - Authentication handshake
  - Reconnection with backoff
  - Offline queue for buffered queries
  - Transparent proxy mode
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Callable

logger = logging.getLogger(__name__)


@dataclass
class PendingRequest:
    """A queued request awaiting response."""
    id: int
    method: str
    params: dict
    future: asyncio.Future
    sent_at: float = field(default_factory=time.time)


class RemoteClient:
    """Client for connecting to a remote Lucy Code server."""

    def __init__(
        self,
        host: str = "127.0.0.1",
        port: int = 9847,
        token: str = "",
        auto_reconnect: bool = True,
    ):
        self.host = host
        self.port = port
        self.token = token
        self.auto_reconnect = auto_reconnect
        self._reader: asyncio.StreamReader | None = None
        self._writer: asyncio.StreamWriter | None = None
        self._connected = False
        self._authenticated = False
        self._msg_id = 0
        self._pending: dict[int, PendingRequest] = {}
        self._offline_queue: list[tuple[str, dict]] = []
        self._reconnect_delay = 1.0
        self._max_reconnect_delay = 30.0
        self._recv_task: asyncio.Task | None = None

    @property
    def is_connected(self) -> bool:
        return self._connected

    async def connect(self) -> bool:
        """Connect to the remote server."""
        try:
            self._reader, self._writer = await asyncio.wait_for(
                asyncio.open_connection(self.host, self.port),
                timeout=10.0,
            )
            self._connected = True
            self._reconnect_delay = 1.0

            # Start receiver
            self._recv_task = asyncio.create_task(self._receive_loop())

            # Authenticate
            if self.token:
                result = await self.call("authenticate", {"token": self.token})
                self._authenticated = result.get("status") == "authenticated"
                if not self._authenticated:
                    logger.warning("Authentication failed")
                    return False

            # Flush offline queue
            await self._flush_queue()

            logger.info("Connected to %s:%d", self.host, self.port)
            return True

        except (OSError, asyncio.TimeoutError) as e:
            logger.warning("Connection failed: %s", e)
            self._connected = False
            return False

    async def disconnect(self) -> None:
        """Disconnect from the server."""
        self._connected = False
        if self._recv_task:
            self._recv_task.cancel()
        if self._writer:
            self._writer.close()
            try:
                await self._writer.wait_closed()
            except Exception:
                pass

    async def call(self, method: str, params: dict | None = None, timeout: float = 30.0) -> dict:
        """Send a JSON-RPC request and wait for response."""
        if not self._connected:
            if self.auto_reconnect:
                success = await self._reconnect()
                if not success:
                    # Queue for later
                    self._offline_queue.append((method, params or {}))
                    return {"queued": True, "offline": True}
            else:
                raise ConnectionError("Not connected")

        self._msg_id += 1
        msg_id = self._msg_id
        loop = asyncio.get_event_loop()
        future = loop.create_future()

        req = PendingRequest(id=msg_id, method=method, params=params or {}, future=future)
        self._pending[msg_id] = req

        msg = json.dumps({
            "jsonrpc": "2.0", "id": msg_id,
            "method": method, "params": params or {},
        }) + "\n"

        try:
            self._writer.write(msg.encode())
            await self._writer.drain()
        except (OSError, ConnectionResetError):
            self._connected = False
            del self._pending[msg_id]
            raise ConnectionError("Connection lost")

        try:
            result = await asyncio.wait_for(future, timeout=timeout)
            return result
        except asyncio.TimeoutError:
            self._pending.pop(msg_id, None)
            raise TimeoutError(f"Request {method} timed out")

    async def query(self, prompt: str) -> dict:
        """Send a query to the remote server."""
        return await self.call("query", {"prompt": prompt})

    async def ping(self) -> dict:
        """Ping the server."""
        return await self.call("ping", timeout=5.0)

    async def get_status(self) -> dict:
        return await self.call("status")

    async def list_tools(self) -> dict:
        return await self.call("list_tools")

    async def _receive_loop(self) -> None:
        """Background task to receive responses."""
        try:
            while self._connected and self._reader:
                line = await self._reader.readline()
                if not line:
                    break

                try:
                    msg = json.loads(line)
                except json.JSONDecodeError:
                    continue

                msg_id = msg.get("id")
                if msg_id is not None and msg_id in self._pending:
                    req = self._pending.pop(msg_id)
                    if "error" in msg:
                        error = msg["error"]
                        req.future.set_exception(
                            RuntimeError(f"RPC error {error.get('code')}: {error.get('message')}")
                        )
                    else:
                        if not req.future.done():
                            req.future.set_result(msg.get("result", {}))

        except (asyncio.CancelledError, ConnectionResetError):
            pass
        finally:
            self._connected = False

    async def _reconnect(self) -> bool:
        """Attempt to reconnect with exponential backoff."""
        for attempt in range(5):
            delay = min(self._reconnect_delay * (2 ** attempt), self._max_reconnect_delay)
            logger.info("Reconnecting in %.1fs (attempt %d)...", delay, attempt + 1)
            await asyncio.sleep(delay)
            if await self.connect():
                return True
        return False

    async def _flush_queue(self) -> None:
        """Send queued requests."""
        queue = self._offline_queue.copy()
        self._offline_queue.clear()
        for method, params in queue:
            try:
                await self.call(method, params)
            except Exception as e:
                logger.warning("Failed to flush queued %s: %s", method, e)

    def get_status_info(self) -> dict[str, Any]:
        return {
            "connected": self._connected,
            "authenticated": self._authenticated,
            "host": self.host,
            "port": self.port,
            "pending_requests": len(self._pending),
            "queued_requests": len(self._offline_queue),
        }
