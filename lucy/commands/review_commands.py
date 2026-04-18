"""
Review commands — /review, /security-review.
"""

from __future__ import annotations

import subprocess
from typing import Any

from lucy.core.commands import Command, CommandResult


class ReviewCommand(Command):
    @property
    def name(self) -> str: return "review"
    @property
    def aliases(self) -> list[str]: return ["code-review", "cr"]
    @property
    def description(self) -> str: return "Request AI code review of recent changes"
    @property
    def usage(self) -> str: return "/review [file|--staged|--unstaged]"

    async def execute(self, args: str, state: Any) -> CommandResult:
        target = args.strip() or "--staged"
        if target == "--staged":
            diff_cmd = ["git", "diff", "--staged"]
        elif target == "--unstaged":
            diff_cmd = ["git", "diff"]
        else:
            diff_cmd = ["git", "diff", target]

        r = subprocess.run(diff_cmd, capture_output=True, text=True, cwd=state.cwd)
        diff = r.stdout

        if not diff:
            return CommandResult(output="No changes to review. Stage changes with `git add`.")

        # Inject as user message for AI review
        from lucy.core.message import create_user_message
        review_msg = create_user_message(
            f"Please review the following code changes and provide feedback on:\n"
            f"1. Potential bugs\n2. Code quality\n3. Performance\n4. Security\n"
            f"5. Suggestions for improvement\n\n```diff\n{diff}\n```"
        )
        state.messages.append(review_msg)

        return CommandResult(output=f"Requesting review of {len(diff.split(chr(10)))} lines of changes...")


class SecurityReviewCommand(Command):
    @property
    def name(self) -> str: return "security-review"
    @property
    def aliases(self) -> list[str]: return ["sec-review", "security"]
    @property
    def description(self) -> str: return "Run a security-focused code review"
    @property
    def usage(self) -> str: return "/security-review [file|dir]"

    async def execute(self, args: str, state: Any) -> CommandResult:
        target = args.strip() or "."

        # Get file list
        if target == ".":
            r = subprocess.run(["git", "diff", "--name-only", "HEAD"],
                               capture_output=True, text=True, cwd=state.cwd)
            files = r.stdout.strip().split("\n") if r.stdout.strip() else []
        else:
            import os
            if os.path.isfile(os.path.join(state.cwd, target)):
                files = [target]
            else:
                import glob
                files = glob.glob(os.path.join(state.cwd, target, "**/*"), recursive=True)
                files = [os.path.relpath(f, state.cwd) for f in files if os.path.isfile(f)]

        if not files:
            return CommandResult(output="No files to review.")

        # Read content of changed files
        contents = []
        for f in files[:10]:  # Limit to 10 files
            try:
                import os
                full = os.path.join(state.cwd, f)
                with open(full) as fh:
                    contents.append(f"### {f}\n```\n{fh.read()[:5000]}\n```\n")
            except OSError:
                continue

        from lucy.core.message import create_user_message
        msg = create_user_message(
            f"Please perform a SECURITY review of these files. Check for:\n"
            f"1. Injection vulnerabilities (SQL, XSS, command injection)\n"
            f"2. Authentication/authorization issues\n"
            f"3. Sensitive data exposure\n"
            f"4. Insecure dependencies\n"
            f"5. Cryptographic weaknesses\n"
            f"6. Path traversal\n\n" + "\n".join(contents)
        )
        state.messages.append(msg)

        return CommandResult(
            output=f"Requesting security review of {len(files)} file(s)..."
        )


def get_commands() -> list[Command]:
    return [ReviewCommand(), SecurityReviewCommand()]
