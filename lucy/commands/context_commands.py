"""
Context commands — /context, /files, /compact, /add-dir.
"""

from __future__ import annotations

import os
from typing import Any

from lucy.core.commands import Command, CommandResult


class ContextCommand(Command):
    @property
    def name(self) -> str: return "context"
    @property
    def aliases(self) -> list[str]: return ["ctx"]
    @property
    def description(self) -> str: return "Show context window usage"
    @property
    def usage(self) -> str: return "/context — show token usage and context stats"

    async def execute(self, args: str, state: Any) -> CommandResult:
        msg_count = len(state.messages)
        total_chars = sum(len(m.get_text()) for m in state.messages)
        est_tokens = total_chars // 4  # rough estimate

        lines = [
            "Context Window:",
            f"  Messages: {msg_count}",
            f"  Characters: {total_chars:,}",
            f"  Estimated tokens: {est_tokens:,}",
            f"  Model: {state.model}",
            f"  Working directory: {state.cwd}",
        ]
        if hasattr(state, 'additional_dirs') and state.additional_dirs:
            lines.append(f"  Additional dirs: {', '.join(state.additional_dirs)}")
        return CommandResult(output="\n".join(lines))


class FilesCommand(Command):
    @property
    def name(self) -> str: return "files"
    @property
    def description(self) -> str: return "List files mentioned in conversation"
    @property
    def usage(self) -> str: return "/files — show all files referenced"

    async def execute(self, args: str, state: Any) -> CommandResult:
        import re
        files = set()
        for m in state.messages:
            text = m.get_text()
            # Match file paths
            for match in re.finditer(r'[\w./\\-]+\.\w+', text):
                path = match.group()
                if os.path.exists(os.path.join(state.cwd, path)):
                    files.add(path)
        if files:
            lines = ["Files referenced in conversation:\n"]
            for f in sorted(files):
                size = ""
                full = os.path.join(state.cwd, f)
                try:
                    s = os.path.getsize(full)
                    size = f" ({s:,} bytes)"
                except OSError:
                    pass
                lines.append(f"  📄 {f}{size}")
            return CommandResult(output="\n".join(lines))
        return CommandResult(output="No files referenced in conversation.")


class CompactCommand(Command):
    @property
    def name(self) -> str: return "compact"
    @property
    def description(self) -> str: return "Compact conversation to save tokens"
    @property
    def usage(self) -> str: return "/compact — summarize and compact messages"

    async def execute(self, args: str, state: Any) -> CommandResult:
        from lucy.core.message import UserMessage, AssistantMessage
        if len(state.messages) < 4:
            return CommandResult(output="Conversation too short to compact.")

        # Keep first message, compact middle, keep last 2
        before = len(state.messages)
        before_chars = sum(len(m.get_text()) for m in state.messages)

        # Build summary of middle messages
        middle = state.messages[1:-2]
        summary_parts = []
        for m in middle:
            role = "User" if isinstance(m, UserMessage) else "Assistant"
            text = m.get_text()[:200]
            summary_parts.append(f"[{role}]: {text}")

        summary = "Previous conversation summary:\n" + "\n".join(summary_parts)

        from lucy.core.message import create_user_message, CompactBoundaryMessage
        boundary = CompactBoundaryMessage(summary=summary)

        kept = [state.messages[0], boundary] + state.messages[-2:]
        state.messages = kept

        after_chars = sum(len(m.get_text()) for m in state.messages)
        saved = before_chars - after_chars

        return CommandResult(
            output=f"Compacted: {before} → {len(kept)} messages\n"
                   f"Saved: ~{saved:,} characters (~{saved//4:,} tokens)"
        )


class AddDirCommand(Command):
    @property
    def name(self) -> str: return "add-dir"
    @property
    def aliases(self) -> list[str]: return ["adddir"]
    @property
    def description(self) -> str: return "Add an additional working directory"
    @property
    def usage(self) -> str: return "/add-dir <path> — add directory to scope"

    async def execute(self, args: str, state: Any) -> CommandResult:
        path = args.strip()
        if not path:
            return CommandResult(error="Usage: /add-dir <path>")
        if not os.path.isabs(path):
            path = os.path.join(state.cwd, path)
        if not os.path.isdir(path):
            return CommandResult(error=f"Not a directory: {path}")
        if not hasattr(state, 'additional_dirs'):
            state.additional_dirs = []
        if path not in state.additional_dirs:
            state.additional_dirs.append(path)
        return CommandResult(output=f"Added directory: {path}\nTotal dirs: {len(state.additional_dirs) + 1}")


def get_commands() -> list[Command]:
    return [ContextCommand(), FilesCommand(), CompactCommand(), AddDirCommand()]
