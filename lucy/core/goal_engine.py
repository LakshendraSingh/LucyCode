"""
Goal-Driven Autonomous Engine — Lucy's most powerful mode.

Takes a high-level goal and autonomously works until completion:
1. Decomposes the goal into a dynamic plan
2. Executes steps with real-time replanning
3. Self-verifies using tests and type checks
4. Self-corrects on failures
5. Checkpoints for crash recovery
6. Reports progress with ETA
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, AsyncGenerator

from lucy.core.agentic import Plan, PlanStep, PlanStepStatus, PlanningAgent
from lucy.core.config import get_config
from lucy.core.context import build_system_prompt, get_git_status, get_lucymd_content
from lucy.core.goal_events import (
    GoalEvent,
    goal_checkpoint_event,
    goal_completed_event,
    goal_correcting_event,
    goal_failed_event,
    goal_paused_event,
    goal_planning_event,
    goal_progress_event,
    goal_replanning_event,
    goal_step_complete_event,
    goal_step_failed_event,
    goal_step_start_event,
    goal_verification_event,
    goal_verifying_event,
)
from lucy.core.message import (
    AssistantMessage,
    Message,
    StreamEvent,
    ToolUseBlock,
    UserMessage,
    create_user_message,
)
from lucy.core.query import QueryParams, query_loop
from lucy.core.tool import ToolContext, ToolRegistry, get_tool_registry
from lucy.core.verification import VerificationEngine, VerificationResult
from lucy.utils.session import deserialize_message, serialize_message

logger = logging.getLogger(__name__)


def _default_checkpoint_dir() -> Path:
    """Determine default checkpoint directory with graceful fallback for sandboxes."""
    custom_env = os.environ.get("LUCY_GOALS_DIR") or os.environ.get("LUCYCODE_GOALS_DIR")
    if custom_env:
        path = Path(custom_env)
        try:
            path.mkdir(parents=True, exist_ok=True)
            return path
        except OSError:
            pass

    primary = Path.home() / ".lucycode" / "goals"
    try:
        primary.mkdir(parents=True, exist_ok=True)
        return primary
    except OSError:
        pass

    # Fallback to workspace .lucy/goals
    workspace_fallback = Path.cwd() / ".lucy" / "goals"
    try:
        workspace_fallback.mkdir(parents=True, exist_ok=True)
        return workspace_fallback
    except OSError:
        pass

    # Final fallback to system temporary directory
    import tempfile
    temp_fallback = Path(tempfile.gettempdir()) / "lucycode" / "goals"
    temp_fallback.mkdir(parents=True, exist_ok=True)
    return temp_fallback


# ---------------------------------------------------------------------------
# Goal Status
# ---------------------------------------------------------------------------

class GoalStatus(str, Enum):
    """Lifecycle states of an autonomous goal."""
    PENDING = "pending"
    PLANNING = "planning"
    EXECUTING = "executing"
    VERIFYING = "verifying"
    CORRECTING = "correcting"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"


# ---------------------------------------------------------------------------
# Goal Checkpoint
# ---------------------------------------------------------------------------

@dataclass
class GoalCheckpoint:
    """Serializable checkpoint for crash recovery and pause/resume."""
    goal_id: str
    goal_text: str
    status: GoalStatus
    plan: Plan
    current_step: int
    messages: list[dict[str, Any]]  # serialized conversation
    files_modified: list[str] = field(default_factory=list)
    files_created: list[str] = field(default_factory=list)
    verification_results: list[VerificationResult] = field(default_factory=list)
    started_at: float = field(default_factory=time.time)
    elapsed_seconds: float = 0.0
    token_budget_used: int = 0
    token_budget_total: int = 500_000

    def to_dict(self) -> dict[str, Any]:
        """Serialize checkpoint to a JSON-compatible dictionary."""
        return {
            "goal_id": self.goal_id,
            "goal_text": self.goal_text,
            "status": self.status.value,
            "plan": self.plan.to_dict(),
            "current_step": self.current_step,
            "messages": self.messages,
            "files_modified": list(self.files_modified),
            "files_created": list(self.files_created),
            "verification_results": [r.to_dict() for r in self.verification_results],
            "started_at": self.started_at,
            "elapsed_seconds": round(self.elapsed_seconds, 2),
            "token_budget_used": self.token_budget_used,
            "token_budget_total": self.token_budget_total,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> GoalCheckpoint:
        """Deserialize checkpoint from dictionary."""
        status_val = data.get("status", GoalStatus.PENDING.value)
        try:
            status = GoalStatus(status_val)
        except ValueError:
            status = GoalStatus.PENDING

        plan_data = data.get("plan", {})
        plan = Plan.from_dict(plan_data) if plan_data else Plan(goal=data.get("goal_text", ""))

        v_results = [
            VerificationResult.from_dict(r) for r in data.get("verification_results", [])
        ]

        return cls(
            goal_id=data.get("goal_id", ""),
            goal_text=data.get("goal_text", ""),
            status=status,
            plan=plan,
            current_step=int(data.get("current_step", 1)),
            messages=data.get("messages", []),
            files_modified=data.get("files_modified", []),
            files_created=data.get("files_created", []),
            verification_results=v_results,
            started_at=float(data.get("started_at", time.time())),
            elapsed_seconds=float(data.get("elapsed_seconds", 0.0)),
            token_budget_used=int(data.get("token_budget_used", 0)),
            token_budget_total=int(data.get("token_budget_total", 500_000)),
        )

    def save(self, directory: Path | None = None) -> Path:
        """Save checkpoint to disk as JSON."""
        dir_path = directory or _default_checkpoint_dir()
        try:
            dir_path.mkdir(parents=True, exist_ok=True)
        except OSError:
            pass
        file_path = dir_path / f"{self.goal_id}.json"

        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(self.to_dict(), f, indent=2)

        return file_path

    @classmethod
    def load(cls, path: Path) -> GoalCheckpoint:
        """Load checkpoint from JSON file."""
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return cls.from_dict(data)


# ---------------------------------------------------------------------------
# Goal Configuration
# ---------------------------------------------------------------------------

@dataclass
class GoalConfig:
    """Configuration for goal execution."""
    max_tokens: int = 500_000  # Total token budget
    max_time_seconds: int = 3600  # 1 hour max
    max_turns: int = 200  # Max agent turns
    auto_verify: bool = True  # Run tests after changes
    auto_commit: bool = False  # Git commit after each step
    confirmation_gates: list[str] = field(default_factory=lambda: ["destructive"])
    # Verification strategies
    run_tests: bool = True
    run_typecheck: bool = True
    run_lint: bool = True
    check_build: bool = True
    # Self-correction parameters
    max_correction_retries: int = 3
    # Checkpointing
    checkpoint_interval_steps: int = 1


# ---------------------------------------------------------------------------
# Goal Engine
# ---------------------------------------------------------------------------

class GoalEngine:
    """The autonomous goal execution engine."""

    def __init__(
        self,
        config: GoalConfig | None = None,
        checkpoint_dir: Path | None = None,
    ) -> None:
        self.config = config or GoalConfig()
        self._current_checkpoint: GoalCheckpoint | None = None
        self._checkpoint_dir = checkpoint_dir or _default_checkpoint_dir()
        try:
            self._checkpoint_dir.mkdir(parents=True, exist_ok=True)
        except OSError:
            pass
        self._verification_engine = VerificationEngine()
        self._pause_requested = False
        self._abort_event = asyncio.Event()

    @property
    def current_goal(self) -> GoalCheckpoint | None:
        """Currently active or last handled goal checkpoint."""
        return self._current_checkpoint

    def pause_requested(self) -> None:
        """Flag the engine to pause gracefully after current work."""
        self._pause_requested = True

    async def pause(self) -> GoalCheckpoint | None:
        """Pause current goal, persist state, and return checkpoint."""
        self._pause_requested = True
        self._abort_event.set()
        if self._current_checkpoint:
            self._current_checkpoint.status = GoalStatus.PAUSED
            self._current_checkpoint.save(self._checkpoint_dir)
            return self._current_checkpoint
        return None

    def cancel_goal(self, goal_id: str | None = None) -> bool:
        """Cancel current or specified goal."""
        target_id = goal_id or (self._current_checkpoint.goal_id if self._current_checkpoint else None)
        if not target_id:
            return False

        self._pause_requested = True
        self._abort_event.set()

        cp_path = self._checkpoint_dir / f"{target_id}.json"
        if cp_path.is_file():
            try:
                cp = GoalCheckpoint.load(cp_path)
                cp.status = GoalStatus.FAILED
                cp.save(self._checkpoint_dir)
                if self._current_checkpoint and self._current_checkpoint.goal_id == target_id:
                    self._current_checkpoint = cp
                return True
            except Exception as e:
                logger.error("Failed to cancel goal %s: %s", target_id, e)
                return False
        return False

    def list_goals(self) -> list[GoalCheckpoint]:
        """List all goals (active, completed, failed, paused)."""
        checkpoints: list[GoalCheckpoint] = []
        if not self._checkpoint_dir.exists():
            return checkpoints

        for path in sorted(self._checkpoint_dir.glob("*.json"), key=os.path.getmtime, reverse=True):
            try:
                cp = GoalCheckpoint.load(path)
                checkpoints.append(cp)
            except Exception as e:
                logger.warning("Could not read checkpoint %s: %s", path, e)

        return checkpoints

    def get_goal(self, goal_id: str) -> GoalCheckpoint | None:
        """Get checkpoint by goal ID."""
        path = self._checkpoint_dir / f"{goal_id}.json"
        if path.is_file():
            try:
                return GoalCheckpoint.load(path)
            except Exception as e:
                logger.error("Failed loading goal %s: %s", goal_id, e)
        return None

    # -----------------------------------------------------------------------
    # Execution Lifecycle
    # -----------------------------------------------------------------------

    async def execute(
        self,
        goal_text: str,
        context: ToolContext,
        model: str | None = None,
        tools: ToolRegistry | None = None,
        abort_event: asyncio.Event | None = None,
    ) -> AsyncGenerator[GoalEvent, None]:
        """Execute a goal autonomously. Yields GoalEvents for progress reporting."""
        goal_id = f"goal_{int(time.time())}_{uuid.uuid4().hex[:6]}"
        self._pause_requested = False
        self._abort_event = abort_event or asyncio.Event()

        # Step 1: Planning
        yield goal_planning_event(goal=goal_text, estimated_steps=0)

        plan = await self._decompose_and_plan(goal_text, context, model, tools)
        estimated_steps = len(plan.steps)
        yield goal_planning_event(goal=goal_text, estimated_steps=estimated_steps)

        # Initialize checkpoint
        checkpoint = GoalCheckpoint(
            goal_id=goal_id,
            goal_text=goal_text,
            status=GoalStatus.PLANNING,
            plan=plan,
            current_step=1,
            messages=[],
            files_modified=[],
            files_created=[],
            started_at=time.time(),
            token_budget_total=self.config.max_tokens,
        )
        self._current_checkpoint = checkpoint
        cp_path = checkpoint.save(self._checkpoint_dir)
        yield goal_checkpoint_event(goal_id=goal_id, step_id=0, checkpoint_path=str(cp_path))

        # Run main loop
        async for event in self._run_goal_loop(checkpoint, context, model, tools):
            yield event

    async def resume(
        self,
        goal_id: str,
        context: ToolContext | None = None,
        model: str | None = None,
        tools: ToolRegistry | None = None,
        abort_event: asyncio.Event | None = None,
    ) -> AsyncGenerator[GoalEvent, None]:
        """Resume a goal from saved checkpoint."""
        checkpoint = self.get_goal(goal_id)
        if not checkpoint:
            yield goal_failed_event(
                error=f"Goal checkpoint not found: {goal_id}",
                partial_progress="Could not find checkpoint to resume.",
            )
            return

        self._current_checkpoint = checkpoint
        self._pause_requested = False
        self._abort_event = abort_event or asyncio.Event()

        ctx = context or ToolContext(cwd=os.getcwd(), permission_mode="auto_accept")

        yield goal_progress_event(
            steps_done=checkpoint.plan.progress[0],
            steps_total=checkpoint.plan.progress[1],
            tokens_used=checkpoint.token_budget_used,
            tokens_budget=checkpoint.token_budget_total,
            eta_seconds=0.0,
        )

        async for event in self._run_goal_loop(checkpoint, ctx, model, tools):
            yield event

    # -----------------------------------------------------------------------
    # Core Autonomous Execution Loop
    # -----------------------------------------------------------------------

    async def _run_goal_loop(
        self,
        checkpoint: GoalCheckpoint,
        context: ToolContext,
        model: str | None = None,
        tools: ToolRegistry | None = None,
    ) -> AsyncGenerator[GoalEvent, None]:
        """Core loop executing steps, verifying, replanning, and checkpointing."""
        checkpoint.status = GoalStatus.EXECUTING
        registry = tools or get_tool_registry()

        # Re-hydrate conversation messages from checkpoint
        messages: list[Message] = []
        for raw_msg in checkpoint.messages:
            deserialized = deserialize_message(raw_msg)
            if deserialized:
                messages.append(deserialized)

        # Track system context
        git_ctx = await get_git_status(context.cwd)
        lucymd_ctx = get_lucymd_content(context.cwd)
        system_prompt = build_system_prompt(
            cwd=context.cwd,
            git_status=git_ctx,
            lucymd=lucymd_ctx,
            custom_instructions=(
                "You are executing an autonomous goal. Work systematically step-by-step. "
                "Use the available tools directly to inspect, edit, write code, run commands, and verify changes. "
                "Keep actions atomic, precise, and verify before moving forward."
            ),
        )

        while checkpoint.current_step <= len(checkpoint.plan.steps):
            # Check pause / abort conditions
            if self._pause_requested or self._abort_event.is_set():
                checkpoint.status = GoalStatus.PAUSED
                checkpoint.elapsed_seconds += (time.time() - checkpoint.started_at)
                cp_path = checkpoint.save(self._checkpoint_dir)
                yield goal_paused_event(goal_id=checkpoint.goal_id, checkpoint_path=str(cp_path))
                return

            # Check time budget
            checkpoint.elapsed_seconds = time.time() - checkpoint.started_at
            if checkpoint.elapsed_seconds > self.config.max_time_seconds:
                checkpoint.status = GoalStatus.FAILED
                checkpoint.save(self._checkpoint_dir)
                yield goal_failed_event(
                    error=f"Time budget exceeded ({int(checkpoint.elapsed_seconds)}s > {self.config.max_time_seconds}s)",
                    partial_progress=f"Completed {checkpoint.plan.progress[0]} of {len(checkpoint.plan.steps)} steps",
                )
                return

            # Check token budget
            if checkpoint.token_budget_used >= self.config.max_tokens:
                checkpoint.status = GoalStatus.FAILED
                checkpoint.save(self._checkpoint_dir)
                yield goal_failed_event(
                    error=f"Token budget exceeded ({checkpoint.token_budget_used} >= {self.config.max_tokens})",
                    partial_progress=f"Completed {checkpoint.plan.progress[0]} of {len(checkpoint.plan.steps)} steps",
                )
                return

            step_idx = checkpoint.current_step - 1
            step = checkpoint.plan.steps[step_idx]

            # Skip already completed steps if resuming
            if step.status == PlanStepStatus.DONE:
                checkpoint.current_step += 1
                continue

            step.status = PlanStepStatus.IN_PROGRESS
            total_steps = len(checkpoint.plan.steps)
            done_steps = sum(1 for s in checkpoint.plan.steps if s.status == PlanStepStatus.DONE)

            # Emit ETA and step start
            avg_step_duration = (checkpoint.elapsed_seconds / max(1, done_steps)) if done_steps > 0 else 30.0
            eta_seconds = (total_steps - done_steps) * avg_step_duration

            yield goal_step_start_event(
                step_id=step.id,
                description=step.description,
                progress=(done_steps, total_steps),
            )
            yield goal_progress_event(
                steps_done=done_steps,
                steps_total=total_steps,
                tokens_used=checkpoint.token_budget_used,
                tokens_budget=checkpoint.token_budget_total,
                eta_seconds=eta_seconds,
            )

            # Execute the step using query loop
            step_success, step_output, new_files_mod, new_files_created, used_tokens = await self._execute_step(
                step=step,
                checkpoint=checkpoint,
                context=context,
                system_prompt=system_prompt,
                messages=messages,
                tools=registry,
                model=model,
            )

            checkpoint.token_budget_used += used_tokens
            checkpoint.files_modified.extend([f for f in new_files_mod if f not in checkpoint.files_modified])
            checkpoint.files_created.extend([f for f in new_files_created if f not in checkpoint.files_created])
            step.output = step_output

            if not step_success:
                yield goal_step_failed_event(step_id=step.id, error=step.error or "Step execution failed")

            # Self-Verification Stage
            verification_passed = True
            if self.config.auto_verify and (new_files_mod or new_files_created or self.config.run_tests):
                checkpoint.status = GoalStatus.VERIFYING
                yield goal_verifying_event(strategy="all")

                verification_results = await self._verification_engine.verify_all(
                    cwd=context.cwd,
                    files_changed=new_files_mod + new_files_created,
                    run_tests=self.config.run_tests,
                    run_typecheck=self.config.run_typecheck,
                    run_lint=self.config.run_lint,
                    check_build=self.config.check_build,
                )
                checkpoint.verification_results = verification_results
                yield goal_verification_event(verification_results)

                # Self-Correction Loop on failure
                failed_checks = [r for r in verification_results if not r.passed]
                if failed_checks:
                    verification_passed = await self._run_self_correction(
                        failed_checks=failed_checks,
                        step=step,
                        checkpoint=checkpoint,
                        context=context,
                        system_prompt=system_prompt,
                        messages=messages,
                        tools=registry,
                        model=model,
                    )

            if not verification_passed:
                # Attempt dynamic replanning for the remaining work
                checkpoint.status = GoalStatus.PLANNING
                replanned = await self._replan_from_failure(
                    step=step,
                    checkpoint=checkpoint,
                    context=context,
                    model=model,
                    tools=registry,
                )
                if replanned:
                    yield goal_replanning_event(
                        reason=f"Verification failed on step {step.id}; revised plan created",
                        original_steps=total_steps,
                        new_steps=len(checkpoint.plan.steps),
                    )
                    checkpoint.status = GoalStatus.EXECUTING
                    continue
                else:
                    checkpoint.status = GoalStatus.FAILED
                    checkpoint.save(self._checkpoint_dir)
                    yield goal_failed_event(
                        error=f"Step {step.id} failed verification and correction retries were exhausted.",
                        partial_progress=f"Completed {done_steps} of {total_steps} steps.",
                    )
                    return

            # Mark step complete
            step.status = PlanStepStatus.DONE
            yield goal_step_complete_event(step_id=step.id, output=step.output)

            # Auto-commit if configured
            if self.config.auto_commit:
                await self._git_commit_step(context.cwd, step.description)

            # Dynamic replanning check: evaluate if subsequent steps need adjustment
            replanned_forward = await self._check_dynamic_replanning(
                checkpoint=checkpoint,
                last_step=step,
                context=context,
                model=model,
                tools=registry,
            )
            if replanned_forward:
                yield goal_replanning_event(
                    reason="Step completed; remaining plan optimized",
                    original_steps=total_steps,
                    new_steps=len(checkpoint.plan.steps),
                )

            # Checkpoint save
            checkpoint.current_step += 1
            checkpoint.messages = [serialize_message(m) for m in messages]
            if checkpoint.current_step % self.config.checkpoint_interval_steps == 0 or checkpoint.current_step > len(checkpoint.plan.steps):
                cp_path = checkpoint.save(self._checkpoint_dir)
                yield goal_checkpoint_event(
                    goal_id=checkpoint.goal_id,
                    step_id=step.id,
                    checkpoint_path=str(cp_path),
                )

        # All steps completed successfully
        checkpoint.status = GoalStatus.COMPLETED
        checkpoint.elapsed_seconds = time.time() - checkpoint.started_at
        checkpoint.save(self._checkpoint_dir)

        summary = (
            f"Goal '{checkpoint.goal_text}' completed successfully in "
            f"{int(checkpoint.elapsed_seconds)}s across {len(checkpoint.plan.steps)} steps."
        )
        yield goal_completed_event(
            summary=summary,
            files_modified=checkpoint.files_modified + checkpoint.files_created,
            verification_passed=True,
        )

    # -----------------------------------------------------------------------
    # Step Execution Implementation
    # -----------------------------------------------------------------------

    async def _execute_step(
        self,
        step: PlanStep,
        checkpoint: GoalCheckpoint,
        context: ToolContext,
        system_prompt: str,
        messages: list[Message],
        tools: ToolRegistry,
        model: str | None = None,
    ) -> tuple[bool, str, list[str], list[str], int]:
        """Execute a single step using the query loop with tool safety confirmation gates."""
        step_prompt = (
            f"Autonomous Goal: {checkpoint.goal_text}\n\n"
            f"Active Step {step.id}: {step.description}\n"
            f"Recommended Tools: {', '.join(step.tools_needed) if step.tools_needed else 'Any suitable tools'}\n\n"
            "Execute this step directly using the available tools (FileRead, FileWrite, FileEdit, Bash, etc.). "
            "Inspect files, write necessary code, run scripts or checks. "
            "When finished, summarize exactly what actions were taken and files modified."
        )

        user_msg = create_user_message(step_prompt)
        messages.append(user_msg)

        # Wrap tool context to track safety gates and modified files
        files_modified: list[str] = []
        files_created: list[str] = []
        used_tokens = 0

        # Safety gate check wrapper
        original_ask = context.ask_permission

        def _guarded_ask(tool_name: str, summary: str) -> bool:
            if "destructive" in self.config.confirmation_gates:
                lower = summary.lower()
                is_destructive = any(w in lower for w in ["rm -rf", "git reset --hard", "drop table", "clean -f"])
                if is_destructive and original_ask:
                    return original_ask(tool_name, f"Destructive command detected: {summary}")
            return original_ask(tool_name, summary) if original_ask else True

        step_context = ToolContext(
            cwd=context.cwd,
            permission_mode=context.permission_mode,
            is_interactive=context.is_interactive,
            max_result_chars=context.max_result_chars,
            ask_permission=_guarded_ask,
        )

        params = QueryParams(
            messages=list(messages),
            system_prompt=system_prompt,
            tools=tools,
            tool_context=step_context,
            model=model,
            max_turns=30,
            abort_event=self._abort_event,
        )

        step_output_parts: list[str] = []
        is_success = True

        try:
            async for event in query_loop(params):
                if isinstance(event, StreamEvent):
                    if event.type == "tool_use_complete":
                        inp = event.data.get("input", {})
                        name = event.data.get("name", "")
                        fpath = inp.get("file_path") or inp.get("path")
                        if fpath:
                            if name in ("FileWrite", "Write"):
                                files_created.append(fpath)
                            elif name in ("FileEdit", "Edit", "NotebookEdit"):
                                files_modified.append(fpath)

                elif isinstance(event, AssistantMessage):
                    messages.append(event)
                    if event.usage:
                        used_tokens += (event.usage.input_tokens + event.usage.output_tokens)
                    text = event.get_text()
                    if text:
                        step_output_parts.append(text)
                    if event.api_error:
                        is_success = False
                        step.error = event.api_error

                elif isinstance(event, UserMessage):
                    messages.append(event)

        except Exception as e:
            logger.exception("Step %d execution error: %s", step.id, e)
            is_success = False
            step.error = str(e)

        combined_output = "\n".join(step_output_parts).strip()
        return is_success, combined_output, files_modified, files_created, used_tokens

    # -----------------------------------------------------------------------
    # Self-Correction Engine
    # -----------------------------------------------------------------------

    async def _run_self_correction(
        self,
        failed_checks: list[VerificationResult],
        step: PlanStep,
        checkpoint: GoalCheckpoint,
        context: ToolContext,
        system_prompt: str,
        messages: list[Message],
        tools: ToolRegistry,
        model: str | None = None,
    ) -> bool:
        """Attempt to self-correct verification failures iteratively."""
        checkpoint.status = GoalStatus.CORRECTING

        for attempt in range(1, self.config.max_correction_retries + 1):
            first_fail = failed_checks[0]
            failure_analysis = await self._verification_engine.analyze_failure(first_fail)

            # Signal correcting event
            # (Note: GoalEngine.execute caller listens to these events via the generator,
            # but since self-correction is called within the generator, we can handle correction turns)
            logger.info(
                "Self-correction step %d (attempt %d/%d): %s",
                step.id, attempt, self.config.max_correction_retries, first_fail.strategy,
            )

            correction_prompt = (
                f"⚠️ Self-Verification Failed for step {step.id}!\n\n"
                f"Strategy: {first_fail.strategy}\n"
                f"Command: {first_fail.command}\n\n"
                f"Diagnosis & Suggestions:\n{failure_analysis}\n\n"
                f"Detailed Output:\n{first_fail.output[:2000]}\n\n"
                "Please fix these errors immediately using FileEdit or FileWrite. "
                "Ensure syntax, types, and tests pass."
            )

            user_msg = create_user_message(correction_prompt)
            messages.append(user_msg)

            params = QueryParams(
                messages=list(messages),
                system_prompt=system_prompt,
                tools=tools,
                tool_context=context,
                model=model,
                max_turns=20,
                abort_event=self._abort_event,
            )

            async for event in query_loop(params):
                if isinstance(event, AssistantMessage):
                    messages.append(event)
                    if event.usage:
                        checkpoint.token_budget_used += (event.usage.input_tokens + event.usage.output_tokens)
                elif isinstance(event, UserMessage):
                    messages.append(event)

            # Re-run verification
            re_results = await self._verification_engine.verify_all(
                cwd=context.cwd,
                run_tests=self.config.run_tests,
                run_typecheck=self.config.run_typecheck,
                run_lint=self.config.run_lint,
                check_build=self.config.check_build,
            )
            checkpoint.verification_results = re_results
            failed_checks = [r for r in re_results if not r.passed]
            if not failed_checks:
                logger.info("Self-correction succeeded on attempt %d for step %d!", attempt, step.id)
                try:
                    from lucy.core.recursive_harness import get_harness2
                    h2 = get_harness2()
                    clean_diag = failure_analysis.split("\n")[0].strip() if failure_analysis else "Verification fixed"
                    h2.experience_library.add_experience(
                        domain="debugging",
                        lesson=f"When encountering {first_fail.strategy} failure ({first_fail.command[:50]}): {clean_diag[:140]}",
                        trigger_pattern=rf"\b({first_fail.strategy}|debug|fix|test)\b",
                        confidence=0.95,
                    )
                except Exception as ex:
                    logger.debug("Failed saving self-correction experience: %s", ex)
                return True

        return False

    # -----------------------------------------------------------------------
    # Dynamic Planning and Replanning
    # -----------------------------------------------------------------------

    async def _decompose_and_plan(
        self,
        goal: str,
        context: ToolContext,
        model: str | None = None,
        tools: ToolRegistry | None = None,
    ) -> Plan:
        """Decompose a high-level goal into an actionable Plan."""
        planner = PlanningAgent()

        # Gather directory listing and context for planner
        file_summary = ""
        try:
            items = os.listdir(context.cwd)[:30]
            file_summary = f"Root project files: {', '.join(items)}"
        except Exception:
            pass

        # Use PlanningAgent heuristic or prompt-based plan
        plan = await planner.create_plan(goal=goal, context=file_summary)
        if not plan.steps:
            # Fallback guarantee
            plan.steps = [
                PlanStep(id=1, description=f"Analyze repository structure for: {goal}", tools_needed=["Glob", "Grep", "Read"]),
                PlanStep(id=2, description="Implement required changes", tools_needed=["Write", "Edit"], dependencies=[1]),
                PlanStep(id=3, description="Verify changes with tests and checks", tools_needed=["Bash"], dependencies=[2]),
            ]

        return plan

    async def _replan_from_failure(
        self,
        step: PlanStep,
        checkpoint: GoalCheckpoint,
        context: ToolContext,
        model: str | None = None,
        tools: ToolRegistry | None = None,
    ) -> bool:
        """Replan remaining steps when a step fails after all correction retries."""
        logger.warning("Replanning goal after step %d failure: %s", step.id, step.description)

        # Break the failing step into smaller, simpler sub-steps
        current_idx = checkpoint.current_step - 1
        new_substeps = [
            PlanStep(
                id=step.id,
                description=f"Isolate root cause of failure in: {step.description}",
                tools_needed=["Read", "Grep", "Bash"],
                dependencies=step.dependencies,
            ),
            PlanStep(
                id=step.id + 1,
                description=f"Implement targeted fix with minimal scope for: {step.description}",
                tools_needed=["Edit", "Write"],
                dependencies=[step.id],
            ),
            PlanStep(
                id=step.id + 2,
                description="Verify isolated fix and regression test",
                tools_needed=["Bash"],
                dependencies=[step.id + 1],
            ),
        ]

        # Shift remaining subsequent steps
        remaining = checkpoint.plan.steps[current_idx + 1:]
        new_steps_list = checkpoint.plan.steps[:current_idx] + new_substeps
        offset = len(new_substeps) - 1
        for s in remaining:
            s.id += offset
            s.dependencies = [d + offset if d >= step.id else d for d in s.dependencies]
            new_steps_list.append(s)

        checkpoint.plan.steps = new_steps_list
        return True

    async def _check_dynamic_replanning(
        self,
        checkpoint: GoalCheckpoint,
        last_step: PlanStep,
        context: ToolContext,
        model: str | None = None,
        tools: ToolRegistry | None = None,
    ) -> bool:
        """Inspect if remaining steps should be dynamically adapted or pruned."""
        # Simple dynamic pruning: if all remaining steps are already met or if any step is redundant
        modified = False
        remaining = checkpoint.plan.steps[checkpoint.current_step:]
        for s in remaining:
            # If step is redundant with output of last_step
            if s.description.lower() in last_step.output.lower() and "already done" in last_step.output.lower():
                s.status = PlanStepStatus.SKIPPED
                modified = True

        return modified

    async def _git_commit_step(self, cwd: str, step_description: str) -> None:
        """Commit progress after a step to git repository."""
        try:
            proc = await asyncio.create_subprocess_shell(
                f'git add -A && git commit -m "feat(goal): {step_description[:80]}"',
                cwd=cwd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            await asyncio.wait_for(proc.communicate(), timeout=15)
        except Exception as e:
            logger.debug("Auto-commit skipped or failed: %s", e)
