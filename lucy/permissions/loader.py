"""
Permission rule loader — read rules from config files.
"""

from __future__ import annotations

import json
import os
from typing import Any

from lucy.permissions.types import PermissionAction, PermissionRule, PermissionScope


def load_permission_rules(config_dir: str | None = None) -> list[PermissionRule]:
    """Load permission rules from config files.

    Reads from:
    1. ~/.lucycode/permissions.json (global)
    2. .lucycode/permissions.json (project)
    3. CLAUDE.md permission blocks (project)
    """
    rules: list[PermissionRule] = []

    # Default rules
    rules.extend(_default_rules())

    # Global config
    if config_dir is None:
        config_dir = os.path.expanduser("~/.lucycode")

    global_file = os.path.join(config_dir, "permissions.json")
    if os.path.exists(global_file):
        rules.extend(_load_from_file(global_file, PermissionScope.GLOBAL))

    # Project config
    cwd = os.getcwd()
    project_file = os.path.join(cwd, ".lucycode", "permissions.json")
    if os.path.exists(project_file):
        rules.extend(_load_from_file(project_file, PermissionScope.PROJECT))

    return rules


def _load_from_file(path: str, scope: PermissionScope) -> list[PermissionRule]:
    """Load rules from a JSON file."""
    try:
        with open(path) as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError):
        return []

    rules = []
    for item in data.get("rules", []):
        try:
            rule = PermissionRule(
                id=item.get("id", ""),
                tool=item.get("tool", ""),
                command=item.get("command", ""),
                path=item.get("path", ""),
                action=PermissionAction(item.get("action", "ask")),
                scope=scope,
                reason=item.get("reason", ""),
                priority=item.get("priority", 0),
                enabled=item.get("enabled", True),
            )
            rules.append(rule)
        except (ValueError, KeyError):
            continue

    return rules


def save_permission_rules(rules: list[PermissionRule], path: str) -> None:
    """Save rules to a JSON file."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    data = {
        "rules": [
            {
                "id": r.id, "tool": r.tool, "command": r.command,
                "path": r.path, "action": r.action.value,
                "reason": r.reason, "priority": r.priority,
                "enabled": r.enabled,
            }
            for r in rules
        ]
    }
    with open(path, "w") as f:
        json.dump(data, f, indent=2)


def _default_rules() -> list[PermissionRule]:
    """Default built-in permission rules."""
    return [
        # Always allow read-only tools
        PermissionRule(
            id="builtin-allow-read",
            tool="Read", action=PermissionAction.ALLOW,
            reason="File reading is always safe", priority=100,
        ),
        PermissionRule(
            id="builtin-allow-grep",
            tool="Grep*", action=PermissionAction.ALLOW,
            reason="Grep is read-only", priority=100,
        ),
        PermissionRule(
            id="builtin-allow-glob",
            tool="Glob*", action=PermissionAction.ALLOW,
            reason="Glob is read-only", priority=100,
        ),
        PermissionRule(
            id="builtin-allow-lsp",
            tool="LSP", action=PermissionAction.ALLOW,
            reason="LSP queries are read-only", priority=100,
        ),
        # Deny system-level access
        PermissionRule(
            id="builtin-deny-system",
            path="/etc/*", action=PermissionAction.DENY,
            reason="System configuration files", priority=90,
        ),
        PermissionRule(
            id="builtin-deny-usr",
            path="/usr/*", action=PermissionAction.DENY,
            reason="System binaries", priority=90,
        ),
    ]
