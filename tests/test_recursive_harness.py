"""
Unit tests for Harness²: Recursive Agent Harnessing (Google Research inspired).
Tests the Propose -> Probe -> Compose loop, Experience Library, and slash commands.
"""

import asyncio
from pathlib import Path
import tempfile
import unittest

from lucy.commands.harness2_commands import Harness2Command
from lucy.commands.harness_commands import HarnessCommand
from lucy.core.recursive_harness import (
    ExperienceEntry,
    ExperienceLibrary,
    Harness2Engine,
    HarnessMutation,
    HarnessTarget,
    ProbeReport,
)


class TestRecursiveHarness(unittest.TestCase):
    """Test suite for Harness² architecture."""

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.storage_dir = Path(self.temp_dir.name)
        self.engine = Harness2Engine(storage_dir=self.storage_dir)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_experience_library_seed_and_query(self):
        lib = self.engine.experience_library
        self.assertGreater(len(lib.entries), 0)

        # Query by keyword
        matches = lib.query("Write a python function with def and types")
        self.assertGreater(len(matches), 0)
        self.assertTrue(any(m.domain == "coding" for m in matches))

        # Query by domain
        sec_matches = lib.query("bash script", domain="security")
        self.assertTrue(any(m.domain == "security" for m in sec_matches))

        # Test prompt formatting
        prompt_block = lib.format_for_prompt("python function")
        self.assertIn("[Recursive Harness Knowledge - Experience Library]", prompt_block)
        self.assertIn("CODING", prompt_block)

    def test_propose_mutation(self):
        mut = self.engine.propose(
            target=HarnessTarget.SKILL_RULES,
            target_name="coding",
            rationale="Test rationale",
            proposed_content="Always ensure variables are initialized before use.",
        )
        self.assertIsNotNone(mut.id)
        self.assertEqual(mut.target, HarnessTarget.SKILL_RULES)
        self.assertFalse(mut.composed)

        # Check persistence
        self.assertTrue((self.storage_dir / "mutations.json").exists())

    def test_propose_from_failure(self):
        mut_syntax = self.engine.propose_from_failure(
            task_id="test_task",
            failure_log="SyntaxError: invalid syntax at line 14",
            category="debugging",
        )
        self.assertEqual(mut_syntax.target, HarnessTarget.ERROR_POLICY)
        self.assertIn("syntax check", mut_syntax.proposed_content)

        mut_perm = self.engine.propose_from_failure(
            task_id="test_perm",
            failure_log="PermissionError: [Errno 1] Operation not permitted",
            category="workstation",
        )
        self.assertEqual(mut_perm.target, HarnessTarget.TOOL_GUIDANCE)
        self.assertIn("/tmp/", mut_perm.proposed_content)

    def test_probe_and_compose_cycle(self):
        mut = self.engine.propose(
            target=HarnessTarget.SKILL_RULES,
            target_name="coding",
            rationale="Unit test probe",
            proposed_content="Always document inputs and outputs.",
        )

        async def mock_probe_executor(prompt: str, cwd: Path, model: str | None):
            if "[Harness Rule" in prompt:
                # Candidate succeeds on code_fibonacci
                fib_code = (
                    "def fibonacci(n: int):\n"
                    "    '''Generate Fibonacci numbers up to n elements.\n"
                    "    >>> list(fibonacci(7))\n"
                    "    [0, 1, 1, 2, 3, 5, 8]\n"
                    "    '''\n"
                    "    a, b = 0, 1\n"
                    "    for _ in range(n):\n"
                    "        yield a\n"
                    "        a, b = b, a + b\n"
                )
                (cwd / "fibonacci.py").write_text(fib_code, encoding="utf-8")
                return {"turns": 1, "tokens": 80, "output": "Created fibonacci.py"}
            else:
                return {"turns": 1, "tokens": 10, "output": "Failed baseline"}

        # Probe against built-in task code_fibonacci
        report = asyncio.run(self.engine.probe(mut, task_ids=["code_fibonacci"], custom_executor=mock_probe_executor))
        self.assertIsInstance(report, ProbeReport)
        self.assertEqual(report.mutation_id, mut.id)
        self.assertTrue(report.improved)
        self.assertGreater(report.candidate_score, report.baseline_score)
        self.assertIn("code_fibonacci", report.behavioral_contrast)

        # Compose
        composed = self.engine.compose(mut, report)
        self.assertTrue(composed)
        self.assertTrue(mut.composed)
        self.assertIsNotNone(mut.composed_at)
        self.assertIsNotNone(mut.applied_experience_id)

    def test_end_to_end_recursive_cycle(self):
        async def mock_cycle_executor(prompt: str, cwd: Path, model: str | None):
            if "[Harness Rule" in prompt:
                fix_code = "def parse_mapping(data):\n    return {str(k).lower(): v for k, v in data.items()}\n"
                (cwd / "parser.py").write_text(fix_code, encoding="utf-8")
                return {"turns": 1, "tokens": 50, "output": "Fixed parser"}
            return {"turns": 1, "tokens": 10, "output": "Failed"}

        mut, rep, ok = asyncio.run(self.engine.run_recursive_cycle(
            target_name="debugging",
            custom_executor=mock_cycle_executor,
        ))
        self.assertIsNotNone(mut)
        self.assertIsNotNone(rep)
        self.assertTrue(ok)
        self.assertTrue(mut.composed)

    def test_rejection_when_no_improvement(self):
        mut = self.engine.propose(
            target=HarnessTarget.SYSTEM_PROMPT,
            target_name="coding",
            rationale="Failing probe test",
            proposed_content="Do not create any files.",
        )

        async def mock_failing_executor(prompt: str, cwd: Path, model: str | None):
            return {"turns": 1, "tokens": 10, "output": "Nothing done"}

        report = asyncio.run(self.engine.probe(mut, task_ids=["code_fibonacci"], custom_executor=mock_failing_executor))
        self.assertFalse(report.improved)

        composed = self.engine.compose(mut, report)
        self.assertFalse(composed)
        self.assertFalse(mut.composed)

    def test_harness2_slash_commands(self):
        cmd = Harness2Command()

        # Help
        res_help = asyncio.run(cmd.execute("help", None))
        self.assertIn("Harness²: Recursive Agent Harnessing", res_help.output)

        # Status
        res_status = asyncio.run(cmd.execute("status", None))
        self.assertIn("Active Mutations", res_status.output)

        # Propose
        res_prop = asyncio.run(cmd.execute("propose coding Always write clean doctests", None))
        self.assertIn("Created mutation", res_prop.output)

        # Library
        res_lib = asyncio.run(cmd.execute("library", None))
        self.assertIn("Continual Experience Library", res_lib.output)

        # Reset
        res_rst = asyncio.run(cmd.execute("reset", None))
        self.assertIn("reset to clean baseline", res_rst.output)

    def test_harness_recursive_alias(self):
        h_cmd = HarnessCommand()
        res = asyncio.run(h_cmd.execute("recursive coding", None))
        self.assertIn("Harness² Recursive Cycle Complete", res.output)


if __name__ == "__main__":
    unittest.main()

