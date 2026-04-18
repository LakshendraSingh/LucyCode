"""
Cron service — background cron-like task scheduling.
"""

from __future__ import annotations

import asyncio
import logging
import re
import subprocess
import time
from typing import Any

logger = logging.getLogger(__name__)


class CronService:
    """Background scheduler for recurring tasks."""

    def __init__(self):
        self._running = False
        self._task: asyncio.Task | None = None

    async def start(self, cwd: str) -> None:
        """Start the cron service."""
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._loop(cwd))
        logger.info("Cron service started")

    async def stop(self) -> None:
        """Stop the cron service."""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("Cron service stopped")

    async def _loop(self, cwd: str) -> None:
        """Main cron loop — check and run jobs."""
        from lucy.tools.cron_tool import get_cron_manager

        while self._running:
            mgr = get_cron_manager()
            now = time.time()

            for job in mgr.list_all():
                if not job.enabled:
                    continue

                # Parse schedule and check if due
                interval = _parse_schedule(job.schedule)
                if interval <= 0:
                    continue

                last = job.last_run or job.created_at
                if now - last >= interval:
                    # Run the job
                    logger.info("Running cron job: %s (%s)", job.name, job.id)
                    try:
                        result = subprocess.run(
                            job.command, shell=True, capture_output=True,
                            text=True, timeout=300, cwd=cwd,
                        )
                        job.last_run = time.time()
                        job.run_count += 1
                        if result.returncode != 0:
                            logger.warning("Cron job %s failed: %s", job.id, result.stderr[:200])
                    except Exception as e:
                        logger.error("Cron job %s error: %s", job.id, e)
                        job.last_run = time.time()

            await asyncio.sleep(10)  # Check every 10 seconds


def _parse_schedule(schedule: str) -> float:
    """Parse a schedule string to interval in seconds."""
    schedule = schedule.strip().lower()

    # Simple format: "every Ns", "every Nm", "every Nh"
    m = re.match(r"every\s+(\d+)\s*([smhd])", schedule)
    if m:
        value = int(m.group(1))
        unit = m.group(2)
        multipliers = {"s": 1, "m": 60, "h": 3600, "d": 86400}
        return value * multipliers.get(unit, 60)

    # Cron format: basic support for */N
    parts = schedule.split()
    if len(parts) == 5:
        # */N in minutes field
        if parts[0].startswith("*/"):
            try:
                return int(parts[0][2:]) * 60
            except ValueError:
                pass

    return 0


_service: CronService | None = None


def get_cron_service() -> CronService:
    global _service
    if _service is None:
        _service = CronService()
    return _service
