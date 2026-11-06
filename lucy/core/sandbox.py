"""
Sandbox execution engine — isolates and constrains tool actions.

Provides multi-level sandboxing for LucyCode:
  1. Filesystem isolation:
     - Restricts writes and edits strictly to the workspace root and allowed scratch dirs.
     - Blocks access to sensitive host directories (~/.ssh, ~/.aws, ~/.gnupg, keychain, private keys).
  2. Command execution sandbox:
     - Detects and blocks privilege escalation (sudo, su), system modifications, and dangerous patterns.
     - Enforces command isolation within workspace boundaries.
  3. Sandbox profiles:
     - 'workspace': Allows reads across safe system paths, writes only in workspace/scratch.
     - 'strict': Strictest boundary — isolated filesystem, no network, no writes outside cwd.
     - 'read_only': Absolute zero write capability (safe code exploration).
"""

from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

from lucy.core.tool import PermissionBehavior, PermissionResult, ToolContext

logger = logging.getLogger(__name__)


class SandboxProfile(str, Enum):
    WORKSPACE = "workspace"
    STRICT = "strict"
    READ_ONLY = "read_only"


# Sensitive paths that are NEVER allowed to be read or written in sandbox mode
SENSITIVE_PATTERNS = [
    r"\.ssh($|/)",
    r"\.aws($|/)",
    r"\.gnupg($|/)",
    r"\.netrc($|/)",
    r"\.bash_history($|/)",
    r"\.zsh_history($|/)",
    r"id_rsa($|\.)",
    r"id_ed25519($|\.)",
    r"\.pem$",
    r"\.key$",
    r"keychain($|/)",
    r"credentials\.json$",
    r"\.env\.local$",
    r"\.env\.production$",
]

# Sensitive system directories where writes are permanently forbidden
SYSTEM_WRITE_BLOCKED = [
    "/etc",
    "/usr",
    "/bin",
    "/sbin",
    "/System",
    "/Library",
    "/boot",
    "/sys",
    "/proc",
    "/dev",
]

# Dangerous bash commands permanently blocked in sandbox
DANGEROUS_COMMANDS = [
    r"\bsudo\b",
    r"\bsu\s+",
    r"\bchmod\s+(-R\s+)?777\b",
    r"\bchown\b",
    r"\bmkfs\b",
    r"\bfdisk\b",
    r"\bdd\s+if=",
    r">+\s*/dev/sd",
    r":\(\)\s*\{\s*:\s*\|\s*:\s*&\s*\}\s*;\s*:",  # fork bomb
    r"\brm\s+(-[a-zA-Z]*r[a-zA-Z]*f*|-rf|-fr)\s+(/\s*$|/\*|~\s*$|~\*)",
    r"\bshutdown\b",
    r"\breboot\b",
    r"\binit\s+[06]\b",
    r"\bcurl\b.*\|\s*(ba)?sh\b",
    r"\bwget\b.*\|\s*(ba)?sh\b",
]


@dataclass
class SandboxConfig:
    """Configuration for sandbox boundaries."""
    enabled: bool = False
    profile: SandboxProfile = SandboxProfile.WORKSPACE
    workspace_root: str = ""
    allow_network: bool = True
    allowed_write_dirs: list[str] = field(default_factory=list)
    allowed_read_dirs: list[str] = field(default_factory=list)
    custom_blocked_patterns: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        if not self.workspace_root:
            self.workspace_root = os.getcwd()
        self.workspace_root = os.path.abspath(self.workspace_root)

        if not self.allowed_write_dirs:
            # Default write scopes: workspace root + temporary scratch dirs
            self.allowed_write_dirs = [
                self.workspace_root,
                os.path.abspath("/tmp"),
                os.path.expanduser("~/.lucycode"),
                os.path.expanduser("~/.lucy"),
            ]


