"""
Billing commands — /cost, /usage, /stats.
"""

from __future__ import annotations

from typing import Any

from lucy.core.commands import Command, CommandResult


class CostCommand(Command):
    @property
    def name(self) -> str: return "cost"
    @property
    def aliases(self) -> list[str]: return ["billing"]
    @property
    def description(self) -> str: return "Show session cost and token usage"

    async def execute(self, args: str, state: Any) -> CommandResult:
        c = state.cost
        lines = [
            "💰 Session Cost:",
            f"  Total: {c.format_cost()}",
            f"  Turns: {c.turn_count}",
            f"",
            "📊 Token Usage:",
            f"  Input:  {c.total_input_tokens:>12,}",
            f"  Output: {c.total_output_tokens:>12,}",
            f"  Cache creation: {c.total_cache_creation_tokens:>8,}",
            f"  Cache read:     {c.total_cache_read_tokens:>8,}",
            f"  Total:  {c.format_tokens()}",
        ]
        return CommandResult(output="\n".join(lines))


class UsageCommand(Command):
    @property
    def name(self) -> str: return "usage"
    @property
    def description(self) -> str: return "Show detailed usage statistics"

    async def execute(self, args: str, state: Any) -> CommandResult:
        from lucy.core.message import UserMessage, AssistantMessage
        user_msgs = sum(1 for m in state.messages if isinstance(m, UserMessage))
        asst_msgs = sum(1 for m in state.messages if isinstance(m, AssistantMessage))
        tool_calls = 0
        for m in state.messages:
            if isinstance(m, AssistantMessage):
                tool_calls += len(m.get_tool_use_blocks())

        lines = [
            "📈 Usage Statistics:",
            f"  Messages: {len(state.messages)} ({user_msgs} user, {asst_msgs} assistant)",
            f"  Tool calls: {tool_calls}",
            f"  Model: {state.model}",
            f"  Session: {state.conversation_id[:8]}",
            f"  Cost: {state.cost.format_cost()}",
            f"  Tokens: {state.cost.format_tokens()}",
        ]
        if state.cost.turn_count > 0:
            avg = state.cost.total_cost_usd / state.cost.turn_count
            lines.append(f"  Avg cost/turn: ${avg:.4f}")
        return CommandResult(output="\n".join(lines))


class StatsCommand(Command):
    @property
    def name(self) -> str: return "stats"
    @property
    def description(self) -> str: return "Show session statistics"

    async def execute(self, args: str, state: Any) -> CommandResult:
        lines = [
            "📊 Session Stats:",
            f"  Session ID: {state.conversation_id}",
            f"  Model: {state.model}",
            f"  Messages: {len(state.messages)}",
            f"  Working dir: {state.cwd}",
            f"  Permission mode: {state.permission_mode}",
            f"  Cost: {state.cost.format_cost()}",
            f"  Tokens: {state.cost.format_tokens()}",
        ]
        return CommandResult(output="\n".join(lines))


def get_commands() -> list[Command]:
    return [CostCommand(), UsageCommand(), StatsCommand()]
