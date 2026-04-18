"""
Auth commands — /login, /logout.
"""

from __future__ import annotations

import os
from typing import Any

from lucy.core.commands import Command, CommandResult


class LoginCommand(Command):
    @property
    def name(self) -> str: return "login"
    @property
    def description(self) -> str: return "Set or update API key"
    @property
    def usage(self) -> str: return "/login [api_key]"

    async def execute(self, args: str, state: Any) -> CommandResult:
        from lucy.core.config import get_config, save_config
        key = args.strip()
        if not key:
            return CommandResult(output="Enter your Anthropic API key:\n  /login sk-ant-...")
        config = get_config()
        config.api_key = key
        save_config(config)
        os.environ["ANTHROPIC_API_KEY"] = key
        return CommandResult(output="✅ API key updated")


class LogoutCommand(Command):
    @property
    def name(self) -> str: return "logout"
    @property
    def description(self) -> str: return "Remove stored API key"

    async def execute(self, args: str, state: Any) -> CommandResult:
        from lucy.core.config import get_config, save_config
        config = get_config()
        config.api_key = ""
        save_config(config)
        os.environ.pop("ANTHROPIC_API_KEY", None)
        return CommandResult(output="✅ API key removed")


def get_commands() -> list[Command]:
    return [LoginCommand(), LogoutCommand()]
