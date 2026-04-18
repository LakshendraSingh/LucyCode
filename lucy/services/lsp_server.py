"""
LSP Server — VS Code Language Server Protocol integration.

Implements a Language Server that provides AI-powered features:
  - Code completion (textDocument/completion)
  - Code actions ("Ask Lucy Code", "Fix", "Refactor")
  - Hover information (explain code)
  - Diagnostics (AI-suggested improvements)
  - Custom commands (lucy.ask, lucy.fix)

Transport: stdio (launched by the VS Code extension)
"""

from __future__ import annotations

import asyncio
import json
import logging
import sys
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# LSP Message types (minimal implementation)
# ---------------------------------------------------------------------------

@dataclass
class LSPMessage:
    """A JSON-RPC 2.0 message."""
    jsonrpc: str = "2.0"
    id: int | str | None = None
    method: str | None = None
    params: dict[str, Any] | None = None
    result: Any = None
    error: dict[str, Any] | None = None


class LSPTransport:
    """Stdio-based LSP transport."""

    def __init__(self):
        self._reader = None
        self._writer = None

    async def start(self):
        """Set up stdin/stdout for LSP communication."""
        loop = asyncio.get_event_loop()
        self._reader = asyncio.StreamReader()
        protocol = asyncio.StreamReaderProtocol(self._reader)
        await loop.connect_read_pipe(lambda: protocol, sys.stdin.buffer)
        w_transport, w_protocol = await loop.connect_write_pipe(
            asyncio.streams.FlowControlMixin, sys.stdout.buffer
        )
        self._writer = asyncio.StreamWriter(
            w_transport, w_protocol, self._reader, loop
        )

    async def read_message(self) -> LSPMessage | None:
        """Read an LSP message from stdin."""
        if not self._reader:
            return None

        # Read headers
        content_length = 0
        while True:
            line = await self._reader.readline()
            if not line:
                return None
            line_str = line.decode("utf-8").strip()
            if not line_str:
                break
            if line_str.startswith("Content-Length:"):
                content_length = int(line_str.split(":")[1].strip())

        if content_length == 0:
            return None

        # Read body
        body = await self._reader.readexactly(content_length)
        try:
            data = json.loads(body)
            return LSPMessage(
                id=data.get("id"),
                method=data.get("method"),
                params=data.get("params"),
                result=data.get("result"),
                error=data.get("error"),
            )
        except json.JSONDecodeError:
            return None

    def send_message(self, msg: dict[str, Any]) -> None:
        """Send an LSP message to stdout."""
        if not self._writer:
            return
        body = json.dumps(msg)
        header = f"Content-Length: {len(body)}\r\n\r\n"
        self._writer.write(header.encode("utf-8") + body.encode("utf-8"))

    def send_response(self, msg_id: int | str, result: Any) -> None:
        self.send_message({"jsonrpc": "2.0", "id": msg_id, "result": result})

    def send_error(self, msg_id: int | str, code: int, message: str) -> None:
        self.send_message({
            "jsonrpc": "2.0", "id": msg_id,
            "error": {"code": code, "message": message},
        })

    def send_notification(self, method: str, params: dict[str, Any]) -> None:
        self.send_message({"jsonrpc": "2.0", "method": method, "params": params})


# ---------------------------------------------------------------------------
# LSP Server
# ---------------------------------------------------------------------------

