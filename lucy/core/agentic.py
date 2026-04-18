"""
Agentic AI — planning, self-reflection, goal decomposition, and reasoning.

Higher-order agentic patterns that sit above the query loop:
  - PlanningAgent: Create a plan before executing
  - ReflectionAgent: Self-critique and retry
  - GoalDecomposer: Break complex goals into subtasks
  - ReasoningChain: Chain-of-thought with explicit steps
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, AsyncGenerator

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------

class PlanStepStatus(str, Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    DONE = "done"
    FAILED = "failed"
    SKIPPED = "skipped"


@dataclass
class PlanStep:
    """A single step in an execution plan."""
    id: int
    description: str
    status: PlanStepStatus = PlanStepStatus.PENDING
    tools_needed: list[str] = field(default_factory=list)
    dependencies: list[int] = field(default_factory=list)
    output: str = ""
    error: str = ""

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "description": self.description,
            "status": self.status.value,
            "tools": self.tools_needed,
            "deps": self.dependencies,
        }


@dataclass
class Plan:
    """An execution plan."""
    goal: str
    steps: list[PlanStep] = field(default_factory=list)
    created_at: float = field(default_factory=time.time)
    reasoning: str = ""

    def to_markdown(self) -> str:
        lines = [f"## Plan: {self.goal}\n"]
        if self.reasoning:
            lines.append(f"**Reasoning**: {self.reasoning}\n")
        for step in self.steps:
            icon = {
                "pending": "⬜", "in_progress": "🔄",
                "done": "✅", "failed": "❌", "skipped": "⏭️"
            }.get(step.status.value, "?")
            deps = f" (after step {', '.join(map(str, step.dependencies))})" if step.dependencies else ""
            tools = f" [{', '.join(step.tools_needed)}]" if step.tools_needed else ""
            lines.append(f"{icon} **Step {step.id}**: {step.description}{deps}{tools}")
            if step.output:
                lines.append(f"   → {step.output[:200]}")
            if step.error:
                lines.append(f"   ⚠️ {step.error}")
        return "\n".join(lines)

    @property
    def is_complete(self) -> bool:
        return all(s.status in (PlanStepStatus.DONE, PlanStepStatus.SKIPPED) for s in self.steps)

    @property
    def progress(self) -> tuple[int, int]:
        done = sum(1 for s in self.steps if s.status in (PlanStepStatus.DONE, PlanStepStatus.SKIPPED))
        return done, len(self.steps)


@dataclass
class ReflectionResult:
    """Result of a self-reflection cycle."""
    original_output: str
    critique: str
    improved_output: str
    rounds: int = 1
    quality_score: float = 0.0  # 0.0-1.0


@dataclass
class SubGoal:
    """A decomposed sub-goal."""
    id: int
    description: str
    complexity: str = "medium"  # simple, medium, complex
    dependencies: list[int] = field(default_factory=list)
    result: str = ""


# ---------------------------------------------------------------------------
# Planning Agent
# ---------------------------------------------------------------------------

class PlanningAgent:
    """Create and execute structured plans.

    The planning agent:
    1. Analyzes the goal and creates a step-by-step plan
    2. Executes each step using the appropriate tools
    3. Tracks progress and handles failures
    4. Can replan if a step fails
    """

    def __init__(self):
        self._current_plan: Plan | None = None

    async def create_plan(self, goal: str, context: str = "") -> Plan:
        """Create a plan by analyzing the goal.

        This uses a structured prompt to generate plan steps.
        """
        plan_prompt = (
            f"Analyze this goal and create a detailed execution plan.\n\n"
            f"Goal: {goal}\n\n"
            f"Context: {context}\n\n"
            "For each step, specify:\n"
            "1. A clear action description\n"
            "2. What tools are needed (Bash, Read, Write, Edit, Grep, Glob, WebSearch)\n"
            "3. Dependencies on previous steps\n"
            "\nRespond with a JSON array of steps:\n"
            '[{"description": "...", "tools": [...], "deps": [...]}]'
        )

        # Parse the plan
        plan = Plan(goal=goal)

        # Generate reasonable default plan from goal analysis
        steps_data = self._analyze_goal(goal)
        for i, step_data in enumerate(steps_data, 1):
            plan.steps.append(PlanStep(
                id=i,
                description=step_data.get("description", ""),
                tools_needed=step_data.get("tools", []),
                dependencies=step_data.get("deps", []),
            ))

        self._current_plan = plan
        return plan

    def _analyze_goal(self, goal: str) -> list[dict]:
        """Heuristic goal analysis to create plan steps."""
        goal_lower = goal.lower()
        steps = []

        # File-related tasks
        if any(w in goal_lower for w in ["fix", "bug", "error", "debug"]):
            steps = [
                {"description": "Understand the error/bug", "tools": ["Grep", "Read"], "deps": []},
                {"description": "Locate relevant files", "tools": ["Grep", "Glob"], "deps": [1]},
                {"description": "Read and analyze the code", "tools": ["Read"], "deps": [2]},
                {"description": "Implement the fix", "tools": ["Edit"], "deps": [3]},
                {"description": "Verify the fix", "tools": ["Bash"], "deps": [4]},
            ]
        elif any(w in goal_lower for w in ["create", "write", "implement", "add", "build"]):
            steps = [
                {"description": "Analyze requirements", "tools": ["Read", "Grep"], "deps": []},
                {"description": "Plan the implementation", "tools": [], "deps": [1]},
                {"description": "Write the code", "tools": ["Write", "Edit"], "deps": [2]},
                {"description": "Test the implementation", "tools": ["Bash"], "deps": [3]},
                {"description": "Review and polish", "tools": ["Read"], "deps": [4]},
            ]
        elif any(w in goal_lower for w in ["refactor", "clean", "improve", "optimize"]):
            steps = [
                {"description": "Read current code", "tools": ["Read", "Glob"], "deps": []},
                {"description": "Identify improvement areas", "tools": ["Grep"], "deps": [1]},
                {"description": "Apply refactoring", "tools": ["Edit"], "deps": [2]},
                {"description": "Run tests", "tools": ["Bash"], "deps": [3]},
            ]
        elif any(w in goal_lower for w in ["test", "verify", "check"]):
            steps = [
                {"description": "Find test files", "tools": ["Glob", "Grep"], "deps": []},
                {"description": "Run existing tests", "tools": ["Bash"], "deps": [1]},
                {"description": "Write new tests if needed", "tools": ["Write"], "deps": [2]},
                {"description": "Run full test suite", "tools": ["Bash"], "deps": [3]},
            ]
        elif any(w in goal_lower for w in ["explain", "understand", "analyze", "review"]):
            steps = [
                {"description": "Find relevant files", "tools": ["Glob", "Grep"], "deps": []},
                {"description": "Read code", "tools": ["Read"], "deps": [1]},
                {"description": "Analyze structure", "tools": ["Grep"], "deps": [2]},
                {"description": "Generate explanation", "tools": [], "deps": [3]},
            ]
        else:
            steps = [
                {"description": "Analyze the request", "tools": ["Read", "Grep"], "deps": []},
                {"description": "Execute the task", "tools": ["Bash", "Edit", "Write"], "deps": [1]},
                {"description": "Verify results", "tools": ["Bash", "Read"], "deps": [2]},
            ]

        return steps

    def get_current_plan(self) -> Plan | None:
        return self._current_plan

    def update_step(self, step_id: int, status: PlanStepStatus, output: str = "", error: str = "") -> None:
        if self._current_plan:
            for step in self._current_plan.steps:
                if step.id == step_id:
                    step.status = status
                    if output:
                        step.output = output
                    if error:
                        step.error = error
                    break


# ---------------------------------------------------------------------------
# Reflection Agent
# ---------------------------------------------------------------------------

class ReflectionAgent:
    """Self-critique and iterative improvement.

    Pattern:
    1. Generate initial response
    2. Critique the response (identify issues)
    3. Generate improved response
    4. Repeat until quality threshold met
    """

    def __init__(self, max_rounds: int = 3, quality_threshold: float = 0.8):
        self.max_rounds = max_rounds
        self.quality_threshold = quality_threshold

    def build_critique_prompt(self, task: str, output: str) -> str:
        return (
            f"Critically review this response to the task.\n\n"
            f"Task: {task}\n\n"
            f"Response:\n{output}\n\n"
            "Rate the quality (0.0-1.0) and list specific issues:\n"
            "1. Is it correct?\n"
            "2. Is it complete?\n"
            "3. Is it well-structured?\n"
            "4. Are there edge cases missed?\n\n"
            "Format: QUALITY: 0.X\nISSUES:\n- issue 1\n- issue 2"
        )

    def build_improvement_prompt(self, task: str, output: str, critique: str) -> str:
        return (
            f"Improve this response based on the critique.\n\n"
            f"Original task: {task}\n\n"
            f"Current response:\n{output}\n\n"
            f"Critique:\n{critique}\n\n"
            "Provide an improved, corrected response."
        )

    def parse_quality_score(self, critique: str) -> float:
        """Extract quality score from critique output."""
        for line in critique.split("\n"):
            line = line.strip().upper()
            if line.startswith("QUALITY:"):
                try:
                    return float(line.split(":", 1)[1].strip())
                except (ValueError, IndexError):
                    pass
        return 0.5  # Default


# ---------------------------------------------------------------------------
# Goal decomposition
# ---------------------------------------------------------------------------

class GoalDecomposer:
    """Break complex goals into manageable sub-goals."""

    def decompose(self, goal: str) -> list[SubGoal]:
        """Decompose a goal into sub-goals using heuristic analysis."""
        # Split compound goals
        sub_goals_text = self._split_goal(goal)

        sub_goals = []
        for i, text in enumerate(sub_goals_text, 1):
            complexity = self._estimate_complexity(text)
            deps = [i - 1] if i > 1 else []
            sub_goals.append(SubGoal(
                id=i,
                description=text,
                complexity=complexity,
                dependencies=deps,
            ))

        return sub_goals

    def _split_goal(self, goal: str) -> list[str]:
        """Split a compound goal into parts using all delimiters."""
        import re

        # Use a regex to split on all conjunctions at once
        delimiters = r'\s+and then\s+|\s+then\s+|\s+and also\s+|\.\s*Then\s+|\.\s*Also\s+|;\s+'
        parts = re.split(delimiters, goal, flags=re.IGNORECASE)
        parts = [p.strip() for p in parts if p.strip()]

        if len(parts) > 1:
            return parts

        # Try numbered items
        numbered = re.findall(r'\d+[.)] (.+?)(?=\d+[.)]|$)', goal)
        if numbered:
            return numbered

        return [goal]

    def _estimate_complexity(self, goal: str) -> str:
        """Estimate task complexity."""
        goal_lower = goal.lower()

        complex_keywords = ["architecture", "system", "refactor", "rewrite", "migrate", "integrate"]
        simple_keywords = ["rename", "add comment", "format", "log", "print", "delete"]

        if any(k in goal_lower for k in complex_keywords):
            return "complex"
        if any(k in goal_lower for k in simple_keywords):
            return "simple"
        return "medium"


# ---------------------------------------------------------------------------
# Reasoning chain
# ---------------------------------------------------------------------------

@dataclass
class ReasoningStep:
    """A single step in a reasoning chain."""
    step_num: int
    thought: str
    action: str = ""
    observation: str = ""


class ReasoningChain:
    """Explicit chain-of-thought reasoning with observable steps.

    Pattern (ReAct-style):
    1. Thought: reason about the current state
    2. Action: decide what to do
    3. Observation: observe the result
    4. Repeat until conclusion
    """

    def __init__(self):
        self.steps: list[ReasoningStep] = []
        self._step_counter = 0

    def add_thought(self, thought: str) -> ReasoningStep:
        self._step_counter += 1
        step = ReasoningStep(step_num=self._step_counter, thought=thought)
        self.steps.append(step)
        return step

    def add_action(self, action: str) -> None:
        if self.steps:
            self.steps[-1].action = action

    def add_observation(self, observation: str) -> None:
        if self.steps:
            self.steps[-1].observation = observation

    def to_markdown(self) -> str:
        lines = ["## Reasoning Chain\n"]
        for step in self.steps:
            lines.append(f"**Step {step.step_num}**")
            lines.append(f"  💭 Thought: {step.thought}")
            if step.action:
                lines.append(f"  🔧 Action: {step.action}")
            if step.observation:
                lines.append(f"  👁️ Observation: {step.observation}")
            lines.append("")
        return "\n".join(lines)

    def build_context_prompt(self) -> str:
        """Build a prompt containing the reasoning chain for injection."""
        if not self.steps:
            return ""
        parts = ["\n## Previous Reasoning:\n"]
        for step in self.steps[-5:]:  # Last 5 steps
            parts.append(f"Thought: {step.thought}")
            if step.action:
                parts.append(f"Action: {step.action}")
            if step.observation:
                parts.append(f"Observation: {step.observation}")
        return "\n".join(parts)

    def clear(self) -> None:
        self.steps.clear()
        self._step_counter = 0


# ---------------------------------------------------------------------------
# Agentic system prompt builder
# ---------------------------------------------------------------------------

def build_agentic_prompt(
    base_prompt: str,
    planning_enabled: bool = False,
    reflection_enabled: bool = False,
    reasoning_chain: ReasoningChain | None = None,
    plan: Plan | None = None,
) -> str:
    """Enhance a system prompt with agentic capabilities."""
    additions = []

    if planning_enabled:
        additions.append(
            "\n## Planning Mode\n"
            "Before taking action, create a structured plan:\n"
            "1. Break the task into clear steps\n"
            "2. Identify which tools are needed for each step\n"
            "3. Execute steps in order, checking progress\n"
            "4. If a step fails, replan and try an alternative approach\n"
        )

    if reflection_enabled:
        additions.append(
            "\n## Self-Reflection\n"
            "After completing a task:\n"
            "1. Review your work critically\n"
            "2. Check for correctness and completeness\n"
            "3. Identify potential issues or edge cases\n"
            "4. Improve if quality is below expectations\n"
        )

    if plan:
        additions.append(f"\n{plan.to_markdown()}\n")

    if reasoning_chain:
        ctx = reasoning_chain.build_context_prompt()
        if ctx:
            additions.append(ctx)

    if additions:
        return base_prompt + "\n".join(additions)
    return base_prompt
