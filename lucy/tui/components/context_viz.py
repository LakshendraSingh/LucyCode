"""
Context visualization — display context window state.
"""

from __future__ import annotations

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text


def render_context_viz(console: Console, messages: list,
                       model: str = "", max_tokens: int = 200000) -> None:
    """Visualize the context window state."""
    from lucy.core.message import UserMessage, AssistantMessage

    user_msgs = sum(1 for m in messages if isinstance(m, UserMessage))
    asst_msgs = sum(1 for m in messages if isinstance(m, AssistantMessage))
    total_chars = sum(len(m.get_text()) for m in messages)
    est_tokens = total_chars // 4
    tool_calls = sum(
        len(m.get_tool_use_blocks()) for m in messages
        if isinstance(m, AssistantMessage)
    )

    # Token budget bar
    pct = est_tokens / max(max_tokens, 1) * 100
    width = 40
    filled = int(width * est_tokens / max(max_tokens, 1))
    if pct < 60:
        color = "green"
    elif pct < 85:
        color = "yellow"
    else:
        color = "red"
    bar = "█" * min(filled, width) + "░" * max(0, width - filled)

    t = Text()
    t.append("📊 Context Window\n\n", style="bold")
    t.append(f"  Model: ", style="dim")
    t.append(f"{model}\n", style="cyan")
    t.append(f"  Messages: {user_msgs} user + {asst_msgs} assistant = {len(messages)} total\n")
    t.append(f"  Tool calls: {tool_calls}\n")
    t.append(f"  Characters: {total_chars:,}\n")
    t.append(f"  Est. tokens: {est_tokens:,} / {max_tokens:,} ({pct:.0f}%)\n\n")
    t.append(f"  [{color}][{bar}][/{color}]\n")

    if pct > 80:
        t.append(f"\n  ⚠️  Context window is {pct:.0f}% full. Consider /compact", style="yellow")

    console.print(Panel(t, border_style="blue"))


def render_message_breakdown(console: Console, messages: list) -> None:
    """Show a breakdown of messages by type and size."""
    from lucy.core.message import UserMessage, AssistantMessage

    table = Table(title="Message Breakdown")
    table.add_column("#", justify="right", style="dim")
    table.add_column("Role", style="cyan")
    table.add_column("Chars", justify="right")
    table.add_column("~Tokens", justify="right")
    table.add_column("Tools", justify="right")
    table.add_column("Preview")

    for i, m in enumerate(messages):
        role = "user" if isinstance(m, UserMessage) else "assistant"
        text = m.get_text()
        chars = len(text)
        tokens = chars // 4
        tools = len(m.get_tool_use_blocks()) if isinstance(m, AssistantMessage) else 0
        preview = text[:50].replace("\n", " ")

        table.add_row(str(i), role, f"{chars:,}", f"{tokens:,}",
                       str(tools) if tools else "", preview)

    console.print(table)
