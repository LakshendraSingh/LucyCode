"""
UI commands — /theme, /vim, /keybindings, /output-style.
"""

from __future__ import annotations

from typing import Any

from lucy.core.commands import Command, CommandResult


class ThemeCommand(Command):
    @property
    def name(self) -> str: return "theme"
    @property
    def description(self) -> str: return "Change the UI theme"
    @property
    def usage(self) -> str: return "/theme [dark|light|monokai|solarized|dracula]"

    async def execute(self, args: str, state: Any) -> CommandResult:
        from lucy.core.config import get_config, save_config
        theme = args.strip().lower()
        available = ["dark", "light", "monokai", "solarized", "dracula"]
        if not theme:
            config = get_config()
            return CommandResult(output=f"Current theme: {config.theme}\nAvailable: {', '.join(available)}")
        if theme not in available:
            return CommandResult(error=f"Unknown theme. Available: {', '.join(available)}")
        config = get_config()
        config.theme = theme
        save_config(config)
        return CommandResult(output=f"Theme set to: {theme}")


class VimCommand(Command):
    @property
    def name(self) -> str: return "vim"
    @property
    def description(self) -> str: return "Toggle vim keybindings mode"
    @property
    def usage(self) -> str: return "/vim [on|off]"

    async def execute(self, args: str, state: Any) -> CommandResult:
        from lucy.shell.vim import get_vim_manager
        mode = args.strip().lower()
        manager = get_vim_manager()
        
        if mode == "on":
            manager.enabled = True
            return CommandResult(output="Vim mode: ON")
        elif mode == "off":
            manager.enabled = False
            return CommandResult(output="Vim mode: OFF")
        else:
            current = manager.toggle()
            return CommandResult(output=f"Vim mode: {'ON' if current else 'OFF'}\nUsage: /vim [on|off]")


class OutputStyleCommand(Command):
    @property
    def name(self) -> str: return "output-style"
    @property
    def aliases(self) -> list[str]: return ["style"]
    @property
    def description(self) -> str: return "Set output rendering style"
    @property
    def usage(self) -> str: return "/output-style [markdown|plain|json]"

    async def execute(self, args: str, state: Any) -> CommandResult:
        style = args.strip().lower()
        available = ["markdown", "plain", "json"]
        if not style:
            current = getattr(state, 'output_style', 'markdown')
            return CommandResult(output=f"Current style: {current}\nAvailable: {', '.join(available)}")
        if style not in available:
            return CommandResult(error=f"Unknown style. Available: {', '.join(available)}")
        state.output_style = style
        return CommandResult(output=f"Output style: {style}")


class KeybindingsCommand(Command):
    @property
    def name(self) -> str: return "keybindings"
    @property
    def aliases(self) -> list[str]: return ["keys"]
    @property
    def description(self) -> str: return "Show keyboard shortcuts"
    @property
    def usage(self) -> str: return "/keybindings"

    async def execute(self, args: str, state: Any) -> CommandResult:
        bindings = [
            "Keyboard Shortcuts:",
            "",
            "  Ctrl+C    — Cancel current operation",
            "  Ctrl+D    — Exit Lucy Code",
            "  Tab       — Auto-complete commands and paths",
            "  Up/Down   — Navigate input history",
            "  Ctrl+L    — Clear screen",
            "  Ctrl+R    — Search command history",
            "",
            "Slash Commands:",
            "  /help     — Show all commands",
            "  /clear    — Clear conversation",
            "  /compact  — Compact to save tokens",
            "  /exit     — Exit",
        ]
        return CommandResult(output="\n".join(bindings))


def get_commands() -> list[Command]:
    return [ThemeCommand(), VimCommand(), OutputStyleCommand(), KeybindingsCommand()]
