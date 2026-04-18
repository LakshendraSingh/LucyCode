"""
Logging utilities.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path


def setup_logging(verbose: bool = False, debug: bool = False) -> None:
    """Configure logging for the application."""
    level = logging.DEBUG if debug else (logging.INFO if verbose else logging.WARNING)

    # File handler — always writes to ~/.lucy/logs/
    log_dir = Path.home() / ".lucy" / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / "lucy.log"

    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        handlers=[
            logging.FileHandler(log_file, mode="a"),
        ],
    )

    # Only add console handler in debug mode
    if debug:
        console_handler = logging.StreamHandler()
        console_handler.setLevel(logging.DEBUG)
        console_handler.setFormatter(
            logging.Formatter("%(levelname)s: %(message)s")
        )
        logging.getLogger().addHandler(console_handler)


def get_logger(name: str) -> logging.Logger:
    """Get a named logger."""
    return logging.getLogger(name)
