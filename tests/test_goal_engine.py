"""
Unit tests for the Goal-Driven Autonomous Engine, Verification Engine, and Goal Events.

Run with: python3 tests/test_goal_engine.py
"""

from __future__ import annotations

import asyncio
import json
import os
import shutil
import sys
import tempfile
import time
from pathlib import Path

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lucy.core.agentic import Plan, PlanStep, PlanStepStatus
from lucy.core.goal_engine import GoalCheckpoint, GoalConfig, GoalEngine, GoalStatus
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
from lucy.core.tool import ToolContext
from lucy.core.verification import ProjectType, VerificationEngine, VerificationResult, VerificationStrategy
from lucy.commands.goal_commands import GoalCommand, get_commands


class TestRunner:
    def __init__(self) -> None:
        self.passed: list[str] = []
        self.failed: list[tuple[str, str]] = []

    def ok(self, name: str) -> None:
        self.passed.append(name)
        print(f"  ✓ {name}")

    def fail(self, name: str, error: str) -> None:
        self.failed.append((name, error))
        print(f"  ✗ {name}: {error}")

    def summary(self) -> bool:
        print("\n" + "=" * 60)
        print(f"  Results: {len(self.passed)}/{len(self.passed) + len(self.failed)} passed")
        if self.failed:
            for name, err in self.failed:
                print(f"  FAILED: {name} -> {err}")
        print("=" * 60)
        return len(self.failed) == 0


runner = TestRunner()


# ---------------------------------------------------------------------------
# 1. Verification Result & Engine Tests
# ---------------------------------------------------------------------------
print("\n── Verification Result & Engine ──")

try:
    res = VerificationResult(
        strategy="test",
        passed=False,
        output="FAILED test_foo.py::test_bar - AssertionError: Expected 1, got 2",
        errors=["AssertionError: Expected 1, got 2"],
        warnings=[],
        duration_seconds=1.234,
        command="pytest -q",
    )
    d = res.to_dict()
    assert d["strategy"] == "test"
    assert d["passed"] is False
    assert d["command"] == "pytest -q"
    restored = VerificationResult.from_dict(d)
    assert restored.strategy == "test"
    assert restored.passed is False
    assert restored.errors == res.errors
    runner.ok("VerificationResult serialization roundtrip")
except Exception as e:
    runner.fail("VerificationResult serialization roundtrip", str(e))


async def test_verification_engine():
    engine = VerificationEngine()

    # Project type detection: Python (current repo has pyproject.toml)
    ptype = await engine.detect_project_type(os.getcwd())
    assert ptype == ProjectType.PYTHON, f"Expected PYTHON, got {ptype}"
    runner.ok(f"detect_project_type detected {ptype.value} for current repo")

    # Project type detection in temporary dirs
    with tempfile.TemporaryDirectory() as tmpdir:
        (Path(tmpdir) / "Cargo.toml").write_text("[package]\nname='foo'", encoding="utf-8")
        rust_type = await engine.detect_project_type(tmpdir)
        assert rust_type == ProjectType.RUST
        runner.ok("detect_project_type detects Rust project")

    with tempfile.TemporaryDirectory() as tmpdir:
        (Path(tmpdir) / "package.json").write_text('{"devDependencies":{"typescript":"^5.0.0"}}', encoding="utf-8")
        (Path(tmpdir) / "tsconfig.json").write_text('{}', encoding="utf-8")
        ts_type = await engine.detect_project_type(tmpdir)
        assert ts_type == ProjectType.TYPESCRIPT
        runner.ok("detect_project_type detects TypeScript project")

    with tempfile.TemporaryDirectory() as tmpdir:
        (Path(tmpdir) / "go.mod").write_text("module example.com/foo", encoding="utf-8")
        go_type = await engine.detect_project_type(tmpdir)
        assert go_type == ProjectType.GO
        runner.ok("detect_project_type detects Go project")

    # Failure analysis
    fail_res = VerificationResult(
        strategy="test",
        passed=False,
        output="app/test.py:42: FAILED test_calc - AssertionError: 4 != 5",
        command="pytest",
    )
    analysis = await engine.analyze_failure(fail_res)
    assert "app/test.py:42" in analysis
    assert "Assertion" in analysis
    runner.ok("analyze_failure provides structured error diagnosis")


asyncio.run(test_verification_engine())


