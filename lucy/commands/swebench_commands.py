"""
SWE-bench slash commands — /swebench.

Run, monitor, and export Princeton SWE-bench benchmark evaluations.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from lucy.core.commands import Command, CommandResult


_LATEST_SWE_RESULTS = []


class SWEBenchCommand(Command):
    """Slash command to execute and manage SWE-bench evaluation runs."""

    @property
    def name(self) -> str:
        return "swebench"

    @property
    def aliases(self) -> list[str]:
        return ["swe"]

    @property
    def description(self) -> str:
        return "Run, monitor, and export SWE-bench evaluations against GitHub issues"

    @property
    def usage(self) -> str:
        return "/swebench [run <dataset.jsonl> | export [file] | status]"

    async def execute(self, args: str, state: Any) -> CommandResult:
        global _LATEST_SWE_RESULTS
        from lucy.core.swe_bench import SWEBenchRunner, SWEInstance

        parts = args.strip().split(None, 1)
        subcommand = parts[0].lower() if parts else ""
        sub_arg = parts[1].strip() if len(parts) > 1 else ""

        cwd = getattr(state, "cwd", os.getcwd())
        model = getattr(state, "model", "gemini")
        runner = SWEBenchRunner(workspace_root=cwd, model=model)

        if subcommand == "run":
            if not sub_arg:
                return CommandResult(
                    error="Usage: /swebench run <dataset.json or dataset.jsonl>"
                )

            dataset_path = Path(cwd) / sub_arg if not os.path.isabs(sub_arg) else Path(sub_arg)
            if not dataset_path.exists():
                return CommandResult(error=f"Dataset file not found: {dataset_path}")

            try:
                instances = runner.load_dataset(dataset_path)
            except Exception as e:
                return CommandResult(error=f"Failed to load SWE-bench dataset: {e}")

            if not instances:
                return CommandResult(output="No instances found in dataset.")

            lines = [f"Starting SWE-bench evaluation of {len(instances)} instances..."]
            results = []
            for idx, inst in enumerate(instances, 1):
                res = await runner.run_instance(inst)
                results.append(res)
                status_icon = "RESOLVED" if res.resolved else "UNRESOLVED"
                lines.append(f"[{idx}/{len(instances)}] {inst.instance_id}: {status_icon} ({res.execution_time_seconds}s)")

            _LATEST_SWE_RESULTS = results
            resolved_count = sum(1 for r in results if r.resolved)
            rate = (resolved_count / len(results)) * 100
            lines.append(f"\nCompleted: {resolved_count}/{len(results)} resolved ({rate:.1f}% pass rate).")
            lines.append("Export predictions with `/swebench export`.")
            return CommandResult(output="\n".join(lines))

        elif subcommand == "export":
            if not _LATEST_SWE_RESULTS:
                return CommandResult(error="No SWE-bench results to export. Run `/swebench run <file>` first.")
            out_file = sub_arg or "predictions.jsonl"
            out_path = Path(cwd) / out_file if not os.path.isabs(out_file) else Path(out_file)
            saved = runner.export_predictions(_LATEST_SWE_RESULTS, out_path)
            return CommandResult(output=f"Exported {len(_LATEST_SWE_RESULTS)} predictions to {saved}")

        elif subcommand == "status":
            if not _LATEST_SWE_RESULTS:
                return CommandResult(output="No SWE-bench evaluation run in current session.")
            resolved_count = sum(1 for r in _LATEST_SWE_RESULTS if r.resolved)
            rate = (resolved_count / len(_LATEST_SWE_RESULTS)) * 100
            lines = [
                f"Total instances evaluated: {len(_LATEST_SWE_RESULTS)}",
                f"Resolved: {resolved_count}",
                f"Pass rate: {rate:.1f}%",
                "Instances:",
            ]
            for r in _LATEST_SWE_RESULTS:
                lines.append(f" - {r.instance_id}: {'RESOLVED' if r.resolved else 'FAILED'} ({r.execution_time_seconds}s)")
            return CommandResult(output="\n".join(lines))

        else:
            return CommandResult(
                output=(
                    "SWE-bench Benchmark Runner\n\n"
                    "Commands:\n"
                    "  /swebench run <path>    Run autonomous evaluation on a dataset (.json/.jsonl)\n"
                    "  /swebench status        Show status and scores from the last evaluation run\n"
                    "  /swebench export [path] Export model patches to standard predictions.jsonl"
                )
            )


def get_commands() -> list[Command]:
    return [SWEBenchCommand()]

