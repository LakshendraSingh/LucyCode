"""
Speculative execution — pre-compute likely next steps.

After the LLM decides on an action, speculatively pre-fetch data
that will likely be needed next:
- If reading file A, also read files that import/reference A
- If running a test, pre-read the source file being tested
- If editing a file, pre-check for lint/type errors
"""

from __future__ import annotations

import asyncio
import logging
import os
import re
from pathlib import Path
from typing import Any

from lucy.core.tool import ToolContext

logger = logging.getLogger(__name__)

MAX_PREFETCH_BYTES = 12 * 1024  # 12 KB max per prefetched file
MAX_PREFETCH_FILES = 3          # Maximum files to prefetch per turn
SPECULATION_TIMEOUT_SECONDS = 2.0


class SpeculativeEngine:
    """Pre-fetches data for likely next steps without blocking the agentic loop."""

    def __init__(self) -> None:
        self._cache: dict[str, str] = {}
        self._recent_fetches: set[str] = set()

    async def speculate(
        self,
        tool_name: str,
        tool_input: dict[str, Any],
        context: ToolContext,
    ) -> dict[str, str]:
        """Given a tool call, pre-fetch likely needed data.

        Returns a dict of {key: pre-fetched content} that can be
        injected as supplementary context. Never blocks longer than 2s.
        """
        try:
            return await asyncio.wait_for(
                self._do_speculate(tool_name, tool_input, context),
                timeout=SPECULATION_TIMEOUT_SECONDS,
            )
        except (asyncio.TimeoutError, Exception) as e:
            logger.debug("Speculative prefetch timed out or skipped: %s", e)
            return {}

    async def _do_speculate(
        self,
        tool_name: str,
        tool_input: dict[str, Any],
        context: ToolContext,
    ) -> dict[str, str]:
        """Internal speculation logic."""
        cwd = context.cwd or os.getcwd()
        predicted_paths: list[str] = []

        # 1. File read
        if tool_name in ("Read", "FileRead", "ReadFile"):
            file_path = tool_input.get("file_path", "")
            if file_path:
                predicted_paths.extend(self._speculate_file_read(file_path, cwd))

        # 2. Bash command
        elif tool_name in ("Bash", "bash"):
            cmd = tool_input.get("command", "")
            if cmd:
                predicted_paths.extend(self._speculate_bash(cmd, cwd))

        # 3. File Edit / Write
        elif tool_name in ("Edit", "FileEdit", "Write", "FileWrite"):
            file_path = tool_input.get("file_path", "")
            if file_path:
                predicted_paths.extend(self._speculate_file_edit(file_path, cwd))

        # Read contents of predicted files
        results: dict[str, str] = {}
        count = 0
        for p in predicted_paths:
            if count >= MAX_PREFETCH_FILES:
                break
            abs_path = os.path.abspath(os.path.join(cwd, p) if not os.path.isabs(p) else p)

            # Skip if already read or nonexistent
            if abs_path in self._recent_fetches or not os.path.isfile(abs_path):
                continue

            try:
                # Read first portion asynchronously
                content = await self._async_read_file(abs_path)
                if content:
                    rel_name = os.path.relpath(abs_path, cwd)
                    results[f"speculative:{rel_name}"] = content
                    self._recent_fetches.add(abs_path)
                    count += 1
            except Exception as e:
                logger.debug("Failed to prefetch file %s: %s", abs_path, e)

        return results

    def _speculate_file_read(self, file_path: str, cwd: str) -> list[str]:
        """Given a file read, predict related files to pre-fetch."""
        predicted: list[str] = []
        path_obj = Path(file_path)
        if not path_obj.is_absolute():
            path_obj = Path(cwd) / path_obj

        if not path_obj.exists() or not path_obj.is_file():
            return predicted

        stem = path_obj.stem
        suffix = path_obj.suffix
        parent = path_obj.parent

        # 1. Test <-> Implementation pairing
        if stem.startswith("test_"):
            impl_name = stem[5:] + suffix
            for candidate in [parent / impl_name, Path(cwd) / "src" / impl_name, Path(cwd) / impl_name]:
                if candidate.exists() and candidate.is_file():
                    predicted.append(str(candidate))
        elif stem.endswith("_test") or stem.endswith(".test"):
            impl_name = stem.rsplit(".", 1)[0] + suffix
            candidate = parent / impl_name
            if candidate.exists():
                predicted.append(str(candidate))
        else:
            # Source file -> look for corresponding test file
            for test_candidate in [
                parent / f"test_{stem}{suffix}",
                Path(cwd) / "tests" / f"test_{stem}{suffix}",
                parent / f"{stem}.test{suffix}",
            ]:
                if test_candidate.exists() and test_candidate.is_file():
                    predicted.append(str(test_candidate))

        # 2. Extract imports from file
        try:
            text = path_obj.read_text(encoding="utf-8", errors="ignore")[:8000]

            # Python imports
            if suffix == ".py":
                # from .foo import bar OR from foo import bar
                for match in re.finditer(r"(?:from|import)\s+([a-zA-Z0-9_\.]+)", text):
                    mod_name = match.group(1).split(".")[0]
                    # Check local sibling module
                    sibling = parent / f"{mod_name}.py"
                    if sibling.exists() and sibling.is_file() and sibling != path_obj:
                        predicted.append(str(sibling))
                    # Check project root module
                    root_mod = Path(cwd) / f"{mod_name}.py"
                    if root_mod.exists() and root_mod.is_file() and root_mod != path_obj:
                        predicted.append(str(root_mod))

            # JS/TS imports
            elif suffix in (".js", ".ts", ".jsx", ".tsx"):
                for match in re.finditer(r"(?:import|require)\s*\(?['\"]([^'\"]+)['\"]\)?", text):
                    target = match.group(1)
                    if target.startswith("."):  # Relative import
                        for ext in [suffix, ".ts", ".js", ".tsx", ".jsx", ""]:
                            candidate = (parent / target).with_suffix(ext) if ext else (parent / target)
                            if candidate.is_file():
                                predicted.append(str(candidate))
                                break
                            index_cand = parent / target / f"index{suffix}"
                            if index_cand.is_file():
                                predicted.append(str(index_cand))
                                break

        except Exception as e:
            logger.debug("Error extracting imports from %s: %s", path_obj, e)

        return predicted

    def _speculate_bash(self, command: str, cwd: str) -> list[str]:
        """Given a bash command, predict what context will be needed."""
        predicted: list[str] = []
        cmd_parts = command.strip().split()
        if not cmd_parts:
            return predicted

        # 1. Test runner commands
        is_test = any(tok in command for tok in ["pytest", "npm test", "jest", "unittest", "cargo test", "go test"])
        if is_test:
            # Look for file arguments in the command line
            for part in cmd_parts:
                part_clean = part.strip("\"'")
                if os.path.isfile(os.path.join(cwd, part_clean)):
                    predicted.append(part_clean)
                    # Also speculate tested source file
                    predicted.extend(self._speculate_file_read(part_clean, cwd))

        # 2. Git status / git diff commands
        if "git status" in command or "git diff" in command:
            try:
                git_dir = Path(cwd) / ".git"
                if git_dir.exists():
                    # Check recent uncommitted files or modified files
                    status_path = Path(cwd) / ".git" / "logs" / "HEAD"
                    if status_path.exists():
                        # We can inspect common project files
                        for candidate in ["pyproject.toml", "package.json", "Cargo.toml"]:
                            if (Path(cwd) / candidate).exists():
                                predicted.append(candidate)
            except Exception:
                pass

        # 3. Linter / typecheck commands
        if any(lint in command for lint in ["ruff", "mypy", "flake8", "eslint", "tsc"]):
            for part in cmd_parts:
                part_clean = part.strip("\"'")
                if os.path.isfile(os.path.join(cwd, part_clean)):
                    predicted.append(part_clean)

        return predicted

    def _speculate_file_edit(self, file_path: str, cwd: str) -> list[str]:
        """Given a file being edited, predict what context will be checked next."""
        # Typically the user/assistant will run tests or check the file importing this file
        return self._speculate_file_read(file_path, cwd)

    async def _async_read_file(self, abs_path: str) -> str:
        """Asynchronously read first portion of a file."""
        loop = asyncio.get_running_loop()

        def _read() -> str:
            with open(abs_path, "r", encoding="utf-8", errors="replace") as f:
                lines = []
                total_bytes = 0
                for line in f:
                    lines.append(line)
                    total_bytes += len(line.encode("utf-8"))
                    if total_bytes >= MAX_PREFETCH_BYTES or len(lines) >= 200:
                        lines.append("\n... (speculative pre-fetch truncated)")
                        break
                return "".join(lines)

        return await loop.run_in_executor(None, _read)


# Global singleton
_speculative_engine: SpeculativeEngine | None = None


def get_speculative_engine() -> SpeculativeEngine:
    global _speculative_engine
    if _speculative_engine is None:
        _speculative_engine = SpeculativeEngine()
    return _speculative_engine
