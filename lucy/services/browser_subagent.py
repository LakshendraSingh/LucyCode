"""
Browser Subagent powered by the Chrome DevTools Protocol (CDP).

An autonomous sub-agent specialized in webpage interaction, button discovery,
deterministic CDP clicking, form automation, and verification.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
from dataclasses import dataclass, field
from typing import Any

from lucy.services.cdp_client import CDPClient, CDPElement, CDPClickResult, get_cdp_client

logger = logging.getLogger(__name__)


@dataclass
class BrowserSubagentResult:
    """Outcome of a Browser Subagent execution."""
    success: bool
    action: str
    output: str
    current_url: str
    page_title: str
    clicked_element: dict[str, Any] | None = None
    elements_found: list[dict[str, Any]] = field(default_factory=list)
    steps: list[str] = field(default_factory=list)
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "success": self.success,
            "action": self.action,
            "output": self.output,
            "current_url": self.current_url,
            "page_title": self.page_title,
            "clicked_element": self.clicked_element,
            "elements_found": self.elements_found,
            "steps": self.steps,
            "error": self.error,
        }


class BrowserSubagent:
    """Autonomous Browser Subagent powered by Chrome DevTools Protocol (CDP)."""

    def __init__(self, cdp_client: CDPClient | None = None) -> None:
        self.cdp = cdp_client or get_cdp_client()

    async def ensure_connected(self) -> bool:
        """Ensure connection to CDP endpoint."""
        if not self.cdp.is_connected:
            return await self.cdp.connect()
        return True

    async def navigate(self, url: str) -> BrowserSubagentResult:
        """Navigate to a webpage and report initial state."""
        await self.ensure_connected()
        steps = [f"Navigating to {url} via CDP"]
        ok = await self.cdp.navigate(url)
        current_url = await self.cdp.get_current_url()
        title = await self.cdp.get_page_title()

        if ok:
            steps.append(f"Arrived at: {current_url} ('{title}')")
            return BrowserSubagentResult(
                success=True,
                action="navigate",
                output=f"Successfully navigated to {current_url} ('{title}').",
                current_url=current_url,
                page_title=title,
                steps=steps,
            )
        else:
            steps.append(f"Failed to navigate to {url}")
            return BrowserSubagentResult(
                success=False,
                action="navigate",
                output=f"Failed to navigate to {url}",
                current_url=current_url,
                page_title=title,
                steps=steps,
                error="Navigation failed",
            )

    async def find_buttons(self, filter_text: str | None = None, url: str | None = None) -> BrowserSubagentResult:
        """Find and list all interactive buttons on the webpage via CDP."""
        await self.ensure_connected()
        steps: list[str] = []

        if url:
            steps.append(f"Navigating to {url}")
            await self.cdp.navigate(url)

        current_url = await self.cdp.get_current_url()
        title = await self.cdp.get_page_title()

        steps.append("Scanning DOM for buttons and interactive controls via CDP")
        elements = await self.cdp.find_clickable_elements(filter_text=filter_text)
        serialized = [el.to_dict() for el in elements]

        filter_desc = f" matching '{filter_text}'" if filter_text else ""
        output_lines = [
            f"Found {len(elements)} clickable element(s){filter_desc} on '{title}' ({current_url}):\n"
        ]
        for i, el in enumerate(elements[:15], 1):
            label = el.text or el.aria_label or el.id or el.selector
            output_lines.append(
                f"  {i}. [{el.tag.upper()}] '{label}' -> selector: {el.selector} (x: {el.center_x}, y: {el.center_y})"
            )
        if len(elements) > 15:
            output_lines.append(f"  ... and {len(elements) - 15} more.")

        return BrowserSubagentResult(
            success=True,
            action="find_buttons",
            output="\n".join(output_lines),
            current_url=current_url,
            page_title=title,
            elements_found=serialized,
            steps=steps,
        )

    async def click_button(
        self,
        button_target: str,
        url: str | None = None,
        selector: str | None = None,
    ) -> BrowserSubagentResult:
        """Find a button by text or selector and click it using Chrome DevTools Protocol."""
        await self.ensure_connected()
        steps: list[str] = []

        if url:
            steps.append(f"Navigating to target URL: {url}")
            await self.cdp.navigate(url)

        initial_url = await self.cdp.get_current_url()
        steps.append(f"Locating button matching '{button_target or selector}'")

        click_res: CDPClickResult = await self.cdp.click_element(
            target=button_target, selector=selector
        )

        final_url = click_res.final_url
        title = await self.cdp.get_page_title()

        if click_res.success:
            elem = click_res.element
            label = elem.text if elem else button_target
            steps.append(f"Dispatched CDP click to '{label}' at {click_res.click_coordinates}")
            if click_res.navigation_occurred:
                steps.append(f"Page navigated from {initial_url} to {final_url}")

            return BrowserSubagentResult(
                success=True,
                action="click_button",
                output=click_res.output,
                current_url=final_url,
                page_title=title,
                clicked_element=elem.to_dict() if elem else None,
                steps=steps,
            )

        # Fallback: if CDP click didn't find the element and we are on macOS,
        # attempt to interact with active desktop browser window (Safari, Chrome, etc.)
        import sys
        if sys.platform == "darwin":
            try:
                from lucy.services.universal_ui import get_universal_ui
                uui = get_universal_ui()
                front = uui.get_frontmost_app()
                front_app = front.get("name", "")
                if front.get("is_browser") or front_app in ("Safari", "Google Chrome", "Brave Browser", "Arc", "Microsoft Edge"):
                    steps.append(f"Attempting native macOS browser interaction on active window in {front_app}")
                    ui_res = uui.click_element(app_name=front_app, label=button_target)
                    if ui_res.success:
                        steps.append(f"Successfully clicked '{button_target}' via native UI accessibility in {front_app}")
                        return BrowserSubagentResult(
                            success=True,
                            action="click_button",
                            output=f"Successfully clicked '{button_target}' on webpage in {front_app} ({ui_res.message}).",
                            current_url=front.get("browser_url") or initial_url,
                            page_title=front.get("browser_title") or title,
                            steps=steps,
                        )
            except Exception as e:
                logger.debug("Universal UI browser click fallback failed: %s", e)

        steps.append(f"Failed to find or click target: {click_res.error}")
        return BrowserSubagentResult(
            success=False,
            action="click_button",
            output=click_res.output,
            current_url=final_url,
            page_title=title,
            error=click_res.error,
            steps=steps,
        )

    async def execute_task(self, task: str) -> BrowserSubagentResult:
        """
        Execute an autonomous multi-step browser task (e.g. 'open github.com and click sign in').
        Parses intent, navigates if needed, locates target buttons, and performs clicks.
        """
        await self.ensure_connected()
        steps: list[str] = [f"Starting browser sub-agent task: {task}"]

        # 1. Check for URL in task prompt
        url_match = re.search(r"https?://[^\s]+|(?:\b[a-zA-Z0-9-]+\.(?:com|org|io|dev|net|edu|gov)[^\s]*)", task)
        target_url = None
        if url_match:
            raw_url = url_match.group(0).rstrip(".,;")
            if not raw_url.startswith("http"):
                target_url = f"https://{raw_url}"
            else:
                target_url = raw_url
            steps.append(f"Identified starting URL: {target_url}")
            await self.cdp.navigate(target_url)

        # 2. Check for click intent
        click_match = re.search(r"(?:click|press|tap|hit|submit)\s+(?:on\s+)?(?:the\s+)?[\"']?([^\"'\n\.,;]+)[\"']?", task, re.IGNORECASE)
        button_query = None
        if click_match:
            button_query = click_match.group(1).strip()
            # Clean trailing words like 'button' or 'link'
            button_query_clean = re.sub(r"\s+(?:button|link|icon)$", "", button_query, flags=re.IGNORECASE).strip()
            button_query = button_query_clean or button_query

        current_url = await self.cdp.get_current_url()
        page_title = await self.cdp.get_page_title()

        if button_query:
            steps.append(f"Attempting to find and click '{button_query}' via CDP")
            click_res = await self.click_button(button_target=button_query)
            steps.extend(click_res.steps)

            if click_res.success:
                return BrowserSubagentResult(
                    success=True,
                    action="execute_task",
                    output=f"Task completed successfully: {click_res.output}",
                    current_url=click_res.current_url,
                    page_title=click_res.page_title,
                    clicked_element=click_res.clicked_element,
                    steps=steps,
                )
            else:
                return BrowserSubagentResult(
                    success=False,
                    action="execute_task",
                    output=f"Sub-agent could not click '{button_query}': {click_res.output}",
                    current_url=click_res.current_url,
                    page_title=click_res.page_title,
                    error=click_res.error,
                    steps=steps,
                )

        # If no explicit click was requested, return page buttons and inspection
        inspect_res = await self.find_buttons()
        steps.extend(inspect_res.steps)
        return BrowserSubagentResult(
            success=True,
            action="execute_task",
            output=f"Page loaded: '{page_title}' ({current_url}).\n{inspect_res.output}",
            current_url=current_url,
            page_title=page_title,
            elements_found=inspect_res.elements_found,
            steps=steps,
        )

    async def capture_screenshot(self) -> str:
        """Capture page screenshot."""
        return await self.cdp.capture_screenshot()


_global_browser_subagent: BrowserSubagent | None = None


def get_browser_subagent() -> BrowserSubagent:
    """Retrieve or initialize singleton BrowserSubagent instance."""
    global _global_browser_subagent
    if _global_browser_subagent is None:
        _global_browser_subagent = BrowserSubagent()
    return _global_browser_subagent

