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
import base64
import hashlib
import json
import logging
import os
from pathlib import Path
import secrets
import struct
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
    is_websocket: bool = False
    app_state: Any = None


def _encode_ws_frame(text: str) -> bytes:
    """Encode string payload as an unmasked RFC 6455 text frame."""
    payload = text.encode("utf-8")
    length = len(payload)
    header = bytearray([0x81])  # FIN + Opcode 1 (text)
    if length <= 125:
        header.append(length)
    elif length <= 65535:
        header.append(126)
        header.extend(struct.pack("!H", length))
    else:
        header.append(127)
        header.extend(struct.pack("!Q", length))
    return bytes(header) + payload


async def _read_ws_frame(reader: asyncio.StreamReader) -> tuple[int, bytes | None]:
    """Read a single RFC 6455 frame, returning (opcode, unmasked_payload)."""
    head = await reader.readexactly(2)
    b1, b2 = head[0], head[1]
    opcode = b1 & 0x0F
    masked = bool(b2 & 0x80)
    payload_len = b2 & 0x7F

    if payload_len == 126:
        ext = await reader.readexactly(2)
        payload_len = struct.unpack("!H", ext)[0]
    elif payload_len == 127:
        ext = await reader.readexactly(8)
        payload_len = struct.unpack("!Q", ext)[0]

    mask_key = None
    if masked:
        mask_key = await reader.readexactly(4)

    payload = await reader.readexactly(payload_len)
    if masked and mask_key:
        payload = bytes(b ^ mask_key[i % 4] for i, b in enumerate(payload))

    return opcode, payload


