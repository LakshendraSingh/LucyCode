"""
Progress display — progress bars and task progress.
"""

from __future__ import annotations

from rich.console import Console
from rich.progress import (
    BarColumn,
    Progress,
    SpinnerColumn,
    TaskProgressColumn,
    TextColumn,
    TimeElapsedColumn,
    TimeRemainingColumn,
)


def create_progress() -> Progress:
    """Create a rich progress bar."""
    return Progress(
        SpinnerColumn(),
        TextColumn("[bold blue]{task.description}"),
        BarColumn(bar_width=40),
        TaskProgressColumn(),
        TimeElapsedColumn(),
        TimeRemainingColumn(),
    )


def render_progress_bar(console: Console, current: int, total: int,
                        label: str = "Progress") -> None:
    """Render a simple inline progress bar."""
    width = 30
    filled = int(width * current / max(total, 1))
    bar = "█" * filled + "░" * (width - filled)
    pct = current / max(total, 1) * 100
    console.print(f"  {label}: [{bar}] {pct:.0f}% ({current}/{total})")


def render_token_budget(console: Console, used: int, budget: int,
                        label: str = "Context") -> None:
    """Render a token budget bar."""
    pct = used / max(budget, 1) * 100
    width = 30
    filled = int(width * used / max(budget, 1))

    if pct < 60:
        color = "green"
    elif pct < 85:
        color = "yellow"
    else:
        color = "red"

    bar = "█" * min(filled, width) + "░" * max(0, width - filled)
    console.print(f"  {label}: [{color}][{bar}][/{color}] "
                  f"{used:,}/{budget:,} ({pct:.0f}%)")
