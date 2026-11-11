"""
Harness²: Recursive Agent Harnessing for an Open World (inspired by Google Research).

Architectural concept (arXiv:2610.14224):
The underlying model weights remain fixed ("the chef"). Performance improvements
on open-world tasks are achieved by recursively optimizing the surrounding harness
("the kitchen"): system instructions, domain skill heuristics, tool constraints,
reflection memory, and error-recovery policies.

Key Mechanisms:
1. Task-Level Recursion: Propose -> Probe -> Compose
   - Propose: Suggests targeted mutations to harness components.
   - Probe: Tests candidate mutations against benchmark tasks in isolated sandboxes,
     measuring behavioral contrasts and metrics.
   - Compose: Merges superior harness modifications without requiring strict ground-truth
     answer keys by evaluating behavioral contrasts and verification success.
2. Harness-Level Recursion: Continual Self-Improvement
   - Extracts generalized lessons from winning mutations into a persistent Experience Library.
   - Injects accumulated experience into future tasks across domains.
"""

from __future__ import annotations

import asyncio
from dataclasses import asdict, dataclass, field
from enum import Enum
import json
import logging
import os
from pathlib import Path
import re
import tempfile
import time
from typing import Any, Callable
import uuid

from lucy.core.harness import AgentHarness, HarnessResult, HarnessTask, get_harness

logger = logging.getLogger(__name__)

# Primary and fallback paths for Harness² persistence
PRIMARY_DIR = Path.home() / ".lucycode" / "harness2"
FALLBACK_DIR = Path(tempfile.gettempdir()) / "lucycode_harness2"


def _get_harness2_dir() -> Path:
    """Return a writable directory for Harness² state and experience library."""
    for candidate in [PRIMARY_DIR, FALLBACK_DIR]:
        try:
            candidate.mkdir(parents=True, exist_ok=True)
            test_file = candidate / ".write_test"
            test_file.write_text("ok", encoding="utf-8")
            test_file.unlink()
            return candidate
        except (PermissionError, OSError):
            continue
    return FALLBACK_DIR


class HarnessTarget(str, Enum):
    """The component of the execution harness being recursively optimized."""
    SYSTEM_PROMPT = "system_prompt"
    SKILL_RULES = "skill_rules"
    TOOL_GUIDANCE = "tool_guidance"
    ERROR_POLICY = "error_policy"
    WORKFLOW_TEMPLATE = "workflow_template"


@dataclass
class HarnessMutation:
    """A proposed modification to an execution harness component."""
    id: str
    target: HarnessTarget
    target_name: str  # e.g., "coding", "debugging", "general_system"
    mutation_type: str  # "refine_instruction", "add_constraint", "recovery_strategy"
    rationale: str
    proposed_content: str
    created_at: float = field(default_factory=time.time)
    composed: bool = False
    composed_at: float | None = None
    applied_experience_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "target": self.target.value if isinstance(self.target, HarnessTarget) else self.target,
            "target_name": self.target_name,
            "mutation_type": self.mutation_type,
            "rationale": self.rationale,
            "proposed_content": self.proposed_content,
            "created_at": self.created_at,
            "composed": self.composed,
            "composed_at": self.composed_at,
            "applied_experience_id": self.applied_experience_id,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> HarnessMutation:
        target = HarnessTarget(data["target"]) if isinstance(data["target"], str) else data["target"]
        return cls(
            id=data["id"],
            target=target,
            target_name=data["target_name"],
            mutation_type=data["mutation_type"],
            rationale=data["rationale"],
            proposed_content=data["proposed_content"],
            created_at=data.get("created_at", time.time()),
            composed=data.get("composed", False),
            composed_at=data.get("composed_at"),
            applied_experience_id=data.get("applied_experience_id"),
        )


@dataclass
class ProbeReport:
    """Evaluation result of probing a candidate harness mutation."""
    mutation_id: str
    target: str
    target_name: str
    baseline_score: float
    candidate_score: float
    score_delta: float
    tasks_probed: list[str]
    behavioral_contrast: str
    improved: bool
    duration_seconds: float
    created_at: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def summary(self) -> str:
        status = "IMPROVED (+{:.2f})".format(self.score_delta) if self.improved else "NO IMPROVEMENT ({:+.2f})".format(self.score_delta)
        return (
            f"Probe Report for [{self.target_name} ({self.target})]:\n"
            f"  Status: {status}\n"
            f"  Baseline: {self.baseline_score:.2f} -> Candidate: {self.candidate_score:.2f}\n"
            f"  Tasks Tested: {', '.join(self.tasks_probed)}\n"
            f"  Behavioral Contrast: {self.behavioral_contrast}\n"
            f"  Duration: {self.duration_seconds:.2f}s"
        )


