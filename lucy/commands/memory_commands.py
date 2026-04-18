"""
Memory commands — /memory, /thinkback.
"""

from __future__ import annotations

import json
import os
import time
from typing import Any

from lucy.core.commands import Command, CommandResult


class MemoryCommand(Command):
    @property
    def name(self) -> str: return "memory"
    @property
    def aliases(self) -> list[str]: return ["mem"]
    @property
    def description(self) -> str: return "Manage cross-session memories"
    @property
    def usage(self) -> str: return "/memory [list|add|clear] [content]"

    async def execute(self, args: str, state: Any) -> CommandResult:
        parts = args.strip().split(None, 1)
        action = parts[0] if parts else "list"
        content = parts[1] if len(parts) > 1 else ""

        mem_file = os.path.join(os.path.expanduser("~/.lucycode"), "memories.json")

        if action == "list":
            memories = _load_memories(mem_file)
            if not memories:
                return CommandResult(output="No memories stored.\nUse /memory add <content> to add.")
            lines = ["🧠 Memories:\n"]
            for i, m in enumerate(memories, 1):
                ts = time.strftime("%m/%d", time.localtime(m.get("timestamp", 0)))
                lines.append(f"  {i}. [{ts}] {m['content'][:100]}")
            return CommandResult(output="\n".join(lines))

        if action == "add":
            if not content:
                return CommandResult(error="Usage: /memory add <content>")
            memories = _load_memories(mem_file)
            memories.append({"content": content, "timestamp": time.time()})
            _save_memories(mem_file, memories)
            return CommandResult(output=f"✅ Memory added ({len(memories)} total)")

        if action == "clear":
            _save_memories(mem_file, [])
            return CommandResult(output="✅ All memories cleared")

        if action == "search":
            if not content:
                return CommandResult(error="Usage: /memory search <query>")
            memories = _load_memories(mem_file)
            matches = [m for m in memories if content.lower() in m["content"].lower()]
            if matches:
                lines = [f"Found {len(matches)} matching memories:\n"]
                for m in matches:
                    lines.append(f"  • {m['content'][:100]}")
                return CommandResult(output="\n".join(lines))
            return CommandResult(output="No matching memories found.")

        return CommandResult(error=f"Unknown action: {action}")


class ThinkbackCommand(Command):
    @property
    def name(self) -> str: return "thinkback"
    @property
    def description(self) -> str: return "Review thinking blocks from the conversation"

    async def execute(self, args: str, state: Any) -> CommandResult:
        from lucy.core.message import AssistantMessage
        thinking_blocks = []
        for m in state.messages:
            if isinstance(m, AssistantMessage):
                text = m.get_thinking_text()
                if text:
                    thinking_blocks.append(text[:500])

        if not thinking_blocks:
            return CommandResult(output="No thinking blocks in this conversation.")

        lines = [f"🧠 Thinking Blocks ({len(thinking_blocks)}):\n"]
        for i, block in enumerate(thinking_blocks, 1):
            lines.append(f"--- Block {i} ---")
            lines.append(block)
            lines.append("")

        return CommandResult(output="\n".join(lines))


def _load_memories(path: str) -> list[dict]:
    if os.path.exists(path):
        try:
            with open(path) as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            pass
    return []


def _save_memories(path: str, memories: list[dict]):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        json.dump(memories, f, indent=2)


def get_commands() -> list[Command]:
    return [MemoryCommand(), ThinkbackCommand()]
