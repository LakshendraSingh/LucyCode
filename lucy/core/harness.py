"""
Agentic LLM Evaluation and Benchmarking Harness for LucyCode.

Provides isolated test environments, task execution pipelines, automated grading,
tool call tracking, token/cost measurement, and reproducible benchmark suites.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import shutil
import subprocess
import sys
import tempfile
import time
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Callable

logger = logging.getLogger(__name__)


@dataclass
class HarnessTask:
    """Specification of an evaluation scenario for the LLM agent."""
    id: str
    name: str
    category: str  # coding, debugging, workstation, security, refactoring
    prompt: str
    initial_files: dict[str, str] = field(default_factory=dict)
    validation_commands: list[str] = field(default_factory=list)
    expected_files: list[str] = field(default_factory=list)
    forbidden_patterns: list[str] = field(default_factory=list)
    max_turns: int = 10
    timeout_seconds: float = 120.0
    tags: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class HarnessResult:
    """Grading and metrics from executing a HarnessTask."""
    task_id: str
    task_name: str
    category: str
    passed: bool
    score: float  # 0.0 to 1.0
    duration_seconds: float
    turns_used: int = 0
    tokens_used: int = 0
    estimated_cost: float = 0.0
    tool_calls_count: int = 0
    tool_calls_breakdown: dict[str, int] = field(default_factory=dict)
    stdout: str = ""
    error_message: str | None = None
    validation_results: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class BenchmarkReport:
    """Aggregated benchmark report over multiple tasks."""
    suite_name: str
    model_name: str
    started_at: float
    finished_at: float
    total_tasks: int
    passed_tasks: int
    overall_score: float
    total_duration_seconds: float
    total_tokens_used: int
    results: list[HarnessResult] = field(default_factory=list)

    @property
    def pass_rate(self) -> float:
        return (self.passed_tasks / self.total_tasks * 100.0) if self.total_tasks > 0 else 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "suite_name": self.suite_name,
            "model_name": self.model_name,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "total_tasks": self.total_tasks,
            "passed_tasks": self.passed_tasks,
            "pass_rate": round(self.pass_rate, 2),
            "overall_score": round(self.overall_score, 3),
            "total_duration_seconds": round(self.total_duration_seconds, 2),
            "total_tokens_used": self.total_tokens_used,
            "results": [r.to_dict() for r in self.results],
        }

    def summary_table(self) -> str:
        lines = [
            f"Benchmark Suite: {self.suite_name} (Model: {self.model_name})",
            "=" * 72,
            f"{'Task ID':<16} {'Category':<14} {'Result':<8} {'Score':<8} {'Time (s)':<10} {'Turns'}",
            "-" * 72,
        ]
        for r in self.results:
            status = "PASS" if r.passed else "FAIL"
            lines.append(
                f"{r.task_id:<16} {r.category:<14} {status:<8} {r.score:<8.2f} {r.duration_seconds:<10.2f} {r.turns_used}"
            )
        lines.append("-" * 72)
        lines.append(
            f"Summary: {self.passed_tasks}/{self.total_tasks} passed ({self.pass_rate:.1f}%) | "
            f"Avg Score: {self.overall_score:.2f} | Time: {self.total_duration_seconds:.2f}s | Tokens: {self.total_tokens_used:,}"
        )
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Standard Built-in Benchmark Tasks
# ---------------------------------------------------------------------------

BUILTIN_TASKS: list[HarnessTask] = [
    HarnessTask(
        id="code_fibonacci",
        name="Fibonacci Generator with Type Hints",
        category="coding",
        prompt="Write a Python module 'fibonacci.py' containing an efficient generator function fibonacci(n: int) -> Iterator[int] with full docstring and doctest.",
        expected_files=["fibonacci.py"],
        validation_commands=[
            "python3 -c 'import fibonacci, inspect; assert inspect.isgeneratorfunction(fibonacci.fibonacci)'",
            "python3 -c 'import fibonacci; assert list(fibonacci.fibonacci(7)) == [0, 1, 1, 2, 3, 5, 8]'",
            "python3 -m doctest fibonacci.py",
        ],
        tags=["python", "algorithms"],
    ),
    HarnessTask(
        id="bugfix_json_parser",
        name="Bugfix Dict Key Type Error",
        category="debugging",
        prompt="Fix the bug in 'parser.py' so that integer keys in JSON are converted to strings properly without raising AttributeError, and all tests pass.",
        initial_files={
            "parser.py": "def parse_mapping(data):\n    # BUG: assumes all keys are strings and calls lower()\n    return {k.lower(): v for k, v in data.items()}\n",
            "test_parser.py": "from parser import parse_mapping\ndef test_parse():\n    assert parse_mapping({'A': 1, 2: 'two'}) == {'a': 1, '2': 'two'}\n",
        },
        expected_files=["parser.py"],
        validation_commands=[
            "python3 -m unittest test_parser.py",
        ],
        tags=["debugging", "python"],
    ),
    HarnessTask(
        id="workstation_script",
        name="System Status Report Script",
        category="workstation",
        prompt="Create a script 'report.py' that collects current machine hostname, python version, and CPU count, and writes them to 'system_status.json'.",
        expected_files=["report.py"],
        validation_commands=[
            "python3 report.py",
            "python3 -c 'import json; d = json.load(open(\"system_status.json\")); assert \"python_version\" in d and \"cpu_count\" in d'",
        ],
        tags=["workstation", "system"],
    ),
    HarnessTask(
        id="security_sanitizer",
        name="Command Injection Sanitizer",
        category="security",
        prompt="Write a module 'sanitizer.py' with a function sanitize_shell_arg(arg: str) -> str that safely escapes shell arguments using standard library shlex.quote and rejects args containing null bytes.",
        expected_files=["sanitizer.py"],
        validation_commands=[
            "python3 -c 'import sanitizer; assert sanitizer.sanitize_shell_arg(\"hello world\") == \"\\\"hello world\\\"\" or sanitizer.sanitize_shell_arg(\"hello world\") == \"\\'hello world\\'\"'",
            "python3 -c 'import sanitizer; assert sanitizer.sanitize_shell_arg(\"; rm -rf /\") != \"; rm -rf /\"'",
            "python3 -c 'import sanitizer; \ntry:\n sanitizer.sanitize_shell_arg(\"bad\\x00byte\"); assert False\nexcept ValueError:\n pass'",
        ],
        tags=["security", "sanitization"],
    ),
]


class AgentHarness:
    """Execution harness for evaluating LLM agent performance in isolated sandboxes."""

    def __init__(self, tasks: list[HarnessTask] | None = None, results_dir: Path | None = None) -> None:
        self.tasks = {t.id: t for t in (tasks or BUILTIN_TASKS)}
        self.results_dir = results_dir or (Path.home() / ".lucycode" / "harness")
        try:
            self.results_dir.mkdir(parents=True, exist_ok=True)
        except (PermissionError, OSError) as e:
            logger.debug("Failed creating harness results_dir %s: %s, falling back to /tmp/lucycode_harness", self.results_dir, e)
            self.results_dir = Path("/tmp/lucycode_harness")
            self.results_dir.mkdir(parents=True, exist_ok=True)

    def register_task(self, task: HarnessTask) -> None:
        self.tasks[task.id] = task

    def get_task(self, task_id: str) -> HarnessTask | None:
        return self.tasks.get(task_id)

    def list_tasks(self, category: str | None = None) -> list[HarnessTask]:
        if category:
            return [t for t in self.tasks.values() if t.category == category]
        return list(self.tasks.values())

    async def run_task(
        self,
        task: HarnessTask,
        model: str | None = None,
        custom_executor: Callable[[str, Path, str | None], Any] | None = None,
    ) -> HarnessResult:
        """Execute a single evaluation scenario in an isolated temporary directory."""
        t0 = time.time()
        temp_dir = Path(tempfile.mkdtemp(prefix=f"lucy_harness_{task.id}_"))
        tool_breakdown: dict[str, int] = {}
        total_tokens = 0
        turns = 0
        stdout_capture = []

        try:
            # 1. Setup initial environment files
            for rel_path, content in task.initial_files.items():
                p = temp_dir / rel_path
                p.parent.mkdir(parents=True, exist_ok=True)
                p.write_text(content, encoding="utf-8")

            # 2. Execute task with agent
            if custom_executor:
                exec_res = await custom_executor(task.prompt, temp_dir, model)
                if isinstance(exec_res, dict):
                    turns = exec_res.get("turns", 1)
                    total_tokens = exec_res.get("tokens", 0)
                    stdout_capture.append(exec_res.get("output", ""))
            else:
                # Use Lucy's goal engine or query runner in isolated mode
                from lucy.core.tool import ToolContext, get_tool_registry
                from lucy.core.query import QueryParams, query_loop
                from lucy.core.message import create_user_message, AssistantMessage, StreamEvent

                reg = get_tool_registry()
                ctx = ToolContext(cwd=str(temp_dir), permission_mode="auto_accept", is_interactive=False)
                user_msg = create_user_message(task.prompt)
                abort_evt = asyncio.Event()

                params = QueryParams(
                    messages=[user_msg],
                    system_prompt="You are Lucy Code. Complete the requested programming or workstation task precisely. Verify your changes.",
                    tools=reg,
                    tool_context=ctx,
                    model=model,
                    max_turns=task.max_turns,
                    abort_event=abort_evt,
                )

                try:
                    async for event in query_loop(params):
                        if isinstance(event, AssistantMessage):
                            turns += 1
                            if event.usage:
                                total_tokens += (event.usage.input_tokens + event.usage.output_tokens)
                            for block in event.get_tool_use_blocks():
                                tool_breakdown[block.name] = tool_breakdown.get(block.name, 0) + 1
                            text = event.get_text()
                            if text:
                                stdout_capture.append(text)
                except Exception as ex:
                    logger.debug("Harness task loop exception: %s", ex)

            # 3. Grade Results
            duration = time.time() - t0
            validation_records: list[dict[str, Any]] = []
            checks_passed = 0
            total_checks = len(task.expected_files) + len(task.validation_commands)

            # Check expected files
            for ef in task.expected_files:
                target_file = temp_dir / ef
                exists = target_file.exists()
                if exists:
                    checks_passed += 1
                validation_records.append({
                    "check": f"File exists: {ef}",
                    "passed": exists,
                })

            # Check validation commands
            for cmd in task.validation_commands:
                try:
                    proc = subprocess.run(
                        cmd,
                        shell=True,
                        cwd=str(temp_dir),
                        capture_output=True,
                        text=True,
                        timeout=15,
                    )
                    passed = (proc.returncode == 0)
                    if passed:
                        checks_passed += 1
                    validation_records.append({
                        "check": cmd,
                        "passed": passed,
                        "stdout": proc.stdout[:300],
                        "stderr": proc.stderr[:300],
                    })
                except Exception as ex:
                    validation_records.append({
                        "check": cmd,
                        "passed": False,
                        "error": str(ex),
                    })

            score = (checks_passed / total_checks) if total_checks > 0 else 1.0
            passed = (score == 1.0)

            return HarnessResult(
                task_id=task.id,
                task_name=task.name,
                category=task.category,
                passed=passed,
                score=score,
                duration_seconds=round(duration, 3),
                turns_used=turns,
                tokens_used=total_tokens,
                tool_calls_count=sum(tool_breakdown.values()),
                tool_calls_breakdown=tool_breakdown,
                stdout="\n".join(stdout_capture),
                validation_results=validation_records,
            )

        except Exception as e:
            return HarnessResult(
                task_id=task.id,
                task_name=task.name,
                category=task.category,
                passed=False,
                score=0.0,
                duration_seconds=round(time.time() - t0, 3),
                error_message=str(e),
            )
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)

    async def run_suite(
        self,
        suite_name: str = "all",
        model: str | None = None,
        custom_executor: Callable[[str, Path, str | None], Any] | None = None,
    ) -> BenchmarkReport:
        """Run a collection of tasks and produce an aggregated report."""
        t0 = time.time()
        if suite_name == "all":
            selected = list(self.tasks.values())
        else:
            selected = [t for t in self.tasks.values() if t.category == suite_name or suite_name in t.tags]

        results: list[HarnessResult] = []
        for task in selected:
            res = await self.run_task(task, model=model, custom_executor=custom_executor)
            results.append(res)

        t1 = time.time()
        passed_cnt = sum(1 for r in results if r.passed)
        avg_score = (sum(r.score for r in results) / len(results)) if results else 0.0
        tokens = sum(r.tokens_used for r in results)

        report = BenchmarkReport(
            suite_name=suite_name,
            model_name=model or "default",
            started_at=t0,
            finished_at=t1,
            total_tasks=len(results),
            passed_tasks=passed_cnt,
            overall_score=avg_score,
            total_duration_seconds=t1 - t0,
            total_tokens_used=tokens,
            results=results,
        )

        self._save_report(report)
        return report

    def _save_report(self, report: BenchmarkReport) -> None:
        fname = f"benchmark_{report.suite_name}_{int(report.started_at)}.json"
        path = self.results_dir / fname
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(report.to_dict(), f, indent=2)
        except Exception as e:
            logger.error("Failed to save benchmark report: %s", e)


_harness: AgentHarness | None = None


def get_harness() -> AgentHarness:
    global _harness
    if _harness is None:
        _harness = AgentHarness()
    return _harness
