"""
Permission dialog — interactive permission approval UI.
"""

from __future__ import annotations

from rich.console import Console
from rich.panel import Panel
from rich.text import Text

from lucy.permissions.bash_classifier import BashRiskLevel, classify_bash_command


def render_permission_dialog(
    console: Console,
    tool_name: str,
    description: str,
    command: str = "",
    path: str = "",
    theme: str = "dark",
) -> str:
    """Display a permission dialog and get user response.

    Returns: 'y' (yes), 'n' (no), 'a' (always), 's' (session)
    """
    # Classify risk if bash command
    risk_text = ""
    if command:
        risk, reason = classify_bash_command(command)
        risk_colors = {
            "safe": "green", "low": "green",
            "medium": "yellow", "high": "red",
            "critical": "bold red",
        }
        risk_text = f"\n  Risk: [{risk_colors.get(risk.value, 'yellow')}]{risk.value}[/] — {reason}"

    # Build dialog
    content = Text()
    content.append("⚠️  Permission Required\n\n", style="bold yellow")
    content.append(f"  Tool: ", style="dim")
    content.append(f"{tool_name}\n", style="bold cyan")

    if description:
        content.append(f"  Action: ", style="dim")
        content.append(f"{description}\n")

    if command:
        content.append(f"  Command: ", style="dim")
        cmd_preview = command[:200]
        content.append(f"{cmd_preview}\n", style="bold")

    if path:
        content.append(f"  Path: ", style="dim")
        content.append(f"{path}\n")

    console.print(Panel(content, border_style="yellow", title="Permission"))

    if risk_text:
        console.print(risk_text)

    console.print(
        "\n  [bold][y][/bold] Allow  "
        "[bold][n][/bold] Deny  "
        "[bold][a][/bold] Always allow  "
        "[bold][s][/bold] Allow for session"
    )

    try:
        response = input("  Choice [y/n/a/s]: ").strip().lower()
        if response in ("y", "yes"):
            return "y"
        elif response in ("a", "always"):
            return "a"
        elif response in ("s", "session"):
            return "s"
        else:
            return "n"
    except (EOFError, KeyboardInterrupt):
        return "n"
