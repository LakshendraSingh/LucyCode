"""
Unit tests for the Skills Engine and Skill slash commands.
"""

from __future__ import annotations

import asyncio
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock

# Ensure project root is in sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lucy.core.commands import find_command
from lucy.commands.skill_commands import SkillCommand
from lucy.core.context import build_system_prompt
from lucy.core.skills_engine import (
    SkillsEngine,
    Skill,
    SkillActivation,
    SkillMetadata,
    _parse_simple_yaml,
    parse_frontmatter,
)


class TestSkills(unittest.TestCase):
    """Test suite for Declarative Skills Engine."""

    def test_frontmatter_fallback_parser(self) -> None:
        """Test that the pure-python YAML frontmatter parser handles standard frontmatter."""
        sample = """
name: my-skill
description: "A custom skill description"
version: "1.2.0"
priority: 7
tags: ["alpha", "beta"]
activates_on:
  keywords: ["foo", "bar"]
  file_patterns: ["*.py", "*.ts"]
  project_files: ["package.json"]
  always: false
"""
        data = _parse_simple_yaml(sample)
        self.assertEqual(data["name"], "my-skill")
        self.assertEqual(data["description"], "A custom skill description")
        self.assertEqual(data["version"], "1.2.0")
        self.assertEqual(data["priority"], 7)
        self.assertEqual(data["tags"], ["alpha", "beta"])
        self.assertEqual(data["activates_on"]["keywords"], ["foo", "bar"])
        self.assertEqual(data["activates_on"]["file_patterns"], ["*.py", "*.ts"])
        self.assertEqual(data["activates_on"]["project_files"], ["package.json"])
        self.assertFalse(data["activates_on"]["always"])

    def test_parse_frontmatter_with_body(self) -> None:
        """Test parsing frontmatter with markdown body."""
        content = """---
name: testing
description: Best practices for tests
priority: 5
---

# Testing Best Practices

1. Arrange
2. Act
3. Assert
"""
        meta, body = parse_frontmatter(content)
        self.assertEqual(meta["name"], "testing")
        self.assertEqual(meta["priority"], 5)
        self.assertIn("# Testing Best Practices", body)
        self.assertIn("3. Assert", body)

    def test_builtin_skills_discovery(self) -> None:
        """Test discovering all 10 built-in skills."""
        engine = SkillsEngine()
        skills = engine.discover(force_refresh=True)

        expected_skills = {
            "debugging",
            "security-audit",
            "code-review",
            "performance",
            "testing",
            "refactoring",
            "python",
            "typescript",
            "git-workflow",
            "api-design",
        }

        discovered_names = {s.metadata.name for s in skills}
        self.assertTrue(expected_skills.issubset(discovered_names), f"Missing skills: {expected_skills - discovered_names}")

        for skill in skills:
            self.assertEqual(skill.source_type, "builtin")
            self.assertGreater(len(skill.instructions), 50)
            self.assertNotEqual(skill.metadata.description, "")

    def test_context_activation_keywords(self) -> None:
        """Test auto-activation triggered by keywords in prompt."""
        engine = SkillsEngine()
        engine.discover(force_refresh=True)

        # Prompt about debugging
        active = engine.activate_for_context(
            cwd=tempfile.gettempdir(),
            user_prompt="I hit a strange crash and error traceback in production",
        )
        active_names = [s.metadata.name for s in active]
        self.assertIn("debugging", active_names)

        # Prompt about security
        active = engine.activate_for_context(
            cwd=tempfile.gettempdir(),
            user_prompt="Perform a security audit for SQL injection vulnerabilities",
        )
        active_names = [s.metadata.name for s in active]
        self.assertIn("security-audit", active_names)

    def test_context_activation_project_files(self) -> None:
        """Test auto-activation triggered by project indicator files."""
        temp_dir = tempfile.mkdtemp()
        try:
            # Create tsconfig.json -> typescript skill
            (Path(temp_dir) / "tsconfig.json").write_text("{}", encoding="utf-8")

            engine = SkillsEngine()
            active = engine.activate_for_context(cwd=temp_dir, user_prompt="Explain this interface")
            active_names = [s.metadata.name for s in active]
            self.assertIn("typescript", active_names)
        finally:
            shutil.rmtree(temp_dir)

    def test_context_activation_file_patterns(self) -> None:
        """Test auto-activation triggered by file patterns."""
        engine = SkillsEngine()
        active = engine.activate_for_context(
            cwd=tempfile.gettempdir(),
            user_prompt="Check this test file",
            files=["test_auth.py"],
        )
        active_names = [s.metadata.name for s in active]
        self.assertIn("testing", active_names)

    def test_max_active_skills_cap(self) -> None:
        """Test that skills engine respects max_active_skills cap."""
        engine = SkillsEngine(max_active_skills=3)
        active = engine.activate_for_context(
            cwd=tempfile.gettempdir(),
            user_prompt="Please debug, test, benchmark performance, refactor, review code, and check security vulnerability",
        )
        self.assertLessEqual(len(active), 3)

    def test_manual_activate_and_deactivate(self) -> None:
        """Test explicit activation and deactivation."""
        engine = SkillsEngine()
        engine.discover(force_refresh=True)

        # Activate
        self.assertTrue(engine.activate("performance"))
        self.assertIn("performance", engine._active_skills)
        perf_skill = engine.get_skill("performance")
        self.assertIsNotNone(perf_skill)
        self.assertTrue(perf_skill.is_active)

        # Persists through context evaluation
        engine.activate_for_context(cwd=tempfile.gettempdir(), user_prompt="some neutral text")
        self.assertIn("performance", engine._active_skills)

        # Deactivate
        self.assertTrue(engine.deactivate("performance"))
        self.assertNotIn("performance", engine._active_skills)
        self.assertFalse(engine.get_skill("performance").is_active)

        # Deactivate again handled cleanly
        engine.deactivate("performance")
        self.assertNotIn("performance", engine._active_skills)

    def test_create_skill_custom(self) -> None:
        """Test creating a custom skill file."""
        temp_dir = tempfile.mkdtemp()
        try:
            engine = SkillsEngine()
            skill_path = Path(temp_dir) / "custom-dev" / "SKILL.md"
            skill = engine.create_skill(
                name="custom-dev",
                description="Custom internal guidelines",
                instructions="# Custom Guidelines\nAlways use strict types.",
                path=str(skill_path),
                keywords=["internal", "custom"],
            )
            self.assertEqual(skill.metadata.name, "custom-dev")
            self.assertTrue(skill_path.exists())
            self.assertIn("Always use strict types.", skill.instructions)

            fetched = engine.get_skill("custom-dev")
            self.assertIsNotNone(fetched)
            self.assertEqual(fetched.metadata.name, "custom-dev")
        finally:
            shutil.rmtree(temp_dir)

    def test_prompt_injection_order_and_content(self) -> None:
        """Test system prompt injection formatting and ordering."""
        prompt = build_system_prompt(
            cwd=tempfile.gettempdir(),
            lucymd="Custom instructions from LUCY.md",
            user_prompt="I need to debug this bug traceback",
        )

        self.assertIn("You are Lucy Code", prompt)
        self.assertIn("## Active Skills & Domain Guidelines", prompt)
        self.assertIn("debugging", prompt)
        self.assertIn("<user_instructions>", prompt)
        self.assertIn("Custom instructions from LUCY.md", prompt)

        base_idx = prompt.find("You are Lucy Code")
        skills_idx = prompt.find("## Active Skills & Domain Guidelines")
        user_idx = prompt.find("<user_instructions>")

        self.assertTrue(base_idx < skills_idx < user_idx, "Skills must be after base prompt and before LUCY.md")

    def test_slash_command_execution(self) -> None:
        """Test /skill slash command actions."""
        async def _test():
            cmd = find_command("skill")
            self.assertIsNotNone(cmd)
            self.assertIsInstance(cmd, SkillCommand)

            mock_state = MagicMock()
            mock_state.cwd = tempfile.gettempdir()

            # /skill list
            res_list = await cmd.execute("list", mock_state)
            self.assertIn("Discovered Skills:", res_list.output)
            self.assertIn("debugging", res_list.output)

            # /skill info debugging
            res_info = await cmd.execute("info debugging", mock_state)
            self.assertIn("Skill: debugging", res_info.output)
            self.assertIn("Priority:", res_info.output)
            self.assertIn("Instructions:", res_info.output)

            # /skill activate debugging
            res_act = await cmd.execute("activate debugging", mock_state)
            self.assertIn("Activated skill", res_act.output)

            # /skill deactivate debugging
            res_deact = await cmd.execute("deactivate debugging", mock_state)
            self.assertIn("Deactivated skill", res_deact.output)

            # /skill refresh
            res_ref = await cmd.execute("refresh", mock_state)
            self.assertIn("Refreshed skills", res_ref.output)

        asyncio.run(_test())


if __name__ == "__main__":
    unittest.main()
