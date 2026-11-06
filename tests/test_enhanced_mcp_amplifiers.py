"""
Tests for Enhanced MCP and Intelligence Amplifiers.

Verifies:
  - Part 1: SSE Transport, Streamable HTTP Transport, Server Host, OAuth2, MCPManager
  - Part 2: Parallel Tool Execution, Learning Engine, Speculative Engine, Context Engine
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import tempfile
import time
import unittest
from pathlib import Path
from typing import Any

# Ensure lucy is on sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lucy.core.context import build_system_prompt
from lucy.core.context_engine import ContextEngine, get_context_engine
from lucy.core.learning import Correction, LearningEngine, get_learning_engine
from lucy.core.message import (
    AssistantMessage,
    TextBlock,
    ToolResultBlock,
    ToolUseBlock,
    UserMessage,
    create_tool_result_message,
    create_user_message,
)
from lucy.core.parallel_tools import ParallelToolExecutor
from lucy.core.speculative import SpeculativeEngine, get_speculative_engine
from lucy.core.tool import Tool, ToolContext, ToolRegistry, ToolResult
from lucy.services.mcp import (
    MCPAuthConfig,
    MCPConnection,
    MCPOAuth2,
    MCPServerConfig,
    MCPServerHost,
    MCPSSEConnection,
    MCPStreamableHTTPConnection,
    MCPTool,
    MCPToolAdapter,
    MCPTransport,
    get_mcp_manager,
)


class DummyReadTool(Tool):
    """Dummy read tool that is concurrent safe."""
    @property
    def name(self) -> str:
        return "DummyRead"

    @property
    def description(self) -> str:
        return "Reads test data"

    @property
    def input_schema(self) -> dict[str, Any]:
        return {"type": "object", "properties": {"target": {"type": "string"}}}

    def get_prompt(self) -> str:
        return "Read test data"

    def is_read_only(self, tool_input: dict[str, Any]) -> bool:
        return True

    def is_concurrent_safe(self, tool_input: dict[str, Any]) -> bool:
        return True

    async def call(self, tool_input: dict[str, Any], context: ToolContext) -> ToolResult:
        await asyncio.sleep(0.01)
        return ToolResult(data=f"read:{tool_input.get('target', '')}")


class DummyWriteTool(Tool):
    """Dummy write tool that is NOT concurrent safe."""
    @property
    def name(self) -> str:
        return "DummyWrite"

    @property
    def description(self) -> str:
        return "Writes test data"

    @property
    def input_schema(self) -> dict[str, Any]:
        return {"type": "object", "properties": {"val": {"type": "string"}}}

    def get_prompt(self) -> str:
        return "Write test data"

    def is_read_only(self, tool_input: dict[str, Any]) -> bool:
        return False

    def is_concurrent_safe(self, tool_input: dict[str, Any]) -> bool:
        return False

    async def call(self, tool_input: dict[str, Any], context: ToolContext) -> ToolResult:
        return ToolResult(data=f"wrote:{tool_input.get('val', '')}")


class TestEnhancedMCPAmplifiers(unittest.TestCase):
    """Unit test suite for Enhanced MCP and Intelligence Amplifiers."""

    def test_mcp_transports_and_config(self) -> None:
        """Test MCP transport parsing and configs."""
        async def _test():
            self.assertEqual(MCPTransport.from_string("stdio"), MCPTransport.STDIO)
            self.assertEqual(MCPTransport.from_string("sse"), MCPTransport.SSE)
            self.assertEqual(MCPTransport.from_string("streamable-http"), MCPTransport.STREAMABLE_HTTP)
            self.assertEqual(MCPTransport.from_string("streamable_http"), MCPTransport.STREAMABLE_HTTP)

            auth = MCPAuthConfig(
                type="oauth2",
                client_id="test_client",
                scopes=["tools:read"],
                access_token="dummy_token",
                expires_at=time.time() + 3600,
            )
            cfg = MCPServerConfig(
                name="remote-server",
                url="https://example.com/sse",
                transport=MCPTransport.SSE,
                auth=auth,
            )
            self.assertEqual(cfg.name, "remote-server")
            self.assertEqual(cfg.transport, MCPTransport.SSE)
            self.assertEqual(cfg.auth.client_id, "test_client")

            # Test OAuth2 caching
            with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as tf:
                tf.write(b"{}")
                tf.flush()
                token_path = Path(tf.name)
            try:
                oauth = MCPOAuth2(token_storage_path=token_path)
                token = await oauth.authenticate(auth, "remote-server")
                self.assertEqual(token, "dummy_token")
            finally:
                if token_path.exists():
                    token_path.unlink()

        asyncio.run(_test())

    def test_mcp_server_host(self) -> None:
        """Test hosting Lucy tools via MCP JSON-RPC."""
        async def _test():
            registry = ToolRegistry()
            registry.register(DummyReadTool())
            registry.register(DummyWriteTool())

            host = MCPServerHost(registry=registry)

            # 1. Initialize
            init_req = {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {"protocolVersion": "2024-11-05"},
            }
            resp = await host.handle_request(init_req)
            self.assertEqual(resp["id"], 1)
            self.assertIn("capabilities", resp["result"])
            self.assertEqual(resp["result"]["serverInfo"]["name"], "lucy-code")

            # 2. Ping
            ping_resp = await host.handle_request({"jsonrpc": "2.0", "id": 2, "method": "ping"})
            self.assertEqual(ping_resp["id"], 2)

            # 3. Tools list
            list_resp = await host.handle_request({"jsonrpc": "2.0", "id": 3, "method": "tools/list"})
            tool_names = [t["name"] for t in list_resp["result"]["tools"]]
            self.assertIn("DummyRead", tool_names)
            self.assertIn("DummyWrite", tool_names)

            # 4. Tools call
            call_resp = await host.handle_request({
                "jsonrpc": "2.0",
                "id": 4,
                "method": "tools/call",
                "params": {"name": "DummyRead", "arguments": {"target": "unit_test"}},
            })
            self.assertEqual(call_resp["id"], 4)
            self.assertEqual(call_resp["result"]["content"][0]["text"], "read:unit_test")
            self.assertFalse(call_resp["result"]["isError"])

        asyncio.run(_test())

    def test_parallel_tool_executor(self) -> None:
        """Test concurrent read tools and sequential write tools."""
        async def _test():
            registry = ToolRegistry()
            registry.register(DummyReadTool())
            registry.register(DummyWriteTool())

            executor = ParallelToolExecutor(max_concurrency=4)
            context = ToolContext(cwd=os.getcwd(), is_interactive=False)

            blocks = [
                ToolUseBlock(id="r1", name="DummyRead", input={"target": "A"}),
                ToolUseBlock(id="r2", name="DummyRead", input={"target": "B"}),
                ToolUseBlock(id="w1", name="DummyWrite", input={"val": "W1"}),
                ToolUseBlock(id="r3", name="DummyRead", input={"target": "C"}),
            ]

            results = await executor.execute_tools(blocks, registry, context, assistant_uuid="ast_1")
            self.assertEqual(len(results), 4)
            res_contents = [r.content[0].content if isinstance(r.content, list) else r.content for r in results]
            self.assertEqual(res_contents[0], "read:A")
            self.assertEqual(res_contents[1], "read:B")
            self.assertEqual(res_contents[2], "wrote:W1")
            self.assertEqual(res_contents[3], "read:C")

        asyncio.run(_test())

    def test_learning_engine(self) -> None:
        """Test learning engine correction detection and persistence."""
        async def _test():
            with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tf:
                db_path = Path(tf.name)
            try:
                engine = LearningEngine(db_path=db_path)

                # 1. Detection
                self.assertTrue(engine.detect_correction("No, I meant use postgresql instead of sqlite", "I have configured SQLite"))
                self.assertTrue(engine.detect_correction("Don't use var, use const instead", "var x = 10;"))
                self.assertFalse(engine.detect_correction("Sounds great, please proceed", "Will do!"))

                # 2. Rule extraction
                corr = engine.extract_rule(
                    user_message="Don't use requests, use aiohttp instead",
                    previous_assistant="import requests\nresp = requests.get(url)",
                    context="/Users/test/project",
                )
                self.assertIn("aiohttp", corr.learned_rule)
                self.assertTrue("requests" in corr.trigger.lower() or "requests" in corr.learned_rule.lower())

                # 3. Persistence
                engine.record_correction(corr)

                # Reload from fresh engine instance
                engine2 = LearningEngine(db_path=db_path)
                self.assertGreaterEqual(len(engine2._corrections), 1)
                saved_corr = engine2._corrections[0]
                self.assertEqual(saved_corr.id, corr.id)

                # 4. Prompt injection
                injection = engine2.build_prompt_injection(context="project", user_prompt="make an http call with requests")
                self.assertIn("<learned_corrections>", injection)
                self.assertIn("aiohttp", injection)
            finally:
                if db_path.exists():
                    db_path.unlink()

        asyncio.run(_test())

    def test_speculative_engine(self) -> None:
        """Test speculative execution prefetching."""
        async def _test():
            spec = SpeculativeEngine()
            context = ToolContext(cwd=os.getcwd())

            test_file = os.path.abspath("lucy/core/learning.py")
            results = await spec.speculate("Read", {"file_path": test_file}, context)
            self.assertIsInstance(results, dict)

            bash_results = await spec.speculate("Bash", {"command": "pytest tests/test_lucy.py"}, context)
            self.assertIsInstance(bash_results, dict)

        asyncio.run(_test())

    def test_context_engine(self) -> None:
        """Test ContextEngine token counting, tool selection, and compaction."""
        engine = ContextEngine(max_tokens=1000)

        # 1. Token estimation
        sample_text = "Hello world! This is a test of token estimation in Lucy Code."
        tokens = engine.estimate_tokens(sample_text)
        self.assertGreater(tokens, 0)

        user_msg = create_user_message(sample_text)
        msg_tokens = engine.estimate_tokens(user_msg)
        self.assertGreaterEqual(msg_tokens, tokens)

        # 2. Dynamic tool selection
        tools = [
            DummyReadTool(),
            DummyWriteTool(),
        ]
        selected = engine.select_tools(tools, "Please read the test data")
        self.assertTrue(any(t.name == "DummyRead" for t in selected))

        # 3. Smart compaction
        msgs = [
            create_user_message("Initial goal: refactor the database"),
            AssistantMessage(content=[
                TextBlock(text="Refactoring step 1"),
                ToolUseBlock(id="u1", name="FileEdit", input={"file_path": "models.py"}),
            ]),
            UserMessage(content=[ToolResultBlock(tool_use_id="u1", content="Success")]),
            create_user_message("Recent turn 1"),
            AssistantMessage(content=[TextBlock(text="Working on recent turn 1")]),
            create_user_message("Recent turn 2"),
        ]
        compacted = engine.smart_compact(msgs, preserve_recent=3)
        self.assertLess(len(compacted), len(msgs))
        self.assertEqual(compacted[0].get_text(), "Initial goal: refactor the database")
        self.assertIn("models.py", compacted[1].summary)

        # 4. Diff-aware context
        orig = "def foo():\n    return 1\n"
        new = "def foo():\n    return 2\n"
        diff = engine.diff_aware_context("test.py", orig, new)
        self.assertIn("-    return 1", diff)
        self.assertIn("+    return 2", diff)


if __name__ == "__main__":
    unittest.main()
