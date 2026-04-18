"""
Search component — full-text search in transcripts and history.
"""

from __future__ import annotations

import re
from typing import Any

from rich.console import Console
from rich.text import Text


def search_messages(messages: list, query: str,
                    case_sensitive: bool = False) -> list[dict[str, Any]]:
    """Search through conversation messages."""
    from lucy.core.message import UserMessage, AssistantMessage

    results = []
    flags = 0 if case_sensitive else re.IGNORECASE

    for i, msg in enumerate(messages):
        text = msg.get_text()
        role = "user" if isinstance(msg, UserMessage) else "assistant"

        matches = list(re.finditer(re.escape(query), text, flags))
        if matches:
            results.append({
                "index": i,
                "role": role,
                "matches": len(matches),
                "preview": _build_preview(text, matches[0].start(), query),
                "message": msg,
            })

    return results


def render_search_results(console: Console, results: list[dict[str, Any]],
                          query: str) -> None:
    """Render search results."""
    if not results:
        console.print(f"[dim]No results for '{query}'[/dim]")
        return

    console.print(f"[bold]Found {len(results)} message(s) matching '{query}':[/bold]\n")

    for r in results[:20]:
        icon = "👤" if r["role"] == "user" else "🤖"
        t = Text()
        t.append(f"  {icon} Message #{r['index']} ", style="bold")
        t.append(f"({r['matches']} match{'es' if r['matches'] > 1 else ''})", style="dim")
        t.append(f"\n    {r['preview']}\n")
        console.print(t)


def _build_preview(text: str, match_pos: int, query: str, context: int = 60) -> str:
    """Build a preview string around a match position."""
    start = max(0, match_pos - context)
    end = min(len(text), match_pos + len(query) + context)

    preview = text[start:end].replace("\n", " ")
    if start > 0:
        preview = "..." + preview
    if end < len(text):
        preview = preview + "..."

    return preview
