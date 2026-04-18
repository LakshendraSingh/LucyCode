"""
Plugin architecture — extensible commands, tools, hooks, and MCP servers.

Plugins are directories containing a plugin.json manifest that can provide:
  - Custom tools
  - Custom slash commands
  - Hook definitions
  - MCP server configurations
  - Skills (prompt templates)

Plugins can be loaded from:
  - Built-in (bundled with Lucy Code)
  - Local directory (~/.lucy/plugins/)
  - Git repositories
"""

from __future__ import annotations

import json
import logging
import os
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from lucy.core.config import get_config

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Plugin manifest
# ---------------------------------------------------------------------------

@dataclass
class PluginManifest:
    """Plugin manifest (from plugin.json)."""
    name: str = ""
    description: str = ""
    version: str = "0.0.1"
    author: str = ""
    # Component declarations
    tools: list[dict[str, Any]] = field(default_factory=list)
    commands: list[dict[str, Any]] = field(default_factory=list)
    hooks: dict[str, list[dict[str, Any]]] = field(default_factory=dict)
    mcp_servers: dict[str, dict[str, Any]] = field(default_factory=dict)
    skills: list[dict[str, Any]] = field(default_factory=list)
    # Plugin settings schema
    settings_schema: dict[str, Any] = field(default_factory=dict)
    # Dependencies
    dependencies: list[str] = field(default_factory=list)


@dataclass
class LoadedPlugin:
    """A fully loaded plugin."""
    name: str
    manifest: PluginManifest
    path: str
    source: str  # "builtin", "local", "git:<url>"
    enabled: bool = True
    is_builtin: bool = False
    errors: list[str] = field(default_factory=list)

    @property
    def id(self) -> str:
        return f"{self.name}@{self.source}"


# ---------------------------------------------------------------------------
# Plugin loader
# ---------------------------------------------------------------------------

class PluginLoader:
    """Loads plugins from various sources."""

    def __init__(self) -> None:
        self._plugins: list[LoadedPlugin] = []
        self._errors: list[str] = []

    def load_from_directory(self, directory: str) -> list[LoadedPlugin]:
        """Load all plugins from a directory."""
        plugins: list[LoadedPlugin] = []
        dir_path = Path(directory)

        if not dir_path.exists():
            return plugins

        for entry in sorted(dir_path.iterdir()):
            if not entry.is_dir():
                continue
            manifest_path = entry / "plugin.json"
            if not manifest_path.exists():
                continue

            plugin = self._load_single_plugin(str(entry), "local")
            if plugin:
                plugins.append(plugin)

        return plugins

    def load_builtin_plugins(self) -> list[LoadedPlugin]:
        """Load built-in plugins that ship with Lucy Code."""
        # Built-in plugins are defined in code, not on disk
        return []

    def _load_single_plugin(self, path: str, source: str) -> LoadedPlugin | None:
        """Load a single plugin from a directory."""
        manifest_path = Path(path) / "plugin.json"

        try:
            with open(manifest_path) as f:
                raw = json.load(f)
        except (json.JSONDecodeError, OSError) as e:
            self._errors.append(f"Failed to load {manifest_path}: {e}")
            return None

        manifest = PluginManifest(
            name=raw.get("name", Path(path).name),
            description=raw.get("description", ""),
            version=raw.get("version", "0.0.1"),
            author=raw.get("author", ""),
            tools=raw.get("tools", []),
            commands=raw.get("commands", []),
            hooks=raw.get("hooks", {}),
            mcp_servers=raw.get("mcpServers", {}),
            skills=raw.get("skills", []),
            settings_schema=raw.get("settingsSchema", {}),
            dependencies=raw.get("dependencies", []),
        )

        plugin = LoadedPlugin(
            name=manifest.name,
            manifest=manifest,
            path=path,
            source=source,
            is_builtin=(source == "builtin"),
        )

        # Validate
        errors = validate_plugin(plugin)
        plugin.errors = errors
        if errors:
            for err in errors:
                logger.warning("Plugin %s: %s", manifest.name, err)

        return plugin

    @property
    def loaded_plugins(self) -> list[LoadedPlugin]:
        return list(self._plugins)

    @property
    def load_errors(self) -> list[str]:
        return list(self._errors)


def validate_plugin(plugin: LoadedPlugin) -> list[str]:
    """Validate a loaded plugin."""
    errors: list[str] = []
    if not plugin.name:
        errors.append("Plugin name is required")
    if not plugin.manifest.description:
        errors.append("Plugin description is recommended")
    return errors


# ---------------------------------------------------------------------------
# Plugin manager
# ---------------------------------------------------------------------------

