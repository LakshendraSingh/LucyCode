"""
Task commands — /tasks.
"""

from __future__ import annotations

from typing import Any

from lucy.core.commands import Command, CommandResult


class TasksCommand(Command):
    @property
    def name(self) -> str: return "tasks"
    @property
    def aliases(self) -> list[str]: return ["task"]
    @property
    def description(self) -> str: return "Manage background tasks"
    @property
    def usage(self) -> str: return "/tasks [list|get|stop] [id]"

    async def execute(self, args: str, state: Any) -> CommandResult:
        from lucy.tools.task_tools import get_task_manager
        mgr = get_task_manager()

        parts = args.strip().split(None, 1)
        action = parts[0] if parts else "list"
        target = parts[1].strip() if len(parts) > 1 else ""

        if action == "list":
            return CommandResult(output=mgr.format_status())

        if action == "get":
            if not target:
                return CommandResult(error="Usage: /tasks get <id>")
            record = mgr.get(target)
            if not record:
                return CommandResult(error=f"Task not found: {target}")
            import time
            elapsed = ""
            if record.started_at:
                e = (record.completed_at or time.time()) - record.started_at
                elapsed = f"\nElapsed: {e:.1f}s"
            output = (f"Task: {record.name}\nID: {record.id}\n"
                      f"Status: {record.status.value}\n"
                      f"Progress: {record.progress*100:.0f}%{elapsed}")
            if record.output:
                output += f"\nOutput:\n{record.output[:500]}"
            return CommandResult(output=output)

        if action == "stop":
            if not target:
                return CommandResult(error="Usage: /tasks stop <id>")
            if mgr.cancel(target):
                return CommandResult(output=f"Cancelled task: {target}")
            return CommandResult(error=f"Cannot cancel: {target}")

        return CommandResult(error=f"Unknown action: {action}")


def get_commands() -> list[Command]:
    return [TasksCommand()]
