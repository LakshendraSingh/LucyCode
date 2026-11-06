"""
Learning engine — improves over time by learning from corrections.

When the user corrects Lucy or provides feedback, the learning engine:
1. Extracts the correction pattern
2. Stores it as a procedural memory in SQLite
3. Injects relevant corrections into future prompts
"""

from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
import re
import sqlite3
import time
from typing import Any

logger = logging.getLogger(__name__)

DEFAULT_LEARNING_DB = Path.home() / ".lucycode" / "learning.db"


@dataclass
class Correction:
    """A learned correction."""
    id: str
    trigger: str          # What pattern triggered the mistake
    original_response: str  # What Lucy said/did wrong
    correction: str       # What the user said to correct
    learned_rule: str     # The extracted rule
    context: str          # File type, project, etc.
    confidence: float = 1.0
    times_applied: int = 0
    created_at: float = field(default_factory=time.time)


class LearningEngine:
    """Learns from user corrections to improve over time."""

    # Regex patterns indicating user is correcting the assistant
    CORRECTION_PATTERNS = [
        re.compile(r"^(?:no|nope|not quite|that's wrong|that is wrong|incorrect|stop doing)\b", re.IGNORECASE),
        re.compile(r"\b(?:don't|do not|never|shouldn't)\s+(?:use|do|create|modify|run|call)\b", re.IGNORECASE),
        re.compile(r"\b(?:i meant|i asked for|i said|instead of|rather than|actually,?\s+use)\b", re.IGNORECASE),
        re.compile(r"\b(?:use\s+[\w\.\-]+(?:\s+[\w\.\-]+)*\s+instead)\b", re.IGNORECASE),
        re.compile(r"\b(?:you forgot to|you should have|you made a mistake)\b", re.IGNORECASE),
        re.compile(r"\b(?:wrong file|wrong syntax|wrong function|wrong approach|broken)\b", re.IGNORECASE),
        re.compile(r"\balways\s+(?:use|include|follow|write)\b", re.IGNORECASE),
    ]

    def __init__(self, db_path: Path | None = None) -> None:
        self._db_path = db_path or DEFAULT_LEARNING_DB
        self._corrections: list[Correction] = []
        self._conn: sqlite3.Connection | None = None
        self._init_db()
        self.load()

    def _init_db(self) -> None:
        """Initialize the SQLite database schema."""
        try:
            self._db_path.parent.mkdir(parents=True, exist_ok=True)
            self._conn = sqlite3.connect(str(self._db_path), check_same_thread=False)
            self._conn.row_factory = sqlite3.Row
            self._conn.execute("PRAGMA journal_mode=WAL")

            self._conn.executescript("""
                CREATE TABLE IF NOT EXISTS corrections (
                    id TEXT PRIMARY KEY,
                    trigger TEXT NOT NULL,
                    original_response TEXT DEFAULT '',
                    correction TEXT NOT NULL,
                    learned_rule TEXT NOT NULL,
                    context TEXT DEFAULT '',
                    confidence REAL DEFAULT 1.0,
                    times_applied INTEGER DEFAULT 0,
                    created_at REAL NOT NULL
                );

                CREATE VIRTUAL TABLE IF NOT EXISTS corrections_fts USING fts5(
                    trigger, learned_rule, context, content='corrections', content_rowid='rowid'
                );
            """)
            self._conn.commit()
        except Exception as e:
            logger.debug("Failed to initialize learning database at %s: %s (falling back to memory)", self._db_path, e)
            try:
                self._conn = sqlite3.connect(":memory:", check_same_thread=False)
                self._conn.row_factory = sqlite3.Row
                self._conn.executescript("""
                    CREATE TABLE IF NOT EXISTS corrections (
                        id TEXT PRIMARY KEY,
                        trigger TEXT NOT NULL,
                        original_response TEXT DEFAULT '',
                        correction TEXT NOT NULL,
                        learned_rule TEXT NOT NULL,
                        context TEXT DEFAULT '',
                        confidence REAL DEFAULT 1.0,
                        times_applied INTEGER DEFAULT 0,
                        created_at REAL NOT NULL
                    );
                """)
                self._conn.commit()
            except Exception:
                self._conn = None

    def detect_correction(self, user_message: str, previous_assistant: str) -> bool:
        """Detect if the user is correcting the previous response."""
        if not user_message or not previous_assistant:
            return False

        user_clean = user_message.strip()
        # Very short prompts like "ok", "thanks" are not corrections
        if len(user_clean) < 3:
            return False

        for pattern in self.CORRECTION_PATTERNS:
            if pattern.search(user_clean):
                return True

        return False

    def extract_rule(self, user_message: str, previous_assistant: str, context: str) -> Correction:
        """Extract a reusable rule from the correction."""
        user_clean = user_message.strip()
        trigger = ""
        learned_rule = ""

        # Pattern 1: "Use X instead of Y" or "Instead of Y, use X"
        m1 = re.search(r"use\s+([^,]+?)\s+instead of\s+([^,\.\n]+)", user_clean, re.IGNORECASE)
        if m1:
            better, worse = m1.group(1).strip(), m1.group(2).strip()
            trigger = worse
            learned_rule = f"Use {better} instead of {worse}."

        m2 = re.search(r"instead of\s+([^,]+?)[,\s]+(?:use|do)\s+([^,\.\n]+)", user_clean, re.IGNORECASE)
        if not learned_rule and m2:
            worse, better = m2.group(1).strip(), m2.group(2).strip()
            trigger = worse
            learned_rule = f"Use {better} instead of {worse}."

        # Pattern 2: "Don't do X, do Y" or "Don't use X"
        m3 = re.search(r"(?:don't|do not|never)\s+([^,\.;]+)(?:[,\s]+(?:do|use|prefer)\s+([^,\.\n]+))?", user_clean, re.IGNORECASE)
        if not learned_rule and m3:
            prohibited = m3.group(1).strip()
            alternative = m3.group(2).strip() if m3.group(2) else ""
            trigger = prohibited
            if alternative:
                learned_rule = f"Do not {prohibited}; use {alternative} instead."
            else:
                learned_rule = f"Never {prohibited}."

        # Pattern 3: "No, I meant X" / "Actually, X"
        m4 = re.search(r"(?:no,?\s+i meant|i asked for|actually,?\s+)\s*([^,\.\n]+)", user_clean, re.IGNORECASE)
        if not learned_rule and m4:
            wanted = m4.group(1).strip()
            trigger = wanted
            learned_rule = f"Always ensure: {wanted}."

        # Pattern 4: "Always X"
        m5 = re.search(r"always\s+([^,\.\n]+)", user_clean, re.IGNORECASE)
        if not learned_rule and m5:
            rule_text = m5.group(1).strip()
            trigger = rule_text
            learned_rule = f"Always {rule_text}."

        # Fallback extraction: Clean up message directly
        if not learned_rule:
            first_sentence = user_clean.split("\n")[0].split(".")[0]
            # Strip initial negative tokens
            clean = re.sub(r"^(?:no|nope|not quite|that's wrong|incorrect)[,\s]*", "", first_sentence, flags=re.IGNORECASE).strip()
            learned_rule = f"Follow user preference: {clean}."
            trigger = clean[:50]

        # Context summary
        ctx_summary = context
        if ctx_summary and len(ctx_summary) > 100:
            ctx_summary = Path(ctx_summary).name

        # Create unique ID based on hash of rule and trigger
        cid = "corr_" + hashlib.sha256(f"{trigger}:{learned_rule}".encode("utf-8")).hexdigest()[:12]

        correction = Correction(
            id=cid,
            trigger=trigger,
            original_response=previous_assistant[:300],
            correction=user_clean[:300],
            learned_rule=learned_rule,
            context=ctx_summary,
            confidence=1.0,
            times_applied=0,
            created_at=time.time(),
        )
        return correction

    def record_correction(self, correction: Correction) -> None:
        """Record and persist a correction."""
        # Check if already present; update if so
        for existing in self._corrections:
            if existing.id == correction.id or existing.learned_rule.lower() == correction.learned_rule.lower():
                existing.confidence = min(2.0, existing.confidence + 0.2)
                existing.times_applied += 1
                self.save()
                return

        self._corrections.append(correction)
        self.save()

        # Also mirror to procedural memory store if available
        try:
            from lucy.core.memory import ProceduralMemory, get_memory_store
            store = get_memory_store()
            store.add_procedural(ProceduralMemory(
                pattern_type="correction",
                tool_name="UserFeedback",
                trigger=correction.trigger,
                action=correction.learned_rule,
                frequency=1,
                success_rate=1.0,
            ))
        except Exception:
            pass

    def get_relevant_corrections(self, context: str, user_prompt: str, limit: int = 5) -> list[Correction]:
        """Get corrections relevant to the current user prompt and context."""
        if not self._corrections:
            return []

        search_text = f"{context} {user_prompt}".lower()
        scored: list[tuple[float, Correction]] = []

        for c in self._corrections:
            score = 0.0
            # Keyword match against trigger
            trig_words = set(re.findall(r"\w{3,}", c.trigger.lower()))
            for word in trig_words:
                if word in search_text:
                    score += 2.0

            # Match against rule words
            rule_words = set(re.findall(r"\w{4,}", c.learned_rule.lower()))
            for word in rule_words:
                if word in search_text:
                    score += 1.0

            # Context match (e.g., project name, file extension)
            if c.context and c.context.lower() in search_text:
                score += 1.5

            if score > 0.0:
                final_score = score * c.confidence * (1.0 + c.times_applied * 0.1)
                scored.append((final_score, c))

        scored.sort(key=lambda x: x[0], reverse=True)
        return [c for _, c in scored[:limit]]

    def build_prompt_injection(self, context: str, user_prompt: str) -> str:
        """Build a prompt section with relevant learned corrections."""
        relevant = self.get_relevant_corrections(context, user_prompt)
        if not relevant:
            return ""

        lines = [
            "<learned_corrections>",
            "Follow these user-verified guidelines learned from past corrections:",
        ]
        for c in relevant:
            lines.append(f"- Rule: {c.learned_rule}")
            c.times_applied += 1

        lines.append("</learned_corrections>")
        return "\n".join(lines)

    def mark_applied(self, correction_id: str) -> None:
        """Increment application count for a correction."""
        for c in self._corrections:
            if c.id == correction_id:
                c.times_applied += 1
                break
        self.save()

    def save(self) -> None:
        """Persist corrections to SQLite."""
        if not self._conn:
            return

        try:
            for c in self._corrections:
                self._conn.execute(
                    """
                    INSERT OR REPLACE INTO corrections
                    (id, trigger, original_response, correction, learned_rule, context, confidence, times_applied, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        c.id, c.trigger, c.original_response, c.correction,
                        c.learned_rule, c.context, c.confidence, c.times_applied, c.created_at,
                    ),
                )
            self._conn.commit()
        except Exception as e:
            logger.warning("Failed to save corrections to %s: %s", self._db_path, e)

    def load(self) -> None:
        """Load corrections from SQLite."""
        if not self._conn:
            return

        try:
            cursor = self._conn.execute("SELECT * FROM corrections ORDER BY created_at DESC")
            rows = cursor.fetchall()
            self._corrections = [
                Correction(
                    id=r["id"],
                    trigger=r["trigger"],
                    original_response=r["original_response"],
                    correction=r["correction"],
                    learned_rule=r["learned_rule"],
                    context=r["context"],
                    confidence=float(r["confidence"]),
                    times_applied=int(r["times_applied"]),
                    created_at=float(r["created_at"]),
                )
                for r in rows
            ]
        except Exception as e:
            logger.warning("Failed to load corrections from %s: %s", self._db_path, e)


# Global singleton
_learning_engine: LearningEngine | None = None


def get_learning_engine() -> LearningEngine:
    global _learning_engine
    if _learning_engine is None:
        _learning_engine = LearningEngine()
    return _learning_engine
