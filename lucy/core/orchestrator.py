"""
Multi-agent orchestrator — parallel, pipeline, and debate patterns.

Manages concurrent agent execution with isolated contexts, shared
result aggregation, inter-agent communication, and cost tracking.
"""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
import os
import json
import subprocess
import tempfile
from typing import Any, AsyncGenerator, Callable

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Agent specification
# ---------------------------------------------------------------------------

class AgentRole(str, Enum):
    CODER = "coder"
    RESEARCHER = "researcher"
    REVIEWER = "reviewer"
    TESTER = "tester"
    PLANNER = "planner"
    ARCHITECT = "architect"
    DEBUGGER = "debugger"
    CUSTOM = "custom"


@dataclass
class AgentSpec:
    """Specification for an agent to be orchestrated."""
    task: str
    role: AgentRole = AgentRole.CUSTOM
    name: str = ""
    model: str | None = None          # Override model
    allowed_tools: list[str] | None = None  # Restrict tools
    max_turns: int = 30
    working_directory: str | None = None
    system_prompt_extra: str = ""      # Appended to system prompt
    context: dict[str, Any] = field(default_factory=dict)  # Shared context

    def __post_init__(self):
        if not self.name:
            self.name = f"{self.role.value}_{uuid.uuid4().hex[:6]}"


@dataclass
class AgentResult:
    """Result from a completed agent."""
    agent_name: str
    role: AgentRole
    task: str
    output: str
    turn_count: int = 0
    cost: float = 0.0
    elapsed_seconds: float = 0.0
    success: bool = True
    error: str | None = None


# ---------------------------------------------------------------------------
# Agent execution
# ---------------------------------------------------------------------------

async def _run_single_agent(
    spec: AgentSpec,
    parent_cwd: str,
    permission_mode: str = "auto_accept",
    ask_permission: Any = None,
    on_progress: Callable[[str, str], None] | None = None,
) -> AgentResult:
    """Run a single agent with the given spec."""
    from lucy.core.context import build_system_prompt, get_lucymd_content, get_git_status
    from lucy.core.message import AssistantMessage, StreamEvent, UserMessage, create_user_message
    from lucy.core.query import QueryParams, query_loop
    from lucy.core.tool import ToolContext, ToolRegistry, get_tool_registry
    
    # Check for external teammate mode
    mode = os.environ.get("LUCY_TEAMMATE_MODE", "in-process")
    if mode in ("terminal", "tmux") and not os.environ.get("LUCY_IS_WORKER"):
        return await _run_external_agent(spec, mode)

    start_time = time.monotonic()
    cwd = spec.working_directory or parent_cwd

    # Build context
    git_status = await get_git_status(cwd)
    lucymd = get_lucymd_content(cwd)

    role_instruction = ""
    if spec.role != AgentRole.CUSTOM:
        role_instruction = f"\n\nYou are acting as a {spec.role.value}. "
        role_instructions = {
            AgentRole.CODER: "Focus on writing clean, working code. Implement features and fix bugs.",
            AgentRole.RESEARCHER: "Focus on research and analysis. Read files, search, and gather information.",
            AgentRole.REVIEWER: "Focus on code review. Find bugs, suggest improvements, check quality.",
            AgentRole.TESTER: "Focus on testing. Write tests, run test suites, verify correctness.",
            AgentRole.PLANNER: "Focus on planning. Break down tasks, identify dependencies, create plans.",
            AgentRole.ARCHITECT: "Focus on architecture. Design systems, define interfaces, plan structure.",
            AgentRole.DEBUGGER: "Focus on debugging. Trace errors, find root causes, fix issues.",
        }
        role_instruction += role_instructions.get(spec.role, "")

    system_prompt = build_system_prompt(
        cwd=cwd, git_status=git_status, lucymd=lucymd,
    )
    if role_instruction:
        system_prompt += role_instruction
    if spec.system_prompt_extra:
        system_prompt += f"\n\n{spec.system_prompt_extra}"

    # Context injection
    context_text = ""
    if spec.context:
        context_text = "\n\nShared context from parent agent:\n"
        for k, v in spec.context.items():
            context_text += f"- {k}: {v}\n"

    # Build tool registry (filtered if needed)
    full_registry = get_tool_registry()
    if spec.allowed_tools:
        registry = ToolRegistry()
        for tool in full_registry.get_all():
            if tool.name in spec.allowed_tools or any(
                a in spec.allowed_tools for a in tool.aliases
            ):
                registry.register(tool)
    else:
        registry = full_registry

    tool_context = ToolContext(
        cwd=cwd,
        permission_mode=permission_mode,
        is_interactive=False,
        ask_permission=ask_permission,
    )

    user_msg = create_user_message(
        f"Complete this task:\n\n{spec.task}{context_text}\n\n"
        "Work step by step. When done, provide a clear summary."
    )

    abort_event = asyncio.Event()
    params = QueryParams(
        messages=[user_msg],
        system_prompt=system_prompt,
        tools=registry,
        tool_context=tool_context,
        model=spec.model,
        max_turns=spec.max_turns,
        abort_event=abort_event,
    )

    result_text = ""
    turn_count = 0

    try:
        async for event in query_loop(params):
            if isinstance(event, AssistantMessage):
                text = event.get_text()
                if text:
                    result_text = text
                turn_count += 1
                if on_progress:
                    on_progress(spec.name, f"Turn {turn_count}")
            elif isinstance(event, StreamEvent):
                pass

        elapsed = time.monotonic() - start_time
        return AgentResult(
            agent_name=spec.name,
            role=spec.role,
            task=spec.task,
            output=result_text or "(no output)",
            turn_count=turn_count,
            elapsed_seconds=elapsed,
        )

    except Exception as e:
        elapsed = time.monotonic() - start_time
        return AgentResult(
            agent_name=spec.name,
            role=spec.role,
            task=spec.task,
            output="",
            turn_count=turn_count,
            elapsed_seconds=elapsed,
            success=False,
            error=str(e),
        )
    

