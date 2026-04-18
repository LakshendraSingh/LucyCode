"""
AutoDream — autonomous code exploration and improvement agent.

Runs in the background to:
  - Analyze codebase structure and identify issues
  - Run lint/test/typecheck and report findings
  - Generate "dream reports" with improvement suggestions
  - Operate within configurable budget caps
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

DREAMS_DIR = Path.home() / ".lucy" / "dreams"


@dataclass
class DreamConfig:
    """Configuration for AutoDream."""
    scope_dirs: list[str] = field(default_factory=list)
    scope_files: list[str] = field(default_factory=list)
    max_api_calls: int = 10
    max_cost_usd: float = 0.50
    run_lint: bool = True
    run_tests: bool = True
    run_typecheck: bool = True
    lint_command: str = ""
    test_command: str = ""
    typecheck_command: str = ""


@dataclass
class DreamFinding:
    """A finding from the dream analysis."""
    category: str  # "bug", "improvement", "refactor", "performance", "security"
    severity: str  # "info", "warning", "error", "critical"
    file: str
    line: int | None = None
    description: str = ""
    suggestion: str = ""


@dataclass
class DreamReport:
    """A complete dream report."""
    id: str = ""
    project: str = ""
    created_at: float = field(default_factory=time.time)
    elapsed_seconds: float = 0.0
    findings: list[DreamFinding] = field(default_factory=list)
    summary: str = ""
    lint_output: str = ""
    test_output: str = ""
    typecheck_output: str = ""
    api_calls: int = 0
    cost_usd: float = 0.0

    def to_markdown(self) -> str:
        """Render the report as Markdown."""
        lines = [
            f"# Dream Report — {self.id}",
            f"",
            f"**Project**: {self.project}",
            f"**Generated**: {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(self.created_at))}",
            f"**Duration**: {self.elapsed_seconds:.1f}s | **API calls**: {self.api_calls} | **Cost**: ${self.cost_usd:.4f}",
            f"",
            f"## Summary",
            f"",
            self.summary or "No summary available.",
            f"",
        ]

        if self.findings:
            lines.append(f"## Findings ({len(self.findings)})")
            lines.append("")

            by_severity = {"critical": [], "error": [], "warning": [], "info": []}
            for f in self.findings:
                by_severity.get(f.severity, by_severity["info"]).append(f)

            for severity in ["critical", "error", "warning", "info"]:
                findings = by_severity[severity]
                if not findings:
                    continue
                icon = {"critical": "🔴", "error": "🟠", "warning": "🟡", "info": "🔵"}[severity]
                lines.append(f"### {icon} {severity.title()} ({len(findings)})")
                lines.append("")
                for f in findings:
                    loc = f"{f.file}:{f.line}" if f.line else f.file
                    lines.append(f"- **[{f.category}]** `{loc}`: {f.description}")
                    if f.suggestion:
                        lines.append(f"  - 💡 {f.suggestion}")
                lines.append("")

        if self.lint_output:
            lines.extend(["## Lint Output", "", "```", self.lint_output[:2000], "```", ""])
        if self.test_output:
            lines.extend(["## Test Output", "", "```", self.test_output[:2000], "```", ""])
        if self.typecheck_output:
            lines.extend(["## Type Check Output", "", "```", self.typecheck_output[:2000], "```", ""])

        return "\n".join(lines)

    def save(self, path: Path | None = None) -> str:
        """Save report to disk."""
        DREAMS_DIR.mkdir(parents=True, exist_ok=True)
        filename = f"dream_{self.id}.md"
        filepath = (path or DREAMS_DIR) / filename
        filepath.write_text(self.to_markdown())
        return str(filepath)


class AutoDream:
    """Autonomous code exploration agent."""

    def __init__(self, project_root: str, config: DreamConfig | None = None):
        self.project_root = project_root
        self.config = config or DreamConfig()
        self._api_calls = 0
        self._cost = 0.0

    async def run(self) -> DreamReport:
        """Run a full dream analysis."""
        import uuid
        start_time = time.monotonic()

        report = DreamReport(
            id=uuid.uuid4().hex[:8],
            project=self.project_root,
        )

        # 1. Run static analysis tools
        if self.config.run_lint:
            report.lint_output = await self._run_command(
                self.config.lint_command or self._detect_lint_command()
            )

        if self.config.run_tests:
            report.test_output = await self._run_command(
                self.config.test_command or self._detect_test_command()
            )

        if self.config.run_typecheck:
            report.typecheck_output = await self._run_command(
                self.config.typecheck_command or self._detect_typecheck_command()
            )

        # 2. Analyze outputs for findings
        report.findings.extend(self._parse_lint_findings(report.lint_output))
        report.findings.extend(self._parse_test_findings(report.test_output))

        # 3. Scan for common issues
        report.findings.extend(await self._scan_common_issues())

        # 4. Generate summary
        report.summary = self._generate_summary(report)

        report.elapsed_seconds = time.monotonic() - start_time
        report.api_calls = self._api_calls
        report.cost_usd = self._cost

        # Save report
        filepath = report.save()
        logger.info("Dream report saved: %s", filepath)

        return report

    async def _run_command(self, command: str) -> str:
        """Run a shell command and capture output."""
        if not command:
            return ""
        try:
            proc = await asyncio.create_subprocess_shell(
                command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
                cwd=self.project_root,
            )
            stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=120)
            return stdout.decode("utf-8", errors="replace")
        except asyncio.TimeoutError:
            return "(command timed out)"
        except Exception as e:
            return f"(error: {e})"

    def _detect_lint_command(self) -> str:
        """Auto-detect the lint command."""
        root = Path(self.project_root)
        if (root / "pyproject.toml").exists() or (root / "setup.py").exists():
            return "python3 -m flake8 --max-line-length=100 . 2>&1 || true"
        if (root / "package.json").exists():
            return "npx eslint . 2>&1 || true"
        return ""

    def _detect_test_command(self) -> str:
        root = Path(self.project_root)
        if (root / "pyproject.toml").exists():
            return "python3 -m pytest --tb=short -q 2>&1 || true"
        if (root / "package.json").exists():
            return "npm test 2>&1 || true"
        return ""

    def _detect_typecheck_command(self) -> str:
        root = Path(self.project_root)
        if (root / "pyproject.toml").exists():
            return "python3 -m mypy . --ignore-missing-imports 2>&1 || true"
        if (root / "tsconfig.json").exists():
            return "npx tsc --noEmit 2>&1 || true"
        return ""

    def _parse_lint_findings(self, output: str) -> list[DreamFinding]:
        """Parse lint output into findings."""
        findings = []
        for line in output.split("\n"):
            line = line.strip()
            if not line:
                continue
            # Common format: path:line:col: code message
            parts = line.split(":", 3)
            if len(parts) >= 4:
                try:
                    findings.append(DreamFinding(
                        category="lint",
                        severity="warning",
                        file=parts[0].strip(),
                        line=int(parts[1].strip()),
                        description=parts[3].strip(),
                    ))
                except (ValueError, IndexError):
                    pass
        return findings[:50]

    def _parse_test_findings(self, output: str) -> list[DreamFinding]:
        """Parse test output into findings."""
        findings = []
        if "FAILED" in output or "ERRORS" in output:
            findings.append(DreamFinding(
                category="test",
                severity="error",
                file="tests",
                description="Some tests are failing",
                suggestion="Run the test suite and fix failing tests",
            ))
        return findings

    async def _scan_common_issues(self) -> list[DreamFinding]:
        """Scan for common code issues."""
        findings = []
        root = Path(self.project_root)

        for py_file in root.rglob("*.py"):
            if any(p in py_file.parts for p in [".git", "__pycache__", "venv", ".venv", "node_modules"]):
                continue
            try:
                content = py_file.read_text(errors="ignore")
            except Exception:
                continue

            # TODO comments
            for i, line in enumerate(content.split("\n"), 1):
                if "TODO" in line and not line.strip().startswith("#"):
                    continue
                if "# TODO" in line or "# FIXME" in line or "# HACK" in line:
                    findings.append(DreamFinding(
                        category="improvement",
                        severity="info",
                        file=str(py_file.relative_to(root)),
                        line=i,
                        description=line.strip(),
                    ))

            # Large files
            lines = content.count("\n")
            if lines > 500:
                findings.append(DreamFinding(
                    category="refactor",
                    severity="info",
                    file=str(py_file.relative_to(root)),
                    description=f"Large file ({lines} lines) — consider splitting",
                ))

            # Import *
            if "from " in content and "import *" in content:
                findings.append(DreamFinding(
                    category="improvement",
                    severity="warning",
                    file=str(py_file.relative_to(root)),
                    description="Wildcard import detected",
                    suggestion="Use explicit imports for clarity",
                ))

        return findings[:100]

    def _generate_summary(self, report: DreamReport) -> str:
        """Generate a text summary of findings."""
        total = len(report.findings)
        by_severity = {}
        for f in report.findings:
            by_severity[f.severity] = by_severity.get(f.severity, 0) + 1

        parts = [f"Found {total} issues:"]
        for sev in ["critical", "error", "warning", "info"]:
            if sev in by_severity:
                parts.append(f"  {sev}: {by_severity[sev]}")
        return "\n".join(parts)


def list_dream_reports() -> list[dict[str, str]]:
    """List saved dream reports."""
    if not DREAMS_DIR.exists():
        return []
    reports = []
    for f in sorted(DREAMS_DIR.glob("dream_*.md"), reverse=True):
        reports.append({"file": str(f), "name": f.stem})
    return reports[:20]
