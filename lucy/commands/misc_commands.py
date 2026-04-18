"""
Miscellaneous commands — /copy, /feedback, /upgrade, /brief, /fast, /effort, /privacy-settings.
"""

from __future__ import annotations

import subprocess
import sys
from typing import Any

from lucy.core.commands import Command, CommandResult


class CopyCommand(Command):
    @property
    def name(self) -> str: return "copy"
    @property
    def aliases(self) -> list[str]: return ["cp-output", "yank"]
    @property
    def description(self) -> str: return "Copy last assistant response to clipboard"

    async def execute(self, args: str, state: Any) -> CommandResult:
        from lucy.core.message import AssistantMessage
        for m in reversed(state.messages):
            if isinstance(m, AssistantMessage):
                text = m.get_text()
                try:
                    if sys.platform == "darwin":
                        subprocess.run(["pbcopy"], input=text.encode(), check=True)
                    elif sys.platform == "linux":
                        subprocess.run(["xclip", "-selection", "clipboard"],
                                       input=text.encode(), check=True)
                    else:
                        return CommandResult(error="Clipboard not supported on this platform")
                    return CommandResult(output=f"✅ Copied {len(text)} chars to clipboard")
                except (FileNotFoundError, subprocess.SubprocessError) as e:
                    return CommandResult(error=f"Clipboard error: {e}")
        return CommandResult(output="No assistant messages to copy.")


class FeedbackCommand(Command):
    @property
    def name(self) -> str: return "feedback"
    @property
    def description(self) -> str: return "Send feedback about Lucy Code"

    async def execute(self, args: str, state: Any) -> CommandResult:
        msg = args.strip()
        if not msg:
            return CommandResult(output="Usage: /feedback <your message>\nYour feedback helps improve Lucy Code!")
        # Log to local file
        from lucy.core.config import get_config
        import os, time
        config = get_config()
        fb_path = os.path.join(str(config.config_dir), "feedback.log")
        with open(fb_path, "a") as f:
            f.write(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {msg}\n")
        return CommandResult(output="✅ Feedback recorded. Thank you!")


class UpgradeCommand(Command):
    @property
    def name(self) -> str: return "upgrade"
    @property
    def aliases(self) -> list[str]: return ["update"]
    @property
    def description(self) -> str: return "Check for updates"

    async def execute(self, args: str, state: Any) -> CommandResult:
        from lucy import __version__
        return CommandResult(
            output=f"Current version: {__version__}\n"
                   f"Run: pip install --upgrade lucycode"
        )


class BriefCommand(Command):
    @property
    def name(self) -> str: return "brief"
    @property
    def description(self) -> str: return "Toggle brief response mode"

    async def execute(self, args: str, state: Any) -> CommandResult:
        current = getattr(state, 'brief_mode', False)
        state.brief_mode = not current
        return CommandResult(output=f"Brief mode: {'ON' if state.brief_mode else 'OFF'}")


class FastCommand(Command):
    @property
    def name(self) -> str: return "fast"
    @property
    def aliases(self) -> list[str]: return ["turbo"]
    @property
    def description(self) -> str: return "Switch to fastest model (haiku)"

    async def execute(self, args: str, state: Any) -> CommandResult:
        from lucy.api.models import resolve_model
        state.model = resolve_model("haiku")
        return CommandResult(output=f"Switched to fast model: {state.model}")


class EffortCommand(Command):
    @property
    def name(self) -> str: return "effort"
    @property
    def description(self) -> str: return "Set thinking effort level"
    @property
    def usage(self) -> str: return "/effort [low|medium|high]"

    async def execute(self, args: str, state: Any) -> CommandResult:
        from lucy.core.config import get_config
        level = args.strip().lower()
        levels = {"low": 3000, "medium": 10000, "high": 50000}
        if level not in levels:
            config = get_config()
            return CommandResult(output=f"Current thinking budget: {config.max_thinking_tokens}\n"
                                        f"Usage: /effort [low|medium|high]")
        config = get_config()
        config.max_thinking_tokens = levels[level]
        return CommandResult(output=f"Thinking effort: {level} ({levels[level]} tokens)")


class PrivacyCommand(Command):
    @property
    def name(self) -> str: return "privacy-settings"
    @property
    def aliases(self) -> list[str]: return ["privacy"]
    @property
    def description(self) -> str: return "Manage privacy settings"

    async def execute(self, args: str, state: Any) -> CommandResult:
        lines = [
            "🔒 Privacy Settings:",
            f"  Telemetry: disabled",
            f"  Session storage: ~/.lucycode/sessions/",
            f"  API: direct to Anthropic (no proxy)",
            "",
            "All data is stored locally. No telemetry is collected.",
        ]
        return CommandResult(output="\n".join(lines))


def get_commands() -> list[Command]:
    return [CopyCommand(), FeedbackCommand(), UpgradeCommand(), BriefCommand(),
            FastCommand(), EffortCommand(), PrivacyCommand()]
