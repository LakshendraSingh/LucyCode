"""
Plan commands — /plan, /ultraplan.
"""

from __future__ import annotations

from typing import Any

from lucy.core.commands import Command, CommandResult


class PlanCommand(Command):
    @property
    def name(self) -> str: return "plan"
    @property
    def description(self) -> str: return "Enter plan mode (read-only analysis)"
    @property
    def usage(self) -> str: return "/plan [on|off|status]"

    async def execute(self, args: str, state: Any) -> CommandResult:
        action = args.strip().lower()
        if action == "off":
            state.permission_mode = "default"
            return CommandResult(output="✅ Plan mode OFF — normal execution resumed")
        if action == "status":
            is_plan = state.permission_mode == "plan"
            return CommandResult(output=f"Plan mode: {'ON' if is_plan else 'OFF'}")
        # Default: turn on
        state.permission_mode = "plan"
        return CommandResult(
            output="📋 Plan mode ON — only read-only operations allowed\n"
                   "Use /plan off to resume normal execution"
        )


class UltraPlanCommand(Command):
    @property
    def name(self) -> str: return "ultraplan"
    @property
    def description(self) -> str: return "Deep analysis: enter plan mode with max thinking"
    @property
    def usage(self) -> str: return "/ultraplan [topic]"

    async def execute(self, args: str, state: Any) -> CommandResult:
        from lucy.core.config import get_config
        config = get_config()

        # Enter plan mode
        state.permission_mode = "plan"

        # Boost thinking budget
        old_budget = config.max_thinking_tokens
        config.max_thinking_tokens = 100000

        topic = args.strip()
        msg = (
            "🧠 UltraPlan mode activated:\n"
            "  • Plan mode: ON (read-only)\n"
            f"  • Thinking budget: {config.max_thinking_tokens:,} tokens (was {old_budget:,})\n"
        )
        if topic:
            msg += f"  • Focus: {topic}\n"
            # Inject planning prompt
            from lucy.core.message import create_user_message
            plan_msg = create_user_message(
                f"Please create a detailed plan for: {topic}\n\n"
                f"Analyze the codebase, consider all edge cases, and provide a "
                f"step-by-step implementation plan. Do NOT make any changes — "
                f"only analyze and plan."
            )
            state.messages.append(plan_msg)
            msg += "  • Planning prompt injected"

        msg += "\nUse /plan off to exit"
        return CommandResult(output=msg)


def get_commands() -> list[Command]:
    return [PlanCommand(), UltraPlanCommand()]
