"""
KAIROS — Knowledge-Aware Intelligent Recurring Operations System.

A background daemon that:
  - Watches filesystem for changes
  - Maintains a persistent knowledge graph
  - Runs scheduled tasks (cron-like)
  - Auto-indexes project files
  - Provides IPC via Unix socket
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

logger = logging.getLogger(__name__)

KAIROS_DIR = Path.home() / ".lucy" / "kairos"
KAIROS_SOCKET = KAIROS_DIR / "kairos.sock"
INDEX_FILE = KAIROS_DIR / "index.json"


# ---------------------------------------------------------------------------
# File index
# ---------------------------------------------------------------------------

@dataclass
class FileRecord:
    """Tracked file metadata."""
    path: str
    hash: str = ""
    size: int = 0
    modified_at: float = 0.0
    indexed_at: float = 0.0
    language: str = ""
    line_count: int = 0
    symbols: list[str] = field(default_factory=list)
    summary: str = ""


class FileIndex:
    """Persistent file index for the project."""

    def __init__(self):
        self._records: dict[str, FileRecord] = {}
        self._dirty = False

    def update(self, path: str) -> FileRecord | None:
        """Update index for a file."""
        try:
            stat = os.stat(path)
        except OSError:
            self._records.pop(path, None)
            return None

        # Check if changed
        existing = self._records.get(path)
        if existing and existing.modified_at >= stat.st_mtime:
            return existing

        # Read and hash
        try:
            with open(path, "rb") as f:
                content = f.read(1024 * 1024)  # 1MB limit
            file_hash = hashlib.md5(content).hexdigest()
        except (OSError, PermissionError):
            return None

        # Detect language
        ext = Path(path).suffix.lower()
        lang_map = {
            ".py": "python", ".js": "javascript", ".ts": "typescript",
            ".go": "go", ".rs": "rust", ".c": "c", ".cpp": "cpp",
            ".java": "java", ".rb": "ruby", ".sh": "bash",
            ".md": "markdown", ".json": "json", ".yaml": "yaml",
            ".html": "html", ".css": "css", ".sql": "sql",
        }
        language = lang_map.get(ext, "")

        # Count lines
        try:
            line_count = content.count(b"\n") + 1
        except Exception:
            line_count = 0

        # Extract symbols (basic: function/class names for Python)
        symbols = []
        if language == "python":
            for line in content.decode("utf-8", errors="ignore").split("\n"):
                stripped = line.strip()
                if stripped.startswith("def ") or stripped.startswith("class "):
                    name = stripped.split("(")[0].split(":")[0]
                    name = name.replace("def ", "").replace("class ", "").strip()
                    if name:
                        symbols.append(name)

        record = FileRecord(
            path=path,
            hash=file_hash,
            size=stat.st_size,
            modified_at=stat.st_mtime,
            indexed_at=time.time(),
            language=language,
            line_count=line_count,
            symbols=symbols[:100],
        )
        self._records[path] = record
        self._dirty = True
        return record

    def remove(self, path: str) -> None:
        if path in self._records:
            del self._records[path]
            self._dirty = True

    def search(self, query: str) -> list[FileRecord]:
        """Search index by filename or symbol."""
        q = query.lower()
        results = []
        for r in self._records.values():
            if q in r.path.lower():
                results.append(r)
            elif any(q in s.lower() for s in r.symbols):
                results.append(r)
        return results[:50]

    def get_stats(self) -> dict[str, Any]:
        by_lang: dict[str, int] = {}
        total_lines = 0
        for r in self._records.values():
            lang = r.language or "other"
            by_lang[lang] = by_lang.get(lang, 0) + 1
            total_lines += r.line_count
        return {
            "total_files": len(self._records),
            "total_lines": total_lines,
            "by_language": by_lang,
        }

    def save(self, path: Path | None = None) -> None:
        path = path or INDEX_FILE
        path.parent.mkdir(parents=True, exist_ok=True)
        data = {k: {
            "path": r.path, "hash": r.hash, "size": r.size,
            "modified_at": r.modified_at, "indexed_at": r.indexed_at,
            "language": r.language, "line_count": r.line_count,
            "symbols": r.symbols,
        } for k, r in self._records.items()}
        with open(path, "w") as f:
            json.dump(data, f, indent=2)
        self._dirty = False

    def load(self, path: Path | None = None) -> None:
        path = path or INDEX_FILE
        if not path.exists():
            return
        try:
            with open(path) as f:
                data = json.load(f)
            for k, v in data.items():
                self._records[k] = FileRecord(**v)
        except Exception as e:
            logger.warning("Failed to load index: %s", e)


# ---------------------------------------------------------------------------
# Scheduled tasks
# ---------------------------------------------------------------------------

@dataclass
class ScheduledTask:
    """A recurring task."""
    name: str
    callback: Callable[[], Any]
    interval_seconds: float
    last_run: float = 0.0
    enabled: bool = True


# ---------------------------------------------------------------------------
# File watcher
# ---------------------------------------------------------------------------

class FileWatcher:
    """Watch directories for file changes."""

    def __init__(self, root: str, ignore_patterns: list[str] | None = None):
        self.root = root
        self.ignore_patterns = ignore_patterns or [
            ".git", "__pycache__", "node_modules", ".venv",
            "venv", ".tox", "dist", "build", ".mypy_cache",
        ]
        self._callbacks: list[Callable[[str, str], None]] = []

    def on_change(self, callback: Callable[[str, str], None]) -> None:
        """Register a callback for file changes. callback(path, event_type)."""
        self._callbacks.append(callback)

    def _should_ignore(self, path: str) -> bool:
        parts = Path(path).parts
        return any(p in self.ignore_patterns for p in parts)

    async def poll_once(self, index: FileIndex) -> int:
        """Scan for changes and update the index. Returns count of changes."""
        changes = 0
        seen = set()

        for dirpath, dirnames, filenames in os.walk(self.root):
            # Filter ignored directories
            dirnames[:] = [
                d for d in dirnames
                if d not in self.ignore_patterns and not d.startswith(".")
            ]

            for fname in filenames:
                if fname.startswith("."):
                    continue
                full_path = os.path.join(dirpath, fname)
                if self._should_ignore(full_path):
                    continue
                seen.add(full_path)
                record = index.update(full_path)
                if record and record.indexed_at == record.modified_at:
                    changes += 1
                    for cb in self._callbacks:
                        try:
                            cb(full_path, "modified")
                        except Exception:
                            pass

        # Detect deletions
        for path in list(index._records.keys()):
            if path not in seen:
                index.remove(path)
                changes += 1
                for cb in self._callbacks:
                    try:
                        cb(path, "deleted")
                    except Exception:
                        pass

        return changes


# ---------------------------------------------------------------------------
# KAIROS Daemon
# ---------------------------------------------------------------------------

class KairosDaemon:
    """The KAIROS background daemon."""

    def __init__(self, project_root: str):
        self.project_root = project_root
        self.index = FileIndex()
        self.watcher = FileWatcher(project_root)
        self._scheduled: list[ScheduledTask] = []
        self._running = False
        self._poll_interval = 5.0  # seconds

    def add_scheduled_task(
        self, name: str, callback: Callable, interval: float
    ) -> None:
        self._scheduled.append(ScheduledTask(
            name=name, callback=callback, interval_seconds=interval,
        ))

    async def start(self) -> None:
        """Start the KAIROS daemon."""
        KAIROS_DIR.mkdir(parents=True, exist_ok=True)
        self.index.load()
        self._running = True

        logger.info("KAIROS daemon started for %s", self.project_root)

        # Initial full scan
        changes = await self.watcher.poll_once(self.index)
        self.index.save()
        logger.info("Initial scan: %d files indexed", len(self.index._records))

        # Main loop
        while self._running:
            await asyncio.sleep(self._poll_interval)

            # Poll for changes
            changes = await self.watcher.poll_once(self.index)
            if changes:
                self.index.save()

            # Run scheduled tasks
            now = time.time()
            for task in self._scheduled:
                if task.enabled and (now - task.last_run) >= task.interval_seconds:
                    try:
                        result = task.callback()
                        if asyncio.iscoroutine(result):
                            await result
                        task.last_run = now
                    except Exception as e:
                        logger.warning("Scheduled task %s failed: %s", task.name, e)

    def stop(self) -> None:
        self._running = False
        self.index.save()

    def get_status(self) -> dict[str, Any]:
        stats = self.index.get_stats()
        return {
            "running": self._running,
            "project": self.project_root,
            "files_indexed": stats["total_files"],
            "total_lines": stats["total_lines"],
            "languages": stats["by_language"],
            "scheduled_tasks": len(self._scheduled),
        }
