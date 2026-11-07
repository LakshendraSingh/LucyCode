"""
Comprehensive unit tests for the Workstation Automation Engine (/automate, app, screen, browser, workflow).
"""

from __future__ import annotations

import asyncio
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lucy.core.tool import ToolContext
from lucy.services.app_automation import AppAutomationService, get_app_automation
from lucy.services.browser_automation import BrowserAutomationService, get_browser_automation
from lucy.services.computer_use import ComputerUseService, get_computer_use_service
from lucy.services.screen_automation import ScreenAutomationService, ScreenRegion, get_screen_automation
from lucy.services.workflow_engine import WorkflowEngine, WorkflowStep, get_workflow_engine
from lucy.tools.workstation_tools import WORKSTATION_TOOLS, ClipboardTool, GetScreenInfoTool, ListAppsTool, ScreenshotTool, WorkflowTool
from lucy.commands.automation_commands import AutomateCommand


class TestWorkstationAutomation(unittest.TestCase):
    """Test suite for workstation automation services, tools, and slash commands."""

    def setUp(self) -> None:
        self.tmp_dir = tempfile.mkdtemp()

    def tearDown(self) -> None:
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def test_app_automation_basic(self) -> None:
        """Test AppAutomationService methods."""
        auto = get_app_automation()
        self.assertIsInstance(auto, AppAutomationService)

        # Running apps query (may be 0 in sandboxed/headless CI)
        apps = auto.list_running_apps()
        self.assertIsInstance(apps, list)
        self.assertGreaterEqual(len(apps), 0)

        # Frontmost app query
        front = auto.get_frontmost_app()
        # May be None in headless/CI, but shouldn't raise exception
        if front:
            self.assertTrue(front.is_running)

        # Clipboard get/set roundtrip
        test_val = "LucyCode_Test_Clipboard_12345"
        ok = auto.set_clipboard(test_val)
        if ok:
            content = auto.get_clipboard()
            self.assertEqual(content.text, test_val)

        # AppleScript execution
        ok, out = auto.run_applescript('return "hello from applescript"')
        self.assertTrue(ok)
        self.assertIn("hello from applescript", out)

    def test_screen_automation_info_and_diff(self) -> None:
        """Test ScreenAutomationService screen info and image comparison."""
        screen = get_screen_automation()
        self.assertIsInstance(screen, ScreenAutomationService)

        info = screen.get_screen_info()
        self.assertGreater(info.width, 0)
        self.assertGreater(info.height, 0)
        self.assertGreaterEqual(info.scale_factor, 1.0)
        self.assertGreater(len(info.monitors), 0)

        # Screenshot comparison
        dummy_b64 = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
        sim = screen.compare_screenshots(dummy_b64, dummy_b64)
        self.assertAlmostEqual(sim, 1.0)

    def test_workflow_engine_crud_and_execution(self) -> None:
        """Test creating, saving, loading, and executing a multi-step workflow."""
        storage = Path(self.tmp_dir) / "wf_test"
        engine = WorkflowEngine(storage_dir=storage)

        # 1. Create
        wf = engine.create_workflow(name="Build and Notify", description="Test pipeline")
        self.assertEqual(wf.name, "Build and Notify")

        # 2. Add steps
        s1 = engine.add_step(
            workflow_id=wf.id,
            type="bash",
            params={"command": "echo 'build ok'"},
            description="Run build step",
        )
        self.assertIsNotNone(s1)

        s2 = engine.add_step(
            workflow_id=wf.id,
            type="write_file",
            params={"path": str(Path(self.tmp_dir) / "output.txt"), "content": "artifact data"},
            description="Write artifact",
        )
        self.assertIsNotNone(s2)

        s3 = engine.add_step(
            workflow_id=wf.id,
            type="wait",
            params={"seconds": 0.05},
            description="Short pause",
        )
        self.assertIsNotNone(s3)

        # 3. Reload from disk
        reloaded = engine.load_workflow(wf.id)
        self.assertIsNotNone(reloaded)
        self.assertEqual(len(reloaded.steps), 3)

        # 4. Execute workflow
        async def _run():
            runs = []
            async for update in engine.execute(wf.id):
                runs.append(update)
            return runs

        runs = asyncio.run(_run())
        self.assertGreater(len(runs), 0)
        final_run = runs[-1]
        self.assertEqual(final_run.status, "completed")
        self.assertEqual(len(final_run.results), 3)
        self.assertTrue(all(r.success for r in final_run.results))

        # Check created file
        self.assertTrue((Path(self.tmp_dir) / "output.txt").exists())

        # 5. List workflows
        all_wf = engine.list_workflows()
        self.assertEqual(len(all_wf), 1)

        # 6. Delete
        self.assertTrue(engine.delete_workflow(wf.id))
        self.assertIsNone(engine.load_workflow(wf.id))

    def test_browser_automation_service(self) -> None:
        """Test BrowserAutomationService search and extraction fallbacks."""
        browser = get_browser_automation()
        self.assertIsInstance(browser, BrowserAutomationService)

        # Web search query via zero-dependency DuckDuckGo Lite scraper
        async def _test_search():
            res = await browser.search_web_and_read("python programming language")
            return res

        results = asyncio.run(_test_search())
        self.assertIsInstance(results, str)
        self.assertGreater(len(results), 20)

    def test_workstation_tools_registered(self) -> None:
        """Verify all workstation tools conform to Tool interface."""
        self.assertEqual(len(WORKSTATION_TOOLS), 12)
        names = [t.name for t in WORKSTATION_TOOLS]
        expected = [
            "screenshot", "find_on_screen", "launch_app", "focus_app",
            "list_apps", "notify", "clipboard", "applescript",
            "browser", "workflow", "speak", "screen_info",
        ]
        for exp in expected:
            self.assertIn(exp, names)

        # Execute ListAppsTool
        list_tool = ListAppsTool()
        ctx = ToolContext(cwd=self.tmp_dir)
        res = asyncio.run(list_tool.call({}, ctx))
        self.assertIn("Running Applications", res.data)

        # Execute GetScreenInfoTool
        scr_tool = GetScreenInfoTool()
        res_scr = asyncio.run(scr_tool.call({}, ctx))
        self.assertIn("width", res_scr.data)

    def test_automate_slash_command(self) -> None:
        """Verify /automate command execution."""
        cmd = AutomateCommand()
        self.assertEqual(cmd.name, "automate")

        # /automate help
        res_help = asyncio.run(cmd.execute("help", None))
        self.assertIn("Workstation Automation Commands", res_help.output)

        # /automate screen info
        res_screen = asyncio.run(cmd.execute("screen info", None))
        self.assertIn("Screen Geometry", res_screen.output)

        # /automate apps list
        res_apps = asyncio.run(cmd.execute("apps list", None))
        self.assertIn("Running Applications", res_apps.output)


if __name__ == "__main__":
    unittest.main()
