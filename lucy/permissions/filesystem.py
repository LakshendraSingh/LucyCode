"""
Filesystem permission checks — path validation and scope enforcement.
"""

from __future__ import annotations

import os
from typing import Any

from lucy.permissions.types import PermissionAction, PermissionCheck, PermissionDecision


def check_path_permission(
    path: str,
    cwd: str,
    additional_dirs: list[str] | None = None,
    action: str = "read",
) -> PermissionCheck:
    """Check if accessing a path is permitted.

    Validates that the path is within the allowed scope:
    - Current working directory
    - Additional directories
    - Home directory config files
    """
    abs_path = os.path.abspath(path) if not os.path.isabs(path) else path
    abs_cwd = os.path.abspath(cwd)
    allowed_dirs = [abs_cwd] + [os.path.abspath(d) for d in (additional_dirs or [])]

    # Always allow home config dirs
    home = os.path.expanduser("~")
    config_dirs = [
        os.path.join(home, ".lucycode"),
        os.path.join(home, ".config"),
        os.path.join(home, ".ssh"),  # read-only
        os.path.join(home, ".gitconfig"),
    ]

    # Check if within allowed directories
    for allowed in allowed_dirs:
        if abs_path.startswith(allowed):
            return PermissionCheck(
                decision=PermissionDecision.ALLOWED,
                explanation=f"Within working directory: {allowed}",
                path=abs_path,
            )

    # Config dirs — read always OK, write only in .lucycode
    for cfg in config_dirs:
        if abs_path.startswith(cfg):
            if action == "read":
                return PermissionCheck(
                    decision=PermissionDecision.ALLOWED,
                    explanation=f"Reading config: {cfg}",
                    path=abs_path,
                )
            if cfg.endswith(".lucycode"):
                return PermissionCheck(
                    decision=PermissionDecision.ALLOWED,
                    explanation="Writing Lucy config",
                    path=abs_path,
                )

    # System paths — always deny writes
    system_dirs = ["/etc", "/usr", "/bin", "/sbin", "/var", "/System", "/Library"]
    if action != "read":
        for sys_dir in system_dirs:
            if abs_path.startswith(sys_dir):
                return PermissionCheck(
                    decision=PermissionDecision.DENIED,
                    explanation=f"Cannot write to system directory: {sys_dir}",
                    path=abs_path,
                )

    # Outside project — needs approval
    return PermissionCheck(
        decision=PermissionDecision.NEEDS_APPROVAL,
        explanation=f"Path is outside project directory: {abs_path}",
        path=abs_path,
    )


def is_path_within_scope(path: str, scope_dirs: list[str]) -> bool:
    """Check if a path is within any of the given scope directories."""
    abs_path = os.path.abspath(path)
    for scope in scope_dirs:
        if abs_path.startswith(os.path.abspath(scope)):
            return True
    return False


def validate_path_safety(path: str) -> tuple[bool, str]:
    """Validate that a path is safe to access."""
    abs_path = os.path.abspath(path)

    # Prevent traversal
    if ".." in path:
        resolved = os.path.realpath(path)
        if resolved != abs_path:
            return False, f"Path traversal detected: {path} -> {resolved}"

    # Prevent symlink attacks
    if os.path.islink(abs_path):
        target = os.path.realpath(abs_path)
        # Allow if target is also within scope
        return True, f"Symlink to: {target}"

    # Prevent access to sensitive files
    sensitive = [".env", ".aws/credentials", ".ssh/id_rsa", ".ssh/id_ed25519",
                 ".netrc", ".npmrc", ".pypirc"]
    basename = os.path.basename(abs_path)
    for s in sensitive:
        if abs_path.endswith(s) or basename == s:
            return False, f"Sensitive file: {s}"

    return True, "OK"
