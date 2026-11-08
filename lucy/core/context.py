"""
System and user context — git status, date, LUCY.md.

Provides contextual information prepended to each conversation.
"""

from __future__ import annotations

import asyncio
import logging
import os
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


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
    user_prompt: str = "",
    files: list[str] | None = None,
    skills_injection: str | None = None,
    is_autonomous: bool = False,
) -> str:
    """Build the full system prompt with context sections and active skills."""
    if is_coordinator:
        from lucy.core.coordinator import get_coordinator_system_prompt
        sections = [get_coordinator_system_prompt()]
    elif is_assistant:
        from lucy.core.kairos import get_kairos_system_prompt
        sections = [get_kairos_system_prompt()]
    else:
        sections = [_BASE_SYSTEM_PROMPT]

    # ── Skills injection (after base prompt, before LUCY.md) ──
    if skills_injection is not None:
        if skills_injection.strip():
            sections.append(skills_injection.strip())
    else:
        try:
            from lucy.core.skills_engine import get_skills_engine
            engine = get_skills_engine()
            target_cwd = cwd or os.getcwd()
            engine.discover(target_cwd)
            # Auto-activate skills based on project type and user prompt
            engine.activate_for_context(target_cwd, user_prompt=user_prompt, files=files)
            skills_text = engine.get_system_prompt_injection()
            if skills_text:
                sections.append(skills_text)
        except Exception as e:
            logger.debug("Failed to inject skills into system prompt: %s", e)

    # ── Learned corrections injection ──
    try:
        from lucy.core.learning import get_learning_engine
        learning = get_learning_engine()
        corrections_text = learning.build_prompt_injection(
            context=cwd or "",
            user_prompt=user_prompt or custom_instructions or "",
        )
        if corrections_text:
            sections.append(corrections_text)
    except Exception as e:
        logger.debug("Failed to inject learned corrections: %s", e)

    if lucymd:
        sections.append(f"<user_instructions>\n{lucymd}\n</user_instructions>")

    if git_status:
        sections.append(f"<git_status>\n{git_status}\n</git_status>")

    # ── Repo Map Injection (Structural Codebase Awareness) ──
    try:
        from lucy.core.repomap import get_repo_map
        rm = get_repo_map(cwd or os.getcwd())
        map_text = rm.render_map(max_tokens=1200)
        if map_text and map_text != "(Empty repository)":
            sections.append(
                f"<repo_map>\n"
                f"# Repository Architectural Symbol Map (Ranked by PageRank Centrality)\n"
                f"{map_text}\n"
                f"</repo_map>"
            )
    except Exception as e:
        logger.debug("Repo map generation skipped: %s", e)

    if custom_instructions:
        sections.append(custom_instructions)

    if is_autonomous:
        sections.append(
            "## Autonomous Execution Mode (ACTIVE)\n"
            "- You are running in FULLY AUTONOMOUS MODE.\n"
            "- You must NOT ask the user anything in the middle of the assigned task.\n"
            "- NEVER call AskUserQuestion or pause for manual human confirmation.\n"
            "- Make executive decisions independently: choose standard conventions, best practices, and sensible defaults.\n"
            "- If you encounter ambiguities, multiple candidate targets, or minor errors, select the best resolution autonomously, verify it yourself, and drive the task to 100% completion without stopping."
        )

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
- **Ask When Unsure**: If an instruction is ambiguous, multiple interpretations exist, or you encounter unexpected screen/system states, use the `AskUserQuestion` tool to prompt the user directly in the middle of execution with structured options and a recommended default. Never guess blindly.
- When given a task, do it — don't ask for confirmation for trivial steps, but prompt the user if a genuine decision is required.
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
- **revert_change** (`undo`, `rollback`): Revert or rollback file modifications (last edit, specific file, or all session changes).
- **AskUserQuestion** (`ask_user`): Prompt the user in the middle of execution with structured choices whenever you are unsure, face multiple candidate targets, or need human guidance.
- **Workstation & Universal UI Automation**:
  - `ui_inspect`: Inspect active app, window title, browser URL, visible buttons, and menus.
  - `ui_click`: Deterministically click buttons or controls by label across any application with verification.
  - `ui_menu`: Trigger menu items universally (`File > New`, `Edit > Paste`, etc.) across any macOS application without guessing shortcuts.
  - `ui_type`: Paste or type text into fields or active windows with zero dropped characters.
  - `ui_verify`: Verify live application state (active URL, window title, button presence) to prevent false positives.
  - `launch_app` / `focus_app`: Open or bring desktop applications to the foreground.
  - `applescript`: Execute native macOS AppleScript automation.
  - `browser`: Open URLs, search, inspect DOM, or click elements in the web browser.
  - `browser_subagent` (`cdp_browser`, `cdp_click`): Autonomous browser sub-agent powered by Chrome DevTools Protocol (CDP). Discovers interactive buttons and dispatches deterministic clicks and multi-step browser workflows.
  - `email`: Compose and send emails directly to recipients via Gmail or Mail.app.
  - `presentation`: Build modern, polished 16:9 PowerPoint presentations (.pptx) with curated color themes, feature cards, KPI metrics, process workflows, and comparison slides.