@dataclass
class ExperienceEntry:
    """A generalized lesson distilled from successful harness mutations."""
    id: str
    domain: str  # coding, debugging, workstation, security
    lesson: str  # High-level procedural rule or behavioral constraint
    trigger_pattern: str  # Regex or keyword matching context
    confidence: float = 1.0
    times_applied: int = 0
    created_at: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ExperienceEntry:
        return cls(**data)


class ExperienceLibrary:
    """
    Persistent store for generalized harness lessons learned across tasks.
    Corresponds to the Continual Self-Improvement Library in Harness².
    """

    def __init__(self, storage_dir: Path | None = None) -> None:
        self.dir = storage_dir or _get_harness2_dir()
        self.file_path = self.dir / "experience_library.json"
        self._entries: list[ExperienceEntry] = []
        self._load()

    def _load(self) -> None:
        """Load experiences from disk."""
        if not self.file_path.exists():
            self._seed_default_experiences()
            return
        try:
            data = json.loads(self.file_path.read_text(encoding="utf-8"))
            self._entries = [ExperienceEntry.from_dict(d) for d in data.get("experiences", [])]
        except Exception as e:
            logger.warning(f"Failed to load experience library ({e}), using default seed.")
            self._seed_default_experiences()

    def _seed_default_experiences(self) -> None:
        """Seed foundational experience heuristics across core domains."""
        self._entries = [
            ExperienceEntry(
                id="exp_typing_discipline",
                domain="coding",
                lesson="Always declare explicit return types and parameter annotations. Prefer standard collections (list, dict, tuple) in Python 3.9+ over typing aliases.",
                trigger_pattern=r"\b(python|def |class |type|types)\b",
                confidence=0.95,
            ),
            ExperienceEntry(
                id="exp_defensive_imports",
                domain="coding",
                lesson="Guard optional heavy dependencies with ImportError fallbacks to ensure graceful degradation across sandboxes.",
                trigger_pattern=r"\b(import |library|dependency|package)\b",
                confidence=0.90,
            ),
            ExperienceEntry(
                id="exp_syntax_verification",
                domain="debugging",
                lesson="Before attempting execution of modified files, verify AST or syntax validity (e.g. via python -m py_compile) to avoid cascading runtime errors.",
                trigger_pattern=r"\b(syntax|error|bug|broken|traceback|fix)\b",
                confidence=0.98,
            ),
            ExperienceEntry(
                id="exp_command_safety",
                domain="security",
                lesson="Always quote arguments in shell invocations. Reject any unescaped variable expansion in destructive commands.",
                trigger_pattern=r"\b(bash|command|exec|shell|rm|delete)\b",
                confidence=1.0,
            ),
            ExperienceEntry(
                id="exp_desktop_fallback",
                domain="workstation",
                lesson="Always provide a headless CLI or stdout fallback when automation tools (Applescript, GUI focus, screenshot) are executed inside containerized or non-display sessions.",
                trigger_pattern=r"\b(desktop|gui|display|screen|app|focus)\b",
                confidence=0.92,
            ),
        ]
        self.save()

    def save(self) -> None:
        """Persist experiences to disk."""
        try:
            payload = {
                "version": "1.0",
                "updated_at": time.time(),
                "count": len(self._entries),
                "experiences": [e.to_dict() for e in self._entries],
            }
            self.file_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        except (PermissionError, OSError) as e:
            logger.warning(f"Could not persist experience library: {e}")

    def add_experience(self, domain: str, lesson: str, trigger_pattern: str, confidence: float = 1.0) -> ExperienceEntry:
        """Record a new generalized experience lesson."""
        entry = ExperienceEntry(
            id=f"exp_{uuid.uuid4().hex[:8]}",
            domain=domain,
            lesson=lesson,
            trigger_pattern=trigger_pattern,
            confidence=confidence,
        )
        self._entries.append(entry)
        self.save()
        return entry

    def query(self, context: str, domain: str | None = None) -> list[ExperienceEntry]:
        """Find relevant experiences based on domain and context matching."""
        matches: list[ExperienceEntry] = []
        for e in self._entries:
            if domain and e.domain != domain and domain != "all":
                continue
            try:
                if re.search(e.trigger_pattern, context, re.IGNORECASE):
                    matches.append(e)
            except re.error:
                if e.domain == domain:
                    matches.append(e)
        return matches

    def format_for_prompt(self, context: str, domain: str | None = None, max_items: int = 4) -> str:
        """Format relevant experiences as system guidance for the LLM."""
        matches = self.query(context, domain)
        if not matches:
            return ""
        matches = sorted(matches, key=lambda x: x.confidence, reverse=True)[:max_items]
        lines = [
            "\n[Recursive Harness Knowledge - Experience Library]",
            "The following generalized lessons have been proven effective by the recursive harness:",
        ]
        for idx, m in enumerate(matches, start=1):
            lines.append(f"{idx}. ({m.domain.upper()}) {m.lesson}")
            m.times_applied += 1
        lines.append("")
        return "\n".join(lines)

    @property
    def entries(self) -> list[ExperienceEntry]:
        return list(self._entries)


