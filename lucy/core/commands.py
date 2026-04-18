"""
Slash command system.

Commands are invoked via /name in the REPL.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Callable

from lucy.core.state import AppState


@dataclass
class CommandResult:
    """Result of a command execution."""
    output: str = ""
    error: str | None = None
    should_exit: bool = False
    clear_screen: bool = False


class Command(ABC):
    """Base class for slash commands."""

    @property
    @abstractmethod
    def name(self) -> str:
        ...

    @property
    def aliases(self) -> list[str]:
        return []

    @property
    @abstractmethod
    def description(self) -> str:
        ...

    @abstractmethod
    async def execute(self, args: str, state: AppState) -> CommandResult:
        ...

    def matches(self, input_name: str) -> bool:
        return input_name == self.name or input_name in self.aliases


# ---------------------------------------------------------------------------
# Built-in commands
# ---------------------------------------------------------------------------

class HelpCommand(Command):
    @property
    def name(self) -> str:
        return "help"

    @property
    def description(self) -> str:
        return "Show available commands"

    async def execute(self, args: str, state: AppState) -> CommandResult:
        lines = ["Available commands:\n"]
        for cmd in get_all_commands():
            aliases = f" (aliases: {', '.join(cmd.aliases)})" if cmd.aliases else ""
            lines.append(f"  /{cmd.name}{aliases} — {cmd.description}")
        return CommandResult(output="\n".join(lines))


class ClearCommand(Command):
    @property
    def name(self) -> str:
        return "clear"

    @property
    def description(self) -> str:
        return "Clear the conversation and start fresh"

    async def execute(self, args: str, state: AppState) -> CommandResult:
        state.messages.clear()
        return CommandResult(output="Conversation cleared.", clear_screen=True)


class ExitCommand(Command):
    @property
    def name(self) -> str:
        return "exit"

    @property
    def aliases(self) -> list[str]:
        return ["quit", "q"]

    @property
    def description(self) -> str:
        return "Exit Lucy Code"

    async def execute(self, args: str, state: AppState) -> CommandResult:
        return CommandResult(output="Goodbye!", should_exit=True)


class CostCommand(Command):
    @property
    def name(self) -> str:
        return "cost"

    @property
    def description(self) -> str:
        return "Show session cost and token usage"

    async def execute(self, args: str, state: AppState) -> CommandResult:
        c = state.cost
        lines = [
            "Session usage:",
            f"  Model: {state.model}",
            f"  Turns: {c.turn_count}",
            f"  Input tokens:  {c.total_input_tokens:,}",
            f"  Output tokens: {c.total_output_tokens:,}",
            f"  Cache created: {c.total_cache_creation_tokens:,}",
            f"  Cache read:    {c.total_cache_read_tokens:,}",
            f"  Total cost:    {c.format_cost()}",
        ]
        return CommandResult(output="\n".join(lines))


class ModelCommand(Command):
    @property
    def name(self) -> str:
        return "model"

    @property
    def description(self) -> str:
        return "Show or change the current model"

    async def execute(self, args: str, state: AppState) -> CommandResult:
        if not args.strip():
            return CommandResult(output=f"Current model: {state.model}")
        from lucy.api.models import resolve_model
        new_model = resolve_model(args.strip())
        state.model = new_model
        return CommandResult(output=f"Model changed to: {new_model}")


class VersionCommand(Command):
    @property
    def name(self) -> str:
        return "version"

    @property
    def description(self) -> str:
        return "Show Lucy Code version"

    async def execute(self, args: str, state: AppState) -> CommandResult:
        from lucy import __version__
        return CommandResult(output=f"Lucy Code v{__version__}")


class CompactCommand(Command):
    @property
    def name(self) -> str:
        return "compact"

    @property
    def description(self) -> str:
        return "Summarize the conversation to free context space"

    async def execute(self, args: str, state: AppState) -> CommandResult:
        msg_count = len(state.messages)
        if msg_count < 6:
            return CommandResult(output="Conversation is too short to compact.")
        try:
            from lucy.utils.compact import compact_messages
            new_messages, summary = await compact_messages(
                state.messages, model=state.model
            )
            removed = msg_count - len(new_messages)
            state.messages = new_messages
            if summary:
                preview = summary[:500] + ("..." if len(summary) > 500 else "")
                return CommandResult(
                    output=f"Compacted: summarized {removed} older messages.\n\nSummary:\n{preview}"
                )
            return CommandResult(output=f"Compacted: removed {removed} older messages.")
        except Exception:
            keep = min(6, msg_count)
            removed = msg_count - keep
            state.messages = state.messages[-keep:]
            return CommandResult(
                output=f"Compacted (simple): removed {removed} messages, kept {keep}."
            )


class ConfigCommand(Command):
    @property
    def name(self) -> str:
        return "config"

    @property
    def description(self) -> str:
        return "Show current configuration"

    async def execute(self, args: str, state: AppState) -> CommandResult:
        from lucy.core.config import get_config
        config = get_config()
        lines = [
            "Configuration:",
            f"  Model:      {config.model}",
            f"  Theme:      {config.theme}",
            f"  Thinking:   {'enabled' if config.thinking_enabled else 'disabled'}",
            f"  Permission: {config.permission_mode}",
            f"  Base URL:   {config.base_url}",
            f"  Verbose:    {config.verbose}",
        ]
        return CommandResult(output="\n".join(lines))


class SessionsCommand(Command):
    @property
    def name(self) -> str:
        return "sessions"

    @property
    def aliases(self) -> list[str]:
        return ["history"]

    @property
    def description(self) -> str:
        return "List, save, or load sessions"

    async def execute(self, args: str, state: AppState) -> CommandResult:
        from lucy.utils.session import list_sessions, load_session, save_session

        args = args.strip()

        if args.startswith("save"):
            title = args[4:].strip() or "Untitled"
            save_session(
                session_id=state.conversation_id,
                messages=state.messages,
                title=title,
                model=state.model,
                cwd=state.cwd,
                total_cost=state.cost.total_cost,
            )
            return CommandResult(
                output=f"Session saved: {state.conversation_id}\n  Title: {title}"
            )

        if args.startswith("load "):
            session_id = args[5:].strip()
            msgs, info = load_session(session_id)
            if msgs:
                state.messages = msgs
                title = info.title if info else session_id
                return CommandResult(
                    output=f"Loaded session: {title}\n  {len(msgs)} messages restored."
                )
            return CommandResult(error=f"Session not found: {session_id}")

        sessions = list_sessions(limit=15)
        if not sessions:
            return CommandResult(output="No sessions found.")

        lines = ["Recent sessions:\n"]
        lines.append(f"  {'ID':<36}  {'Title':<35}  {'Msgs':>5}")
        lines.append("  " + "\u2500" * 80)
        for s in sessions:
            title = (s.title or s.first_prompt or "Untitled")[:35]
            lines.append(f"  {s.session_id:<36}  {title:<35}  {s.message_count:>5}")
        lines.append("\n  Use /sessions load <id> to resume.")
        return CommandResult(output="\n".join(lines))


class HooksCommand(Command):
    @property
    def name(self) -> str:
        return "hooks"

    @property
    def description(self) -> str:
        return "Show registered hooks"

    async def execute(self, args: str, state: AppState) -> CommandResult:
        from lucy.core.hooks import get_hook_registry, HookCommand as HC, HookCallbackDef

        registry = get_hook_registry()
        hooks = registry.get_all()

        if not hooks:
            return CommandResult(
                output="No hooks registered.\n  Configure in ~/.lucy/hooks.json"
            )

        lines = [f"Registered hooks ({len(hooks)}):\n"]
        for hook in hooks:
            if isinstance(hook, HC):
                status = "\u2713" if hook.enabled else "\u2717"
                lines.append(f"  {status} [{hook.event.value}] {hook.name or hook.command[:50]}")
            elif isinstance(hook, HookCallbackDef):
                lines.append(f"  \u2713 [{hook.event.value}] {hook.name} (callback)")
        return CommandResult(output="\n".join(lines))


class PluginsCommand(Command):
    @property
    def name(self) -> str:
        return "plugins"

    @property
    def description(self) -> str:
        return "List installed plugins"

    async def execute(self, args: str, state: AppState) -> CommandResult:
        from lucy.core.plugins import get_plugin_manager

        mgr = get_plugin_manager()
        mgr.initialize()
        plugins = mgr.get_all_plugins()

        if not plugins:
            return CommandResult(
                output="No plugins installed.\n  Place plugins in ~/.lucy/plugins/"
            )

        lines = [f"Installed plugins ({len(plugins)}):\n"]
        for p in plugins:
            status = "\u2713" if p.enabled else "\u2717"
            lines.append(f"  {status} {p.name} v{p.manifest.version}")
            if p.manifest.description:
                lines.append(f"    {p.manifest.description}")
        return CommandResult(output="\n".join(lines))


class MCPCommand(Command):
    @property
    def name(self) -> str:
        return "mcp"

    @property
    def description(self) -> str:
        return "Show MCP server connections and tools"

    async def execute(self, args: str, state: AppState) -> CommandResult:
        from lucy.services.mcp import get_mcp_manager

        mgr = get_mcp_manager()
        connections = mgr.get_connections()

        if not connections:
            return CommandResult(
                output="No MCP servers connected.\n  Configure in ~/.lucy/mcp.json"
            )

        lines = [f"MCP servers ({len(connections)}):\n"]
        for name, conn in connections.items():
            status = "\u2713 connected" if conn.is_connected else "\u2717 disconnected"
            lines.append(f"  {name}: {status}")
            for tool in conn.tools:
                lines.append(f"    \U0001f527 {tool.name}: {tool.description[:60]}")
        return CommandResult(output="\n".join(lines))


class StatusCommand(Command):
    @property
    def name(self) -> str:
        return "status"

    @property
    def aliases(self) -> list[str]:
        return ["info"]

    @property
    def description(self) -> str:
        return "Show system status overview"

    async def execute(self, args: str, state: AppState) -> CommandResult:
        from lucy.core.hooks import get_hook_registry
        from lucy.core.plugins import get_plugin_manager
        from lucy.core.tool import get_tool_registry
        from lucy.native_bindings import is_native_available
        from lucy.services.ide import detect_ide, get_ide_name
        from lucy.services.mcp import get_mcp_manager

        reg = get_tool_registry()
        hook_reg = get_hook_registry()
        plugin_mgr = get_plugin_manager()
        mcp_mgr = get_mcp_manager()
        ide = detect_ide()

        lines = [
            "Lucy Code Status:",
            f"  Session:     {state.conversation_id[:8]}...",
            f"  Model:       {state.model}",
            f"  CWD:         {state.cwd}",
            f"  Messages:    {len(state.messages)}",
            f"  Cost:        {state.cost.format_cost()}",
            f"  Tools:       {len(reg.get_all())}",
            f"  Hooks:       {len(hook_reg.get_all())}",
            f"  Plugins:     {len(plugin_mgr.get_all_plugins())}",
            f"  MCP servers: {len(mcp_mgr.get_connections())}",
            f"  IDE:         {get_ide_name(ide)}",
            f"  Native C:    {'available' if is_native_available() else 'not built'}",
        ]
        return CommandResult(output="\n".join(lines))


class TasksCommand(Command):
    @property
    def name(self) -> str:
        return "tasks"

    @property
    def description(self) -> str:
        return "List background tasks"

    async def execute(self, args: str, state: AppState) -> CommandResult:
        from lucy.core.background import get_task_manager
        mgr = get_task_manager()

        args = args.strip()
        if args.startswith("cancel "):
            task_id = args[7:].strip()
            if mgr.cancel(task_id):
                return CommandResult(output=f"Task {task_id} cancelled.")
            return CommandResult(error=f"Task not found or already done: {task_id}")

        return CommandResult(output=mgr.format_status())


class MemoryCommand(Command):
    @property
    def name(self) -> str:
        return "memory"

    @property
    def description(self) -> str:
        return "Search or show memory stats"

    async def execute(self, args: str, state: AppState) -> CommandResult:
        from lucy.core.memory import get_memory_store
        store = get_memory_store()

        args = args.strip()
        if args.startswith("search "):
            query = args[7:].strip()
            result = store.retrieve_relevant(query)
            return CommandResult(output=result or "No memories found.")

        stats = store.get_stats()
        lines = [
            "Memory Store:",
            f"  Episodic:   {stats['episodic']} entries",
            f"  Semantic:   {stats['semantic']} entries",
            f"  Procedural: {stats['procedural']} entries",
            "\n  Use /memory search <query> to search.",
        ]
        return CommandResult(output="\n".join(lines))


class DreamCommand(Command):
    @property
    def name(self) -> str:
        return "dream"

    @property
    def description(self) -> str:
        return "Run AutoDream or list reports"

    async def execute(self, args: str, state: AppState) -> CommandResult:
        from lucy.services.autodream import AutoDream, list_dream_reports

        args = args.strip()
        if args == "run":
            dreamer = AutoDream(state.cwd)
            report = await dreamer.run()
            return CommandResult(
                output=f"Dream complete: {len(report.findings)} findings.\n"
                f"Report: {report.save()}"
            )

        reports = list_dream_reports()
        if not reports:
            return CommandResult(output="No dream reports.\n  Use /dream run to start.")

        lines = ["Dream reports:\n"]
        for r in reports[:10]:
            lines.append(f"  {r['name']}")
        return CommandResult(output="\n".join(lines))


class VoiceCommand(Command):
    @property
    def name(self) -> str:
        return "voice"

    @property
    def description(self) -> str:
        return "Voice mode status"

    async def execute(self, args: str, state: AppState) -> CommandResult:
        from lucy.services.voice import VoiceMode

        vm = VoiceMode()
        status = vm.get_status()
        avail = "\u2713 available" if status["available"] else "\u2717 not available (install sounddevice)"
        lines = [
            "Voice Mode:",
            f"  Audio input:  {avail}",
            f"  State:        {status['state']}",
            f"  TTS engine:   {status['tts_engine']}",
            f"  Whisper:      {status['whisper_model']}",
        ]
        return CommandResult(output="\n".join(lines))


class RemoteCommand(Command):
    @property
    def name(self) -> str:
        return "remote"

    @property
    def description(self) -> str:
        return "Remote server status"

    async def execute(self, args: str, state: AppState) -> CommandResult:
        lines = [
            "Remote Mode:",
            "  Server: not running",
            "  Use `lucy --serve` to start the remote server.",
            "  Use `lucy --connect <host:port>` to connect as a client.",
        ]
        return CommandResult(output="\n".join(lines))


class QRCommand(Command):
    @property
    def name(self) -> str:
        return "qr"

    @property
    def description(self) -> str:
        return "Display QR code for mobile access"

    async def execute(self, args: str, state: AppState) -> CommandResult:
        from lucy.services.mobile_qr import display_mobile_qr
        output = display_mobile_qr(token="demo-token", session_id=state.conversation_id)
        return CommandResult(output=output)


class InitCommand(Command):
    @property
    def name(self) -> str:
        return "init"

    @property
    def description(self) -> str:
        return "Create LUCY.md project instructions file"

    async def execute(self, args: str, state: AppState) -> CommandResult:
        import os
        filepath = os.path.join(state.cwd, "LUCY.md")
        if os.path.exists(filepath):
            return CommandResult(output=f"LUCY.md already exists at {filepath}")

        template = """# Project Instructions

