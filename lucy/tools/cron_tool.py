"""
Cron tool — schedule, list, and delete recurring tasks.

Mirrors OpenCode's CronCreateTool, CronDeleteTool, CronListTool.
"""

from __future__ import annotations

import json
import os
import time
import uuid
from dataclasses import dataclass, field
from typing import Any

from lucy.core.tool import Tool, ToolContext, ToolResult


@dataclass
class CronJob:
    id: str
    schedule: str  # cron-like: "*/5 * * * *" or simple: "every 5m", "every 1h"
    command: str
    name: str = ""
    enabled: bool = True
    created_at: float = field(default_factory=time.time)
    last_run: float | None = None
    run_count: int = 0


class _CronManager:
    def __init__(self):
        self._jobs: dict[str, CronJob] = {}
        self._storage_path: str | None = None

    def set_storage(self, path: str):
        self._storage_path = path
        self._load()

    def _load(self):
        if self._storage_path and os.path.exists(self._storage_path):
            try:
                with open(self._storage_path) as f:
                    data = json.load(f)
                for item in data.get("jobs", []):
                    job = CronJob(**item)
                    self._jobs[job.id] = job
            except Exception:
                pass

    def _save(self):
        if self._storage_path:
            os.makedirs(os.path.dirname(self._storage_path), exist_ok=True)
            with open(self._storage_path, "w") as f:
                json.dump({
                    "jobs": [
                        {
                            "id": j.id, "schedule": j.schedule, "command": j.command,
                            "name": j.name, "enabled": j.enabled,
                            "created_at": j.created_at, "last_run": j.last_run,
                            "run_count": j.run_count,
                        }
                        for j in self._jobs.values()
                    ]
                }, f, indent=2)

    def create(self, schedule: str, command: str, name: str = "") -> CronJob:
        job = CronJob(
            id=uuid.uuid4().hex[:8],
            schedule=schedule,
            command=command,
            name=name or command[:40],
        )
        self._jobs[job.id] = job
        self._save()
        return job

    def delete(self, job_id: str) -> bool:
        if job_id in self._jobs:
            del self._jobs[job_id]
            self._save()
            return True
        return False

    def list_all(self) -> list[CronJob]:
        return sorted(self._jobs.values(), key=lambda j: j.created_at, reverse=True)

    def get(self, job_id: str) -> CronJob | None:
        return self._jobs.get(job_id)


_cron_mgr = _CronManager()


def get_cron_manager() -> _CronManager:
    return _cron_mgr


class CronCreateTool(Tool):
    @property
    def name(self) -> str:
        return "CronCreate"

    @property
    def description(self) -> str:
        return "Schedule a recurring task"

    @property
    def input_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "schedule": {
                    "type": "string",
                    "description": "Schedule: cron format ('*/5 * * * *') or simple ('every 5m', 'every 1h')",
                },
                "command": {"type": "string", "description": "Shell command to run"},
                "name": {"type": "string", "description": "Job name"},
            },
            "required": ["schedule", "command"],
        }

    def get_prompt(self) -> str:
        return (
            "Schedule a recurring task. Use cron format ('*/5 * * * *') or "
            "simple format ('every 5m', 'every 1h', 'every 30s')."
        )

    async def call(self, tool_input: dict[str, Any], context: ToolContext) -> ToolResult:
        schedule = tool_input.get("schedule", "")
        command = tool_input.get("command", "")
        name = tool_input.get("name", "")

        if not schedule or not command:
            return ToolResult(error="schedule and command are required")

        from lucy.core.config import get_config
        storage = os.path.join(str(get_config().config_dir), "cron_jobs.json")
        _cron_mgr.set_storage(storage)

        job = _cron_mgr.create(schedule, command, name)
        return ToolResult(
            data=f"Created cron job:\n  ID: {job.id}\n  Name: {job.name}\n"
                 f"  Schedule: {job.schedule}\n  Command: {job.command}"
        )


class CronDeleteTool(Tool):
    @property
    def name(self) -> str:
        return "CronDelete"

    @property
    def description(self) -> str:
        return "Delete a scheduled task"

    @property
    def input_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "job_id": {"type": "string", "description": "Job ID to delete"},
            },
            "required": ["job_id"],
        }

    def get_prompt(self) -> str:
        return "Delete a scheduled cron job by its ID."

    async def call(self, tool_input: dict[str, Any], context: ToolContext) -> ToolResult:
        job_id = tool_input.get("job_id", "")
        if _cron_mgr.delete(job_id):
            return ToolResult(data=f"Deleted cron job: {job_id}")
        return ToolResult(error=f"Job not found: {job_id}")


class CronListTool(Tool):
    @property
    def name(self) -> str:
        return "CronList"

    @property
    def description(self) -> str:
        return "List all scheduled tasks"

    @property
    def input_schema(self) -> dict[str, Any]:
        return {"type": "object", "properties": {}}

    def get_prompt(self) -> str:
        return "List all scheduled cron jobs."

    def is_read_only(self, tool_input: dict[str, Any]) -> bool:
        return True

    async def call(self, tool_input: dict[str, Any], context: ToolContext) -> ToolResult:
        from lucy.core.config import get_config
        storage = os.path.join(str(get_config().config_dir), "cron_jobs.json")
        _cron_mgr.set_storage(storage)

        jobs = _cron_mgr.list_all()
        if not jobs:
            return ToolResult(data="No cron jobs scheduled.")

        lines = [f"Cron jobs ({len(jobs)}):\n"]
        for j in jobs:
            status = "✓" if j.enabled else "✗"
            last = time.strftime("%H:%M:%S", time.localtime(j.last_run)) if j.last_run else "never"
            lines.append(f"  {status} [{j.id}] {j.name}")
            lines.append(f"    Schedule: {j.schedule} | Last run: {last} | Runs: {j.run_count}")
        return ToolResult(data="\n".join(lines))
