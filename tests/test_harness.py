"""
Unit tests for the LLM Evaluation and Benchmarking Harness.
"""

from __future__ import annotations

import asyncio
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

# Ensure project root is in sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lucy.core.harness import AgentHarness, HarnessResult, HarnessTask, get_harness
from lucy.commands.harness_commands import HarnessCommand


class TestHarness(unittest.TestCase):
    """Test suite for agent evaluation harness and benchmark tasks."""

    def setUp(self) -> None:
        self.tmp_dir = tempfile.mkdtemp()
        self.harness = AgentHarness(results_dir=Path(self.tmp_dir))

    def tearDown(self) -> None:
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def test_harness_builtin_tasks_loaded(self) -> None:
        """Verify built-in evaluation tasks are present across categories."""
        tasks = self.harness.list_tasks()
        self.assertGreaterEqual(len(tasks), 4)

        categories = {t.category for t in tasks}
        self.assertIn("coding", categories)
        self.assertIn("debugging", categories)
        self.assertIn("security", categories)
        self.assertIn("workstation", categories)

    def test_harness_task_execution_with_custom_executor(self) -> None:
        """Test executing and grading a task with a deterministic mock executor."""
        task = HarnessTask(
            id="test_calc",
            name="Create Calculator Module",
            category="coding",
            prompt="Write calc.py with add(a, b)",
            expected_files=["calc.py"],
            validation_commands=[
                "python3 -c 'import calc; assert calc.add(2, 3) == 5'",
            ],
        )

        async def mock_executor(prompt: str, cwd: Path, model: str | None):
            # Create the expected file
            (cwd / "calc.py").write_text("def add(a, b):\n    return a + b\n")
            return {"turns": 1, "tokens": 120, "output": "Created calc.py"}

        result = asyncio.run(self.harness.run_task(task, custom_executor=mock_executor))
        self.assertTrue(result.passed)
        self.assertEqual(result.score, 1.0)
        self.assertEqual(result.turns_used, 1)
        self.assertGreaterEqual(result.duration_seconds, 0.0)
        self.assertEqual(len(result.validation_results), 2)  # 1 file check + 1 command check

    def test_harness_task_failure_grading(self) -> None:
        """Test that failing validation commands produce a score < 1.0 and passed=False."""
        task = HarnessTask(
            id="test_fail",
            name="Failing Task",
            category="coding",
            prompt="Do nothing",
            expected_files=["missing_file.py"],
            validation_commands=[
                "python3 -c 'exit(1)'",
            ],
        )

        async def mock_empty_executor(prompt: str, cwd: Path, model: str | None):
            return {"turns": 1, "tokens": 50, "output": "Did nothing"}

        result = asyncio.run(self.harness.run_task(task, custom_executor=mock_empty_executor))
        self.assertFalse(result.passed)
        self.assertEqual(result.score, 0.0)

    def test_harness_run_suite_and_report(self) -> None:
        """Test running a suite of tasks and aggregating report."""
        task1 = HarnessTask(
            id="t1",
            name="Task 1",
            category="coding",
            prompt="Write a.txt",
            expected_files=["a.txt"],
        )
        task2 = HarnessTask(
            id="t2",
            name="Task 2",
            category="coding",
            prompt="Write b.txt",
            expected_files=["b.txt"],
        )
        harness = AgentHarness(tasks=[task1, task2], results_dir=Path(self.tmp_dir))

        async def executor(prompt: str, cwd: Path, model: str | None):
            (cwd / "a.txt").write_text("hello")
            (cwd / "b.txt").write_text("world")
            return {"turns": 1, "tokens": 80, "output": "done"}

        report = asyncio.run(harness.run_suite(suite_name="coding", custom_executor=executor))
        self.assertEqual(report.total_tasks, 2)
        self.assertEqual(report.passed_tasks, 2)
        self.assertEqual(report.pass_rate, 100.0)
        self.assertIn("Benchmark Suite: coding", report.summary_table())

    def test_harness_slash_command(self) -> None:
        """Test /harness slash command outputs."""
        cmd = HarnessCommand()
        self.assertEqual(cmd.name, "harness")

        # /harness help
        res_help = asyncio.run(cmd.execute("help", None))
        self.assertIn("Evaluation Harness Commands", res_help.output)

        # /harness list
        res_list = asyncio.run(cmd.execute("list", None))
        self.assertIn("code_fibonacci", res_list.output)
        self.assertIn("bugfix_json_parser", res_list.output)


if __name__ == "__main__":
    unittest.main()
