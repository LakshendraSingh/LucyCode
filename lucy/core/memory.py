"""
Advanced memory system — persistent cross-session knowledge.

Three memory types:
  - Episodic: Past session summaries and key events
  - Semantic: Code snippets and concepts with embeddings
  - Procedural: Tool usage patterns and user preferences

Storage: SQLite with FTS5 full-text search.
"""

from __future__ import annotations

import json
import logging
import sqlite3
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

MEMORY_DB = Path.home() / ".lucy" / "memory.db"


# ---------------------------------------------------------------------------
# Memory record types
# ---------------------------------------------------------------------------

@dataclass
class EpisodicMemory:
    """A memory of a past session or conversation."""
    id: int = 0
    session_id: str = ""
    timestamp: float = field(default_factory=time.time)
    summary: str = ""
    key_decisions: str = ""
    files_modified: str = ""  # JSON list
    tools_used: str = ""      # JSON list
    model: str = ""
    cost: float = 0.0
    relevance_score: float = 0.0


@dataclass
class SemanticMemory:
    """A stored code concept or snippet."""
    id: int = 0
    content: str = ""
    source_file: str = ""
    language: str = ""
    category: str = ""  # "function", "class", "pattern", "concept", "error"
    tags: str = ""      # JSON list
    created_at: float = field(default_factory=time.time)
    access_count: int = 0
    relevance_score: float = 0.0


@dataclass
class ProceduralMemory:
    """A remembered tool usage pattern or preference."""
    id: int = 0
    pattern_type: str = ""  # "tool_usage", "preference", "workflow", "correction"
    tool_name: str = ""
    trigger: str = ""       # What triggers this pattern
    action: str = ""        # What to do
    frequency: int = 1
    last_used: float = field(default_factory=time.time)
    success_rate: float = 1.0


# ---------------------------------------------------------------------------
# Memory Store
# ---------------------------------------------------------------------------

