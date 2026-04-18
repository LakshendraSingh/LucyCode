"""
Configuration management.

Reads settings from (in priority order):
  1. Environment variables
  2. CLI arguments
  3. Config file (~/.lucy/config.json)
  4. Defaults
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


# ---------------------------------------------------------------------------
# Defaults
# ---------------------------------------------------------------------------

DEFAULT_MODEL = "claude-sonnet-4-20250514"
DEFAULT_MAX_TOKENS = 16384
DEFAULT_MAX_THINKING_TOKENS = 10000
DEFAULT_TIMEOUT_SECONDS = 120
DEFAULT_MAX_RETRIES = 3

CONFIG_DIR = Path.home() / ".lucycode"
CONFIG_FILE = CONFIG_DIR / "config.json"
SESSIONS_DIR = CONFIG_DIR / "sessions"
OLD_CONFIG_DIR = Path.home() / ".opencode"


# ---------------------------------------------------------------------------
# Config dataclass
# ---------------------------------------------------------------------------

@dataclass
class Config:
    """Application configuration."""

    # API
    api_key: str = ""
    base_url: str = "https://api.anthropic.com"
    model: str = DEFAULT_MODEL
    max_tokens: int = DEFAULT_MAX_TOKENS
    max_thinking_tokens: int = DEFAULT_MAX_THINKING_TOKENS
    timeout: int = DEFAULT_TIMEOUT_SECONDS
    max_retries: int = DEFAULT_MAX_RETRIES

    # Behavior
    verbose: bool = False
    debug: bool = False
    permission_mode: str = "default"  # default | auto_accept | plan
    thinking_enabled: bool = True

    # Paths
    config_dir: Path = field(default_factory=lambda: CONFIG_DIR)
    sessions_dir: Path = field(default_factory=lambda: SESSIONS_DIR)

    # UI
    theme: str = "dark"
    show_cost: bool = False
    show_tokens: bool = False

    # Proxy
    http_proxy: str = ""
    https_proxy: str = ""


def load_config(
    cli_args: dict[str, Any] | None = None,
) -> Config:
    """Load configuration from environment, file, and CLI args.

    Priority: env > CLI args > config file > defaults.
    """
    # ── 0. Migration ──
    if not CONFIG_DIR.exists() and OLD_CONFIG_DIR.exists():
        import shutil
        try:
            # Create parent if needed
            CONFIG_DIR.parent.mkdir(parents=True, exist_ok=True)
            # Copy old directory to new one
            shutil.copytree(OLD_CONFIG_DIR, CONFIG_DIR, dirs_exist_ok=True)
            # Update permissions
            os.chmod(CONFIG_DIR, 0o700)
        except Exception:
            pass # Fail silently, user can re-init

    config = Config()

    # ── 1. Config file ──
    if CONFIG_FILE.exists():
        try:
            with open(CONFIG_FILE) as f:
                file_config = json.load(f)
            _apply_dict(config, file_config)
        except (json.JSONDecodeError, OSError):
            pass  # Ignore corrupt config

    # ── 2. CLI args ──
    if cli_args:
        _apply_dict(config, cli_args)

    # ── 3. Environment variables (highest priority) ──
    env_map = {
        "ANTHROPIC_API_KEY": "api_key",
        "ANTHROPIC_BASE_URL": "base_url",
        "LUCY_MODEL": "model",
        "CLAUDE_MODEL": "model",
        "LUCY_MAX_TOKENS": ("max_tokens", int),
        "LUCY_TIMEOUT": ("timeout", int),
        "LUCY_VERBOSE": ("verbose", _str_to_bool),
        "LUCY_DEBUG": ("debug", _str_to_bool),
        "LUCY_THEME": "theme",
        "LUCY_PERMISSION_MODE": "permission_mode",
        "HTTP_PROXY": "http_proxy",
        "HTTPS_PROXY": "https_proxy",
        "http_proxy": "http_proxy",
        "https_proxy": "https_proxy",
        # Offline model hosts
        "OLLAMA_HOST": "ollama_host",
        "OPENAI_BASE_URL": "openai_base_url",
        "OPENAI_API_KEY": "openai_api_key",
        "OPENAI_API_BASE": "openai_base_url",
        "LLAMACPP_HOST": "llamacpp_host",
    }

    for env_key, target in env_map.items():
        val = os.environ.get(env_key)
        if val is None:
            continue
        if isinstance(target, tuple):
            attr_name, converter = target
            try:
                setattr(config, attr_name, converter(val))
            except (ValueError, TypeError):
                pass
        else:
            # For new offline host fields, store as extra attrs
            if target in ("ollama_host", "openai_base_url", "openai_api_key", "llamacpp_host"):
                setattr(config, target, val)
            else:
                setattr(config, target, val)

    # Auto-detect: if no API key and no offline model set, default to Ollama
    if not config.api_key and config.model == DEFAULT_MODEL:
        from lucy.api.models import DEFAULT_OFFLINE_MODEL
        config.model = DEFAULT_OFFLINE_MODEL

    # Ensure directories exist
    config.config_dir.mkdir(parents=True, exist_ok=True)
    config.sessions_dir.mkdir(parents=True, exist_ok=True)

    return config



def save_config(config: Config) -> None:
    """Save configuration to the config file."""
    config.config_dir.mkdir(parents=True, exist_ok=True)
    data = {
        "model": config.model,
        "max_tokens": config.max_tokens,
        "theme": config.theme,
        "permission_mode": config.permission_mode,
        "thinking_enabled": config.thinking_enabled,
        "show_cost": config.show_cost,
        "show_tokens": config.show_tokens,
        "verbose": config.verbose,
    }
    with open(CONFIG_FILE, "w") as f:
        json.dump(data, f, indent=2)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _str_to_bool(s: str) -> bool:
    return s.lower() in ("1", "true", "yes", "on")


def _apply_dict(config: Config, d: dict[str, Any]) -> None:
    """Apply a dict of settings to a Config object."""
    for key, val in d.items():
        if hasattr(config, key) and val is not None:
            expected_type = type(getattr(config, key))
            if expected_type == bool and isinstance(val, str):
                val = _str_to_bool(val)
            elif expected_type == int and isinstance(val, str):
                try:
                    val = int(val)
                except ValueError:
                    continue
            setattr(config, key, val)


# Global singleton
_config: Config | None = None


def get_config() -> Config:
    """Get the global config (load on first access)."""
    global _config
    if _config is None:
        _config = load_config()
    return _config


def set_config(config: Config) -> None:
    """Set the global config (for testing or CLI override)."""
    global _config
    _config = config
