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
                                            f"Available: default, auto_accept, plan")
            if rest in ("default", "auto_accept", "plan"):
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


def get_commands() -> list[Command]:
    return [PermissionsCommand()]
