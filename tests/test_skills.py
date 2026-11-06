"""
Unit tests for the Skills Engine and Skill slash commands.
"""

from __future__ import annotations

import os
import shutil
import tempfile
from pathlib import Path
from unittest.mock import MagicMock

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


def test_frontmatter_fallback_parser():
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
    assert data["name"] == "my-skill"
    assert data["description"] == "A custom skill description"
    assert data["version"] == "1.2.0"
    assert data["priority"] == 7
    assert data["tags"] == ["alpha", "beta"]
    assert data["activates_on"]["keywords"] == ["foo", "bar"]
    assert data["activates_on"]["file_patterns"] == ["*.py", "*.ts"]
    assert data["activates_on"]["project_files"] == ["package.json"]
    assert data["activates_on"]["always"] is False


def test_parse_frontmatter_with_body():
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
    assert meta["name"] == "testing"
    assert meta["priority"] == 5
    assert "# Testing Best Practices" in body
    assert "3. Assert" in body


def test_builtin_skills_discovery():
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
    assert expected_skills.issubset(discovered_names), f"Missing skills: {expected_skills - discovered_names}"

    for skill in skills:
        assert skill.source_type == "builtin"
        assert len(skill.instructions) > 50
        assert skill.metadata.description != ""


def test_context_activation_keywords():
    """Test auto-activation triggered by keywords in prompt."""
    engine = SkillsEngine()
    engine.discover(force_refresh=True)

    # Prompt about debugging
    active = engine.activate_for_context(
        cwd=tempfile.gettempdir(),
        user_prompt="I hit a strange crash and error traceback in production",
    )
    active_names = [s.metadata.name for s in active]
    assert "debugging" in active_names

    # Prompt about security
    active = engine.activate_for_context(
        cwd=tempfile.gettempdir(),
        user_prompt="Perform a security audit for SQL injection vulnerabilities",
    )
    active_names = [s.metadata.name for s in active]
    assert "security-audit" in active_names


def test_context_activation_project_files():
    """Test auto-activation triggered by project indicator files."""
    temp_dir = tempfile.mkdtemp()
    try:
        # Create tsconfig.json -> typescript skill
        (Path(temp_dir) / "tsconfig.json").write_text("{}", encoding="utf-8")

        engine = SkillsEngine()
        active = engine.activate_for_context(cwd=temp_dir, user_prompt="Explain this interface")
        active_names = [s.metadata.name for s in active]
        assert "typescript" in active_names
    finally:
        shutil.rmtree(temp_dir)


def test_context_activation_file_patterns():
    """Test auto-activation triggered by file patterns."""
    engine = SkillsEngine()
    active = engine.activate_for_context(
        cwd=tempfile.gettempdir(),
        user_prompt="Check this test file",
        files=["test_auth.py"],
    )
    active_names = [s.metadata.name for s in active]
    assert "testing" in active_names


def test_max_active_skills_cap():
    """Test that skills engine respects max_active_skills cap."""
    engine = SkillsEngine(max_active_skills=3)
    # Trigger many skills simultaneously: debug, security, review, performance, refactor, test
    active = engine.activate_for_context(
        cwd=tempfile.gettempdir(),
        user_prompt="Please debug, test, benchmark performance, refactor, review code, and check security vulnerability",
    )
    assert len(active) <= 3


def test_manual_activate_and_deactivate():
    """Test explicit activation and deactivation."""
    engine = SkillsEngine()
    engine.discover(force_refresh=True)

    # Activate
    assert engine.activate("performance") is True
    assert "performance" in engine._active_skills
    perf_skill = engine.get_skill("performance")
    assert perf_skill is not None and perf_skill.is_active is True

    # Persists through context evaluation
    engine.activate_for_context(cwd=tempfile.gettempdir(), user_prompt="some neutral text")
    assert "performance" in engine._active_skills

    # Deactivate
    assert engine.deactivate("performance") is True
    assert "performance" not in engine._active_skills
    assert engine.get_skill("performance").is_active is False

    # Deactivate again returns True (idempotent) or handled cleanly
    engine.deactivate("performance")
    assert "performance" not in engine._active_skills


def test_create_skill_custom():
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
        assert skill.metadata.name == "custom-dev"
        assert skill_path.exists()
        assert "Always use strict types." in skill.instructions

        # Ensure it can be retrieved and activated
        fetched = engine.get_skill("custom-dev")
        assert fetched is not None
        assert fetched.metadata.name == "custom-dev"
    finally:
        shutil.rmtree(temp_dir)


def test_prompt_injection_order_and_content():
    """Test system prompt injection formatting and ordering."""
    prompt = build_system_prompt(
        cwd=tempfile.gettempdir(),
        lucymd="Custom instructions from LUCY.md",
        user_prompt="I need to debug this bug traceback",
    )

    # 1. Base prompt should appear first
    assert "You are Lucy Code" in prompt

    # 2. Skills section should appear
    assert "## Active Skills & Domain Guidelines" in prompt
    assert "debugging" in prompt

    # 3. User instructions should appear after skills
    assert "<user_instructions>" in prompt
    assert "Custom instructions from LUCY.md" in prompt

    base_idx = prompt.find("You are Lucy Code")
    skills_idx = prompt.find("## Active Skills & Domain Guidelines")
    user_idx = prompt.find("<user_instructions>")

    assert base_idx < skills_idx < user_idx, "Skills must be after base prompt and before LUCY.md"


async def test_slash_command_execution():
    """Test /skill slash command actions."""
    cmd = find_command("skill")
    assert cmd is not None
    assert isinstance(cmd, SkillCommand)

    mock_state = MagicMock()
    mock_state.cwd = tempfile.gettempdir()

    # /skill list
    res_list = await cmd.execute("list", mock_state)
    assert "Discovered Skills:" in res_list.output
    assert "debugging" in res_list.output

    # /skill info debugging
    res_info = await cmd.execute("info debugging", mock_state)
    assert "Skill: debugging" in res_info.output
    assert "Priority:" in res_info.output
    assert "Instructions:" in res_info.output

    # /skill activate debugging
    res_act = await cmd.execute("activate debugging", mock_state)
    assert "Activated skill" in res_act.output

    # /skill deactivate debugging
    res_deact = await cmd.execute("deactivate debugging", mock_state)
    assert "Deactivated skill" in res_deact.output

    # /skill refresh
    res_ref = await cmd.execute("refresh", mock_state)
    assert "Refreshed skills" in res_ref.output
