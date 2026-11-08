"""
Permission commands — /permissions.
"""

from __future__ import annotations

from typing import Any

from lucy.core.commands import Command, CommandResult


class PermissionsCommand(Command):
    @property
    def name(self) -> str: return "permissions"
    @property
    def aliases(self) -> list[str]: return ["perms"]
    @property
    def description(self) -> str: return "Manage permission rules"
    @property
    def usage(self) -> str: return "/permissions [list|mode|allow|deny] [args]"

    async def execute(self, args: str, state: Any) -> CommandResult:
        parts = args.strip().split(None, 1)
        action = parts[0] if parts else "list"
        rest = parts[1] if len(parts) > 1 else ""

        if action == "list":
            from lucy.permissions.rules import get_rule_engine
            engine = get_rule_engine()
            rules = engine.get_rules()
            if not rules:
                return CommandResult(output="No permission rules configured.")
            lines = ["Permission Rules:\n"]
            for r in rules:
                status = "✓" if r.enabled else "✗"
                lines.append(f"  {status} [{r.action.value}] tool={r.tool or '*'} "
                             f"cmd={r.command or '*'} path={r.path or '*'}")
                if r.reason:
                    lines.append(f"    Reason: {r.reason}")
            denials = engine.get_denials()
            if denials:
                lines.append(f"\nRecent denials: {len(denials)}")
            return CommandResult(output="\n".join(lines))

        if action == "mode":
            if not rest:
                return CommandResult(output=f"Current mode: {state.permission_mode}\n"
                                            f"Available: default, auto_accept, plan, autonomous")
            if rest in ("default", "auto_accept", "plan", "autonomous"):
                if rest == "autonomous":
                    state.autonomous = True
                    state.permission_mode = "auto_accept"
                    return CommandResult(output="Permission mode: autonomous (auto-accept + zero mid-task prompts)")
                else:
                    if getattr(state, "autonomous", False):
                        state.autonomous = False
                    state.permission_mode = rest
                    return CommandResult(output=f"Permission mode: {rest}")
            return CommandResult(error=f"Unknown mode: {rest}")

        if action in ("allow", "deny"):
            from lucy.permissions.types import PermissionRule, PermissionAction
            from lucy.permissions.rules import get_rule_engine
            tool = rest or "*"
            rule = PermissionRule(
                tool=tool,
                action=PermissionAction.ALLOW if action == "allow" else PermissionAction.DENY,
                reason=f"User-configured via /permissions {action}",
            )
            get_rule_engine().add_rule(rule)
            return CommandResult(output=f"Added rule: {action} tool={tool}")

        return CommandResult(error=f"Unknown action: {action}")


class AutonomousCommand(Command):
    @property
    def name(self) -> str: return "autonomous"
    @property
    def aliases(self) -> list[str]: return ["auto", "no-prompt", "unattended"]
    @property
    def description(self) -> str: return "Toggle autonomous mode (never ask user questions mid-task)"
    @property
    def usage(self) -> str: return "/autonomous [on|off|status]"

    async def execute(self, args: str, state: Any) -> CommandResult:
        arg = args.strip().lower()
        current = getattr(state, "autonomous", False)

        if arg in ("on", "enable", "true", "1"):
            target = True
        elif arg in ("off", "disable", "false", "0"):
            target = False
        elif arg in ("status", ""):
            if not arg:
                target = not current
            else:
                status_str = "ENABLED (Auto-accepting actions, zero mid-task prompts)" if current else "DISABLED"
                return CommandResult(output=f"Autonomous mode: {status_str}")
        else:
            return CommandResult(error=f"Usage: {self.usage}")

        state.autonomous = target
        if target:
            state.permission_mode = "auto_accept"
            return CommandResult(
                output="Autonomous mode ENABLED: Lucy will not ask mid-task questions or pause for confirmations. Actions auto-accepted."
            )
        else:
            state.permission_mode = "default"
            return CommandResult(
                output="Autonomous mode DISABLED: Interactive confirmations and prompts restored."
            )


def get_commands() -> list[Command]:
    return [PermissionsCommand(), AutonomousCommand()]
