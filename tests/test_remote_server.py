"""
Tests for Lucy Code Remote Server, WebSocket bridge, and agent query execution.
"""

import asyncio
import base64
import hashlib
import json
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from lucy.services.remote_server import RemoteServer, _encode_ws_frame, _read_ws_frame


class MockWriter:
    """In-memory mock StreamWriter for isolated unit testing."""

    def __init__(self):
        self.data = bytearray()
        self.closed = False
        self.is_closing_flag = False

    def get_extra_info(self, name: str, default=None):
        if name == "peername":
            return ("127.0.0.1", 54321)
        return default

    def write(self, data: bytes):
        self.data.extend(data)

    async def drain(self):
        pass

    def is_closing(self):
        return self.is_closing_flag

    def close(self):
        self.closed = True
        self.is_closing_flag = True

    async def wait_closed(self):
        pass


class TestRemoteServerUnit(unittest.IsolatedAsyncioTestCase):
    """Test remote server logic purely in-memory without network sockets."""

    def setUp(self):
        self.server = RemoteServer(host="127.0.0.1", port=9847, auth_required=False)

    async def test_encode_and_read_ws_frame(self):
        """Test encoding and decoding RFC 6455 WebSocket frames."""
        raw_text = json.dumps({"test": "hello_pixel", "num": 42})
        encoded = _encode_ws_frame(raw_text)

        reader = asyncio.StreamReader()
        reader.feed_data(encoded)
        reader.feed_eof()

        opcode, payload = await _read_ws_frame(reader)
        self.assertEqual(opcode, 0x01)
        self.assertIsNotNone(payload)
        decoded_text = payload.decode("utf-8")
        self.assertEqual(json.loads(decoded_text), {"test": "hello_pixel", "num": 42})

    async def test_http_get_index_serves_html(self):
        """HTTP GET request serves the mobile web index.html."""
        reader = asyncio.StreamReader()
        writer = MockWriter()

        request_bytes = b"GET / HTTP/1.1\r\nHost: 127.0.0.1:9847\r\n\r\n"
        reader.feed_data(request_bytes)
        reader.feed_eof()

        await self.server._handle_connection(reader, writer)

        output = bytes(writer.data)
        self.assertIn(b"HTTP/1.1 200 OK", output)
        self.assertIn(b"Lucy Code", output)
        self.assertIn(b"Lucy", output)

    async def test_websocket_handshake(self):
        """WebSocket upgrade request completes 101 Switching Protocols with valid accept key."""
        reader = asyncio.StreamReader()
        writer = MockWriter()

        ws_key = base64.b64encode(b"test_key_123456").decode("ascii")
        request = (
            f"GET / HTTP/1.1\r\n"
            f"Host: 127.0.0.1:9847\r\n"
            f"Upgrade: websocket\r\n"
            f"Connection: Upgrade\r\n"
            f"Sec-WebSocket-Key: {ws_key}\r\n"
            f"Sec-WebSocket-Version: 13\r\n\r\n"
        ).encode("ascii")

        reader.feed_data(request)
        reader.feed_eof()

        await self.server._handle_connection(reader, writer)

        output = bytes(writer.data)
        self.assertIn(b"HTTP/1.1 101 Switching Protocols", output)
        self.assertIn(b"Upgrade: websocket", output)

        magic = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"
        expected_accept = base64.b64encode(
            hashlib.sha1((ws_key + magic).encode("ascii")).digest()
        ).decode("ascii")
        self.assertIn(f"Sec-WebSocket-Accept: {expected_accept}".encode("ascii"), output)

    async def test_jsonrpc_handlers(self):
        """Test ping, status, list_tools handlers."""
        session = MagicMock()
        session.is_websocket = False
        session.app_state = None

        ping_res = await self.server._handle_ping({}, session)
        self.assertTrue(ping_res.get("pong"))

        status_res = await self.server._handle_status({}, session)
        self.assertEqual(status_res.get("server"), "lucy-remote")

        tools_res = await self.server._handle_list_tools({}, session)
        self.assertIn("tools", tools_res)

    async def test_handle_slash_commands(self):
        """Slash commands like /help and /companion execute directly via remote server."""
        session = MagicMock()
        session.is_websocket = False
        session.app_state = self.server._get_or_create_app_state()

        comp_res = await self.server._handle_query({"prompt": "/companion"}, session)
        self.assertEqual(comp_res.get("status"), "success")
        self.assertIn("Lucy", comp_res.get("response", ""))

        clear_res = await self.server._handle_query({"prompt": "/clear"}, session)
        self.assertEqual(clear_res.get("status"), "success")
        self.assertIn("cleared", clear_res.get("response", "").lower())

    async def test_handle_query_execution(self):
        """Natural language queries execute through query_loop and return assistant message."""
        session = MagicMock()
        session.is_websocket = False
        session.app_state = self.server._get_or_create_app_state()

        from lucy.core.message import AssistantMessage, TextBlock

        mock_msg = AssistantMessage(content=[TextBlock(text="I am Lucy, your coding AI agent!")])

        async def fake_query_loop(params):
            yield mock_msg

        with patch("lucy.core.query.query_loop", side_effect=fake_query_loop):
            res = await self.server._handle_query({"prompt": "Hello Lucy, who are you?"}, session)
            self.assertEqual(res.get("status"), "success")
            self.assertIn("I am Lucy", res.get("response", ""))

    async def test_upload_file_text_and_base64(self):
        """Test uploading files via remote server to workspace uploads/ directory."""
        session = MagicMock()
        session.is_websocket = False

        # Text upload
        res1 = await self.server._handle_upload_file(
            {"filename": "test_script.py", "content": "print('hello from upload')", "is_base64": False},
            session,
        )
        self.assertEqual(res1.get("status"), "success")
        self.assertEqual(res1.get("filename"), "test_script.py")
        self.assertTrue(res1.get("size") > 0)

        # Base64 binary upload
        sample_b64 = base64.b64encode(b"binary pixel companion bytes").decode("ascii")
        res2 = await self.server._handle_upload_file(
            {"filename": "test_binary.bin", "content": sample_b64, "is_base64": True},
            session,
        )
        self.assertEqual(res2.get("status"), "success")
        self.assertEqual(res2.get("filename"), "test_binary.bin")
        self.assertEqual(res2.get("size"), len(b"binary pixel companion bytes"))

    async def test_query_with_attachments(self):
        """Test query with attached files stores them and injects note into prompt."""
        session = MagicMock()
        session.is_websocket = False
        session.app_state = self.server._get_or_create_app_state()

        from lucy.core.message import AssistantMessage, TextBlock

        captured_params = []

        async def fake_query_loop(params):
            captured_params.append(params)
            yield AssistantMessage(content=[TextBlock(text="File analyzed!")])

        with patch("lucy.core.query.query_loop", side_effect=fake_query_loop):
            res = await self.server._handle_query(
                {
                    "prompt": "Please review this snippet",
                    "attachments": [
                        {"filename": "review_me.py", "content": "def add(a, b): return a + b", "is_base64": False}
                    ],
                },
                session,
            )
            self.assertEqual(res.get("status"), "success")
            self.assertIn("File analyzed!", res.get("response", ""))
            self.assertTrue(len(captured_params) > 0)
            last_user_text = captured_params[0].messages[-1].get_text()
            self.assertIn("review_me.py", last_user_text)


if __name__ == "__main__":
    unittest.main()