## Overview
<!-- Describe your project here -->

## Architecture
<!-- Describe the architecture -->

## Code Style
- Follow consistent naming conventions
- Add comments for complex logic
- Keep functions focused and small

## Testing
<!-- How to run tests -->

## Important Notes
<!-- Any gotchas or important context -->
"""
        try:
            with open(filepath, "w") as f:
                f.write(template)
            return CommandResult(output=f"Created {filepath}\nEdit this file to add project-specific instructions.")
        except OSError as e:
            return CommandResult(error=f"Failed to create LUCY.md: {e}")


class DoctorCommand(Command):
    @property
    def name(self) -> str:
        return "doctor"

    @property
    def description(self) -> str:
        return "Run system diagnostics"

    async def execute(self, args: str, state: AppState) -> CommandResult:
        import shutil
        import sys
        from lucy.api.models import MODELS, is_offline_model
        from lucy.native_bindings import is_native_available

        checks = []

        # Python version
        py_ver = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
        checks.append(f"  ✓ Python {py_ver}")

        # API key
        api_key = state.model and not is_offline_model(state.model)
        if api_key:
            from lucy.core.config import get_config
            cfg = get_config()
            if cfg.api_key:
                checks.append(f"  ✓ API key: {cfg.api_key[:8]}...{cfg.api_key[-4:]}")
            else:
                checks.append("  ✗ API key: not set (set ANTHROPIC_API_KEY)")

        # Model
        checks.append(f"  ✓ Model: {state.model}")

        # Native extensions
        checks.append(f"  {'✓' if is_native_available() else '✗'} Native C extensions")

        # Git
        if shutil.which("git"):
            checks.append("  ✓ Git: available")
        else:
            checks.append("  ✗ Git: not found")

        # Optional dependencies
        for pkg, name in [
            ("sounddevice", "Voice input"),
            ("whisper", "Whisper transcription"),
            ("aiohttp", "Async HTTP (offline models)"),
            ("qrcode", "QR code generation"),
        ]:
            try:
                __import__(pkg)
                checks.append(f"  ✓ {name} ({pkg})")
            except ImportError:
                checks.append(f"  ⚠ {name} ({pkg}): not installed")

        # Ollama
        try:
            import aiohttp
            import asyncio
            async def _check_ollama():
                try:
                    async with aiohttp.ClientSession() as sess:
                        async with sess.get("http://localhost:11434/api/tags",
                                           timeout=aiohttp.ClientTimeout(total=2)) as r:
                            if r.status == 200:
                                data = await r.json()
                                models = [m["name"] for m in data.get("models", [])]
                                return models
                except Exception:
                    return None
            models = await _check_ollama()
            if models:
                checks.append(f"  ✓ Ollama: {len(models)} models ({', '.join(models[:3])}{'...' if len(models) > 3 else ''})")
            else:
                checks.append("  ⚠ Ollama: not running (start with `ollama serve`)")
        except ImportError:
            checks.append("  ⚠ Ollama: aiohttp needed (pip install aiohttp)")

        # LUCY.md
        import os
        lucymd = os.path.join(state.cwd, "LUCY.md")
        checks.append(f"  {'✓' if os.path.exists(lucymd) else '⚠'} LUCY.md: {'found' if os.path.exists(lucymd) else 'not found (use /init)'}")

        heading = "Lucy Code Doctor"
        return CommandResult(output=f"{heading}\n" + "\n".join(checks))


class UndoCommand(Command):
    @property
    def name(self) -> str:
        return "undo"

    @property
    def description(self) -> str:
        return "Undo last file change"

    async def execute(self, args: str, state: AppState) -> CommandResult:
        from lucy.utils.diff_preview import get_undo_manager

        mgr = get_undo_manager()
        args = args.strip()

        if args == "list":
            history = mgr.get_history()
            if not history:
                return CommandResult(output="No changes to undo.")
            lines = ["Recent changes:\n"]
            for ch in history:
                import os, time as t
                ts = t.strftime("%H:%M:%S", t.localtime(ch.timestamp))
                lines.append(f"  [{ts}] {ch.change_type}: {os.path.basename(ch.filepath)}")
            return CommandResult(output="\n".join(lines))

        if args == "preview":
            diff = mgr.preview_last()
            if not diff:
                return CommandResult(output="No changes to preview.")
            return CommandResult(output=diff)

        # Undo
        if args:
            change = mgr.undo_file(args)
        else:
            change = mgr.undo_last()

        if change:
            import os
            return CommandResult(
                output=f"Undone {change.change_type} on {os.path.basename(change.filepath)}"
            )
        return CommandResult(output="Nothing to undo.")


class PlanCommand(Command):
    @property
    def name(self) -> str:
        return "plan"

    @property
    def description(self) -> str:
        return "Create or show execution plan"

    async def execute(self, args: str, state: AppState) -> CommandResult:
        from lucy.core.agentic import PlanningAgent

        agent = PlanningAgent()
        args = args.strip()

        if not args:
            plan = agent.get_current_plan()
            if plan:
                return CommandResult(output=plan.to_markdown())
            return CommandResult(output="No active plan. Use /plan <goal> to create one.")

        plan = await agent.create_plan(args, context=f"CWD: {state.cwd}")
        return CommandResult(output=plan.to_markdown())


class ModelsCommand(Command):
    @property
    def name(self) -> str:
        return "models"

    @property
    def description(self) -> str:
        return "List all available models (cloud + offline)"

    async def execute(self, args: str, state: AppState) -> CommandResult:
        from lucy.api.models import MODELS, MODEL_ALIASES, is_offline_model

        lines = ["Available models:\n"]

        # Cloud models
        lines.append("  ☁️  Cloud (API key required):")
        for mid, info in MODELS.items():
            if not is_offline_model(mid):
                current = " ← current" if mid == state.model else ""
                lines.append(f"    {info.name} ({mid}){current}")
                lines.append(f"      Context: {info.context_window:,} | ${info.input_price_per_mtok}/M in, ${info.output_price_per_mtok}/M out")

        # Offline models
        lines.append("\n  🏠 Offline (local, free):")
        for mid, info in MODELS.items():
            if is_offline_model(mid):
                current = " ← current" if mid == state.model else ""
                lines.append(f"    {info.name} ({mid}){current}")
                lines.append(f"      Context: {info.context_window:,} | Free")

        # Aliases
        lines.append("\n  🏷️  Shortcuts:")
        for alias, target in sorted(MODEL_ALIASES.items()):
            lines.append(f"    {alias} → {target}")

        lines.append(f"\n  Use /model <name> to switch. Current: {state.model}")
        return CommandResult(output="\n".join(lines))


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

_COMMANDS: list[Command] = [
    HelpCommand(),
    ClearCommand(),
    ExitCommand(),
    CostCommand(),
    ModelCommand(),
    VersionCommand(),
    CompactCommand(),
    ConfigCommand(),
    SessionsCommand(),
    HooksCommand(),
    PluginsCommand(),
    MCPCommand(),
    StatusCommand(),
    TasksCommand(),
    MemoryCommand(),
    DreamCommand(),
    VoiceCommand(),
    RemoteCommand(),
    QRCommand(),
    InitCommand(),
    DoctorCommand(),
    UndoCommand(),
    PlanCommand(),
    ModelsCommand(),
]


def _register_extended_commands():
    """Register Phase 4 command modules."""
    modules = [
        "lucy.commands.git_commands",
        "lucy.commands.session_commands",
        "lucy.commands.context_commands",
        "lucy.commands.review_commands",
        "lucy.commands.debug_commands",
        "lucy.commands.ui_commands",
        "lucy.commands.auth_commands",
        "lucy.commands.billing_commands",
        "lucy.commands.misc_commands",
        "lucy.commands.agent_commands",
        "lucy.commands.permission_commands",
        "lucy.commands.task_commands",
        "lucy.commands.mcp_commands",
        "lucy.commands.memory_commands",
        "lucy.commands.plan_commands",
        "lucy.commands.plugin_commands",
    ]
    for mod_name in modules:
        try:
            import importlib
            mod = importlib.import_module(mod_name)
            if hasattr(mod, "get_commands"):
                for cmd in mod.get_commands():
                    # Skip if name conflicts with existing
                    if not any(c.name == cmd.name for c in _COMMANDS):
                        _COMMANDS.append(cmd)
        except ImportError:
            pass  # Module not available


_register_extended_commands()


def get_all_commands() -> list[Command]:
    return list(_COMMANDS)


def find_command(name: str) -> Command | None:
    for cmd in _COMMANDS:
        if cmd.matches(name):
            return cmd
    return None


def parse_command_input(text: str) -> tuple[str, str] | None:
    """Parse a /command input. Returns (command_name, args) or None."""
    text = text.strip()
    if not text.startswith("/"):
        return None
    parts = text[1:].split(None, 1)
    if not parts:
        return None
    name = parts[0].lower()
    args = parts[1] if len(parts) > 1 else ""
    return name, args

