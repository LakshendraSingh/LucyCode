"""
Permission rule engine — evaluate rules against tool invocations.
"""

from __future__ import annotations

import logging
import time
from typing import Any

from lucy.permissions.types import (
    DenialRecord,
    PermissionAction,
    PermissionCheck,
    PermissionDecision,
    PermissionRule,
    PermissionScope,
)

logger = logging.getLogger(__name__)


class RuleEngine:
    """Evaluate permission rules against tool invocations."""

    def __init__(self):
        self._rules: list[PermissionRule] = []
        self._denials: list[DenialRecord] = []
        self._session_allows: set[str] = set()  # Cached "always allow" for session

    def add_rule(self, rule: PermissionRule) -> None:
        self._rules.append(rule)
        self._rules.sort(key=lambda r: r.priority, reverse=True)

    def set_rules(self, rules: list[PermissionRule]) -> None:
        self._rules = sorted(rules, key=lambda r: r.priority, reverse=True)

    def clear_rules(self) -> None:
        self._rules.clear()

    def get_rules(self) -> list[PermissionRule]:
        return list(self._rules)

    def check(self, tool_name: str, command: str = "", path: str = "",
              permission_mode: str = "default") -> PermissionCheck:
        """Check if an action is allowed."""
        # Auto-accept mode
        if permission_mode == "auto_accept":
            return PermissionCheck(
                decision=PermissionDecision.ALLOWED,
                explanation="Auto-accept mode",
                tool_name=tool_name,
                command=command,
                path=path,
            )

        # Plan mode — deny all writes
        if permission_mode == "plan":
            return PermissionCheck(
                decision=PermissionDecision.DENIED,
                explanation="Plan mode — only read-only operations allowed",
                tool_name=tool_name,
                command=command,
                path=path,
            )

        # Check session allows cache
        cache_key = f"{tool_name}:{command}:{path}"
        if cache_key in self._session_allows:
            return PermissionCheck(
                decision=PermissionDecision.ALLOWED,
                explanation="Previously allowed this session",
                tool_name=tool_name,
                command=command,
                path=path,
            )

        # Evaluate rules (highest priority first)
        for rule in self._rules:
            if not rule.enabled:
                continue
            if (rule.matches_tool(tool_name) and
                    rule.matches_command(command) and
                    rule.matches_path(path)):
                if rule.action == PermissionAction.ALLOW:
                    return PermissionCheck(
                        decision=PermissionDecision.ALLOWED,
                        rule=rule,
                        explanation=rule.reason or f"Allowed by rule: {rule.id}",
                        tool_name=tool_name,
                        command=command,
                        path=path,
                    )
                elif rule.action == PermissionAction.DENY:
                    self._record_denial(tool_name, command, path, rule.reason)
                    return PermissionCheck(
                        decision=PermissionDecision.DENIED,
                        rule=rule,
                        explanation=rule.reason or f"Denied by rule: {rule.id}",
                        tool_name=tool_name,
                        command=command,
                        path=path,
                    )
                elif rule.action == PermissionAction.ASK:
                    return PermissionCheck(
                        decision=PermissionDecision.NEEDS_APPROVAL,
                        rule=rule,
                        explanation=rule.reason or "Requires user approval",
                        tool_name=tool_name,
                        command=command,
                        path=path,
                    )

        # Default: ask for non-read-only tools
        return PermissionCheck(
            decision=PermissionDecision.NEEDS_APPROVAL,
            explanation="No matching rule — requires approval",
            tool_name=tool_name,
            command=command,
            path=path,
        )

    def allow_for_session(self, tool_name: str, command: str = "", path: str = "") -> None:
        """Cache an allow for the rest of the session."""
        self._session_allows.add(f"{tool_name}:{command}:{path}")

    def _record_denial(self, tool_name: str, command: str, path: str, reason: str) -> None:
        self._denials.append(DenialRecord(
            tool_name=tool_name,
            command=command,
            path=path,
            reason=reason,
            timestamp=time.time(),
        ))

    def get_denials(self) -> list[DenialRecord]:
        return list(self._denials)

    def get_denial_count(self) -> int:
        return len(self._denials)

    def clear_session(self) -> None:
        self._session_allows.clear()
        self._denials.clear()


# Global singleton
_engine = RuleEngine()


def get_rule_engine() -> RuleEngine:
    return _engine