### Best Practices
- Read files before editing — understand the existing code first.
- Make targeted edits with Edit instead of rewriting entire files with Write.
- Verify changes work after making them.
- Use Grep/Glob to understand the codebase before making changes.
- For Bash: prefer specific targeted commands over broad ones.
- Always provide absolute file paths.
- **Reverting Changes**: If an edit causes regressions, if tests fail, or if the user asks to undo, use the `revert_change` tool (or slash command `/revert`) to safely roll back the last modification, a specific file, or all session changes.
- **For Desktop & Application Automation Tasks** (Works universally on ANY app):
  - **Zero False Positives**: NEVER claim a task succeeded (such as sending an email, creating a document, or submitting a form) without verifying the live state.
  - **Do NOT blindly guess keyboard shortcuts**: Blind shortcut sequences (e.g. hitting random keys) frequently fail silently or send keystrokes into the wrong window.
  - **Inspect before acting**: Call `ui_inspect` first to verify which application, window, and URL are currently active. If automating a web app like Gmail in Safari, confirm that the active tab is actually on the expected URL before interacting.
  - **Target by UI element or menu**: Use `ui_menu` (e.g. `['File', 'New']`) to open documents and `ui_click` with the exact button name (e.g. `'Compose'`, `'Send'`, `'Save'`).
  - **Verify outcome**: Use `ui_verify` to confirm that the expected change occurred (e.g. URL changed, modal closed, window created). If an element was not found or verification failed, report the actual screen state to the user instead of falsely claiming completion.
- **For Presentation & Slide Deck Tasks** (e.g. "open power point and make a ppt on X in 20 slides use images", "create a good looking ppt for Y"):
  - Use the `presentation` tool to generate the requested `.pptx` deck with modern design themes (`modern_dark`, `clean_light`, `executive_navy`, `warm_editorial`, `vibrant_tech`).
  - Honor the requested slide count and topics. If the user asks for 20 slides, generate all 20 comprehensive, rich slides across the topic's full domain.
  - When images or visuals are requested, incorporate `type: "image"` slides with `points`, `caption`, and `image_path` or `image_url` (or visual infographic topics).
  - Structure the slides into clear archetypes: high-impact Title slide, 2-4 column feature Cards, Big Number Key Metrics, Process workflows, Comparison, Image/Visual showcase, and Summary slides.
  - If the user asked to "open power point" or "open ppt", use `bash` (e.g. `open <output_path>` or `open -a "Microsoft PowerPoint" <output_path>`) to open the generated presentation in PowerPoint immediately upon completion.
- **For Web Browser Interaction & Button Clicking** (e.g. "find and click the Sign In button", "submit the form on webpage"):
  - Use the `browser_subagent` tool with `action: "click_button"` passing `button` (the button text, aria-label, or selector) and optionally `url`.
  - The Browser Subagent is powered by the Chrome DevTools Protocol (CDP), deterministically discovering all candidate buttons in the live DOM, computing box coordinates, scrolling into view, and dispatching genuine mouse click events without guessing shortcuts.
  - You can also use `action: "find_buttons"` to inspect all clickable controls on the page, or `action: "run_task"` for end-to-end multi-step browsing.
- **For YouTube & Web Video Playback** (e.g. "open youtube and play sahiba at 01:14"):
  - NEVER guess or hardcode arbitrary video IDs (which frequently lead to 'Video unavailable' errors).
  - Use the `browser` tool with `action: "youtube"`, passing `query` (e.g. `"sahiba"`) and `timestamp` (e.g. `"01:14"` or `74`).
  - This dynamically searches YouTube, verifies that the video is active and playable (filtering out unavailable or deleted videos), appends the exact timestamp (`&t=74s`), and launches it in the browser so it starts playing immediately at the requested mark.

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
