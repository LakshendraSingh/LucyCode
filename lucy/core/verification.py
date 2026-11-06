"""
Self-verification engine — validates code changes automatically.

Strategies:
1. Test runner: detect and run project tests (pytest, jest, go test, cargo test, etc.)
2. Type checker: mypy, pyright, tsc
3. Linter: ruff, eslint, clippy
4. Build check: make, cargo build, go build
5. Custom checks: from LUCY.md or project config
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import shutil
import sys
import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Project Types and Strategies
# ---------------------------------------------------------------------------

class ProjectType(str, Enum):
    """Supported project types for verification."""
    PYTHON = "python"
    JAVASCRIPT = "javascript"
    TYPESCRIPT = "typescript"
    GO = "go"
    RUST = "rust"
    JAVA = "java"
    CPP = "cpp"
    UNKNOWN = "unknown"


class VerificationStrategy(str, Enum):
    """Strategies for verifying code changes."""
    TEST = "test"
    TYPECHECK = "typecheck"
    LINT = "lint"
    BUILD = "build"
    CUSTOM = "custom"


# ---------------------------------------------------------------------------
# Verification Result
# ---------------------------------------------------------------------------

@dataclass
class VerificationResult:
    """Outcome of a verification check."""
    strategy: str  # "test", "typecheck", "lint", "build", "custom"
    passed: bool
    output: str
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    duration_seconds: float = 0.0
    command: str = ""

    def to_dict(self) -> dict[str, Any]:
        """Convert result to dictionary for serialization."""
        return {
            "strategy": self.strategy,
            "passed": self.passed,
            "output": self.output,
            "errors": list(self.errors),
            "warnings": list(self.warnings),
            "duration_seconds": round(self.duration_seconds, 3),
            "command": self.command,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> VerificationResult:
        """Create result from serialized dictionary."""
        return cls(
            strategy=data.get("strategy", "custom"),
            passed=bool(data.get("passed", False)),
            output=data.get("output", ""),
            errors=list(data.get("errors", [])),
            warnings=list(data.get("warnings", [])),
            duration_seconds=float(data.get("duration_seconds", 0.0)),
            command=data.get("command", ""),
        )


# ---------------------------------------------------------------------------
# Verification Engine
# ---------------------------------------------------------------------------

class VerificationEngine:
    """Runs automated verification checks on code changes."""

    def __init__(self, timeout_seconds: float = 120.0) -> None:
        self.timeout_seconds = timeout_seconds

    async def detect_project_type(self, cwd: str) -> ProjectType:
        """Auto-detect project type from files in current directory or parents."""
        cur = Path(cwd).resolve()

        # Check directory tree upward up to 3 levels
        for _ in range(4):
            if (cur / "Cargo.toml").is_file():
                return ProjectType.RUST
            if (cur / "go.mod").is_file():
                return ProjectType.GO
            if (cur / "tsconfig.json").is_file():
                return ProjectType.TYPESCRIPT
            if (cur / "package.json").is_file():
                try:
                    pkg_text = (cur / "package.json").read_text(encoding="utf-8")
                    pkg_data = json.loads(pkg_text)
                    deps = {**pkg_data.get("dependencies", {}), **pkg_data.get("devDependencies", {})}
                    if "typescript" in deps:
                        return ProjectType.TYPESCRIPT
                except Exception:
                    pass
                return ProjectType.JAVASCRIPT
            if (
                (cur / "pyproject.toml").is_file()
                or (cur / "setup.py").is_file()
                or (cur / "requirements.txt").is_file()
                or (cur / "Pipfile").is_file()
            ):
                return ProjectType.PYTHON
            if (cur / "pom.xml").is_file() or (cur / "build.gradle").is_file() or (cur / "build.gradle.kts").is_file():
                return ProjectType.JAVA
            if (cur / "CMakeLists.txt").is_file() or (cur / "Makefile").is_file():
                return ProjectType.CPP

            if cur.parent == cur:
                break
            cur = cur.parent

        # Secondary check: file extensions in current directory
        try:
            path_cwd = Path(cwd)
            if any(path_cwd.glob("*.py")):
                return ProjectType.PYTHON
            if any(path_cwd.glob("*.ts")) or any(path_cwd.glob("*.tsx")):
                return ProjectType.TYPESCRIPT
            if any(path_cwd.glob("*.js")) or any(path_cwd.glob("*.jsx")):
                return ProjectType.JAVASCRIPT
            if any(path_cwd.glob("*.go")):
                return ProjectType.GO
            if any(path_cwd.glob("*.rs")):
                return ProjectType.RUST
        except Exception:
            pass

        return ProjectType.UNKNOWN

    async def verify_all(
        self,
        cwd: str,
        files_changed: list[str] | None = None,
        run_tests: bool = True,
        run_typecheck: bool = True,
        run_lint: bool = True,
        check_build: bool = True,
    ) -> list[VerificationResult]:
        """Run all applicable verification strategies for the project."""
        results: list[VerificationResult] = []

        # 1. Custom checks from LUCY.md or project config first
        custom_results = await self.run_custom_checks(cwd)
        if custom_results:
            results.extend(custom_results)
            # If custom checks defined tests/lint, they may satisfy the requirements
            custom_strategies = {r.strategy for r in custom_results}
            if "test" in custom_strategies:
                run_tests = False
            if "lint" in custom_strategies:
                run_lint = False
            if "typecheck" in custom_strategies:
                run_typecheck = False
            if "build" in custom_strategies:
                check_build = False

        # 2. Build check
        if check_build:
            build_res = await self.run_build(cwd)
            if build_res.command:  # Only append if a command was applicable
                results.append(build_res)
                # If build fails, tests & typechecks might fail cascadingly
                if not build_res.passed:
                    logger.warning("Build verification failed; continuing with remaining checks")

        # 3. Type check
        if run_typecheck:
            tc_res = await self.run_typecheck(cwd)
            if tc_res.command:
                results.append(tc_res)

        # 4. Lint check
        if run_lint:
            lint_res = await self.run_lint(cwd)
            if lint_res.command:
                results.append(lint_res)

        # 5. Test runner
        if run_tests:
            test_res = await self.run_tests(cwd)
            if test_res.command:
                results.append(test_res)

        return results

    async def run_tests(self, cwd: str) -> VerificationResult:
        """Auto-detect and run tests for the project."""
        ptype = await self.detect_project_type(cwd)
        cmd = self._detect_test_command(cwd, ptype)
        if not cmd:
            return VerificationResult(
                strategy=VerificationStrategy.TEST.value,
                passed=True,
                output="No test runner detected for project.",
                command="",
            )

        return await self._run_command(cmd, cwd, strategy=VerificationStrategy.TEST.value)

    async def run_typecheck(self, cwd: str) -> VerificationResult:
        """Run type checking according to project type."""
        ptype = await self.detect_project_type(cwd)
        cmd = self._detect_typecheck_command(cwd, ptype)
        if not cmd:
            return VerificationResult(
                strategy=VerificationStrategy.TYPECHECK.value,
                passed=True,
                output="No type checker detected for project.",
                command="",
            )

        return await self._run_command(cmd, cwd, strategy=VerificationStrategy.TYPECHECK.value)

    async def run_lint(self, cwd: str) -> VerificationResult:
        """Run linting according to project type."""
        ptype = await self.detect_project_type(cwd)
        cmd = self._detect_lint_command(cwd, ptype)
        if not cmd:
            return VerificationResult(
                strategy=VerificationStrategy.LINT.value,
                passed=True,
                output="No linter detected for project.",
                command="",
            )

        return await self._run_command(cmd, cwd, strategy=VerificationStrategy.LINT.value)

    async def run_build(self, cwd: str) -> VerificationResult:
        """Run build check according to project type."""
        ptype = await self.detect_project_type(cwd)
        cmd = self._detect_build_command(cwd, ptype)
        if not cmd:
            return VerificationResult(
                strategy=VerificationStrategy.BUILD.value,
                passed=True,
                output="No build command needed or detected.",
                command="",
            )

        return await self._run_command(cmd, cwd, strategy=VerificationStrategy.BUILD.value)

    async def run_custom_checks(self, cwd: str) -> list[VerificationResult]:
        """Detect and run custom verification commands defined in LUCY.md or configs."""
        commands = self._find_custom_commands(cwd)
        results: list[VerificationResult] = []

        for name, cmd in commands.items():
            strat = VerificationStrategy.CUSTOM.value
            if any(k in name.lower() for k in ["test", "spec"]):
                strat = VerificationStrategy.TEST.value
            elif any(k in name.lower() for k in ["type", "mypy", "tsc"]):
                strat = VerificationStrategy.TYPECHECK.value
            elif any(k in name.lower() for k in ["lint", "format", "style"]):
                strat = VerificationStrategy.LINT.value
            elif any(k in name.lower() for k in ["build", "compile"]):
                strat = VerificationStrategy.BUILD.value

            res = await self._run_command(cmd, cwd, strategy=strat)
            results.append(res)

        return results

    async def analyze_failure(self, result: VerificationResult) -> str:
        """Analyze a verification failure and produce detailed diagnosis and suggestions."""
        if result.passed:
            return "Verification passed. No errors to analyze."

        output = result.output.strip()
        strategy = result.strategy
        cmd = result.command

        analysis_parts: list[str] = [
            f"### Failure Analysis ({strategy.upper()})",
            f"**Command executed:** `{cmd}`",
        ]

        # Extract file locations and lines if present
        # Common pattern: file.py:123: error... or file.ts(123,45): error...
        locations = re.findall(r'([a-zA-Z0-9_\-./\\]+\.[a-zA-Z0-9]+)[:\(](\d+)(?:[:\)]|\,\d+\)?)', output)
        if locations:
            unique_locs = list(dict.fromkeys(f"{f}:{line}" for f, line in locations[:5]))
            analysis_parts.append(f"**Identified Error Locations:**\n" + "\n".join(f"- `{loc}`" for loc in unique_locs))

        # Categorize common errors
        if strategy == VerificationStrategy.TEST.value:
            failures = re.findall(r'(FAILED|FAIL|ERROR)[:\s]+([^\n]+)', output)
            if failures:
                analysis_parts.append("**Test Failures:**")
                for marker, desc in failures[:5]:
                    analysis_parts.append(f"- **{marker}**: {desc.strip()}")
            elif "AssertionError" in output:
                analysis_parts.append("**Root Cause:** Assertion failure during test execution.")

        elif strategy == VerificationStrategy.TYPECHECK.value:
            type_errors = [line for line in output.splitlines() if "error:" in line.lower() or "type" in line.lower()]
            if type_errors:
                analysis_parts.append("**Type Issues:**")
                for err in type_errors[:5]:
                    analysis_parts.append(f"- `{err.strip()}`")

        elif strategy == VerificationStrategy.LINT.value:
            lint_errors = [line for line in output.splitlines() if re.search(r'[EFW]\d{3,4}|error|rule', line, re.IGNORECASE)]
            if lint_errors:
                analysis_parts.append("**Lint Violations:**")
                for err in lint_errors[:5]:
                    analysis_parts.append(f"- `{err.strip()}`")

        elif strategy == VerificationStrategy.BUILD.value:
            analysis_parts.append("**Build / Compilation Failure:**")
            build_errors = [line for line in output.splitlines() if "error" in line.lower() or "fatal" in line.lower()]
            for err in build_errors[:5]:
                analysis_parts.append(f"- `{err.strip()}`")

        # Provide actionable recommendations
        analysis_parts.append("\n**Recommended Correction Steps:**")
        if strategy == VerificationStrategy.TEST.value:
            analysis_parts.append(
                "1. Review the assertion failure or exception traceback above.\n"
                "2. Check if recent modifications introduced unintended behavioral regressions or broke test fixtures.\n"
                "3. Fix the implementation or update the test if requirements were intentionally updated."
            )
        elif strategy == VerificationStrategy.TYPECHECK.value:
            analysis_parts.append(
                "1. Verify parameter and return types at the error locations.\n"
                "2. Ensure all imported types exist and type annotations are consistent with runtime values.\n"
                "3. Add explicit cast or type guard if necessary."
            )
        elif strategy == VerificationStrategy.LINT.value:
            analysis_parts.append(
                "1. Format the code or fix the flagged style/import violations.\n"
                "2. Remove unused imports or variables if reported by linter."
            )
        elif strategy == VerificationStrategy.BUILD.value:
            analysis_parts.append(
                "1. Check for missing dependencies, syntax errors, or mismatched configuration files.\n"
                "2. Ensure compilation flags and build scripts match current platform requirements."
            )
        else:
            analysis_parts.append(
                "1. Review the command output details above and address the non-zero exit code."
            )

        return "\n".join(analysis_parts)

    # -----------------------------------------------------------------------
    # Command detection helpers
    # -----------------------------------------------------------------------

    def _resolve_tool(self, name: str, cwd: str) -> str | None:
        """Find an executable in local project environments or system PATH."""
        path_cwd = Path(cwd)

        # Check Python virtual environments
        venv_bins = [
            path_cwd / ".venv" / "bin" / name,
            path_cwd / "venv" / "bin" / name,
            path_cwd / "env" / "bin" / name,
            path_cwd / ".venv" / "Scripts" / f"{name}.exe",
            path_cwd / "venv" / "Scripts" / f"{name}.exe",
        ]
        for p in venv_bins:
            if p.is_file() and os.access(str(p), os.X_OK):
                return str(p)

        # Check Node.js local bin
        node_bin = path_cwd / "node_modules" / ".bin" / name
        if node_bin.is_file() and os.access(str(node_bin), os.X_OK):
            return str(node_bin)

        # Check system PATH
        sys_tool = shutil.which(name)
        if sys_tool:
            return sys_tool

        return None

    def _detect_test_command(self, cwd: str, ptype: ProjectType) -> str | None:
        """Determine test command for project."""
        cur = Path(cwd)

        if ptype == ProjectType.PYTHON:
            pytest_bin = self._resolve_tool("pytest", cwd)
            if pytest_bin:
                return f"{pytest_bin} -q"
            # Fallback to python unittest
            python_bin = self._resolve_tool("python3", cwd) or self._resolve_tool("python", cwd) or "python3"
            test_dir = cur / "tests" if (cur / "tests").is_dir() else cur
            return f"{python_bin} -m unittest discover -s {test_dir.name}"

        if ptype in (ProjectType.JAVASCRIPT, ProjectType.TYPESCRIPT):
            pkg_path = cur / "package.json"
            if pkg_path.is_file():
                try:
                    data = json.loads(pkg_path.read_text(encoding="utf-8"))
                    scripts = data.get("scripts", {})
                    if "test" in scripts and "no test specified" not in scripts["test"]:
                        npm = self._resolve_tool("npm", cwd) or "npm"
                        return f"{npm} test"
                except Exception:
                    pass
            for runner in ["vitest", "jest"]:
                r_bin = self._resolve_tool(runner, cwd)
                if r_bin:
                    return f"{r_bin} run"

        if ptype == ProjectType.GO:
            go = self._resolve_tool("go", cwd) or "go"
            return f"{go} test ./..."

        if ptype == ProjectType.RUST:
            cargo = self._resolve_tool("cargo", cwd) or "cargo"
            return f"{cargo} test"

        if ptype == ProjectType.JAVA:
            if (cur / "mvnw").is_file():
                return "./mvnw test"
            if (cur / "pom.xml").is_file():
                return "mvn test"
            if (cur / "gradlew").is_file():
                return "./gradlew test"
            if (cur / "build.gradle").is_file() or (cur / "build.gradle.kts").is_file():
                return "gradle test"

        if ptype == ProjectType.CPP:
            if (cur / "Makefile").is_file():
                return "make test"
            if (cur / "CMakeLists.txt").is_file():
                return "ctest --output-on-failure"

        return None

    def _detect_typecheck_command(self, cwd: str, ptype: ProjectType) -> str | None:
        """Determine typecheck command for project."""
        cur = Path(cwd)

        if ptype == ProjectType.PYTHON:
            for checker in ["mypy", "pyright"]:
                c_bin = self._resolve_tool(checker, cwd)
                if c_bin:
                    return f"{c_bin} ."
            return None

        if ptype == ProjectType.TYPESCRIPT:
            tsc = self._resolve_tool("tsc", cwd)
            if tsc:
                return f"{tsc} --noEmit"
            return "npx tsc --noEmit"

        if ptype == ProjectType.GO:
            go = self._resolve_tool("go", cwd) or "go"
            return f"{go} vet ./..."

        return None

    def _detect_lint_command(self, cwd: str, ptype: ProjectType) -> str | None:
        """Determine linter command for project."""
        cur = Path(cwd)

        if ptype == ProjectType.PYTHON:
            for linter in ["ruff", "flake8"]:
                l_bin = self._resolve_tool(linter, cwd)
                if l_bin:
                    if linter == "ruff":
                        return f"{l_bin} check ."
                    return f"{l_bin} ."
            # Fallback syntax compilation check
            python_bin = self._resolve_tool("python3", cwd) or "python3"
            return f"{python_bin} -m compileall -q ."

        if ptype in (ProjectType.JAVASCRIPT, ProjectType.TYPESCRIPT):
            pkg_path = cur / "package.json"
            if pkg_path.is_file():
                try:
                    data = json.loads(pkg_path.read_text(encoding="utf-8"))
                    scripts = data.get("scripts", {})
                    if "lint" in scripts:
                        npm = self._resolve_tool("npm", cwd) or "npm"
                        return f"{npm} run lint"
                except Exception:
                    pass
            eslint = self._resolve_tool("eslint", cwd)
            if eslint:
                return f"{eslint} ."

        if ptype == ProjectType.RUST:
            cargo = self._resolve_tool("cargo", cwd) or "cargo"
            return f"{cargo} clippy -- -D warnings"

        if ptype == ProjectType.GO:
            golangci = self._resolve_tool("golangci-lint", cwd)
            if golangci:
                return f"{golangci} run"

        return None

    def _detect_build_command(self, cwd: str, ptype: ProjectType) -> str | None:
        """Determine build command for project."""
        cur = Path(cwd)

        if ptype == ProjectType.RUST:
            cargo = self._resolve_tool("cargo", cwd) or "cargo"
            return f"{cargo} build"

        if ptype == ProjectType.GO:
            go = self._resolve_tool("go", cwd) or "go"
            return f"{go} build ./..."

        if ptype in (ProjectType.JAVASCRIPT, ProjectType.TYPESCRIPT):
            pkg_path = cur / "package.json"
            if pkg_path.is_file():
                try:
                    data = json.loads(pkg_path.read_text(encoding="utf-8"))
                    scripts = data.get("scripts", {})
                    if "build" in scripts:
                        npm = self._resolve_tool("npm", cwd) or "npm"
                        return f"{npm} run build"
                except Exception:
                    pass

        if ptype == ProjectType.CPP:
            if (cur / "Makefile").is_file():
                return "make"
            if (cur / "CMakeLists.txt").is_file():
                return "cmake --build ."

        if ptype == ProjectType.JAVA:
            if (cur / "mvnw").is_file():
                return "./mvnw compile"
            if (cur / "pom.xml").is_file():
                return "mvn compile"
            if (cur / "gradlew").is_file():
                return "./gradlew build -x test"
            if (cur / "build.gradle").is_file() or (cur / "build.gradle.kts").is_file():
                return "gradle build -x test"

        return None

    def _find_custom_commands(self, cwd: str) -> dict[str, str]:
        """Look for custom verification commands in LUCY.md or .lucy/config.json."""
        custom_cmds: dict[str, str] = {}
        cur = Path(cwd)

        # Check LUCY.md or CLAUDE.md
        for doc_name in ["LUCY.md", ".lucy/LUCY.md", "CLAUDE.md", ".claude/CLAUDE.md"]:
            doc_path = cur / doc_name
            if doc_path.is_file():
                try:
                    content = doc_path.read_text(encoding="utf-8")
                    # Parse lines like "test: pytest" or "verify: make check"
                    matches = re.findall(r'(?:^|\n)[-*#\s]*([a-zA-Z0-9_-]+)\s*(?:command|script)?[:=]\s*`?([^\n`]+)`?', content, re.IGNORECASE)
                    for key, val in matches:
                        clean_key = key.strip().lower()
                        clean_val = val.strip()
                        if clean_key in ("test", "tests", "typecheck", "lint", "build", "verify"):
                            custom_cmds[clean_key] = clean_val
                except Exception as e:
                    logger.debug("Failed parsing %s for custom verification: %s", doc_path, e)

        # Check .lucy/config.json
        config_path = cur / ".lucy" / "config.json"
        if config_path.is_file():
            try:
                data = json.loads(config_path.read_text(encoding="utf-8"))
                verify_section = data.get("verification", {})
                for k, v in verify_section.items():
                    if isinstance(v, str):
                        custom_cmds[k] = v
            except Exception:
                pass

        return custom_cmds

    # -----------------------------------------------------------------------
    # Subprocess execution
    # -----------------------------------------------------------------------

    async def _run_command(self, cmd: str, cwd: str, strategy: str) -> VerificationResult:
        """Run a verification command and capture output."""
        start_time = time.time()
        logger.info("Running verification [%s]: %s (cwd=%s)", strategy, cmd, cwd)

        try:
            proc = await asyncio.create_subprocess_shell(
                cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=cwd,
            )

            try:
                stdout_data, stderr_data = await asyncio.wait_for(
                    proc.communicate(),
                    timeout=self.timeout_seconds,
                )
            except asyncio.TimeoutError:
                try:
                    proc.kill()
                    await proc.wait()
                except Exception:
                    pass
                duration = time.time() - start_time
                return VerificationResult(
                    strategy=strategy,
                    passed=False,
                    output=f"Command timed out after {self.timeout_seconds}s: {cmd}",
                    errors=[f"Timed out after {self.timeout_seconds} seconds"],
                    duration_seconds=duration,
                    command=cmd,
                )

            duration = time.time() - start_time
            stdout_str = stdout_data.decode("utf-8", errors="replace")
            stderr_str = stderr_data.decode("utf-8", errors="replace")
            combined_output = (stdout_str + ("\n" + stderr_str if stderr_str else "")).strip()

            passed = (proc.returncode == 0)
            errors, warnings = self._parse_output(combined_output, passed)

            return VerificationResult(
                strategy=strategy,
                passed=passed,
                output=combined_output,
                errors=errors,
                warnings=warnings,
                duration_seconds=duration,
                command=cmd,
            )

        except Exception as e:
            duration = time.time() - start_time
            logger.exception("Failed to execute verification command: %s", cmd)
            return VerificationResult(
                strategy=strategy,
                passed=False,
                output=f"Execution error: {e}",
                errors=[str(e)],
                duration_seconds=duration,
                command=cmd,
            )

    def _parse_output(self, output: str, passed: bool) -> tuple[list[str], list[str]]:
        """Extract structured errors and warnings from tool output."""
        errors: list[str] = []
        warnings: list[str] = []

        lines = output.splitlines()
        for line in lines:
            trimmed = line.strip()
            if not trimmed:
                continue

            lower = trimmed.lower()
            if "error:" in lower or lower.startswith("error") or "failed" in lower or "fatal:" in lower:
                if len(errors) < 15:
                    errors.append(trimmed)
            elif "warning:" in lower or lower.startswith("warn"):
                if len(warnings) < 15:
                    warnings.append(trimmed)

        if not passed and not errors:
            # Pick the last 3 non-empty lines as error summary
            non_empty = [l.strip() for l in lines if l.strip()]
            errors = non_empty[-3:] if non_empty else ["Command failed with non-zero exit code."]

        return errors, warnings
