"""
Browser Subagent Tool powered by the Chrome DevTools Protocol (CDP).

Allows the agent to delegate webpage automation, button finding, and clicking
to an autonomous Browser Subagent communicating directly with the browser via CDP.
"""

from __future__ import annotations

import json
from typing import Any

from lucy.core.tool import (
    PermissionBehavior,
    PermissionResult,
    Tool,
    ToolContext,
    ToolResult,
)
from lucy.services.browser_subagent import get_browser_subagent


class BrowserSubagentTool(Tool):
    """Autonomous Browser Subagent tool powered by Chrome DevTools Protocol (CDP)."""

    @property
    def name(self) -> str:
        return "browser_subagent"

    @property
    def aliases(self) -> list[str]:
        return ["cdp_browser", "cdp_click", "BrowserAgent", "browser_agent"]

    @property
    def description(self) -> str:
        return (
            "Autonomous browser sub-agent powered by the Chrome DevTools Protocol (CDP). "
            "Use this tool to find and click buttons, links, and controls on webpages, "
            "navigate to URLs, inspect interactive elements, or execute end-to-end browser workflows."
        )

    @property
    def input_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["click_button", "find_buttons", "navigate", "run_task", "screenshot"],
                    "description": (
                        "Action to perform: "
                        "'click_button' (find and click a button by text or selector), "
                        "'find_buttons' (list all clickable buttons and elements on the page), "
                        "'navigate' (load a URL via CDP), "
                        "'run_task' (delegate a multi-step browsing task to the sub-agent), "
                        "'screenshot' (capture page viewport)."
                    ),
                },
                "button": {
                    "type": "string",
                    "description": "Label, text, aria-label, or partial text of the button to click (e.g. 'Sign in', 'Submit', 'Play', 'Search').",
                },
                "url": {
                    "type": "string",
                    "description": "Optional webpage URL to open or navigate to before performing action.",
                },
                "selector": {
                    "type": "string",
                    "description": "Optional CSS selector to target an exact element (e.g. '#submit-btn', 'button.primary').",
                },
                "task": {
                    "type": "string",
                    "description": "High-level natural language instruction for the sub-agent when action='run_task' (e.g. 'Go to example.com and click the Learn More button').",
                },
            },
            "required": ["action"],
        }

    def is_read_only(self, tool_input: dict[str, Any]) -> bool:
        action = tool_input.get("action", "")
        return action in ("find_buttons", "screenshot")

    async def check_permissions(
        self, tool_input: dict[str, Any], context: ToolContext
    ) -> PermissionResult:
        if getattr(context, "autonomous", False) or context.permission_mode in ("auto_accept", "autonomous"):
            return PermissionResult(behavior=PermissionBehavior.ALLOW, updated_input=tool_input)

        action = tool_input.get("action", "")
        if self.is_read_only(tool_input):
            return PermissionResult(behavior=PermissionBehavior.ALLOW, updated_input=tool_input)

        btn = tool_input.get("button") or tool_input.get("selector") or ""
        url = tool_input.get("url") or ""
        msg = f"Browser Subagent action: {action}"
        if btn:
            msg += f" on button '{btn}'"
        if url:
            msg += f" at {url}"

        return PermissionResult(
            behavior=PermissionBehavior.ASK,
            message=msg,
            updated_input=tool_input,
        )

    def get_prompt(self) -> str:
        return (
            "Use the browser_subagent tool to control Chromium browsers via Chrome DevTools Protocol (CDP). "
            "To click any button or interactive element on a webpage, pass action='click_button' "
            "and specify the button's visible text or selector. "
            "You can also use action='find_buttons' to inspect all available buttons before clicking."
        )

    async def call(self, tool_input: dict[str, Any], context: ToolContext) -> ToolResult:
        subagent = get_browser_subagent()
        action = tool_input.get("action", "").strip().lower()
        button = tool_input.get("button", "")
        url = tool_input.get("url")
        selector = tool_input.get("selector")
        task = tool_input.get("task", "")

        try:
            if action == "navigate":
                if not url:
                    return ToolResult(error="Parameter 'url' is required for action='navigate'")
                res = await subagent.navigate(url)
                return ToolResult(data=res.output)

            elif action == "find_buttons":
                res = await subagent.find_buttons(filter_text=button, url=url)
                return ToolResult(data=res.output)

            elif action == "click_button":
                if not button and not selector:
                    return ToolResult(error="Either 'button' (text) or 'selector' is required for action='click_button'")
                res = await subagent.click_button(button_target=button, url=url, selector=selector)
                if res.success:
                    return ToolResult(data=res.output)
                return ToolResult(error=res.output)

            elif action == "run_task":
                task_str = task or button
                if not task_str:
                    return ToolResult(error="Parameter 'task' is required for action='run_task'")
                res = await subagent.execute_task(task_str)
                if res.success:
                    return ToolResult(data=res.output)
                return ToolResult(error=res.output)

            elif action == "screenshot":
                b64 = await subagent.capture_screenshot()
                return ToolResult(data=f"Captured page screenshot via CDP ({len(b64)} base64 bytes).")

            else:
                return ToolResult(
                    error=f"Unknown browser_subagent action '{action}'. Valid actions: click_button, find_buttons, navigate, run_task, screenshot."
                )

        except Exception as e:
            return ToolResult(error=f"Browser Subagent error: {e}")