class PluginManager:
    """Manages the lifecycle of plugins."""

    def __init__(self) -> None:
        self._loader = PluginLoader()
        self._plugins: dict[str, LoadedPlugin] = {}
        self._initialized = False

    def initialize(self) -> None:
        """Load all plugins from configured sources."""
        if self._initialized:
            return

        config = get_config()
        plugins_dir = config.config_dir / "plugins"

        # Load from plugins directory
        if plugins_dir.exists():
            for plugin in self._loader.load_from_directory(str(plugins_dir)):
                self._plugins[plugin.id] = plugin

        # Load built-in plugins
        for plugin in self._loader.load_builtin_plugins():
            self._plugins[plugin.id] = plugin

        self._initialized = True
        logger.info("Loaded %d plugins", len(self._plugins))

    def get_plugin(self, name: str) -> LoadedPlugin | None:
        """Get a plugin by name."""
        for plugin in self._plugins.values():
            if plugin.name == name:
                return plugin
        return None

    def get_all_plugins(self) -> list[LoadedPlugin]:
        """Get all loaded plugins."""
        return list(self._plugins.values())

    def get_enabled_plugins(self) -> list[LoadedPlugin]:
        """Get all enabled plugins."""
        return [p for p in self._plugins.values() if p.enabled]

    def enable_plugin(self, name: str) -> bool:
        plugin = self.get_plugin(name)
        if plugin:
            plugin.enabled = True
            return True
        return False

    def disable_plugin(self, name: str) -> bool:
        plugin = self.get_plugin(name)
        if plugin:
            plugin.enabled = False
            return True
        return False

    def install_plugin(self, source: str) -> LoadedPlugin | None:
        """Install a plugin from a source (local path or git URL)."""
        config = get_config()
        plugins_dir = config.config_dir / "plugins"
        plugins_dir.mkdir(parents=True, exist_ok=True)

        if os.path.isdir(source):
            plugin = self._loader._load_single_plugin(source, "local")
            if plugin:
                self._plugins[plugin.id] = plugin
            return plugin

        # Git clone support
        if source.startswith("git:") or source.startswith("https://") or source.startswith("http://"):
            import subprocess
            
            # Process git: URL format or regular https URL
            git_url = source
            if source.startswith("git:"):
                git_url = source[4:]
            
            # Use name from URL as directory name
            name = git_url.split("/")[-1]
            if name.endswith(".git"):
                name = name[:-4]
            
            dest_path = plugins_dir / name
            
            if dest_path.exists():
                logger.info("Plugin already exists at %s, pulling updates...", dest_path)
                try:
                    subprocess.run(["git", "-C", str(dest_path), "pull"], check=True)
                except Exception as e:
                    logger.error("Failed to pull updates: %s", e)
                    return None
            else:
                logger.info("Cloning plugin from %s into %s", git_url, dest_path)
                try:
                    subprocess.run(["git", "clone", git_url, str(dest_path)], check=True)
                except Exception as e:
                    logger.error("Failed to clone plugin: %s", e)
                    return None

            plugin = self._loader._load_single_plugin(str(dest_path), f"git:{git_url}")
            if plugin:
                self._plugins[plugin.id] = plugin
            return plugin

        return None

    def get_all_hooks(self) -> list[dict[str, Any]]:
        """Collect hook definitions from all enabled plugins."""
        all_hooks: list[dict[str, Any]] = []
        for plugin in self.get_enabled_plugins():
            for event, hooks in plugin.manifest.hooks.items():
                for hook in hooks:
                    hook_copy = dict(hook)
                    hook_copy["_plugin"] = plugin.name
                    hook_copy["_event"] = event
                    all_hooks.append(hook_copy)
        return all_hooks

    def get_all_mcp_servers(self) -> dict[str, dict[str, Any]]:
        """Collect MCP server configs from all enabled plugins."""
        servers: dict[str, dict[str, Any]] = {}
        for plugin in self.get_enabled_plugins():
            for name, config_data in plugin.manifest.mcp_servers.items():
                key = f"{plugin.name}/{name}"
                servers[key] = config_data
        return servers

    # --- Facade methods used by /plugin commands ---

    def list_plugins(self) -> list[dict[str, Any]]:
        """List plugins as dicts for display."""
        self.initialize()
        return [
            {
                "name": p.name,
                "version": p.manifest.version,
                "description": p.manifest.description,
                "enabled": p.enabled,
                "source": p.source,
            }
            for p in self._plugins.values()
        ]

    def install(self, name_or_path: str) -> None:
        """Install by name (from plugin dir) or path."""
        config = get_config()
        source = config.config_dir / "plugins" / name_or_path
        if source.exists():
            plugin = self.install_plugin(str(source))
            if not plugin:
                raise ValueError(f"Failed to install: {name_or_path}")
        elif os.path.isdir(name_or_path):
            plugin = self.install_plugin(name_or_path)
            if not plugin:
                raise ValueError(f"Failed to install: {name_or_path}")
        else:
            raise ValueError(f"Plugin source not found: {name_or_path}")

    def remove(self, name: str) -> None:
        """Remove a plugin."""
        plugin = self.get_plugin(name)
        if plugin:
            self._plugins.pop(plugin.id, None)
            import shutil
            if os.path.exists(plugin.path):
                shutil.rmtree(plugin.path)
        else:
            raise ValueError(f"Plugin not found: {name}")

    def get_info(self, name: str) -> dict[str, Any] | None:
        """Get plugin info as dict."""
        plugin = self.get_plugin(name)
        if plugin:
            return {
                "name": plugin.name,
                "version": plugin.manifest.version,
                "description": plugin.manifest.description,
                "author": plugin.manifest.author,
                "source": plugin.source,
                "path": plugin.path,
                "enabled": plugin.enabled,
                "errors": plugin.errors,
                "tools": plugin.manifest.tools,
                "commands": plugin.manifest.commands,
            }
        return None

    def reload_all(self) -> int:
        """Reload all plugins."""
        self._plugins.clear()
        self._initialized = False
        self.initialize()
        return len(self._plugins)


# Global singleton
_plugin_manager: PluginManager | None = None


def get_plugin_manager() -> PluginManager:
    global _plugin_manager
    if _plugin_manager is None:
        _plugin_manager = PluginManager()
    return _plugin_manager
