"""
Task management tools — create, get, list, stop, update, output.

Mirrors OpenCode's TaskCreateTool, TaskGetTool, TaskListTool, TaskStopTool,
TaskUpdateTool, TaskOutputTool.
"""

from __future__ import annotations

import asyncio
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Coroutine

from lucy.core.tool import Tool, ToolContext, ToolResult


# ---------------------------------------------------------------------------
# Task infrastructure
# ---------------------------------------------------------------------------

class TaskStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class TaskRecord:
    id: str
    name: str
    description: str = ""
    status: TaskStatus = TaskStatus.PENDING
    output: str = ""
    error: str | None = None
    created_at: float = field(default_factory=time.time)
    started_at: float | None = None
    completed_at: float | None = None
    progress: float = 0.0  # 0.0 - 1.0
    _task: asyncio.Task | None = field(default=None, repr=False)


class _TaskManager:
    """Global task manager singleton."""

    def __init__(self):
        self._tasks: dict[str, TaskRecord] = {}

    def create(self, name: str, description: str = "") -> TaskRecord:
        task_id = uuid.uuid4().hex[:12]
        record = TaskRecord(id=task_id, name=name, description=description)
        self._tasks[task_id] = record
        return record

    def get(self, task_id: str) -> TaskRecord | None:
        return self._tasks.get(task_id)

    def list_all(self, status: TaskStatus | None = None) -> list[TaskRecord]:
        tasks = list(self._tasks.values())
        if status:
            tasks = [t for t in tasks if t.status == status]
        return sorted(tasks, key=lambda t: t.created_at, reverse=True)

    def cancel(self, task_id: str) -> bool:
        record = self._tasks.get(task_id)
        if not record:
            return False
        if record.status in (TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED):
            return False
        record.status = TaskStatus.CANCELLED
        record.completed_at = time.time()
        if record._task and not record._task.done():
            record._task.cancel()
        return True

    def update(self, task_id: str, status: TaskStatus | None = None,
               output: str | None = None, progress: float | None = None) -> bool:
        record = self._tasks.get(task_id)
        if not record:
            return False
        if status:
            record.status = status
        if output is not None:
            record.output = output
        if progress is not None:
            record.progress = progress
        if status in (TaskStatus.COMPLETED, TaskStatus.FAILED):
            record.completed_at = time.time()
        return True

    def format_status(self) -> str:
        tasks = self.list_all()
        if not tasks:
            return "No tasks."
        lines = [f"Tasks ({len(tasks)}):\n"]
        for t in tasks:
            icon = {"pending": "⬜", "running": "🔄", "completed": "✅",
                    "failed": "❌", "cancelled": "⏹️"}.get(t.status.value, "?")
            elapsed = ""
            if t.started_at:
                e = (t.completed_at or time.time()) - t.started_at
                elapsed = f" ({e:.1f}s)"
            prog = f" {t.progress*100:.0f}%" if t.status == TaskStatus.RUNNING else ""
            lines.append(f"  {icon} [{t.id}] {t.name}{prog}{elapsed}")
            if t.error:
                lines.append(f"    Error: {t.error}")
        return "\n".join(lines)


_manager = _TaskManager()


def get_task_manager() -> _TaskManager:
    return _manager


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------

class TaskCreateTool(Tool):
    @property
    def name(self) -> str:
        return "TaskCreate"

    @property
    def description(self) -> str:
        return "Create a new background task"

    @property
    def input_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Task name"},
                "description": {"type": "string", "description": "Task description"},
                "command": {"type": "string", "description": "Shell command to run as the task"},
            },
            "required": ["name"],
        }

    def get_prompt(self) -> str:
        return (
            "Create a background task. If a command is provided, it runs as a subprocess. "
            "Use TaskGet to check status and TaskOutput to see results."
        )

    async def call(self, tool_input: dict[str, Any], context: ToolContext) -> ToolResult:
        import subprocess as sp

        name = tool_input.get("name", "Unnamed Task")
        desc = tool_input.get("description", "")
        command = tool_input.get("command", "")

        record = _manager.create(name, desc)

        if command:
            record.status = TaskStatus.RUNNING
            record.started_at = time.time()

            async def _run():
                try:
                    proc = await asyncio.create_subprocess_shell(
                        command, stdout=asyncio.subprocess.PIPE,
                        stderr=asyncio.subprocess.PIPE, cwd=context.cwd,
                    )
                    stdout, stderr = await proc.communicate()
                    record.output = (stdout.decode(errors="replace") +
                                     ("\nSTDERR:\n" + stderr.decode(errors="replace") if stderr else ""))
                    record.status = TaskStatus.COMPLETED if proc.returncode == 0 else TaskStatus.FAILED
                    if proc.returncode != 0:
                        record.error = f"Exit code: {proc.returncode}"
                except Exception as e:
                    record.status = TaskStatus.FAILED
                    record.error = str(e)
                finally:
                    record.completed_at = time.time()

            record._task = asyncio.create_task(_run())

        return ToolResult(data=f"Created task [{record.id}]: {name}")


