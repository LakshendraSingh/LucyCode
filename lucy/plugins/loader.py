"""
Plugin loader — discover and load plugins from directories.
"""

from __future__ import annotations

import importlib
import importlib.util
import json
import logging
import os
import sys
from typing import Any

from lucy.plugins.manifest import parse_manifest, PluginManifest

logger = logging.getLogger(__name__)


class LoadedPlugin:
    def __init__(self, manifest: PluginManifest, module: Any = None):
        self.manifest = manifest
        self.module = module
        self.enabled = True
        self.tools: list = []
        self.commands: list = []

    @property
    def name(self) -> str:
        return self.manifest.name

    @property
    def version(self) -> str:
        return self.manifest.version


class PluginLoader:
    """Discover and load plugins."""

    def __init__(self, plugins_dir: str | None = None):
        self._dir = plugins_dir or os.path.expanduser("~/.lucycode/plugins")
        self._plugins: dict[str, LoadedPlugin] = {}

    def discover(self) -> list[PluginManifest]:
        """Discover all plugins in the plugins directory."""
        manifests = []
        if not os.path.exists(self._dir):
            return manifests

        for name in os.listdir(self._dir):
            path = os.path.join(self._dir, name)
            if not os.path.isdir(path):
                continue
            manifest_path = os.path.join(path, "manifest.json")
            if os.path.exists(manifest_path):
                try:
                    manifest = parse_manifest(manifest_path)
                    manifests.append(manifest)
                except Exception as e:
                    logger.warning("Failed to parse manifest for %s: %s", name, e)

        return manifests

    def load_all(self) -> int:
        """Load all discovered plugins. Returns count loaded."""
        manifests = self.discover()
        loaded = 0

        for manifest in manifests:
            try:
                self.load(manifest)
                loaded += 1
            except Exception as e:
                logger.error("Failed to load plugin %s: %s", manifest.name, e)

        return loaded

    def load(self, manifest: PluginManifest) -> LoadedPlugin:
        """Load a single plugin."""
        plugin_dir = os.path.join(self._dir, manifest.name)
        entry_point = os.path.join(plugin_dir, manifest.entry_point)

        if not os.path.exists(entry_point):
            raise FileNotFoundError(f"Plugin entry point not found: {entry_point}")

        # Dynamic import
        spec = importlib.util.spec_from_file_location(
            f"lucy_plugin_{manifest.name}", entry_point,
        )
        if spec is None or spec.loader is None:
            raise ImportError(f"Cannot load plugin: {manifest.name}")

        module = importlib.util.module_from_spec(spec)
        sys.modules[f"lucy_plugin_{manifest.name}"] = module
        spec.loader.exec_module(module)

        plugin = LoadedPlugin(manifest=manifest, module=module)

        # Register tools
        if hasattr(module, "get_tools"):
            plugin.tools = module.get_tools()

        # Register commands
        if hasattr(module, "get_commands"):
            plugin.commands = module.get_commands()

        self._plugins[manifest.name] = plugin
        logger.info("Loaded plugin: %s v%s", manifest.name, manifest.version)

        return plugin

    def unload(self, name: str) -> bool:
        plugin = self._plugins.pop(name, None)
        if plugin:
            sys.modules.pop(f"lucy_plugin_{name}", None)
            return True
        return False

    def get(self, name: str) -> LoadedPlugin | None:
        return self._plugins.get(name)

    def get_all(self) -> list[LoadedPlugin]:
        return list(self._plugins.values())

    def reload_all(self) -> int:
        """Unload all plugins and reload."""
        names = list(self._plugins.keys())
        for name in names:
            self.unload(name)
        return self.load_all()

    def get_all_tools(self) -> list:
        """Get all tools from all loaded plugins."""
        tools = []
        for plugin in self._plugins.values():
            tools.extend(plugin.tools)
        return tools

    def get_all_commands(self) -> list:
        """Get all commands from all loaded plugins."""
        commands = []
        for plugin in self._plugins.values():
            commands.extend(plugin.commands)
        return commands


_loader: PluginLoader | None = None


def get_plugin_loader() -> PluginLoader:
    global _loader
    if _loader is None:
        _loader = PluginLoader()
    return _loader