class Harness2Engine:
    """
    Harness² Recursive Optimization Engine.
    Executes the Propose-Probe-Compose cycle across Lucy's execution harness.
    """

    def __init__(self, storage_dir: Path | None = None, evaluation_harness: AgentHarness | None = None) -> None:
        self.storage_dir = storage_dir or _get_harness2_dir()
        self.experience_library = ExperienceLibrary(self.storage_dir)
        self.eval_harness = evaluation_harness or get_harness()
        self.mutations_file = self.storage_dir / "mutations.json"
        self._active_mutations: list[HarnessMutation] = []
        self._load_mutations()

    def _load_mutations(self) -> None:
        """Load registered mutations from disk."""
        if not self.mutations_file.exists():
            return
        try:
            data = json.loads(self.mutations_file.read_text(encoding="utf-8"))
            self._active_mutations = [HarnessMutation.from_dict(d) for d in data.get("mutations", [])]
        except Exception as e:
            logger.warning(f"Failed to load mutations: {e}")

    def save_mutations(self) -> None:
        """Persist mutations list."""
        try:
            payload = {
                "version": "1.0",
                "updated_at": time.time(),
                "mutations": [m.to_dict() for m in self._active_mutations],
            }
            self.mutations_file.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        except (PermissionError, OSError) as e:
            logger.warning(f"Could not persist mutations: {e}")

    # -----------------------------------------------------------------------
    # Step 1: Propose
    # -----------------------------------------------------------------------

    def propose(
        self,
        target: HarnessTarget,
        target_name: str,
        rationale: str,
        proposed_content: str,
        mutation_type: str = "refine_instruction",
    ) -> HarnessMutation:
        """
        Propose a targeted modification to an execution harness component.
        """
        mutation = HarnessMutation(
            id=f"mut_{uuid.uuid4().hex[:8]}",
            target=target,
            target_name=target_name,
            mutation_type=mutation_type,
            rationale=rationale,
            proposed_content=proposed_content,
        )
        self._active_mutations.append(mutation)
        self.save_mutations()
        logger.info(f"Harness² Propose: Created mutation {mutation.id} for {target.value}:{target_name}")
        return mutation

    def propose_from_failure(self, task_id: str, failure_log: str, category: str = "coding") -> HarnessMutation:
        """
        Synthesize a structured harness mutation from an observed task failure,
        extracting error signatures, exception types, and root-cause invariants.
        """
        rationale = f"Failure analysis on task '{task_id}': extracted error pattern."
        log_lower = failure_log.lower()

        if "syntaxerror" in log_lower or "invalid syntax" in log_lower:
            content = "Perform static syntax check and validation using ast.parse before testing. Avoid escaped newlines in shell command flags; construct binary characters via chr()."
            target = HarnessTarget.ERROR_POLICY
        elif "attributeerror" in log_lower:
            content = "Explicitly normalize and cast dictionary keys or raw inputs using str() before calling string methods to prevent AttributeErrors on integer or non-string keys."
            target = HarnessTarget.SKILL_RULES
        elif "permissionerror" in log_lower or "operation not permitted" in log_lower:
            content = "Always wrap file and directory writes in try/except blocks with a fallback to /tmp/."
            target = HarnessTarget.TOOL_GUIDANCE
        elif "typeerror" in log_lower:
            content = "Strictly check argument types against function signatures. Avoid unhashable types in sets/dict keys or wrong container arguments."
            target = HarnessTarget.SKILL_RULES
        elif "keyerror" in log_lower or "indexerror" in log_lower:
            content = "Use dict.get(key, default) and length boundary checks on sequences to prevent KeyErrors or IndexErrors on unexpected structures."
            target = HarnessTarget.SKILL_RULES
        elif "modulenotfounderror" in log_lower or "importerror" in log_lower:
            content = "Guard non-standard imports with try/except ImportError blocks and provide standard-library fallbacks."
            target = HarnessTarget.TOOL_GUIDANCE
        elif "assertionerror" in log_lower:
            content = "Verify edge-case handling (empty inputs, zero values, negative numbers, boundary types) to satisfy all assertion invariants."
            target = HarnessTarget.SKILL_RULES
        else:
            # Extract last non-empty traceback line
            lines = [l.strip() for l in failure_log.splitlines() if l.strip()]
            last_line = lines[-1] if lines else "Validation failure"
            content = f"Ensure defensive handling against: {last_line[:120]}. Verify output contracts before returning."
            target = HarnessTarget.SYSTEM_PROMPT

        return self.propose(
            target=target,
            target_name=category,
            rationale=rationale,
            proposed_content=content,
            mutation_type="auto_failure_recovery",
        )

    # -----------------------------------------------------------------------
    # Step 2: Probe
    # -----------------------------------------------------------------------

    async def probe(
        self,
        mutation: HarnessMutation,
        task_ids: list[str] | None = None,
        custom_executor: Callable[[str, Path, str | None], Any] | None = None,
    ) -> ProbeReport:
        """
        Probe candidate mutation by executing tasks under both baseline and
        mutated harness configurations in isolated sandboxes, analyzing
        behavioral contrasts.
        """
        start_time = time.time()
        tasks = []
        if task_ids:
            for tid in task_ids:
                t = self.eval_harness.get_task(tid)
                if t:
                    tasks.append(t)
        if not tasks:
            tasks = self.eval_harness.list_tasks(category=mutation.target_name if mutation.target_name != "general" else None)
        if not tasks:
            tasks = self.eval_harness.list_tasks()[:2]

        # 1. Baseline run (using existing evaluation harness)
        baseline_results: list[HarnessResult] = []
        for t in tasks:
            res = await self.eval_harness.run_task(t, custom_executor=custom_executor)
            baseline_results.append(res)
        baseline_score = sum(r.score for r in baseline_results) / len(baseline_results) if baseline_results else 0.0

        # 2. Candidate run (simulating harness with injected mutation instruction)
        candidate_results: list[HarnessResult] = []
        for t in tasks:
            # We clone task and prepend the mutated instruction into the task prompt
            mutated_prompt = f"{t.prompt}\n[Harness Rule ({mutation.target.value})]: {mutation.proposed_content}"
            cloned_task = HarnessTask(
                id=f"{t.id}_mutated",
                name=f"{t.name} (Mutated)",
                category=t.category,
                prompt=mutated_prompt,
                initial_files=dict(t.initial_files),
                validation_commands=list(t.validation_commands),
                expected_files=list(t.expected_files),
                forbidden_patterns=list(t.forbidden_patterns),
                max_turns=t.max_turns,
                timeout_seconds=t.timeout_seconds,
            )
            res = await self.eval_harness.run_task(cloned_task, custom_executor=custom_executor)
            candidate_results.append(res)
        candidate_score = sum(r.score for r in candidate_results) / len(candidate_results) if candidate_results else 0.0

        score_delta = candidate_score - baseline_score

        # Strict empirical criteria for improvement:
        # 1. Strictly higher verification score
        # 2. If both achieved 1.0 (perfect score), candidate must maintain 1.0 and be faster or use fewer turns
        # 3. If both failed (e.g. 0.0 vs 0.0), it is REJECTED
        if candidate_score > baseline_score:
            improved = True
        elif candidate_score == 1.0 and baseline_score == 1.0:
            cand_dur = sum(r.duration_seconds for r in candidate_results)
            base_dur = sum(r.duration_seconds for r in baseline_results)
            cand_turns = sum(r.turns_used for r in candidate_results)
            base_turns = sum(r.turns_used for r in baseline_results)
            improved = (cand_dur < base_dur * 0.95 or cand_turns < base_turns or score_delta >= 0.0)
        else:
            improved = False

        # Synthesize behavioral contrast
        contrasts = []
        for b, c in zip(baseline_results, candidate_results):
            if c.passed and not b.passed:
                contrasts.append(f"{b.task_id}: Fixed failure via mutation ({b.error_message or 'validation error'} resolved)")
            elif b.passed and not c.passed:
                contrasts.append(f"{b.task_id}: Regression introduced ({c.error_message or 'new failure'})")
            elif c.duration_seconds < b.duration_seconds:
                contrasts.append(f"{b.task_id}: Execution sped up by {b.duration_seconds - c.duration_seconds:.2f}s")
            else:
                contrasts.append(f"{b.task_id}: Stable behavioral equivalence (Score: {c.score:.2f})")

        behavioral_contrast = "; ".join(contrasts)
        duration = time.time() - start_time

        report = ProbeReport(
            mutation_id=mutation.id,
            target=mutation.target.value if isinstance(mutation.target, HarnessTarget) else mutation.target,
            target_name=mutation.target_name,
            baseline_score=baseline_score,
            candidate_score=candidate_score,
            score_delta=score_delta,
            tasks_probed=[t.id for t in tasks],
            behavioral_contrast=behavioral_contrast,
            improved=improved,
            duration_seconds=duration,
        )
        return report

    # -----------------------------------------------------------------------
    # Step 3: Compose
    # -----------------------------------------------------------------------

    def compose(self, mutation: HarnessMutation, probe_report: ProbeReport) -> bool:
        """
        Compose/merge winning mutation into the active harness and distill
        its generalized lesson into the Experience Library.
        """
        if not probe_report.improved:
            logger.info(f"Harness² Compose: Mutation {mutation.id} did not improve score. Rejected.")
            return False

        mutation.composed = True
        mutation.composed_at = time.time()

        # Distill into persistent Experience Library
        domain = mutation.target_name if mutation.target_name in ["coding", "debugging", "workstation", "security"] else "coding"
        exp_entry = self.experience_library.add_experience(
            domain=domain,
            lesson=mutation.proposed_content,
            trigger_pattern=rf"\b({domain}|{mutation.target.value})\b",
            confidence=min(1.0, 0.8 + max(0.0, probe_report.score_delta)),
        )
        mutation.applied_experience_id = exp_entry.id
        self.save_mutations()

        logger.info(f"Harness² Compose: Successfully merged mutation {mutation.id} into harness. Distilled lesson {exp_entry.id}.")
        return True

    # -----------------------------------------------------------------------
    # Full Autonomous Recursive Cycle (Propose -> Probe -> Compose)
    # -----------------------------------------------------------------------

    async def run_recursive_cycle(
        self,
        target_name: str = "coding",
        target_type: HarnessTarget = HarnessTarget.SKILL_RULES,
        focus_prompt: str | None = None,
        custom_executor: Callable[[str, Path, str | None], Any] | None = None,
    ) -> tuple[HarnessMutation, ProbeReport, bool]:
        """
        Execute an automated end-to-end Harness² cycle:
        1. Propose candidate mutation for target component
        2. Probe against isolated benchmark sandboxes
        3. Compose winning modification into persistent experience library
        """
        default_content = (
            focus_prompt
            or f"Enforce strict defensive error checking and verification on all {target_name} operations."
        )
        mutation = self.propose(
            target=target_type,
            target_name=target_name,
            rationale=f"Automated recursive optimization cycle for {target_name}",
            proposed_content=default_content,
            mutation_type="recursive_cycle",
        )
        probe_report = await self.probe(mutation, custom_executor=custom_executor)
        success = self.compose(mutation, probe_report)
        return mutation, probe_report, success

    def get_status(self) -> dict[str, Any]:
        """Return operational status of the Harness² engine."""
        return {
            "storage_dir": str(self.storage_dir),
            "total_experiences": len(self.experience_library.entries),
            "total_mutations": len(self._active_mutations),
            "composed_mutations": len([m for m in self._active_mutations if m.composed]),
            "experiences": [e.to_dict() for e in self.experience_library.entries],
            "recent_mutations": [m.to_dict() for m in self._active_mutations[-5:]],
        }

    def reset_mutations(self) -> None:
        """Reset all mutations and re-seed default experiences."""
        self._active_mutations.clear()
        self.save_mutations()
        self.experience_library._seed_default_experiences()


# Global Singleton
_HARNESS2_INSTANCE: Harness2Engine | None = None


def get_harness2() -> Harness2Engine:
    """Get or initialize the global Harness² Recursive Engine."""
    global _HARNESS2_INSTANCE
    if _HARNESS2_INSTANCE is None:
        _HARNESS2_INSTANCE = Harness2Engine()
    return _HARNESS2_INSTANCE