class MemoryStore:
    """SQLite-backed persistent memory with FTS5 search."""

    def __init__(self, db_path: Path | None = None):
        self.db_path = db_path or MEMORY_DB
        self._conn: sqlite3.Connection | None = None

    def initialize(self) -> None:
        """Create tables and indexes."""
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self.db_path))
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")

        self._conn.executescript("""
            CREATE TABLE IF NOT EXISTS episodic (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL,
                timestamp REAL NOT NULL,
                summary TEXT NOT NULL,
                key_decisions TEXT DEFAULT '',
                files_modified TEXT DEFAULT '[]',
                tools_used TEXT DEFAULT '[]',
                model TEXT DEFAULT '',
                cost REAL DEFAULT 0.0
            );

            CREATE TABLE IF NOT EXISTS semantic (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                content TEXT NOT NULL,
                source_file TEXT DEFAULT '',
                language TEXT DEFAULT '',
                category TEXT DEFAULT '',
                tags TEXT DEFAULT '[]',
                created_at REAL NOT NULL,
                access_count INTEGER DEFAULT 0
            );

            CREATE TABLE IF NOT EXISTS procedural (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                pattern_type TEXT NOT NULL,
                tool_name TEXT DEFAULT '',
                trigger TEXT NOT NULL,
                action TEXT NOT NULL,
                frequency INTEGER DEFAULT 1,
                last_used REAL NOT NULL,
                success_rate REAL DEFAULT 1.0
            );

            CREATE VIRTUAL TABLE IF NOT EXISTS episodic_fts USING fts5(
                summary, key_decisions, content='episodic', content_rowid='id'
            );

            CREATE VIRTUAL TABLE IF NOT EXISTS semantic_fts USING fts5(
                content, tags, content='semantic', content_rowid='id'
            );

            CREATE VIRTUAL TABLE IF NOT EXISTS procedural_fts USING fts5(
                trigger, action, content='procedural', content_rowid='id'
            );
        """)
        self._conn.commit()

    def close(self) -> None:
        if self._conn:
            self._conn.close()
            self._conn = None

    # --- Episodic ---

    def add_episodic(self, mem: EpisodicMemory) -> int:
        self._ensure_conn()
        cur = self._conn.execute(
            "INSERT INTO episodic (session_id, timestamp, summary, key_decisions, "
            "files_modified, tools_used, model, cost) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (mem.session_id, mem.timestamp, mem.summary, mem.key_decisions,
             mem.files_modified, mem.tools_used, mem.model, mem.cost),
        )
        row_id = cur.lastrowid
        # Update FTS
        self._conn.execute(
            "INSERT INTO episodic_fts(rowid, summary, key_decisions) VALUES (?, ?, ?)",
            (row_id, mem.summary, mem.key_decisions),
        )
        self._conn.commit()
        return row_id

    def search_episodic(self, query: str, limit: int = 10) -> list[EpisodicMemory]:
        self._ensure_conn()
        rows = self._conn.execute(
            "SELECT e.*, rank FROM episodic e "
            "JOIN episodic_fts ON e.id = episodic_fts.rowid "
            "WHERE episodic_fts MATCH ? ORDER BY rank LIMIT ?",
            (query, limit),
        ).fetchall()
        return [self._row_to_episodic(r) for r in rows]

    def get_recent_episodic(self, limit: int = 10) -> list[EpisodicMemory]:
        self._ensure_conn()
        rows = self._conn.execute(
            "SELECT * FROM episodic ORDER BY timestamp DESC LIMIT ?", (limit,)
        ).fetchall()
        return [self._row_to_episodic(r) for r in rows]

    # --- Semantic ---

    def add_semantic(self, mem: SemanticMemory) -> int:
        self._ensure_conn()
        cur = self._conn.execute(
            "INSERT INTO semantic (content, source_file, language, category, "
            "tags, created_at, access_count) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (mem.content, mem.source_file, mem.language, mem.category,
             mem.tags, mem.created_at, mem.access_count),
        )
        row_id = cur.lastrowid
        self._conn.execute(
            "INSERT INTO semantic_fts(rowid, content, tags) VALUES (?, ?, ?)",
            (row_id, mem.content, mem.tags),
        )
        self._conn.commit()
        return row_id

    def search_semantic(self, query: str, limit: int = 10) -> list[SemanticMemory]:
        self._ensure_conn()
        rows = self._conn.execute(
            "SELECT s.*, rank FROM semantic s "
            "JOIN semantic_fts ON s.id = semantic_fts.rowid "
            "WHERE semantic_fts MATCH ? ORDER BY rank LIMIT ?",
            (query, limit),
        ).fetchall()
        results = [self._row_to_semantic(r) for r in rows]
        # Bump access count
        for r in results:
            self._conn.execute(
                "UPDATE semantic SET access_count = access_count + 1 WHERE id = ?", (r.id,)
            )
        self._conn.commit()
        return results

    # --- Procedural ---

    def add_procedural(self, mem: ProceduralMemory) -> int:
        self._ensure_conn()
        cur = self._conn.execute(
            "INSERT INTO procedural (pattern_type, tool_name, trigger, action, "
            "frequency, last_used, success_rate) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (mem.pattern_type, mem.tool_name, mem.trigger, mem.action,
             mem.frequency, mem.last_used, mem.success_rate),
        )
        row_id = cur.lastrowid
        self._conn.execute(
            "INSERT INTO procedural_fts(rowid, trigger, action) VALUES (?, ?, ?)",
            (row_id, mem.trigger, mem.action),
        )
        self._conn.commit()
        return row_id

    def search_procedural(self, query: str, limit: int = 10) -> list[ProceduralMemory]:
        self._ensure_conn()
        rows = self._conn.execute(
            "SELECT p.*, rank FROM procedural p "
            "JOIN procedural_fts ON p.id = procedural_fts.rowid "
            "WHERE procedural_fts MATCH ? ORDER BY rank LIMIT ?",
            (query, limit),
        ).fetchall()
        return [self._row_to_procedural(r) for r in rows]

    def get_tool_patterns(self, tool_name: str) -> list[ProceduralMemory]:
        self._ensure_conn()
        rows = self._conn.execute(
            "SELECT * FROM procedural WHERE tool_name = ? ORDER BY frequency DESC",
            (tool_name,),
        ).fetchall()
        return [self._row_to_procedural(r) for r in rows]

    def record_tool_use(self, tool_name: str, input_desc: str, success: bool) -> None:
        """Record a tool usage for pattern learning."""
        patterns = self.get_tool_patterns(tool_name)
        for p in patterns:
            if input_desc in p.trigger:
                self._conn.execute(
                    "UPDATE procedural SET frequency = frequency + 1, "
                    "last_used = ?, success_rate = (success_rate * frequency + ?) / (frequency + 1) "
                    "WHERE id = ?",
                    (time.time(), 1.0 if success else 0.0, p.id),
                )
                self._conn.commit()
                return

        # New pattern
        self.add_procedural(ProceduralMemory(
            pattern_type="tool_usage",
            tool_name=tool_name,
            trigger=input_desc,
            action=f"Use {tool_name}",
            success_rate=1.0 if success else 0.0,
        ))

    # --- Memory retrieval for context building ---

    def retrieve_relevant(self, query: str, max_tokens: int = 2000) -> str:
        """Retrieve relevant memories for injection into system prompt."""
        parts = []
        total_chars = 0
        char_limit = max_tokens * 4  # rough token→char conversion

        # Episodic memories
        episodes = self.search_episodic(query, limit=3)
        if episodes:
            parts.append("## Relevant Past Sessions")
            for ep in episodes:
                text = f"- [{ep.session_id[:8]}] {ep.summary[:200]}"
                if total_chars + len(text) > char_limit:
                    break
                parts.append(text)
                total_chars += len(text)

        # Semantic memories
        concepts = self.search_semantic(query, limit=5)
        if concepts:
            parts.append("\n## Related Knowledge")
            for c in concepts:
                text = f"- [{c.category}] {c.content[:150]}"
                if total_chars + len(text) > char_limit:
                    break
                parts.append(text)
                total_chars += len(text)

        # Procedural memories
        procs = self.search_procedural(query, limit=3)
        if procs:
            parts.append("\n## Known Patterns")
            for p in procs:
                text = f"- {p.trigger[:100]} → {p.action[:100]}"
                if total_chars + len(text) > char_limit:
                    break
                parts.append(text)
                total_chars += len(text)

        return "\n".join(parts)

    # --- Stats ---

    def get_stats(self) -> dict[str, int]:
        self._ensure_conn()
        return {
            "episodic": self._conn.execute("SELECT COUNT(*) FROM episodic").fetchone()[0],
            "semantic": self._conn.execute("SELECT COUNT(*) FROM semantic").fetchone()[0],
            "procedural": self._conn.execute("SELECT COUNT(*) FROM procedural").fetchone()[0],
        }

    # --- Helpers ---

    def _ensure_conn(self) -> None:
        if self._conn is None:
            self.initialize()

    def _row_to_episodic(self, row) -> EpisodicMemory:
        return EpisodicMemory(
            id=row["id"], session_id=row["session_id"],
            timestamp=row["timestamp"], summary=row["summary"],
            key_decisions=row["key_decisions"],
            files_modified=row["files_modified"],
            tools_used=row["tools_used"],
            model=row["model"], cost=row["cost"],
        )

    def _row_to_semantic(self, row) -> SemanticMemory:
        return SemanticMemory(
            id=row["id"], content=row["content"],
            source_file=row["source_file"], language=row["language"],
            category=row["category"], tags=row["tags"],
            created_at=row["created_at"], access_count=row["access_count"],
        )

    def _row_to_procedural(self, row) -> ProceduralMemory:
        return ProceduralMemory(
            id=row["id"], pattern_type=row["pattern_type"],
            tool_name=row["tool_name"], trigger=row["trigger"],
            action=row["action"], frequency=row["frequency"],
            last_used=row["last_used"], success_rate=row["success_rate"],
        )


# Global singleton
_memory_store: MemoryStore | None = None


def get_memory_store() -> MemoryStore:
    global _memory_store
    if _memory_store is None:
        _memory_store = MemoryStore()
        _memory_store.initialize()
    return _memory_store
