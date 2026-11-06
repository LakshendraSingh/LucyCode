"""
Goal commands — /goal slash command for autonomous goal execution.

Commands:
  /goal <description>  - Start autonomous goal execution
  /goal status         - Show current goal progress
  /goal pause          - Pause current goal
  /goal resume [id]    - Resume a paused goal
  /goal list           - List all goals
  /goal cancel [id]    - Cancel current or specified goal
"""

from __future__ import annotations

import asyncio
import os
import time
from typing import Any

from lucy.core.commands import Command, CommandResult
from lucy.core.goal_engine import GoalConfig, GoalEngine, GoalStatus
from lucy.core.tool import ToolContext, get_tool_registry

# Global GoalEngine instance for the session
_GLOBAL_GOAL_ENGINE: GoalEngine | None = None


def get_goal_engine(config: GoalConfig | None = None) -> GoalEngine:
    """Get or initialize the global GoalEngine instance."""
    global _GLOBAL_GOAL_ENGINE
    if _GLOBAL_GOAL_ENGINE is None:
        _GLOBAL_GOAL_ENGINE = GoalEngine(config=config)
    return _GLOBAL_GOAL_ENGINE


class GoalCommand(Command):
    """Command for controlling autonomous goal-driven execution."""

    @property
    def name(self) -> str:
        return "goal"

    @property
    def aliases(self) -> list[str]:
        return ["goals", "autonomous", "auto"]

    @property
    def description(self) -> str:
        return "Autonomous goal-driven execution engine"

    @property
    def usage(self) -> str:
        return "/goal [<description> | status | pause | resume [id] | list | cancel [id]]"

    async def execute(self, args: str, state: Any) -> CommandResult:
        engine = get_goal_engine()
        raw_args = args.strip()

        if not raw_args:
            # Print usage and current status if active
            cur = engine.current_goal
            status_line = (
                f"\nCurrent active goal: [{cur.status.value.upper()}] {cur.goal_id} — {cur.goal_text}"
                if cur else "\nNo active goal."
            )
            return CommandResult(
                output=(
                    "🎯 LucyCode Goal-Driven Autonomous Engine\n\n"
                    "Usage:\n"
                    "  /goal <description>   Start autonomous execution of a goal\n"
                    "  /goal status          Show current goal progress and steps\n"
                    "  /goal pause           Pause current goal execution\n"
                    "  /goal resume [id]     Resume a paused goal\n"
                    "  /goal list            List all saved goals\n"
                    "  /goal cancel [id]     Cancel current or specified goal\n"
                    f"{status_line}"
                )
            )

        parts = raw_args.split(None, 1)
        subcommand = parts[0].lower()
        subarg = parts[1].strip() if len(parts) > 1 else ""

        # 1. /goal list
        if subcommand == "list":
            goals = engine.list_goals()
            if not goals:
                return CommandResult(output="No saved goals found in ~/.lucycode/goals/.")

            lines = ["📋 Saved Goals:\n", f"{'ID':<25} {'STATUS':<12} {'STEPS':<8} {'GOAL'}"]
            lines.append("─" * 75)
            for g in goals:
                done, total = g.plan.progress
                icon = {
                    GoalStatus.COMPLETED: "✅",
                    GoalStatus.FAILED: "❌",
                    GoalStatus.PAUSED: "⏸️",
                    GoalStatus.EXECUTING: "🔄",
                    GoalStatus.PLANNING: "📝",
                    GoalStatus.VERIFYING: "🧪",
                    GoalStatus.CORRECTING: "🛠️",
                }.get(g.status, "⬜")
                status_str = f"{icon} {g.status.value}"
                text_preview = (g.goal_text[:35] + "...") if len(g.goal_text) > 35 else g.goal_text
                lines.append(f"{g.goal_id:<25} {status_str:<12} {f'{done}/{total}':<8} {text_preview}")

            return CommandResult(output="\n".join(lines))

        # 2. /goal status
        if subcommand == "status":
            cur = engine.current_goal
            if not cur and subarg:
                cur = engine.get_goal(subarg)

            if not cur:
                goals = engine.list_goals()
                if goals:
                    cur = goals[0]

            if not cur:
                return CommandResult(error="No goal currently active or found.")

            done, total = cur.plan.progress
            lines = [
                f"🎯 Goal [{cur.status.value.upper()}]: {cur.goal_text}",
                f"ID: {cur.goal_id}",
                f"Progress: {done}/{total} steps ({((done/total)*100 if total else 0):.0f}%)",
                f"Tokens used: {cur.token_budget_used:,} / {cur.token_budget_total:,}",
                f"Elapsed: {int(cur.elapsed_seconds)}s",
                "\nPlan Steps:",
            ]
            for s in cur.plan.steps:
                icon = {
                    "done": "✅",
                    "in_progress": "🔄",
                    "failed": "❌",
                    "skipped": "⏭️",
                    "pending": "⬜",
                }.get(s.status.value, "⬜")
                lines.append(f"  {icon} Step {s.id}: {s.description}")
                if s.output:
                    lines.append(f"     Output: {s.output[:120]}...")
                if s.error:
                    lines.append(f"     Error: {s.error[:120]}")

            if cur.files_modified or cur.files_created:
                all_files = cur.files_created + cur.files_modified
                lines.append(f"\nFiles affected ({len(all_files)}):")
                for f in all_files[:10]:
                    lines.append(f"  • {f}")

            return CommandResult(output="\n".join(lines))

        # 3. /goal pause
        if subcommand == "pause":
            cp = await engine.pause()
            if cp:
                return CommandResult(
                    output=f"⏸️ Goal {cp.goal_id} paused. State saved to ~/.lucycode/goals/{cp.goal_id}.json\n"
                           f"Resume anytime with `/goal resume {cp.goal_id}`."
                )
            return CommandResult(error="No goal is currently running to pause.")

        # 4. /goal cancel
        if subcommand == "cancel":
            target_id = subarg if subarg else None
            success = engine.cancel_goal(target_id)
            if success:
                return CommandResult(output=f"🛑 Goal cancelled: {target_id or 'current'}")
            return CommandResult(error=f"Could not cancel goal: {target_id or 'no active goal'}")

        # 5. /goal resume [id]
        if subcommand == "resume":
            target_id = subarg
            if not target_id:
                # Find most recent paused or pending goal
                goals = engine.list_goals()
                paused = [g for g in goals if g.status in (GoalStatus.PAUSED, GoalStatus.PENDING, GoalStatus.EXECUTING)]
                if paused:
                    target_id = paused[0].goal_id
                elif goals:
                    target_id = goals[0].goal_id

            if not target_id:
                return CommandResult(error="Usage: /goal resume <goal_id> (no saved goals found to resume)")

            ctx = ToolContext(
                cwd=getattr(state, "cwd", os.getcwd()),
                permission_mode=getattr(state, "permission_mode", "auto_accept"),
                is_interactive=True,
            )

            lines_out = [f"▶️ Resuming goal {target_id}..."]
            try:
                async for event in engine.resume(goal_id=target_id, context=ctx, model=getattr(state, "model", None)):
                    summary = event.format_summary()
                    lines_out.append(summary)
            except Exception as e:
                return CommandResult(error=f"Error executing goal: {e}")

            return CommandResult(output="\n".join(lines_out[-25:]))

        # 6. /goal <description> -> Start new autonomous goal
        goal_text = raw_args
        ctx = ToolContext(
            cwd=getattr(state, "cwd", os.getcwd()),
            permission_mode=getattr(state, "permission_mode", "auto_accept"),
            is_interactive=True,
        )

        lines_out = [f"🚀 Starting autonomous goal: '{goal_text}'\n"]
        try:
            async for event in engine.execute(goal_text=goal_text, context=ctx, model=getattr(state, "model", None)):
                summary = event.format_summary()
                lines_out.append(summary)
        except asyncio.CancelledError:
            await engine.pause()
            lines_out.append("\n⏸️ Execution interrupted. Goal saved.")
        except Exception as e:
            return CommandResult(error=f"Goal execution failed: {e}")

        return CommandResult(output="\n".join(lines_out[-30:]))


def get_commands() -> list[Command]:
    """Export goal commands."""
    return [GoalCommand()]
