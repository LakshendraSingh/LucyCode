"""
Unit tests for Autonomous Execution Mode across CLI, commands, prompt, and tools.
"""

from __future__ import annotations

import asyncio
import os
import sys
import unittest
from unittest.mock import patch

# Ensure project root is in sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from click.testing import CliRunner
from lucy.commands.permission_commands import AutonomousCommand, PermissionsCommand
from lucy.core.config import Config, load_config
from lucy.core.context import build_system_prompt
from lucy.core.state import AppState
from lucy.core.tool import ToolContext, PermissionBehavior, PermissionResult
from lucy.main import cli
from lucy.permissions.rules import RuleEngine
from lucy.permissions.types import PermissionDecision
from lucy.tools.agent_tool import AgentTool
from lucy.tools.ask_user_tool import AskUserQuestionTool
from lucy.tools.bash_tool import BashTool
from lucy.tools.file_edit_tool import FileEditTool
from lucy.tools.file_write_tool import FileWriteTool
from lucy.tools.powershell_tool import PowerShellTool
from lucy.tools.web_fetch_tool import WebFetchTool


class TestAutonomousMode(unittest.TestCase):
    """Test suite for autonomous execution mode."""

    def test_ask_user_question_autonomous_mode(self):
        """Verify AskUserQuestionTool never prompts stdin in autonomous mode."""
        tool = AskUserQuestionTool()
        context = ToolContext(autonomous=True, is_interactive=True)

        result = asyncio.run(
            tool.call(
                {
                    "question": "Which database engine should we configure?",
                    "options": ["PostgreSQL", "SQLite", "MySQL"],
                    "default": "PostgreSQL",
                },
                context,
            )
        )

        self.assertIn("PostgreSQL", result.data)
        self.assertIn("Autonomous Mode Active", result.data)

    def test_ask_user_question_auto_accept_or_non_interactive(self):
        """Verify fallback when permission_mode is auto_accept or context is non-interactive."""
        tool = AskUserQuestionTool()

        # permission_mode = "auto_accept"
        ctx1 = ToolContext(permission_mode="auto_accept", is_interactive=True)
        res1 = asyncio.run(
            tool.call(
                {"question": "Confirm migration?", "options": ["Yes", "No"], "default": "Yes"},
                ctx1,
            )
        )
        self.assertIn("Autonomous Mode Active", res1.data)
        self.assertIn("Yes", res1.data)

        # is_interactive = False
        ctx2 = ToolContext(is_interactive=False)
        res2 = asyncio.run(
            tool.call(
                {"question": "Select format", "options": ["JSON", "YAML"]},
                ctx2,
            )
        )
        self.assertIn("JSON", res2.data)

    def test_build_system_prompt_autonomous_injection(self):
        """Verify autonomous directive is injected into system prompt when enabled."""
        prompt_auto = build_system_prompt(is_autonomous=True)
        self.assertIn("## Autonomous Execution Mode (ACTIVE)", prompt_auto)
        self.assertIn("NEVER call AskUserQuestion", prompt_auto)
        self.assertIn("Make executive decisions independently", prompt_auto)

        prompt_normal = build_system_prompt(is_autonomous=False)
        self.assertNotIn("## Autonomous Execution Mode (ACTIVE)", prompt_normal)

    def test_autonomous_slash_command(self):
        """Test /autonomous slash command execution and state synchronization."""
        cmd = AutonomousCommand()
        state = AppState(autonomous=False, permission_mode="default")

        # Turn ON
        res_on = asyncio.run(cmd.execute("on", state))
        self.assertTrue(state.autonomous)
        self.assertEqual(state.permission_mode, "auto_accept")
        self.assertIn("ENABLED", res_on.output)

        # Check status
        res_status = asyncio.run(cmd.execute("status", state))
        self.assertIn("ENABLED", res_status.output)

        # Turn OFF
        res_off = asyncio.run(cmd.execute("off", state))
        self.assertFalse(state.autonomous)
        self.assertEqual(state.permission_mode, "default")
        self.assertIn("DISABLED", res_off.output)

        # Toggle
        res_toggle = asyncio.run(cmd.execute("", state))
        self.assertTrue(state.autonomous)
        self.assertEqual(state.permission_mode, "auto_accept")
        self.assertIn("ENABLED", res_toggle.output)

    def test_permissions_command_autonomous_mode(self):
        """Test /permissions mode autonomous."""
        cmd = PermissionsCommand()
        state = AppState(autonomous=False, permission_mode="default")

        res = asyncio.run(cmd.execute("mode autonomous", state))
        self.assertTrue(state.autonomous)
        self.assertEqual(state.permission_mode, "auto_accept")
        self.assertIn("autonomous", res.output)

        res_back = asyncio.run(cmd.execute("mode default", state))
        self.assertFalse(state.autonomous)
        self.assertEqual(state.permission_mode, "default")
        self.assertIn("default", res_back.output)

    def test_rule_engine_autonomous_mode(self):
        """Verify rule engine allows actions in autonomous permission mode."""
        engine = RuleEngine()
        check1 = engine.check("Bash", command="rm -rf /tmp/test", permission_mode="autonomous")
        self.assertEqual(check1.decision, PermissionDecision.ALLOWED)

        check2 = engine.check("Bash", command="rm -rf /tmp/test", permission_mode="auto_accept")
        self.assertEqual(check2.decision, PermissionDecision.ALLOWED)

    def test_tools_check_permissions_autonomous(self):
        """Verify mutating tools bypass manual prompts in autonomous mode."""
        ctx = ToolContext(autonomous=True, permission_mode="auto_accept")

        # BashTool
        bash = BashTool()
        perm = asyncio.run(bash.check_permissions({"command": "rm -rf foo"}, ctx))
        self.assertEqual(perm.behavior, PermissionBehavior.ALLOW)

        # FileEditTool
        edit = FileEditTool()
        perm = asyncio.run(edit.check_permissions({"file_path": "foo.txt"}, ctx))
        self.assertEqual(perm.behavior, PermissionBehavior.ALLOW)

        # FileWriteTool
        write = FileWriteTool()
        perm = asyncio.run(write.check_permissions({"file_path": "foo.txt"}, ctx))
        self.assertEqual(perm.behavior, PermissionBehavior.ALLOW)

        # AgentTool
        agent = AgentTool()
        perm = asyncio.run(agent.check_permissions({"task": "subtask"}, ctx))
        self.assertEqual(perm.behavior, PermissionBehavior.ALLOW)

        # WebFetchTool
        fetch = WebFetchTool()
        perm = asyncio.run(fetch.check_permissions({"url": "https://example.com"}, ctx))
        self.assertEqual(perm.behavior, PermissionBehavior.ALLOW)

        # PowerShellTool
        pwsh = PowerShellTool()
        perm = asyncio.run(pwsh.check_permissions({"command": "dir"}, ctx))
        self.assertEqual(perm.behavior, PermissionBehavior.ALLOW)

    def test_config_autonomous_env_var(self):
        """Verify LUCY_AUTONOMOUS environment variable is respected."""
        with patch.dict(os.environ, {"LUCY_AUTONOMOUS": "1"}):
            cfg = load_config()
            self.assertTrue(cfg.autonomous)

        with patch.dict(os.environ, {"LUCY_AUTONOMOUS": "false"}):
            cfg2 = load_config()
            self.assertFalse(cfg2.autonomous)

    def test_cli_autonomous_flags(self):
        """Verify CLI flags --autonomous, --auto, and -y are registered."""
        runner = CliRunner()
        result = runner.invoke(cli, ["--help"])
        self.assertEqual(result.exit_code, 0)
        self.assertIn("--autonomous", result.output)
        self.assertIn("--auto", result.output)
        self.assertIn("-y", result.output)

    def test_welcome_banner_disclaimer(self):
        """Verify that the welcome banner at program startup contains the mistake disclaimer."""
        from io import StringIO
        from rich.console import Console
        from lucy.tui.renderer import render_welcome

        buf = StringIO()
        console = Console(file=buf, color_system=None, width=120)
        render_welcome(console, "test-model")
        output = buf.getvalue()

        self.assertIn("Lucy is an AI and can make mistakes", output)
        self.assertIn("Always review code, diffs, and commands before execution", output)


if __name__ == "__main__":
    unittest.main()
