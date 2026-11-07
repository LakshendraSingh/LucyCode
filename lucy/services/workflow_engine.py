"""
Persistent workflow automation engine for LucyCode.

Allows creating, saving, scheduling, and executing multi-step desktop and workstation
workflows with rollback, error handling, step-by-step streaming, and disk persistence.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import subprocess
import time
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, AsyncGenerator

logger = logging.getLogger(__name__)


@dataclass
class WorkflowStep:
    """A single atomic automation step."""
    id: str
    type: str  # bash, open_app, type_text, screenshot, wait, notify, clipboard_set, open_url, write_file, applescript
    params: dict[str, Any]
    description: str
    timeout: float = 30.0
    on_error: str = "stop"  # stop, skip, retry

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> WorkflowStep:
        return cls(
            id=data.get("id", str(uuid.uuid4())[:8]),
            type=data.get("type", "bash"),
            params=data.get("params", {}),
            description=data.get("description", ""),
            timeout=float(data.get("timeout", 30.0)),
            on_error=data.get("on_error", "stop"),
        )


@dataclass
class WorkflowResult:
    """Execution output of a single step."""
    step_id: str
    success: bool
    output: str
    duration_seconds: float
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class Workflow:
    """Named sequence of automation steps."""
    id: str
    name: str
    description: str
    steps: list[WorkflowStep] = field(default_factory=list)
    created_at: float = field(default_factory=time.time)
    tags: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "steps": [s.to_dict() for s in self.steps],
            "created_at": self.created_at,
            "tags": self.tags,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Workflow:
        return cls(
            id=data.get("id", str(uuid.uuid4())[:8]),
            name=data.get("name", "Unnamed Workflow"),
            description=data.get("description", ""),
            steps=[WorkflowStep.from_dict(s) for s in data.get("steps", [])],
            created_at=data.get("created_at", time.time()),
            tags=data.get("tags", []),
        )


@dataclass
class WorkflowRun:
    """Historical or active run instance of a workflow."""
    id: str
    workflow_id: str
    started_at: float
    finished_at: float | None = None
    status: str = "running"  # running, completed, failed, cancelled
    results: list[WorkflowResult] = field(default_factory=list)
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "workflow_id": self.workflow_id,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "status": self.status,
            "results": [r.to_dict() for r in self.results],
            "error": self.error,
        }


class WorkflowEngine:
    """Manages saving, loading, and async streaming execution of workflows."""

    def __init__(self, storage_dir: Path | None = None) -> None:
        self.storage_dir = storage_dir or (Path.home() / ".lucycode" / "workflows")
        self.runs_dir = self.storage_dir / "runs"
        self._active_runs: dict[str, WorkflowRun] = {}
        self._cancellation_tokens: set[str] = set()

        try:
            self.storage_dir.mkdir(parents=True, exist_ok=True)
            self.runs_dir.mkdir(parents=True, exist_ok=True)
        except (PermissionError, OSError) as e:
            logger.debug("Failed creating storage_dir %s: %s, falling back to /tmp/lucycode_workflows", self.storage_dir, e)
            self.storage_dir = Path("/tmp/lucycode_workflows")
            self.runs_dir = self.storage_dir / "runs"
            self.storage_dir.mkdir(parents=True, exist_ok=True)
            self.runs_dir.mkdir(parents=True, exist_ok=True)

    def create_workflow(self, name: str, description: str = "", tags: list[str] | None = None) -> Workflow:
        """Create and persist a new empty workflow."""
        wf = Workflow(
            id=str(uuid.uuid4())[:8],
            name=name,
            description=description,
            tags=tags or [],
        )
        self.save_workflow(wf)
        return wf

    def save_workflow(self, wf: Workflow) -> None:
        """Serialize workflow to disk."""
        target = self.storage_dir / f"{wf.id}.json"
        with open(target, "w", encoding="utf-8") as f:
            json.dump(wf.to_dict(), f, indent=2)

    def load_workflow(self, workflow_id: str) -> Workflow | None:
        """Read workflow by id from disk."""
        target = self.storage_dir / f"{workflow_id}.json"
        if not target.exists():
            return None
        try:
            with open(target, "r", encoding="utf-8") as f:
                data = json.load(f)
            return Workflow.from_dict(data)
        except Exception as e:
            logger.error("Failed to load workflow %s: %s", workflow_id, e)
            return None

    def list_workflows(self) -> list[Workflow]:
        """Return all persisted workflows."""
        results: list[Workflow] = []
        for file in self.storage_dir.glob("*.json"):
            try:
                with open(file, "r", encoding="utf-8") as f:
                    results.append(Workflow.from_dict(json.load(f)))
            except Exception:
                continue
        return sorted(results, key=lambda w: w.created_at, reverse=True)

    def delete_workflow(self, workflow_id: str) -> bool:
        """Delete workflow file from disk."""
        target = self.storage_dir / f"{workflow_id}.json"
        if target.exists():
            target.unlink()
            return True
        return False

    def add_step(
        self,
        workflow_id: str,
        type: str,
        params: dict[str, Any],
        description: str = "",
        timeout: float = 30.0,
        on_error: str = "stop",
    ) -> WorkflowStep | None:
        """Add a step to an existing workflow and persist."""
        wf = self.load_workflow(workflow_id)
        if not wf:
            return None
        step = WorkflowStep(
            id=f"step_{len(wf.steps) + 1}",
            type=type,
            params=params,
            description=description or f"Run {type}",
            timeout=timeout,
            on_error=on_error,
        )
        wf.steps.append(step)
        self.save_workflow(wf)
        return step

    async def execute(
        self,
        workflow_id: str,
        context: dict[str, Any] | None = None,
    ) -> AsyncGenerator[WorkflowRun, None]:
        """
        Execute workflow steps sequentially, streaming updated WorkflowRun instances.
        """
        wf = self.load_workflow(workflow_id)
        if not wf:
            raise ValueError(f"Workflow '{workflow_id}' not found")

        run = WorkflowRun(
            id=str(uuid.uuid4())[:8],
            workflow_id=wf.id,
            started_at=time.time(),
            status="running",
        )
        self._active_runs[run.id] = run
        yield run

        for step in wf.steps:
            if run.id in self._cancellation_tokens:
                run.status = "cancelled"
                run.finished_at = time.time()
                self._save_run(run)
                yield run
                return

            t0 = time.time()
            step_res = await self._execute_step(step, context or {})
            step_res.duration_seconds = time.time() - t0
            run.results.append(step_res)

            if not step_res.success:
                if step.on_error == "stop":
                    run.status = "failed"
                    run.error = f"Step '{step.description}' failed: {step_res.error}"
                    run.finished_at = time.time()
                    self._save_run(run)
                    yield run
                    return
                elif step.on_error == "retry":
                    # Single retry attempt
                    t1 = time.time()
                    retry_res = await self._execute_step(step, context or {})
                    retry_res.duration_seconds = time.time() - t1
                    run.results[-1] = retry_res
                    if not retry_res.success:
                        run.status = "failed"
                        run.error = f"Step '{step.description}' failed on retry: {retry_res.error}"
                        run.finished_at = time.time()
                        self._save_run(run)
                        yield run
                        return

            yield run

        run.status = "completed"
        run.finished_at = time.time()
        self._save_run(run)
        yield run

    async def _execute_step(self, step: WorkflowStep, context: dict[str, Any]) -> WorkflowResult:
        """Dispatch single step according to type."""
        try:
            if step.type == "bash":
                cmd = step.params.get("command", "")
                proc = await asyncio.create_subprocess_shell(
                    cmd,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                try:
                    stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=step.timeout)
                    out = stdout.decode(errors="ignore") + stderr.decode(errors="ignore")
                    return WorkflowResult(
                        step_id=step.id,
                        success=(proc.returncode == 0),
                        output=out.strip(),
                        duration_seconds=0.0,
                        error=None if proc.returncode == 0 else f"Exit code {proc.returncode}",
                    )
                except asyncio.TimeoutError:
                    proc.kill()
                    return WorkflowResult(
                        step_id=step.id,
                        success=False,
                        output="",
                        duration_seconds=step.timeout,
                        error=f"Timeout after {step.timeout}s",
                    )

            elif step.type == "open_app":
                from lucy.services.app_automation import get_app_automation
                app_name = step.params.get("app", "")
                ok = get_app_automation().launch_app(app_name)
                return WorkflowResult(step_id=step.id, success=ok, output=f"Launched {app_name}", duration_seconds=0.0)

            elif step.type == "open_url":
                from lucy.services.browser_automation import get_browser_automation
                url = step.params.get("url", "")
                res = await get_browser_automation().open_url(url)
                return WorkflowResult(step_id=step.id, success=res.success, output=res.output, duration_seconds=0.0)

            elif step.type == "notify":
                from lucy.services.app_automation import get_app_automation
                title = step.params.get("title", "LucyCode")
                msg = step.params.get("message", "")
                res = get_app_automation().send_notification(title, msg)
                return WorkflowResult(step_id=step.id, success=res.sent, output=f"Notified: {title}", duration_seconds=0.0)

            elif step.type == "clipboard_set":
                from lucy.services.app_automation import get_app_automation
                text = step.params.get("text", "")
                ok = get_app_automation().set_clipboard(text)
                return WorkflowResult(step_id=step.id, success=ok, output=f"Copied {len(text)} chars to clipboard", duration_seconds=0.0)

            elif step.type == "wait":
                secs = float(step.params.get("seconds", 1.0))
                await asyncio.sleep(secs)
                return WorkflowResult(step_id=step.id, success=True, output=f"Waited {secs}s", duration_seconds=secs)

            elif step.type == "screenshot":
                from lucy.services.screen_automation import get_screen_automation
                out_path = step.params.get("path", f"/tmp/lucy_wf_{int(time.time())}.png")
                b64 = get_screen_automation().screenshot()
                with open(out_path, "wb") as f:
                    f.write(base64.b64decode(b64))
                return WorkflowResult(step_id=step.id, success=True, output=f"Saved screenshot to {out_path}", duration_seconds=0.0)

            elif step.type == "write_file":
                p = step.params.get("path", "")
                content = step.params.get("content", "")
                with open(p, "w", encoding="utf-8") as f:
                    f.write(content)
                return WorkflowResult(step_id=step.id, success=True, output=f"Wrote {len(content)} chars to {p}", duration_seconds=0.0)

            elif step.type == "applescript":
                from lucy.services.app_automation import get_app_automation
                script = step.params.get("script", "")
                ok, out = get_app_automation().run_applescript(script)
                return WorkflowResult(step_id=step.id, success=ok, output=out, duration_seconds=0.0)

            elif step.type == "type_text":
                from lucy.services.computer_use import get_computer_use_service
                text = step.params.get("text", "")
                get_computer_use_service().type_text(text)
                return WorkflowResult(step_id=step.id, success=True, output=f"Typed {len(text)} chars", duration_seconds=0.0)

            else:
                return WorkflowResult(step_id=step.id, success=False, output="", duration_seconds=0.0, error=f"Unknown step type: {step.type}")

        except Exception as e:
            return WorkflowResult(step_id=step.id, success=False, output="", duration_seconds=0.0, error=str(e))

    def cancel_run(self, run_id: str) -> bool:
        """Signal cancellation for a running workflow."""
        if run_id in self._active_runs:
            self._cancellation_tokens.add(run_id)
            return True
        return False

    def get_run(self, run_id: str) -> WorkflowRun | None:
        """Lookup active or persisted run."""
        if run_id in self._active_runs:
            return self._active_runs[run_id]
        run_file = self.runs_dir / f"{run_id}.json"
        if run_file.exists():
            try:
                with open(run_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                return WorkflowRun(
                    id=data["id"],
                    workflow_id=data["workflow_id"],
                    started_at=data["started_at"],
                    finished_at=data.get("finished_at"),
                    status=data.get("status", "completed"),
                    results=[WorkflowResult(**r) for r in data.get("results", [])],
                    error=data.get("error"),
                )
            except Exception:
                pass
        return None

    def list_runs(self, workflow_id: str | None = None) -> list[WorkflowRun]:
        """List historical workflow runs."""
        runs: list[WorkflowRun] = []
        for file in self.runs_dir.glob("*.json"):
            try:
                with open(file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                if workflow_id and data.get("workflow_id") != workflow_id:
                    continue
                runs.append(
                    WorkflowRun(
                        id=data["id"],
                        workflow_id=data["workflow_id"],
                        started_at=data["started_at"],
                        finished_at=data.get("finished_at"),
                        status=data.get("status", "completed"),
                        results=[WorkflowResult(**r) for r in data.get("results", [])],
                        error=data.get("error"),
                    )
                )
            except Exception:
                continue
        return sorted(runs, key=lambda r: r.started_at, reverse=True)

    def _save_run(self, run: WorkflowRun) -> None:
        """Write completed/stopped run record to disk."""
        run_file = self.runs_dir / f"{run.id}.json"
        try:
            with open(run_file, "w", encoding="utf-8") as f:
                json.dump(run.to_dict(), f, indent=2)
        except Exception as e:
            logger.error("Failed to save run %s: %s", run.id, e)


_workflow_engine: WorkflowEngine | None = None


def get_workflow_engine() -> WorkflowEngine:
    global _workflow_engine
    if _workflow_engine is None:
        _workflow_engine = WorkflowEngine()
    return _workflow_engine
