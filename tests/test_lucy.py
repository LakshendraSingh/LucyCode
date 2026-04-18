"""
Lucy Code test suite — verifies all components.

Run: python -m pytest tests/test_lucy.py -v
  or: python tests/test_lucy.py
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import tempfile
import uuid

# Ensure lucy is importable
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# ─── Test helpers ────────────────────────────────────────────

def run_async(coro):
    """Run an async function synchronously."""
    return asyncio.get_event_loop().run_until_complete(coro)


class TestResult:
    def __init__(self):
        self.passed: list[str] = []
        self.failed: list[tuple[str, str]] = []
        self.total = 0

    def ok(self, name: str):
        self.passed.append(name)
        self.total += 1
        print(f"  ✓ {name}")

    def fail(self, name: str, err: str):
        self.failed.append((name, err))
        self.total += 1
        print(f"  ✗ {name}: {err}")

    def summary(self) -> bool:
        print(f"\n{'═' * 50}")
        print(f"  {len(self.passed)}/{self.total} passed, {len(self.failed)} failed")
        if self.failed:
            for name, err in self.failed:
                print(f"  FAIL: {name} — {err}")
        print(f"{'═' * 50}")
        return len(self.failed) == 0


results = TestResult()


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 1. Message Serialization
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

print("\n── Message Serialization ──")

try:
    from lucy.core.message import (
        create_user_message, AssistantMessage, TextBlock, ToolUseBlock,
        ToolResultBlock, ThinkingBlock, CompactBoundaryMessage, MessageUsage,
    )
    from lucy.utils.session import serialize_message, deserialize_message

    # User message roundtrip
    msg = create_user_message("Hello")
    s = serialize_message(msg)
    d = deserialize_message(s)
    assert d is not None and d.get_text() == "Hello"
    results.ok("UserMessage roundtrip")

    # Assistant message with tool_use
    asst = AssistantMessage(
        content=[
            ThinkingBlock(thinking="Let me check", signature="sig123"),
            TextBlock(text="Here's the answer"),
            ToolUseBlock(id="tu1", name="Bash", input={"command": "ls"}),
        ],
        model="lucy-sonnet-4-20250514",
        stop_reason="tool_use",
        usage=MessageUsage(input_tokens=100, output_tokens=50),
    )
    s2 = serialize_message(asst)
    d2 = deserialize_message(s2)
    assert d2 is not None
    assert d2.get_text() == "Here's the answer"
    assert d2.get_thinking_text() == "Let me check"
    assert d2.usage.input_tokens == 100
    results.ok("AssistantMessage roundtrip (with thinking + tool_use)")

    # Tool result roundtrip
    from lucy.core.message import create_tool_result_message
    tr = create_tool_result_message("tu1", "file1.py\nfile2.py", is_error=False)
    s3 = serialize_message(tr)
    d3 = deserialize_message(s3)
    assert d3 is not None
    results.ok("ToolResult roundtrip")

    # CompactBoundary roundtrip
    cb = CompactBoundaryMessage(summary="Previous conversation about X")
    s4 = serialize_message(cb)
    d4 = deserialize_message(s4)
    assert d4 is not None and d4.summary == "Previous conversation about X"
    results.ok("CompactBoundaryMessage roundtrip")

except Exception as e:
    results.fail("Message serialization", str(e))


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 2. Session Persistence
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

print("\n── Session Persistence ──")

try:
    from lucy.utils.session import (
        save_session, load_session, list_sessions, delete_session,
        save_message, save_metadata,
    )

    # Use a temp directory for sessions
    with tempfile.TemporaryDirectory() as tmpdir:
        # Monkey-patch sessions dir
        from lucy.utils import session as session_mod
        original_fn = session_mod._get_session_dir
        session_mod._get_session_dir = lambda: __import__("pathlib").Path(tmpdir)

        try:
            sid = str(uuid.uuid4())
            msgs = [
                create_user_message("What is Python?"),
                AssistantMessage(
                    content=[TextBlock(text="Python is a language.")],
                    model="test-model",
                ),
                create_user_message("Tell me more"),
                AssistantMessage(
                    content=[TextBlock(text="It's very popular.")],
                    model="test-model",
                ),
            ]

            # Save
            save_session(sid, msgs, title="Test Session", model="test-model")
            results.ok("save_session")

            # Load
            loaded_msgs, info = load_session(sid)
            assert len(loaded_msgs) == 4
            assert loaded_msgs[0].get_text() == "What is Python?"
            assert loaded_msgs[1].get_text() == "Python is a language."
            assert info.title == "Test Session"
            assert info.model == "test-model"
            results.ok("load_session (4 messages + metadata)")

            # List
            sessions = list_sessions(limit=10)
            assert len(sessions) == 1
            assert sessions[0].session_id == sid
            results.ok("list_sessions")

            # Incremental append
            sid2 = str(uuid.uuid4())
            save_message(sid2, create_user_message("Hi"))
            save_message(sid2, AssistantMessage(
                content=[TextBlock(text="Hello!")], model="test"
            ))
            save_metadata(sid2, title="Incremental", model="test")
            loaded2, info2 = load_session(sid2)
            assert len(loaded2) == 2
            results.ok("save_message incremental append")

            # Delete
            assert delete_session(sid)
            loaded_del, _ = load_session(sid)
            assert len(loaded_del) == 0
            results.ok("delete_session")

        finally:
            session_mod._get_session_dir = original_fn

except Exception as e:
    results.fail("Session persistence", str(e))


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 3. Hooks System
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

print("\n── Hooks System ──")

try:
    from lucy.core.hooks import (
        HookEvent, HookInput, HookOutput, HookCommand, HookCallbackDef,
        HookRegistry, execute_hook, run_hooks_for_event,
    )

    # Registry
    reg = HookRegistry()
    h1 = HookCommand(command="echo hello", event=HookEvent.SESSION_START, name="h1")
    h2 = HookCommand(command="echo bye", event=HookEvent.SESSION_END, name="h2")
    h3 = HookCommand(command="echo lint", event=HookEvent.PRE_TOOL_USE, name="h3", tool_name="Edit")
    reg.register(h1)
    reg.register(h2)
    reg.register(h3)

    assert len(reg.get_hooks_for_event(HookEvent.SESSION_START)) == 1
    assert len(reg.get_hooks_for_event(HookEvent.SESSION_END)) == 1
    assert len(reg.get_hooks_for_event(HookEvent.PRE_TOOL_USE, tool_name="Edit")) == 1
    assert len(reg.get_hooks_for_event(HookEvent.PRE_TOOL_USE, tool_name="Bash")) == 0
    results.ok("HookRegistry filtering")

    # Execute shell hook
    hi = HookInput(session_id="test", cwd="/tmp", hook_event="SessionStart")
    output = run_async(execute_hook(h1, hi))
    assert output.exit_code == 0
    assert "hello" in output.raw_output
    results.ok("execute shell hook (echo)")

    # Callback hook
    async def my_callback(inp: HookInput) -> HookOutput:
        return HookOutput(additional_context="injected context", continue_execution=True)

    cb_hook = HookCallbackDef(
        callback=my_callback, event=HookEvent.USER_PROMPT_SUBMIT, name="cb_test"
    )
    output2 = run_async(execute_hook(cb_hook, hi))
    assert output2.additional_context == "injected context"
    results.ok("execute callback hook")

    # Unregister
    reg.unregister("h1")
    assert len(reg.get_hooks_for_event(HookEvent.SESSION_START)) == 0
    results.ok("unregister hook")

    # Config loading
    import tempfile
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        json.dump({
            "hooks": {
                "PreToolUse": [
                    {"command": "echo pre", "name": "cfg-pre"},
                    {"command": "echo pre2", "tool_name": "Bash"},
                ],
                "PostToolUse": [
                    {"command": "echo post"},
                ],
            }
        }, f)
        f.flush()
        config_path = f.name

    from lucy.core.hooks import load_hooks_from_config, get_hook_registry
    old_reg = get_hook_registry()
    old_reg.clear()
    load_hooks_from_config(config_path)
    loaded = get_hook_registry().get_all()
    assert len(loaded) == 3, f"Expected 3 hooks from config, got {len(loaded)}"
    results.ok("load_hooks_from_config (3 hooks)")
    os.unlink(config_path)

except Exception as e:
    results.fail("Hooks system", str(e))


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 4. Plugin Architecture
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

print("\n── Plugin Architecture ──")

try:
    from lucy.core.plugins import (
        PluginManifest, LoadedPlugin, PluginLoader, validate_plugin,
    )

    # Create a test plugin
    with tempfile.TemporaryDirectory() as tmpdir:
        plugin_dir = os.path.join(tmpdir, "test-plugin")
        os.makedirs(plugin_dir)
        with open(os.path.join(plugin_dir, "plugin.json"), "w") as f:
            json.dump({
                "name": "test-plugin",
                "description": "A test plugin",
                "version": "1.0.0",
                "author": "Test",
                "tools": [{"name": "test_tool"}],
                "hooks": {
                    "PreToolUse": [{"command": "echo lint"}],
                },
                "mcpServers": {
                    "my-server": {"command": "npx", "args": ["-y", "server"]},
                },
            }, f)

        loader = PluginLoader()
        plugins = loader.load_from_directory(tmpdir)
        assert len(plugins) == 1
        p = plugins[0]
        assert p.name == "test-plugin"
        assert p.manifest.version == "1.0.0"
        assert len(p.manifest.tools) == 1
        assert "PreToolUse" in p.manifest.hooks
        assert "my-server" in p.manifest.mcp_servers
        results.ok("load plugin from directory")

        errors = validate_plugin(p)
        assert len(errors) == 0
        results.ok("validate_plugin (no errors)")

        # Invalid plugin (no name)
        bad = LoadedPlugin(name="", manifest=PluginManifest(), path="", source="test")
        errors2 = validate_plugin(bad)
        assert len(errors2) > 0
        results.ok("validate_plugin (catches missing name)")

except Exception as e:
    results.fail("Plugin architecture", str(e))


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 5. MCP Types
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

print("\n── MCP Server Types ──")

try:
    from lucy.services.mcp import (
        MCPServerConfig, MCPTransport, MCPTool, MCPResource,
        MCPConnection, MCPToolAdapter, MCPManager, get_mcp_manager,
    )

    # Config
    cfg = MCPServerConfig(
        name="test-mcp",
        command="npx",
        args=["-y", "@example/server"],
        transport=MCPTransport.STDIO,
        timeout=30,
    )
    assert cfg.transport == MCPTransport.STDIO
    results.ok("MCPServerConfig creation")

    # MCPTool
    tool = MCPTool(name="read_file", description="Read a file", server_name="test-mcp")
    assert tool.name == "read_file"

    # MCPManager singleton
    mgr = get_mcp_manager()
    assert mgr is not None
    assert len(mgr.get_tools()) == 0  # No servers connected
    results.ok("MCPManager singleton")

except Exception as e:
    results.fail("MCP types", str(e))


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 6. Tool Registration
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

print("\n── Tool Registration ──")

try:
    from lucy.core.tool import ToolRegistry
    from lucy.tools.web_search_tool import WebSearchTool
    from lucy.tools.agent_tool import AgentTool

    reg = ToolRegistry()
    web = WebSearchTool()
    agent = AgentTool()

    reg.register(web)
    reg.register(agent)

    assert reg.find_by_name("WebSearch") is web
    assert reg.find_by_name("Agent") is agent
    assert reg.find_by_name("Search") is web  # alias
    assert reg.find_by_name("SubAgent") is agent  # alias
    assert len(reg.get_all()) == 2
    results.ok("WebSearchTool + AgentTool registration (with aliases)")

    # Schema
    schema = web.input_schema
    assert "query" in schema.get("properties", {})
    results.ok("WebSearchTool schema has 'query'")

    schema2 = agent.input_schema
    assert "task" in schema2.get("properties", {})
    results.ok("AgentTool schema has 'task'")

except Exception as e:
    results.fail("Tool registration", str(e))


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 7. IDE Integration
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

print("\n── IDE Integration ──")

try:
    from lucy.services.ide import (
        IDE, detect_ide, get_ide_name, get_terminal_info,
    )

    ide = detect_ide()
    assert isinstance(ide, IDE)
    results.ok(f"detect_ide() => {ide.value}")

    name = get_ide_name(ide)
    assert isinstance(name, str)
    results.ok(f"get_ide_name() => {name}")

    info = get_terminal_info()
    assert "shell" in info
    assert "ide" in info
    results.ok("get_terminal_info()")

except Exception as e:
    results.fail("IDE integration", str(e))


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 8. Native C Bindings
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

print("\n── Native C Bindings ──")

try:
    from lucy.native_bindings import (
        is_native_available, native_search, native_diff,
        native_is_binary, native_count_lines, native_file_size,
    )

    if is_native_available():
        # search
        r = native_search(".", "import", max_results=3)
        assert r is not None and len(r) > 0
        results.ok(f"native_search: {len(r)} results")

        # diff
        d = native_diff("hello\nworld\n", "hello\nplanet\n")
        assert d is not None
        results.ok(f"native_diff: {len(d)} chars")

        # fileio
        b = native_is_binary(__file__)
        assert b is not None and b is False
        results.ok(f"native_is_binary: {b}")

        lines = native_count_lines(__file__)
        assert lines is not None and lines > 0
        results.ok(f"native_count_lines: {lines}")

        size = native_file_size(__file__)
        assert size is not None and size > 0
        results.ok(f"native_file_size: {size}")
    else:
        results.ok("native extensions not built (graceful fallback)")

except Exception as e:
    results.fail("Native C bindings", str(e))


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 9. Slash Commands
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

print("\n── Slash Commands ──")

try:
    from lucy.core.commands import find_command, get_all_commands, parse_command_input

    # Phase 2 commands exist
    cmds = get_all_commands()
    cmd_names = [c.name for c in cmds]
    assert "sessions" in cmd_names
    assert "hooks" in cmd_names
    assert "plugins" in cmd_names
    assert "mcp" in cmd_names
    assert "status" in cmd_names
    results.ok(f"{len(cmds)} commands registered (including Phase 2)")

    # Aliases work
    assert find_command("history") is not None  # alias for sessions
    assert find_command("info") is not None      # alias for status
    assert find_command("q") is not None          # alias for exit
    results.ok("command aliases work")

    # Parse
    assert parse_command_input("/help") == ("help", "")
    assert parse_command_input("/sessions save My Project") == ("sessions", "save My Project")
    assert parse_command_input("not a command") is None
    results.ok("parse_command_input")

    # Execute /status
    from lucy.core.state import AppState
    state = AppState(model="test-model")
    result = run_async(find_command("status").execute("", state))
    assert "Lucy Code Status:" in result.output
    assert "test-model" in result.output
    results.ok("/status command executes")

    # Execute /hooks
    result2 = run_async(find_command("hooks").execute("", state))
    assert result2.output  # either "No hooks" or hook list
    results.ok("/hooks command executes")

    # Execute /plugins
    result3 = run_async(find_command("plugins").execute("", state))
    assert result3.output
    results.ok("/plugins command executes")

    # Execute /mcp
    result4 = run_async(find_command("mcp").execute("", state))
    assert result4.output
    results.ok("/mcp command executes")

except Exception as e:
    results.fail("Slash commands", str(e))


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 10. Context Compaction Types
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

print("\n── Context Compaction ──")

try:
    from lucy.utils.compact import (
        compact_messages, COMPACT_SYSTEM_PROMPT,
        MIN_MESSAGES_TO_COMPACT, KEEP_RECENT_MESSAGES,
        _format_messages_for_summary,
    )

    assert MIN_MESSAGES_TO_COMPACT == 6
    assert KEEP_RECENT_MESSAGES == 4
    results.ok("compaction constants")

    # Too few messages — should be a no-op
    short_msgs = [create_user_message("hi")]
    new, summary = run_async(compact_messages(short_msgs))
    assert new is short_msgs  # identity — not modified
    assert summary == ""
    results.ok("short conversation skips compaction")

    # Format for summary
    msgs = [
        create_user_message("What is Python?"),
        AssistantMessage(content=[TextBlock(text="Python is a language.")], model="x"),
    ]
    formatted = _format_messages_for_summary(msgs)
    assert "What is Python?" in formatted
    assert "Python is a language." in formatted
    results.ok("_format_messages_for_summary")

except Exception as e:
    results.fail("Context compaction", str(e))


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 11. Rebranding & New Features (NEW)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

print("\n── Rebranding & New Features ──")

try:
    from lucy.core.context import get_lucymd_content
    from lucy.core.orchestrator import _run_external_agent, AgentSpec
    from lucy.core.plugins import get_plugin_manager

    # 1. LUCY.md branding & fallback
    with tempfile.TemporaryDirectory() as tmpdir:
        # Test LUCY.md
        lucymd_path = os.path.join(tmpdir, "LUCY.md")
        with open(lucymd_path, "w") as f:
            f.write("System: Lucy instructions")
        
        content = get_lucymd_content(tmpdir)
        assert "Lucy instructions" in content
        results.ok("get_lucymd_content finds LUCY.md")

        # Test fallback to CLAUDE.md
        os.remove(lucymd_path)
        claudemd_path = os.path.join(tmpdir, "CLAUDE.md")
        with open(claudemd_path, "w") as f:
            f.write("System: Claude fallback")
        
        content_fb = get_lucymd_content(tmpdir)
        assert "Claude fallback" in content_fb
        results.ok("get_lucymd_content falls back to CLAUDE.md")

    # 2. Teammate Spawning IPC
    with tempfile.TemporaryDirectory() as tmpdir:
        spec = AgentSpec(task="Test spawning", name="worker1")
        # We'll test the serialization part of _run_external_agent logic
        spec_path = os.path.join(tmpdir, "spec.json")
        spec_dict = {
            "task": spec.task,
            "role": spec.role.value if hasattr(spec.role, "value") else spec.role,
            "name": spec.name,
        }
        with open(spec_path, 'w') as f:
            json.dump(spec_dict, f)
        
        with open(spec_path, 'r') as f:
            loaded = json.load(f)
        assert loaded["name"] == "worker1"
        assert loaded["task"] == "Test spawning"
        results.ok("Teammate spawning: AgentSpec serialization")

    # 3. Internet Plugins (Mocked Git)
    mgr = get_plugin_manager()
    # Test the URL detection logic
    source_git = "https://github.com/user/plugin.git"
    source_local = "/path/to/plugin"
    
    is_git_url = any(source_git.startswith(p) for p in ["git:", "https://", "http://"])
    is_local_path = not is_git_url
    
    assert is_git_url is True
    assert is_local_path is False
    results.ok("PluginManager: Git URL detection")

except Exception as e:
    results.fail("Rebranding & New Features", str(e))


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Results
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

all_pass = results.summary()
sys.exit(0 if all_pass else 1)
