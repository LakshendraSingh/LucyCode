"""
Unit tests for SWE-bench runner and slash command.
"""

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

from lucy.commands.swebench_commands import SWEBenchCommand
from lucy.core.swe_bench import SWEBenchRunner, SWEInstance, SWEResult


class TestSWEBench(unittest.TestCase):
    """Test SWE-bench data loading, execution, and export pipeline."""

    def test_load_dataset_json(self):
        sample_data = [
            {
                "instance_id": "django__django-11001",
                "problem_statement": "Fix ordering in QuerySet when raw SQL expressions are used.",
                "repo": "django/django",
                "base_commit": "abc1234",
                "test_patch": "diff --git a/tests/test.py b/tests/test.py\n",
                "fail_to_pass": ["tests.test_query.OrderTests"],
            }
        ]
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
            json.dump(sample_data, f)
            temp_path = f.name

        try:
            instances = SWEBenchRunner.load_dataset(temp_path)
            self.assertEqual(len(instances), 1)
            self.assertEqual(instances[0].instance_id, "django__django-11001")
            self.assertIn("QuerySet", instances[0].problem_statement)
            self.assertEqual(instances[0].fail_to_pass, ["tests.test_query.OrderTests"])
        finally:
            Path(temp_path).unlink(missing_ok=True)

    def test_load_dataset_jsonl(self):
        line1 = json.dumps({"instance_id": "pytest-dev__pytest-5221", "problem_statement": "Fixture ordering bug"})
        line2 = json.dumps({"instance_id": "psf__requests-863", "problem_statement": "Redirect hook bug"})
        with tempfile.NamedTemporaryFile("w", suffix=".jsonl", delete=False) as f:
            f.write(f"{line1}\n{line2}\n")
            temp_path = f.name

        try:
            instances = SWEBenchRunner.load_dataset(temp_path)
            self.assertEqual(len(instances), 2)
            self.assertEqual(instances[0].instance_id, "pytest-dev__pytest-5221")
            self.assertEqual(instances[1].instance_id, "psf__requests-863")
        finally:
            Path(temp_path).unlink(missing_ok=True)

    def test_export_predictions(self):
        results = [
            SWEResult(
                instance_id="sympy__sympy-12481",
                model="gemini",
                resolved=True,
                model_patch="diff --git a/sympy/core.py b/sympy/core.py\n+ # fix\n",
                execution_time_seconds=3.4,
            ),
            SWEResult(
                instance_id="sympy__sympy-12482",
                model="gemini",
                resolved=False,
                model_patch="",
                execution_time_seconds=1.2,
            ),
        ]
        with tempfile.TemporaryDirectory() as tmpdir:
            out_file = Path(tmpdir) / "predictions.jsonl"
            SWEBenchRunner.export_predictions(results, out_file)

            self.assertTrue(out_file.exists())
            lines = [json.loads(line) for line in out_file.read_text().splitlines() if line]
            self.assertEqual(len(lines), 2)
            self.assertEqual(lines[0]["instance_id"], "sympy__sympy-12481")
            self.assertIn("# fix", lines[0]["model_patch"])
            self.assertEqual(lines[0]["model_name_or_path"], "gemini")

    @patch("lucy.core.goal_engine.GoalEngine")
    def test_run_instance_mocked(self, mock_engine_cls):
        mock_engine = mock_engine_cls.return_value
        mock_engine.execute_goal = AsyncMock(return_value=None)

        runner = SWEBenchRunner(model="mock-model")
        inst = SWEInstance(
            instance_id="test-inst-1",
            problem_statement="Refactor module logic",
        )

        import asyncio
        res = asyncio.run(runner.run_instance(inst))
        self.assertEqual(res.instance_id, "test-inst-1")
        self.assertEqual(res.model, "mock-model")
        self.assertIsInstance(res.execution_time_seconds, float)


class TestSWEBenchCommand(unittest.IsolatedAsyncioTestCase):
    """Test /swebench slash command."""

    async def test_swebench_help_and_status(self):
        cmd = SWEBenchCommand()
        class DummyState:
            cwd = "/tmp"
            model = "test-model"

        # Usage check
        res = await cmd.execute("", DummyState())
        self.assertIn("SWE-bench Benchmark Runner", res.output)

        # Status check when empty
        res_stat = await cmd.execute("status", DummyState())
        self.assertIn("No SWE-bench evaluation run", res_stat.output)


if __name__ == "__main__":
    unittest.main()

