"""
Goal event definitions for autonomous goal execution progress reporting.

Events emitted by GoalEngine during the execution lifecycle:
- planning: Goal decomposition and plan creation
- step_start: Beginning execution of a plan step
- step_complete: Successful step completion
- step_failed: Step execution failure
- verifying: Running verification checks
- verification_result: Outcome of verification checks
- replanning: Dynamic replanning due to failure or changed context
- correcting: Self-correction attempt after failure
- progress: Step progress, ETA, and token budget updates
- completed: Goal execution successfully finished
- failed: Goal execution ended in failure
- paused: Goal execution paused and checkpointed
- checkpoint: State saved to disk
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from typing import Any

from lucy.core.verification import VerificationResult


@dataclass
class GoalEvent:
    """Event emitted during goal execution for progress reporting."""
    type: str  # planning | step_start | step_complete | step_failed | verifying | verification_result | replanning | correcting | progress | completed | failed | paused | checkpoint
    data: dict[str, Any]
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        """Convert event to dictionary."""
        return {
            "type": self.type,
            "data": self.data,
            "timestamp": self.timestamp,
        }

    def to_ndjson(self) -> str:
        """Convert event to NDJSON line."""
        return json.dumps(self.to_dict())

    def format_summary(self) -> str:
        """User-friendly one-line summary for logging and TUI."""
        t = self.type
        d = self.data
        if t == "planning":
            est = d.get("estimated_steps", 0)
            return f"📋 Planning goal: '{d.get('goal', '')}' ({est} steps planned)"
        if t == "step_start":
            sid = d.get("step_id", 0)
            desc = d.get("description", "")
            done = d.get("steps_done", 0)
            total = d.get("steps_total", 0)
            return f"🚀 [Step {sid} ({done}/{total})]: {desc}"
        if t == "step_complete":
            sid = d.get("step_id", 0)
            return f"✅ Step {sid} completed"
        if t == "step_failed":
            sid = d.get("step_id", 0)
            err = d.get("error", "")
            return f"❌ Step {sid} failed: {err}"
        if t == "verifying":
            strat = d.get("strategy", "all")
            return f"🔍 Running self-verification ({strat})..."
        if t == "verification_result":
            passed = d.get("passed", False)
            status = "PASSED" if passed else "FAILED"
            return f"🧪 Verification checks {status}"
        if t == "replanning":
            reason = d.get("reason", "")
            orig = d.get("original_steps", 0)
            new_s = d.get("new_steps", 0)
            return f"🔄 Replanning ({reason}): {orig} -> {new_s} steps"
        if t == "correcting":
            sid = d.get("step_id", 0)
            att = d.get("attempt", 1)
            max_att = d.get("max_attempts", 3)
            return f"🛠️ Self-correcting step {sid} (attempt {att}/{max_att})"
        if t == "progress":
            done = d.get("steps_done", 0)
            total = d.get("steps_total", 0)
            pct = d.get("percent", 0.0)
            eta = d.get("eta_seconds", 0.0)
            return f"⏳ Progress: {done}/{total} steps ({pct:.1f}%) | ETA: {int(eta)}s"
        if t == "completed":
            files = d.get("files_modified", [])
            return f"🎉 Goal completed! ({len(files)} files modified)"
        if t == "failed":
            return f"💥 Goal failed: {d.get('error', '')}"
        if t == "paused":
            gid = d.get("goal_id", "")
            return f"⏸️ Goal {gid} paused. Checkpoint saved."
        if t == "checkpoint":
            gid = d.get("goal_id", "")
            sid = d.get("step_id", 0)
            return f"💾 Checkpoint saved for goal {gid} (step {sid})"
        return f"[{t}] {d}"


# ---------------------------------------------------------------------------
# Specific Event Constructors
# ---------------------------------------------------------------------------

def goal_planning_event(goal: str, estimated_steps: int = 0) -> GoalEvent:
    """Create a planning event."""
    return GoalEvent(
        type="planning",
        data={"goal": goal, "estimated_steps": estimated_steps},
    )


def goal_step_start_event(step_id: int, description: str, progress: tuple[int, int]) -> GoalEvent:
    """Create a step_start event."""
    return GoalEvent(
        type="step_start",
        data={
            "step_id": step_id,
            "description": description,
            "steps_done": progress[0],
            "steps_total": progress[1],
        },
    )


def goal_step_complete_event(step_id: int, output: str) -> GoalEvent:
    """Create a step_complete event."""
    return GoalEvent(
        type="step_complete",
        data={"step_id": step_id, "output": output},
    )


def goal_step_failed_event(step_id: int, error: str, retry_count: int = 0) -> GoalEvent:
    """Create a step_failed event."""
    return GoalEvent(
        type="step_failed",
        data={"step_id": step_id, "error": error, "retry_count": retry_count},
    )


def goal_verifying_event(strategy: str = "all") -> GoalEvent:
    """Create a verifying event."""
    return GoalEvent(
        type="verifying",
        data={"strategy": strategy},
    )


def goal_verification_event(results: list[VerificationResult]) -> GoalEvent:
    """Create a verification_result event."""
    all_passed = all(r.passed for r in results) if results else True
    return GoalEvent(
        type="verification_result",
        data={
            "passed": all_passed,
            "results": [r.to_dict() for r in results],
        },
    )


def goal_replanning_event(reason: str, original_steps: int, new_steps: int) -> GoalEvent:
    """Create a replanning event."""
    return GoalEvent(
        type="replanning",
        data={
            "reason": reason,
            "original_steps": original_steps,
            "new_steps": new_steps,
        },
    )


def goal_correcting_event(step_id: int, attempt: int, max_attempts: int, error: str) -> GoalEvent:
    """Create a correcting event."""
    return GoalEvent(
        type="correcting",
        data={
            "step_id": step_id,
            "attempt": attempt,
            "max_attempts": max_attempts,
            "error": error,
        },
    )


def goal_progress_event(
    steps_done: int,
    steps_total: int,
    tokens_used: int,
    tokens_budget: int,
    eta_seconds: float,
) -> GoalEvent:
    """Create a progress event."""
    pct = (steps_done / steps_total * 100.0) if steps_total > 0 else 0.0
    return GoalEvent(
        type="progress",
        data={
            "steps_done": steps_done,
            "steps_total": steps_total,
            "percent": round(pct, 1),
            "tokens_used": tokens_used,
            "tokens_budget": tokens_budget,
            "eta_seconds": round(eta_seconds, 1),
        },
    )


def goal_completed_event(
    summary: str,
    files_modified: list[str],
    verification_passed: bool,
) -> GoalEvent:
    """Create a completed event."""
    return GoalEvent(
        type="completed",
        data={
            "summary": summary,
            "files_modified": list(files_modified),
            "verification_passed": verification_passed,
        },
    )


def goal_failed_event(error: str, partial_progress: str) -> GoalEvent:
    """Create a failed event."""
    return GoalEvent(
        type="failed",
        data={"error": error, "partial_progress": partial_progress},
    )


def goal_paused_event(goal_id: str, checkpoint_path: str) -> GoalEvent:
    """Create a paused event."""
    return GoalEvent(
        type="paused",
        data={"goal_id": goal_id, "checkpoint_path": checkpoint_path},
    )


def goal_checkpoint_event(goal_id: str, step_id: int, checkpoint_path: str) -> GoalEvent:
    """Create a checkpoint event."""
    return GoalEvent(
        type="checkpoint",
        data={"goal_id": goal_id, "step_id": step_id, "checkpoint_path": checkpoint_path},
    )
