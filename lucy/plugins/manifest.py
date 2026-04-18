"""
Plugin manifest — parsing and validation.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from typing import Any


@dataclass
class PluginManifest:
    name: str
    version: str = "0.1.0"
    description: str = ""
    author: str = ""
    license: str = ""
    entry_point: str = "plugin.py"
    dependencies: list[str] = field(default_factory=list)
    min_lucy_version: str = "0.3.0"
    tools: list[dict[str, str]] = field(default_factory=list)
    commands: list[dict[str, str]] = field(default_factory=list)
    hooks: list[str] = field(default_factory=list)
    permissions: list[str] = field(default_factory=list)
    repository: str = ""
    homepage: str = ""
    tags: list[str] = field(default_factory=list)


def parse_manifest(path: str) -> PluginManifest:
    """Parse a manifest.json file into a PluginManifest."""
    with open(path) as f:
        data = json.load(f)

    return PluginManifest(
        name=data.get("name", os.path.basename(os.path.dirname(path))),
        version=data.get("version", "0.1.0"),
        description=data.get("description", ""),
        author=data.get("author", ""),
        license=data.get("license", ""),
        entry_point=data.get("entry_point", "plugin.py"),
        dependencies=data.get("dependencies", []),
        min_lucy_version=data.get("min_lucy_version", "0.3.0"),
        tools=data.get("tools", []),
        commands=data.get("commands", []),
        hooks=data.get("hooks", []),
        permissions=data.get("permissions", []),
        repository=data.get("repository", ""),
        homepage=data.get("homepage", ""),
        tags=data.get("tags", []),
    )


def validate_manifest(manifest: PluginManifest) -> list[str]:
    """Validate a manifest. Returns list of issues."""
    issues = []

    if not manifest.name:
        issues.append("Missing required field: name")
    if not manifest.name.replace("-", "").replace("_", "").isalnum():
        issues.append("Name must be alphanumeric (hyphens/underscores OK)")
    if not manifest.version:
        issues.append("Missing required field: version")
    if not manifest.entry_point:
        issues.append("Missing required field: entry_point")

    # Version format
    parts = manifest.version.split(".")
    if len(parts) != 3 or not all(p.isdigit() for p in parts):
        issues.append("Version must be semver (e.g., 1.0.0)")

    return issues


def create_manifest_template(name: str, path: str) -> str:
    """Create a template manifest.json for a new plugin."""
    manifest = {
        "name": name,
        "version": "0.1.0",
        "description": f"{name} plugin for Lucy Code",
        "author": "",
        "license": "MIT",
        "entry_point": "plugin.py",
        "dependencies": [],
        "min_lucy_version": "1.0.0",
        "tools": [],
        "commands": [],
        "hooks": [],
        "permissions": [],
        "tags": [],
    }

    os.makedirs(path, exist_ok=True)
    manifest_path = os.path.join(path, "manifest.json")
    with open(manifest_path, "w") as f:
        json.dump(manifest, f, indent=2)

    # Create entry point
    entry_path = os.path.join(path, "plugin.py")
    with open(entry_path, "w") as f:
        f.write(f'"""\n{name} plugin for Lucy Code.\n"""\n\n\n'
                f'def get_tools():\n    """Return list of Tool instances."""\n    return []\n\n\n'
                f'def get_commands():\n    """Return list of Command instances."""\n    return []\n')

    return manifest_path
