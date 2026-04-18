"""
Plugin commands — /plugin, /reload-plugins.
"""

from __future__ import annotations

from typing import Any

from lucy.core.commands import Command, CommandResult


class PluginCommand(Command):
    @property
    def name(self) -> str: return "plugin"
    @property
    def aliases(self) -> list[str]: return ["plugins"]
    @property
    def description(self) -> str: return "Manage plugins"
    @property
    def usage(self) -> str: return "/plugin [list|install|remove|info] [name]"

    async def execute(self, args: str, state: Any) -> CommandResult:
        parts = args.strip().split(None, 1)
        action = parts[0] if parts else "list"
        target = parts[1] if len(parts) > 1 else ""

        from lucy.core.plugins import get_plugin_manager
        mgr = get_plugin_manager()

        if action == "list":
            plugins = mgr.list_plugins()
            if not plugins:
                return CommandResult(output="No plugins installed.\nUse /plugin install <name> to add one.")
            lines = ["Plugins:\n"]
            for p in plugins:
                status = "✅" if p.get("enabled", True) else "❌"
                lines.append(f"  {status} {p['name']} v{p.get('version', '?')}")
                if p.get("description"):
                    lines.append(f"     {p['description']}")
            return CommandResult(output="\n".join(lines))

        if action == "install":
            if not target:
                return CommandResult(error="Usage: /plugin install <name>")
            try:
                mgr.install(target)
                return CommandResult(output=f"✅ Installed plugin: {target}")
            except Exception as e:
                return CommandResult(error=f"Install failed: {e}")

        if action == "remove":
            if not target:
                return CommandResult(error="Usage: /plugin remove <name>")
            try:
                mgr.remove(target)
                return CommandResult(output=f"✅ Removed plugin: {target}")
            except Exception as e:
                return CommandResult(error=f"Remove failed: {e}")

        if action == "info":
            if not target:
                return CommandResult(error="Usage: /plugin info <name>")
            info = mgr.get_info(target)
            if info:
                import json
                return CommandResult(output=json.dumps(info, indent=2))
            return CommandResult(error=f"Plugin not found: {target}")

        return CommandResult(error=f"Unknown action: {action}")


class ReloadPluginsCommand(Command):
    @property
    def name(self) -> str: return "reload-plugins"
    @property
    def description(self) -> str: return "Reload all plugins"

    async def execute(self, args: str, state: Any) -> CommandResult:
        from lucy.core.plugins import get_plugin_manager
        mgr = get_plugin_manager()
        count = mgr.reload_all()
        return CommandResult(output=f"✅ Reloaded {count} plugin(s)")


def get_commands() -> list[Command]:
    return [PluginCommand(), ReloadPluginsCommand()]
