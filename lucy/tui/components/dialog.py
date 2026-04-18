"""
Dialog system — generic dialogs for user interaction.
"""

from __future__ import annotations

from rich.console import Console
from rich.panel import Panel
from rich.text import Text


def confirm_dialog(console: Console, title: str, message: str = "",
                   default: bool = False) -> bool:
    """Display a confirmation dialog."""
    default_str = "Y/n" if default else "y/N"
    content = Text()
    content.append(f"❓ {title}\n", style="bold")
    if message:
        content.append(f"\n{message}\n")

    console.print(Panel(content, border_style="yellow"))

    try:
        response = input(f"  [{default_str}]: ").strip().lower()
        if not response:
            return default
        return response in ("y", "yes")
    except (EOFError, KeyboardInterrupt):
        return False


def select_dialog(console: Console, title: str,
                  options: list[str], default: int = 0) -> int | None:
    """Display a selection dialog. Returns index or None."""
    content = Text()
    content.append(f"📋 {title}\n\n", style="bold")
    for i, opt in enumerate(options):
        marker = "→" if i == default else " "
        content.append(f"  {marker} {i + 1}. {opt}\n")

    console.print(Panel(content, border_style="cyan"))

    try:
        response = input(f"  Choice [1-{len(options)}]: ").strip()
        if not response:
            return default
        idx = int(response) - 1
        if 0 <= idx < len(options):
            return idx
        return None
    except (ValueError, EOFError, KeyboardInterrupt):
        return None


def text_input_dialog(console: Console, title: str, default: str = "",
                      multiline: bool = False) -> str | None:
    """Display a text input dialog."""
    content = Text()
    content.append(f"✏️  {title}", style="bold")
    if default:
        content.append(f" [{default}]", style="dim")

    console.print(content)

    try:
        if multiline:
            lines = []
            console.print("[dim]  (Enter empty line to finish)[/dim]")
            while True:
                line = input("  ")
                if not line:
                    break
                lines.append(line)
            return "\n".join(lines) if lines else default
        else:
            response = input("  > ").strip()
            return response if response else default
    except (EOFError, KeyboardInterrupt):
        return None


def multi_select_dialog(console: Console, title: str,
                        options: list[str]) -> list[int]:
    """Display a multi-select dialog. Returns list of selected indices."""
    content = Text()
    content.append(f"☑️  {title}\n\n", style="bold")
    for i, opt in enumerate(options):
        content.append(f"  {i + 1}. {opt}\n")

    console.print(Panel(content, border_style="cyan"))

    try:
        response = input("  Select (comma-separated numbers): ").strip()
        if not response:
            return []
        indices = []
        for part in response.split(","):
            try:
                idx = int(part.strip()) - 1
                if 0 <= idx < len(options):
                    indices.append(idx)
            except ValueError:
                continue
        return indices
    except (EOFError, KeyboardInterrupt):
        return []
