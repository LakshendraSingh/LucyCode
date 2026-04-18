"""
System and user context — git status, date, LUCY.md.

Provides contextual information prepended to each conversation.
"""

from __future__ import annotations

import asyncio
import os
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Any


async def get_git_status(cwd: str | None = None) -> str | None:
    """Get git status summary (branch, recent commits, diff status)."""
    cwd = cwd or os.getcwd()

    try:
        # Check if it's a git repo
        result = subprocess.run(
            ["git", "rev-parse", "--is-inside-work-tree"],
            capture_output=True, text=True, cwd=cwd, timeout=5,
        )
        if result.returncode != 0:
            return None

        # Get branch, status, log, username in parallel
        async def _run(args: list[str]) -> str:
            proc = await asyncio.create_subprocess_exec(
                *args, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE, cwd=cwd,
            )
            stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=10)
            return stdout.decode("utf-8", errors="replace").strip()

        branch, status, log, user_name = await asyncio.gather(
            _run(["git", "branch", "--show-current"]),
            _run(["git", "--no-optional-locks", "status", "--short"]),
            _run(["git", "--no-optional-locks", "log", "--oneline", "-n", "5"]),
            _run(["git", "config", "user.name"]),
            return_exceptions=True,
        )

        # Handle exceptions gracefully
        branch = branch if isinstance(branch, str) else ""
        status = status if isinstance(status, str) else ""
        log = log if isinstance(log, str) else ""
        user_name = user_name if isinstance(user_name, str) else ""

        # Truncate long status
        if len(status) > 2000:
            status = status[:2000] + "\n... (truncated)"

        parts = [
            "Git status at conversation start (snapshot, will not update):",
            f"Current branch: {branch or '(detached)'}",
        ]
        if user_name:
            parts.append(f"Git user: {user_name}")
        parts.append(f"Status:\n{status or '(clean)'}")
        parts.append(f"Recent commits:\n{log or '(none)'}")

        return "\n\n".join(parts)

    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        return None


def get_system_context(cwd: str | None = None) -> dict[str, str]:
    """Get system-level context (date, OS, etc.)."""
    return {
        "currentDate": f"Today's date is {datetime.now().strftime('%Y-%m-%d')}.",
    }


def get_lucymd_content(cwd: str | None = None) -> str | None:
    """Find and read LUCY.md files from cwd upward.

    Searches for LUCY.md (or fallback CLAUDE.md) in the current directory
    and parent directories. Returns concatenated content.
    """
    cwd = cwd or os.getcwd()
    current = Path(cwd)
    contents: list[str] = []
    visited: set[str] = set()

    while True:
        # Search for names (LUCY.md preferred, CLAUDE.md fallback)
        for name in ["LUCY.md", ".lucy/LUCY.md", "CLAUDE.md", ".claude/CLAUDE.md"]:
            candidate = current / name
            real = str(candidate.resolve())
            if real not in visited and candidate.is_file():
                visited.add(real)
                try:
                    text = candidate.read_text(encoding="utf-8").strip()
                    if text:
                        contents.append(f"# From {candidate}\n\n{text}")
                except OSError:
                    pass

        parent = current.parent
        if parent == current:
            break
        current = parent

    if not contents:
        return None

    return "\n\n---\n\n".join(contents)


def build_system_prompt(
    cwd: str | None = None,
    git_status: str | None = None,
    lucymd: str | None = None,
    custom_instructions: str | None = None,
    is_coordinator: bool = False,
    is_assistant: bool = False,
) -> str:
    """Build the full system prompt with context sections."""
    if is_coordinator:
        from lucy.core.coordinator import get_coordinator_system_prompt
        sections = [get_coordinator_system_prompt()]
    elif is_assistant:
        from lucy.core.kairos import get_kairos_system_prompt
        sections = [get_kairos_system_prompt()]
    else:
        sections = [_BASE_SYSTEM_PROMPT]

    if lucymd:
        sections.append(f"<user_instructions>\n{lucymd}\n</user_instructions>")

    if git_status:
        sections.append(f"<git_status>\n{git_status}\n</git_status>")

    if custom_instructions:
        sections.append(custom_instructions)

    sections.append(f"Today's date is {datetime.now().strftime('%Y-%m-%d')}.")

    return "\n\n".join(sections)


# ---------------------------------------------------------------------------
# Base system prompt
# ---------------------------------------------------------------------------

_BASE_SYSTEM_PROMPT = """You are Lucy Code, an expert AI coding assistant running in the user's terminal. You help with software engineering tasks: writing code, debugging, running commands, searching files, and managing projects.

## Core Behavior
- Be direct and concise. Avoid unnecessary preamble.
- **Be Pragmatic**: Only use tools (Bash, Read, Glob, etc.) if the answer is not already in your context. Avoid deep or recursive file exploration for simple questions.
- **Stop Hallucinating**: Do not guess file paths or command outputs. If a tool returns "File not found" or an error, do not keep trying the same path or similar guessed paths (like /home/user). If you cannot find a file after a brief search, stop and ask the user for the correct path.
- When given a task, do it — don't ask for confirmation unless the instruction is ambiguous.
- Use tools to gather information before making changes. Read files before editing them.
- After making changes, verify they work (run tests, lint, build) when appropriate.
- Think step-by-step for complex tasks.

## Tool Use
You have access to tools for:
- **Bash**: Execute shell commands. The terminal is NON-INTERACTIVE; avoid commands that wait for input (like bare 'bash' or 'sudo' with password prompts).
- **Read**: Read file contents
- **Write**: Create or overwrite files
- **Edit**: Make surgical edits to existing files (search-and-replace)
- **Grep**: Search for patterns across files
- **Glob**: Find files matching patterns

### Best Practices
- Read files before editing — understand the existing code first.
- Make targeted edits with Edit instead of rewriting entire files with Write.
- Verify changes work after making them.
- Use Grep/Glob to understand the codebase before making changes.
- For Bash: prefer specific targeted commands over broad ones.
- Always provide absolute file paths.

## Code Quality
- Match the existing code style.
- Preserve existing comments and docstrings unless they're about the change.
- Write clean, readable, well-commented code.
- Follow language idioms and best practices.

## Communication
- Keep responses concise.
- When showing code changes, use diffs or highlight what changed.
- If you're uncertain, say so — don't guess.
"""