async def _run_external_agent(spec: AgentSpec, mode: str) -> AgentResult:
    """Run an agent in an external terminal window or tmux pane."""
    import sys
    
    with tempfile.TemporaryDirectory() as tmpdir:
        spec_path = os.path.join(tmpdir, "spec.json")
        out_path = os.path.join(tmpdir, "result.json")
        
        # Serialize spec
        spec_dict = {
            "task": spec.task,
            "role": spec.role.value if hasattr(spec.role, 'value') else spec.role,
            "name": spec.name,
            "model": spec.model,
            "allowed_tools": spec.allowed_tools,
            "max_turns": spec.max_turns,
            "working_directory": spec.working_directory,
            "system_prompt_extra": spec.system_prompt_extra,
            "context": spec.context,
        }
        with open(spec_path, 'w') as f:
            json.dump(spec_dict, f)
            
        # Build command
        # Use full path if we can find it to be safer
        python_exe = sys.executable
        # Try to find the lucy script entry point
        cmd_args = f"--worker-spec {spec_path} --worker-out {out_path}"
        full_cmd = f"{python_exe} -m lucy.main {cmd_args}"
        
        env = os.environ.copy()
        env["LUCY_IS_WORKER"] = "1"
        
        try:
            if mode == "tmux":
                subprocess.run(["tmux", "split-window", "-h", f"export LUCY_IS_WORKER=1; {full_cmd}"], check=True)
            elif mode == "terminal":
                if sys.platform == "darwin": # macOS
                    osascript = f'tell application "Terminal" to do script "{full_cmd}"'
                    subprocess.run(["osascript", "-e", osascript], check=True)
                elif sys.platform == "win32": # Windows
                    subprocess.run(["start", "cmd", "/c", full_cmd], shell=True, check=True)
                else: # Linux
                    # Try common terminal emulators
                    terminals = ["x-terminal-emulator", "gnome-terminal", "konsole", "xfce4-terminal"]
                    spawned = False
                    for term in terminals:
                        try:
                            if term == "gnome-terminal":
                                subprocess.run([term, "--", "bash", "-c", full_cmd], check=True)
                            else:
                                subprocess.run([term, "-e", full_cmd], check=True)
                            spawned = True
                            break
                        except FileNotFoundError:
                            continue
                    if not spawned:
                        raise RuntimeError("No suitable terminal emulator found")
            
            # Poll for result
            start_wait = time.monotonic()
            while time.monotonic() - start_wait < 600: # 10 minute timeout
                if os.path.exists(out_path):
                    with open(out_path, 'r') as f:
                        res_data = json.load(f)
                    
                    return AgentResult(
                        agent_name=res_data.get("agent_name", spec.name),
                        role=res_data.get("role", spec.role),
                        task=res_data.get("task", spec.task),
                        output=res_data.get("output", ""),
                        turn_count=res_data.get("turn_count", 0),
                        elapsed_seconds=res_data.get("elapsed_seconds", 0.0),
                        success=res_data.get("success", True),
                        error=res_data.get("error"),
                    )
                await asyncio.sleep(1)
                
            return AgentResult(
                agent_name=spec.name,
                role=spec.role,
                task=spec.task,
                output="",
                success=False,
                error="External agent timed out"
            )
            
        except Exception as e:
            return AgentResult(
                agent_name=spec.name,
                role=spec.role,
                task=spec.task,
                output="",
                success=False,
                error=f"Failed to spawn external agent: {e}"
            )


# ---------------------------------------------------------------------------
# Orchestration patterns
# ---------------------------------------------------------------------------