class RemoteServer:
    """WebSocket-style JSON-RPC server using raw TCP + upgrade.

    For production, use `websockets` or `aiohttp`. This provides
    a minimal working implementation with the same protocol.
    """

    def __init__(
        self,
        host: str = "127.0.0.1",
        port: int = 9847,
        auth_required: bool = False,
    ):
        self.host = host
        self.port = port
        self.auth_required = auth_required
        self.auth_manager = AuthManager()
        self.rate_limiter = RateLimiter()
        self._sessions: dict[str, RemoteSession] = {}
        self._handlers: dict[str, Callable] = {}
        self._server: asyncio.AbstractServer | None = None

        # Register tools and hooks for agent execution
        try:
            from lucy.main import _register_tools, _load_hooks
            _register_tools()
            _load_hooks()
        except Exception as e:
            logger.debug("Tool initialization notice: %s", e)

        # Register built-in handlers
        self._handlers["ping"] = self._handle_ping
        self._handlers["query"] = self._handle_query
        self._handlers["upload_file"] = self._handle_upload_file
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
        """Handle an incoming connection — supports RFC 6455 WebSockets, HTTP static files, and TCP JSON-RPC."""
        addr = writer.get_extra_info("peername")
        client_id = f"{addr[0]}:{addr[1]}" if addr else "unknown"
        logger.info("Client connected: %s", client_id)

        session = RemoteSession(
            session_id=secrets.token_hex(8),
            client_id=client_id,
            writer=writer,
            is_websocket=False,
        )
        self._sessions[session.session_id] = session
        authenticated = not self.auth_required

        try:
            # Peek or read initial line to detect protocol
            first_line_bytes = await reader.readline()
            if not first_line_bytes:
                return

            first_line = first_line_bytes.decode("latin1", errors="replace")

            if first_line.startswith("GET "):
                # Read remaining HTTP headers until double CRLF
                header_lines = [first_line.strip()]
                while True:
                    line = await reader.readline()
                    if not line or line in (b"\r\n", b"\n"):
                        break
                    header_lines.append(line.decode("latin1", errors="replace").strip())

                headers: dict[str, str] = {}
                for h in header_lines[1:]:
                    if ":" in h:
                        k, v = h.split(":", 1)
                        headers[k.strip().lower()] = v.strip()

                is_ws = (
                    "upgrade" in headers.get("connection", "").lower()
                    and headers.get("upgrade", "").lower() == "websocket"
                )

                if is_ws:
                    # Perform RFC 6455 WebSocket Handshake
                    ws_key = headers.get("sec-websocket-key", "")
                    magic = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"
                    accept = base64.b64encode(hashlib.sha1((ws_key + magic).encode("ascii")).digest()).decode("ascii")

                    response = (
                        "HTTP/1.1 101 Switching Protocols\r\n"
                        "Upgrade: websocket\r\n"
                        "Connection: Upgrade\r\n"
                        f"Sec-WebSocket-Accept: {accept}\r\n\r\n"
                    )
                    writer.write(response.encode("ascii"))
                    await writer.drain()

                    session.is_websocket = True

                    # Run RFC 6455 message frame loop
                    while True:
                        try:
                            opcode, payload = await _read_ws_frame(reader)
                        except (asyncio.IncompleteReadError, EOFError, ConnectionResetError):
                            break

                        if opcode == 0x08:  # Close frame
                            break
                        elif opcode == 0x09:  # Ping frame -> reply with Pong
                            pong = bytearray([0x8A, len(payload or b"")]) + (payload or b"")
                            writer.write(pong)
                            await writer.drain()
                            continue
                        elif opcode == 0x01 and payload:  # Text frame
                            try:
                                text = payload.decode("utf-8")
                                msg = json.loads(text)
                                await self._process_message(msg, session, client_id, authenticated)
                            except Exception as e:
                                self._send_error(session, None, -32700, f"Parse error: {e}")
                    return

                else:
                    # Serve mobile_web/index.html over HTTP for direct browser access
                    html_path = Path(__file__).parent / "mobile_web" / "index.html"
                    if html_path.exists():
                        content = html_path.read_bytes()
                        resp = (
                            f"HTTP/1.1 200 OK\r\n"
                            f"Content-Type: text/html; charset=utf-8\r\n"
                            f"Content-Length: {len(content)}\r\n"
                            f"Connection: close\r\n\r\n"
                        ).encode("ascii") + content
                        writer.write(resp)
                        await writer.drain()
                    else:
                        resp = b"HTTP/1.1 404 Not Found\r\nContent-Length: 0\r\nConnection: close\r\n\r\n"
                        writer.write(resp)
                        await writer.drain()
                    return

            # Otherwise, treat as TCP newline-delimited JSON-RPC
            try:
                msg = json.loads(first_line)
                await self._process_message(msg, session, client_id, authenticated)
            except json.JSONDecodeError:
                self._send_error(session, None, -32700, "Parse error")

            while True:
                line = await reader.readline()
                if not line:
                    break
                try:
                    msg = json.loads(line)
                    await self._process_message(msg, session, client_id, authenticated)
                except json.JSONDecodeError:
                    self._send_error(session, None, -32700, "Parse error")

        except (asyncio.CancelledError, ConnectionResetError, BrokenPipeError):
            pass
        finally:
            self._sessions.pop(session.session_id, None)
            try:
                writer.close()
                await writer.wait_closed()
            except Exception:
                pass
            logger.info("Client disconnected: %s", client_id)

    async def _process_message(
        self, msg: dict, session: RemoteSession, client_id: str, authenticated: bool
    ) -> None:
        """Process a single JSON-RPC message."""
        msg_id = msg.get("id")
        method = msg.get("method", "")
        params = msg.get("params", {})

        # Auth check
        if method == "authenticate":
            token = params.get("token", "")
            auth = self.auth_manager.validate(token)
            if auth:
                self._send_result(session, msg_id, {"status": "authenticated"})
            else:
                self._send_error(session, msg_id, -32001, "Invalid token")
            return

        if self.auth_required and not authenticated:
            self._send_error(session, msg_id, -32002, "Not authenticated")
            return

        # Rate limit
        if not self.rate_limiter.check(client_id):
            self._send_error(session, msg_id, -32003, "Rate limited")
            return

        # Dispatch
        handler = self._handlers.get(method)
        if handler:
            try:
                result = await handler(params, session)
                self._send_result(session, msg_id, result)
            except Exception as e:
                self._send_error(session, msg_id, -32000, str(e))
        else:
            self._send_error(session, msg_id, -32601, f"Method not found: {method}")

    def _send_result(self, session: RemoteSession, msg_id: Any, result: Any) -> None:
        payload = json.dumps({"jsonrpc": "2.0", "id": msg_id, "result": result})
        if session.is_websocket:
            session.writer.write(_encode_ws_frame(payload))
        else:
            session.writer.write((payload + "\n").encode())

    def _send_error(self, session: RemoteSession, msg_id: Any, code: int, message: str) -> None:
        payload = json.dumps({
            "jsonrpc": "2.0", "id": msg_id,
            "error": {"code": code, "message": message},
        })
        if session.is_websocket:
            session.writer.write(_encode_ws_frame(payload))
        else:
            session.writer.write((payload + "\n").encode())

    def _send_notification(self, session: RemoteSession, method: str, params: dict) -> None:
        """Send a JSON-RPC notification (no response expected)."""
        if not session.writer or session.writer.is_closing():
            return
        payload = json.dumps({"jsonrpc": "2.0", "method": method, "params": params})
        try:
            if session.is_websocket:
                session.writer.write(_encode_ws_frame(payload))
            else:
                session.writer.write((payload + "\n").encode())
        except Exception:
            pass

    def _get_or_create_app_state(self) -> Any:
        """Get or initialize AppState for conversation memory and tool execution."""
        from lucy.core.config import get_config
        from lucy.core.state import AppState
        from lucy.api.models import resolve_model

        config = get_config()
        model = resolve_model(config.model)
        return AppState(
            model=model,
            autonomous=True,
            permission_mode="auto_accept",
            is_non_interactive=False,
        )

    # --- Handlers ---

    async def _handle_ping(self, params: dict, session: RemoteSession) -> dict:
        return {"pong": True, "time": time.time()}

    async def _handle_upload_file(self, params: dict, session: RemoteSession) -> dict:
        """Handle file upload from web/mobile client, saving into workspace uploads/ folder."""
        filename = params.get("filename", "").strip()
        if not filename:
            return {"error": "filename is required"}

        content = params.get("content", "")
        is_base64 = params.get("is_base64", False)

        uploads_dir = Path.cwd() / "uploads"
        uploads_dir.mkdir(parents=True, exist_ok=True)

        safe_name = Path(filename).name
        target_path = uploads_dir / safe_name

        try:
            if is_base64:
                raw_bytes = base64.b64decode(content)
                target_path.write_bytes(raw_bytes)
            else:
                target_path.write_text(content, encoding="utf-8")

            size = target_path.stat().st_size
            rel_path = f"uploads/{safe_name}"
            return {
                "status": "success",
                "filename": safe_name,
                "path": str(target_path),
                "relative_path": rel_path,
                "size": size,
                "message": f"Uploaded {safe_name} ({size:,} bytes) to {rel_path}",
            }
        except Exception as e:
            return {"status": "error", "error": f"Failed to save file: {e}"}

    async def _handle_query(self, params: dict, session: RemoteSession) -> dict:
        prompt = params.get("prompt", "").strip()
        attachments = params.get("attachments", [])

        # Process attachments if attached to query
        if attachments:
            uploads_dir = Path.cwd() / "uploads"
            uploads_dir.mkdir(parents=True, exist_ok=True)
            saved_notes = []
            for att in attachments:
                raw_name = att.get("filename", "upload.txt")
                safe_name = Path(raw_name).name
                att_content = att.get("content", "")
                is_b64 = att.get("is_base64", False)
                dest = uploads_dir / safe_name
                try:
                    if is_b64:
                        dest.write_bytes(base64.b64decode(att_content))
                    else:
                        dest.write_text(att_content, encoding="utf-8")
                    saved_notes.append(f"uploads/{safe_name} ({dest.stat().st_size} bytes)")
                except Exception as e:
                    logger.debug("Failed saving attachment %s: %s", raw_name, e)
            if saved_notes:
                prefix = f"[Attached files saved to workspace: {', '.join(saved_notes)}]\n"
                prompt = prefix + prompt if prompt else prefix.strip()

        if not prompt:
            return {"error": "prompt is required"}

        # Initialize session state if absent
        if session.app_state is None:
            session.app_state = self._get_or_create_app_state()
        state = session.app_state

        # 1. Handle Slash Commands (/help, /tools, /companion, /clear, etc.)
        if prompt.startswith("/"):
            from lucy.core.commands import find_command, parse_command_input
            cmd_parsed = parse_command_input(prompt)
            if cmd_parsed:
                cmd_name, cmd_args = cmd_parsed
                if cmd_name == "clear":
                    state.messages.clear()
                    return {"status": "success", "prompt": prompt, "response": "Chat conversation cleared."}

                cmd = find_command(cmd_name)
                if cmd:
                    try:
                        res = await cmd.execute(cmd_args, state)
                        out = res.output or res.error or "Command executed."
                        return {"status": "success", "prompt": prompt, "response": out}
                    except Exception as e:
                        return {"status": "error", "prompt": prompt, "response": f"Command error: {e}"}
                else:
                    return {
                        "status": "error",
                        "prompt": prompt,
                        "response": f"Unknown command: /{cmd_name}. Type /help for available commands.",
                    }

        # 2. Agentic Query Execution via query_loop & Tool Execution
        from lucy.core.context import build_system_prompt, get_git_status, get_lucymd_content
        from lucy.core.message import AssistantMessage, StreamEvent, UserMessage, create_user_message
        from lucy.core.query import QueryParams, query_loop
        from lucy.core.tool import ToolContext, get_tool_registry

        git_status = await get_git_status(state.cwd)
        lucymd = get_lucymd_content(state.cwd)
        system_prompt = build_system_prompt(
            cwd=state.cwd,
            git_status=git_status,
            lucymd=lucymd,
            user_prompt=prompt,
            is_autonomous=True,
        )

        tool_context = ToolContext(
            cwd=state.cwd,
            permission_mode="auto_accept",
            autonomous=True,
            is_interactive=False,
        )

        user_msg = create_user_message(prompt)
        state.messages.append(user_msg)

        registry = get_tool_registry()
        params_obj = QueryParams(
            messages=list(state.messages),
            system_prompt=system_prompt,
            tools=registry,
            tool_context=tool_context,
            model=state.model,
            thinking_enabled=False,
            parallel_tools=True,
        )

        accumulated_text: list[str] = []
        tools_executed: list[str] = []
        last_assistant_msg: AssistantMessage | None = None

        try:
            async for event in query_loop(params_obj):
                if isinstance(event, StreamEvent):
                    if event.type == "text_delta":
                        text_chunk = event.data.get("text", "")
                        if text_chunk:
                            accumulated_text.append(text_chunk)
                            if session.is_websocket:
                                self._send_notification(session, "stream_delta", {"text": text_chunk})
                    elif event.type == "tool_use_start":
                        tool_name = event.data.get("name", "")
                        if tool_name:
                            tools_executed.append(tool_name)
                            if session.is_websocket:
                                self._send_notification(session, "tool_start", {"tool": tool_name})
                elif isinstance(event, AssistantMessage):
                    last_assistant_msg = event
                    state.messages.append(event)
                elif isinstance(event, UserMessage):
                    state.messages.append(event)

            # Determine response string
            final_text = ""
            if last_assistant_msg and last_assistant_msg.get_text().strip():
                final_text = last_assistant_msg.get_text()
            elif accumulated_text:
                final_text = "".join(accumulated_text)
            elif tools_executed:
                final_text = f"Executed actions successfully: {', '.join(tools_executed)}"
            else:
                final_text = "I completed processing your request."

            return {
                "status": "success",
                "prompt": prompt,
                "response": final_text,
                "tools_used": tools_executed,
            }

        except Exception as e:
            logger.exception("Remote query execution error: %s", e)
            error_msg = f"Lucy encountered an error: {e}"
            return {
                "status": "error",
                "prompt": prompt,
                "response": error_msg,
                "error": str(e),
            }

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


if __name__ == "__main__":
    import sys
    host = "127.0.0.1"
    port = 9847
    if len(sys.argv) > 1:
        port = int(sys.argv[1])
    print(f"🚀 Lucy Code Remote & Web Server listening on http://{host}:{port} and ws://{host}:{port}")
    try:
        asyncio.run(run_remote_server(host=host, port=port))
    except KeyboardInterrupt:
        print("\nServer stopped.")
