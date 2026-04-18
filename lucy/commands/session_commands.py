"""
Session commands — /session, /resume, /rename, /share, /export, /tag.
"""

from __future__ import annotations

import json
import os
from typing import Any

from lucy.core.commands import Command, CommandResult


class SessionCommand(Command):
    @property
    def name(self) -> str: return "session"
    @property
    def aliases(self) -> list[str]: return ["sessions"]
    @property
    def description(self) -> str: return "Manage sessions"
    @property
    def usage(self) -> str: return "/session [list|info|delete] [id]"

    async def execute(self, args: str, state: Any) -> CommandResult:
        from lucy.utils.session import list_sessions
        parts = args.strip().split(None, 1)
        action = parts[0] if parts else "list"

        if action == "list":
            sessions = list_sessions(limit=20)
            if not sessions:
                return CommandResult(output="No sessions found.")
            lines = [f"{'ID':<38} {'Title':<40} {'Messages':>8}"]
            lines.append("─" * 90)
            for s in sessions:
                title = (s.title or s.first_prompt or "Untitled")[:40]
                lines.append(f"{s.session_id:<38} {title:<40} {s.message_count:>8}")
            return CommandResult(output="\n".join(lines))

        if action == "info":
            sid = parts[1] if len(parts) > 1 else state.conversation_id
            return CommandResult(output=f"Session: {sid}\nMessages: {len(state.messages)}")

        if action == "delete":
            sid = parts[1] if len(parts) > 1 else ""
            if not sid:
                return CommandResult(error="Usage: /session delete <id>")
            from lucy.utils.session import delete_session
            if delete_session(sid):
                return CommandResult(output=f"Deleted session: {sid}")
            return CommandResult(error=f"Session not found: {sid}")

        return CommandResult(error=f"Unknown action: {action}")


class ResumeCommand(Command):
    @property
    def name(self) -> str: return "resume"
    @property
    def description(self) -> str: return "Resume a previous session"
    @property
    def usage(self) -> str: return "/resume <session_id>"

    async def execute(self, args: str, state: Any) -> CommandResult:
        sid = args.strip()
        if not sid:
            return CommandResult(error="Usage: /resume <session_id>")
        from lucy.utils.session import load_session
        msgs, info = load_session(sid)
        if msgs:
            state.messages = msgs
            state.conversation_id = sid
            return CommandResult(output=f"Resumed session ({len(msgs)} messages)")
        return CommandResult(error=f"Session not found: {sid}")


class RenameCommand(Command):
    @property
    def name(self) -> str: return "rename"
    @property
    def description(self) -> str: return "Rename the current session"
    @property
    def usage(self) -> str: return "/rename <new title>"

    async def execute(self, args: str, state: Any) -> CommandResult:
        title = args.strip()
        if not title:
            return CommandResult(error="Usage: /rename <new title>")
        state.session_title = title
        from lucy.utils.session import save_metadata
        save_metadata(session_id=state.conversation_id, title=title,
                      model=state.model, cwd=state.cwd, total_cost=state.cost.total_cost)
        return CommandResult(output=f"Session renamed to: {title}")


class ExportCommand(Command):
    @property
    def name(self) -> str: return "export"
    @property
    def description(self) -> str: return "Export conversation to a file"
    @property
    def usage(self) -> str: return "/export [format] [path] — formats: markdown, json, html"

    async def execute(self, args: str, state: Any) -> CommandResult:
        parts = args.strip().split()
        fmt = parts[0] if parts else "markdown"
        path = parts[1] if len(parts) > 1 else f"lucy-export-{state.conversation_id[:8]}.{_ext(fmt)}"

        if not os.path.isabs(path):
            path = os.path.join(state.cwd, path)

        from lucy.core.message import UserMessage, AssistantMessage
        content = _format_messages(state.messages, fmt)

        with open(path, "w") as f:
            f.write(content)

        return CommandResult(output=f"Exported to: {path}")


class TagCommand(Command):
    @property
    def name(self) -> str: return "tag"
    @property
    def description(self) -> str: return "Add tags to the current session"
    @property
    def usage(self) -> str: return "/tag <tag1> [tag2] ..."

    async def execute(self, args: str, state: Any) -> CommandResult:
        tags = args.strip().split()
        if not tags:
            return CommandResult(error="Usage: /tag <tag1> [tag2] ...")
        if not hasattr(state, 'tags'):
            state.tags = []
        state.tags.extend(tags)
        return CommandResult(output=f"Tags: {', '.join(state.tags)}")


class ShareCommand(Command):
    @property
    def name(self) -> str: return "share"
    @property
    def description(self) -> str: return "Share session (export as markdown)"
    @property
    def usage(self) -> str: return "/share [path]"

    async def execute(self, args: str, state: Any) -> CommandResult:
        path = args.strip() or f"lucy-session-{state.conversation_id[:8]}.md"
        if not os.path.isabs(path):
            path = os.path.join(state.cwd, path)

        from lucy.core.message import UserMessage, AssistantMessage
        content = _format_messages(state.messages, "markdown")
        with open(path, "w") as f:
            f.write(content)
        return CommandResult(output=f"Session shared to: {path}")


def _ext(fmt: str) -> str:
    return {"markdown": "md", "json": "json", "html": "html"}.get(fmt, "txt")


def _format_messages(messages: list, fmt: str) -> str:
    from lucy.core.message import UserMessage, AssistantMessage
    if fmt == "json":
        entries = []
        for m in messages:
            role = "user" if isinstance(m, UserMessage) else "assistant"
            entries.append({"role": role, "content": m.get_text()})
        return json.dumps(entries, indent=2)

    elif fmt == "html":
        lines = ["<html><body>"]
        for m in messages:
            role = "user" if isinstance(m, UserMessage) else "assistant"
            lines.append(f'<div class="{role}"><strong>{role}:</strong><p>{m.get_text()}</p></div>')
        lines.append("</body></html>")
        return "\n".join(lines)

    else:  # markdown
        lines = ["# Lucy Code Session\n"]
        for m in messages:
            role = "User" if isinstance(m, UserMessage) else "Assistant"
            lines.append(f"## {role}\n\n{m.get_text()}\n")
        return "\n".join(lines)


def get_commands() -> list[Command]:
    return [SessionCommand(), ResumeCommand(), RenameCommand(),
            ExportCommand(), TagCommand(), ShareCommand()]
