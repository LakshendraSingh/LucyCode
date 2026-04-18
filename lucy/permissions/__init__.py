"""
Permissions system — rule-based permission management.

Provides bash command classification, path validation,
dangerous pattern detection, and permission rule matching.
"""

from lucy.permissions.types import (
    PermissionRule,
    PermissionScope,
    PermissionAction,
    PermissionDecision,
)
from lucy.permissions.rules import RuleEngine, get_rule_engine
from lucy.permissions.loader import load_permission_rules
from lucy.permissions.bash_classifier import classify_bash_command, BashRiskLevel
from lucy.permissions.filesystem import check_path_permission
from lucy.permissions.explainer import explain_permission

__all__ = [
    "PermissionRule", "PermissionScope", "PermissionAction", "PermissionDecision",
    "RuleEngine", "get_rule_engine", "load_permission_rules",
    "classify_bash_command", "BashRiskLevel",
    "check_path_permission", "explain_permission",
]
