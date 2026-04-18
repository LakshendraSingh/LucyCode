"""
Process management utilities.
"""

from __future__ import annotations

import asyncio
import os
import signal
import sys
from typing import Any


class ProcessManager:
    """Manage child processes and cleanup."""

    def __init__(self):
        self._processes: list[asyncio.subprocess.Process] = []
        self._cleanup_callbacks: list[Any] = []

    def register(self, process: asyncio.subprocess.Process) -> None:
        self._processes.append(process)

    def add_cleanup(self, callback: Any) -> None:
        self._cleanup_callbacks.append(callback)

    async def cleanup_all(self) -> None:
        """Kill all managed processes."""
        for proc in self._processes:
            try:
                if proc.returncode is None:
                    proc.terminate()
                    try:
                        await asyncio.wait_for(proc.wait(), timeout=5)
                    except asyncio.TimeoutError:
                        proc.kill()
            except ProcessLookupError:
                pass

        for callback in self._cleanup_callbacks:
            try:
                if asyncio.iscoroutinefunction(callback):
                    await callback()
                else:
                    callback()
            except Exception:
                pass

        self._processes.clear()
        self._cleanup_callbacks.clear()


_manager = ProcessManager()


def get_process_manager() -> ProcessManager:
    return _manager


def setup_signal_handlers(cleanup_func: Any = None) -> None:
    """Set up graceful signal handlers."""
    def handler(sig, frame):
        if cleanup_func:
            cleanup_func()
        sys.exit(128 + sig)

    signal.signal(signal.SIGINT, handler)
    signal.signal(signal.SIGTERM, handler)
    if hasattr(signal, "SIGPIPE"):
        signal.signal(signal.SIGPIPE, signal.SIG_DFL)
