"""
Unit tests for Browser Subagent powered by Chrome DevTools Protocol (CDP).
"""

from __future__ import annotations

import asyncio
import os
import sys
import unittest

# Ensure project root is in sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lucy.commands.browser_commands import BrowserCommand, get_commands
from lucy.core.state import AppState
from lucy.core.tool import ToolContext, PermissionBehavior
from lucy.services.browser_subagent import BrowserSubagent, BrowserSubagentResult
from lucy.services.cdp_client import CDPClient, CDPElement, CDPClickResult
from lucy.tools.browser_subagent_tool import BrowserSubagentTool


class TestBrowserSubagent(unittest.TestCase):
    """Test suite for CDP client, Browser Subagent, and slash commands."""

    def setUp(self):
        from lucy.services.cdp_client import get_cdp_client
        from lucy.services.browser_subagent import get_browser_subagent
        self.cdp = get_cdp_client()
        self.cdp.set_mock_mode(True)
        self.subagent = get_browser_subagent()
        self.subagent.cdp = self.cdp

    def test_cdp_element_dataclass(self):
        """Test CDPElement serialization."""
        elem = CDPElement(
            tag="button",
            id="checkout-btn",
            text="Proceed to Checkout",
            role="button",
            aria_label="Checkout",
            selector="#checkout-btn",
            x=100,
            y=200,
            width=150,
            height=40,
            center_x=175,
            center_y=220,
        )
        d = elem.to_dict()
        self.assertEqual(d["tag"], "button")
        self.assertEqual(d["text"], "Proceed to Checkout")
        self.assertEqual(d["center_x"], 175)
        self.assertEqual(d["center_y"], 220)

    def test_cdp_find_clickable_elements(self):
        """Test finding clickable elements via CDP with and without filters."""
        elements = asyncio.run(self.cdp.find_clickable_elements())
        self.assertGreaterEqual(len(elements), 3)

        # Filter for "submit"
        filtered = asyncio.run(self.cdp.find_clickable_elements(filter_text="submit"))
        self.assertEqual(len(filtered), 1)
        self.assertEqual(filtered[0].id, "submit-btn")
        self.assertEqual(filtered[0].text, "Submit")

    def test_cdp_click_element_by_text(self):
        """Test clicking button by visible text."""
        res = asyncio.run(self.cdp.click_element(target="Sign In"))
        self.assertTrue(res.success)
        self.assertIsNotNone(res.element)
        self.assertEqual(res.element.text, "Sign In")
        self.assertEqual(res.click_coordinates, (840, 55))
        self.assertIn("Successfully clicked button", res.output)

    def test_cdp_click_element_by_selector(self):
        """Test clicking button by CSS selector."""
        res = asyncio.run(self.cdp.click_element(selector="#submit-btn"))
        self.assertTrue(res.success)
        self.assertIsNotNone(res.element)
        self.assertEqual(res.element.id, "submit-btn")
        self.assertEqual(res.click_coordinates, (260, 320))

    def test_cdp_click_element_not_found(self):
        """Test clicking non-existent element returns informative candidate suggestions."""
        res = asyncio.run(self.cdp.click_element(target="Nonexistent Button"))
        self.assertFalse(res.success)
        self.assertIn("Available buttons", res.output)

    def test_cdp_click_coordinates(self):
        """Test direct coordinate click via CDP."""
        res = asyncio.run(self.cdp.click_element(coordinates=(350, 450)))
        self.assertTrue(res.success)
        self.assertEqual(res.click_coordinates, (350, 450))

    def test_browser_subagent_find_buttons(self):
        """Test BrowserSubagent find_buttons formatting."""
        res = asyncio.run(self.subagent.find_buttons())
        self.assertTrue(res.success)
        self.assertIn("clickable element", res.output)
        self.assertIn("Submit", res.output)
        self.assertIn("Sign In", res.output)

    def test_browser_subagent_click_button(self):
        """Test BrowserSubagent click_button workflow."""
        res = asyncio.run(self.subagent.click_button("Submit"))
        self.assertTrue(res.success)
        self.assertEqual(res.action, "click_button")
        self.assertIn("Successfully clicked button 'Submit'", res.output)
        self.assertIsNotNone(res.clicked_element)

    def test_browser_subagent_execute_task(self):
        """Test BrowserSubagent execute_task autonomous loop."""
        res = asyncio.run(
            self.subagent.execute_task("Go to https://example.com and click the Sign In button")
        )
        self.assertTrue(res.success)
        self.assertIn("Task completed successfully", res.output)
        self.assertIn("Sign In", res.output)

    def test_browser_subagent_tool(self):
        """Test BrowserSubagentTool tool execution."""
        tool = BrowserSubagentTool()
        ctx = ToolContext(autonomous=True)

        # 1. find_buttons
        r1 = asyncio.run(tool.call({"action": "find_buttons"}, ctx))
        self.assertIn("Submit", r1.data)

        # 2. click_button
        r2 = asyncio.run(tool.call({"action": "click_button", "button": "Play Video"}, ctx))
        self.assertIn("Successfully clicked button", r2.data)

        # 3. run_task
        r3 = asyncio.run(tool.call({"action": "run_task", "task": "click Submit"}, ctx))
        self.assertIn("Task completed successfully", r3.data)

        # 4. screenshot
        r4 = asyncio.run(tool.call({"action": "screenshot"}, ctx))
        self.assertIn("Captured page screenshot via CDP", r4.data)

    def test_browser_subagent_tool_permissions(self):
        """Test permission behavior: auto-allow when autonomous, ask when mutating in interactive."""
        tool = BrowserSubagentTool()

        ctx_auto = ToolContext(autonomous=True)
        perm1 = asyncio.run(tool.check_permissions({"action": "click_button", "button": "Submit"}, ctx_auto))
        self.assertEqual(perm1.behavior, PermissionBehavior.ALLOW)

        ctx_normal = ToolContext(autonomous=False, permission_mode="default")
        perm2 = asyncio.run(tool.check_permissions({"action": "click_button", "button": "Submit"}, ctx_normal))
        self.assertEqual(perm2.behavior, PermissionBehavior.ASK)

        # Read-only action allows without prompt
        perm3 = asyncio.run(tool.check_permissions({"action": "find_buttons"}, ctx_normal))
        self.assertEqual(perm3.behavior, PermissionBehavior.ALLOW)

    def test_browser_command(self):
        """Test /browser slash commands."""
        cmds = get_commands()
        self.assertEqual(len(cmds), 1)
        cmd = cmds[0]
        self.assertEqual(cmd.name, "browser")
        self.assertIn("cdp", cmd.aliases)

        state = AppState()

        # Status
        res_status = asyncio.run(cmd.execute("status", state))
        self.assertIn("Chrome DevTools Protocol (CDP) Browser Subagent Status", res_status.output)

        # Buttons
        res_btn = asyncio.run(cmd.execute("buttons", state))
        self.assertIn("Submit", res_btn.output)

        # Click
        res_click = asyncio.run(cmd.execute("click Submit", state))
        self.assertIn("Successfully clicked button", res_click.output)

        # Task
        res_task = asyncio.run(cmd.execute("task click Sign In", state))
        self.assertIn("Task completed successfully", res_task.output)


if __name__ == "__main__":
    unittest.main()
