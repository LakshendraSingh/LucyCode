"""
Git utilities — status, diff, commit, branch, worktree operations.
"""

from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass, field
from typing import Any


@dataclass
class GitStatus:
    branch: str = ""
    is_dirty: bool = False
    staged: list[str] = field(default_factory=list)
    unstaged: list[str] = field(default_factory=list)
    untracked: list[str] = field(default_factory=list)
    ahead: int = 0
    behind: int = 0
    remote: str = ""
    last_commit: str = ""


def get_git_status(cwd: str) -> GitStatus | None:
    """Get comprehensive git status."""
    try:
        subprocess.run(["git", "rev-parse", "--git-dir"],
                       cwd=cwd, capture_output=True, check=True)
    except (subprocess.CalledProcessError, FileNotFoundError):
        return None

    status = GitStatus()

    # Branch
    r = subprocess.run(["git", "branch", "--show-current"],
                       cwd=cwd, capture_output=True, text=True)
    status.branch = r.stdout.strip()

    # Status
    r = subprocess.run(["git", "status", "--porcelain"],
                       cwd=cwd, capture_output=True, text=True)
    for line in r.stdout.strip().split("\n"):
        if not line:
            continue
        index = line[0]
        worktree = line[1]
        file = line[3:]

        if index in ("M", "A", "D", "R"):
            status.staged.append(file)
        if worktree in ("M", "D"):
            status.unstaged.append(file)
        if index == "?" and worktree == "?":
            status.untracked.append(file)

    status.is_dirty = bool(status.staged or status.unstaged or status.untracked)

    # Ahead/behind
    r = subprocess.run(["git", "rev-list", "--left-right", "--count", "HEAD...@{upstream}"],
                       cwd=cwd, capture_output=True, text=True)
    if r.returncode == 0 and r.stdout.strip():
        parts = r.stdout.strip().split()
        if len(parts) == 2:
            status.ahead = int(parts[0])
            status.behind = int(parts[1])

    # Remote
    r = subprocess.run(["git", "remote", "get-url", "origin"],
                       cwd=cwd, capture_output=True, text=True)
    status.remote = r.stdout.strip()

    # Last commit
    r = subprocess.run(["git", "log", "-1", "--oneline"],
                       cwd=cwd, capture_output=True, text=True)
    status.last_commit = r.stdout.strip()

    return status


def git_diff(cwd: str, staged: bool = False, file: str = "") -> str:
    """Get git diff output."""
    cmd = ["git", "diff"]
    if staged:
        cmd.append("--staged")
    if file:
        cmd.append(file)
    r = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)
    return r.stdout


def git_log(cwd: str, count: int = 10, oneline: bool = True) -> str:
    """Get git log."""
    cmd = ["git", "log", f"-{count}"]
    if oneline:
        cmd.append("--oneline")
    r = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)
    return r.stdout


def git_stash(cwd: str, message: str = "") -> bool:
    """Stash current changes."""
    cmd = ["git", "stash", "push"]
    if message:
        cmd.extend(["-m", message])
    r = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)
    return r.returncode == 0


def git_stash_pop(cwd: str) -> bool:
    """Pop the last stash."""
    r = subprocess.run(["git", "stash", "pop"], cwd=cwd, capture_output=True, text=True)
    return r.returncode == 0
