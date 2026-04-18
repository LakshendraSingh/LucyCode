"""
Hooks system — lifecycle event hooks for Lucy Code.

Hooks are user-defined commands that execute at specific lifecycle points:
  - PreToolUse: before a tool is invoked
  - PostToolUse: after a tool completes
  - SessionStart: when a session begins
  - SessionEnd: when a session ends
  - UserPromptSubmit: when user sends a prompt
  - Notification: for background notifications

Hooks are configured in ~/.lucy/hooks.json or CLAUDE.md.
They receive JSON input on stdin and can produce JSON output on stdout.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Awaitable, Union

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Hook events
# ---------------------------------------------------------------------------

class HookEvent(str, Enum):
    PRE_TOOL_USE = "PreToolUse"
    POST_TOOL_USE = "PostToolUse"
    SESSION_START = "SessionStart"
    SESSION_END = "SessionEnd"
    USER_PROMPT_SUBMIT = "UserPromptSubmit"
    NOTIFICATION = "Notification"
    PRE_COMPACT = "PreCompact"
    POST_COMPACT = "PostCompact"
    SETUP = "Setup"
    STOP = "Stop"


# ---------------------------------------------------------------------------
# Hook input/output
# ---------------------------------------------------------------------------

@dataclass
class HookInput:
    """Input passed to a hook via stdin (as JSON)."""
    session_id: str = ""
    cwd: str = ""
    hook_event: str = ""
    # Event-specific data
    tool_name: str | None = None
    tool_input: dict[str, Any] | None = None
    tool_output: str | None = None
    user_prompt: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass
class HookOutput:
    """Parsed output from a hook."""
    # Control flow
    continue_execution: bool = True
    suppress_output: bool = False
    stop_reason: str | None = None
    # Permission override
    decision: str | None = None  # "approve" | "block"
    reason: str | None = None
    permission_decision: str | None = None  # "allow" | "deny" | "ask"
    # Content injection
    system_message: str | None = None
    additional_context: str | None = None
    updated_input: dict[str, Any] | None = None
    # Raw data
    raw_output: str = ""
    is_error: bool = False
    exit_code: int = 0


# ---------------------------------------------------------------------------
# Hook definition
# ---------------------------------------------------------------------------

@dataclass
class HookCommand:
    """A hook defined as a shell command."""
    command: str
    event: HookEvent
    # Optional matcher — only fire for specific tools/patterns
    tool_name: str | None = None  # e.g. "Bash" - only fire for this tool
    pattern: str | None = None    # regex pattern to match against tool input
    timeout: int = 60             # seconds
    enabled: bool = True
    name: str = ""                # human-readable name


@dataclass
class HookCallbackDef:
    """A hook defined as a Python callable."""
    callback: Callable[[HookInput], Awaitable[HookOutput]]
    event: HookEvent
    tool_name: str | None = None
    name: str = ""


HookDefinition = Union[HookCommand, HookCallbackDef]


# ---------------------------------------------------------------------------
# Hook registry
# ---------------------------------------------------------------------------

class HookRegistry:
    """Registry for all hooks."""

    def __init__(self) -> None:
        self._hooks: list[HookDefinition] = []

    def register(self, hook: HookDefinition) -> None:
        """Register a hook."""
        self._hooks.append(hook)

    def unregister(self, name: str) -> None:
        """Unregister a hook by name."""
        self._hooks = [h for h in self._hooks if getattr(h, "name", "") != name]

    def get_hooks_for_event(
        self, event: HookEvent, tool_name: str | None = None
    ) -> list[HookDefinition]:
        """Get all hooks matching an event, optionally filtered by tool name."""
        result: list[HookDefinition] = []
        for hook in self._hooks:
            if not getattr(hook, "enabled", True):
                continue
            if isinstance(hook, HookCommand) and hook.event != event:
                continue
            if isinstance(hook, HookCallbackDef) and hook.event != event:
                continue
            # Filter by tool name if specified
            hook_tool = getattr(hook, "tool_name", None)
            if hook_tool and tool_name and hook_tool != tool_name:
                continue
            result.append(hook)
        return result

    def get_all(self) -> list[HookDefinition]:
        return list(self._hooks)

    def clear(self) -> None:
        self._hooks.clear()


# Global registry
_hook_registry = HookRegistry()


def get_hook_registry() -> HookRegistry:
    return _hook_registry


def register_hook(hook: HookDefinition) -> None:
    _hook_registry.register(hook)


# ---------------------------------------------------------------------------
# Hook execution
# ---------------------------------------------------------------------------

async def execute_hook(
    hook: HookDefinition,
    hook_input: HookInput,
) -> HookOutput:
    """Execute a single hook and return its output."""
    if isinstance(hook, HookCallbackDef):
        try:
            return await hook.callback(hook_input)
        except Exception as e:
            logger.warning("Hook callback '%s' failed: %s", hook.name, e)
            return HookOutput(is_error=True, raw_output=str(e), exit_code=1)

    if isinstance(hook, HookCommand):
        return await _execute_command_hook(hook, hook_input)

    return HookOutput()


async def _execute_command_hook(
    hook: HookCommand,
    hook_input: HookInput,
) -> HookOutput:
    """Execute a command-based hook."""
    # Serialize input to JSON
    input_json = json.dumps({
        "session_id": hook_input.session_id,
        "cwd": hook_input.cwd,
        "hook_event": hook_input.hook_event,
        "tool_name": hook_input.tool_name,
        "tool_input": hook_input.tool_input,
        "tool_output": hook_input.tool_output,
        "user_prompt": hook_input.user_prompt,
        **hook_input.extra,
    }, default=str)

    try:
        proc = await asyncio.create_subprocess_shell(
            hook.command,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=hook_input.cwd or None,
        )

        try:
            stdout_bytes, stderr_bytes = await asyncio.wait_for(
                proc.communicate(input=input_json.encode("utf-8")),
                timeout=hook.timeout,
            )
        except asyncio.TimeoutError:
            proc.kill()
            await proc.wait()
            return HookOutput(
                is_error=True,
                raw_output=f"Hook timed out after {hook.timeout}s",
                exit_code=-1,
            )

        stdout = stdout_bytes.decode("utf-8", errors="replace")
        stderr = stderr_bytes.decode("utf-8", errors="replace")
        exit_code = proc.returncode or 0

        return _parse_hook_output(stdout, stderr, exit_code)

    except Exception as e:
        logger.warning("Hook command '%s' failed: %s", hook.name, e)
        return HookOutput(is_error=True, raw_output=str(e), exit_code=1)


def _parse_hook_output(stdout: str, stderr: str, exit_code: int) -> HookOutput:
    """Parse hook stdout into a HookOutput."""
    output = HookOutput(exit_code=exit_code, raw_output=stdout)

    if exit_code == 2:
        # Exit code 2 = blocking error
        output.decision = "block"
        output.reason = stderr or stdout
        output.continue_execution = False
        output.is_error = True
        return output

    if exit_code != 0:
        output.is_error = True
        output.raw_output = stderr or stdout
        return output

    # Try to parse JSON output
    trimmed = stdout.strip()
    if trimmed.startswith("{"):
        try:
            data = json.loads(trimmed)
            if data.get("continue") is False:
                output.continue_execution = False
                output.stop_reason = data.get("stopReason")
            if data.get("decision"):
                output.decision = data["decision"]
                output.reason = data.get("reason")
            if data.get("systemMessage"):
                output.system_message = data["systemMessage"]
            if data.get("suppressOutput"):
                output.suppress_output = True
            # Hook-specific output
            hso = data.get("hookSpecificOutput", {})
            if hso:
                output.permission_decision = hso.get("permissionDecision")
                output.additional_context = hso.get("additionalContext")
                output.updated_input = hso.get("updatedInput")
        except json.JSONDecodeError:
            pass  # Not JSON — treat as plain text

    return output


# ---------------------------------------------------------------------------
# Aggregate hook results
# ---------------------------------------------------------------------------

async def run_hooks_for_event(
    event: HookEvent,
    hook_input: HookInput,
    tool_name: str | None = None,
) -> list[HookOutput]:
    """Run all hooks for a given event and return their outputs."""
    registry = get_hook_registry()
    hooks = registry.get_hooks_for_event(event, tool_name=tool_name)

    results: list[HookOutput] = []
    for hook in hooks:
        result = await execute_hook(hook, hook_input)
        results.append(result)
        # If a hook blocks, stop executing subsequent hooks
        if not result.continue_execution:
            break

    return results


# ---------------------------------------------------------------------------
# Hook config loading
# ---------------------------------------------------------------------------

def load_hooks_from_config(config_path: str | None = None) -> None:
    """Load hooks from a JSON config file.

    Config format:
    {
      "hooks": {
        "PreToolUse": [
          {"command": "my-linter --check", "tool_name": "Edit"},
          {"command": "security-scan"}
        ],
        "PostToolUse": [
          {"command": "post-tool-notify"}
        ]
      }
    }
    """
    if config_path is None:
        config_path = str(Path.home() / ".lucy" / "hooks.json")

    path = Path(config_path)
    if not path.exists():
        return

    try:
        with open(path) as f:
            config = json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        logger.warning("Failed to load hooks config: %s", e)
        return

    hooks_config = config.get("hooks", {})
    registry = get_hook_registry()

    for event_name, hook_defs in hooks_config.items():
        try:
            event = HookEvent(event_name)
        except ValueError:
            logger.warning("Unknown hook event: %s", event_name)
            continue

        if not isinstance(hook_defs, list):
            hook_defs = [hook_defs]

        for i, hdef in enumerate(hook_defs):
            if isinstance(hdef, str):
                hdef = {"command": hdef}

            registry.register(HookCommand(
                command=hdef.get("command", ""),
                event=event,
                tool_name=hdef.get("tool_name"),
                pattern=hdef.get("pattern"),
                timeout=hdef.get("timeout", 60),
                enabled=hdef.get("enabled", True),
                name=hdef.get("name", f"{event_name}_{i}"),
            ))
