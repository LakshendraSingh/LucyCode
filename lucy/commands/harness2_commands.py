"""
Slash command suite for Harness²: Recursive Agent Harnessing (/harness2, /recursive-harness).
"""

from __future__ import annotations

import asyncio
from typing import Any

from lucy.core.commands import Command, CommandResult, register_command
from lucy.core.recursive_harness import HarnessTarget, get_harness2


class Harness2Command(Command):
    """Command suite for Harness²: Recursive Agent Harnessing (Google Research inspired)."""

    name = "harness2"
    description = "Harness² recursive agent self-improvement (Propose-Probe-Compose cycle)"
    aliases = ["recursive-harness", "rsi"]

    async def execute(self, args_str: str, state: Any) -> CommandResult:
        parts = args_str.strip().split(maxsplit=2) if args_str else []
        sub = parts[0].lower() if parts else "status"
        arg1 = parts[1].strip() if len(parts) > 1 else ""
        arg2 = parts[2].strip() if len(parts) > 2 else ""

        h2 = get_harness2()

        if sub in ("help", "--help", "-h"):
            help_text = """
Harness²: Recursive Agent Harnessing (/harness2)
------------------------------------------------
  /harness2 status                     View active harness mutations and experience library
  /harness2 optimize [domain]          Run automated recursive Propose-Probe-Compose cycle
  /harness2 propose [domain] [rule]    Propose a targeted harness mutation
  /harness2 probe [task_id]            Probe latest mutation against benchmark task
  /harness2 compose [mutation_id]      Compose/merge winning mutation into harness
  /harness2 library                    View distilled lessons in Continual Experience Library
  /harness2 reset                      Reset mutations to base configuration
"""
            return CommandResult(output=help_text.strip())

        elif sub == "status":
            st = h2.get_status()
            lines = [
                "Harness²: Recursive Agent Harnessing",
                "=" * 60,
                f"Storage Directory:   {st['storage_dir']}",
                f"Total Experiences:   {st['total_experiences']}",
                f"Active Mutations:    {st['total_mutations']}",
                f"Composed (Merged):   {st['composed_mutations']}",
                "-" * 60,
                "Recent Mutations:",
            ]
            if st["recent_mutations"]:
                for m in st["recent_mutations"]:
                    status = "COMPOSED" if m.get("composed") else "PENDING"
                    lines.append(f"  [{m['id']}] ({m['target']}:{m['target_name']}) {status} - {m['proposed_content'][:50]}...")
            else:
                lines.append("  (No mutations recorded yet. Run '/harness2 optimize' to begin)")
            return CommandResult(output="\n".join(lines))

        elif sub == "optimize":
            domain = arg1 or "coding"
            focus_rule = arg2 or None
            mutation, probe_report, success = await h2.run_recursive_cycle(
                target_name=domain,
                target_type=HarnessTarget.SKILL_RULES,
                focus_prompt=focus_rule,
            )
            res_str = "SUCCESS (Composed & Distilled into Experience Library)" if success else "REJECTED (No metric gain)"
            out = [
                f"Harness² Recursive Cycle Complete for domain: '{domain}'",
                "=" * 60,
                f"Mutation ID:         {mutation.id}",
                f"Target Component:    {mutation.target.value}:{mutation.target_name}",
                f"Proposed Rule:       {mutation.proposed_content}",
                f"Baseline Score:      {probe_report.baseline_score:.2f}",
                f"Candidate Score:     {probe_report.candidate_score:.2f} (Delta: {probe_report.score_delta:+.2f})",
                f"Behavioral Contrast: {probe_report.behavioral_contrast}",
                f"Cycle Outcome:       {res_str}",
            ]
            return CommandResult(output="\n".join(out))

        elif sub == "propose":
            domain = arg1 or "coding"
            rule = arg2 or "Always perform defensive error checking and input validation."
            mut = h2.propose(
                target=HarnessTarget.SKILL_RULES,
                target_name=domain,
                rationale=f"User proposed mutation for {domain}",
                proposed_content=rule,
            )
            return CommandResult(output=f"Created mutation [{mut.id}] for {domain}.\nContent: {rule}\nRun '/harness2 probe' to evaluate it.")

        elif sub == "probe":
            if not h2._active_mutations:
                return CommandResult(error="No active mutations to probe. Use '/harness2 propose' or '/harness2 optimize'.")
            target_mut = h2._active_mutations[-1]
            task_ids = [arg1] if arg1 else None
            report = await h2.probe(target_mut, task_ids=task_ids)
            return CommandResult(output=report.summary())

        elif sub == "compose":
            mut_id = arg1 or (h2._active_mutations[-1].id if h2._active_mutations else None)
            if not mut_id:
                return CommandResult(error="No mutation ID specified.")
            mut = next((m for m in h2._active_mutations if m.id == mut_id), None)
            if not mut:
                return CommandResult(error=f"Mutation '{mut_id}' not found.")
            report = await h2.probe(mut)
            success = h2.compose(mut, report)
            if success:
                return CommandResult(output=f"Successfully composed mutation [{mut.id}] into active harness and distilled experience.")
            else:
                return CommandResult(output=f"Mutation [{mut.id}] failed probe validation and was not composed.")

        elif sub == "library":
            entries = h2.experience_library.entries
            lines = [
                f"Continual Experience Library ({len(entries)} lessons)",
                "=" * 65,
                f"{'ID':<18} {'DOMAIN':<12} {'CONF':<6} {'LESSON'}",
                "-" * 65,
            ]
            for e in entries:
                lines.append(f"{e.id:<18} {e.domain:<12} {e.confidence:<6.2f} {e.lesson[:45]}...")
            return CommandResult(output="\n".join(lines))

        elif sub == "reset":
            h2.reset_mutations()
            return CommandResult(output="Harness² mutations reset to clean baseline. Experience library restored to defaults.")

        return CommandResult(error=f"Unknown harness2 command: '{sub}'. Run '/harness2 help' for usage.")


def get_commands() -> list[Command]:
    return [Harness2Command()]


def register():
    register_command(Harness2Command())