# ---------------------------------------------------------------------------
# 2. Goal Events Tests
# ---------------------------------------------------------------------------
print("\n── Goal Events ──")

try:
    ev_plan = goal_planning_event("Refactor database schema", estimated_steps=4)
    assert ev_plan.type == "planning"
    assert ev_plan.data["estimated_steps"] == 4
    runner.ok("goal_planning_event creation")

    ev_start = goal_step_start_event(1, "Create migration script", (0, 4))
    assert ev_start.type == "step_start"
    assert ev_start.data["step_id"] == 1
    assert "Create migration" in ev_start.format_summary()
    runner.ok("goal_step_start_event creation and format_summary")

    ev_v = goal_verification_event([
        VerificationResult("lint", True, "ok"),
        VerificationResult("test", True, "all passed"),
    ])
    assert ev_v.data["passed"] is True
    runner.ok("goal_verification_event all passed")

    ev_prog = goal_progress_event(2, 4, 1500, 500000, 45.0)
    assert ev_prog.data["percent"] == 50.0
    assert ev_prog.data["eta_seconds"] == 45.0
    runner.ok("goal_progress_event percentage and ETA calculation")

    ndjson_line = ev_prog.to_ndjson()
    parsed = json.loads(ndjson_line)
    assert parsed["type"] == "progress"
    assert parsed["data"]["percent"] == 50.0
    runner.ok("GoalEvent to_ndjson serialization")
except Exception as e:
    runner.fail("Goal Events", str(e))


# ---------------------------------------------------------------------------
# 3. Plan and Checkpoint Serialization Tests
# ---------------------------------------------------------------------------
print("\n── Plan & Goal Checkpoint Serialization ──")

try:
    plan = Plan(goal="Implement user authentication")
    plan.steps = [
        PlanStep(id=1, description="Create Auth model", status=PlanStepStatus.DONE, output="Created auth.py"),
        PlanStep(id=2, description="Write tests", status=PlanStepStatus.IN_PROGRESS, dependencies=[1]),
    ]
    p_dict = plan.to_dict()
    assert len(p_dict["steps"]) == 2
    assert p_dict["steps"][0]["output"] == "Created auth.py"
    restored_plan = Plan.from_dict(p_dict)
    assert restored_plan.goal == plan.goal
    assert restored_plan.steps[0].status == PlanStepStatus.DONE
    runner.ok("Plan and PlanStep serialization roundtrip")

    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)
        checkpoint = GoalCheckpoint(
            goal_id="goal_test_123",
            goal_text="Build autonomous engine",
            status=GoalStatus.EXECUTING,
            plan=plan,
            current_step=2,
            messages=[{"type": "user", "uuid": "u1", "content": "Start"}],
            files_modified=["lucy/core/goal_engine.py"],
            files_created=["lucy/core/verification.py"],
            started_at=time.time() - 100,
            elapsed_seconds=100.0,
            token_budget_used=12000,
            token_budget_total=500_000,
        )
        saved_file = checkpoint.save(tmp_path)
        assert saved_file.is_file()

        loaded_cp = GoalCheckpoint.load(saved_file)
        assert loaded_cp.goal_id == "goal_test_123"
        assert loaded_cp.status == GoalStatus.EXECUTING
        assert loaded_cp.current_step == 2
        assert loaded_cp.files_modified == ["lucy/core/goal_engine.py"]
        assert loaded_cp.token_budget_used == 12000
        runner.ok("GoalCheckpoint save and load JSON persistence")
except Exception as e:
    runner.fail("Plan and Checkpoint", str(e))


# ---------------------------------------------------------------------------
# 4. Goal Engine Execution, Pause, Resume, and Listing Tests
# ---------------------------------------------------------------------------
print("\n── Goal Engine Functionality ──")


