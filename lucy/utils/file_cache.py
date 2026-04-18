"""
File cache — content caching and invalidation.
"""

from __future__ import annotations

import hashlib
import os
import time
from typing import Any


class FileCache:
    """Cache file contents with mtime-based invalidation."""

    def __init__(self, max_entries: int = 1000, max_size_bytes: int = 50_000_000):
        self._cache: dict[str, dict[str, Any]] = {}
        self._max_entries = max_entries
        self._max_size = max_size_bytes
        self._total_size = 0

    def get(self, path: str) -> str | None:
        """Get cached file content, or None if stale/missing."""
        entry = self._cache.get(path)
        if entry is None:
            return None

        try:
            stat = os.stat(path)
            if stat.st_mtime_ns != entry["mtime_ns"]:
                del self._cache[path]
                self._total_size -= len(entry["content"])
                return None
        except OSError:
            del self._cache[path]
            self._total_size -= len(entry["content"])
            return None

        entry["last_access"] = time.time()
        return entry["content"]

    def put(self, path: str, content: str) -> None:
        """Cache file content."""
        try:
            stat = os.stat(path)
        except OSError:
            return

        content_size = len(content)
        if content_size > self._max_size // 10:
            return  # Single file too large

        # Evict if needed
        while (self._total_size + content_size > self._max_size or
               len(self._cache) >= self._max_entries):
            self._evict_oldest()
            if not self._cache:
                break

        old = self._cache.get(path)
        if old:
            self._total_size -= len(old["content"])

        self._cache[path] = {
            "content": content,
            "mtime_ns": stat.st_mtime_ns,
            "size": stat.st_size,
            "last_access": time.time(),
            "checksum": hashlib.md5(content.encode()).hexdigest(),
        }
        self._total_size += content_size

    def invalidate(self, path: str) -> None:
        """Invalidate a cached entry."""
        entry = self._cache.pop(path, None)
        if entry:
            self._total_size -= len(entry["content"])

    def invalidate_dir(self, dir_path: str) -> int:
        """Invalidate all entries under a directory."""
        to_remove = [p for p in self._cache if p.startswith(dir_path)]
        for p in to_remove:
            self.invalidate(p)
        return len(to_remove)

    def clear(self) -> None:
        self._cache.clear()
        self._total_size = 0

    def stats(self) -> dict[str, Any]:
        return {
            "entries": len(self._cache),
            "total_size_bytes": self._total_size,
            "max_entries": self._max_entries,
            "max_size_bytes": self._max_size,
        }

    def _evict_oldest(self) -> None:
        if not self._cache:
            return
        oldest = min(self._cache.items(), key=lambda x: x[1]["last_access"])
        self._total_size -= len(oldest[1]["content"])
        del self._cache[oldest[0]]


_cache = FileCache()


def get_file_cache() -> FileCache:
    return _cache
