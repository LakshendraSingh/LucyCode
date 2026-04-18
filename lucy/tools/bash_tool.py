"""
BashTool — Execute shell commands.

Mirrors the original BashTool with timeout, output limits,
and dangerous command detection.
"""

from __future__ import annotations

import asyncio
import os
import shlex
from typing import Any

from lucy.core.tool import (
    PermissionBehavior,
    PermissionResult,
    Tool,
    ToolContext,
    ToolResult,
)

# Commands considered dangerous / destructive
DANGEROUS_PATTERNS = [
    "rm -rf /",
    "rm -rf ~",
    "mkfs",
    "> /dev/sd",
    "dd if=",
    ":(){:|:&};:",
    "chmod -R 777 /",
    "mv /* ",
]

DEFAULT_TIMEOUT = 120  # seconds
MAX_OUTPUT_CHARS = 100_000


class BashTool(Tool):
    """Execute shell commands in the user's environment."""

    @property
    def name(self) -> str:
        return "Bash"

    @property
    def is_core(self) -> bool:
        return True

    @property
    def description(self) -> str:
        return "Execute a shell command"

    @property
    def input_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "command": {
                    "type": "string",
                    "description": "The shell command to execute",
                },
                "timeout": {
                    "type": "integer",
                    "description": "Timeout in seconds (default: 120)",
                },
            },
            "required": ["command"],
        }

    def get_prompt(self) -> str:
        return (
            "Execute a shell command. The terminal is NON-INTERACTIVE. "
            "IMPORTANT: Do NOT attempt to run commands that start interactive shells (e.g. 'bash', 'zsh', 'sh', 'python', 'node') without arguments. "
            "Do NOT run commands that wait for user input (e.g. 'sudo' without a password hint, or editors like 'vim'). "
            "Always use one-shot, non-blocking commands. For long-running tasks, they will be timed out. "
            "Use this for running tests, installing dependencies, searching files, and git operations. "
            "Always prefer FileRead/FileWrite/FileEdit over 'cat' or 'sed' where possible."
        )

    def is_read_only(self, tool_input: dict[str, Any]) -> bool:
        cmd = tool_input.get("command", "")
        read_only_prefixes = [
            "cat ", "head ", "tail ", "less ", "more ", "wc ",
            "find ", "ls ", "tree ", "du ", "df ",
            "grep ", "rg ", "ag ", "git log", "git diff",
            "git status", "git branch", "echo ", "pwd", "which ",
            "env", "printenv", "whoami", "uname", "date",
            "python --version", "node --version", "npm --version",
        ]
        return any(cmd.strip().startswith(p) for p in read_only_prefixes)

    def is_destructive(self, tool_input: dict[str, Any]) -> bool:
        cmd = tool_input.get("command", "")
        return any(pat in cmd for pat in DANGEROUS_PATTERNS)

    async def check_permissions(
        self, tool_input: dict[str, Any], context: ToolContext
    ) -> PermissionResult:
        cmd = tool_input.get("command", "")
        if self.is_destructive(tool_input):
            return PermissionResult(
                behavior=PermissionBehavior.ASK,
                message=f"Dangerous command detected: {cmd}",
                updated_input=tool_input,
            )
        if not self.is_read_only(tool_input) and context.permission_mode == "default":
            return PermissionResult(
                behavior=PermissionBehavior.ASK,
                message=f"Run command: {cmd}",
                updated_input=tool_input,
            )
        return PermissionResult(
            behavior=PermissionBehavior.ALLOW,
            updated_input=tool_input,
        )

    def get_activity_description(self, tool_input: dict[str, Any] | None = None) -> str | None:
        if tool_input:
            cmd = tool_input.get("command", "")
            if len(cmd) > 60:
                cmd = cmd[:57] + "..."
            return f"Running `{cmd}`"
        return "Running command"

    async def call(self, tool_input: dict[str, Any], context: ToolContext) -> ToolResult:
        command = tool_input.get("command", "")
        timeout = tool_input.get("timeout", DEFAULT_TIMEOUT)

        if not command.strip():
            return ToolResult(error="Empty command")

        # Block common interactive commands that cause hangs
        parts = command.strip().split()
        if parts:
            base_cmd = os.path.basename(parts[0])
            interactive_blocks = ["bash", "zsh", "sh", "python", "python3", "node", "irb", "lua"]
            if base_cmd in interactive_blocks and len(parts) == 1:
                return ToolResult(error=f"Command '{base_cmd}' without arguments is interactive and will hang in this environment. Please specify a script or use -c flag (e.g. 'python -c ...').")

        cwd = context.cwd or os.getcwd()

        try:
            proc = await asyncio.create_subprocess_shell(
                command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=cwd,
                env={**os.environ},
            )

            try:
                stdout_bytes, stderr_bytes = await asyncio.wait_for(
                    proc.communicate(), timeout=timeout
                )
            except asyncio.TimeoutError:
                proc.kill()
                await proc.wait()
                return ToolResult(
                    error=f"Command timed out after {timeout}s: {command}"
                )

            stdout = stdout_bytes.decode("utf-8", errors="replace")
            stderr = stderr_bytes.decode("utf-8", errors="replace")
            returncode = proc.returncode or 0

            # Build output
            output = ""
            if stdout:
                output += stdout
            if stderr:
                if output:
                    output += "\n"
                output += stderr

            # Truncate
            if len(output) > MAX_OUTPUT_CHARS:
                output = (
                    output[:MAX_OUTPUT_CHARS]
                    + f"\n\n... (output truncated, {len(output)} total chars)"
                )

            if returncode != 0:
                return ToolResult(
                    data=f"Exit code: {returncode}\n{output}" if output else f"Exit code: {returncode}",
                )

            return ToolResult(data=output or "(no output)")

        except Exception as e:
            return ToolResult(error=f"Failed to execute command: {e}")
