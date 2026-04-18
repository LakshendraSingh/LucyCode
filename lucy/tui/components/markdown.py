"""
ANSI Markdown renderer — render markdown as rich terminal output.
"""

from __future__ import annotations

import re
from typing import Any

from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.syntax import Syntax
from rich.text import Text


def render_markdown(console: Console, text: str, theme: str = "dark") -> None:
    """Render markdown text with full formatting support."""
    try:
        md = Markdown(text, code_theme="monokai" if theme == "dark" else "friendly")
        console.print(md)
    except Exception:
        # Fallback: basic rendering
        console.print(text)


def render_code_block(console: Console, code: str, language: str = "",
                      title: str = "", theme: str = "dark") -> None:
    """Render a syntax-highlighted code block."""
    code_theme = "monokai" if theme == "dark" else "friendly"
    syntax = Syntax(
        code, language or "text",
        theme=code_theme, line_numbers=True,
        word_wrap=True,
    )
    if title:
        console.print(Panel(syntax, title=title, border_style="blue"))
    else:
        console.print(syntax)


def extract_code_blocks(text: str) -> list[dict[str, str]]:
    """Extract fenced code blocks from markdown."""
    pattern = r'```(\w*)\n(.*?)```'
    blocks = []
    for match in re.finditer(pattern, text, re.DOTALL):
        blocks.append({
            "language": match.group(1),
            "code": match.group(2).strip(),
        })
    return blocks


def render_table(console: Console, headers: list[str],
                 rows: list[list[str]], title: str = "") -> None:
    """Render a formatted table."""
    from rich.table import Table

    table = Table(title=title, show_header=True)
    for h in headers:
        table.add_column(h)
    for row in rows:
        table.add_row(*[str(c) for c in row])
    console.print(table)
