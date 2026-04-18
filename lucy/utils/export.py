"""
Export utilities — export conversations to various formats.
"""

from __future__ import annotations

import json
import os
import time
from typing import Any


def export_markdown(messages: list, metadata: dict[str, Any] | None = None) -> str:
    """Export conversation to markdown."""
    from lucy.core.message import UserMessage, AssistantMessage
    lines = ["# Lucy Code Conversation\n"]

    if metadata:
        lines.append(f"- **Model**: {metadata.get('model', 'unknown')}")
        lines.append(f"- **Date**: {time.strftime('%Y-%m-%d %H:%M')}")
        if metadata.get("session_id"):
            lines.append(f"- **Session**: {metadata['session_id'][:8]}")
        lines.append("")

    for msg in messages:
        role = "User" if isinstance(msg, UserMessage) else "Assistant"
        text = msg.get_text()
        lines.append(f"## {role}")
        lines.append("")
        lines.append(text)
        lines.append("")

        if isinstance(msg, AssistantMessage):
            for tu in msg.get_tool_use_blocks():
                lines.append(f"> 🔧 **Tool**: {tu.name}")
                lines.append(f"> ```json")
                lines.append(f"> {json.dumps(tu.input, indent=2)[:500]}")
                lines.append(f"> ```")
                lines.append("")

    return "\n".join(lines)


def export_json(messages: list, metadata: dict[str, Any] | None = None) -> str:
    """Export conversation to JSON."""
    from lucy.core.message import UserMessage, AssistantMessage
    entries = []
    for msg in messages:
        role = "user" if isinstance(msg, UserMessage) else "assistant"
        entry = {"role": role, "content": msg.get_text()}
        if isinstance(msg, AssistantMessage):
            tools = msg.get_tool_use_blocks()
            if tools:
                entry["tool_calls"] = [
                    {"name": t.name, "input": t.input} for t in tools
                ]
        entries.append(entry)

    data = {"metadata": metadata or {}, "messages": entries}
    return json.dumps(data, indent=2, ensure_ascii=False)


def export_html(messages: list, metadata: dict[str, Any] | None = None) -> str:
    """Export conversation to HTML."""
    from lucy.core.message import UserMessage, AssistantMessage
    title = metadata.get("title", "Lucy Code Conversation") if metadata else "Lucy Code Conversation"

    html = [f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>{title}</title>
<style>
body {{ font-family: system-ui, sans-serif; max-width: 800px; margin: 0 auto; padding: 20px; background: #1a1a2e; color: #eee; }}
.user {{ background: #16213e; padding: 16px; border-radius: 12px; margin: 12px 0; border-left: 4px solid #4a9eff; }}
.assistant {{ background: #0f3460; padding: 16px; border-radius: 12px; margin: 12px 0; border-left: 4px solid #e94560; }}
.role {{ font-weight: bold; margin-bottom: 8px; }}
.tool {{ background: #1a1a3e; padding: 8px; border-radius: 6px; margin: 8px 0; font-size: 0.9em; }}
pre {{ background: #0d1117; padding: 12px; border-radius: 6px; overflow-x: auto; }}
code {{ font-family: 'SF Mono', monospace; }}
</style></head><body>
<h1>{title}</h1>"""]

    for msg in messages:
        role = "user" if isinstance(msg, UserMessage) else "assistant"
        text = msg.get_text().replace("<", "&lt;").replace(">", "&gt;")
        text = text.replace("\n", "<br>")
        html.append(f'<div class="{role}"><div class="role">{"👤 You" if role == "user" else "🤖 Lucy"}</div>{text}</div>')

    html.append("</body></html>")
    return "\n".join(html)


def export_to_file(messages: list, path: str, fmt: str = "markdown",
                   metadata: dict[str, Any] | None = None) -> str:
    """Export to a file. Returns the path."""
    exporters = {
        "markdown": export_markdown,
        "md": export_markdown,
        "json": export_json,
        "html": export_html,
    }
    exporter = exporters.get(fmt, export_markdown)
    content = exporter(messages, metadata)

    os.makedirs(os.path.dirname(path) if os.path.dirname(path) else ".", exist_ok=True)
    with open(path, "w") as f:
        f.write(content)

    return path
