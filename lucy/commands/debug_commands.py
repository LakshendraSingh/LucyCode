"""
Debug commands — /doctor, /debug-tool-call, /env.
"""

from __future__ import annotations

import os
import platform
import shutil
import subprocess
import sys
from typing import Any

from lucy.core.commands import Command, CommandResult


class DoctorCommand(Command):
    @property
    def name(self) -> str: return "doctor"
    @property
    def aliases(self) -> list[str]: return ["diag", "diagnostics"]
    @property
    def description(self) -> str: return "Run diagnostic checks"
    @property
    def usage(self) -> str: return "/doctor — check system health"

    async def execute(self, args: str, state: Any) -> CommandResult:
        from lucy.core.config import get_config
        config = get_config()
        checks = []

        # Python version
        py = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
        checks.append(f"✅ Python: {py}")

        # Platform
        checks.append(f"✅ Platform: {platform.system()} {platform.machine()}")

        # API key
        if config.api_key:
            masked = config.api_key[:8] + "..." + config.api_key[-4:]
            checks.append(f"✅ API key: {masked}")
        else:
            checks.append(f"⚠️  API key: not set (using offline model)")

        # Model
        checks.append(f"✅ Model: {config.model}")

        # Git
        git = shutil.which("git")
        if git:
            r = subprocess.run(["git", "--version"], capture_output=True, text=True)
            checks.append(f"✅ Git: {r.stdout.strip()}")
        else:
            checks.append(f"❌ Git: not found")

        # Tools available
        for tool_name in ["rg", "fd", "jq", "pwsh", "node", "npm", "cargo"]:
            path = shutil.which(tool_name)
            if path:
                checks.append(f"✅ {tool_name}: {path}")
            else:
                checks.append(f"⬜ {tool_name}: not found (optional)")

        # Config directory
        checks.append(f"✅ Config: {config.config_dir}")
        checks.append(f"✅ Sessions: {config.sessions_dir}")

        # Installed packages
        for pkg in ["anthropic", "aiohttp", "rich", "click"]:
            try:
                __import__(pkg)
                checks.append(f"✅ {pkg}: installed")
            except ImportError:
                checks.append(f"❌ {pkg}: not installed")

        return CommandResult(output="🩺 Lucy Code Doctor\n\n" + "\n".join(checks))


class DebugToolCallCommand(Command):
    @property
    def name(self) -> str: return "debug-tool-call"
    @property
    def aliases(self) -> list[str]: return ["dtc"]
    @property
    def description(self) -> str: return "Debug the last tool call"
    @property
    def usage(self) -> str: return "/debug-tool-call"

    async def execute(self, args: str, state: Any) -> CommandResult:
        from lucy.core.message import AssistantMessage, UserMessage, ToolUseBlock, ToolResultBlock
        # Find last tool use and result
        tool_uses = []
        for m in reversed(state.messages):
            if isinstance(m, AssistantMessage):
                blocks = m.get_tool_use_blocks()
                if blocks:
                    tool_uses.extend(blocks)
                    break

        if not tool_uses:
            return CommandResult(output="No tool calls found in conversation.")

        lines = ["Last tool call(s):\n"]
        for tu in tool_uses:
            lines.append(f"  Tool: {tu.name}")
            lines.append(f"  ID: {tu.id}")
            import json
            lines.append(f"  Input: {json.dumps(tu.input, indent=2)[:500]}")

        # Find corresponding result
        for m in reversed(state.messages):
            if isinstance(m, UserMessage) and isinstance(m.content, list):
                for block in m.content:
                    if isinstance(block, ToolResultBlock):
                        lines.append(f"\n  Result (error={block.is_error}):")
                        content = str(block.content)[:500]
                        lines.append(f"  {content}")
                        break
                break

        return CommandResult(output="\n".join(lines))


class EnvCommand(Command):
    @property
    def name(self) -> str: return "env"
    @property
    def description(self) -> str: return "Show environment information"
    @property
    def usage(self) -> str: return "/env — show relevant env vars"

    async def execute(self, args: str, state: Any) -> CommandResult:
        relevant = [
            "ANTHROPIC_API_KEY", "ANTHROPIC_BASE_URL",
            "LUCY_MODEL", "LUCY_VERBOSE", "LUCY_THEME",
            "OLLAMA_HOST", "OPENAI_API_KEY", "OPENAI_BASE_URL",
            "HTTP_PROXY", "HTTPS_PROXY",
            "SHELL", "TERM", "LANG", "PATH",
        ]
        lines = ["Environment:\n"]
        for key in relevant:
            val = os.environ.get(key, "")
            if val:
                # Mask sensitive values
                if "KEY" in key or "SECRET" in key or "TOKEN" in key:
                    val = val[:8] + "..." + val[-4:] if len(val) > 12 else "***"
                lines.append(f"  {key}={val}")
            else:
                lines.append(f"  {key}=(not set)")

        return CommandResult(output="\n".join(lines))


def get_commands() -> list[Command]:
    return [DoctorCommand(), DebugToolCallCommand(), EnvCommand()]
