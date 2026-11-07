"""
Slash command suite for LLM evaluation harness (/harness, /benchmark).
"""

from __future__ import annotations

import asyncio
from typing import Any

from lucy.core.commands import Command, CommandResult, register_command
from lucy.core.harness import get_harness


class HarnessCommand(Command):
    """Command suite for benchmarking and evaluating LLM model performance."""

    name = "harness"
    description = "Run LLM evaluation benchmarks and measure coding task scores"
    aliases = ["benchmark", "eval"]

    async def execute(self, args_str: str, state: Any) -> CommandResult:
        parts = args_str.strip().split(maxsplit=1) if args_str else []
        sub = parts[0].lower() if parts else "list"
        arg = parts[1].strip() if len(parts) > 1 else ""

        harness = get_harness()

        if sub in ("help", "--help", "-h"):
            help_text = """
LLM Evaluation Harness Commands (/harness)
------------------------------------------
  /harness list                     List all available evaluation tasks
  /harness run [all|coding|debugging|security|workstation|<task_id>]
                                    Run benchmark suite or specific task
  /harness report                   Show summary of latest benchmark execution
  /harness recursive [domain]       Run Harness² recursive self-improvement cycle
"""
            return CommandResult(output=help_text.strip())

        elif sub in ("recursive", "harness2", "optimize", "rsi"):
            from lucy.commands.harness2_commands import Harness2Command
            h2_cmd = Harness2Command()
            args_forward = f"optimize {arg}" if sub in ("recursive", "optimize", "rsi") else arg
            return await h2_cmd.execute(args_forward, state)

        elif sub == "list":
            tasks = harness.list_tasks()
            lines = [f"{'ID':<24} {'CATEGORY':<14} {'NAME'}", "-" * 60]
            for t in tasks:
                lines.append(f"{t.id:<24} {t.category:<14} {t.name}")
            return CommandResult(output="\n".join(lines))

        elif sub == "run":
            suite = arg or "all"
            target_model = getattr(state, "model", None) if state else None

            # Check if arg is a single task id
            if suite in harness.tasks:
                task = harness.tasks[suite]
                res = await harness.run_task(task, model=target_model)
                status = "PASS" if res.passed else "FAIL"
                out = [
                    f"Task: {res.task_name} ({res.task_id})",
                    f"Result: {status} (Score: {res.score:.2f})",
                    f"Duration: {res.duration_seconds:.2f}s | Turns: {res.turns_used} | Tokens: {res.tokens_used}",
                ]
                if res.validation_results:
                    out.append("\nValidation Checks:")
                    for c in res.validation_results:
                        chk_st = "✓" if c.get("passed") else "✗"
                        out.append(f"  {chk_st} {c.get('check')}")
                return CommandResult(output="\n".join(out))

            # Run full suite
            report = await harness.run_suite(suite_name=suite, model=target_model)
            return CommandResult(output=report.summary_table())

        elif sub == "report":
            # Find latest json in results_dir
            files = sorted(harness.results_dir.glob("benchmark_*.json"), key=lambda f: f.stat().st_mtime, reverse=True)
            if not files:
                return CommandResult(output="No benchmark reports found. Run '/harness run' to generate one.")
            import json
            with open(files[0], "r", encoding="utf-8") as f:
                d = json.load(f)
            from lucy.core.harness import BenchmarkReport, HarnessResult
            rep = BenchmarkReport(
                suite_name=d["suite_name"],
                model_name=d["model_name"],
                started_at=d["started_at"],
                finished_at=d["finished_at"],
                total_tasks=d["total_tasks"],
                passed_tasks=d["passed_tasks"],
                overall_score=d["overall_score"],
                total_duration_seconds=d["total_duration_seconds"],
                total_tokens_used=d["total_tokens_used"],
                results=[HarnessResult(**r) for r in d.get("results", [])],
            )
            return CommandResult(output=rep.summary_table())

        return CommandResult(error=f"Unknown harness command: '{sub}'. Run '/harness help' for usage.")


def get_commands() -> list[Command]:
    return [HarnessCommand()]


def register():
    register_command(HarnessCommand())

