"""
Rich-based terminal renderer — markdown, code blocks, tool output.
"""

from __future__ import annotations

from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.syntax import Syntax
from rich.text import Text
from rich.rule import Rule

from lucy.core.message import (
    AssistantMessage,
    TextBlock,
    ThinkingBlock,
    ToolUseBlock,
)
from lucy.tui.theme import Theme, get_theme


def create_console() -> Console:
    """Create a Rich console for output."""
    return Console(highlight=False)


def render_assistant_message(
    console: Console,
    message: AssistantMessage,
    theme: Theme | None = None,
    show_thinking: bool = True,
    verbose: bool = False,
) -> None:
    """Render an assistant message to the console."""
    theme = theme or get_theme()

    for block in message.content:
        if isinstance(block, ThinkingBlock) and show_thinking and block.thinking:
            console.print(
                Panel(
                    Text(block.thinking, style=theme.thinking),
                    title="[dim]Thinking[/dim]",
                    border_style=theme.dim,
                    expand=True,
                    padding=(0, 1),
                )
            )
        elif isinstance(block, TextBlock) and block.text:
            console.print(Markdown(block.text))
        elif isinstance(block, ToolUseBlock):
            _render_tool_use(console, block, theme)


def render_tool_result(
    console: Console,
    tool_name: str,
    result: str,
    is_error: bool = False,
    theme: Theme | None = None,
) -> None:
    """Render a tool result."""
    theme = theme or get_theme()
    style = theme.tool_error if is_error else theme.tool_result
    title = f"[{theme.tool_name}]{tool_name}[/{theme.tool_name}]"
    if is_error:
        title += " [red](error)[/red]"

    # Truncate for display
    display_result = result
    if len(display_result) > 3000:
        display_result = display_result[:3000] + "\n... (truncated for display)"

    console.print(
        Panel(
            Text(display_result, style=style),
            title=title,
            border_style=theme.dim,
            expand=True,
            padding=(0, 1),
        )
    )


def render_streaming_text(console: Console, text: str) -> None:
    """Print streaming text (no newline)."""
    console.print(text, end="", highlight=False)


def render_error(console: Console, message: str, theme: Theme | None = None) -> None:
    """Render an error message."""
    theme = theme or get_theme()
    console.print(f"[{theme.error}]✗ {message}[/{theme.error}]")


def render_info(console: Console, message: str, theme: Theme | None = None) -> None:
    """Render an info message."""
    theme = theme or get_theme()
    console.print(f"[{theme.info}]{message}[/{theme.info}]")


def render_success(console: Console, message: str, theme: Theme | None = None) -> None:
    """Render a success message."""
    theme = theme or get_theme()
    console.print(f"[{theme.success}]✓ {message}[/{theme.success}]")


def render_separator(console: Console, theme: Theme | None = None) -> None:
    """Render a horizontal rule."""
    theme = theme or get_theme()
    console.print(Rule(style=theme.dim))


def render_welcome(console: Console, model: str, theme: Theme | None = None) -> None:
    """Render the welcome banner."""
    theme = theme or get_theme()
    from lucy import __version__

    console.print()
    console.print(
        Panel(
            Text.from_markup(
                f"[bold {theme.primary}]Lucy Code[/bold {theme.primary}] "
                f"[{theme.dim}]v{__version__}[/{theme.dim}]\n"
                f"[{theme.dim}]Model: [/{theme.dim}]"
                f"[{theme.secondary}]{model}[/{theme.secondary}]\n"
                f"[{theme.dim}]Type /help for commands • Ctrl+C to interrupt • /exit to quit[/{theme.dim}]"
            ),
            border_style=theme.primary,
            padding=(1, 2),
        )
    )
    console.print()


def _render_tool_use(console: Console, block: ToolUseBlock, theme: Theme) -> None:
    """Render a tool_use block."""
    import json

    # Format input
    input_str = json.dumps(block.input, indent=2, default=str)
    if len(input_str) > 500:
        input_str = input_str[:500] + "\n..."

    console.print(
        f"[{theme.tool_name}]⚡ {block.name}[/{theme.tool_name}] "
        f"[{theme.dim}]{_summarize_tool_input(block)}[/{theme.dim}]"
    )


def _summarize_tool_input(block: ToolUseBlock) -> str:
    """Create a one-line summary of tool input."""
    inp = block.input
    if block.name in ("Bash",):
        return inp.get("command", "")[:80]
    if block.name in ("Read", "FileRead", "ReadFile"):
        return inp.get("file_path", "")
    if block.name in ("Write", "FileWrite", "WriteFile"):
        return inp.get("file_path", "")
    if block.name in ("Edit", "FileEdit"):
        return inp.get("file_path", "")
    if block.name in ("Grep", "GrepTool", "Search"):
        return f"'{inp.get('pattern', '')}'"
    if block.name in ("Glob", "GlobTool", "FindFiles"):
        return inp.get("pattern", "")
    return ""