class LucyCodeLSPServer:
    """Lucy Code Language Server Protocol server."""

    def __init__(self):
        self.transport = LSPTransport()
        self._initialized = False
        self._shutdown = False
        self._workspace_folders: list[str] = []

    async def start(self):
        """Start the LSP server."""
        await self.transport.start()
        logger.info("Lucy Code LSP server started")

        while not self._shutdown:
            msg = await self.transport.read_message()
            if msg is None:
                break
            await self._handle_message(msg)

    async def _handle_message(self, msg: LSPMessage) -> None:
        """Route an LSP message to the appropriate handler."""
        method = msg.method or ""

        handlers = {
            "initialize": self._handle_initialize,
            "initialized": self._handle_initialized,
            "shutdown": self._handle_shutdown,
            "exit": self._handle_exit,
            "textDocument/completion": self._handle_completion,
            "textDocument/hover": self._handle_hover,
            "textDocument/codeAction": self._handle_code_action,
            "textDocument/didOpen": self._handle_did_open,
            "textDocument/didChange": self._handle_did_change,
            "textDocument/didSave": self._handle_did_save,
            "workspace/executeCommand": self._handle_execute_command,
        }

        handler = handlers.get(method)
        if handler:
            await handler(msg)
        elif msg.id is not None:
            # Unknown request — respond with method not found
            self.transport.send_error(msg.id, -32601, f"Method not found: {method}")

    async def _handle_initialize(self, msg: LSPMessage) -> None:
        params = msg.params or {}
        root_uri = params.get("rootUri", "")
        if root_uri.startswith("file://"):
            self._workspace_folders.append(root_uri[7:])

        capabilities = {
            "completionProvider": {
                "triggerCharacters": [".", "/", "@"],
                "resolveProvider": False,
            },
            "hoverProvider": True,
            "codeActionProvider": {
                "codeActionKinds": [
                    "quickfix",
                    "refactor",
                    "source.lucy",
                ],
            },
            "textDocumentSync": {
                "openClose": True,
                "change": 1,  # Full sync
                "save": {"includeText": True},
            },
            "executeCommandProvider": {
                "commands": [
                    "lucy.ask",
                    "lucy.fix",
                    "lucy.refactor",
                    "lucy.explain",
                    "lucy.test",
                ],
            },
        }

        self.transport.send_response(msg.id, {
            "capabilities": capabilities,
            "serverInfo": {"name": "lucy-lsp", "version": "0.3.0"},
        })

    async def _handle_initialized(self, msg: LSPMessage) -> None:
        self._initialized = True
        logger.info("LSP client initialized")

    async def _handle_shutdown(self, msg: LSPMessage) -> None:
        self._shutdown = True
        self.transport.send_response(msg.id, None)

    async def _handle_exit(self, msg: LSPMessage) -> None:
        sys.exit(0)

    async def _handle_completion(self, msg: LSPMessage) -> None:
        """Provide AI-powered completions."""
        params = msg.params or {}
        # Extract document and position
        doc = params.get("textDocument", {})
        position = params.get("position", {})
        uri = doc.get("uri", "")
        line = position.get("line", 0)

        # Return a placeholder completion
        items = [
            {
                "label": "# Ask Lucy Code...",
                "kind": 15,  # Snippet
                "detail": "Ask Lucy Code for help",
                "insertText": "# TODO: ",
                "documentation": "Use Lucy Code to get AI assistance",
            }
        ]

        self.transport.send_response(msg.id, {"isIncomplete": False, "items": items})

    async def _handle_hover(self, msg: LSPMessage) -> None:
        """Provide AI-powered hover information."""
        params = msg.params or {}
        # For now, return empty hover
        self.transport.send_response(msg.id, None)

    async def _handle_code_action(self, msg: LSPMessage) -> None:
        """Provide code actions (Ask Lucy Code, Fix, Refactor)."""
        params = msg.params or {}
        doc = params.get("textDocument", {})
        range_info = params.get("range", {})

        actions = [
            {
                "title": "Ask Lucy Code about this code",
                "kind": "source.lucy",
                "command": {
                    "title": "Ask Lucy Code",
                    "command": "lucy.ask",
                    "arguments": [doc.get("uri", ""), range_info],
                },
            },
            {
                "title": "Fix with Lucy Code",
                "kind": "quickfix",
                "command": {
                    "title": "Fix",
                    "command": "lucy.fix",
                    "arguments": [doc.get("uri", ""), range_info],
                },
            },
            {
                "title": "Refactor with Lucy Code",
                "kind": "refactor",
                "command": {
                    "title": "Refactor",
                    "command": "lucy.refactor",
                    "arguments": [doc.get("uri", ""), range_info],
                },
            },
        ]

        self.transport.send_response(msg.id, actions)

    async def _handle_did_open(self, msg: LSPMessage) -> None:
        pass

    async def _handle_did_change(self, msg: LSPMessage) -> None:
        pass

    async def _handle_did_save(self, msg: LSPMessage) -> None:
        pass

    async def _handle_execute_command(self, msg: LSPMessage) -> None:
        """Execute a custom Lucy Code command."""
        params = msg.params or {}
        command = params.get("command", "")
        args = params.get("arguments", [])

        if command == "lucy.ask":
            result = {"message": "Lucy Code is thinking..."}
        elif command == "lucy.fix":
            result = {"message": "Lucy Code is fixing..."}
        elif command == "lucy.refactor":
            result = {"message": "Lucy Code is refactoring..."}
        elif command == "lucy.explain":
            result = {"message": "Lucy Code is explaining..."}
        elif command == "lucy.test":
            result = {"message": "Lucy Code is testing..."}
        else:
            self.transport.send_error(msg.id, -32600, f"Unknown command: {command}")
            return

        self.transport.send_response(msg.id, result)

    def send_diagnostics(self, uri: str, diagnostics: list[dict]) -> None:
        """Publish diagnostics (AI suggestions) for a file."""
        self.transport.send_notification("textDocument/publishDiagnostics", {
            "uri": uri,
            "diagnostics": diagnostics,
        })


async def run_lsp_server():
    """Entry point for running the LSP server."""
    server = LucyCodeLSPServer()
    await server.start()
