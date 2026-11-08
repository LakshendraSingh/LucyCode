"""
Browser slash commands — /browser powered by Chrome DevTools Protocol (CDP).
"""

from __future__ import annotations

from typing import Any

from lucy.core.commands import Command, CommandResult
from lucy.services.browser_subagent import get_browser_subagent
from lucy.services.cdp_client import get_cdp_client


class BrowserCommand(Command):
    """Control browser via Chrome DevTools Protocol (CDP) sub-agent."""

    @property
    def name(self) -> str:
        return "browser"

    @property
    def aliases(self) -> list[str]:
        return ["cdp", "browse"]

    @property
    def description(self) -> str:
        return "Control browser and click buttons via Chrome DevTools Protocol (CDP)"

    @property
    def usage(self) -> str:
        return "/browser [open <url>|buttons [filter]|click <button>|task <instruction>|status]"

    async def execute(self, args: str, state: Any) -> CommandResult:
        subagent = get_browser_subagent()
        cdp = get_cdp_client()

        parts = args.strip().split(None, 1)
        action = parts[0].lower() if parts else "status"
        rest = parts[1] if len(parts) > 1 else ""

        if action in ("status", ""):
            is_avail = await cdp.is_cdp_available()
            url = await cdp.get_current_url() if is_avail or cdp.is_connected else "N/A"
            title = await cdp.get_page_title() if is_avail or cdp.is_connected else "N/A"
            status_text = "CONNECTED" if (is_avail or cdp.is_connected) else "STANDBY (Will auto-launch on demand)"
            lines = [
                "Chrome DevTools Protocol (CDP) Browser Subagent Status:",
                f"  CDP Port: {cdp.port}",
                f"  Status: {status_text}",
                f"  Active URL: {url}",
                f"  Active Title: {title}",
                "",
                "Commands:",
                "  /browser open <url>         - Navigate to webpage",
                "  /browser buttons [filter]   - List clickable buttons and controls",
                "  /browser click <name>       - Click button by label or text via CDP",
                "  /browser task <instruction> - Run autonomous browsing task",
            ]
            return CommandResult(output="\n".join(lines))

        elif action == "open":
            if not rest:
                return CommandResult(error="Usage: /browser open <url>")
            url = rest.strip()
            if not url.startswith("http"):
                url = f"https://{url}"
            res = await subagent.navigate(url)
            return CommandResult(output=res.output)

        elif action in ("buttons", "find", "list"):
            res = await subagent.find_buttons(filter_text=rest or None)
            return CommandResult(output=res.output)

        elif action in ("click", "press", "tap"):
            if not rest:
                return CommandResult(error="Usage: /browser click <button_name_or_selector>")
            res = await subagent.click_button(button_target=rest.strip())
            if res.success:
                return CommandResult(output=res.output)
            return CommandResult(error=res.output)

        elif action in ("task", "run", "do"):
            if not rest:
                return CommandResult(error="Usage: /browser task <instruction>")
            res = await subagent.execute_task(rest.strip())
            if res.success:
                return CommandResult(output=res.output)
            return CommandResult(error=res.output)

        else:
            return CommandResult(error=f"Unknown browser action: '{action}'. Usage: {self.usage}")


def get_commands() -> list[Command]:
    """Return browser command instances."""
    return [BrowserCommand()]

