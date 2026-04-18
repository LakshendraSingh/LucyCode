"""
Permission explainer — human-readable explanations of permission decisions.
"""

from __future__ import annotations

from lucy.permissions.types import PermissionCheck, PermissionDecision


def explain_permission(check: PermissionCheck) -> str:
    """Generate a human-readable explanation of a permission decision."""
    parts = []

    # Decision
    icon = {
        "allowed": "✅",
        "denied": "❌",
        "needs_approval": "⚠️",
    }.get(check.decision.value, "?")

    parts.append(f"{icon} Permission {check.decision.value.replace('_', ' ')}")

    # What was checked
    if check.tool_name:
        parts.append(f"  Tool: {check.tool_name}")
    if check.command:
        parts.append(f"  Command: {check.command[:100]}")
    if check.path:
        parts.append(f"  Path: {check.path}")

    # Why
    if check.explanation:
        parts.append(f"  Reason: {check.explanation}")

    # Rule info
    if check.rule:
        parts.append(f"  Matched rule: {check.rule.id or 'unnamed'}")
        if check.rule.reason:
            parts.append(f"  Rule reason: {check.rule.reason}")

    return "\n".join(parts)


def format_permission_prompt(check: PermissionCheck) -> str:
    """Format a permission approval prompt for the user."""
    lines = [f"⚠️  Permission required"]

    if check.tool_name:
        lines.append(f"  Tool: {check.tool_name}")
    if check.command:
        cmd_preview = check.command[:200]
        lines.append(f"  Command: {cmd_preview}")
    if check.path:
        lines.append(f"  Path: {check.path}")
    if check.explanation:
        lines.append(f"  Reason: {check.explanation}")

    lines.append("\n  [y] Allow  [n] Deny  [a] Always allow  [s] Allow for session")
    return "\n".join(lines)
