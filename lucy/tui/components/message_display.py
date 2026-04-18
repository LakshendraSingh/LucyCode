"""
Message display — rich message rendering with badges and metadata.
"""

from __future__ import annotations

import time
from typing import Any

from rich.console import Console
from rich.panel import Panel
from rich.text import Text


def render_user_message(console: Console, text: str, theme: Any = None) -> None:
    """Render a user message."""
    t = Text()
    t.append("👤 You", style="bold blue")
    t.append(f"\n{text}")
    console.print(Panel(t, border_style="blue", padding=(0, 1)))


def render_assistant_response(console: Console, text: str, model: str = "",
                               cost: float = 0.0, tokens: int = 0,
                               thinking: str = "", theme: Any = None) -> None:
    """Render a complete assistant response with metadata."""
    t = Text()

    # Header with model badge
    t.append("🤖 Lucy", style="bold magenta")
    if model:
        short_model = model.split("-")[0] if "-" in model else model
        t.append(f" [{short_model}]", style="dim magenta")

    t.append(f"\n\n{text}")

    # Footer
    footer_parts = []
    if cost > 0:
        footer_parts.append(f"${cost:.4f}")
    if tokens > 0:
        footer_parts.append(f"{tokens:,} tokens")
    footer = " • ".join(footer_parts)

    console.print(Panel(
        t,
        border_style="magenta",
        padding=(0, 1),
        subtitle=f"[dim]{footer}[/dim]" if footer else None,
    ))


def render_tool_execution(console: Console, tool_name: str,
                          summary: str = "", result: str = "",
                          is_error: bool = False, theme: Any = None) -> None:
    """Render a tool execution block."""
    icon = "❌" if is_error else "⚡"
    style = "red" if is_error else "green"

    t = Text()
    t.append(f"{icon} {tool_name}", style=f"bold {style}")
    if summary:
        t.append(f" — {summary}", style="dim")

    if result:
        t.append(f"\n{result[:500]}", style="dim" if not is_error else "red")

    console.print(Panel(t, border_style=style, padding=(0, 1)))


def render_thinking_block(console: Console, thinking: str, theme: Any = None) -> None:
    """Render a thinking/reasoning block."""
    if not thinking:
        return
    t = Text()
    t.append("💭 Thinking\n", style="bold dim")
    t.append(thinking[:1000], style="dim italic")
    console.print(Panel(t, border_style="dim", padding=(0, 1)))


def render_system_message(console: Console, text: str, style: str = "info") -> None:
    """Render a system message (info, warning, error)."""
    icons = {"info": "ℹ️", "warning": "⚠️", "error": "❌", "success": "✅"}
    styles = {"info": "blue", "warning": "yellow", "error": "red", "success": "green"}
    icon = icons.get(style, "ℹ️")
    color = styles.get(style, "blue")
    console.print(f"[{color}]{icon} {text}[/{color}]")