async def test_goal_engine_ops():
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)
        config = GoalConfig(
            max_tokens=100_000,
            max_time_seconds=600,
            auto_verify=False,
        )
        engine = GoalEngine(config=config, checkpoint_dir=tmp_path)

        # 1. Create a dummy goal checkpoint to simulate execution
        plan = Plan(goal="Test Autonomous Workflow")
        plan.steps = [
            PlanStep(id=1, description="Step 1: Init", status=PlanStepStatus.DONE),
            PlanStep(id=2, description="Step 2: Build", status=PlanStepStatus.PENDING),
        ]
        cp = GoalCheckpoint(
            goal_id="goal_test_lifecycle",
            goal_text="Test Autonomous Workflow",
            status=GoalStatus.PAUSED,
            plan=plan,
            current_step=2,
            messages=[],
        )
        cp.save(tmp_path)

        # List goals
        goals = engine.list_goals()
        assert len(goals) == 1
        assert goals[0].goal_id == "goal_test_lifecycle"
        runner.ok("GoalEngine.list_goals returns saved goals")

        # Get goal
        fetched = engine.get_goal("goal_test_lifecycle")
        assert fetched is not None
        assert fetched.goal_text == "Test Autonomous Workflow"
        runner.ok("GoalEngine.get_goal retrieves goal by ID")

        # Cancel goal
        cancelled = engine.cancel_goal("goal_test_lifecycle")
        assert cancelled is True
        updated = engine.get_goal("goal_test_lifecycle")
        assert updated.status == GoalStatus.FAILED
        runner.ok("GoalEngine.cancel_goal marks goal as FAILED")


asyncio.run(test_goal_engine_ops())


# ---------------------------------------------------------------------------
# 5. Goal Commands Tests (/goal)
# ---------------------------------------------------------------------------
print("\n── Goal Slash Commands (/goal) ──")


async def test_goal_commands():
    cmds = get_commands()
    assert len(cmds) == 1
    cmd = cmds[0]
    assert cmd.name == "goal"
    assert "goals" in cmd.aliases
    assert "autonomous" in cmd.aliases
    runner.ok("GoalCommand registration and aliases")

    class MockState:
        def __init__(self):
            self.cwd = os.getcwd()
            self.model = "claude-3-7-sonnet"
            self.permission_mode = "auto_accept"

    state = MockState()

    # Empty args -> usage output
    res_usage = await cmd.execute("", state)
    assert "Usage" in res_usage.output
    runner.ok("/goal without args displays command help")

    # /goal list
    res_list = await cmd.execute("list", state)
    assert res_list.output is not None
    runner.ok("/goal list executes successfully")

    # /goal status
    res_status = await cmd.execute("status", state)
    assert res_status.output is not None or res_status.error is not None
    runner.ok("/goal status executes successfully")

    # /goal cancel on non-existent
    res_cancel = await cmd.execute("cancel nonexistent_123", state)
    assert "nonexistent_123" in (res_cancel.error or res_cancel.output)
    runner.ok("/goal cancel handles non-existent targets properly")


asyncio.run(test_goal_commands())


# ---------------------------------------------------------------------------
# 6. Autonomous Goal Execution Lifecycle Simulation
# ---------------------------------------------------------------------------
print("\n── Autonomous Goal Execution Simulation ──")


async def test_goal_execution_simulation():
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)
        config = GoalConfig(
            max_tokens=500_000,
            max_time_seconds=300,
            auto_verify=False,
        )
        engine = GoalEngine(config=config, checkpoint_dir=tmp_path)

        # Mock _execute_step to simulate tool execution without external API call
        async def mock_execute_step(step, checkpoint, context, system_prompt, messages, tools, model=None):
            return True, f"Mock output for {step.description}", ["modified_file.py"], ["created_file.py"], 250

        engine._execute_step = mock_execute_step

        ctx = ToolContext(cwd=tmpdir, permission_mode="auto_accept")
        events: list[GoalEvent] = []

        async for event in engine.execute(goal_text="Create greeting service", context=ctx):
            events.append(event)

        event_types = [e.type for e in events]
        assert "planning" in event_types
        assert "step_start" in event_types
        assert "step_complete" in event_types
        assert "progress" in event_types
        assert "checkpoint" in event_types
        assert "completed" in event_types
        runner.ok("GoalEngine.execute yields full lifecycle events (planning -> steps -> progress -> completed)")

        # Verify final checkpoint status
        final_cp = engine.current_goal
        assert final_cp is not None
        assert final_cp.status == GoalStatus.COMPLETED
        assert "created_file.py" in final_cp.files_created
        assert "modified_file.py" in final_cp.files_modified
        assert final_cp.token_budget_used > 0
        runner.ok("Final checkpoint has COMPLETED status and recorded files")


if __name__ == "__main__":
    asyncio.run(test_goal_execution_simulation())
    success = runner.summary()
    sys.exit(0 if success else 1)