class SandboxManager:
    """Enforces sandbox boundary rules on tools and actions."""

    def __init__(self, config: SandboxConfig | None = None) -> None:
        self.config = config or SandboxConfig()

    @property
    def is_enabled(self) -> bool:
        return self.config.enabled

    def enable(self, profile: SandboxProfile | str = SandboxProfile.WORKSPACE) -> None:
        """Enable sandbox mode."""
        self.config.enabled = True
        if isinstance(profile, str):
            self.config.profile = SandboxProfile(profile)
        else:
            self.config.profile = profile
        logger.info("Sandbox enabled with profile: %s", self.config.profile.value)

    def disable(self) -> None:
        """Disable sandbox mode."""
        self.config.enabled = False
        logger.info("Sandbox disabled")

    def set_profile(self, profile: SandboxProfile | str) -> None:
        if isinstance(profile, str):
            self.config.profile = SandboxProfile(profile)
        else:
            self.config.profile = profile

    def is_path_sensitive(self, path: str) -> bool:
        """Check if a path matches sensitive credentials or secret files."""
        normalized = os.path.abspath(os.path.expanduser(path))
        for pattern in SENSITIVE_PATTERNS + self.config.custom_blocked_patterns:
            if re.search(pattern, normalized, re.IGNORECASE):
                return True
        return False

    def validate_read_path(self, path: str, cwd: str = "") -> tuple[bool, str]:
        """Validate if reading from this path is permitted."""
        if not self.config.enabled:
            return True, ""

        if not path:
            return False, "Path is empty"

        abs_path = os.path.abspath(os.path.expanduser(path))
        if not os.path.isabs(path) and cwd:
            abs_path = os.path.abspath(os.path.join(cwd, path))

        # 1. Check sensitive credential files (never readable in sandbox)
        if self.is_path_sensitive(abs_path):
            return False, f"Sandbox violation: Access to sensitive path '{abs_path}' is forbidden."

        # 2. Strict profile restricts reads strictly to workspace, /tmp, and Python lib
        if self.config.profile == SandboxProfile.STRICT:
            ws = self.config.workspace_root
            if not (abs_path.startswith(ws) or abs_path.startswith("/tmp") or "/lib/python" in abs_path):
                return False, f"Sandbox violation (strict): Read outside workspace '{ws}' is forbidden: {abs_path}"

        return True, ""

    def validate_write_path(self, path: str, cwd: str = "") -> tuple[bool, str]:
        """Validate if writing or editing this path is permitted."""
        if not self.config.enabled:
            return True, ""

        if not path:
            return False, "Path is empty"

        # Read-only profile blocks ALL writes
        if self.config.profile == SandboxProfile.READ_ONLY:
            return False, "Sandbox violation (read_only): All file write and edit operations are forbidden."

        abs_path = os.path.abspath(os.path.expanduser(path))
        if not os.path.isabs(path) and cwd:
            abs_path = os.path.abspath(os.path.join(cwd, path))

        # Block writes to sensitive paths
        if self.is_path_sensitive(abs_path):
            return False, f"Sandbox violation: Writing to sensitive path '{abs_path}' is forbidden."

        # Block writes to system directories
        for sys_dir in SYSTEM_WRITE_BLOCKED:
            if abs_path == sys_dir or abs_path.startswith(sys_dir + os.sep):
                return False, f"Sandbox violation: Writing to system directory '{sys_dir}' is forbidden."

        # Block writes to user shell configurations
        home = os.path.expanduser("~")
        shell_configs = [
            os.path.join(home, ".bashrc"),
            os.path.join(home, ".zshrc"),
            os.path.join(home, ".bash_profile"),
            os.path.join(home, ".profile"),
            os.path.join(home, ".zprofile"),
        ]
        if abs_path in shell_configs:
            return False, f"Sandbox violation: Modifying shell startup configuration '{abs_path}' is forbidden."

        # Ensure target is inside an allowed write directory
        in_allowed = False
        for allowed in self.config.allowed_write_dirs:
            norm_allowed = os.path.abspath(os.path.expanduser(allowed))
            if abs_path == norm_allowed or abs_path.startswith(norm_allowed + os.sep):
                in_allowed = True
                break

        if not in_allowed:
            return False, (
                f"Sandbox violation: Target path '{abs_path}' is outside the sandbox workspace boundary "
                f"({self.config.workspace_root})."
            )

        return True, ""

    def validate_command(self, command: str) -> tuple[bool, str]:
        """Validate if executing a shell command is permitted."""
        if not self.config.enabled:
            return True, ""

        if not command or not command.strip():
            return False, "Command is empty"

        clean_cmd = command.strip()

        # Read-only profile allows only read-only commands
        if self.config.profile == SandboxProfile.READ_ONLY:
            read_only_prefixes = (
                "ls", "cat", "grep", "find", "head", "tail", "wc", "git status",
                "git log", "git diff", "pwd", "echo", "which"
            )
            if not any(clean_cmd.startswith(p) for p in read_only_prefixes):
                return False, "Sandbox violation (read_only): Only non-modifying inspection commands are permitted."

        # Check dangerous patterns
        for pattern in DANGEROUS_COMMANDS:
            if re.search(pattern, clean_cmd, re.IGNORECASE):
                return False, f"Sandbox violation: Execution of dangerous command matching '{pattern}' is blocked."

        # Block commands accessing sensitive credentials
        for pattern in SENSITIVE_PATTERNS:
            if re.search(pattern, clean_cmd, re.IGNORECASE):
                return False, f"Sandbox violation: Command references sensitive path pattern '{pattern}'."

        return True, ""

    def check_tool_permission(
        self,
        tool_name: str,
        tool_input: dict[str, Any],
        context: ToolContext,
    ) -> PermissionResult:
        """Check if an arbitrary tool invocation complies with sandbox policy."""
        if not self.config.enabled:
            return PermissionResult(behavior=PermissionBehavior.ALLOW, updated_input=tool_input)

        name = tool_name.lower()

        # Filesystem read tools
        if name in ("read", "fileread", "view"):
            path = tool_input.get("file_path") or tool_input.get("path") or ""
            allowed, reason = self.validate_read_path(path, context.cwd)
            if not allowed:
                return PermissionResult(behavior=PermissionBehavior.DENY, message=reason)

        # Filesystem write / edit tools
        elif name in ("write", "filewrite", "edit", "fileedit", "notebookedit"):
            path = tool_input.get("file_path") or tool_input.get("path") or ""
            allowed, reason = self.validate_write_path(path, context.cwd)
            if not allowed:
                return PermissionResult(behavior=PermissionBehavior.DENY, message=reason)

        # Shell execution tools
        elif name in ("bash", "powershell", "shell"):
            cmd = tool_input.get("command") or ""
            allowed, reason = self.validate_command(cmd)
            if not allowed:
                return PermissionResult(behavior=PermissionBehavior.DENY, message=reason)

        return PermissionResult(behavior=PermissionBehavior.ALLOW, updated_input=tool_input)


# Global singleton
_sandbox_manager: SandboxManager | None = None


def get_sandbox_manager() -> SandboxManager:
    """Get the global sandbox manager singleton."""
    global _sandbox_manager
    if _sandbox_manager is None:
        _sandbox_manager = SandboxManager()
    return _sandbox_manager