class Orchestrator:
    """Multi-agent orchestrator with parallel, pipeline, and debate patterns."""

    def __init__(
        self,
        cwd: str = "",
        permission_mode: str = "auto_accept",
        ask_permission: Any = None,
    ):
        self.cwd = cwd
        self.permission_mode = permission_mode
        self.ask_permission = ask_permission
        self._progress: list[tuple[str, str]] = []

    def _on_progress(self, agent_name: str, msg: str) -> None:
        self._progress.append((agent_name, msg))

    async def run_parallel(self, specs: list[AgentSpec]) -> list[AgentResult]:
        """Run multiple agents in parallel and collect results."""
        tasks = [
            _run_single_agent(
                spec, self.cwd, self.permission_mode,
                self.ask_permission, self._on_progress,
            )
            for spec in specs
        ]
        return list(await asyncio.gather(*tasks, return_exceptions=False))

    async def run_pipeline(self, specs: list[AgentSpec]) -> list[AgentResult]:
        """Run agents sequentially, passing output as context to the next."""
        results: list[AgentResult] = []
        prev_output = ""

        for i, spec in enumerate(specs):
            if prev_output:
                spec.context["previous_agent_output"] = prev_output
                spec.context["pipeline_step"] = f"{i + 1}/{len(specs)}"

            result = await _run_single_agent(
                spec, self.cwd, self.permission_mode,
                self.ask_permission, self._on_progress,
            )
            results.append(result)
            prev_output = result.output

            if not result.success:
                break  # Stop pipeline on failure

        return results

    async def run_debate(
        self,
        specs: list[AgentSpec],
        rounds: int = 3,
        judge_spec: AgentSpec | None = None,
    ) -> list[AgentResult]:
        """Run agents in debate mode — each critiques the other's work.

        If judge_spec is provided, a judge agent picks the best solution.
        """
        if len(specs) < 2:
            return await self.run_parallel(specs)

        all_results: list[AgentResult] = []

        # Initial round — both work independently
        first_round = await self.run_parallel(specs)
        all_results.extend(first_round)

        # Debate rounds
        for round_num in range(1, rounds):
            debate_specs = []
            for i, spec in enumerate(specs):
                other_idx = (i + 1) % len(specs)
                other_output = all_results[-len(specs) + other_idx].output

                new_spec = AgentSpec(
                    task=(
                        f"Review and improve upon this solution:\n\n"
                        f"---\n{other_output}\n---\n\n"
                        f"Original task: {spec.task}\n\n"
                        f"Provide an improved solution. This is debate round {round_num + 1}/{rounds}."
                    ),
                    role=spec.role,
                    name=f"{spec.name}_r{round_num + 1}",
                    model=spec.model,
                    allowed_tools=spec.allowed_tools,
                    max_turns=spec.max_turns,
                    working_directory=spec.working_directory,
                )
                debate_specs.append(new_spec)

            round_results = await self.run_parallel(debate_specs)
            all_results.extend(round_results)

        # Judge (optional)
        if judge_spec:
            final_outputs = all_results[-len(specs):]
            solutions = "\n\n---\n\n".join(
                f"**{r.agent_name}**:\n{r.output}" for r in final_outputs
            )
            judge_spec.task = (
                f"Judge these solutions and pick the best one. Explain why.\n\n"
                f"Original task: {specs[0].task}\n\n"
                f"Solutions:\n{solutions}"
            )
            judge_result = await _run_single_agent(
                judge_spec, self.cwd, self.permission_mode,
                self.ask_permission, self._on_progress,
            )
            all_results.append(judge_result)

        return all_results

    async def run_map_reduce(
        self,
        items: list[str],
        map_spec: AgentSpec,
        reduce_spec: AgentSpec,
    ) -> list[AgentResult]:
        """Map-reduce: apply map_spec to each item, then reduce."""
        # Map phase
        map_specs = []
        for item in items:
            spec = AgentSpec(
                task=f"{map_spec.task}\n\nInput item:\n{item}",
                role=map_spec.role,
                name=f"map_{uuid.uuid4().hex[:6]}",
                model=map_spec.model,
                allowed_tools=map_spec.allowed_tools,
                max_turns=map_spec.max_turns,
            )
            map_specs.append(spec)

        map_results = await self.run_parallel(map_specs)

        # Reduce phase
        mapped_outputs = "\n\n---\n\n".join(
            f"Result {i+1}: {r.output}" for i, r in enumerate(map_results)
        )
        reduce_spec.context["mapped_results"] = mapped_outputs
        reduce_result = await _run_single_agent(
            reduce_spec, self.cwd, self.permission_mode,
            self.ask_permission, self._on_progress,
        )

        return [*map_results, reduce_result]

    def format_results(self, results: list[AgentResult]) -> str:
        """Format agent results for display."""
        lines = [f"Orchestration complete ({len(results)} agents):\n"]
        total_cost = 0.0
        total_time = 0.0

        for r in results:
            status = "✓" if r.success else "✗"
            lines.append(
                f"  {status} {r.agent_name} ({r.role.value}) — "
                f"{r.turn_count} turns, {r.elapsed_seconds:.1f}s"
            )
            if r.error:
                lines.append(f"    Error: {r.error}")
            else:
                preview = r.output[:200].replace("\n", " ")
                lines.append(f"    {preview}...")
            total_cost += r.cost
            total_time += r.elapsed_seconds

        lines.append(f"\n  Total: {total_time:.1f}s")
        return "\n".join(lines)
