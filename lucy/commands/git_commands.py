"""
Git commands — /branch, /commit, /diff, /rewind, /commit-push-pr.
"""

from __future__ import annotations

import subprocess
from typing import Any

from lucy.core.commands import Command, CommandResult


class BranchCommand(Command):
    @property
    def name(self) -> str: return "branch"
    @property
    def aliases(self) -> list[str]: return ["br"]
    @property
    def description(self) -> str: return "List, create, or switch git branches"
    @property
    def usage(self) -> str: return "/branch [name] — switch/create branch. No args = list."

    async def execute(self, args: str, state: Any) -> CommandResult:
        args = args.strip()
        if not args:
            r = subprocess.run(["git", "branch", "-a", "--color"], capture_output=True, text=True, cwd=state.cwd)
            return CommandResult(output=r.stdout or r.stderr)
        r = subprocess.run(["git", "checkout", "-b" if not _branch_exists(args, state.cwd) else "", args],
                           capture_output=True, text=True, cwd=state.cwd)
        if r.returncode == 0:
            return CommandResult(output=f"Switched to branch: {args}")
        # Try just checkout
        r = subprocess.run(["git", "checkout", args], capture_output=True, text=True, cwd=state.cwd)
        return CommandResult(output=r.stdout or r.stderr, error=r.stderr if r.returncode else None)


class CommitCommand(Command):
    @property
    def name(self) -> str: return "commit"
    @property
    def description(self) -> str: return "Stage all changes and commit"
    @property
    def usage(self) -> str: return "/commit [message] — commit with optional message"

    async def execute(self, args: str, state: Any) -> CommandResult:
        msg = args.strip() or "Changes from Lucy Code session"
        subprocess.run(["git", "add", "-A"], cwd=state.cwd, capture_output=True)
        r = subprocess.run(["git", "commit", "-m", msg], capture_output=True, text=True, cwd=state.cwd)
        return CommandResult(output=r.stdout or r.stderr)


class DiffCommand(Command):
    @property
    def name(self) -> str: return "diff"
    @property
    def description(self) -> str: return "Show git diff"
    @property
    def usage(self) -> str: return "/diff [file] — show changes"

    async def execute(self, args: str, state: Any) -> CommandResult:
        cmd = ["git", "diff", "--stat"]
        if args.strip():
            cmd = ["git", "diff", args.strip()]
        r = subprocess.run(cmd, capture_output=True, text=True, cwd=state.cwd)
        output = r.stdout or "No changes."
        return CommandResult(output=output)


class RewindCommand(Command):
    @property
    def name(self) -> str: return "rewind"
    @property
    def aliases(self) -> list[str]: return ["undo-commit"]
    @property
    def description(self) -> str: return "Undo the last N commits (soft reset)"
    @property
    def usage(self) -> str: return "/rewind [N] — undo last N commits (default 1)"

    async def execute(self, args: str, state: Any) -> CommandResult:
        n = 1
        if args.strip().isdigit():
            n = int(args.strip())
        r = subprocess.run(["git", "reset", "--soft", f"HEAD~{n}"], capture_output=True, text=True, cwd=state.cwd)
        if r.returncode == 0:
            return CommandResult(output=f"Rewound {n} commit(s). Changes are staged.")
        return CommandResult(error=r.stderr)


class CommitPushPRCommand(Command):
    @property
    def name(self) -> str: return "commit-push-pr"
    @property
    def aliases(self) -> list[str]: return ["pr", "push"]
    @property
    def description(self) -> str: return "Commit, push, and create a pull request"
    @property
    def usage(self) -> str: return "/commit-push-pr [title] — full PR workflow"

    async def execute(self, args: str, state: Any) -> CommandResult:
        title = args.strip()
        msgs = []
        # Stage + commit
        subprocess.run(["git", "add", "-A"], cwd=state.cwd, capture_output=True)
        r = subprocess.run(["git", "commit", "-m", title or "Changes from Lucy Code"],
                           capture_output=True, text=True, cwd=state.cwd)
        msgs.append(r.stdout.strip() if r.stdout else r.stderr.strip())

        # Get current branch
        br = subprocess.run(["git", "branch", "--show-current"], capture_output=True, text=True, cwd=state.cwd)
        branch = br.stdout.strip()

        # Push
        r = subprocess.run(["git", "push", "--set-upstream", "origin", branch],
                           capture_output=True, text=True, cwd=state.cwd)
        msgs.append(r.stdout.strip() if r.stdout else r.stderr.strip())

        # Try gh CLI for PR
        r = subprocess.run(["gh", "pr", "create", "--title", title or branch, "--fill"],
                           capture_output=True, text=True, cwd=state.cwd)
        if r.returncode == 0:
            msgs.append(f"PR created: {r.stdout.strip()}")
        else:
            msgs.append(f"Push complete. Create PR manually (gh not available or failed).")

        return CommandResult(output="\n".join(msgs))


def _branch_exists(name: str, cwd: str) -> bool:
    r = subprocess.run(["git", "branch", "--list", name], capture_output=True, text=True, cwd=cwd)
    return bool(r.stdout.strip())


def get_commands() -> list[Command]:
    return [BranchCommand(), CommitCommand(), DiffCommand(), RewindCommand(), CommitPushPRCommand()]
