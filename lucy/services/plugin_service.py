"""
Plugin service — plugin installation, validation, and marketplace.
"""

from __future__ import annotations

import json
import os
import shutil
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
    tools: list[dict[str, Any]] = field(default_factory=list)
    commands: list[dict[str, Any]] = field(default_factory=list)
    hooks: list[str] = field(default_factory=list)


class PluginService:
    """Manage plugin installation and validation."""

    def __init__(self, plugins_dir: str | None = None):
        self._dir = plugins_dir or os.path.expanduser("~/.lucycode/plugins")
        os.makedirs(self._dir, exist_ok=True)

    def list_installed(self) -> list[PluginManifest]:
        plugins = []
        if not os.path.exists(self._dir):
            return plugins
        for name in os.listdir(self._dir):
            manifest_path = os.path.join(self._dir, name, "manifest.json")
            if os.path.exists(manifest_path):
                try:
                    manifest = self._load_manifest(manifest_path)
                    plugins.append(manifest)
                except Exception:
                    continue
        return plugins

    def install_from_path(self, source: str, name: str | None = None) -> PluginManifest:
        """Install a plugin from a local directory."""
        manifest_path = os.path.join(source, "manifest.json")
        if not os.path.exists(manifest_path):
            raise ValueError(f"No manifest.json found in {source}")

        manifest = self._load_manifest(manifest_path)
        plugin_name = name or manifest.name

        dest = os.path.join(self._dir, plugin_name)
        if os.path.exists(dest):
            shutil.rmtree(dest)
        shutil.copytree(source, dest)

        return manifest

    def uninstall(self, name: str) -> bool:
        path = os.path.join(self._dir, name)
        if os.path.exists(path):
            shutil.rmtree(path)
            return True
        return False

    def validate(self, name: str) -> list[str]:
        """Validate a plugin. Returns list of issues."""
        issues = []
        path = os.path.join(self._dir, name)

        if not os.path.exists(path):
            return [f"Plugin directory not found: {path}"]

        manifest_path = os.path.join(path, "manifest.json")
        if not os.path.exists(manifest_path):
            issues.append("Missing manifest.json")
            return issues

        try:
            manifest = self._load_manifest(manifest_path)
        except Exception as e:
            issues.append(f"Invalid manifest: {e}")
            return issues

        # Check entry point
        entry = os.path.join(path, manifest.entry_point)
        if not os.path.exists(entry):
            issues.append(f"Entry point not found: {manifest.entry_point}")

        # Check version compatibility
        from lucy import __version__
        # Simple version check
        if manifest.min_lucy_version > __version__:
            issues.append(f"Requires Lucy Code >= {manifest.min_lucy_version}")

        return issues

    def get_manifest(self, name: str) -> PluginManifest | None:
        path = os.path.join(self._dir, name, "manifest.json")
        if os.path.exists(path):
            return self._load_manifest(path)
        return None

    def _load_manifest(self, path: str) -> PluginManifest:
        with open(path) as f:
            data = json.load(f)
        return PluginManifest(
            name=data.get("name", ""),
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
        )


_service: PluginService | None = None


def get_plugin_service() -> PluginService:
    global _service
    if _service is None:
        _service = PluginService()
    return _service
