"""
Background task manager — run tasks asynchronously with tracking.

Provides:
  - Named async tasks with status tracking
  - Output buffering (ring buffer)
  - Task lifecycle: start → running → done/failed/cancelled
  - Integration with hooks for lifecycle events
"""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Coroutine

logger = logging.getLogger(__name__)


class TaskStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class BackgroundTask:
    """A tracked background task."""
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    name: str = ""
    status: TaskStatus = TaskStatus.PENDING
    created_at: float = field(default_factory=time.time)
    started_at: float | None = None
    finished_at: float | None = None
    output_buffer: list[str] = field(default_factory=list)
    max_output_lines: int = 500
    result: Any = None
    error: str | None = None
    _task: asyncio.Task | None = field(default=None, repr=False)

    @property
    def elapsed(self) -> float:
        if self.started_at is None:
            return 0.0
        end = self.finished_at or time.time()
        return end - self.started_at

    @property
    def output(self) -> str:
        return "\n".join(self.output_buffer)

    def append_output(self, text: str) -> None:
        """Append text to the output buffer (ring buffer)."""
        lines = text.split("\n")
        self.output_buffer.extend(lines)
        if len(self.output_buffer) > self.max_output_lines:
            excess = len(self.output_buffer) - self.max_output_lines
            self.output_buffer = self.output_buffer[excess:]


class TaskManager:
    """Manages background tasks."""

    def __init__(self) -> None:
        self._tasks: dict[str, BackgroundTask] = {}

    def start(
        self,
        coro: Coroutine,
        name: str = "",
        on_output: Callable[[str], None] | None = None,
    ) -> BackgroundTask:
        """Start a new background task."""
        bt = BackgroundTask(name=name or f"task_{len(self._tasks)}")
        self._tasks[bt.id] = bt

        async def _wrapper():
            bt.status = TaskStatus.RUNNING
            bt.started_at = time.time()
            try:
                result = await coro
                bt.result = result
                bt.status = TaskStatus.DONE
                if isinstance(result, str):
                    bt.append_output(result)
            except asyncio.CancelledError:
                bt.status = TaskStatus.CANCELLED
            except Exception as e:
                bt.error = str(e)
                bt.status = TaskStatus.FAILED
                logger.warning("Background task %s failed: %s", bt.name, e)
            finally:
                bt.finished_at = time.time()

        bt._task = asyncio.create_task(_wrapper())
        return bt

    def start_shell(self, command: str, cwd: str = "", name: str = "") -> BackgroundTask:
        """Start a shell command as a background task."""
        async def _run_shell():
            proc = await asyncio.create_subprocess_shell(
                command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
                cwd=cwd or None,
            )
            output_lines = []
            while True:
                line = await proc.stdout.readline()
                if not line:
                    break
                text = line.decode("utf-8", errors="replace").rstrip()
                output_lines.append(text)
                bt = self._tasks.get(task_id)
                if bt:
                    bt.append_output(text)

            await proc.wait()
            return "\n".join(output_lines)

        bt = BackgroundTask(name=name or command[:40])
        task_id = bt.id
        self._tasks[bt.id] = bt

        async def _wrapper():
            bt.status = TaskStatus.RUNNING
            bt.started_at = time.time()
            try:
                result = await _run_shell()
                bt.result = result
                bt.status = TaskStatus.DONE
            except asyncio.CancelledError:
                bt.status = TaskStatus.CANCELLED
            except Exception as e:
                bt.error = str(e)
                bt.status = TaskStatus.FAILED
            finally:
                bt.finished_at = time.time()

        bt._task = asyncio.create_task(_wrapper())
        return bt

    def cancel(self, task_id: str) -> bool:
        """Cancel a running task."""
        bt = self._tasks.get(task_id)
        if bt and bt._task and not bt._task.done():
            bt._task.cancel()
            return True
        return False

    async def wait(self, task_id: str, timeout: float | None = None) -> BackgroundTask | None:
        """Wait for a task to complete."""
        bt = self._tasks.get(task_id)
        if bt and bt._task:
            try:
                await asyncio.wait_for(bt._task, timeout=timeout)
            except asyncio.TimeoutError:
                pass
            except asyncio.CancelledError:
                pass
        return bt

    def get(self, task_id: str) -> BackgroundTask | None:
        return self._tasks.get(task_id)

    def get_all(self) -> list[BackgroundTask]:
        return list(self._tasks.values())

    def get_running(self) -> list[BackgroundTask]:
        return [t for t in self._tasks.values() if t.status == TaskStatus.RUNNING]

    def get_completed(self) -> list[BackgroundTask]:
        return [
            t for t in self._tasks.values()
            if t.status in (TaskStatus.DONE, TaskStatus.FAILED, TaskStatus.CANCELLED)
        ]

    def cleanup(self, max_age_seconds: float = 3600) -> int:
        """Remove old completed tasks."""
        now = time.time()
        to_remove = []
        for tid, bt in self._tasks.items():
            if bt.finished_at and (now - bt.finished_at) > max_age_seconds:
                to_remove.append(tid)
        for tid in to_remove:
            del self._tasks[tid]
        return len(to_remove)

    def format_status(self) -> str:
        """Format all tasks for display."""
        tasks = self.get_all()
        if not tasks:
            return "No background tasks."

        lines = [f"Background tasks ({len(tasks)}):\n"]
        for bt in tasks:
            icon = {"pending": "⏳", "running": "🔄", "done": "✅",
                    "failed": "❌", "cancelled": "⛔"}.get(bt.status.value, "?")
            lines.append(f"  {icon} [{bt.id}] {bt.name} — {bt.status.value} ({bt.elapsed:.1f}s)")
            if bt.error:
                lines.append(f"    Error: {bt.error}")
        return "\n".join(lines)


# Global singleton
_task_manager: TaskManager | None = None


def get_task_manager() -> TaskManager:
    global _task_manager
    if _task_manager is None:
        _task_manager = TaskManager()
    return _task_manager
