"""
Diff viewer — structured diff display with syntax highlighting.
"""

from __future__ import annotations

from rich.console import Console
from rich.panel import Panel
from rich.syntax import Syntax
from rich.text import Text


def render_diff(console: Console, diff: str, title: str = "Changes") -> None:
    """Render a unified diff with color highlighting."""
    lines = diff.split("\n")
    text = Text()

    for line in lines:
        if line.startswith("+++") or line.startswith("---"):
            text.append(line + "\n", style="bold")
        elif line.startswith("@@"):
            text.append(line + "\n", style="cyan")
        elif line.startswith("+"):
            text.append(line + "\n", style="green")
        elif line.startswith("-"):
            text.append(line + "\n", style="red")
        else:
            text.append(line + "\n", style="dim")

    console.print(Panel(text, title=title, border_style="blue"))


def render_file_diff(console: Console, old_content: str, new_content: str,
                     filename: str, language: str = "") -> None:
    """Render a side-by-side comparison of old and new content."""
    import difflib

    diff = difflib.unified_diff(
        old_content.splitlines(keepends=True),
        new_content.splitlines(keepends=True),
        fromfile=f"a/{filename}",
        tofile=f"b/{filename}",
        lineterm="",
    )
    diff_str = "\n".join(diff)

    if diff_str:
        render_diff(console, diff_str, title=filename)
    else:
        console.print(f"[dim]No changes in {filename}[/dim]")


def format_diff_stats(diff: str) -> str:
    """Format diff statistics (added/removed lines)."""
    added = sum(1 for line in diff.split("\n") if line.startswith("+") and not line.startswith("+++"))
    removed = sum(1 for line in diff.split("\n") if line.startswith("-") and not line.startswith("---"))
    return f"[green]+{added}[/green] [red]-{removed}[/red]"
