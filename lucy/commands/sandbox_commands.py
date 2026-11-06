"""
/sandbox slash commands — inspect and manage sandbox security profiles.
"""

from __future__ import annotations

import os
from typing import Any

from lucy.core.commands import Command, CommandResult, register_command
from lucy.core.sandbox import SandboxProfile, get_sandbox_manager


class SandboxCommand(Command):
    """Inspect and configure LucyCode's sandbox boundaries."""

    name = "sandbox"
    description = "Manage sandbox security mode and directory isolation (/sandbox on|off|status|mode)"
    aliases = ["jail", "isolate"]

    async def execute(self, args: list[str], state: Any) -> CommandResult:
        mgr = get_sandbox_manager()
        sub = args[0].lower() if args else "status"

        if sub in ("status", "info"):
            status_color = "green" if mgr.is_enabled else "yellow"
            status_text = "ENABLED" if mgr.is_enabled else "DISABLED"

            output_lines = [
                f"\n🔒 Sandbox Status: [{status_color}]{status_text}[/{status_color}]",
                f"  Profile: [bold]{mgr.config.profile.value}[/bold]",
                f"  Workspace Root: {mgr.config.workspace_root}",
                f"  Allowed Write Dirs ({len(mgr.config.allowed_write_dirs)}):",
            ]
            for d in mgr.config.allowed_write_dirs:
                output_lines.append(f"    • {d}")

            output_lines.append("\n  Security Policies Enforced:")
            output_lines.append("    • Host credentials protected (~/.ssh, ~/.aws, ~/.gnupg, keychain, keys)")
            output_lines.append("    • System root writes blocked (/etc, /usr, /bin, /System, /Library)")
            output_lines.append("    • Shell profiles protected (~/.bashrc, ~/.zshrc, ~/.profile)")
            output_lines.append("    • Destructive commands blocked (sudo, su, fork bombs, rm -rf /)")

            output_lines.append("\nUsage: /sandbox <on|off|mode|allow|status>")
            return CommandResult(output="\n".join(output_lines))

        elif sub in ("on", "enable"):
            profile = SandboxProfile.WORKSPACE
            if len(args) > 1:
                try:
                    profile = SandboxProfile(args[1].lower())
                except ValueError:
                    return CommandResult(
                        error=f"Invalid profile '{args[1]}'. Options: workspace, strict, read_only"
                    )
            mgr.enable(profile)
            return CommandResult(
                output=f"✓ Sandbox mode ENABLED with profile: [bold]{profile.value}[/bold]"
            )

        elif sub in ("off", "disable"):
            mgr.disable()
            return CommandResult(output="⚠ Sandbox mode DISABLED.")

        elif sub in ("mode", "profile"):
            if len(args) < 2:
                return CommandResult(
                    error="Please specify profile: /sandbox mode <workspace|strict|read_only>"
                )
            try:
                prof = SandboxProfile(args[1].lower())
                mgr.set_profile(prof)
                if not mgr.is_enabled:
                    mgr.enable(prof)
                return CommandResult(
                    output=f"✓ Sandbox profile switched to: [bold]{prof.value}[/bold]"
                )
            except ValueError:
                return CommandResult(
                    error=f"Invalid profile '{args[1]}'. Available: workspace, strict, read_only"
                )

        elif sub in ("allow", "add"):
            if len(args) < 2:
                return CommandResult(error="Please specify path: /sandbox allow <directory_path>")
            target = os.path.abspath(os.path.expanduser(args[1]))
            if target not in mgr.config.allowed_write_dirs:
                mgr.config.allowed_write_dirs.append(target)
                return CommandResult(output=f"✓ Added allowed write directory: {target}")
            return CommandResult(output=f"Path already in allowed write list: {target}")

        return CommandResult(
            error="Unknown subcommand. Available: /sandbox <status|on|off|mode|allow>"
        )


def get_commands() -> list[Command]:
    return [SandboxCommand()]


def register_sandbox_commands() -> None:
    register_command(SandboxCommand())