class TaskGetTool(Tool):
    @property
    def name(self) -> str:
        return "TaskGet"

    @property
    def description(self) -> str:
        return "Get the status of a task"

    @property
    def input_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "task_id": {"type": "string", "description": "Task ID"},
            },
            "required": ["task_id"],
        }

    def get_prompt(self) -> str:
        return "Get the current status of a background task by its ID."

    def is_read_only(self, tool_input: dict[str, Any]) -> bool:
        return True

    async def call(self, tool_input: dict[str, Any], context: ToolContext) -> ToolResult:
        task_id = tool_input.get("task_id", "")
        record = _manager.get(task_id)
        if not record:
            return ToolResult(error=f"Task not found: {task_id}")

        lines = [
            f"Task: {record.name}",
            f"ID: {record.id}",
            f"Status: {record.status.value}",
            f"Progress: {record.progress*100:.0f}%",
        ]
        if record.description:
            lines.append(f"Description: {record.description}")
        if record.error:
            lines.append(f"Error: {record.error}")
        if record.started_at:
            elapsed = (record.completed_at or time.time()) - record.started_at
            lines.append(f"Elapsed: {elapsed:.1f}s")

        return ToolResult(data="\n".join(lines))


class TaskListTool(Tool):
    @property
    def name(self) -> str:
        return "TaskList"

    @property
    def description(self) -> str:
        return "List all tasks"

    @property
    def input_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "status": {
                    "type": "string",
                    "enum": ["pending", "running", "completed", "failed", "cancelled"],
                    "description": "Filter by status",
                },
            },
        }

    def get_prompt(self) -> str:
        return "List all background tasks, optionally filtered by status."

    def is_read_only(self, tool_input: dict[str, Any]) -> bool:
        return True

    async def call(self, tool_input: dict[str, Any], context: ToolContext) -> ToolResult:
        status_str = tool_input.get("status")
        status = TaskStatus(status_str) if status_str else None
        return ToolResult(data=_manager.format_status())


class TaskStopTool(Tool):
    @property
    def name(self) -> str:
        return "TaskStop"

    @property
    def description(self) -> str:
        return "Stop/cancel a running task"

    @property
    def input_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "task_id": {"type": "string", "description": "Task ID to stop"},
            },
            "required": ["task_id"],
        }

    def get_prompt(self) -> str:
        return "Stop a running background task by its ID."

    async def call(self, tool_input: dict[str, Any], context: ToolContext) -> ToolResult:
        task_id = tool_input.get("task_id", "")
        if _manager.cancel(task_id):
            return ToolResult(data=f"Task {task_id} cancelled.")
        return ToolResult(error=f"Cannot cancel task: {task_id}")


class TaskUpdateTool(Tool):
    @property
    def name(self) -> str:
        return "TaskUpdate"

    @property
    def description(self) -> str:
        return "Update a task's status or progress"

    @property
    def input_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "task_id": {"type": "string", "description": "Task ID"},
                "status": {"type": "string", "enum": ["pending", "running", "completed", "failed"]},
                "output": {"type": "string", "description": "Task output text"},
                "progress": {"type": "number", "description": "Progress 0.0-1.0"},
            },
            "required": ["task_id"],
        }

    def get_prompt(self) -> str:
        return "Update a task's status, output, or progress."

    async def call(self, tool_input: dict[str, Any], context: ToolContext) -> ToolResult:
        task_id = tool_input.get("task_id", "")
        status = TaskStatus(tool_input["status"]) if "status" in tool_input else None
        output = tool_input.get("output")
        progress = tool_input.get("progress")

        if _manager.update(task_id, status=status, output=output, progress=progress):
            return ToolResult(data=f"Task {task_id} updated.")
        return ToolResult(error=f"Task not found: {task_id}")


class TaskOutputTool(Tool):
    @property
    def name(self) -> str:
        return "TaskOutput"

    @property
    def description(self) -> str:
        return "Get the output of a completed task"

    @property
    def input_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "task_id": {"type": "string", "description": "Task ID"},
            },
            "required": ["task_id"],
        }

    def get_prompt(self) -> str:
        return "Get the output produced by a task."

    def is_read_only(self, tool_input: dict[str, Any]) -> bool:
        return True

    async def call(self, tool_input: dict[str, Any], context: ToolContext) -> ToolResult:
        task_id = tool_input.get("task_id", "")
        record = _manager.get(task_id)
        if not record:
            return ToolResult(error=f"Task not found: {task_id}")

        if not record.output:
            return ToolResult(data=f"Task [{task_id}] has no output yet. Status: {record.status.value}")

        return ToolResult(data=record.output)
